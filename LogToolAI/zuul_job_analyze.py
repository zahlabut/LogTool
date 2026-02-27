#!/usr/bin/python3
"""
Analyze Zuul job logs (local directory): console result, tempest results (from tempest_results.html/xml, stestr_failing.txt),
tobiko results (from tobiko_results.html/xml), errors from all logs in directory and subdirs, report. Optional Ollama.
Run from LogToolMain or directly.
"""

import datetime
import hashlib
import html as html_module
import os
import re
import sys
import tempfile
import time as time_module
import gzip
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import config
import logtool_common as common

CONSOLE_LOG = 'job-output.txt'
TAIL_LINES = 400
# Only .log and .log.gz are scanned for error blocks (excludes .txt, .html, .xml, .yaml, etc.).
LOG_EXTENSIONS_FOR_GREP = ('.log', '.log.gz')
# Tempest result files we look for by name (anywhere under job dir).
TEMPEST_RESULT_NAMES = ('tempest_results.html', 'tempest_results.xml', 'stestr_failing.txt', 'tempest_results.log', 'tempest_results.log.gz')
# Tempest-related paths to use when no html/xml: build logs under tempest/ or named tempest*build*.log
TEMPEST_RELATED_PATTERN = re.compile(r'tempest.*build.*\.log$|^tempest[\-_].*\.log$', re.IGNORECASE)
def _is_tempest_related_path(job_dir, full_path):
    """True if path is under a 'tempest' dir or matches tempest build log naming."""
    rel = os.path.relpath(full_path, job_dir)
    parts = rel.split(os.sep)
    if any(p.lower() == 'tempest' for p in parts):
        return full_path.lower().endswith(('.log', '.yaml'))
    name = os.path.basename(full_path)
    return bool(TEMPEST_RELATED_PATTERN.search(name))

# Tobiko result files (pytest/JUnit style: tobiko_results.html, tobiko_results.xml).
TOBIKO_RESULT_NAMES = ('tobiko_results.html', 'tobiko_results.xml', 'tobiko_results.log', 'tobiko_results.log.gz')
TOBIKO_RELATED_PATTERN = re.compile(r'tobiko.*build.*\.log$|^tobiko[\-_].*\.log$', re.IGNORECASE)
def _is_tobiko_related_path(job_dir, full_path):
    """True if path is under a 'tobiko' dir or matches tobiko build/log naming."""
    rel = os.path.relpath(full_path, job_dir)
    parts = rel.split(os.sep)
    if any(p.lower() == 'tobiko' for p in parts):
        return full_path.lower().endswith(('.log', '.yaml', '.xml', '.html'))
    name = os.path.basename(full_path)
    return bool(TOBIKO_RELATED_PATTERN.search(name))


def _html_escape(s):
    return html_module.escape(str(s))


# Subdir next to main HTML report where per-log HTML files are written (linked from main).
REPORT_LOGS_SUBDIR = 'zuul_job_analysis_report_logs'


def _safe_log_filename(log_path, used_names=None):
    """Return a safe HTML filename for a log path (unique, readable). used_names is optional set to avoid collisions."""
    base = log_path.replace('/', '_').replace('\\', '_')
    base = re.sub(r'[^\w\-\.]', '_', base)
    base = base[-60:] if len(base) > 60 else (base or 'log')
    h = hashlib.md5(log_path.encode('utf-8', errors='replace')).hexdigest()[:8]
    name = base + '_' + h + '.html'
    if used_names is not None:
        while name in used_names:
            h = hashlib.md5((log_path + h).encode('utf-8', errors='replace')).hexdigest()[:8]
            name = base + '_' + h + '.html'
        used_names.add(name)
    return name


def _line_for_display(line_text):
    """Expand literal \\n and \\t in log lines so embedded tracebacks (e.g. in JSON details) format correctly."""
    if not line_text:
        return line_text
    return line_text.replace('\\n', '\n').replace('\\t', '\t')


def _html_highlight_line(line_text):
    """Escape and wrap ERROR_KEYWORDS in <span class="hl"> for HTML."""
    out = _html_escape(line_text)
    for kw in config.ERROR_KEYWORDS:
        k = (kw or '').strip()
        if not k:
            continue
        # Case-insensitive wrap of first occurrence only per keyword to avoid nested spans
        pat = re.compile(re.escape(k), re.IGNORECASE)
        out = pat.sub(lambda m: '<span class="hl">' + m.group(0) + '</span>', out)
    return out


