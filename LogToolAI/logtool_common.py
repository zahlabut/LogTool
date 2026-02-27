# Shared functions and helpers for LogToolAI modes.
# Import this module and use its functions; it reads config.py for parameters.

import re
import sys
import os
import json
import shlex
import socket
import gzip
import hashlib
import zipfile
import linecache
import datetime
import difflib
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from string import digits
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

# --- Display (from config) ---
_USE_COLOR = sys.stdout.isatty() and not config.NO_COLOR
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
_REPORT_ERROR_HL = '\033[1;31m'
_TRACEBACK_START = 'traceback'
_HL_KEYWORDS_LOWER = [k.strip().lower() for k in config.ERROR_KEYWORDS if k.strip()]
_HL_KEYWORDS_LOWER.sort(key=len, reverse=True)
_ollama_debug_lock = threading.Lock()
_ollama_404_hint_printed = [False]


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
        # Space-separated date + time (e.g. Zuul console "2026-02-24 21:09:15.023346 |")
        m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})(?:\.(\d+))?\s', line)
        if m:
            base = m.group(1) + ' ' + m.group(2)
            dt = datetime.datetime.strptime(base, '%Y-%m-%d %H:%M:%S')
            if m.group(3):
                us = int((m.group(3) + '000000')[:6])
                dt = dt.replace(microsecond=us)
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


def remove_digits(s):
    return str(s).translate(str.maketrans('', '', digits))


def similar(a, b):
    return difflib.SequenceMatcher(None, remove_digits(a), remove_digits(b)).ratio()


def _normalize_signature_text(s):
    s = re.sub(r'\bstream\s+[A-Za-z0-9_.-]+', 'stream __', s, flags=re.IGNORECASE)
    s = re.sub(r'\bimagestream\s+[A-Za-z0-9_.-]+', 'imagestream __', s, flags=re.IGNORECASE)
    # Collapse package-like tokens (e.g. perl-Error, perl-Encode, rhosp-rhel-9.4-appstream) so
    # DNF/yum install blocks that only differ by package name merge into one (avoid duplicate blocks).
    s = re.sub(r'\b[a-zA-Z][a-zA-Z0-9_.]*-[a-zA-Z0-9_.-]+\b', '__', s)
    # Normalize DNF/yum operation words so "Installing", "Verifying", "Downloading" blocks merge
    s = re.sub(r'\b(?:Installing|Verifying|Downloading)\b', '_DnfOp_', s, flags=re.IGNORECASE)
    return s


def block_signature(block_text):
    s = remove_digits(block_text)
    s = _normalize_signature_text(s)
    return s[:config.SIGNATURE_LEN] if len(s) > config.SIGNATURE_LEN else s


def c(style, msg):
    if _USE_COLOR and style:
        return style + msg + _RESET
    return msg


def r(style, s):
    return style + s + _REPORT_RESET


def highlight_error_keywords(line_text):
    if not line_text or not _HL_KEYWORDS_LOWER:
        return line_text
    line_lower = line_text.lower()
    spans = []
    for kw in _HL_KEYWORDS_LOWER:
        if not kw:
            continue
        start = 0
        while True:
            i = line_lower.find(kw, start)
            if i == -1:
                break
            spans.append((i, i + len(kw)))
            start = i + 1
    if not spans:
        return line_text
    spans.sort(key=lambda x: x[0])
    merged = [spans[0]]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out = []
    pos = 0
    for a, b in merged:
        out.append(line_text[pos:a])
        out.append(_REPORT_ERROR_HL + line_text[a:b] + _REPORT_RESET)
        pos = b
    out.append(line_text[pos:])
    return ''.join(out)


def wrap_for_report(text, width=76, first_indent='  ', wrap_indent='    '):
    if not text or not text.strip():
        return ''
    text = re.sub(r'\s+', ' ', text.strip())
    if len(text) <= width:
        return first_indent + text
    lines = []
    current = first_indent
    for word in text.split():
        next_bit = (' ' + word) if current.strip() else word
        if len(current) + len(next_bit) <= width:
            current += next_bit
        else:
            lines.append(current)
            current = wrap_indent + word
    if current.strip():
        lines.append(current)
    return '\n'.join(lines)


def escape_ansi(line):
    return re.sub(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]', '', line)


def trim_to_first_error(lines_with_nums):
    if not lines_with_nums:
        return lines_with_nums
    keywords_lower = [k.strip().lower() for k in config.ERROR_KEYWORDS if k.strip()]
    for i, (_, line_text) in enumerate(lines_with_nums):
        low = line_text.lower()
        if any(kw in low for kw in keywords_lower):
            return lines_with_nums[i:]
    return lines_with_nums


