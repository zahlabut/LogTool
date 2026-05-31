#!/usr/bin/python3
"""
Scan all pods (oc get pods -A), find unhealthy ones, oc describe each,
write a single text report with highlighted problem lines (view with less -R).
Run from LogToolMain or directly.
"""

import os
import sys
import re
import datetime
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import logtool_common as common

# Pod STATUS values (oc get pods) that indicate a problem.
_BAD_STATUS_EXACT = frozenset({
    'error', 'crashloopbackoff', 'imagepullbackoff', 'errimagepull',
    'createcontainererror', 'createcontainerconfigerror', 'invalidimagename',
    'oomkilled', 'evicted', 'failed', 'unknown', 'containerstatusunknown',
    'runcontainererror', 'poststarthookerror', 'prestarthookerror',
    'nodeaffinity', 'unschedulable',
})

# Init:Error, Init:CrashLoopBackOff, etc.
_INIT_BAD_MARKERS = (
    'error', 'crashloop', 'imagepull', 'backoff', 'createcontainer', 'failed',
)

# Lines from oc describe to always prefer in the report (case-insensitive substring).
_DESCRIBE_SIGNAL_KEYWORDS = (
    'warning', 'failed', 'error', 'back-off', 'backoff', 'crashloop',
    'imagepull', 'errimagepull', 'oomkilled', 'evicted', 'unhealthy',
    'exit code', 'terminated', 'waiting', 'reason:', 'message:',
    'failedscheduling', 'insufficient', 'forbidden', 'not found',
    'pull access', 'no pull secret', 'secret not found', 'connection refused',
    'liveness probe', 'readiness probe', 'readiness probe failed',
    'containercreating', 'pod sandbox', 'mountvolume', 'failedmount',
    'node not ready', 'taint', 'unschedulable', 'quota', 'limit',
)


def _parse_pod_line(line):
    """Parse oc get pods -A --no-headers line. Returns tuple or None."""
    parts = line.split()
    if len(parts) < 5:
        return None
    ns, name, ready, status = parts[0], parts[1], parts[2], parts[3]
    restarts = parts[4]
    age = ' '.join(parts[5:]) if len(parts) > 5 else ''
    return ns, name, ready, status, restarts, age


def _is_problem_pod(ready, status):
    """
    Return (is_bad, reason_string) for oc get pods STATUS/READY.
    """
    st = (status or '').strip()
    st_lower = st.lower()
    if st_lower in _BAD_STATUS_EXACT:
        return True, st
    if st_lower.startswith('init:'):
        tail = st[5:].lower()
        if any(m in tail for m in _INIT_BAD_MARKERS):
            return True, st
    if st_lower == 'running' and ready and '/' in ready:
        got_s, want_s = ready.split('/', 1)
        try:
            if int(got_s) < int(want_s):
                return True, 'Running (not ready: {})'.format(ready)
        except ValueError:
            pass
    return False, None


def _get_all_pods():
    ok, out = common.run('oc get pods -A --no-headers 2>/dev/null', timeout=120)
    if not ok or not out.strip():
        return []
    pods = []
    for line in out.splitlines():
        parsed = _parse_pod_line(line.strip())
        if parsed:
            pods.append(parsed)
    return pods


def _describe_pod(ns, name):
    ok, out = common.run(
        'oc describe pod -n {} {} 2>/dev/null'.format(ns, name),
        timeout=90,
    )
    return out if ok and out.strip() else ''


def _line_is_signal(line):
    low = line.lower()
    if common.line_has_error_keyword(line):
        return True
    return any(kw in low for kw in _DESCRIBE_SIGNAL_KEYWORDS)


