#!/usr/bin/python3
"""
Same as collect_and_analyze_pod_logs.py for steps 1–3 (pod list, baseline, collect logs).
Step 4: send each collected log file to a REMOTE Ollama server for end-to-end analysis.
Ollama returns a list of errors with explanations. Step 5: write report.

Use when Ollama runs on a bigger remote host. No grep/heuristic;
analysis is done entirely by the remote model. Good for offloading work to a powerful machine.

Default remote Ollama: http://10.9.95.129:11434 (override with OLLAMA_HOST). Optional: POD_LOGS_DIR, POD_LOGS_REPORT.
Self-contained: no imports from collect_and_analyze_pod_logs.
"""

import os
import sys
import re
import json
import gzip
import subprocess
import time as time_module
import datetime
import urllib.error
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    requests = None

# --- Config (override with env) ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGS_DIR = os.path.join(_SCRIPT_DIR, 'collected_pod_logs')
MAX_WORKERS = int(os.environ.get('POD_LOGS_MAX_WORKERS', '16'))

# --- Remote Ollama config (default: your remote server; override with OLLAMA_HOST) ---
DEFAULT_OLLAMA_HOST = 'http://10.9.95.129:11434'
OLLAMA_HOST = (os.environ.get('OLLAMA_HOST') or DEFAULT_OLLAMA_HOST).strip().rstrip('/')

OLLAMA_MODEL = os.environ.get('POD_LOGS_OLLAMA_MODEL', 'llama3.2')
# Connect timeout: max seconds to establish connection and send request body. Read timeout: max seconds to wait for Ollama response (analysis).
# With 'requests' library we report which one fired; with urllib only a single combined timeout is used.
OLLAMA_CONNECT_TIMEOUT = int(os.environ.get('POD_LOGS_OLLAMA_CONNECT_TIMEOUT', '90'))
OLLAMA_READ_TIMEOUT = int(os.environ.get('POD_LOGS_OLLAMA_TIMEOUT', '300'))   # legacy env name for read timeout
REMOTE_OLLAMA_MAX_LOG_CHARS = 14000
REMOTE_OLLAMA_MAX_PREDICT = 2000
# Compress request body with gzip to reduce network transfer. Set POD_LOGS_OLLAMA_GZIP=0 if server rejects it.
OLLAMA_USE_GZIP = os.environ.get('POD_LOGS_OLLAMA_GZIP', '1').strip().lower() in ('1', 'true', 'yes')
# Max concurrent requests to Ollama (threads). Increase for faster runs; reduce if server is overwhelmed.
OLLAMA_MAX_CONCURRENT = int(os.environ.get('POD_LOGS_OLLAMA_MAX_CONCURRENT', '6'))

# --- Colors ---
_USE_COLOR = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
_RESET = '\033[0m'
_CYAN = '\033[36m'
_GREEN = '\033[32m'
_YELLOW = '\033[33m'
_BLUE = '\033[34m'
_DIM = '\033[2m'

_REPORT_BOLD = '\033[1m'
_REPORT_CYAN = '\033[36m'
_REPORT_YELLOW = '\033[33m'
_REPORT_DIM = '\033[2m'
_REPORT_RESET = '\033[0m'


def _c(style, msg):
    return style + msg + _RESET if _USE_COLOR and style else msg


def _r(style, s):
    return style + s + _REPORT_RESET


def run(cmd, capture=True, timeout=300):
    try:
        out = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=timeout)
        return (out.returncode == 0, (out.stdout or '') + (out.stderr or ''))
    except subprocess.TimeoutExpired:
        return (False, 'Timeout')
    except Exception as e:
        return (False, str(e))


