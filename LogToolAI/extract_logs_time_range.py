#!/usr/bin/python3
"""
Extract pod logs for a time range, grep suspicious error strings, and optionally get an Ollama summary.
Pod list → group → baseline → time window → fetch logs → error report (TXT/HTML + ZIP download).
Run from LogToolMain or directly.
"""

import os
import re
import sys
import shutil
import tempfile
import datetime
import time as time_module
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import logtool_common as common

# Reuse pod discovery and baseline from pod-logs mode.
from collect_and_analyze_pod_logs import (
    get_pods,
    group_pods_by_component,
    safe_filename,
    get_baseline_quick,
)


def _parse_absolute_time(s):
    """Parse YYYY-MM-DD HH:MM:SS or ISO-like timestamp (naive UTC)."""
    s = (s or '').strip()
    if not s:
        return None
    s = s.replace('Z', '').replace('z', '')
    if 'T' in s:
        s = s.replace('T', ' ')
    if '.' in s:
        s = s.split('.')[0]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _resolve_time_input(raw, reference_dt):
    """
    Interpret user input relative to reference_dt (usually latest log time):
    - empty -> None (caller uses default)
    - latest / baseline -> reference_dt
    - now -> utcnow
    - digits -> reference_dt - N minutes
    - otherwise absolute datetime
    """
    s = (raw or '').strip()
    if not s:
        return None
    low = s.lower()
    if low in ('latest', 'baseline', 'last'):
        return reference_dt
    if low == 'now':
        return datetime.datetime.utcnow()
    if re.fullmatch(r'\d+', s):
        return reference_dt - datetime.timedelta(minutes=int(s))
    dt = _parse_absolute_time(s)
    if dt is not None:
        return dt
    return None


def _prompt_start_end_window(reference_dt, timeout_sec):
    """Return (start_dt, end_dt) chosen by user."""
    ref_str = reference_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c('\033[2m', 'Reference (latest log in selection): ') + common.c('\033[36m', ref_str))
    print(common.c('\033[2m', 'Define the window (start and end, not only "until now"):'))
    print('  1) Last 30m ending at latest log')
    print('  2) Last 1h ending at latest log')
    print('  3) Last 2h ending at latest log')
    print('  4) Custom start and end')
    choice = common.timed_input(common.c('\033[2m', 'Choice [1-4]: '), '1', timeout_sec=timeout_sec).strip() or '1'
    if choice == '1':
        return reference_dt - datetime.timedelta(minutes=30), reference_dt
    if choice == '2':
        return reference_dt - datetime.timedelta(hours=1), reference_dt
    if choice == '3':
        return reference_dt - datetime.timedelta(hours=2), reference_dt

    print(common.c('\033[2m', 'Start — minutes before latest, or datetime (YYYY-MM-DD HH:MM:SS / ISO):'))
    start_raw = common.timed_input(common.c('\033[2m', 'Start [default 60m before latest]: '), '60', timeout_sec=timeout_sec)
    start_dt = _resolve_time_input(start_raw, reference_dt)
    if start_dt is None:
        try:
            start_dt = reference_dt - datetime.timedelta(minutes=max(0, int((start_raw or '60').strip())))
        except ValueError:
            start_dt = reference_dt - datetime.timedelta(hours=1)

    print(common.c('\033[2m', 'End — latest | now | minutes before latest | datetime:'))
    end_raw = common.timed_input(common.c('\033[2m', 'End [default latest]: '), 'latest', timeout_sec=timeout_sec)
    end_dt = _resolve_time_input(end_raw, reference_dt)
    if end_dt is None:
        end_dt = reference_dt

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
        print(common.c('\033[33m', 'Start was after end; swapped.'))
    return start_dt, end_dt


def _filter_raw_log_by_range(raw, start_dt, end_dt):
    """Keep lines with no parseable time, or timestamp in [start_dt, end_dt]."""
    if not raw:
        return ''
    kept = []
    for line in raw.splitlines():
        dt, _ = common.get_line_date(line)
        if dt is not None and (dt < start_dt or dt > end_dt):
            continue
        kept.append(line)
    if not kept:
        return ''
    return '\n'.join(kept) + '\n'