def split_into_traceback_chunks(lines_with_nums):
    if not lines_with_nums:
        return []
    chunks = []
    current = []
    for line_no, line_text in lines_with_nums:
        if _TRACEBACK_START in line_text.rstrip('\n').lower():
            if current:
                chunks.append(current)
            current = [(line_no, line_text)]
        else:
            current.append((line_no, line_text))
    if current:
        chunks.append(current)
    return chunks if chunks else [lines_with_nums]


def one_representative_block(lines_with_nums):
    trimmed = trim_to_first_error(lines_with_nums)
    if not trimmed:
        return lines_with_nums
    chunks = split_into_traceback_chunks(trimmed)
    if len(chunks) <= 1:
        return trimmed
    intro = chunks[0] if chunks else []
    traceback_chunks = chunks[1:] if len(chunks) > 1 else []
    if not traceback_chunks:
        return trimmed
    unique_tbs = []
    for ch in traceback_chunks:
        ch_text = ''.join(lt for _, lt in ch)
        ch_sig = block_signature(ch_text)
        found = False
        for rep_sig, _ in unique_tbs:
            if similar(rep_sig, ch_sig) >= config.FUZZY_MATCH_RATIO:
                found = True
                break
        if not found:
            unique_tbs.append((ch_sig, ch))
    first_tb = unique_tbs[0][1] if unique_tbs else []
    if intro and not any(_TRACEBACK_START in lt.lower() for _, lt in intro):
        return intro + first_tb
    return first_tb if first_tb else trimmed


def print_menu_columns(items, num_columns=3, cell_width=38):
    max_label_len = cell_width - 7
    for start in range(0, len(items), num_columns):
        row = items[start:start + num_columns]
        cells = []
        for idx, label in row:
            if len(label) > max_label_len:
                label = label[: max_label_len - 3] + '...'
            cells.append('  {}) {}'.format(idx, label))
        line = ''.join(c.ljust(cell_width) for c in cells)
        print(line.rstrip())


# --- Ollama ---
# Sentinel returned by ollama_choose_model_interactive when user chooses "Skip Ollama"
OLLAMA_SKIP = '_skip_ollama'


def ollama_classify_and_explain(block_text, model=None):
    model = model or config.OLLAMA_MODEL
    snippet = (block_text or '')[:config.AI_MAX_BLOCK_CHARS]
    if len(block_text or '') > config.AI_MAX_BLOCK_CHARS:
        snippet += '\n... [truncated]'
    prompt = (
        'Reply with exactly YES or NO on the first line. If YES, write 2-4 short sentences on the following lines explaining: what this error means, common causes, impact, and what to check when fixing it. If NO, write nothing else.\n'
        'Format:\nYES\n<your explanation here, 2-4 sentences>\nor\nNO\n\nLog block:\n' + snippet
    )
    try:
        url = config.OLLAMA_HOST.rstrip('/') + '/api/generate'
        payload = {'model': model, 'prompt': prompt, 'stream': False, 'options': {'num_predict': config.OLLAMA_MAX_PREDICT}}
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        reply = (data.get('response') or '').strip()
        reply_upper = reply.upper()
        if 'NO' in reply_upper and 'YES' not in reply_upper:
            if config.OLLAMA_DEBUG:
                with _ollama_debug_lock:
                    print(c(_DIM, '[Ollama debug] classify reply (NO): ') + repr(reply[:400]) + ('...' if len(reply) > 400 else ''), flush=True)
            return (False, None)
        lines = [l.strip() for l in reply.splitlines() if l.strip()]
        explanation = None
        for i, line in enumerate(lines):
            u = line.upper()
            if u.startswith('YES'):
                rest = line[3:].strip().lstrip('.-:,)').strip()
                parts = [rest] if rest else []
                for j in range(i + 1, len(lines)):
                    if lines[j].upper().startswith('NO'):
                        break
                    if lines[j].strip():
                        parts.append(lines[j].strip())
                explanation = ' '.join(parts).strip() if parts else None
                break
        if not explanation and reply_upper.startswith('YES'):
            rest = reply[3:].strip().lstrip('.-:,)').strip()
            if rest:
                explanation = rest
        if not explanation and 'YES' in reply_upper:
            pos = reply_upper.find('YES')
            after = reply[pos + 3:].strip().lstrip('.-)\n\t ').strip()
            if len(after) > 10:
                explanation = after
        if explanation and len(explanation) > config.AI_MAX_EXPLANATION_CHARS:
            explanation = explanation[: config.AI_MAX_EXPLANATION_CHARS - 3] + '...'
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_DIM, '[Ollama debug] classify reply (YES): ') + repr(reply[:500]) + ('...' if len(reply) > 500 else ''), flush=True)
                print(c(_DIM, '[Ollama debug] parsed explanation: ') + repr(explanation[:300] if explanation else None), flush=True)
        return (True, explanation if explanation else None)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError) as e:
        if isinstance(e, urllib.error.HTTPError) and e.code == 404:
            maybe_print_ollama_404_hint(model=model)
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_YELLOW, '[Ollama debug] classify exception: ') + str(e), flush=True)
        return (True, None)