def get_line_date(line):
    try:
        m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?', line)
        if m:
            ts = m.group().rstrip('Z')
            if '.' in ts:
                ts = ts.split('.')[0]
            dt = datetime.datetime.strptime(ts.replace('T', ' '), '%Y-%m-%d %H:%M:%S')
            return (dt, None)
        m = re.search(r'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}', line)
        if m:
            s = m.group()
            s = s[:10] + ' ' + s[11:]
            dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
            return (dt, None)
        m = re.search(r'\d{4}/\d{2}/\d{2}.\d{2}:\d{2}:\d{2}', line)
        if m:
            dt = datetime.datetime.strptime(m.group(), '%Y/%m/%d %H:%M:%S')
            return (dt, None)
        m = re.search(r'\d{2}\s\w{3}\s\d{4}\s\d{2}:\d{2}:\d{2}', line)
        if m:
            dt = datetime.datetime.strptime(m.group(), '%d %b %Y %H:%M:%S')
            return (dt, None)
        return (None, 'No known timestamp format')
    except Exception as e:
        return (None, str(e))


def get_pods():
    ok, out = run('oc get pods -A --no-headers 2>/dev/null')
    if not ok:
        return []
    pods = []
    for raw in out.splitlines():
        parts = raw.split()
        if len(parts) >= 2:
            pods.append((parts[0].strip(), parts[1].strip()))
    return pods


def safe_filename(namespace, pod_name):
    return (namespace + '_' + pod_name + '.log').replace('/', '-')


def group_pods_by_component(pods):
    groups = {}
    for ns, name in pods:
        if not name:
            continue
        part = name.split('-')[0] if '-' in name else name
        component = part.lower()
        groups.setdefault(component, []).append((ns, name))
    return sorted(groups.items(), key=lambda x: x[0])


def _baseline_one_pod(args):
    ns, name, tail_lines = args
    cmd = 'oc logs -n {} {} --timestamps --all-containers --tail={} 2>/dev/null'.format(ns, name, tail_lines)
    ok, out = run(cmd, timeout=15)
    if not ok or not out.strip():
        return None
    latest = None
    for line in out.splitlines():
        dt, _ = get_line_date(line)
        if dt and (latest is None or dt > latest):
            latest = dt
    return latest


def get_baseline_quick(pods, tail_lines=10):
    n = len(pods)
    print(_c(_YELLOW, '  [baseline]') + ' Fetching last {} lines from {} pods ({} workers)...'.format(tail_lines, n, min(MAX_WORKERS, n)))
    start = time_module.time()
    latest = None
    done = 0
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, n)) as ex:
        futures = {ex.submit(_baseline_one_pod, (ns, name, tail_lines)): (ns, name) for ns, name in pods}
        for fut in as_completed(futures):
            done += 1
            if done % 10 == 0 or done == n:
                print(_c(_YELLOW, '  [baseline]') + ' {}/{} pods checked...'.format(done, n), flush=True)
            try:
                dt = fut.result()
                if dt and (latest is None or dt > latest):
                    latest = dt
            except Exception:
                pass
    elapsed = time_module.time() - start
    ts_str = latest.strftime('%Y-%m-%d %H:%M:%S') if latest else 'none'
    print(_c(_GREEN, '  [baseline] Done in {:.1f}s.').format(elapsed) + ' Latest timestamp: ' + _c(_BLUE, ts_str) + '.')
    return latest


def _collect_one_pod(args):
    ns, name, path, since_iso = args
    if since_iso:
        cmd = 'oc logs -n {} {} --timestamps --all-containers --since-time={} > {} 2>/dev/null'.format(ns, name, since_iso, path)
    else:
        cmd = 'oc logs -n {} {} --timestamps --all-containers > {} 2>/dev/null'.format(ns, name, path)
    run(cmd)
    return path if os.path.isfile(path) else None


def collect_logs_since(logs_dir, pods, since_iso=None):
    n = len(pods)
    print(_c(_YELLOW, '  [collect]') + ' Fetching logs for {} pods ({} workers)...'.format(n, min(MAX_WORKERS, n)), flush=True)
    start = time_module.time()
    tasks = [(ns, name, os.path.join(logs_dir, safe_filename(ns, name)), since_iso) for ns, name in pods]
    created = []
    done = 0
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, n)) as ex:
        futures = {ex.submit(_collect_one_pod, t): t for t in tasks}
        for fut in as_completed(futures):
            done += 1
            if done % 5 == 0 or done == n:
                print(_c(_YELLOW, '  [collect]') + ' {}/{} pods written...'.format(done, n), flush=True)
            try:
                path = fut.result()
                if path:
                    created.append(path)
            except Exception:
                pass
    print(_c(_GREEN, '  [collect] Done in {:.1f}s. {} log files created.').format(time_module.time() - start, len(created)))
    return created