def _extract_error_blocks_from_paths(paths, since_dt):
    """Grep paths for ERROR_KEYWORDS; return deduplicated report_entries tuples."""
    if not paths:
        return []
    keywords_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    try:
        for kw in config.ERROR_KEYWORDS:
            keywords_file.write(kw.strip() + '\n')
        keywords_file.close()
        keywords_path = keywords_file.name
    except Exception:
        return []

    def _extract_one(path):
        return (path, common.extract_blocks_grep(path, keywords_path, since_dt))

    path_blocks = {}
    selected_sorted = sorted(paths)
    n_files = len(selected_sorted)
    n_workers = min(config.MAX_WORKERS, n_files)
    done = 0
    ext_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_extract_one, path): path for path in selected_sorted}
        for fut in as_completed(futures):
            with ext_lock:
                done += 1
                if done % 20 == 0 or done == n_files:
                    print(common.c('\033[2m', '  [grep] {}/{} files...').format(done, n_files), flush=True)
            try:
                path, blocks = fut.result()
                path_blocks[path] = blocks
            except Exception:
                pass
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
            count = sum(
                1 for (_l, bt, _d) in blocks
                if common.similar(common.block_signature(bt), sig) >= config.FUZZY_MATCH_RATIO
            )
            seen_sigs.append(sig)
            report_entries.append((path, lines_with_nums, block_text, sig, count))
    return report_entries


def _write_extract_error_reports(run_dir, logs_dir, report_entries, start_str, end_str, selected_group_name):
    """Write text/HTML error reports; return (report_path, html_path, report_logs_dir)."""
    report_path = os.path.join(run_dir, 'extract_logs_error_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(
            common.r(common.REPORT_BOLD, 'Extract logs error report')
            + ' — window: {} to {}\n'.format(start_str, end_str)
        )
        f.write(common.r(common.REPORT_DIM, 'Pod group: ') + selected_group_name + '\n')
        f.write(common.r(common.REPORT_DIM, 'Logs directory: ') + os.path.abspath(logs_dir) + '\n\n')
        for path in sorted(set(e[0] for e in report_entries)):
            log_file_line = 'Log file: ' + path
            sep_len = len(log_file_line)
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n')
            f.write(common.r(common.REPORT_BOLD, 'Log file: ') + path + '\n')
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n\n')
            for (p, lines_with_nums, block_text, sig, count) in report_entries:
                if p != path:
                    continue
                f.write(
                    common.r(common.REPORT_YELLOW, '  (occurred {} time{})').format(
                        count, 's' if count != 1 else ''
                    ) + '\n'
                )
                for line_no, line_text in lines_with_nums[:config.MAX_BLOCK_LINES_SHOWN]:
                    f.write('  {}: {}'.format(line_no, common.highlight_error_keywords(line_text)))
                if len(lines_with_nums) > config.MAX_BLOCK_LINES_SHOWN:
                    f.write('  ... ({} more lines)\n'.format(len(lines_with_nums) - config.MAX_BLOCK_LINES_SHOWN))
                f.write('\n')
        if not report_entries:
            f.write(common.r(common.REPORT_DIM, '(No suspicious error strings found in extracted logs.)') + '\n')

    html_path = os.path.join(run_dir, 'extract_logs_error_report.html')
    html_content, report_logs_dir = common.build_error_report_html(
        'Extract logs error report',
        'Time window',
        '{} to {}'.format(start_str, end_str),
        report_entries,
        False,
        {},
        html_path,
        'extract_logs_report_logs',
    )
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return report_path, html_path, report_logs_dir


def _cleanup_extract_run_after_zip(run_dir, logs_dir, extra_paths):
    """Remove extracted log files and metadata after ZIP is created (ZIP is kept)."""
    for p in extra_paths or []:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
    if logs_dir and os.path.isdir(logs_dir):
        try:
            shutil.rmtree(logs_dir)
        except OSError:
            pass


def _fetch_one_pod_log(ns, name, since_iso):
    """Fetch log output for one pod since since_iso. Returns (ns, name, raw_output)."""
    cmd = 'oc logs -n {} {} --timestamps --all-containers --since-time={} 2>/dev/null'.format(
        ns, name, since_iso
    )
    ok, out = common.run(cmd, timeout=60)
    return (ns, name, (out or '').strip())


