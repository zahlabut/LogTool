#!/usr/bin/python3
"""
Analyze OpenShift pod logs: collect via oc, grep for errors, optional Ollama filter.
Run from LogToolMain or directly: python3 collect_and_analyze_pod_logs.py
Uses config.py for parameters and logtool_common.py for shared logic.
"""

import os
import sys
import tempfile
import threading
import time as time_module
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import logtool_common as common


def get_pods():
    ok, out = common.run('oc get pods -A --no-headers 2>/dev/null')
    if not ok:
        return []
    pods = []
    for raw in out.splitlines():
        parts = raw.split()
        if len(parts) >= 2:
            pods.append((parts[0].strip(), parts[1].strip()))
    return pods


def group_pods_by_component(pods):
    groups = {}
    for ns, name in pods:
        if not name:
            continue
        part = name.split('-')[0] if '-' in name else name
        component = part.lower()
        groups.setdefault(component, []).append((ns, name))
    return sorted(groups.items(), key=lambda x: x[0])


def safe_filename(namespace, pod_name):
    return (namespace + '_' + pod_name + '.log').replace('/', '-')


def _baseline_one_pod(args):
    ns, name, tail_lines = args
    cmd = 'oc logs -n {} {} --timestamps --all-containers --tail={} 2>/dev/null'.format(ns, name, tail_lines)
    ok, out = common.run(cmd, timeout=15)
    if not ok or not out.strip():
        return None
    latest = None
    for line in out.splitlines():
        dt, _ = common.get_line_date(line)
        if dt and (latest is None or dt > latest):
            latest = dt
    return latest


def get_baseline_quick(pods, tail_lines=10):
    n = len(pods)
    print(common.c('\033[36m', '  [baseline]') + ' Fetching last {} lines from {} pods ({} workers)...'.format(tail_lines, n, min(config.MAX_WORKERS, n)))
    start = time_module.time()
    latest = None
    done = 0
    with ThreadPoolExecutor(max_workers=min(config.MAX_WORKERS, n)) as ex:
        futures = {ex.submit(_baseline_one_pod, (ns, name, tail_lines)): (ns, name) for ns, name in pods}
        for fut in as_completed(futures):
            done += 1
            if done % 10 == 0 or done == n:
                print(common.c('\033[33m', '  [baseline]') + ' {}/{} pods checked...'.format(done, n), flush=True)
            try:
                dt = fut.result()
                if dt and (latest is None or dt > latest):
                    latest = dt
            except Exception:
                pass
    elapsed = time_module.time() - start
    ts_str = latest.strftime('%Y-%m-%d %H:%M:%S') if latest else 'none'
    print(common.c('\033[32m', '  [baseline] Done in {:.1f}s.').format(elapsed) + ' Latest timestamp: ' + common.c('\033[34m', ts_str) + '.')
    return latest


def _collect_one_pod(args):
    ns, name, path, since_iso = args
    if since_iso:
        cmd = 'oc logs -n {} {} --timestamps --all-containers --since-time={} > {} 2>/dev/null'.format(ns, name, since_iso, path)
    else:
        cmd = 'oc logs -n {} {} --timestamps --all-containers > {} 2>/dev/null'.format(ns, name, path)
    common.run(cmd)
    return path if os.path.isfile(path) else None


def collect_logs_since(logs_dir, pods, since_iso=None):
    n = len(pods)
    print(common.c('\033[33m', '  [collect]') + ' Fetching logs for {} pods ({} workers)...'.format(n, min(config.MAX_WORKERS, n)), flush=True)
    start = time_module.time()
    tasks = [(ns, name, os.path.join(logs_dir, safe_filename(ns, name)), since_iso) for ns, name in pods]
    created = []
    done = 0
    with ThreadPoolExecutor(max_workers=min(config.MAX_WORKERS, n)) as ex:
        futures = {ex.submit(_collect_one_pod, t): t for t in tasks}
        for fut in as_completed(futures):
            done += 1
            if done % 5 == 0 or done == n:
                print(common.c('\033[33m', '  [collect]') + ' {}/{} pods written...'.format(done, n), flush=True)
            try:
                path = fut.result()
                if path:
                    created.append(path)
            except Exception:
                pass
    print(common.c('\033[32m', '  [collect] Done in {:.1f}s. {} log files created.').format(time_module.time() - start, len(created)))
    return created