def _filter_log_lines_after_since(raw_content, since_dt):
    """Keep only lines with timestamp >= since_dt (or no parseable timestamp). Reduces payload sent to Ollama."""
    if since_dt is None or not raw_content:
        return raw_content
    kept = []
    for line in raw_content.splitlines(keepends=True):
        dt, _ = get_line_date(line)
        if dt is None:
            kept.append(line)  # no timestamp: keep (e.g. continuation line)
        elif dt >= since_dt:
            kept.append(line)
    return ''.join(kept)


def _analyze_one_log_via_ollama(path, since_dt=None, on_status=None):
    """Send one log file to remote Ollama; return list of (snippet, explanation) or empty list on failure. Only lines >= since_dt are sent. Optional on_status(msg) is called with status strings (e.g. 'Sent, waiting for response')."""
    try:
        with open(path, 'r', errors='replace') as f:
            raw = f.read()
    except Exception:
        return []
    raw = _filter_log_lines_after_since(raw, since_dt)
    if not raw.strip():
        return []
    snippet = raw[:REMOTE_OLLAMA_MAX_LOG_CHARS]
    if len(raw) > REMOTE_OLLAMA_MAX_LOG_CHARS:
        snippet += '\n\n... [log truncated for context limit]'

    prompt = '''You are analyzing a pod log for errors. Look for: ERROR, CRITICAL, Traceback, Exception, failed, failure, CrashLoopBackOff, timeout, refused, denied, FATAL, and similar. Do not skip real issues.

For EACH error or failure you find, you MUST output exactly this format (nothing else between errors):
SNIPPET:
<paste the exact log lines that show the error>
EXPLANATION:
<one or two sentences: what it is and what impact it can have>
---

Use --- to separate multiple errors. If there are truly no errors or failures in the log, reply with exactly: NO_ERRORS_FOUND

Log file path: ''' + path + '''

Log content:
''' + snippet

    url = OLLAMA_HOST + '/api/generate'
    payload = {
        'model': OLLAMA_MODEL,
        'prompt': prompt,
        'stream': False,
        'options': {'num_predict': REMOTE_OLLAMA_MAX_PREDICT},
    }
    body_raw = json.dumps(payload).encode('utf-8')
    use_gzip = OLLAMA_USE_GZIP and len(body_raw) > 256
    if use_gzip:
        body_to_send = gzip.compress(body_raw)
        headers = {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}
    else:
        body_to_send = body_raw
        headers = {'Content-Type': 'application/json'}

    def _parse_reply(reply):
        if not reply:
            return []
        if 'NO_ERRORS_FOUND' in reply.upper() and len(reply.strip()) < 50:
            return []
        entries = []
        for block in reply.split('---'):
            block = block.strip()
            if not block or block.upper() == 'NO_ERRORS_FOUND':
                continue
            snip = None
            expl = None
            if 'EXPLANATION:' in block:
                a, b = block.split('EXPLANATION:', 1)
                snip = a.replace('SNIPPET:', '').strip()
                expl = b.strip().split('\n')[0].strip()
            elif 'SNIPPET:' in block:
                snip = block.replace('SNIPPET:', '').strip()
                expl = '(no explanation parsed)'
            if snip:
                entries.append((snip[:800], expl or '(no explanation)'))
        if not entries and reply and 'NO_ERRORS_FOUND' not in reply.upper():
            entries.append((reply[:800], '(Ollama replied but not in SNIPPET:/EXPLANATION: format; raw reply above)'))
        return entries

    def _do_request(data, req_headers):
        """Returns (response_data dict, None) on success or (None, error_string) on failure. Error string distinguishes connect vs read timeout when requests is used."""
        if requests is not None:
            try:
                r = requests.post(
                    url,
                    data=data,
                    headers=req_headers,
                    timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT),
                )
                r.raise_for_status()
                return (r.json(), None)
            except requests.exceptions.ConnectTimeout:
                return (None, 'connection/upload timed out (request may not have reached Ollama); try increasing POD_LOGS_OLLAMA_CONNECT_TIMEOUT')
            except requests.exceptions.ReadTimeout:
                return (None, 'Ollama took too long to respond (analysis timeout); request was sent and received; try increasing POD_LOGS_OLLAMA_TIMEOUT or reducing log size')
            except requests.exceptions.RequestException as e:
                return (None, str(e))
        else:
            try:
                req = urllib.request.Request(url, data=data, method='POST', headers=req_headers)
                with urllib.request.urlopen(req, timeout=OLLAMA_CONNECT_TIMEOUT + OLLAMA_READ_TIMEOUT) as resp:
                    return (json.loads(resp.read().decode('utf-8')), None)
            except Exception as e:
                err = str(e).lower()
                if 'timed out' in err or 'timeout' in err:
                    return (None, 'timed out (install "requests" to distinguish connect vs analysis timeout)')
                return (None, str(e))

    try:
        if on_status:
            on_status('Sent, waiting for response')
        data, err = _do_request(body_to_send, headers)
        if err:
            if use_gzip and any(x in err for x in ('400', '415', '422', 'Bad Request', 'Unsupported Media')):
                data, err = _do_request(body_raw, {'Content-Type': 'application/json'})
                if err:
                    return [('(Ollama request failed: {})'.format(err), '')]
            else:
                return [('(Ollama request failed: {})'.format(err), '')]
        reply = (data.get('response') or '').strip()
        return _parse_reply(reply)
    except (json.JSONDecodeError, KeyError) as e:
        return [('(Ollama request failed: {})'.format(e), '')]