def _build_html_report(source_path, job_info, report_entries, use_ollama, report_logs_dir=None, main_report_basename='zuul_job_analysis_report.html', ai_cache=None, viewer_links=None):
    """
    Build main HTML report. If report_logs_dir is set, write one HTML file per log (error blocks)
    and in the deployment section emit links to those files instead of inlining content (keeps main short).
    ai_cache: optional dict sig -> (keep, explanation) for Ollama explanations in report.
    viewer_links: optional dict log_path -> viewer_basename (e.g. "view_xxx.html") for "View in log at line N" links.
    """
    ai_cache = ai_cache or {}
    viewer_links = viewer_links or {}
    lines = []
    lines.append('<!DOCTYPE html>')
    lines.append('<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    lines.append('<title>Zuul job analysis report</title>')
    lines.append('<style>')
    lines.append('body { font-family: system-ui, sans-serif; margin: 1rem 2rem; max-width: 1200px; }')
    lines.append('nav { margin: 1rem 0 2rem; } nav ul { list-style: none; padding: 0; } nav li { margin: 0.5rem 0; }')
    lines.append('a { color: #06c; } a:hover { text-decoration: underline; }')
    lines.append('h1 { font-size: 1.5rem; } h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc; }')
    lines.append('section { margin-bottom: 2rem; }')
    lines.append('.meta { color: #666; font-size: 0.9rem; margin-bottom: 1rem; }')
    lines.append('.job-block { margin: 1rem 0; padding: 0.75rem; background: #f8f8f8; border-radius: 4px; }')
    lines.append('.job-id { font-weight: bold; } .job-dir { font-size: 0.9rem; color: #555; }')
    lines.append('pre { white-space: pre-wrap; word-break: break-all; background: #f5f5f5; padding: 0.75rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem; }')
    lines.append('.hl { background: #fce4a0; padding: 0 2px; }')
    lines.append('.block-meta { font-size: 0.9rem; color: #666; margin-bottom: 0.25rem; }')
    lines.append('.test-list { font-size: 0.9rem; margin-top: 0.5rem; }')
    lines.append('.test-list table { border-collapse: collapse; width: 100%; max-width: 800px; }')
    lines.append('.test-list th, .test-list td { text-align: left; padding: 0.2rem 0.5rem; border-bottom: 1px solid #eee; }')
    lines.append('.test-list .pass { color: #0a0; } .test-list .fail { color: #c00; } .test-list .error { color: #c00; } .test-list .skip { color: #666; }')
    lines.append('.log-links { list-style: none; padding: 0; } .log-links li { margin: 0.4rem 0; }')
    lines.append('.ollama-explanation { margin-top: 0.5rem; padding: 0.5rem; background: #e8f4f8; border-left: 3px solid #06c; font-size: 0.9rem; color: #333; }')
    lines.append('</style>')
    lines.append('</head><body>')
    lines.append('<h1>Zuul job analysis report</h1>')
    lines.append('<p class="meta">Source path: ' + _html_escape(source_path) + ' &middot; AI filter: ' + ('on' if use_ollama else 'off') + '</p>')
    lines.append('<nav><ul>')
    lines.append('<li><a href="#console">Console log findings</a></li>')
    lines.append('<li><a href="#tempest">Tempest result</a></li>')
    lines.append('<li><a href="#tobiko">Tobiko result</a></li>')
    lines.append('<li><a href="#deployment">Deployment result (analyzed logs)</a></li>')
    lines.append('</ul></nav>')

    # Section: Console log findings
    lines.append('<section id="console"><h2>Console log findings</h2>')
    for info in job_info:
        lines.append('<div class="job-block">')
        lines.append('<div class="job-id">' + _html_escape(info['id']) + '</div>')
        lines.append('<div class="job-dir">' + _html_escape(info['dir']) + '</div>')
        lines.append('<p><strong>Result:</strong> ' + _html_escape(info['console_result']) + ' &mdash; ' + _html_escape(info['console_detail']) + '</p>')
        lines.append('</div>')
    lines.append('</section>')

    # Section: Tempest result
    lines.append('<section id="tempest"><h2>Tempest result</h2>')
    for info in job_info:
        lines.append('<div class="job-block">')
        lines.append('<div class="job-id">' + _html_escape(info['id']) + '</div>')
        lines.append('<div class="job-dir">' + _html_escape(info['dir']) + '</div>')
        lines.append('<p><strong>Summary:</strong> ' + _html_escape(info['tempest_summary']) + '</p>')
        if info.get('tempest_paths'):
            rels = [os.path.relpath(p, info['dir']) for p in info['tempest_paths'].values()]
            lines.append('<p class="job-dir">Tempest result files: ' + _html_escape(', '.join(rels)) + '</p>')
        details = info.get('tempest_details') or []
        if details:
            lines.append('<div class="test-list"><p><strong>Tests (details):</strong></p><table><thead><tr><th>Status</th><th>Test name</th></tr></thead><tbody>')
            for t in details:
                st = t['status'].lower()
                lines.append('<tr><td class="' + st + '">' + _html_escape(t['status'].upper()) + '</td><td>' + _html_escape(t['name']) + '</td></tr>')
            lines.append('</tbody></table></div>')
        if info.get('tempest_related_paths'):
            rels = [os.path.relpath(p, info['dir']) for p in info['tempest_related_paths']]
            lines.append('<p class="job-dir">Tempest-related files (build logs / under tempest/): ' + _html_escape(', '.join(rels)) + '</p>')
        lines.append('</div>')
    lines.append('</section>')

    # Section: Tobiko result
    lines.append('<section id="tobiko"><h2>Tobiko result</h2>')
    for info in job_info:
        lines.append('<div class="job-block">')
        lines.append('<div class="job-id">' + _html_escape(info['id']) + '</div>')
        lines.append('<div class="job-dir">' + _html_escape(info['dir']) + '</div>')
        lines.append('<p><strong>Summary:</strong> ' + _html_escape(info['tobiko_summary']) + '</p>')
        if info.get('tobiko_paths'):
            rels = [os.path.relpath(p, info['dir']) for p in info['tobiko_paths'].values()]
            lines.append('<p class="job-dir">Tobiko result files: ' + _html_escape(', '.join(rels)) + '</p>')
        details = info.get('tobiko_details') or []
        if details:
            lines.append('<div class="test-list"><p><strong>Tests (details):</strong></p><table><thead><tr><th>Status</th><th>Test name</th></tr></thead><tbody>')
            for t in details:
                st = t['status'].lower()
                lines.append('<tr><td class="' + st + '">' + _html_escape(t['status'].upper()) + '</td><td>' + _html_escape(t['name']) + '</td></tr>')
            lines.append('</tbody></table></div>')
        if info.get('tobiko_related_paths'):
            rels = [os.path.relpath(p, info['dir']) for p in info['tobiko_related_paths']]
            lines.append('<p class="job-dir">Tobiko-related files (build logs / under tobiko/): ' + _html_escape(', '.join(rels)) + '</p>')
        lines.append('</div>')
    lines.append('</section>')

    # Section: Deployment result (analyzed logs / error blocks)
    lines.append('<section id="deployment"><h2>Deployment result (analyzed logs)</h2>')
    if not report_entries:
        lines.append('<p class="meta">(No error blocks to report.)</p>')
    elif report_logs_dir:
        # Per-log HTML files: write each log's blocks to a separate file, link from main (keeps main short)
        os.makedirs(report_logs_dir, exist_ok=True)
        used = set()
        # Unique paths with block count, sorted by blocks descending (most errors first)
        path_counts = [(path, sum(1 for e in report_entries if e[0] == path)) for path in set(e[0] for e in report_entries)]
        path_counts.sort(key=lambda x: -x[1])
        lines.append('<p class="meta">Logs with error blocks (click to open, sorted by block count):</p>')
        lines.append('<ul class="log-links">')
        for p, n_blocks in path_counts:
            safe_name = _safe_log_filename(p, used)
            # Short label: parent/name (e.g. neutron-api/0.log) so links are short but distinguishable
            parts = p.replace('\\', '/').rstrip('/').split('/')
            link_text = '/'.join(parts[-2:]) if len(parts) >= 2 else os.path.basename(p)
            lines.append('<li><a href="' + _html_escape(REPORT_LOGS_SUBDIR + '/' + safe_name) + '">' + _html_escape(link_text) + '</a> <span class="meta">(' + str(n_blocks) + ' block' + ('s' if n_blocks != 1 else '') + ')</span></li>')
            # Write per-log HTML
            log_lines = []
            log_lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Log: ' + _html_escape(p) + '</title>')
            log_lines.append('<style>body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1200px;} pre{white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:0.75rem;border-radius:4px;font-size:0.85rem;} .hl{background:#fce4a0;padding:0 2px;} .block-meta{color:#666;margin-bottom:0.25rem;} .ollama-explanation{margin-top:0.5rem;padding:0.5rem;background:#e8f4f8;border-left:3px solid #06c;font-size:0.9rem;} a{color:#06c;}</style></head><body>')
            log_lines.append('<p><a href="' + _html_escape('../' + main_report_basename) + '">&larr; Back to main report</a></p>')
            log_lines.append('<h2>' + _html_escape(p) + '</h2>')
            for (fp, lines_with_nums, block_text, sig, count) in report_entries:
                if fp != p:
                    continue
                log_lines.append('<p class="block-meta">(occurred ' + str(count) + ' time' + ('s' if count != 1 else '') + ')</p>')
                block_lines = []
                for line_no, line_text in lines_with_nums[:config.MAX_BLOCK_LINES_SHOWN]:
                    display = _line_for_display(line_text)
                    for i, part in enumerate(display.splitlines()):
                        prefix = (str(line_no) + ': ') if i == 0 else '      '
                        block_lines.append(prefix + _html_highlight_line(part))
                if len(lines_with_nums) > config.MAX_BLOCK_LINES_SHOWN:
                    block_lines.append('... (' + str(len(lines_with_nums) - config.MAX_BLOCK_LINES_SHOWN) + ' more lines)')
                log_lines.append('<pre>' + '\n'.join(block_lines) + '</pre>')
                if use_ollama and sig in ai_cache:
                    _, expl = ai_cache[sig]
                    if expl and expl.strip():
                        log_lines.append('<p class="ollama-explanation"><strong>Ollama:</strong> ' + _html_escape(expl.strip()) + '</p>')
                if fp in viewer_links and lines_with_nums:
                    first_ln = lines_with_nums[0][0]
                    log_lines.append('<p><a href="' + _html_escape(viewer_links[fp] + '#L' + str(first_ln)) + '">View in log at line ' + str(first_ln) + '</a></p>')
            log_path = os.path.join(report_logs_dir, safe_name)
            try:
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(log_lines))
            except OSError:
                pass
        lines.append('</ul>')
    else:
        for p in sorted(set(e[0] for e in report_entries)):
            lines.append('<h3>' + _html_escape(p) + '</h3>')
            for (fp, lines_with_nums, block_text, sig, count) in report_entries:
                if fp != p:
                    continue
                lines.append('<p class="block-meta">(occurred ' + str(count) + ' time' + ('s' if count != 1 else '') + ')</p>')
                block_lines = []
                for line_no, line_text in lines_with_nums[:config.MAX_BLOCK_LINES_SHOWN]:
                    display = _line_for_display(line_text)
                    for i, part in enumerate(display.splitlines()):
                        prefix = (str(line_no) + ': ') if i == 0 else '      '
                        block_lines.append(prefix + _html_highlight_line(part))
                if len(lines_with_nums) > config.MAX_BLOCK_LINES_SHOWN:
                    block_lines.append('... (' + str(len(lines_with_nums) - config.MAX_BLOCK_LINES_SHOWN) + ' more lines)')
                lines.append('<pre>' + '\n'.join(block_lines) + '</pre>')
                if use_ollama and sig in ai_cache:
                    _, expl = ai_cache[sig]
                    if expl and expl.strip():
                        lines.append('<p class="ollama-explanation"><strong>Ollama:</strong> ' + _html_escape(expl.strip()) + '</p>')
                if fp in viewer_links and lines_with_nums:
                    first_ln = lines_with_nums[0][0]
                    lines.append('<p><a href="' + _html_escape(viewer_links[fp] + '#L' + str(first_ln)) + '">View in log at line ' + str(first_ln) + '</a></p>')
    lines.append('</section>')
    lines.append('</body></html>')
    return '\n'.join(lines)