def main():
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/7] Pod list'))
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
    print(common.c(_DIM, 'Choose which group of pods to extract (components in alphabetical order):'))
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
    except (ValueError, EOFError):
        idx = num_options
    if idx < 1 or idx > num_options:
        idx = num_options
    if idx == num_options:
        selected_pods = pods
        selected_group_name = 'all'
        print(common.c(_GREEN, 'Selected all {} pods.').format(total))
    else:
        selected_pods = groups[idx - 1][1]
        selected_group_name = groups[idx - 1][0]
        print(common.c(_GREEN, 'Selected group "{}": {} pods.').format(selected_group_name, len(selected_pods)))

    print('')
    print(common.c(_CYAN, '[2/7] Baseline timestamp'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, 'Getting latest log timestamp (oc logs --tail=10 per pod)...'), flush=True)
    baseline = get_baseline_quick(selected_pods)
    reference_dt = baseline or datetime.datetime.utcnow()
    if baseline is None:
        print(common.c(_YELLOW, 'Could not detect latest log timestamp; using now (UTC) as reference.'))
    else:
        print('Last logged message was at: ' + common.c(_CYAN, baseline.strftime('%Y-%m-%d %H:%M:%S')) + '.')
    start_dt, end_dt = _prompt_start_end_window(reference_dt, _timeout)
    since_dt = start_dt
    since_iso = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c(_GREEN, 'Time window: ') + common.c(_CYAN, start_str) + common.c(_GREEN, '  →  ') + common.c(_CYAN, end_str))

    print('')
    print(common.c(_CYAN, '[3/7] Create output folder'))
    print(common.c(_DIM, '-' * 60))
    run_dir = config.timestamped_report_dir('extract_logs')
    os.makedirs(run_dir, exist_ok=True)
    out_dir = os.path.join(run_dir, 'extracted_pod_logs')
    os.makedirs(out_dir, exist_ok=True)
    print(common.c(_DIM, 'Run directory: ') + common.c(_CYAN, run_dir))
    meta_path = os.path.join(run_dir, 'extract_time_range.txt')
    with open(meta_path, 'w', encoding='utf-8') as mf:
        mf.write('Time window: {} to {}\n'.format(start_str, end_str))
        mf.write('Reference (latest log): {}\n'.format(reference_dt.strftime('%Y-%m-%d %H:%M:%S')))
        mf.write('Pod group: {}\n'.format(selected_group_name))
        mf.write('Pods: {}\n'.format(len(selected_pods)))

    print('')
    print(common.c(_CYAN, '[4/7] Fetch and write logs (error strings colorized)'))
    print(common.c(_DIM, '-' * 60))
    n = len(selected_pods)
    n_workers = min(config.MAX_WORKERS, n)
    print(common.c(_DIM, '  Fetching logs for {} pods ({} workers)...').format(n, n_workers), flush=True)
    start = time_module.time()
    written = 0
    written_paths = []
    logs_for_ollama = []  # (ns, name, raw) for pods that had content
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_fetch_one_pod_log, ns, name, since_iso): (ns, name) for ns, name in selected_pods}
        for fut in as_completed(futures):
            try:
                ns, name, raw = fut.result()
                raw = _filter_raw_log_by_range(raw, start_dt, end_dt)
                if not (raw or '').strip():
                    continue
                logs_for_ollama.append((ns, name, raw))
                out_path = os.path.join(out_dir, safe_filename(ns, name))
                with open(out_path, 'w') as f:
                    for line in (raw or '').splitlines():
                        f.write(common.highlight_error_keywords(line + '\n'))
                written_paths.append(out_path)
                written += 1
                if written % 5 == 0 or written == n:
                    print(common.c(_DIM, '  [write] {}/{} pods...').format(written, n), flush=True)
            except Exception:
                pass
    print(common.c(_GREEN, '  Done in {:.1f}s. {} log files written.').format(time_module.time() - start, written))

    summary_path = None
    summary_response = None
    if written > 0 and getattr(config, 'OLLAMA_HOST', '').strip() and common.ollama_reachable():
        print('')
        print(common.c(_CYAN, '[5/7] Ollama summary (what processes, success or errors?)'))
        print(common.c(_DIM, '-' * 60))
        resolved_model = (config.OLLAMA_MODEL or '').strip()
        if not resolved_model:
            if sys.stdin.isatty():
                resolved_model = common.ollama_choose_model_interactive(config.OLLAMA_HOST)
            else:
                resolved_model = common.ollama_pick_best_model(config.OLLAMA_HOST)
        if resolved_model == common.OLLAMA_SKIP:
            print(common.c(_DIM, '  Skipping Ollama summary.'), flush=True)
        elif resolved_model:
            max_chars = getattr(config, 'EXTRACT_OLLAMA_MAX_CHARS', 50000) or 999999
            # Single request with clear file separators so Ollama sees one coherent context.
            combined = []
            pod_names = []
            for ns, name, raw in logs_for_ollama:
                pod_names.append('{} / {}'.format(ns, name))
                combined.append('--- BEGIN POD: {} / {} ---\n'.format(ns, name) + (raw or '') + '\n--- END POD ---')
            log_text = '\n\n'.join(combined)
            if len(log_text) > max_chars:
                log_text = log_text[:max_chars] + '\n\n[... truncated ...]'
            pod_list = ', '.join(pod_names) if len(pod_names) <= 10 else ', '.join(pod_names[:10]) + ' ... ({} total)'.format(len(pod_names))
            prompt = (
                'Context: These logs are from a RHOSO (Red Hat OpenStack on OpenShift) environment. '
                'The group you are looking at is named "{}". '
                'Log time window: {} to {} (UTC, from pod timestamps).\n'
                'We are troubleshooting: we want to know if everything went OK or if there were issues detected and logged.\n\n'
                'Log source names (pods): {}.\n\n'
                'Below are the log contents. Each pod is delimited by "--- BEGIN POD: namespace / podname ---" and "--- END POD ---". '
                'Answer in 3–8 short sentences: (1) What processes or operations do you see in these logs? '
                '(e.g. zone creation, API calls, startup). (2) Based on the messages, did they complete successfully or did any raise errors? '
                'Use plain language. Start directly with what you see—no preamble like "Based on the logs".\n\n'
                'Logs:\n\n'
            ).format(selected_group_name, start_str, end_str, pod_list) + log_text
            print(common.c(_DIM, '  Sending {} chars to Ollama (model: {})...').format(len(log_text), resolved_model), flush=True)
            summary_response = common.ollama_custom_prompt(prompt, model=resolved_model)
            if summary_response:
                print(common.c(_GREEN, '  Ollama summary:') + '\n  ' + summary_response.replace('\n', '\n  '))
                summary_path = os.path.join(run_dir, 'ollama_summary.txt')
                with open(summary_path, 'w') as f:
                    f.write('Ollama summary (time range: {} to {})\n'.format(start_str, end_str))
                    f.write('Model: {}\n\n'.format(resolved_model))
                    f.write(summary_response)
                print(common.c(_DIM, '  Saved to: ') + summary_path)
            else:
                print(common.c(_YELLOW, '  No response from Ollama.'))
        else:
            print(common.c(_YELLOW, '  No model selected — skipping Ollama summary.'))
    else:
        if written > 0 and not (getattr(config, 'OLLAMA_HOST', '').strip() and common.ollama_reachable()):
            print('')
            print(common.c(_CYAN, '[5/7] Ollama summary'))
            print(common.c(_DIM, '  Ollama not configured or unreachable — skipping.'))

    print('')
    print(common.c(_CYAN, '[6/7] Extract suspicious error strings'))
    print(common.c(_DIM, '-' * 60))
    report_entries = []
    if written_paths:
        print(common.c(_DIM, '  Scanning {} log files for configured error keywords...').format(len(written_paths)), flush=True)
        report_entries = _extract_error_blocks_from_paths(written_paths, since_dt)
        print(common.c(_GREEN, '  Found {} unique error block(s).').format(len(report_entries)))
    else:
        print(common.c(_YELLOW, '  No log files to scan.'))

    print('')
    print(common.c(_CYAN, '[7/7] Write report and create download archive'))
    print(common.c(_DIM, '-' * 60))
    report_path, html_path, report_logs_dir = _write_extract_error_reports(
        run_dir, out_dir, report_entries, start_str, end_str, selected_group_name,
    )
    zip_log_paths = list(written_paths)
    if meta_path and os.path.isfile(meta_path):
        zip_log_paths.append(meta_path)
    if summary_path and os.path.isfile(summary_path):
        zip_log_paths.append(summary_path)
    common.print_download_prompt(
        html_path,
        report_path,
        report_logs_dir=report_logs_dir,
        log_paths_to_include=zip_log_paths or None,
        show_ssh_download=True,
    )
    _cleanup_extract_run_after_zip(run_dir, out_dir, [meta_path, summary_path])
    print(common.c(_DIM, 'Time window: ') + start_str + common.c(_DIM, ' → ') + end_str)
    print(common.c(_DIM, 'View extracted logs in the ZIP under logs/ (use less -R for colorized errors).'))


if __name__ == '__main__':
    main()