def ollama_reachable(host=None, timeout=None):
    url = (host or config.OLLAMA_HOST).rstrip('/') + '/api/version'
    t = timeout if timeout is not None else config.OLLAMA_CHECK_TIMEOUT
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=t) as resp:
            return resp.getcode() == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def ollama_fetch_models(host=None):
    base = (host or config.OLLAMA_HOST).rstrip('/')
    url = base + '/api/tags'
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=config.OLLAMA_CHECK_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        models = data.get('models') or []
        if not models:
            return []
        def sort_key(m):
            size = m.get('size') or 0
            param = 0
            details = m.get('details') or {}
            ps = details.get('parameter_size') or ''
            if ps:
                match = re.match(r'([\d.]+)\s*B', ps, re.I)
                if match:
                    param = float(match.group(1))
            return (-size, -param)
        models.sort(key=sort_key)
        out = []
        for m in models:
            size = m.get('size') or 0
            details = m.get('details') or {}
            param_size = details.get('parameter_size') or ''
            name = m.get('name') or m.get('model') or ''
            if not name:
                continue
            out.append({'name': name, 'size': size, 'size_gb': round(size / (1024 ** 3), 1), 'parameter_size': param_size})
        return out
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError):
        return []


def ollama_pick_best_model(host=None):
    """Return the smallest (fastest) model on the server. None if none available."""
    models = ollama_fetch_models(host)
    return models[-1]['name'] if models else None


def ollama_choose_model_interactive(host=None):
    models = ollama_fetch_models(host)
    if not models:
        return None
    print(c(_CYAN, 'Models on Ollama server:'), flush=True)
    print(c(_DIM, '  Smaller models are faster; larger models may be more accurate but slower.'), flush=True)
    print(c(_DIM, '  Large models (e.g. 70B) may need a higher OLLAMA_TIMEOUT in config (current: {}s).').format(config.OLLAMA_TIMEOUT), flush=True)
    print('', flush=True)
    for i, m in enumerate(models, 1):
        extra = ', {}'.format(m['parameter_size']) if m['parameter_size'] else ''
        print('  {}) {}  ({:.1f} GB{})'.format(i, m['name'], m['size_gb'], extra), flush=True)
    print('  0) Auto (use smallest/fastest: {})'.format(models[-1]['name']), flush=True)
    print('  s) Skip Ollama (include all blocks in report, no AI filter)', flush=True)
    print('', flush=True)
    while True:
        try:
            choice = input(c(_DIM, 'Choice [0-{} or s] (default 0): ').format(len(models))).strip().lower() or '0'
            if choice == 's':
                return OLLAMA_SKIP
            if choice == '0':
                return models[-1]['name']
            idx = int(choice)
            if 1 <= idx <= len(models):
                return models[idx - 1]['name']
        except (ValueError, EOFError):
            pass
        print(c(_YELLOW, '  Invalid choice. Enter 0 for auto, s to skip Ollama, or a number from the list.'), flush=True)


def maybe_print_ollama_404_hint(model=None):
    with _ollama_debug_lock:
        if _ollama_404_hint_printed[0]:
            return
        _ollama_404_hint_printed[0] = True
        name = (model or config.OLLAMA_MODEL or 'model')
        print(c(_YELLOW, '[Ollama] HTTP 404: the model may not be installed on the server. On the Ollama host run:  ollama list   and  ollama pull ') + name, flush=True)


