#!/usr/bin/python3
"""
Trace a specific ID across all OpenShift pod logs: collect via oc (like mode 1), find every line
containing the ID, order by time, group by log file with headers. Error keywords highlighted in red.
Run on controller-0 with oc access. Run from LogToolMain or directly.
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


def scan_log_paths_for_id(log_paths, search_id):
    """
  Scan log files for lines containing search_id (substring match).
  Return list of (dt, path, line_no, line_text) sorted by time, then path, then line_no.
  dt is datetime or None.
    """
    if not search_id:
        return []
    entries = []
    for path in log_paths:
        if not os.path.isfile(path):
            continue
        for line_no, line_text in _iter_log_lines(path):
            if search_id not in line_text:
                continue
            dt, _ = common.get_line_date(line_text)
            entries.append((dt, path, line_no, line_text.rstrip('\n')))
    sentinel = datetime.datetime.max

    def sort_key(item):
        dt, path, line_no, _ = item
        return (dt if dt is not None else sentinel, path, line_no)

    entries.sort(key=sort_key)
    return entries


def _write_text_timeline_report(f, search_id, since_str, logs_dir, entries):
    f.write(common.r(common.REPORT_BOLD, 'ID trace report') + '\n')
    f.write(common.r(common.REPORT_DIM, 'Search ID: ') + search_id + '\n')
    f.write(common.r(common.REPORT_DIM, 'Logs since: ') + since_str + '\n')
    f.write(common.r(common.REPORT_DIM, 'Collected logs: ') + os.path.abspath(logs_dir) + '\n')
    f.write(common.r(common.REPORT_DIM, 'Matching lines: ') + str(len(entries)) + '\n\n')
    if not entries:
        f.write(common.r(common.REPORT_DIM, '(No lines containing this ID in the collected logs.)') + '\n')
        return
    current_path = None
    for dt, path, line_no, line_text in entries:
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
        f.write('{}:{} {}'.format(ts, line_no, common.highlight_error_keywords(display)) + '\n')


def _build_timeline_html(search_id, since_str, logs_dir, entries):
    lines = []
    lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    lines.append('<title>ID trace: ' + common.html_escape(search_id) + '</title>')
    lines.append('<style>')
    lines.append('body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1400px;}')
    lines.append('h1{font-size:1.4rem;} h2{font-size:1.1rem;margin-top:1.5rem;color:#333;border-bottom:1px solid #ccc;padding-bottom:0.25rem;}')
    lines.append('.meta{color:#666;font-size:0.9rem;} pre{white-space:pre-wrap;word-break:break-all;font-size:0.85rem;background:#f8f8f8;padding:0.5rem;border-radius:4px;}')
    lines.append('.hl{background:#fce4a0;padding:0 2px;} .ts{color:#555;}')
    lines.append('</style></head><body>')
    lines.append('<h1>ID trace report</h1>')
    lines.append('<p class="meta"><strong>Search ID:</strong> ' + common.html_escape(search_id) + '</p>')
    lines.append('<p class="meta"><strong>Logs since:</strong> ' + common.html_escape(since_str) + '</p>')
    lines.append('<p class="meta"><strong>Collected logs:</strong> ' + common.html_escape(os.path.abspath(logs_dir)) + '</p>')
    lines.append('<p class="meta"><strong>Matching lines:</strong> ' + str(len(entries)) + ' (chronological; new log file = section header)</p>')
    if not entries:
        lines.append('<p class="meta">(No lines containing this ID in the collected logs.)</p>')
        lines.append('</body></html>')
        return '\n'.join(lines)
    current_path = None
    for dt, path, line_no, line_text in entries:
        if path != current_path:
            if current_path is not None:
                lines.append('</pre>')
            current_path = path
            lines.append('<h2>' + common.html_escape(path) + '</h2>')
            lines.append('<pre>')
        ts = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '?'
        display = common.line_for_display(line_text)
        lines.append('<span class="ts">' + common.html_escape(ts) + ':' + str(line_no) + '</span> ' + common.html_highlight_line(display))
    if entries:
        lines.append('</pre>')
    lines.append('</body></html>')
    return '\n'.join(lines)


def main():
    main_start = time_module.time()
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'
    _timeout = getattr(config, 'PROMPT_TIMEOUT_SEC', 0)

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, 'Trace ID in pod logs (controller)'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Collects pod logs via oc, then finds all lines containing your ID, ordered by time.'))
    print(common.c(_DIM, 'Error keywords from config are highlighted (same as mode 1).'))
    print(common.c(_DIM, 'On controller-0: a ZIP is created and an SSH download command is printed at the end (like mode 1).'))
    print('')
    print(common.c(_GREEN, 'Which ID do you want to trace in the pod logs?'))
    print(common.c(_DIM, '  (Any string that appears in log lines: LB network ID, server UUID, port ID,'))
    print(common.c(_DIM, '   floating IP, Neutron/Octavia resource ID, request-id, etc.)'))
    search_id = common.timed_input(common.c(_CYAN, 'Enter ID: '), '', timeout_sec=_timeout).strip()
    if not search_id:
        print(common.c(_YELLOW, 'No ID entered. Exiting.'))
        sys.exit(1)
    print('')
    print(common.c(_GREEN, 'Will collect logs and show every line containing: ') + common.c(_CYAN, search_id))

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
    print(common.c(_DIM, 'Choose which group of pods to collect (components in alphabetical order):'))
    menu_items = []
    for i, (component, group_pods) in enumerate(groups, 1):
        n = len(group_pods)
        menu_items.append((i, '{} ({} pod{})'.format(component, n, 's' if n != 1 else '')))
    menu_items.append((num_options, 'All pods ({} pods)'.format(total)))
    common.print_menu_columns(menu_items, num_columns=3, cell_width=38)
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
    print(common.c(_DIM, 'Choose how far back to collect (from latest timestamp):'))
    print('  1) 2h back  2) 1h back  3) 30m back  4) Custom (minutes)')
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
    print(common.c(_DIM, '  Scanning {} file(s) for "{}"...').format(len(log_paths), search_id), flush=True)
    entries = scan_log_paths_for_id(log_paths, search_id)
    print(common.c(_GREEN, '  Found {} matching line(s).').format(len(entries)), flush=True)

    run_dir = config.timestamped_report_dir('id_trace')
    os.makedirs(run_dir, exist_ok=True)
    report_path = os.path.join(run_dir, 'id_trace_report.txt')
    html_path = os.path.join(run_dir, 'id_trace_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        _write_text_timeline_report(f, search_id, since_str, logs_dir, entries)
    html_content = _build_timeline_html(search_id, since_str, logs_dir, entries)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    elapsed = time_module.time() - main_start
    print(common.c(_GREEN, 'Matching lines: {}.').format(len(entries)))
    print(common.c(_DIM, 'Time: {:.1f}s').format(elapsed))
    # Same as mode 1 on controller: ZIP + SSH command to copy report to your desktop
    common.print_download_prompt(
        html_path, report_path, report_logs_dir=None,
        local_mode=False, show_ssh_download=True,
    )


if __name__ == '__main__':
    main()
