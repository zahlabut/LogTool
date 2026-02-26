# Shared functions and helpers for LogToolAI modes.
# Import this module and use its functions; it reads config.py for parameters.

import re
import sys
import os
import json
import shlex
import linecache
import datetime
import difflib
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from string import digits

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
    models = ollama_fetch_models(host)
    return models[0]['name'] if models else None


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
    print('  0) Auto (use largest: {})'.format(models[0]['name']), flush=True)
    print('', flush=True)
    while True:
        try:
            choice = input(c(_DIM, 'Choice [0-{}] (default 0): ').format(len(models))).strip() or '0'
            if choice == '0':
                return models[0]['name']
            idx = int(choice)
            if 1 <= idx <= len(models):
                return models[idx - 1]['name']
        except (ValueError, EOFError):
            pass
        print(c(_YELLOW, '  Invalid choice. Enter 0 for auto or a number from the list.'), flush=True)


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
            block_dt = datetime.datetime.min
        if since_dt and block_dt < since_dt:
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


# Export for report writing
REPORT_BOLD = _REPORT_BOLD
REPORT_CYAN = _REPORT_CYAN
REPORT_YELLOW = _REPORT_YELLOW
REPORT_DIM = _REPORT_DIM
REPORT_RESET = _REPORT_RESET
