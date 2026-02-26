# Ollama: require real explanations per block

Replace the function `_ollama_classify_and_explain` in `collect_and_analyze_pod_logs.py` with the version below. It asks Ollama for a short explanation (what it means, impact, when it appears) for every block classified as a real issue, and parses multi-line replies so the report shows that explanation.

---

Replace from:

```python
def _ollama_classify_and_explain(block_text):
    """
    Ask local Ollama: is this block a real problem? If yes, get a short explanation.
    ...
    """
    snippet = (block_text or '')[:AI_MAX_BLOCK_CHARS]
    ...
    prompt = (
        'Is this log block a real problem that needs attention? Reply with exactly YES or NO. '
        'If YES, on the next line write one short sentence explaining what the problem is.\n\n' + snippet
    )
    ...
        # YES: extract explanation (first line after YES, or rest of first line after "YES")
        lines = [l.strip() for l in reply.splitlines() if l.strip()]
        explanation = None
        for i, line in enumerate(lines):
            if line.upper().startswith('YES'):
                rest = line[len('YES'):].strip().strip('.:')
                if rest:
                    explanation = rest
                elif i + 1 < len(lines):
                    explanation = lines[i + 1]
                break
        return (True, explanation if explanation else None)
```

With:

```python
def _ollama_classify_and_explain(block_text):
    """
    Ask local Ollama: is this block a real problem? If yes, get a short explanation
    (what it means, impact, when it typically appears). Called only at report stage when POD_LOGS_AI_FILTER=1.
    Returns (keep: bool, explanation: str or None). On failure returns (True, None) to keep block.
    """
    snippet = (block_text or '')[:AI_MAX_BLOCK_CHARS]
    if len(block_text or '') > AI_MAX_BLOCK_CHARS:
        snippet += '\n... [truncated]'
    prompt = (
        'Is this log block a real problem that needs attention? Reply with exactly YES or NO.\n'
        'If YES, you MUST add a short explanation (2-4 sentences) on the next lines:\n'
        '- What this error means (in plain language)\n'
        '- What impact it can have\n'
        '- When or why it typically appears\n'
        'Start your reply with YES or NO, then put the explanation on the following lines.\n\n'
        'Log block:\n' + snippet
    )
    try:
        url = OLLAMA_HOST + '/api/generate'
        body = json.dumps({'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        reply = (data.get('response') or '').strip()
        reply_upper = reply.upper()
        if 'NO' in reply_upper and 'YES' not in reply_upper:
            return (False, None)
        # YES: take everything after the first line that contains YES as the explanation (up to ~400 chars)
        lines = reply.splitlines()
        explanation_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith('YES'):
                rest = line[len('YES'):].strip().lstrip('.-:).').strip()
                if rest:
                    explanation_lines.append(rest)
                for j in range(i + 1, len(lines)):
                    rest_line = lines[j].strip()
                    if rest_line:
                        explanation_lines.append(rest_line)
                break
        explanation = ' '.join(explanation_lines).strip() if explanation_lines else None
        if explanation and len(explanation) > 450:
            explanation = explanation[:447] + '...'
        return (True, explanation if explanation else None)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError):
        return (True, None)
```

---

After this change, when Ollama classifies a block as a real issue it will return 2–4 sentences (what it means, impact, when it appears). That text is shown in the report under `Ollama: ...` for each block. If the model still does not provide an explanation, the report will show `Ollama: (classified as real issue)` as before.
