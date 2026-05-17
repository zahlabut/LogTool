#!/usr/bin/python3
"""
Trace a specific ID across all OpenShift pod logs: collect via oc (like mode 1), find every line
containing the ID (plus context lines around each hit), order by time, show log path per section.
Error keywords highlighted in red. Run on controller-0 with oc access.
"""

import datetime
import gzip
import os
import re
import sys
import time as time_module

# OpenStack request id in log lines, e.g. req-d11ca9c1-a712-47e6-b3c5-bae9a94ef364
_REQ_ID_RE = re.compile(
    r'req-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)

import config
import logtool_common as common
from collect_and_analyze_pod_logs import (
    collect_logs_since,
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


def _extract_request_ids(line_text):
    return {m.group(0) for m in _REQ_ID_RE.finditer(line_text or '')}


def _count_id_lines_per_file(log_paths, search_id):
    counts = {}
    for path in log_paths:
        if not os.path.isfile(path):
            continue
        counts[path] = sum(1 for _ln, text in _iter_log_lines(path) if search_id in text)
    return counts


def build_trace_timeline(log_paths, search_id, context_lines=None):
    """
    1) Grep all logs for search_id; find first/last time and OpenStack req-* ids on those lines.
    2) From first ID time onward, include lines with the ID or the same req-* (octavia-worker, etc.).
    3) Add context lines around each hit.

    Returns (entries, first_dt, last_dt, request_ids, id_counts_per_file).
    entries: (dt, path, line_no, line_text, has_id, has_req)
    """
    if not search_id:
        return [], None, None, set(), {}
    if context_lines is None:
        context_lines = getattr(config, 'ID_TRACE_CONTEXT_LINES', 5)
    correlate = getattr(config, 'ID_TRACE_CORRELATE_REQUEST_IDS', True)
    id_counts = _count_id_lines_per_file(log_paths, search_id)

    request_ids = set()
    id_times = []
    for path in log_paths:
        if not os.path.isfile(path):
            continue
        for _line_no, line_text in _iter_log_lines(path):
            if search_id not in line_text:
                continue
            request_ids |= _extract_request_ids(line_text)
            dt, _ = common.get_line_date(line_text)
            if dt:
                id_times.append(dt)

    if not id_times:
        return [], None, None, request_ids, id_counts

    first_dt = min(id_times)
    last_dt = max(id_times)
    end_dt = last_dt + datetime.timedelta(minutes=2)
    if not correlate:
        request_ids = set()

    include_by_path = {}
    for path in log_paths:
        if not os.path.isfile(path):
            continue
        for line_no, line_text in _iter_log_lines(path):
            has_id = search_id in line_text
            has_req = bool(request_ids) and any(rid in line_text for rid in request_ids)
            if not has_id and not has_req:
                continue
            dt, _ = common.get_line_date(line_text)
            if dt is not None:
                if dt < first_dt or dt > end_dt:
                    continue
            nums = include_by_path.setdefault(path, set())
            nums.add(line_no)
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
            has_req = bool(request_ids) and any(rid in line_text for rid in request_ids) and not has_id
            entries.append((dt, path, line_no, line_text, has_id, has_req))

    def sort_key(item):
        dt, path, line_no, _, _, _ = item
        return (dt if dt is not None else sentinel, path, line_no)

    entries.sort(key=sort_key)
    return entries, first_dt, last_dt, request_ids, id_counts


def _log_display_name(path):
    """Short name for a collected log file (pod log basename)."""
    return os.path.basename(path) or path


def _line_prefix(has_id, has_req):
    if has_id:
        return '[ID] '
    if has_req:
        return '[req] '
    return '     '


def _write_text_timeline_report(f, search_id, collect_since_str, first_id_str, logs_dir, entries, context_lines, request_ids, id_counts):
    f.write(common.r(common.REPORT_BOLD, 'ID trace report') + '\n')
    f.write(common.r(common.REPORT_DIM, 'Search ID: ') + search_id + '\n')
    f.write(common.r(common.REPORT_DIM, 'Logs collected since: ') + collect_since_str + ' (auto)\n')
    if first_id_str:
        f.write(common.r(common.REPORT_DIM, 'Timeline starts at first ID: ') + first_id_str + '\n')
    f.write(common.r(common.REPORT_DIM, 'Collected logs: ') + os.path.abspath(logs_dir) + '\n')
    id_lines = sum(1 for e in entries if e[4])
    req_lines = sum(1 for e in entries if e[5])
    ctx_lines = len(entries) - id_lines - req_lines
    f.write(common.r(common.REPORT_DIM, 'Timeline lines: ') + str(len(entries)) + ' ({} [ID], {} [req], {} context)'.format(id_lines, req_lines, ctx_lines) + '\n')
    if request_ids:
        f.write(common.r(common.REPORT_DIM, 'Correlated request IDs (same OpenStack request as ID hits): ') + ', '.join(sorted(request_ids)[:8]))
        if len(request_ids) > 8:
            f.write(' ... (+{} more)'.format(len(request_ids) - 8))
        f.write('\n')
    f.write(common.r(common.REPORT_DIM, 'Note: octavia-worker often logs req-* but not the LB UUID; [req] lines are from other pods in the same request.') + '\n')
    f.write(common.r(common.REPORT_DIM, 'Context: ') + str(context_lines) + ' lines before/after each hit. ERROR keywords in red.\n\n')
    if id_counts:
        f.write(common.r(common.REPORT_BOLD, 'Direct ID matches per collected log file:') + '\n')
        for path in sorted(id_counts.keys(), key=lambda p: (-id_counts[p], _log_display_name(p))):
            n = id_counts[path]
            mark = '' if n else ' (0 — may still appear via [req])'
            f.write(common.r(common.REPORT_DIM, '  {}: {}{}\n').format(_log_display_name(path), n, mark))
        f.write('\n')
    if not entries:
        f.write(common.r(common.REPORT_DIM, '(No lines containing this ID in the collected logs.)') + '\n')
        f.write(common.r(common.REPORT_DIM, 'Try: All pods, increase ID_TRACE_COLLECT_MAX_HOURS in config, or check the ID string.') + '\n')
        return
    current_path = None
    for dt, path, line_no, line_text, has_id, has_req in entries:
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
        prefix = _line_prefix(has_id, has_req)
        f.write('{} {}:{} {}{}\n'.format(ts, _log_display_name(path), line_no, prefix, highlighted))

    files_in_timeline = sorted(set(e[1] for e in entries))
    f.write('\n')
    f.write(common.r(common.REPORT_DIM, 'Log files in timeline ({}): ').format(len(files_in_timeline)))
    f.write(', '.join(_log_display_name(p) for p in files_in_timeline) + '\n')


def _build_timeline_html(search_id, collect_since_str, first_id_str, logs_dir, entries, context_lines, request_ids, id_counts):
    id_lines = sum(1 for e in entries if e[4])
    req_lines = sum(1 for e in entries if e[5])
    lines = []
    lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    lines.append('<title>ID trace: ' + common.html_escape(search_id) + '</title>')
    lines.append('<style>')
    lines.append('body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1400px;}')
    lines.append('h1{font-size:1.4rem;} h2{font-size:1rem;margin-top:1.5rem;color:#333;border-bottom:1px solid #ccc;padding-bottom:0.25rem;word-break:break-all;}')
    lines.append('.meta{color:#666;font-size:0.9rem;} .timeline{margin:0;padding:0;list-style:none;}')
    lines.append('.timeline li{margin:0.15rem 0;font-family:ui-monospace,monospace;font-size:0.82rem;white-space:pre-wrap;word-break:break-all;}')
    lines.append('.hl{background:#fce4a0;padding:0 2px;} .ts{color:#555;} .ctx{color:#666;} .idtag{color:#06c;font-weight:600;} .reqtag{color:#080;font-weight:600;}')
    lines.append('</style></head><body>')
    lines.append('<h1>ID trace report</h1>')
    lines.append('<p class="meta"><strong>Search ID:</strong> ' + common.html_escape(search_id) + '</p>')
    lines.append('<p class="meta"><strong>Logs collected since:</strong> ' + common.html_escape(collect_since_str) + ' (auto)</p>')
    if first_id_str:
        lines.append('<p class="meta"><strong>Timeline starts at first ID:</strong> ' + common.html_escape(first_id_str) + '</p>')
    lines.append('<p class="meta"><strong>Collected logs:</strong> ' + common.html_escape(os.path.abspath(logs_dir)) + '</p>')
    lines.append('<p class="meta"><strong>Timeline:</strong> ' + str(len(entries)) + ' lines ({} <span class="idtag">[ID]</span>, {} <span class="reqtag">[req]</span>, {} context). Sorted by time.</p>'.format(
        id_lines, req_lines, len(entries) - id_lines - req_lines))
    if request_ids:
        lines.append('<p class="meta"><strong>Correlated request IDs:</strong> ' + common.html_escape(', '.join(sorted(request_ids)[:6])))
        if len(request_ids) > 6:
            lines.append(' ...')
        lines.append('</p>')
    lines.append('<p class="meta">octavia-worker and other pods often log <span class="reqtag">[req]</span> without the LB UUID. Context: ' + str(context_lines) + ' lines per hit.</p>')
    if not entries:
        lines.append('<p class="meta">(No lines containing this ID.) Try All pods and a longer time window.</p>')
        lines.append('</body></html>')
        return '\n'.join(lines)
    current_path = None
    for dt, path, line_no, line_text, has_id, has_req in entries:
        if path != current_path:
            if current_path is not None:
                lines.append('</ul>')
            current_path = path
            lines.append('<h2>Log file: ' + common.html_escape(path) + '</h2>')
            lines.append('<ul class="timeline">')
        ts = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '?'
        display = common.line_for_display(line_text)
        body = common.html_highlight_line(display)
        if has_id:
            tag = '<span class="idtag">[ID]</span> '
            li_cls = ''
        elif has_req:
            tag = '<span class="reqtag">[req]</span> '
            li_cls = ''
        else:
            tag = '<span class="ctx">     </span> '
            li_cls = ' class="ctx"'
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
    max_h = getattr(config, 'ID_TRACE_COLLECT_MAX_HOURS', 24)
    print(common.c(_DIM, 'Collects pod logs (auto, up to {}h back), greps your ID, finds first time it appears.'.format(max_h)))
    print(common.c(_DIM, 'Report: ID lines + same OpenStack req-* in other pods (worker, etc.), sorted by time.'))
    print(common.c(_DIM, 'ERROR keywords highlighted in red (same as mode 1). Tip: choose All pods.'))
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
    print(common.c(_CYAN, '[1/3] Pod list'))
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

    max_hours = getattr(config, 'ID_TRACE_COLLECT_MAX_HOURS', 24)
    now = datetime.datetime.utcnow()
    collect_since_dt = now - datetime.timedelta(hours=max_hours)
    since_iso = collect_since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    collect_since_str = collect_since_dt.strftime('%Y-%m-%d %H:%M:%S')

    print('')
    print(common.c(_CYAN, '[2/3] Collect logs (auto window)'))
    print(common.c(_DIM, '-' * 60))
    if os.path.isdir(logs_dir):
        for f in os.listdir(logs_dir):
            try:
                os.remove(os.path.join(logs_dir, f))
            except OSError:
                pass
    else:
        os.makedirs(logs_dir, exist_ok=True)
    print(common.c(_DIM, 'Auto: collecting up to {}h of logs per pod (since {}).').format(max_hours, collect_since_str), flush=True)
    print(common.c(_DIM, 'Logs directory: ') + common.c(_CYAN, logs_dir))
    log_paths = collect_logs_since(logs_dir, pods, since_iso)
    if not log_paths:
        print(common.c(_YELLOW, 'No log files collected. Exiting.'))
        sys.exit(1)

    print('')
    print(common.c(_CYAN, '[3/3] Grep ID, find first time, build timeline'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, '  Scanning {} file(s) for "{}" (+ correlated req-* )...').format(len(log_paths), search_id), flush=True)
    entries, first_dt, last_dt, request_ids, id_counts = build_trace_timeline(
        log_paths, search_id, context_lines=context_lines)
    if first_dt:
        first_id_str = first_dt.strftime('%Y-%m-%d %H:%M:%S')
        print(common.c(_GREEN, '  First ID logged at: ') + common.c(_CYAN, first_id_str), flush=True)
        if last_dt:
            print(common.c(_DIM, '  Last ID activity: ') + last_dt.strftime('%Y-%m-%d %H:%M:%S'), flush=True)
    else:
        first_id_str = ''
        if not id_counts or not any(id_counts.values()):
            print(common.c(_YELLOW, '  ID not found in collected logs.'), flush=True)
        else:
            print(common.c(_YELLOW, '  ID found but no parseable timestamps.'), flush=True)
    if request_ids:
        print(common.c(_DIM, '  Correlated {} request ID(s), e.g. {}').format(
            len(request_ids), sorted(request_ids)[0][:40] + '...'), flush=True)
    id_hits = sum(1 for e in entries if e[4])
    req_hits = sum(1 for e in entries if e[5])
    files_in = sorted(set(e[1] for e in entries))
    print(common.c(_GREEN, '  Timeline: {} lines ({} [ID], {} [req], {} files).').format(
        len(entries), id_hits, req_hits, len(files_in)), flush=True)
    if files_in:
        print(common.c(_DIM, '  Files: ') + ', '.join(_log_display_name(p) for p in files_in[:12])
              + (' ...' if len(files_in) > 12 else ''), flush=True)
    zero_id = [_log_display_name(p) for p, n in id_counts.items() if n == 0 and 'octavia' in p.lower()]
    if zero_id:
        print(common.c(_DIM, '  No direct ID in: ') + ', '.join(zero_id[:8]) + ' (check [req] lines in timeline)', flush=True)

    run_dir = config.timestamped_report_dir('id_trace')
    os.makedirs(run_dir, exist_ok=True)
    report_path = os.path.join(run_dir, 'id_trace_report.txt')
    html_path = os.path.join(run_dir, 'id_trace_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        _write_text_timeline_report(f, search_id, collect_since_str, first_id_str, logs_dir, entries, context_lines, request_ids, id_counts)
    html_content = _build_timeline_html(search_id, collect_since_str, first_id_str, logs_dir, entries, context_lines, request_ids, id_counts)
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