def ollama_detailed_explanation(block_text, model=None):
    model = model or config.OLLAMA_MODEL
    snippet = (block_text or '')[:config.AI_MAX_BLOCK_CHARS]
    prompt = (
        'This log block is a real error. Write 2-5 short sentences for someone debugging. Include: (1) what the error means, (2) common causes, (3) impact, (4) what to check when fixing. Start your reply immediately with the first sentence of the explanation. No preamble, no "Explanation:" or "The error is".\n\nLog block:\n' + snippet
    )
    try:
        url = config.OLLAMA_HOST.rstrip('/') + '/api/generate'
        payload = {'model': model, 'prompt': prompt, 'stream': False, 'options': {'num_predict': config.OLLAMA_MAX_PREDICT_DETAILED}}
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        reply_raw = (data.get('response') or '').strip()
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_DIM, '[Ollama debug] detailed raw reply: ') + repr(reply_raw[:600]) + ('...' if len(reply_raw) > 600 else ''), flush=True)
        reply = re.sub(r'\n+', ' ', reply_raw).strip()
        for prefix in ('Explanation:', 'The error', 'This error', 'This is', 'Here is', 'In this'):
            if reply.upper().startswith(prefix.upper()):
                reply = reply[len(prefix):].strip().lstrip('.:- ')
                break
        if reply and len(reply) > config.AI_MAX_EXPLANATION_CHARS:
            reply = reply[: config.AI_MAX_EXPLANATION_CHARS - 3] + '...'
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_DIM, '[Ollama debug] detailed after parse: ') + repr(reply[:300] if reply else None), flush=True)
        return reply if reply and len(reply) > 15 else None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError) as e:
        if isinstance(e, urllib.error.HTTPError) and e.code == 404:
            maybe_print_ollama_404_hint(model=model)
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_YELLOW, '[Ollama debug] detailed exception: ') + str(e), flush=True)
        return None


def ollama_custom_prompt(prompt, model=None, max_predict=None):
    """Send a custom prompt to Ollama /api/generate; return the response text or None on failure."""
    model = (model or config.OLLAMA_MODEL or '').strip()
    if not model:
        return None
    num_predict = max_predict if max_predict is not None else getattr(config, 'EXTRACT_OLLAMA_MAX_PREDICT', 1024)
    try:
        url = config.OLLAMA_HOST.rstrip('/') + '/api/generate'
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'num_predict': num_predict},
        }
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return (data.get('response') or '').strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError) as e:
        if isinstance(e, urllib.error.HTTPError) and e.code == 404:
            maybe_print_ollama_404_hint(model=model)
        if config.OLLAMA_DEBUG:
            with _ollama_debug_lock:
                print(c(_YELLOW, '[Ollama debug] custom prompt exception: ') + str(e), flush=True)
        return None


# --- Baseline from log files (for must-gather and local-dir modes) ---
BASELINE_MAX_FILES = 100
BASELINE_TAIL_LINES = 50
BASELINE_TAIL_BYTES = 100 * 1024


def _latest_date_in_file(path):
    """Return the latest datetime found in the last BASELINE_TAIL_LINES of path, or None."""
    try:
        size = os.path.getsize(path)
        with open(path, 'r', errors='ignore') as f:
            if size > BASELINE_TAIL_BYTES:
                f.seek(max(0, size - BASELINE_TAIL_BYTES))
                f.readline()  # skip partial line at seek position
            lines = f.readlines()
        tail = lines[-BASELINE_TAIL_LINES:] if len(lines) > BASELINE_TAIL_LINES else lines
        latest = None
        for line in tail:
            dt, _ = get_line_date(line)
            if dt and (latest is None or dt > latest):
                latest = dt
        return latest
    except Exception:
        return None


def get_baseline_from_log_files(log_paths):
    """Return the latest timestamp found in the selected log files. Uses threading. Prints progress."""
    paths = log_paths if len(log_paths) <= BASELINE_MAX_FILES else log_paths[:BASELINE_MAX_FILES]
    n = len(paths)
    n_workers = min(config.MAX_WORKERS, n)
    if len(log_paths) > BASELINE_MAX_FILES:
        print(c('\033[33m', '  [baseline]') + ' Sampling {} of {} files for latest timestamp ({} workers)...'.format(
            BASELINE_MAX_FILES, len(log_paths), n_workers))
    else:
        print(c('\033[33m', '  [baseline]') + ' Scanning {} files ({} workers)...'.format(n, n_workers), flush=True)
    latest = None
    done = 0
    lock = threading.Lock()
    start = datetime.datetime.utcnow()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_latest_date_in_file, path): path for path in paths}
        for fut in as_completed(futures):
            with lock:
                done += 1
                if done % 20 == 0 or done == n:
                    print(c('\033[33m', '  [baseline]') + ' {}/{} files checked...'.format(done, n), flush=True)
            try:
                dt = fut.result()
                if dt and (latest is None or dt > latest):
                    latest = dt
            except Exception:
                pass
    elapsed = (datetime.datetime.utcnow() - start).total_seconds()
    ts_str = latest.strftime('%Y-%m-%d %H:%M:%S') if latest else 'none'
    print(c('\033[32m', '  [baseline] Done in {:.1f}s. Latest: {}').format(elapsed, ts_str))
    return latest