def discover_zuul_job_dirs(path):
    """
    Return list of absolute paths to Zuul job directories.
    If path/job-output.txt exists, path is a single job dir -> [path].
    Else list immediate subdirs that contain job-output.txt (multiple jobs).
    If none, search recursively (so downloaded external/.../job-output.txt is found).
    """
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return []
    console = os.path.join(path, CONSOLE_LOG)
    if os.path.isfile(console):
        return [path]
    jobs = []
    try:
        for name in sorted(os.listdir(path)):
            sub = os.path.join(path, name)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, CONSOLE_LOG)):
                jobs.append(sub)
        # After URL download, logs may be under external/<host>/.../job-output.txt
        if not jobs:
            for root, _dirs, filenames in os.walk(path):
                if CONSOLE_LOG in filenames:
                    jobs.append(root)
    except OSError:
        pass
    return jobs


def _console_tempest_tobiko_hints(console_path, max_bytes=800000):
    """
    Read console log and extract tempest/tobiko pass-fail hints (Ran N tests, OK/FAILED, passed/failed counts).
    Returns (tempest_hint_str, tobiko_hint_str); each is '' if nothing found.
    """
    if not console_path or not os.path.isfile(console_path):
        return ('', '')
    try:
        size = os.path.getsize(console_path)
        with open(console_path, 'r', errors='ignore') as f:
            if size > max_bytes:
                f.seek(max(0, size - max_bytes))
                f.readline()
            content = f.read()
    except Exception:
        return ('', '')
    if not content.strip():
        return ('', '')

    def _tempest_hints(text):
        parts = []
        m = re.search(r'Ran\s+(\d+)\s+test', text, re.IGNORECASE)
        if m:
            parts.append('Ran {} tests'.format(m.group(1)))
        m = re.search(r'(\d+)\s+passed', text, re.IGNORECASE)
        if m:
            parts.append('{} passed'.format(m.group(1)))
        m = re.search(r'(\d+)\s+failed', text, re.IGNORECASE)
        if m:
            parts.append('{} failed'.format(m.group(1)))
        m = re.search(r'failures?\s*=\s*(\d+)', text, re.IGNORECASE)
        if m and int(m.group(1)) > 0:
            parts.append('failures={}'.format(m.group(1)))
        if re.search(r'\bFAILED\b', text) and not re.search(r'\bOK\b.*\d+ passed', text, re.DOTALL):
            if 'OK' not in ' '.join(parts):
                parts.append('FAILED')
        elif re.search(r'\bOK\b', text) and 'failed' not in ' '.join(parts).lower():
            parts.append('OK')
        if not parts and re.search(r'tempest', text, re.IGNORECASE):
            if re.search(r'tempest.*(fail|error)', text, re.IGNORECASE):
                parts.append('tempest mentioned (fail/error in console)')
            else:
                parts.append('tempest mentioned in console')
        # Only attribute to tempest if tempest/stestr appears in console (avoid tobiko output)
        if parts and not re.search(r'tempest|stestr', text, re.IGNORECASE):
            return ''
        return '; '.join(parts) if parts else ''

    def _tobiko_hints(text):
        parts = []
        if not re.search(r'tobiko', text, re.IGNORECASE):
            return ''
        m = re.search(r'Ran\s+(\d+)\s+test', text, re.IGNORECASE)
        if m:
            parts.append('Ran {} tests'.format(m.group(1)))
        m = re.search(r'(\d+)\s+passed', text, re.IGNORECASE)
        if m:
            parts.append('{} passed'.format(m.group(1)))
        m = re.search(r'(\d+)\s+failed', text, re.IGNORECASE)
        if m:
            parts.append('{} failed'.format(m.group(1)))
        m = re.search(r'failures?\s*=\s*(\d+)', text, re.IGNORECASE)
        if m and int(m.group(1)) > 0:
            parts.append('failures={}'.format(m.group(1)))
        if re.search(r'\bFAILED\b', text):
            parts.append('FAILED')
        elif re.search(r'\bOK\b', text):
            parts.append('OK')
        if re.search(r'tobiko.*(fail|error)', text, re.IGNORECASE) and not parts:
            parts.append('fail/error mentioned with tobiko')
        if not parts:
            parts.append('tobiko mentioned in console')
        return '; '.join(parts) if parts else ''

    t = _tempest_hints(content)
    b = _tobiko_hints(content)
    if t:
        t = t + ' (from console)'
    if b:
        b = b + ' (from console)'
    return (t, b)


def _read_tail(path, num_lines=TAIL_LINES, max_bytes=500000):
    """Read last num_lines (or last max_bytes) from file. Return list of lines."""
    try:
        size = os.path.getsize(path)
        with open(path, 'r', errors='ignore') as f:
            if size > max_bytes:
                f.seek(max(0, size - max_bytes))
                f.readline()
            lines = f.readlines()
        return lines[-num_lines:] if len(lines) > num_lines else lines
    except Exception:
        return []


def get_console_result(job_dir):
    """
    Infer job result from end of job-output.txt.
    Returns (result_str, detail_str): result_str in ('SUCCESS', 'FAILURE', 'UNKNOWN'), detail optional.
    """
    console = os.path.join(job_dir, CONSOLE_LOG)
    if not os.path.isfile(console):
        return ('UNKNOWN', 'No job-output.txt')
    lines = _read_tail(console)
    text = '\n'.join(lines)
    # Zuul / Ansible: PLAY RECAP with failed=0 vs failed>0
    recap = re.search(r'PLAY RECAP.*?failed=(\d+)', text, re.DOTALL | re.IGNORECASE)
    if recap:
        n = int(recap.group(1))
        if n == 0:
            return ('SUCCESS', 'PLAY RECAP: failed=0')
        return ('FAILURE', 'PLAY RECAP: failed={}'.format(n))
    # Common markers
    if re.search(r'\b(SUCCESS|Job succeeded|Build succeeded)\b', text, re.IGNORECASE):
        return ('SUCCESS', 'Console indicates success')
    if re.search(r'\b(FAILURE|FAILED|Job failed|Build failed|TASK \[.*\] failed)\b', text, re.IGNORECASE):
        return ('FAILURE', 'Console indicates failure')
    return ('UNKNOWN', 'Could not determine from console tail')


