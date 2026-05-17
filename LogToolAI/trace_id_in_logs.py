#!/usr/bin/python3
"""
Trace a specific ID across all OpenShift pod logs: collect via oc (like mode 1), find every line
containing the ID (plus context lines around each hit), order by time, show log path per section.
Error keywords highlighted in red. Run on controller-0 with oc access.
"""

import datetime
import gzip
import os
import sys
import time as time_module

import config
import logtool_common as common
from collect_and_analyze_pod_logs import (
    collect_logs_since,
    get_baseline_quick,
    get_pods,
    group_pods_by_component,
)


def _iter_log_lines(path):
    """Yield (line_no, line_text) from a log file (.log or .gz; .gz may be raw text)."""
    use_gzip = (path or '').lower().endswith('.gz')
    kwargs = {'errors': 'replace'}

    def read_lines(open_fn):
        with open_fn(path, 'rt', **kwargs) as f:
            for line_no, line in enumerate(f, 1):
                yield (line_no, line)

    if use_gzip:
        try:
            yield from read_lines(gzip.open)
            return
        except gzip.BadGzipFile:
            pass
    try:
        yield from read_lines(open)
    except OSError:
        return


def _read_log_file_lines(path):
    """Return dict line_no -> line_text (without trailing newline)."""
    out = {}
    for line_no, line_text in _iter_log_lines(path):
        out[line_no] = line_text.rstrip('\n')
    return out


def scan_log_paths_for_id(log_paths, search_id, context_lines=None):
    """
    Find every line containing search_id, plus context_lines before/after each hit (same log file).
    Return list of (dt, path, line_no, line_text, has_id) sorted by time globally.
    has_id is True when the line contains search_id.
    """
    if not search_id:
        return []
    if context_lines is None:
        context_lines = getattr(config, 'ID_TRACE_CONTEXT_LINES', 5)
    include_by_path = {}
    for path in log_paths:
        if not os.path.isfile(path):
            continue
        for line_no, line_text in _iter_log_lines(path):
            if search_id not in line_text:
                continue
            nums = include_by_path.setdefault(path, set())
            for i in range(line_no - context_lines, line_no + context_lines + 1):
                if i >= 1:
                    nums.add(i)
    entries = []
    sentinel = datetime.datetime.max
    for path, line_nums in include_by_path.items():
        lines = _read_log_file_lines(path)
        for line_no in sorted(line_nums):
            line_text = lines.get(line_no, '')
            if not line_text:
                continue
            dt, _ = common.get_line_date(line_text)
            has_id = search_id in line_text
            entries.append((dt, path, line_no, line_text, has_id))

    def sort_key(item):
        dt, path, line_no, _, _ = item
        return (dt if dt is not None else sentinel, path, line_no)

    entries.sort(key=sort_key)
    return entries


def _log_display_name(path):
    """Short name for a collected log file (pod log basename)."""
    return os.path.basename(path) or path