# --- Block extraction (grep) ---
GREP_GROUP_SEP = '---BLOCK---'


def extract_blocks_grep(path, keywords_file, since_dt):
    cmd = "grep -F -i -n -B{} -A{} -f {} --group-separator={} {} 2>/dev/null".format(
        config.CONTEXT_BEFORE, config.CONTEXT_AFTER,
        shlex.quote(keywords_file), shlex.quote(GREP_GROUP_SEP), shlex.quote(path)
    )
    ok, out = run(cmd)
    if not ok or not out.strip():
        return []
    blocks = []
    for raw_block in out.split(GREP_GROUP_SEP):
        raw_block = raw_block.strip()
        if not raw_block:
            continue
        lines_with_nums = []
        for raw_line in raw_block.splitlines():
            if ':' not in raw_line:
                continue
            num_str, content = raw_line.split(':', 1)
            try:
                line_no = int(num_str.strip())
            except ValueError:
                continue
            content = escape_ansi(content)
            if not content.endswith('\n'):
                content += '\n'
            lines_with_nums.append((line_no, content))
        if not lines_with_nums:
            continue
        block_text = ''.join(t for _, t in lines_with_nums)
        block_dt = None
        for _, line_text in reversed(lines_with_nums):
            dt, _ = get_line_date(line_text)
            if dt:
                block_dt = dt
                break
        if block_dt is None:
            block_dt = datetime.datetime.min  # sentinel: no parseable timestamp in block
        # Skip only when we have a parseable timestamp that is before since_dt.
        # If no line in the block had a parseable timestamp, keep the block (don't drop by time).
        if since_dt and block_dt != datetime.datetime.min and block_dt < since_dt:
            continue
        rep = one_representative_block(lines_with_nums)
        if len(rep) == 1:
            line_no = rep[0][0]
            expanded = []
            for i in range(line_no - config.SINGLE_LINE_CONTEXT_BEFORE, line_no + config.SINGLE_LINE_CONTEXT_AFTER + 1):
                if i < 1:
                    continue
                content = linecache.getline(path, i)
                if not content:
                    break
                content = escape_ansi(content)
                if not content.endswith('\n'):
                    content += '\n'
                expanded.append((i, content))
            if expanded:
                rep = expanded
        rep_text = ''.join(t for _, t in rep)
        blocks.append((rep, rep_text, block_dt))
    linecache.clearcache()
    return blocks


def html_escape(s):
    """Escape for HTML content (amp, lt, gt, quote)."""
    if not s:
        return ''
    s = str(s)
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def line_for_display(line_text):
    """Expand literal \\n and \\t in log lines (e.g. JSON details) for display."""
    if not line_text:
        return line_text
    return line_text.replace('\\n', '\n').replace('\\t', '\t')


def html_highlight_line(line_text):
    """Escape HTML and wrap ERROR_KEYWORDS in <span class="hl">."""
    out = html_escape(line_text)
    for kw in (config.ERROR_KEYWORDS or []):
        k = (kw or '').strip()
        if not k:
            continue
        pat = re.compile(re.escape(k), re.IGNORECASE)
        out = pat.sub(lambda m: '<span class="hl">' + m.group(0) + '</span>', out)
    return out


def safe_log_filename(log_path, used_names=None):
    """Return a unique safe HTML filename for a log path. used_names is optional set to avoid collisions."""
    base = (log_path or '').replace('/', '_').replace('\\', '_')
    base = re.sub(r'[^\w\-\.]', '_', base)
    base = base[-60:] if len(base) > 60 else (base or 'log')
    h = hashlib.md5((log_path or '').encode('utf-8', errors='replace')).hexdigest()[:8]
    name = base + '_' + h + '.html'
    if used_names is not None:
        while name in used_names:
            h = hashlib.md5(((log_path or '') + h).encode('utf-8', errors='replace')).hexdigest()[:8]
            name = base + '_' + h + '.html'
        used_names.add(name)
    return name