def main():
    logs_dir = os.environ.get('POD_LOGS_DIR', DEFAULT_LOGS_DIR)
    report_file = os.environ.get('POD_LOGS_REPORT', os.path.join(_SCRIPT_DIR, 'pod_logs_remote_ollama_report.txt'))
    main_start = time_module.time()

    print(_c(_CYAN, '=' * 60))
    print(_c(_CYAN, '[1/5] Pod list (same as standard script)'))
    print(_c(_CYAN, '=' * 60))
    print(_c(_DIM, 'Collecting pod list (oc get pods -A)...'), flush=True)
    pods = get_pods()
    if not pods:
        print(_c(_YELLOW, 'No pods found or oc not available. Exiting.'))
        sys.exit(1)
    print(_c(_GREEN, 'Found {} pods.').format(len(pods)))

    groups = group_pods_by_component(pods)
    total = len(pods)
    print(_c(_DIM, 'Choose which group of pods to analyze (components in alphabetical order):'))
    for i, (component, group_pods) in enumerate(groups, 1):
        n = len(group_pods)
        print('  {}) {} ({} pod{})'.format(i, component, n, 's' if n != 1 else ''))
    print('  {}) All pods ({} pods)'.format(len(groups) + 1, total))
    choice = input(_c(_DIM, 'Choice [1-{}]: ').format(len(groups) + 1)).strip()
    try:
        idx = int(choice)
        if 1 <= idx <= len(groups):
            pods = groups[idx - 1][1]
            print(_c(_GREEN, 'Selected group "{}": {} pods.').format(groups[idx - 1][0], len(pods)))
        elif idx == len(groups) + 1:
            print(_c(_GREEN, 'Selected all pods: {}.').format(total))
        else:
            pods = groups[0][1]
            print(_c(_YELLOW, 'Invalid choice; using first group "{}".').format(groups[0][0]))
    except ValueError:
        pods = groups[0][1]
        print(_c(_YELLOW, 'Invalid input; using first group "{}".').format(groups[0][0]))
    if not pods:
        print(_c(_YELLOW, 'No pods to analyze. Exiting.'))
        sys.exit(0)

    print('')
    print(_c(_CYAN, '[2/5] Baseline timestamp'))
    print(_c(_DIM, '-' * 60))
    print(_c(_DIM, 'Getting latest log timestamp (oc logs --tail=10 per pod)...'), flush=True)
    baseline = get_baseline_quick(pods)
    if baseline is None:
        print(_c(_YELLOW, 'Could not detect any timestamp. Using "since" = 24h ago.'))
        since_dt = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        since_iso = None
    else:
        baseline_str = baseline.strftime('%Y-%m-%d %H:%M:%S')
        print('Last logged message was at: ' + _c(_CYAN, baseline_str) + '.')
        print(_c(_DIM, 'Choose "since" time (messages after this will be analyzed):'))
        print('  1) 2h back')
        print('  2) 1h back')
        print('  3) 30m back')
        print('  4) Custom (enter minutes, e.g. 45)')
        choice = input(_c(_DIM, 'Choice [1-4]: ')).strip() or '1'
        if choice == '1':
            delta = datetime.timedelta(hours=2)
        elif choice == '2':
            delta = datetime.timedelta(hours=1)
        elif choice == '3':
            delta = datetime.timedelta(minutes=30)
        elif choice == '4':
            try:
                mins = int(input('Minutes back: ').strip())
                delta = datetime.timedelta(minutes=max(0, mins))
            except Exception:
                delta = datetime.timedelta(hours=1)
        else:
            delta = datetime.timedelta(hours=2)
        since_dt = baseline - delta
        since_iso = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    since_str = since_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(_c(_GREEN, 'Analyzing logs since: ') + _c(_CYAN, since_str) + '.')

    print('')
    print(_c(_CYAN, '[3/5] Collect logs'))
    print(_c(_DIM, '-' * 60))
    if os.path.isdir(logs_dir):
        for f in os.listdir(logs_dir):
            os.remove(os.path.join(logs_dir, f))
    else:
        os.makedirs(logs_dir, exist_ok=True)
    print(_c(_DIM, 'Logs directory: ') + _c(_CYAN, logs_dir))
    log_paths = collect_logs_since(logs_dir, pods, since_iso)

    print('')
    print(_c(_CYAN, '[4/5] Send logs to REMOTE Ollama for analysis'))
    print(_c(_DIM, '-' * 60))
    print(_c(_DIM, 'Remote Ollama: {}').format(OLLAMA_HOST), flush=True)
    if requests is not None:
        print(_c(_DIM, 'Timeouts: connect/send {}s, read (analysis) {}s (POD_LOGS_OLLAMA_CONNECT_TIMEOUT / POD_LOGS_OLLAMA_TIMEOUT).').format(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT), flush=True)
    else:
        print(_c(_DIM, 'Timeout: {}s total (install "requests" for separate connect vs analysis timeout).').format(OLLAMA_CONNECT_TIMEOUT + OLLAMA_READ_TIMEOUT), flush=True)
    if OLLAMA_USE_GZIP:
        print(_c(_DIM, 'Request body: gzip compressed (set POD_LOGS_OLLAMA_GZIP=0 to disable).'), flush=True)
    n_concurrent = min(OLLAMA_MAX_CONCURRENT, len(log_paths)) if log_paths else 0
    print(_c(_DIM, 'Sending log files to Ollama in parallel ({} workers; only lines since {})...').format(n_concurrent, since_str), flush=True)
    start_analyze = time_module.time()
    results = {}
    sorted_paths = sorted(log_paths)
    done_count = [0]
    lock = threading.Lock()

    def _status(msg, p):
        with lock:
            print(_c(_DIM, '  {}').format(msg) + ' ' + os.path.basename(p) + '...', flush=True)

    def _analyze_and_count(path):
        _status('Sending', path)
        on_status = lambda msg: _status(msg, path)
        out = _analyze_one_log_via_ollama(path, since_dt, on_status=on_status)
        with lock:
            done_count[0] += 1
            print(_c(_YELLOW, '  [{}]/{}').format(done_count[0], len(log_paths)) + ' ' + _c(_GREEN, 'received') + ' ' + os.path.basename(path), flush=True)
        return (path, out)

    path_by_future = {}
    with ThreadPoolExecutor(max_workers=n_concurrent or 1) as ex:
        for p in sorted_paths:
            path_by_future[ex.submit(_analyze_and_count, p)] = p
        for fut in as_completed(path_by_future):
            path = path_by_future[fut]
            try:
                _, entries = fut.result()
                results[path] = entries
            except Exception as e:
                results[path] = [('(Ollama request failed: {})'.format(e), '')]
    elapsed = time_module.time() - start_analyze
    print(_c(_GREEN, '  Done in {:.1f}s.').format(elapsed))

    print('')
    print(_c(_CYAN, '[5/5] Write report'))
    print(_c(_DIM, '-' * 60))
    with open(report_file, 'w') as f:
        f.write(_r(_REPORT_DIM, '--- Pod logs analyzed by REMOTE Ollama (end-to-end). Not from local grep. ---') + '\n')
        f.write(_r(_REPORT_DIM, 'Since time:') + ' {}\n'.format(since_str))
        f.write(_r(_REPORT_DIM, 'Logs directory:') + ' {}\n'.format(os.path.abspath(logs_dir)))
        f.write(_r(_REPORT_DIM, 'Remote Ollama:') + ' {}\n'.format(OLLAMA_HOST))
        f.write(_r(_REPORT_DIM, 'Report generated:') + ' {}\n\n'.format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write(_r(_REPORT_BOLD, '=' * 80) + '\n')
        f.write(_r(_REPORT_BOLD, ' ERROR BLOCKS BY LOG FILE (from remote Ollama) ') + '\n')
        f.write(_r(_REPORT_BOLD, '=' * 80) + '\n\n')

        def _is_request_failure(entries):
            if len(entries) != 1:
                return False
            snippet = entries[0][0]
            return snippet.startswith('(Ollama request failed:')

        for path in sorted(results.keys()):
            entries = results[path]
            f.write(_r(_REPORT_CYAN + _REPORT_BOLD, '--- Log file: {} ---').format(path) + '\n')
            if _is_request_failure(entries):
                f.write(_r(_REPORT_YELLOW + _REPORT_BOLD, 'Analysis skipped: ') + entries[0][0] + '\n')
                f.write(_r(_REPORT_DIM, 'Tip: increase POD_LOGS_OLLAMA_TIMEOUT (read, current {}s) or POD_LOGS_OLLAMA_CONNECT_TIMEOUT, or reduce POD_LOGS_OLLAMA_MAX_CONCURRENT.\n\n').format(OLLAMA_READ_TIMEOUT))
            else:
                f.write(_r(_REPORT_BOLD, 'Errors found by Ollama:') + ' {}\n\n'.format(len(entries)))
                for j, (snippet, explanation) in enumerate(entries, 1):
                    f.write(_r(_REPORT_YELLOW + _REPORT_BOLD, 'Error {}:').format(j) + '\n')
                    f.write(_r(_REPORT_DIM, '[Ollama — not from log] ') + explanation + '\n')
                    f.write(snippet + '\n\n')
                if not entries:
                    f.write(_r(_REPORT_DIM, '(No errors reported by Ollama for this file.)') + '\n\n')
            f.write(_r(_REPORT_BOLD, '=' * 80) + '\n\n')

    total_elapsed = time_module.time() - main_start
    total_errors = sum(
        len(v) for v in results.values()
        if not (len(v) == 1 and v[0][0].startswith('(Ollama request failed:'))
    )
    print(_c(_GREEN, 'Report written to: ') + _c(_CYAN, report_file))
    print(_c(_GREEN, 'Total errors reported by Ollama: {} across {} log files.').format(total_errors, len(results)))
    print(_c(_DIM, 'Total time: ') + _c(_REPORT_BOLD, '{:.1f}s').format(total_elapsed))


if __name__ == '__main__':
    main()