def _write_text_timeline_report(f, search_id, since_str, logs_dir, entries, context_lines):
    f.write(common.r(common.REPORT_BOLD, 'ID trace report') + '\n')
    f.write(common.r(common.REPORT_DIM, 'Search ID: ') + search_id + '\n')
    f.write(common.r(common.REPORT_DIM, 'Logs since: ') + since_str + '\n')
    f.write(common.r(common.REPORT_DIM, 'Collected logs: ') + os.path.abspath(logs_dir) + '\n')
    id_lines = sum(1 for e in entries if e[4])
    f.write(common.r(common.REPORT_DIM, 'Timeline lines: ') + str(len(entries)) + ' ({} with ID, {} context)'.format(id_lines, len(entries) - id_lines) + '\n')
    f.write(common.r(common.REPORT_DIM, 'Context: ') + str(context_lines) + ' lines before/after each ID hit in the same log file.\n')
    f.write(common.r(common.REPORT_DIM, 'Order: chronological (time). Log path header when the source file changes.\n')
    f.write(common.r(common.REPORT_DIM, 'ERROR keywords are highlighted in red (same as mode 1).\n\n')
    if not entries:
        f.write(common.r(common.REPORT_DIM, '(No lines containing this ID in the collected logs.)') + '\n')
        f.write(common.r(common.REPORT_DIM, 'Try: All pods, longer time window (e.g. 2h), or check the ID string.') + '\n')
        return
    current_path = None
    for dt, path, line_no, line_text, has_id in entries:
        if path != current_path:
            current_path = path
            log_file_line = 'Log file: ' + path
            sep_len = len(log_file_line)
            f.write('\n')
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n')
            f.write(common.r(common.REPORT_BOLD, 'Log file: ') + path + '\n')
            f.write(common.r(common.REPORT_CYAN, '=' * sep_len) + '\n')
        ts = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '?'
        display = common.escape_ansi(line_text)
        highlighted = common.highlight_error_keywords(display)
        prefix = '[ID] ' if has_id else '     '
        f.write('{} {}:{} {}{}\n'.format(ts, _log_display_name(path), line_no, prefix, highlighted))

    files_with_id = sorted(set(e[1] for e in entries if e[4]))
    f.write('\n')
    f.write(common.r(common.REPORT_DIM, 'Log files with at least one ID match ({}): ').format(len(files_with_id)))
    f.write(', '.join(_log_display_name(p) for p in files_with_id) + '\n')


def _build_timeline_html(search_id, since_str, logs_dir, entries, context_lines):
    id_lines = sum(1 for e in entries if e[4])
    lines = []
    lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    lines.append('<title>ID trace: ' + common.html_escape(search_id) + '</title>')
    lines.append('<style>')
    lines.append('body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1400px;}')
    lines.append('h1{font-size:1.4rem;} h2{font-size:1rem;margin-top:1.5rem;color:#333;border-bottom:1px solid #ccc;padding-bottom:0.25rem;word-break:break-all;}')
    lines.append('.meta{color:#666;font-size:0.9rem;} .timeline{margin:0;padding:0;list-style:none;}')
    lines.append('.timeline li{margin:0.15rem 0;font-family:ui-monospace,monospace;font-size:0.82rem;white-space:pre-wrap;word-break:break-all;}')
    lines.append('.hl{background:#fce4a0;padding:0 2px;} .ts{color:#555;} .ctx{color:#666;} .idtag{color:#06c;font-weight:600;}')
    lines.append('</style></head><body>')
    lines.append('<h1>ID trace report</h1>')
    lines.append('<p class="meta"><strong>Search ID:</strong> ' + common.html_escape(search_id) + '</p>')
    lines.append('<p class="meta"><strong>Logs since:</strong> ' + common.html_escape(since_str) + '</p>')
    lines.append('<p class="meta"><strong>Collected logs:</strong> ' + common.html_escape(os.path.abspath(logs_dir)) + '</p>')
    lines.append('<p class="meta"><strong>Timeline:</strong> ' + str(len(entries)) + ' lines ({} with <span class="idtag">[ID]</span>, {} context). Sorted by time.</p>'.format(id_lines, len(entries) - id_lines))
    lines.append('<p class="meta">Context: ' + str(context_lines) + ' lines before/after each ID hit. ERROR keywords highlighted in yellow.</p>')
    if not entries:
        lines.append('<p class="meta">(No lines containing this ID.) Try All pods and a longer time window.</p>')
        lines.append('</body></html>')
        return '\n'.join(lines)
    current_path = None
    for dt, path, line_no, line_text, has_id in entries:
        if path != current_path:
            if current_path is not None:
                lines.append('</ul>')
            current_path = path
            lines.append('<h2>Log file: ' + common.html_escape(path) + '</h2>')
            lines.append('<ul class="timeline">')
        ts = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '?'
        display = common.line_for_display(line_text)
        body = common.html_highlight_line(display)
        tag = '<span class="idtag">[ID]</span> ' if has_id else '<span class="ctx">     </span> '
        li_cls = '' if has_id else ' class="ctx"'
        lines.append('<li' + li_cls + '><span class="ts">' + common.html_escape(ts) + ' ' + common.html_escape(_log_display_name(path)) + ':' + str(line_no) + '</span> ' + tag + body + '</li>')
    lines.append('</ul></body></html>')
    return '\n'.join(lines)


def main():
    main_start = time_module.time()
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'
    _timeout = getattr(config, 'PROMPT_TIMEOUT_SEC', 0)
    context_lines = getattr(config, 'ID_TRACE_CONTEXT_LINES', 5)

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, 'Trace ID in pod logs (controller)'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Collects pod logs via oc, finds lines with your ID (+ {} lines context per hit).'.format(context_lines)))
    print(common.c(_DIM, 'Full timeline sorted by time; log path header when the source file changes.'))
    print(common.c(_DIM, 'ERROR keywords highlighted in red (same as mode 1).'))
    print(common.c(_DIM, 'Tip: choose All pods and 2h+ window for the full story across components.'))
    print('')
    print(common.c(_GREEN, 'Which ID do you want to trace in the pod logs?'))
    print(common.c(_DIM, '  (Any string that appears in log lines: LB UUID, server ID, port ID, request-id, etc.)'))
    search_id = common.timed_input(common.c(_CYAN, 'Enter ID: '), '', timeout_sec=_timeout).strip()
    if not search_id:
        print(common.c(_YELLOW, 'No ID entered. Exiting.'))
        sys.exit(1)
    print('')
    print(common.c(_GREEN, 'Will collect logs and build a timeline for: ') + common.c(_CYAN, search_id))

    logs_dir = getattr(config, 'ID_TRACE_LOGS_DIR', os.path.join(config.RESULT_DIR, 'id_trace', 'collected_pod_logs'))

    print('')
    print(common.c(_CYAN, '[1/4] Pod list'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, 'Collecting pod list (oc get pods -A)...'), flush=True)
    pods = get_pods()
    if not pods:
        print(common.c(_YELLOW, 'No pods found or oc not available. Exiting.'))
        sys.exit(1)
    print(common.c(_GREEN, 'Found {} pods.').format(len(pods)))

    groups = group_pods_by_component(pods)
    total = len(pods)
    num_options = len(groups) + 1
    print(common.c(_DIM, 'Choose which pods to collect (recommended: All pods for full ID story):'))
    menu_items = []
    for i, (component, group_pods) in enumerate(groups, 1):
        n = len(group_pods)
        menu_items.append((i, '{} ({} pod{})'.format(component, n, 's' if n != 1 else '')))
    menu_items.append((num_options, 'All pods ({} pods)'.format(total)))
    common.print_menu_columns(menu_items, num_columns=3, cell_width=38)
    default_pod = str(num_options)
    choice = common.timed_input(common.c(_DIM, 'Choice [1-{}] (default All): ').format(num_options), default_pod, timeout_sec=_timeout)
    try:
        idx = int(choice)
        if 1 <= idx <= len(groups):
            pods = groups[idx - 1][1]
            print(common.c(_GREEN, 'Selected group "{}": {} pods.').format(groups[idx - 1][0], len(pods)))
        elif idx == num_options:
            print(common.c(_GREEN, 'Selected all pods: {}.').format(total))
        else:
            pods = groups[0][1]
            print(common.c(_YELLOW, 'Invalid choice; using first group.'))
    except ValueError:
        pods = groups[0][1]
        print(common.c(_YELLOW, 'Invalid input; using first group.'))
    if not pods:
        print(common.c(_YELLOW, 'No pods to collect. Exiting.'))
        sys.exit(0)

    print('')
    print(common.c(_CYAN, '[2/4] Baseline and since time'))
    print(common.c(_DIM, '-' * 60))
    baseline = get_baseline_quick(pods)
    now = datetime.datetime.utcnow()
    ref_dt = baseline if baseline is not None else now
    if baseline is None:
        print(common.c(_YELLOW, 'Could not detect any timestamp in logs.'))
    else:
        print('Last logged message was at: ' + common.c(_CYAN, ref_dt.strftime('%Y-%m-%d %H:%M:%S')) + '.')
    print(common.c(_DIM, 'How far back to collect (wider window = more of the ID story):'))
    print('  1) 2h back  2) 1h back  3) 30m back  4) Custom (minutes)')
    choice = common.timed_input(common.c(_DIM, 'Choice [1-4] (default 2h): '), '1', timeout_sec=_timeout).strip() or '1'
    if choice == '1':
        delta = datetime.timedelta(hours=2)
    elif choice == '2':
        delta = datetime.timedelta(hours=1)
    elif choice == '3':
        delta = datetime.timedelta(minutes=30)
    elif choice == '4':
        try:
            mins = int(common.timed_input('Minutes back: ', '120', timeout_sec=_timeout).strip())
            delta = datetime.timedelta(minutes=max(0, mins))
        except Exception:
            delta = datetime.timedelta(hours=2)
    else:
        delta = datetime.timedelta(hours=2)
    since_dt = ref_dt - delta
    since_iso = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    since_str = since_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c(_GREEN, 'Collecting logs since: ') + common.c(_CYAN, since_str) + '.')

    print('')
    print(common.c(_CYAN, '[3/4] Collect logs'))
    print(common.c(_DIM, '-' * 60))
    if os.path.isdir(logs_dir):
        for f in os.listdir(logs_dir):
            try:
                os.remove(os.path.join(logs_dir, f))
            except OSError:
                pass
    else:
        os.makedirs(logs_dir, exist_ok=True)
    print(common.c(_DIM, 'Logs directory: ') + common.c(_CYAN, logs_dir))
    log_paths = collect_logs_since(logs_dir, pods, since_iso)
    if not log_paths:
        print(common.c(_YELLOW, 'No log files collected. Exiting.'))
        sys.exit(1)

    print('')
    print(common.c(_CYAN, '[4/4] Scan logs for ID and write report'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, '  Scanning {} file(s) for "{}" (+ context)...').format(len(log_paths), search_id), flush=True)
    entries = scan_log_paths_for_id(log_paths, search_id, context_lines=context_lines)
    id_hits = sum(1 for e in entries if e[4])
    files_with_id = sorted(set(e[1] for e in entries if e[4]))
    print(common.c(_GREEN, '  {} line(s) with ID in {} log file(s); {} total timeline lines (with context).').format(
        id_hits, len(files_with_id), len(entries)), flush=True)
    if id_hits < 10 and len(pods) < total:
        print(common.c(_YELLOW, '  Few matches — re-run with All pods and/or 2h+ window if you need more of the story.'), flush=True)
    elif id_hits and len(files_with_id) == 1:
        print(common.c(_DIM, '  ID seen only in: ') + ', '.join(_log_display_name(p) for p in files_with_id), flush=True)

    run_dir = config.timestamped_report_dir('id_trace')
    os.makedirs(run_dir, exist_ok=True)
    report_path = os.path.join(run_dir, 'id_trace_report.txt')
    html_path = os.path.join(run_dir, 'id_trace_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        _write_text_timeline_report(f, search_id, since_str, logs_dir, entries, context_lines)
    html_content = _build_timeline_html(search_id, since_str, logs_dir, entries, context_lines)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    elapsed = time_module.time() - main_start
    print(common.c(_DIM, 'Time: {:.1f}s').format(elapsed))
    common.print_download_prompt(
        html_path, report_path, report_logs_dir=None,
        local_mode=False, show_ssh_download=True,
    )


if __name__ == '__main__':
    main()