def build_error_report_html(title, source_label, source_path, report_entries, use_ollama, ai_cache, html_path, report_logs_subdir_basename):
    """
    Build HTML report for pod/must-gather/local modes: main HTML + per-log HTML + viewer HTML in report_logs_dir.
    Returns (html_content_string, report_logs_dir). Caller writes html_content to html_path.
    """
    ai_cache = ai_cache or {}
    report_logs_dir = os.path.join(os.path.dirname(html_path), report_logs_subdir_basename)
    main_basename = os.path.basename(html_path)
    viewer_links = {}
    if report_entries:
        os.makedirs(report_logs_dir, exist_ok=True)
        viewer_ranges = compute_viewer_line_ranges(report_entries)
        used_viewer = set()
        for p in viewer_ranges:
            viewer_links[p] = 'view_' + safe_log_filename(p, used_viewer)
        for p in viewer_links:
            out_path = os.path.join(report_logs_dir, viewer_links[p])
            build_log_viewer_file(p, viewer_ranges[p], out_path, back_link_url='../' + main_basename, back_link_text='Back to report')
    lines = []
    lines.append('<!DOCTYPE html>')
    lines.append('<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    lines.append('<title>' + html_escape(title) + '</title>')
    lines.append('<style>')
    lines.append('body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1200px;}')
    lines.append('a{color:#06c;} h1{font-size:1.5rem;} h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid #ccc;}')
    lines.append('.meta{color:#666;font-size:0.9rem;}')
    lines.append('pre{white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:0.75rem;border-radius:4px;font-size:0.85rem;}')
    lines.append('.hl{background:#fce4a0;padding:0 2px;}')
    lines.append('.block-meta{color:#666;margin-bottom:0.25rem;}')
    lines.append('.ollama-explanation{margin-top:0.5rem;padding:0.5rem;background:#e8f4f8;border-left:3px solid #06c;font-size:0.9rem;}')
    lines.append('.log-links{list-style:none;padding:0;} .log-links li{margin:0.4rem 0;}')
    lines.append('</style></head><body>')
    lines.append('<h1>' + html_escape(title) + '</h1>')
    lines.append('<p class="meta">' + html_escape(source_label) + ': ' + html_escape(source_path) + ' &middot; AI filter: ' + ('on' if use_ollama else 'off') + '</p>')
    lines.append('<h2>Error blocks</h2>')
    max_block_lines = getattr(config, 'MAX_BLOCK_LINES_SHOWN', 9)
    if not report_entries:
        lines.append('<p class="meta">(No error blocks to report.)</p>')
    elif report_logs_dir and os.path.isdir(report_logs_dir):
        used = set()
        path_counts = [(path, sum(1 for e in report_entries if e[0] == path)) for path in set(e[0] for e in report_entries)]
        path_counts.sort(key=lambda x: -x[1])
        lines.append('<p class="meta">Logs with error blocks (click to open):</p>')
        lines.append('<ul class="log-links">')
        subdir_name = report_logs_subdir_basename
        for p, n_blocks in path_counts:
            safe_name = safe_log_filename(p, used)
            link_text = os.path.basename(p) if os.path.basename(p) else p.replace('/', '_')[-40:]
            lines.append('<li><a href="' + html_escape(subdir_name + '/' + safe_name) + '">' + html_escape(link_text) + '</a> <span class="meta">(' + str(n_blocks) + ' block' + ('s' if n_blocks != 1 else '') + ')</span></li>')
            log_lines = []
            log_lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Log: ' + html_escape(p) + '</title>')
            log_lines.append('<style>body{font-family:system-ui,sans-serif;margin:1rem 2rem;} pre{white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:0.75rem;font-size:0.85rem;} .hl{background:#fce4a0;} .block-meta{color:#666;} .ollama-explanation{margin-top:0.5rem;padding:0.5rem;background:#e8f4f8;border-left:3px solid #06c;} a{color:#06c;}</style></head><body>')
            log_lines.append('<p><a href="' + html_escape('../' + main_basename) + '">&larr; Back to report</a></p>')
            log_lines.append('<h2>' + html_escape(p) + '</h2>')
            for (fp, lines_with_nums, block_text, sig, count) in report_entries:
                if fp != p:
                    continue
                log_lines.append('<p class="block-meta">(occurred ' + str(count) + ' time' + ('s' if count != 1 else '') + ')</p>')
                block_lines = []
                for line_no, line_text in lines_with_nums[:max_block_lines]:
                    display = line_for_display(line_text)
                    for i, part in enumerate(display.splitlines()):
                        prefix = (str(line_no) + ': ') if i == 0 else '      '
                        block_lines.append(prefix + html_highlight_line(part))
                if len(lines_with_nums) > max_block_lines:
                    block_lines.append('... (' + str(len(lines_with_nums) - max_block_lines) + ' more lines)')
                log_lines.append('<pre>' + '\n'.join(block_lines) + '</pre>')
                if use_ollama and sig in ai_cache:
                    _, expl = ai_cache[sig]
                    if expl and expl.strip():
                        log_lines.append('<p class="ollama-explanation"><strong>Ollama:</strong> ' + html_escape(expl.strip()) + '</p>')
                if fp in viewer_links and lines_with_nums:
                    first_ln = lines_with_nums[0][0]
                    log_lines.append('<p><a href="' + html_escape(viewer_links[fp] + '#L' + str(first_ln)) + '">View in log at line ' + str(first_ln) + '</a></p>')
            try:
                with open(os.path.join(report_logs_dir, safe_name), 'w', encoding='utf-8') as f:
                    f.write('\n'.join(log_lines))
            except OSError:
                pass
        lines.append('</ul>')
    else:
        for p in sorted(set(e[0] for e in report_entries)):
            lines.append('<h3>' + html_escape(p) + '</h3>')
            for (fp, lines_with_nums, block_text, sig, count) in report_entries:
                if fp != p:
                    continue
                lines.append('<p class="block-meta">(occurred ' + str(count) + ' time' + ('s' if count != 1 else '') + ')</p>')
                block_lines = []
                for line_no, line_text in lines_with_nums[:max_block_lines]:
                    display = line_for_display(line_text)
                    for i, part in enumerate(display.splitlines()):
                        prefix = (str(line_no) + ': ') if i == 0 else '      '
                        block_lines.append(prefix + html_highlight_line(part))
                if len(lines_with_nums) > max_block_lines:
                    block_lines.append('... (' + str(len(lines_with_nums) - max_block_lines) + ' more lines)')
                lines.append('<pre>' + '\n'.join(block_lines) + '</pre>')
                if use_ollama and sig in ai_cache:
                    _, expl = ai_cache[sig]
                    if expl and expl.strip():
                        lines.append('<p class="ollama-explanation"><strong>Ollama:</strong> ' + html_escape(expl.strip()) + '</p>')
                if fp in viewer_links and lines_with_nums:
                    first_ln = lines_with_nums[0][0]
                    lines.append('<p><a href="' + html_escape(viewer_links[fp] + '#L' + str(first_ln)) + '">View in log at line ' + str(first_ln) + '</a></p>')
    lines.append('</body></html>')
    return ('\n'.join(lines), report_logs_dir)


def compute_viewer_line_ranges(report_entries, context_lines=None):
    """
    From report_entries (list of (path, lines_with_nums, block_text, sig, count)), compute per-path
    merged line ranges (start, end) to include in log viewer, with context_lines before/after each block.
    Returns dict: log_path -> list of (start_line, end_line) sorted and merged.
    """
    context = context_lines if context_lines is not None else getattr(config, 'REPORT_VIEWER_CONTEXT_LINES', 80)
    by_path = {}
    for entry in report_entries:
        path = entry[0]
        lines_with_nums = entry[1]
        if not lines_with_nums:
            continue
        line_nos = [n for n, _ in lines_with_nums]
        start = max(1, min(line_nos) - context)
        end = max(line_nos) + context
        by_path.setdefault(path, []).append((start, end))
    out = {}
    for path, ranges in by_path.items():
        ranges.sort(key=lambda r: r[0])
        merged = []
        for a, b in ranges:
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        out[path] = merged
    return out


def build_log_viewer_file(log_path, line_ranges, output_path, back_link_url=None, back_link_text='Back to report'):
    """
    Write an HTML file that shows selected line ranges from log_path with anchors id="L123".
    line_ranges: list of (start_line, end_line). Log can be plain or .gz.
    """
    include = set()
    for a, b in line_ranges:
        for i in range(a, b + 1):
            include.add(i)
    if not include:
        return
    min_ln, max_ln = min(include), max(include)
    header = []
    header.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0"><title>Log: ' + html_escape(log_path) + '</title>')
    header.append('<style>body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:1400px;} pre{white-space:pre-wrap;word-break:break-all;font-size:0.85rem;} .line{display:block;} .line:hover{background:#f0f0f0;} .line-empty{display:block;height:0;overflow:hidden;line-height:0;margin:0;padding:0;font-size:0;} .hl{background:#fce4a0;padding:0 2px;} a{color:#06c;} .viewer-footer{font-size:0.75rem;color:#999;margin-top:1rem;} .viewer-banner{font-size:0.8rem;color:#666;background:#f0f0f0;padding:0.35rem 0.5rem;margin-bottom:0.5rem;border-radius:4px;}</style></head><body>')
    if back_link_url:
        header.append('<p><a href="' + html_escape(back_link_url) + '">&larr; ' + html_escape(back_link_text) + '</a></p>')
    header.append('<p class="viewer-banner">LogToolAI log viewer — error keywords highlighted in yellow, empty lines collapsed</p>')
    header.append('<h2>' + html_escape(log_path) + '</h2>')
    header.append('<pre>')
    spans = []
    open_fn = gzip.open if (log_path or '').lower().endswith('.gz') else open
    mode = 'rt'
    kwargs = {'errors': 'replace'}
    try:
        with open_fn(log_path, mode, **kwargs) as f:
            for num in range(1, max_ln + 1):
                line = f.readline()
                if not line:
                    break
                if num in include:
                    raw = line.rstrip('\n')
                    if not raw.strip():
                        spans.append('<span id="L' + str(num) + '" class="line line-empty">' + str(num) + ':</span>')
                    else:
                        highlighted = html_highlight_line(raw)
                        spans.append('<span id="L' + str(num) + '" class="line">' + str(num) + ': ' + highlighted + '</span>')
    except (OSError, gzip.BadGzipFile):
        spans.append(html_escape('(Could not read log file: ' + log_path + ')'))
    footer = ['</pre>', '<p class="viewer-footer">LogToolAI log viewer (errors highlighted, empty lines collapsed)</p>', '</body></html>']
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(header) + '\n')
            f.write(''.join(spans))  # no newlines between spans so no blank lines in <pre>
            f.write('\n' + '\n'.join(footer))
    except OSError:
        pass


