#!/usr/bin/python3
"""
Run must-gather, then analyze all collected log files with the same logic as pod logs:
grep for errors, dedupe, optional Ollama filter, write report.
Run from LogToolMain or directly: python3 must_gather_analyze.py
"""

import os
import sys
import tempfile
import time as time_module
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import config
import logtool_common as common


# Log file extensions and path patterns we consider as "logs" under must-gather output.
LOG_EXTENSIONS = ('.log', '.txt')
# Also include files under .../pods/.../ that have no extension (container logs).
PODS_PATH_PART = 'pods'
# Prefix for timestamped must-gather subdirs (must_gather_YYYYMMDD_HHMMSS).
MUST_GATHER_DIR_PREFIX = 'must_gather_'


def find_existing_must_gather_dirs(base_dir):
    """Return list of (full_path, dirname) for existing must_gather_* dirs, newest first."""
    if not os.path.isdir(base_dir):
        return []
    found = []
    for name in os.listdir(base_dir):
        if name.startswith(MUST_GATHER_DIR_PREFIX) and os.path.isdir(os.path.join(base_dir, name)):
            full = os.path.join(base_dir, name)
            found.append((full, name))
    # Sort by name descending so newest (larger timestamp) first
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def run_must_gather(dest_dir):
    """Run oc adm must-gather into dest_dir. Returns (success, message)."""
    parts = ['oc adm must-gather', '--dest-dir=' + dest_dir]
    if getattr(config, 'MUST_GATHER_IMAGE', '').strip():
        parts.append('--image=' + config.MUST_GATHER_IMAGE.strip())
    cmd = ' '.join(parts)
    print(common.c('\033[33m', '  [must-gather]') + ' Running (this can take several minutes): ' + cmd)
    ok, out = common.run(cmd, timeout=3600)  # 1 hour
    if ok:
        return (True, 'must-gather completed')
    return (False, out or 'must-gather failed')


def discover_log_files(root_dir):
    """Walk root_dir recursively; return (list of absolute paths, effective_root for grouping)."""
    root_dir = os.path.abspath(root_dir)
    if not os.path.isdir(root_dir):
        return ([], root_dir)
    effective_root = root_dir
    try:
        subs = [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))]
        if len(subs) == 1 and (subs[0].startswith('must-gather') or subs[0].startswith('namespace')):
            effective_root = os.path.join(root_dir, subs[0])
    except OSError:
        pass
    log_paths = []
    for dirpath, _dirnames, filenames in os.walk(effective_root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, effective_root)
            lower = name.lower()
            if any(lower.endswith(ext) for ext in LOG_EXTENSIONS):
                log_paths.append(path)
            elif PODS_PATH_PART in rel.replace(os.sep, '/'):
                if '.' not in name or lower.endswith('.log'):
                    log_paths.append(path)
    return (sorted(log_paths), effective_root)


def component_from_path(root_dir, path):
    """Derive a group key from path (e.g. 'designate', 'cinder'). Used for grouping like pod component."""
    try:
        rel = os.path.relpath(path, root_dir)
        parts = rel.replace(os.sep, '/').split('/')
        if PODS_PATH_PART in parts:
            idx = parts.index(PODS_PATH_PART)
            if idx + 1 < len(parts):
                pod_name = parts[idx + 1]
                # Same as pod mode: first segment before '-'
                comp = pod_name.split('-')[0].lower()
                if comp:
                    return comp
        # Fallback: use first directory under root (e.g. namespaces, cluster-scoped-resources)
        if len(parts) >= 2:
            return parts[0].lower()
        return os.path.basename(os.path.dirpath(path)).lower() or 'other'
    except Exception:
        return 'other'


def group_logs_by_component(root_dir, log_paths):
    """Return sorted list of (component, list of paths)."""
    groups = {}
    for path in log_paths:
        comp = component_from_path(root_dir, path)
        groups.setdefault(comp, []).append(path)
    return sorted(groups.items(), key=lambda x: x[0])