# Max bytes to scan from start of console for tempest start, and from end for failure time.
_CONSOLE_HEAD_BYTES = 1500000
_CONSOLE_TAIL_BYTES = 600000


def get_console_since_dt(job_dir):
    """
    Determine since_dt to limit log analysis from console (job-output.txt).
    - If tempest stage was reached: since_dt = time when tempest started (analyze from then).
    - If job failed before tempest: since_dt = failure_time - 5 min (analyze last 5 min before failure).
    - If neither can be determined: since_dt = None (analyze full logs).
    Returns (since_dt, reason_str).
    """
    console = os.path.join(job_dir, CONSOLE_LOG)
    if not os.path.isfile(console):
        return (None, 'no console')
    tempest_start_dt = None
    failure_dt = None
    try:
        size = os.path.getsize(console)
        # Scan head for tempest start (first occurrence of tempest run / stestr / play tempest)
        with open(console, 'r', errors='ignore') as f:
            head = f.read(_CONSOLE_HEAD_BYTES)
        for line in head.splitlines():
            dt, _ = common.get_line_date(line)
            if not dt:
                continue
            lower = line.lower()
            if not tempest_start_dt and (
                'tempest' in lower and ('run' in lower or 'stestr' in lower or 'play [' in lower or 'execute' in lower or 'running' in lower)
                or 'stestr run' in lower
                or re.search(r'play\s*\[.*tempest', lower)
                or re.search(r'task\s*\[.*tempest', lower)
            ):
                tempest_start_dt = dt
                break
        # Scan tail for failure time (fatal:, PLAY RECAP with failed>0, TASK [.*] failed)
        with open(console, 'r', errors='ignore') as f:
            if size > _CONSOLE_TAIL_BYTES:
                f.seek(max(0, size - _CONSOLE_TAIL_BYTES))
                f.readline()
            tail = f.read()
        for line in tail.splitlines():
            dt, _ = common.get_line_date(line)
            if not dt:
                continue
            lower = line.lower()
            if 'fatal:' in lower or 'fatal [' in lower:
                failure_dt = dt
                break
            if 'play recap' in lower and 'failed=' in lower:
                failure_dt = dt
                break
            if re.search(r'task\s*\[.*\]\s*failed', lower):
                failure_dt = dt
                break
        # Decide since_dt
        if tempest_start_dt is not None:
            return (tempest_start_dt, 'tempest started at {}'.format(tempest_start_dt.strftime('%Y-%m-%d %H:%M')))
        if failure_dt is not None:
            since = failure_dt - datetime.timedelta(minutes=5)
            return (since, 'job failed at {}, analyzing from -5 min'.format(failure_dt.strftime('%Y-%m-%d %H:%M')))
    except Exception:
        pass
    return (None, 'no timestamp found, analyzing full logs')


def discover_all_log_and_tempest_files(job_dir):
    """
    Walk entire job_dir and all subdirs. Return (log_paths, tempest_paths, tempest_related_paths, tobiko_paths, tobiko_related_paths).
    log_paths: only *.log and *.log.gz (files we grep for error blocks; excludes .txt, .html, .xml).
    tempest_paths: dict keyed by basename for tempest_results.html, tempest_results.xml, stestr_failing.txt, etc.
    tempest_related_paths: list of paths under tempest/ or named like tempest*build*.log (for summary when no html/xml).
    tobiko_paths: dict keyed by basename for tobiko_results.html, tobiko_results.xml, etc.
    tobiko_related_paths: list of paths under tobiko/ or named like tobiko*build*.log.
    """
    job_dir = os.path.abspath(job_dir)
    log_paths = []
    tempest_paths = {}
    tempest_related_paths = []
    tobiko_paths = {}
    tobiko_related_paths = []
    try:
        for root, _dirs, filenames in os.walk(job_dir):
            for name in filenames:
                full = os.path.join(root, name)
                lower = name.lower()
                # Tempest result files (by name)
                if name in TEMPEST_RESULT_NAMES or (name == 'tempest_results.log.gz'):
                    tempest_paths[name] = full
                # Tempest-related (e.g. tempest/tempest-build.log, tempest/tempest-all/tempest-all-build.log)
                if _is_tempest_related_path(job_dir, full):
                    tempest_related_paths.append(full)
                # Tobiko result files (by name)
                if name in TOBIKO_RESULT_NAMES or (name == 'tobiko_results.log.gz'):
                    tobiko_paths[name] = full
                # Tobiko-related (e.g. tobiko/ dir, tobiko*build*.log)
                if _is_tobiko_related_path(job_dir, full):
                    tobiko_related_paths.append(full)
                # Only .log and .log.gz are scanned for error blocks (no .txt, .html, .xml)
                if any(lower.endswith(ext) for ext in LOG_EXTENSIONS_FOR_GREP):
                    log_paths.append(full)
    except OSError:
        pass
    return (sorted(log_paths), tempest_paths, sorted(tempest_related_paths), tobiko_paths, sorted(tobiko_related_paths))


def _parse_junit_testcases(xml_path):
    """
    Parse JUnit-style XML and return list of dicts: [{'name': str, 'status': 'pass'|'fail'|'error'|'skip'}, ...].
    Handles namespaced tags (e.g. testsuite, testcase).
    """
    out = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag != 'testcase':
                continue
            name = elem.get('name') or ''
            classname = (elem.get('classname') or '').strip()
            full_name = (classname + '.' + name).strip('.') or name or ('(unnamed)')
            status = 'pass'
            for child in elem:
                ctag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if ctag == 'failure':
                    status = 'fail'
                    break
                if ctag == 'error':
                    status = 'error'
                    break
                if ctag == 'skipped':
                    status = 'skip'
                    break
            out.append({'name': full_name, 'status': status})
    except Exception:
        pass
    return out


def get_tempest_details(job_dir, tempest_paths):
    """
    Return list of per-test results for tempest: [{'name': str, 'status': 'pass'|'fail'|'error'|'skip'}, ...].
    Uses tempest_results.xml (JUnit) and stestr_failing.txt (failed test IDs).
    """
    details = []
    seen = set()
    xml_path = tempest_paths.get('tempest_results.xml')
    if xml_path and os.path.isfile(xml_path):
        for t in _parse_junit_testcases(xml_path):
            key = (t['name'], t['status'])
            if key not in seen:
                seen.add(key)
                details.append(t)
    stestr_path = tempest_paths.get('stestr_failing.txt')
    if stestr_path and os.path.isfile(stestr_path):
        try:
            with open(stestr_path, 'r', errors='ignore') as f:
                for line in f:
                    name = line.strip()
                    if not name or name.startswith('#'):
                        continue
                    if (name, 'fail') not in seen:
                        seen.add((name, 'fail'))
                        details.append({'name': name, 'status': 'fail'})
        except Exception:
            pass
    return sorted(details, key=lambda x: (x['status'] != 'pass', x['name']))


def get_tobiko_details(job_dir, tobiko_paths):
    """
    Return list of per-test results for Tobiko: [{'name': str, 'status': 'pass'|'fail'|'error'|'skip'}, ...].
    Uses tobiko_results.xml (JUnit).
    """
    xml_path = tobiko_paths.get('tobiko_results.xml')
    if not xml_path or not os.path.isfile(xml_path):
        return []
    details = _parse_junit_testcases(xml_path)
    return sorted(details, key=lambda x: (x['status'] != 'pass', x['name']))