def create_report_archive(html_path, report_path, report_logs_dir=None):
    """
    Create a ZIP archive containing the report files (HTML, TXT, and optional report_logs_dir).
    Returns the absolute path to the created ZIP, or None on failure.
    ZIP is named report_archive_YYYYMMDD_HHMMSS.zip in the same directory as html_path.
    """
    parent = os.path.dirname(os.path.abspath(html_path))
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = 'report_archive_{}.zip'.format(ts)
    zip_path = os.path.join(parent, zip_name)
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in (html_path, report_path):
                path = os.path.abspath(path)
                if os.path.isfile(path):
                    zf.write(path, os.path.basename(path))
            if report_logs_dir and os.path.isdir(report_logs_dir):
                subdir_name = os.path.basename(report_logs_dir.rstrip(os.sep))
                for root, _dirs, files in os.walk(report_logs_dir):
                    for f in files:
                        full = os.path.join(root, f)
                        arcname = os.path.join(subdir_name, os.path.relpath(full, report_logs_dir))
                        zf.write(full, arcname)
        return zip_path
    except (OSError, zipfile.BadZipFile):
        return None


def get_download_command_for_zip(zip_path):
    """
    Return the one-line download command (RunTempest style): desktop runs ssh to bastion,
    su - zuul, ssh to controller, base64 the ZIP, then base64 -d on desktop.
    """
    zip_path = os.path.abspath(zip_path)
    if not os.path.isfile(zip_path):
        return None
    controller = socket.gethostname()
    zip_basename = os.path.basename(zip_path)
    # ssh root@<bastion> "su - zuul -c 'ssh -q controller-0 \"base64 /path/to/file.zip\"'" | base64 -d > file.zip
    cmd = 'ssh root@<your_bastion_host> "su - zuul -c \'ssh -q {} \\"base64 {}\\"\'" | base64 -d > {}'.format(
        controller, zip_path, shlex.quote(zip_basename))
    return cmd