def main():
    logs_dir = config.LOGS_DIR
    report_path = config.REPORT_FILE
    main_start = time_module.time()
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/5] Pod list'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Collecting pod list (oc get pods -A)...'), flush=True)
    pods = get_pods()
    if not pods:
        print(common.c(_YELLOW, 'No pods found or oc not available. Exiting.'))
        sys.exit(1)
    print(common.c(_GREEN, 'Found {} pods.').format(len(pods)))

    groups = group_pods_by_component(pods)
    total = len(pods)
    num_options = len(groups) + 1
    print(common.c(_DIM, 'Choose which group of pods to analyze (components in alphabetical order):'))
    menu_items = []
    for i, (component, group_pods) in enumerate(groups, 1):
        n = len(group_pods)
        menu_items.append((i, '{} ({} pod{})'.format(component, n, 's' if n != 1 else '')))
    menu_items.append((num_options, 'All pods ({} pods)'.format(total)))
    common.print_menu_columns(menu_items, num_columns=3, cell_width=38)
    _timeout = getattr(config, 'PROMPT_TIMEOUT_SEC', 0)
    choice = common.timed_input(common.c(_DIM, 'Choice [1-{}]: ').format(num_options), '1', timeout_sec=_timeout)
    try:
        idx = int(choice)
        if 1 <= idx <= len(groups):
            pods = groups[idx - 1][1]
            print(common.c(_GREEN, 'Selected group "{}": {} pods.').format(groups[idx - 1][0], len(pods)))
        elif idx == len(groups) + 1:
            print(common.c(_GREEN, 'Selected all pods: {}.').format(total))
        else:
            pods = groups[0][1]
            print(common.c(_YELLOW, 'Invalid choice; using first group "{}".').format(groups[0][0]))
    except ValueError:
        pods = groups[0][1]
        print(common.c(_YELLOW, 'Invalid input; using first group "{}".').format(groups[0][0]))
    if not pods:
        print(common.c(_YELLOW, 'No pods to analyze. Exiting.'))
        sys.exit(0)

    print('')
    print(common.c(_CYAN, '[2/5] Baseline timestamp'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, 'Getting latest log timestamp (oc logs --tail=10 per pod)...'), flush=True)
    baseline = get_baseline_quick(pods)
    now = datetime.datetime.utcnow()
    ref_dt = baseline if baseline is not None else now
    if baseline is None:
        print(common.c(_YELLOW, 'Could not detect any timestamp in logs.'))
        print(common.c(_DIM, 'Choose how far back to analyze (from now):'))
    else:
        print('Last logged message was at: ' + common.c(_CYAN, ref_dt.strftime('%Y-%m-%d %H:%M:%S')) + '.')
        print(common.c(_DIM, 'Choose "since" time (messages after this will be analyzed):'))
    print('  1) 2h back')
    print('  2) 1h back')
    print('  3) 30m back')
    print('  4) Custom (enter minutes, e.g. 45)')
    choice = common.timed_input(common.c(_DIM, 'Choice [1-4]: '), '3', timeout_sec=_timeout).strip() or '3'
    if choice == '1':
        delta = datetime.timedelta(hours=2)
    elif choice == '2':
        delta = datetime.timedelta(hours=1)
    elif choice == '3':
        delta = datetime.timedelta(minutes=30)
    elif choice == '4':
        try:
            mins = int(common.timed_input('Minutes back: ', '30', timeout_sec=_timeout).strip())
            delta = datetime.timedelta(minutes=max(0, mins))
        except Exception:
            delta = datetime.timedelta(hours=1)
    else:
        delta = datetime.timedelta(hours=2)
    since_dt = ref_dt - delta
    since_iso = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    since_str = since_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c(_GREEN, 'Analyzing logs since: ') + common.c(_CYAN, since_str) + '.')

    print('')
    print(common.c(_CYAN, '[3/5] Collect logs'))
    print(common.c(_DIM, '-' * 60))
    if os.path.isdir(logs_dir):
        for f in os.listdir(logs_dir):
            os.remove(os.path.join(logs_dir, f))
    else:
        os.makedirs(logs_dir, exist_ok=True)
    print(common.c(_DIM, 'Logs directory: ') + common.c(_CYAN, logs_dir))
    log_paths = collect_logs_since(logs_dir, pods, since_iso)

    total_lines = 0
    total_bytes = 0
    for p in log_paths:
        try:
            with open(p, 'rb') as f:
                data = f.read()
                total_bytes += len(data)
                total_lines += data.count(b'\n') + (1 if data and not data.endswith(b'\n') else 0)
        except (OSError, IOError):
            pass
    print(common.c(_DIM, '  Collected {} lines ({} bytes) in {} file(s).').format(total_lines, total_bytes, len(log_paths)), flush=True)
    if total_lines == 0:
        print(common.c(_YELLOW, '  No log content in the selected time window. Pods may have been restarted or logs rotated. Try a shorter "since" (e.g. 2h or 30m).'), flush=True)

    print('')
    use_ollama = False
    if config.OLLAMA_HOST:
        if common.ollama_reachable():
            use_ollama = True
        else:
            print(common.c(_YELLOW, '  Remote Ollama is not available at {} — AI analyzing will be skipped.').format(config.OLLAMA_HOST), flush=True)
    if not use_ollama and not config.OLLAMA_HOST:
        print(common.c(_DIM, '  AI filter off — set OLLAMA_HOST in config.py to use Ollama.'), flush=True)
    print(common.c(_CYAN, '[4/5] Analyze (grep' + (' + Ollama filter' if use_ollama else '') + ')'))
    print(common.c(_DIM, '-' * 60))
    keywords_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    try:
        for kw in config.ERROR_KEYWORDS:
            keywords_file.write(kw.strip() + '\n')
        keywords_file.close()
        keywords_path = keywords_file.name
    except Exception:
        keywords_path = None
    if not keywords_path:
        print(common.c(_YELLOW, 'Could not create keywords file. Skipping analysis.'))
        sys.exit(1)

    path_blocks = {}
    for path in sorted(log_paths):
        path_blocks[path] = common.extract_blocks_grep(path, keywords_path, since_dt)
    try:
        os.unlink(keywords_path)
    except Exception:
        pass

    ai_report_cache = {}
    report_entries = []
    for path in sorted(path_blocks.keys()):
        blocks = path_blocks[path]
        seen_sigs = []
        for (lines_with_nums, block_text, block_dt) in blocks:
            sig = common.block_signature(block_text)
            found_similar = False
            for seen in seen_sigs:
                if common.similar(sig, seen) >= config.FUZZY_MATCH_RATIO:
                    found_similar = True
                    break
            if found_similar:
                continue
            count = sum(1 for (_l, bt, _d) in blocks if common.similar(common.block_signature(bt), sig) >= config.FUZZY_MATCH_RATIO)
            seen_sigs.append(sig)
            report_entries.append((path, lines_with_nums, block_text, sig, count))

    n_blocks = len(report_entries)
    n_unique = len(set(e[3] for e in report_entries)) if report_entries else 0
    print(common.c(_GREEN, 'Grep found {} error block(s) ({} unique).').format(n_blocks, n_unique), flush=True)
    if n_blocks == 0 and total_lines > 0:
        print(common.c(_YELLOW, '  No lines matched error keywords. Logs are in {} (keywords: config.ERROR_KEYWORDS in config.py).').format(logs_dir), flush=True)
    if use_ollama and n_unique > 0:
        print(common.c(_DIM, '  {} unique block(s) will be sent to Ollama for classification.').format(n_unique), flush=True)
    elif use_ollama and n_unique == 0:
        print(common.c(_DIM, '  No blocks to classify — skipping Ollama.'), flush=True)
        use_ollama = False

    if use_ollama:
        resolved_model = (config.OLLAMA_MODEL or '').strip()
        model_was_auto = False
        if not resolved_model:
            if sys.stdin.isatty():
                resolved_model = common.ollama_choose_model_interactive(config.OLLAMA_HOST)
            else:
                resolved_model = common.ollama_pick_best_model(config.OLLAMA_HOST)
                model_was_auto = True
            if resolved_model == common.OLLAMA_SKIP:
                print(common.c(_DIM, '  Skipping Ollama — all blocks will be included in report.'), flush=True)
                use_ollama = False
            elif not resolved_model:
                print(common.c(_YELLOW, '  No models on Ollama server — AI analyzing will be skipped.'), flush=True)
                use_ollama = False
        if use_ollama:
            unique_sigs = {}
            for (path, lines_with_nums, block_text, sig, count) in report_entries:
                if sig not in unique_sigs:
                    unique_sigs[sig] = block_text
            n_unique = len(unique_sigs)
            n_workers = min(config.OLLAMA_MAX_CONCURRENT, n_unique)
            print(common.c(_DIM, 'Asking Ollama in parallel ({} workers, {} unique blocks; real error? + explanation)...').format(n_workers, n_unique), flush=True)
            if model_was_auto:
                print(common.c(_DIM, '  Model: {} (auto-selected, smallest/fastest on server)').format(resolved_model), flush=True)
            else:
                print(common.c(_DIM, '  Model: {}').format(resolved_model), flush=True)
            print(common.c(_DIM, '  Sending {} blocks to Ollama...').format(n_unique), flush=True)
            start_ollama = time_module.time()
            done_count = [0]
            lock = threading.Lock()

            def _classify_one(args):
                sig, block_text, model = args
                keep, expl = common.ollama_classify_and_explain(block_text, model=model)
                if keep and (not expl or len(expl.strip()) < 40):
                    expl = common.ollama_detailed_explanation(block_text, model=model)
                return (sig, keep, expl)

            with ThreadPoolExecutor(max_workers=n_workers or 1) as ex:
                futures = [ex.submit(_classify_one, (sig, unique_sigs[sig], resolved_model)) for sig in unique_sigs]
            for fut in as_completed(futures):
                try:
                    sig, keep, expl = fut.result()
                    ai_report_cache[sig] = (keep, expl)
                    with lock:
                        done_count[0] += 1
                        print(common.c(_YELLOW, '  [{}]/{}').format(done_count[0], n_unique) + ' ' + common.c(_GREEN, 'received'), flush=True)
                except Exception:
                    with lock:
                        done_count[0] += 1
                        print(common.c(_YELLOW, '  [{}]/{}').format(done_count[0], n_unique) + ' ' + common.c(_DIM, 'failed'), flush=True)
            elapsed_ollama = time_module.time() - start_ollama
            print(common.c(_GREEN, '  Done in {:.1f}s.').format(elapsed_ollama), flush=True)
            for i, entry in enumerate(report_entries):
                path, lines_with_nums, block_text, sig, count = entry
                keep, _ = ai_report_cache.get(sig, (True, None))
                if not keep:
                    report_entries[i] = None
            report_entries = [e for e in report_entries if e is not None]

    print('')
    print(common.c(_CYAN, '[5/5] Write report'))
    print(common.c(_DIM, '-' * 60))
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(common.r(common.REPORT_BOLD, 'Pod logs error report') + ' — since: {}\n'.format(since_str))
        f.write(common.r(common.REPORT_DIM, 'Logs directory: ') + '{}\n'.format(os.path.abspath(logs_dir)))
        f.write(common.r(common.REPORT_DIM, 'AI filter: ') + ('on (Ollama)' if use_ollama else 'off — set OLLAMA_HOST in config to enable') + '\n\n')
        for path in sorted(set(e[0] for e in report_entries)):
            log_file_line = 'Log file: ' + path
            sep_len = len(log_file_line)
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n')
            f.write(common.r(common.REPORT_BOLD, 'Log file: ') + path + '\n')
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n\n')
            for (p, lines_with_nums, block_text, sig, count) in report_entries:
                if p != path:
                    continue
                f.write(common.r(common.REPORT_YELLOW, '  (occurred {} time{})').format(count, 's' if count != 1 else '') + '\n')
                for line_no, line_text in lines_with_nums[:config.MAX_BLOCK_LINES_SHOWN]:
                    f.write('  {}: {}'.format(line_no, common.highlight_error_keywords(line_text)))
                if len(lines_with_nums) > config.MAX_BLOCK_LINES_SHOWN:
                    f.write('  ... ({} more lines)\n'.format(len(lines_with_nums) - config.MAX_BLOCK_LINES_SHOWN))
                if use_ollama and sig in ai_report_cache:
                    _, expl = ai_report_cache[sig]
                    f.write(common.r(common.REPORT_DIM, '  --- Ollama (not from log) ---') + '\n')
                    if expl:
                        f.write(common.wrap_for_report(expl) + '\n')
                    else:
                        f.write('  (classified as real issue)\n')
                f.write('\n')
        if not report_entries:
            f.write(common.r(common.REPORT_DIM, '(No error blocks to report.)') + '\n')

    html_path = getattr(config, 'REPORT_HTML', os.path.join(config.BASE_DIR, 'pod_logs_error_report.html'))
    html_content, report_logs_dir = common.build_error_report_html(
        'Pod logs error report', 'Logs directory', os.path.abspath(logs_dir),
        report_entries, use_ollama, ai_report_cache, html_path, 'pod_logs_report_logs')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(common.c(_GREEN, 'HTML report: ') + common.c(_CYAN, html_path))

    total_elapsed = time_module.time() - main_start
    print(common.c(_GREEN, 'Report written to: ') + common.c(_CYAN, report_path))
    print(common.c(_GREEN, 'Total unique blocks: {}.').format(len(report_entries)))
    print(common.c(_DIM, 'Total time: ') + '{:.1f}s'.format(total_elapsed))
    common.print_download_prompt(html_path, report_path, report_logs_dir=report_logs_dir)


if __name__ == '__main__':
    main()