def main():
    main_start = time_module.time()
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/6] Must-gather: use existing or run fresh'))
    print(common.c(_CYAN, '=' * 60))
    base = getattr(config, 'MUST_GATHER_BASE_DIR', os.path.join(config.BASE_DIR, 'must_gather_output'))
    os.makedirs(base, exist_ok=True)
    _timeout = getattr(config, 'PROMPT_TIMEOUT_SEC', 0)
    existing = find_existing_must_gather_dirs(base)
    dest_dir = None
    if existing:
        print(common.c(_DIM, 'Existing must-gather directories (newest first):'))
        for i, (full, name) in enumerate(existing, 1):
            print(common.c(_DIM, '  {}) {}').format(i, name))
        print(common.c(_DIM, '  0) Run fresh must-gather (new collection)'))
        choice = common.timed_input(common.c(_DIM, 'Choice [0-{}]: ').format(len(existing)), '1', timeout_sec=_timeout)
        try:
            idx = int(choice)
        except (ValueError, EOFError):
            idx = 0
        if 1 <= idx <= len(existing):
            dest_dir = existing[idx - 1][0]
            print(common.c(_GREEN, 'Using existing: ') + common.c(_CYAN, dest_dir))
        else:
            idx = 0
    if dest_dir is None:
        dest_dir = os.path.join(base, 'must_gather_{}'.format(datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')))
        print(common.c(_DIM, 'Destination: ') + common.c(_CYAN, dest_dir))
        ok, msg = run_must_gather(dest_dir)
        if not ok:
            print(common.c(_YELLOW, 'Must-gather failed: ') + msg)
            sys.exit(1)
        print(common.c(_GREEN, 'Must-gather completed.'))

    print('')
    print(common.c(_CYAN, '[2/6] Discover log files'))
    print(common.c(_DIM, '-' * 60))
    log_paths, gather_root = discover_log_files(dest_dir)
    if not log_paths:
        print(common.c(_YELLOW, 'No log files found under {}. Exiting.').format(dest_dir))
        sys.exit(1)
    print(common.c(_GREEN, 'Found {} log files.').format(len(log_paths)))

    groups = group_logs_by_component(gather_root, log_paths)
    total = len(log_paths)
    num_options = len(groups) + 1
    print(common.c(_DIM, 'Choose which group to analyze (by component):'))
    menu_items = []
    for i, (component, paths) in enumerate(groups, 1):
        n = len(paths)
        menu_items.append((i, '{} ({} file{})'.format(component, n, 's' if n != 1 else '')))
    menu_items.append((num_options, 'All ({} files)'.format(total)))
    common.print_menu_columns(menu_items, num_columns=3, cell_width=38)
    choice = common.timed_input(common.c(_DIM, 'Choice [1-{}]: ').format(num_options), '1', timeout_sec=_timeout)
    try:
        idx = int(choice)
    except (ValueError, EOFError):
        idx = num_options
    if idx < 1 or idx > num_options:
        idx = num_options
    if idx == num_options:
        selected_paths = log_paths
        print(common.c(_GREEN, 'Selected all {} files.').format(total))
    else:
        selected_paths = groups[idx - 1][1]
        print(common.c(_GREEN, 'Selected group "{}": {} files.').format(groups[idx - 1][0], len(selected_paths)))

    print('')
    print(common.c(_CYAN, '[3/6] Baseline timestamp'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, 'Scanning last {} lines of selected log files for latest timestamp...').format(common.BASELINE_TAIL_LINES), flush=True)
    baseline = common.get_baseline_from_log_files(selected_paths)
    if baseline is None:
        print(common.c(_YELLOW, 'Could not detect any timestamp. Using "since" = 24h ago.'))
        since_dt = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    else:
        baseline_str = baseline.strftime('%Y-%m-%d %H:%M:%S')
        print('Last logged message was at: ' + common.c(_CYAN, baseline_str) + '.')
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
        since_dt = baseline - delta
    since_str = since_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c(_GREEN, 'Analyzing logs since: ') + common.c(_CYAN, since_str) + '.')

    print('')
    print(common.c(_CYAN, '[4/6] Extract error blocks'))
    print(common.c(_DIM, '-' * 60))
    keywords_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    try:
        for kw in config.ERROR_KEYWORDS:
            keywords_file.write(kw.strip() + '\n')
        keywords_file.close()
        keywords_path = keywords_file.name
    except Exception:
        print(common.c(_YELLOW, 'Could not create keywords file.'))
        sys.exit(1)

    def _extract_one(args):
        path, kw_path, since = args
        return (path, common.extract_blocks_grep(path, kw_path, since))

    selected_sorted = sorted(selected_paths)
    n_files = len(selected_sorted)
    n_workers = min(config.MAX_WORKERS, n_files)
    print(common.c(_DIM, '  Extracting blocks from {} files ({} workers)...').format(n_files, n_workers), flush=True)
    path_blocks = {}
    done = 0
    ext_lock = threading.Lock()
    start_ext = time_module.time()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_extract_one, (path, keywords_path, since_dt)): path for path in selected_sorted}
        for fut in as_completed(futures):
            with ext_lock:
                done += 1
                if done % 50 == 0 or done == n_files:
                    print(common.c(_DIM, '  [extract] {}/{} files...').format(done, n_files), flush=True)
            try:
                path, blocks = fut.result()
                path_blocks[path] = blocks
            except Exception:
                pass
    print(common.c(_GREEN, '  Extract done in {:.1f}s.').format(time_module.time() - start_ext))
    try:
        os.unlink(keywords_path)
    except Exception:
        pass

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

    use_ollama = False
    if config.OLLAMA_HOST:
        if common.ollama_reachable():
            use_ollama = True
        else:
            print(common.c(_YELLOW, '  Ollama not available — AI filter skipped.'), flush=True)
    print(common.c(_CYAN, '[5/6] Analyze (grep' + (' + Ollama filter' if use_ollama else '') + ')'))
    print(common.c(_DIM, '-' * 60))

    ai_report_cache = {}
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
                print(common.c(_YELLOW, '  No models on Ollama server — AI filter skipped.'), flush=True)
                use_ollama = False
        if use_ollama:
            unique_sigs = {}
            for (path, lines_with_nums, block_text, sig, count) in report_entries:
                if sig not in unique_sigs:
                    unique_sigs[sig] = block_text
            n_unique = len(unique_sigs)
            n_workers = min(config.OLLAMA_MAX_CONCURRENT, n_unique)
            print(common.c(_DIM, 'Asking Ollama ({} workers, {} unique blocks)...').format(n_workers, n_unique), flush=True)
            if model_was_auto:
                print(common.c(_DIM, '  Model: {} (auto, smallest/fastest)').format(resolved_model), flush=True)
            else:
                print(common.c(_DIM, '  Model: {}').format(resolved_model), flush=True)
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
                        print(common.c(_YELLOW, '  [{}]/{}').format(done_count[0], n_unique) + ' failed', flush=True)
            print(common.c(_GREEN, '  Done.'), flush=True)
            for i, entry in enumerate(report_entries):
                path, lines_with_nums, block_text, sig, count = entry
                keep, _ = ai_report_cache.get(sig, (True, None))
                if not keep:
                    report_entries[i] = None
            report_entries = [e for e in report_entries if e is not None]

    print('')
    print(common.c(_CYAN, '[6/6] Write report'))
    print(common.c(_DIM, '-' * 60))
    report_path = getattr(config, 'MUST_GATHER_REPORT_FILE', os.path.join(config.BASE_DIR, 'must_gather_error_report.txt'))
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(common.r(common.REPORT_BOLD, 'Must-gather error report') + ' — since: {}\n'.format(since_str))
        f.write(common.r(common.REPORT_DIM, 'Source directory: ') + dest_dir + '\n')
        f.write(common.r(common.REPORT_DIM, 'AI filter: ') + ('on (Ollama)' if use_ollama else 'off') + '\n\n')
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

    html_path = getattr(config, 'MUST_GATHER_REPORT_HTML', os.path.join(config.BASE_DIR, 'must_gather_error_report.html'))
    html_content, report_logs_dir = common.build_error_report_html(
        'Must-gather error report', 'Source directory', dest_dir,
        report_entries, use_ollama, ai_report_cache, html_path, 'must_gather_report_logs')
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