def print_download_prompt(html_path, report_path, report_logs_dir=None, extra_dirs=None):
    """
    Create a ZIP archive of the report, then print the download command block (RunTempest style).
    """
    zip_path = create_report_archive(html_path, report_path, report_logs_dir=report_logs_dir)
    if not zip_path:
        return
    cmd = get_download_command_for_zip(zip_path)
    if not cmd:
        return
    width = 60
    print('')
    print(c(_CYAN, '=' * width))
    print(c(_CYAN, 'DOWNLOAD COMMAND FOR RESULTS ARCHIVE'))
    print(c(_CYAN, '=' * width))
    print(c(_GREEN, 'All results are packaged in a single ZIP file.'))
    print(c(_DIM, 'Copy and paste this command on your local desktop:'))
    print(c(_DIM, '(Replace <your_bastion_host> with your actual bastion hostname)'))
    print('')
    print(c(_YELLOW, '# Download all results (ZIP archive):'))
    print(c(_CYAN, cmd))
    print('')
    print(c(_DIM, 'Then unzip the archive and open the HTML report in your browser.'))
    print(c(_CYAN, '=' * width))


# Export for report writing
REPORT_BOLD = _REPORT_BOLD
REPORT_CYAN = _REPORT_CYAN
REPORT_YELLOW = _REPORT_YELLOW
REPORT_DIM = _REPORT_DIM
REPORT_RESET = _REPORT_RESET