def get_tempest_summary(job_dir, tempest_paths, tempest_related_paths=None):
    """
    Build tempest summary from dedicated files: tempest_results.html, tempest_results.xml, stestr_failing.txt,
    tempest_results.log; if none found, try tempest_related_paths (e.g. tempest-build.log, tempest-all-build.log).
    tempest_paths is dict from discover_all_log_and_tempest_files (basename -> full path).
    """
    parts = []
    rel_prefix = os.path.join(job_dir, '')
    # tempest_results.xml (JUnit-style: testsuite tests= failures= errors=)
    xml_path = tempest_paths.get('tempest_results.xml')
    if xml_path and os.path.isfile(xml_path):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            found = False
            for suite in root.iter():
                if suite.tag.endswith('testsuite') or suite.tag == 'testsuite':
                    tests = suite.get('tests')
                    failures = suite.get('failures')
                    errors = suite.get('errors')
                    skipped = suite.get('skipped')
                    if tests is not None:
                        parts.append('tests={}'.format(tests))
                    if failures is not None and int(failures) > 0:
                        parts.append('failures={}'.format(failures))
                    if errors is not None and int(errors) > 0:
                        parts.append('errors={}'.format(errors))
                    if skipped is not None and int(skipped) > 0:
                        parts.append('skipped={}'.format(skipped))
                    found = True
                    break
            if found:
                rel = os.path.relpath(xml_path, job_dir) if xml_path.startswith(rel_prefix) else xml_path
                parts.append('(from {})'.format(rel))
            else:
                parts.append('tempest_results.xml found (no testsuite)')
        except Exception:
            parts.append('tempest_results.xml found (parse failed)')
    # tempest_results.html - regex for counts
    html_path = tempest_paths.get('tempest_results.html')
    if html_path and os.path.isfile(html_path) and 'tests=' not in ' '.join(parts):
        try:
            with open(html_path, 'r', errors='ignore') as f:
                content = f.read()
            m = re.search(r'(\d+)\s+passed|passed\s*[:\s]*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('passed={}'.format(m.group(1) or m.group(2)))
            m = re.search(r'(\d+)\s+failed|failed\s*[:\s]*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('failed={}'.format(m.group(1) or m.group(2)))
            if parts and not any('from ' in p for p in parts):
                rel = os.path.relpath(html_path, job_dir) if html_path.startswith(rel_prefix) else html_path
                parts.append('(from {})'.format(rel))
        except Exception:
            pass
    # stestr_failing.txt - list of failing test ids
    stestr_path = tempest_paths.get('stestr_failing.txt')
    if stestr_path and os.path.isfile(stestr_path):
        try:
            with open(stestr_path, 'r', errors='ignore') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            if lines:
                parts.append('{} failing test(s) in stestr_failing.txt'.format(len(lines)))
                rel = os.path.relpath(stestr_path, job_dir) if stestr_path.startswith(rel_prefix) else stestr_path
                parts.append('(path: {})'.format(rel))
        except Exception:
            pass
    # tempest_results.log or .log.gz - Ran N tests, OK/FAILED
    for key in ('tempest_results.log', 'tempest_results.log.gz'):
        p = tempest_paths.get(key)
        if not p or not os.path.isfile(p):
            continue
        try:
            if key.endswith('.gz'):
                f = gzip.open(p, 'rt', errors='ignore')
            else:
                f = open(p, 'r', errors='ignore')
            with f:
                content = f.read(100000)
            m = re.search(r'Ran\s+(\d+)\s+test', content, re.IGNORECASE)
            if m and 'Ran ' not in ' '.join(parts):
                parts.append('Ran {} tests'.format(m.group(1)))
            m = re.search(r'\b(OK|FAILED)\s*\(', content)
            if m:
                parts.append(m.group(1))
            m = re.search(r'failures?\s*=\s*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('failures={}'.format(m.group(1)))
        except Exception:
            pass
    # Fallback: tempest build logs (e.g. tempest/tempest-build.log, tempest/tempest-all/tempest-all-build.log)
    if not parts and tempest_related_paths:
        for p in tempest_related_paths:
            if not p.lower().endswith('.log') or not os.path.isfile(p):
                continue
            try:
                with open(p, 'r', errors='ignore') as f:
                    content = f.read(100000)
                if not content.strip():
                    continue
                if 'Ran ' not in ' '.join(parts):
                    m = re.search(r'Ran\s+(\d+)\s+test', content, re.IGNORECASE)
                    if m:
                        parts.append('Ran {} tests'.format(m.group(1)))
                m = re.search(r'\b(OK|FAILED)\s*[\(\s]', content)
                if m and not any(m.group(1) in part for part in parts):
                    parts.append(m.group(1))
                m = re.search(r'failures?\s*=\s*(\d+)', content, re.IGNORECASE)
                if m:
                    parts.append('failures={}'.format(m.group(1)))
                if parts:
                    rel = os.path.relpath(p, job_dir) if p.startswith(rel_prefix) else p
                    parts.append('(from {})'.format(rel))
                    break
            except Exception:
                continue
    if parts:
        return '; '.join(parts)
    # Fallback: scan console log (job-output.txt) for tempest pass/fail hints
    console_path = os.path.join(job_dir, CONSOLE_LOG)
    tempest_hint, _ = _console_tempest_tobiko_hints(console_path)
    if tempest_hint:
        return tempest_hint
    if tempest_related_paths:
        rels = [os.path.relpath(p, job_dir) if p.startswith(rel_prefix) else p for p in tempest_related_paths[:10]]
        return 'No summary in tempest result files; tempest-related files found: ' + ', '.join(rels)
    return 'No tempest result files found (looked for tempest_results.html, .xml, stestr_failing.txt under job dir)'


def get_tobiko_summary(job_dir, tobiko_paths, tobiko_related_paths=None):
    """
    Build Tobiko summary from tobiko_results.html, tobiko_results.xml (JUnit/pytest style);
    if none found, try tobiko_related_paths (e.g. logs under tobiko/).
    """
    parts = []
    rel_prefix = os.path.join(job_dir, '')
    # tobiko_results.xml (JUnit-style testsuite)
    xml_path = tobiko_paths.get('tobiko_results.xml')
    if xml_path and os.path.isfile(xml_path):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            found = False
            for suite in root.iter():
                if suite.tag.endswith('testsuite') or suite.tag == 'testsuite':
                    tests = suite.get('tests')
                    failures = suite.get('failures')
                    errors = suite.get('errors')
                    skipped = suite.get('skipped')
                    if tests is not None:
                        parts.append('tests={}'.format(tests))
                    if failures is not None and int(failures) > 0:
                        parts.append('failures={}'.format(failures))
                    if errors is not None and int(errors) > 0:
                        parts.append('errors={}'.format(errors))
                    if skipped is not None and int(skipped) > 0:
                        parts.append('skipped={}'.format(skipped))
                    found = True
                    break
            if found:
                rel = os.path.relpath(xml_path, job_dir) if xml_path.startswith(rel_prefix) else xml_path
                parts.append('(from {})'.format(rel))
            else:
                parts.append('tobiko_results.xml found (no testsuite)')
        except Exception:
            parts.append('tobiko_results.xml found (parse failed)')
    # tobiko_results.html
    html_path = tobiko_paths.get('tobiko_results.html')
    if html_path and os.path.isfile(html_path) and 'tests=' not in ' '.join(parts):
        try:
            with open(html_path, 'r', errors='ignore') as f:
                content = f.read()
            m = re.search(r'(\d+)\s+passed|passed\s*[:\s]*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('passed={}'.format(m.group(1) or m.group(2)))
            m = re.search(r'(\d+)\s+failed|failed\s*[:\s]*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('failed={}'.format(m.group(1) or m.group(2)))
            if parts and not any('from ' in p for p in parts):
                rel = os.path.relpath(html_path, job_dir) if html_path.startswith(rel_prefix) else html_path
                parts.append('(from {})'.format(rel))
        except Exception:
            pass
    # tobiko_results.log or .log.gz
    for key in ('tobiko_results.log', 'tobiko_results.log.gz'):
        p = tobiko_paths.get(key)
        if not p or not os.path.isfile(p):
            continue
        try:
            if key.endswith('.gz'):
                f = gzip.open(p, 'rt', errors='ignore')
            else:
                f = open(p, 'r', errors='ignore')
            with f:
                content = f.read(100000)
            m = re.search(r'Ran\s+(\d+)\s+test', content, re.IGNORECASE)
            if m and 'Ran ' not in ' '.join(parts):
                parts.append('Ran {} tests'.format(m.group(1)))
            m = re.search(r'\b(OK|FAILED)\s*[\(\s]', content)
            if m and not any(m.group(1) in part for part in parts):
                parts.append(m.group(1))
            m = re.search(r'failures?\s*=\s*(\d+)', content, re.IGNORECASE)
            if m:
                parts.append('failures={}'.format(m.group(1)))
        except Exception:
            pass
    # Fallback: tobiko-related logs (under tobiko/, tobiko*build*.log)
    if not parts and tobiko_related_paths:
        for p in tobiko_related_paths:
            if not p.lower().endswith('.log') or not os.path.isfile(p):
                continue
            try:
                with open(p, 'r', errors='ignore') as f:
                    content = f.read(100000)
                if not content.strip():
                    continue
                if 'Ran ' not in ' '.join(parts):
                    m = re.search(r'Ran\s+(\d+)\s+test', content, re.IGNORECASE)
                    if m:
                        parts.append('Ran {} tests'.format(m.group(1)))
                m = re.search(r'\b(OK|FAILED)\s*[\(\s]', content)
                if m and not any(m.group(1) in part for part in parts):
                    parts.append(m.group(1))
                m = re.search(r'failures?\s*=\s*(\d+)', content, re.IGNORECASE)
                if m:
                    parts.append('failures={}'.format(m.group(1)))
                if parts:
                    rel = os.path.relpath(p, job_dir) if p.startswith(rel_prefix) else p
                    parts.append('(from {})'.format(rel))
                    break
            except Exception:
                continue
    if parts:
        return '; '.join(parts)
    # Fallback: scan console log (job-output.txt) for tobiko pass/fail hints
    console_path = os.path.join(job_dir, CONSOLE_LOG)
    _, tobiko_hint = _console_tempest_tobiko_hints(console_path)
    if tobiko_hint:
        return tobiko_hint
    if tobiko_related_paths:
        rels = [os.path.relpath(p, job_dir) if p.startswith(rel_prefix) else p for p in tobiko_related_paths[:10]]
        return 'No summary in Tobiko result files; Tobiko-related files found: ' + ', '.join(rels)
    return 'No Tobiko result files found (looked for tobiko_results.html, .xml under job dir)'


def main():
    main_start = time_module.time()
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/5] Zuul job: URL or local path'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Enter Zuul job URL (base URL is fine; we add /logs if needed) or path to existing job dir:'))
    print(common.c(_DIM, '  URL example: https://.../zuul/t/tenant/build/<uuid>'))
    try:
        path_in = input(common.c(_DIM, 'URL or path: ')).strip()
    except EOFError:
        print(common.c(_YELLOW, 'No input. Exiting.'))
        sys.exit(1)
    if not path_in:
        print(common.c(_YELLOW, 'Empty input. Exiting.'))
        sys.exit(1)

    if path_in.startswith('http://') or path_in.startswith('https://'):
        print(common.c(_DIM, 'Downloading from URL...'), flush=True)
        from zuul_logs_download import run_zuul_download
        path = run_zuul_download(path_in)
        print(common.c(_GREEN, 'Download complete.'), flush=True)
    else:
        path = os.path.abspath(os.path.expanduser(path_in))
        if not os.path.isdir(path):
            print(common.c(_YELLOW, 'Not a directory or not found: ') + path)
            sys.exit(1)
        print(common.c(_DIM, 'Using path: ') + path, flush=True)

    print(common.c(_DIM, 'Discovering job dirs (job-output.txt)...'), flush=True)
    job_dirs = discover_zuul_job_dirs(path)
    if not job_dirs:
        print(common.c(_YELLOW, 'No Zuul job directory found (expected job-output.txt in path or subdirs).'))
        print(common.c(_DIM, 'If you used a URL, the page may have had no downloadable links (login required or JS-only content).'))
        sys.exit(1)
    if len(job_dirs) == 1:
        selected_jobs = job_dirs
        print(common.c(_GREEN, 'Single job dir: ') + common.c(_CYAN, selected_jobs[0]))
    else:
        print(common.c(_GREEN, 'Found {} job dirs.').format(len(job_dirs)))
        for i, j in enumerate(job_dirs, 1):
            print('  {}) {}'.format(i, os.path.basename(j)))
        print('  {}) All'.format(len(job_dirs) + 1))
        try:
            choice = input(common.c(_DIM, 'Choice [1-{}]: ').format(len(job_dirs) + 1)).strip()
            idx = int(choice)
        except (ValueError, EOFError):
            idx = len(job_dirs) + 1
        if 1 <= idx <= len(job_dirs):
            selected_jobs = [job_dirs[idx - 1]]
        else:
            selected_jobs = job_dirs

    print('')
    print(common.c(_CYAN, '[2/5] Walk job dirs: console + tempest + tobiko + all logs'))
    print(common.c(_DIM, '-' * 60))
    all_log_paths = []
    job_info = []
    for ji, job_dir in enumerate(selected_jobs):
        if len(selected_jobs) > 1:
            print(common.c(_DIM, '  Job {}/{}: {}').format(ji + 1, len(selected_jobs), job_dir), flush=True)
        job_id = os.path.basename(job_dir.rstrip(os.sep))
        console_result, console_detail = get_console_result(job_dir)
        log_paths, tempest_paths, tempest_related_paths, tobiko_paths, tobiko_related_paths = discover_all_log_and_tempest_files(job_dir)
        tempest_summary = get_tempest_summary(job_dir, tempest_paths, tempest_related_paths)
        tobiko_summary = get_tobiko_summary(job_dir, tobiko_paths, tobiko_related_paths)
        tempest_details = get_tempest_details(job_dir, tempest_paths)
        tobiko_details = get_tobiko_details(job_dir, tobiko_paths)
        since_dt, since_reason = get_console_since_dt(job_dir)
        all_log_paths.extend(log_paths)
        job_info.append({
            'dir': job_dir,
            'id': job_id,
            'console_result': console_result,
            'console_detail': console_detail,
            'tempest_summary': tempest_summary,
            'tempest_details': tempest_details,
            'tempest_paths': tempest_paths,
            'tempest_related_paths': tempest_related_paths,
            'tobiko_summary': tobiko_summary,
            'tobiko_details': tobiko_details,
            'tobiko_paths': tobiko_paths,
            'tobiko_related_paths': tobiko_related_paths,
            'log_paths': log_paths,
            'since_dt': since_dt,
            'since_reason': since_reason,
        })
        t_sum = tempest_summary[:40] + '...' if len(tempest_summary) > 40 else tempest_summary
        b_sum = tobiko_summary[:40] + '...' if len(tobiko_summary) > 40 else tobiko_summary
        print(common.c(_DIM, '  {}: console={}, tempest={}, tobiko={}, {} log(s)').format(
            job_id[:16] + '...' if len(job_id) > 16 else job_id,
            console_result,
            t_sum,
            b_sum,
            len(log_paths),
        ))
    n_tempest_detail = sum(len(info.get('tempest_details') or []) for info in job_info)
    n_tobiko_detail = sum(len(info.get('tobiko_details') or []) for info in job_info)
    if n_tempest_detail or n_tobiko_detail:
        print(common.c(_DIM, '  Test details: {} tempest test(s), {} tobiko test(s) (see report).').format(n_tempest_detail, n_tobiko_detail), flush=True)
    for info in job_info:
        reason = info.get('since_reason') or 'full logs'
        print(common.c(_DIM, '  Time window ({}): {}').format(info['id'][:12] + ('...' if len(info['id']) > 12 else ''), reason), flush=True)
    if not all_log_paths:
        print(common.c(_YELLOW, 'No log files to grep. Writing report with console/tempest only.'))

    print('')
    print(common.c(_CYAN, '[3/5] Extract error blocks (grep, threaded)'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, '  Creating keywords file...'), flush=True)
    keywords_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    try:
        for kw in config.ERROR_KEYWORDS:
            keywords_file.write(kw.strip() + '\n')
        keywords_file.close()
        keywords_path = keywords_file.name
    except Exception:
        print(common.c(_YELLOW, 'Could not create keywords file.'))
        sys.exit(1)
    def _since_dt_for_path(path, job_info_list):
        for info in job_info_list:
            d = info['dir']
            if path == d or path.startswith(d + os.sep):
                return info.get('since_dt')
        return None

    n_files = len(all_log_paths)
    n_workers = min(config.MAX_WORKERS, n_files)
    print(common.c(_DIM, '  Scanning {} log file(s) with {} workers...').format(n_files, n_workers or 1), flush=True)
    path_blocks = {}
    done = 0
    ext_lock = threading.Lock()
    start_ext = time_module.time()

    def _extract_one(args):
        p, kw_path, since = args
        return (p, common.extract_blocks_grep(p, kw_path, since_dt=since))

    with ThreadPoolExecutor(max_workers=n_workers or 1) as ex:
        futures = {
            ex.submit(_extract_one, (p, keywords_path, _since_dt_for_path(p, job_info))): p
            for p in all_log_paths
        }
        for fut in as_completed(futures):
            with ext_lock:
                done += 1
                if done % 20 == 0 or done == n_files:
                    print(common.c(_DIM, '  [grep] {}/{} files...').format(done, n_files), flush=True)
            try:
                p, blocks = fut.result()
                path_blocks[p] = blocks
            except Exception:
                pass
    try:
        os.unlink(keywords_path)
    except Exception:
        pass
    print(common.c(_GREEN, '  Scanned {} files in {:.1f}s ({} workers).').format(n_files, time_module.time() - start_ext, n_workers))

    # Deduplicate blocks by signature (can be slow with many blocks; show progress)
    report_entries = []
    sorted_paths = sorted(path_blocks.keys())
    n_paths = len(sorted_paths)
    total_blocks = sum(len(path_blocks[p]) for p in sorted_paths)
    print(common.c(_DIM, '  Deduplicating {} blocks from {} paths...').format(total_blocks, n_paths), flush=True)
    start_dedup = time_module.time()
    PROGRESS_INTERVAL = 50
    BLOCK_PROGRESS_INTERVAL = 100  # print every N blocks within a path (so big paths don't look stuck)
    blocks_done = 0
    for pi, path in enumerate(sorted_paths):
        if (pi + 1) % PROGRESS_INTERVAL == 0 or pi + 1 == n_paths:
            print(common.c(_DIM, '  [dedup] {}/{} paths ({} blocks so far)...').format(pi + 1, n_paths, blocks_done), flush=True)
        blocks = path_blocks[path]
        seen_sigs = []
        for bi, (lines_with_nums, block_text, _block_dt) in enumerate(blocks):
            if BLOCK_PROGRESS_INTERVAL and (bi + 1) % BLOCK_PROGRESS_INTERVAL == 0:
                print(common.c(_DIM, '  [dedup] path {}/{}: {} blocks...').format(pi + 1, n_paths, bi + 1), flush=True)
            sig = common.block_signature(block_text)
            found = any(common.similar(sig, s) >= config.FUZZY_MATCH_RATIO for s in seen_sigs)
            if found:
                blocks_done += 1
                continue
            count = sum(1 for (_l, bt, _d) in blocks if common.similar(common.block_signature(bt), sig) >= config.FUZZY_MATCH_RATIO)
            seen_sigs.append(sig)
            report_entries.append((path, lines_with_nums, block_text, sig, count))
            blocks_done += 1
    print(common.c(_DIM, '  Dedup done in {:.1f}s, {} unique block(s).').format(time_module.time() - start_dedup, len(report_entries)), flush=True)

    n_blocks = len(report_entries)
    use_ollama = False
    print('')
    print(common.c(_CYAN, '[4/5] Optional Ollama filter'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, '  Found {} unique error block(s).').format(n_blocks), flush=True)
    if n_blocks > 0 and config.OLLAMA_HOST and common.ollama_reachable():
        try:
            sys.stdout.flush()
            choice = input(common.c(_DIM, '  Use Ollama to filter blocks (real error vs not)? [y/N]: ')).strip().lower()
        except EOFError:
            choice = 'n'
        if choice in ('y', 'yes'):
            use_ollama = True
        else:
            print(common.c(_DIM, '  Skipping Ollama — all blocks will be included in report.'))
    elif n_blocks == 0:
        print(common.c(_DIM, '  No blocks to filter.'))
    else:
        print(common.c(_DIM, '  Ollama not configured or unreachable.'))

    ai_cache = {}
    if use_ollama and report_entries:
        resolved_model = (config.OLLAMA_MODEL or '').strip()
        if not resolved_model:
            if sys.stdin.isatty():
                resolved_model = common.ollama_choose_model_interactive(config.OLLAMA_HOST)
            else:
                resolved_model = common.ollama_pick_best_model(config.OLLAMA_HOST)
        if resolved_model == common.OLLAMA_SKIP:
            print(common.c(_DIM, '  Skipping Ollama — all blocks will be included in report.'), flush=True)
        elif resolved_model:
            unique_sigs = {}
            for (path, lines_with_nums, block_text, sig, count) in report_entries:
                if sig not in unique_sigs:
                    unique_sigs[sig] = block_text
            ai_cache = {}
            n_unique = len(unique_sigs)
            n_workers_ollama = min(config.OLLAMA_MAX_CONCURRENT, n_unique)
            print(common.c(_DIM, '  Classifying {} unique blocks (Ollama)...').format(n_unique), flush=True)
            done_count = [0]
            lock = threading.Lock()
            def _classify(args):
                s, text, model = args
                keep, expl = common.ollama_classify_and_explain(text, model=model)
                return (s, keep, expl)
            with ThreadPoolExecutor(max_workers=n_workers_ollama or 1) as ex:
                futures = [ex.submit(_classify, (sig, unique_sigs[sig], resolved_model)) for sig in unique_sigs]
                for fut in as_completed(futures):
                    try:
                        sig, keep, expl = fut.result()
                        ai_cache[sig] = (keep, expl)
                        with lock:
                            done_count[0] += 1
                            if done_count[0] % 5 == 0 or done_count[0] == n_unique:
                                print(common.c(_DIM, '  [{}]/{}').format(done_count[0], n_unique), flush=True)
                    except Exception:
                        pass
            for i, entry in enumerate(report_entries):
                keep, _ = ai_cache.get(entry[3], (True, None))
                if not keep:
                    report_entries[i] = None
            report_entries = [e for e in report_entries if e is not None]
            print(common.c(_DIM, '  Ollama filter done.'), flush=True)

    print('')
    print(common.c(_CYAN, '[5/5] Write report'))
    print(common.c(_DIM, '-' * 60))
    report_path = getattr(config, 'ZUUL_JOB_REPORT_FILE', os.path.join(config.BASE_DIR, 'zuul_job_analysis_report.txt'))
    print(common.c(_DIM, '  Writing text report: ') + report_path, flush=True)
    with open(report_path, 'w') as f:
        f.write(common.r(common.REPORT_BOLD, 'Zuul job analysis report') + '\n')
        f.write(common.r(common.REPORT_DIM, 'Source path: ') + path + '\n')
        f.write(common.r(common.REPORT_DIM, 'AI filter: ') + ('on' if use_ollama else 'off') + '\n\n')
        for info in job_info:
            f.write(common.r(common.REPORT_CYAN, '=' * 60) + '\n')
            f.write(common.r(common.REPORT_BOLD, 'Job: ') + info['id'] + '\n')
            f.write(common.r(common.REPORT_DIM, '  Directory: ') + info['dir'] + '\n')
            f.write(common.r(common.REPORT_DIM, '  Console result: ') + info['console_result'] + ' — ' + info['console_detail'] + '\n')
            f.write(common.r(common.REPORT_DIM, '  Tempest summary: ') + info['tempest_summary'] + '\n')
            if info.get('tempest_paths'):
                rels = [os.path.relpath(p, info['dir']) for p in info['tempest_paths'].values()]
                f.write(common.r(common.REPORT_DIM, '  Tempest result files: ') + ', '.join(rels) + '\n')
            details = info.get('tempest_details') or []
            if details:
                f.write(common.r(common.REPORT_BOLD, '  Tempest tests (details):') + '\n')
                for t in details:
                    st = t['status'].upper()
                    if st == 'PASS':
                        f.write('    PASS  ' + t['name'] + '\n')
                    elif st == 'FAIL':
                        f.write('    FAIL  ' + t['name'] + '\n')
                    elif st == 'ERROR':
                        f.write('    ERROR ' + t['name'] + '\n')
                    else:
                        f.write('    SKIP  ' + t['name'] + '\n')
            if info.get('tempest_related_paths'):
                rels = [os.path.relpath(p, info['dir']) for p in info['tempest_related_paths']]
                f.write(common.r(common.REPORT_DIM, '  Tempest-related files (build logs): ') + ', '.join(rels) + '\n')
            f.write(common.r(common.REPORT_DIM, '  Tobiko summary: ') + info['tobiko_summary'] + '\n')
            if info.get('tobiko_paths'):
                rels = [os.path.relpath(p, info['dir']) for p in info['tobiko_paths'].values()]
                f.write(common.r(common.REPORT_DIM, '  Tobiko result files: ') + ', '.join(rels) + '\n')
            details = info.get('tobiko_details') or []
            if details:
                f.write(common.r(common.REPORT_BOLD, '  Tobiko tests (details):') + '\n')
                for t in details:
                    st = t['status'].upper()
                    if st == 'PASS':
                        f.write('    PASS  ' + t['name'] + '\n')
                    elif st == 'FAIL':
                        f.write('    FAIL  ' + t['name'] + '\n')
                    elif st == 'ERROR':
                        f.write('    ERROR ' + t['name'] + '\n')
                    else:
                        f.write('    SKIP  ' + t['name'] + '\n')
            if info.get('tobiko_related_paths'):
                rels = [os.path.relpath(p, info['dir']) for p in info['tobiko_related_paths']]
                f.write(common.r(common.REPORT_DIM, '  Tobiko-related files (build logs): ') + ', '.join(rels) + '\n')
            f.write(common.r(common.REPORT_CYAN, '=' * 60) + '\n\n')
        f.write(common.r(common.REPORT_BOLD, 'Error blocks (from all logs in job dir and subdirs):') + '\n\n')
        for path in sorted(set(e[0] for e in report_entries)):
            f.write(common.r(common.REPORT_CYAN, '--- ') + path + ' ---\n\n')
            for (p, lines_with_nums, block_text, sig, count) in report_entries:
                if p != path:
                    continue
                f.write(common.r(common.REPORT_YELLOW, '  (occurred {} time{})').format(count, 's' if count != 1 else '') + '\n')
                for line_no, line_text in lines_with_nums[:config.MAX_BLOCK_LINES_SHOWN]:
                    display = _line_for_display(line_text)
                    for i, part in enumerate(display.splitlines()):
                        prefix = '  {}: '.format(line_no) if i == 0 else '       '
                        f.write(prefix + common.highlight_error_keywords(part) + '\n')
                if len(lines_with_nums) > config.MAX_BLOCK_LINES_SHOWN:
                    f.write('  ... ({} more lines)\n'.format(len(lines_with_nums) - config.MAX_BLOCK_LINES_SHOWN))
                if use_ollama and sig in ai_cache:
                    _, expl = ai_cache[sig]
                    if expl and expl.strip():
                        f.write(common.r(common.REPORT_DIM, '  --- Ollama ---') + '\n')
                        f.write(common.wrap_for_report(expl) + '\n')
                f.write('\n')
        if not report_entries:
            f.write(common.r(common.REPORT_DIM, '(No error blocks to report.)') + '\n')

    html_path = getattr(config, 'ZUUL_JOB_REPORT_HTML', os.path.join(config.BASE_DIR, 'zuul_job_analysis_report.html'))
    print(common.c(_DIM, '  Writing HTML report: ') + html_path, flush=True)
    report_logs_dir = os.path.join(os.path.dirname(html_path), REPORT_LOGS_SUBDIR)
    main_basename = os.path.basename(html_path)
    viewer_links = {}
    if report_entries:
        os.makedirs(report_logs_dir, exist_ok=True)
        viewer_ranges = common.compute_viewer_line_ranges(report_entries)
        used_viewer = set()
        for p in viewer_ranges:
            viewer_links[p] = 'view_' + _safe_log_filename(p, used_viewer)
        for p in viewer_links:
            out_path = os.path.join(report_logs_dir, viewer_links[p])
            common.build_log_viewer_file(p, viewer_ranges[p], out_path, back_link_url='../' + main_basename, back_link_text='Back to main report')
    html_content = _build_html_report(path, job_info, report_entries, use_ollama, report_logs_dir=report_logs_dir, main_report_basename=main_basename, ai_cache=ai_cache, viewer_links=viewer_links)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(common.c(_DIM, '  Done (main report + {} per-log links).').format(len(report_entries) and len(set(e[0] for e in report_entries)) or 0), flush=True)

    elapsed = time_module.time() - main_start
    print(common.c(_GREEN, 'Report written to: ') + common.c(_CYAN, report_path))
    print(common.c(_GREEN, 'HTML report: ') + common.c(_CYAN, html_path))
    print(common.c(_GREEN, 'Jobs analyzed: {}; error blocks: {}.').format(len(job_info), len(report_entries)))
    print(common.c(_DIM, 'Time: {:.1f}s').format(elapsed))
    common.print_download_prompt(html_path, report_path, report_logs_dir=report_logs_dir)


if __name__ == '__main__':
    main()