def _extract_section(lines, header):
    """Return lines belonging to section starting with header (e.g. 'Events:')."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header or line.startswith(header):
            start = i + 1
            break
    if start is None:
        return []
    collected = []
    for line in lines[start:]:
        if line and not line.startswith(' ') and not line.startswith('\t') and line.endswith(':'):
            break
        collected.append(line.rstrip())
    return collected


def _extract_describe_details(describe_text):
    """
    Pull Events, bad Conditions, and other high-signal lines from oc describe output.
    Returns list of (section_label, line) tuples.
    """
    if not describe_text:
        return []
    lines = describe_text.splitlines()
    out = []

    for line in lines[:30]:
        s = line.strip()
        if s.startswith('Status:') and s.lower() != 'status: running':
            out.append(('Status', line.rstrip()))

    cond_lines = _extract_section(lines, 'Conditions:')
    for line in cond_lines:
        if not line.strip():
            continue
        if re.search(r'\bFalse\b', line) or re.search(r'\bUnknown\b', line) or _line_is_signal(line):
            out.append(('Conditions', line.rstrip()))

    in_containers = False
    for line in lines:
        if line.startswith('Containers:'):
            in_containers = True
            continue
        if in_containers:
            if line and not line.startswith(' ') and not line.startswith('\t') and line.endswith(':'):
                in_containers = False
                continue
            if _line_is_signal(line):
                out.append(('Containers', line.rstrip()))

    event_lines = _extract_section(lines, 'Events:')
    if event_lines:
        for line in event_lines:
            if line.strip():
                out.append(('Events', line.rstrip()))
    else:
        for line in lines:
            if _line_is_signal(line):
                label = 'Details'
                if 'Type' in line and 'Reason' in line:
                    continue
                out.append((label, line.rstrip()))

    seen = set()
    deduped = []
    for label, text in out:
        key = (label, text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((label, text))
    return deduped


def _first_summary_line(details, status, ready, restarts):
    bits = []
    if status:
        bits.append('STATUS={}'.format(status))
    if ready:
        bits.append('READY={}'.format(ready))
    if restarts and restarts != '0':
        bits.append('RESTARTS={}'.format(restarts))
    for label, text in details:
        if label == 'Events' and ('Warning' in text or 'Failed' in text or 'Error' in text):
            cleaned = re.sub(r'\s+', ' ', text.strip())
            bits.append(cleaned[:240])
            break
    if len(bits) <= 3:
        for label, text in details:
            if label in ('Conditions', 'Containers') and _line_is_signal(text):
                cleaned = re.sub(r'\s+', ' ', text.strip())
                bits.append(cleaned[:240])
                break
    return ' | '.join(bits)


def _describe_one(args):
    ns, name, ready, status, restarts, age, reason = args
    describe = _describe_pod(ns, name)
    details = _extract_describe_details(describe)
    summary = _first_summary_line(details, status, ready, restarts)
    return {
        'ns': ns,
        'name': name,
        'ready': ready,
        'status': status,
        'restarts': restarts,
        'age': age,
        'reason': reason,
        'summary': summary,
        'details': details,
        'describe_ok': bool(describe),
    }


def _write_report(report_path, scanned, problems, elapsed):
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(common.r(common.REPORT_BOLD, 'Pod health report') + '\n')
        f.write(common.r(common.REPORT_DIM, 'Generated: ') + ts + '\n')
        f.write(common.r(common.REPORT_DIM, 'Pods scanned: ') + str(scanned) + '\n')
        f.write(common.r(common.REPORT_DIM, 'Problematic pods: ') + str(len(problems)) + '\n')
        f.write(common.r(common.REPORT_DIM, 'View: ') + 'less -R ' + report_path + '\n')
        f.write(common.r(common.REPORT_DIM, 'Problem keywords highlighted in red (use less -R).\n\n'))

        if not problems:
            f.write('(No problematic pods detected by STATUS/READY checks.)\n')
            return

        for idx, pod in enumerate(problems, 1):
            header = '{}/{}  {}/{}'.format(idx, len(problems), pod['ns'], pod['name'])
            sep = '=' * min(78, max(len(header), 40))
            f.write(common.r(common.REPORT_CYAN, sep) + '\n')
            f.write(common.r(common.REPORT_BOLD, header) + '\n')
            f.write(common.r(common.REPORT_CYAN, sep) + '\n')
            f.write(common.r(common.REPORT_YELLOW, 'Detected: ') + pod['reason'] + '\n')
            f.write(common.r(common.REPORT_DIM, 'READY: ') + pod['ready'])
            f.write(common.r(common.REPORT_DIM, '  RESTARTS: ') + pod['restarts'])
            f.write(common.r(common.REPORT_DIM, '  AGE: ') + pod['age'] + '\n')
            f.write(common.r(common.REPORT_BOLD, 'Summary: ') + pod['summary'] + '\n')
            if not pod['describe_ok']:
                f.write(common.r(common.REPORT_YELLOW, '  (oc describe returned no output)\n'))
            f.write('\n')

            by_section = {}
            for label, text in pod['details']:
                by_section.setdefault(label, []).append(text)

            section_order = ('Status', 'Conditions', 'Containers', 'Events', 'Details')
            for section in section_order:
                lines = by_section.get(section)
                if not lines:
                    continue
                f.write(common.r(common.REPORT_BOLD, '--- {} ---').format(section) + '\n')
                for text in lines:
                    f.write('  ' + common.highlight_error_keywords(text) + '\n')
                f.write('\n')

            f.write('\n')


def main():
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'
    main_start = time_module.time()

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/3] List all pods'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Running: oc get pods -A --no-headers'), flush=True)
    all_pods = _get_all_pods()
    if not all_pods:
        print(common.c(_YELLOW, 'No pods found or oc not available. Exiting.'))
        sys.exit(1)
    print(common.c(_GREEN, 'Found {} pods.').format(len(all_pods)))

    print('')
    print(common.c(_CYAN, '[2/3] Detect problematic pods'))
    print(common.c(_DIM, '-' * 60))
    bad_pods = []
    for ns, name, ready, status, restarts, age in all_pods:
        is_bad, reason = _is_problem_pod(ready, status)
        if is_bad:
            bad_pods.append((ns, name, ready, status, restarts, age, reason))

    print(common.c(_GREEN, 'Problematic: {} / {}').format(len(bad_pods), len(all_pods)))
    if bad_pods:
        preview = bad_pods[:8]
        for ns, name, ready, status, restarts, age, reason in preview:
            print(common.c(_DIM, '  {} / {} — {} ({})').format(ns, name, reason, ready))
        if len(bad_pods) > 8:
            print(common.c(_DIM, '  ... and {} more').format(len(bad_pods) - 8))

    print('')
    print(common.c(_CYAN, '[3/3] Describe pods and write report'))
    print(common.c(_DIM, '-' * 60))
    run_dir = config.timestamped_report_dir('pod_health')
    os.makedirs(run_dir, exist_ok=True)
    report_path = os.path.join(run_dir, 'pod_health_report.txt')

    problems = []
    if bad_pods:
        n = len(bad_pods)
        n_workers = min(config.MAX_WORKERS, n)
        print(common.c(_DIM, '  oc describe on {} pod(s) ({} workers)...').format(n, n_workers), flush=True)
        done = 0
        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_describe_one, pod): pod for pod in bad_pods}
            for fut in as_completed(futures):
                done += 1
                if done % 5 == 0 or done == n:
                    print(common.c(_DIM, '  [describe] {}/{}...').format(done, n), flush=True)
                try:
                    problems.append(fut.result())
                except Exception:
                    pass
        problems.sort(key=lambda p: (p['ns'], p['name']))

    _write_report(report_path, len(all_pods), problems, time_module.time() - main_start)

    elapsed = time_module.time() - main_start
    print(common.c(_GREEN, 'Report written: ') + common.c(_CYAN, report_path))
    print(common.c(_DIM, 'View with: ') + 'less -R ' + report_path)
    print(common.c(_DIM, 'Time: {:.1f}s').format(elapsed))


if __name__ == '__main__':
    main()
