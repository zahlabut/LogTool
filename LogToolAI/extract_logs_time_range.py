#!/usr/bin/python3
"""
Extract pod logs for a time range and optionally get an Ollama summary.
Pod list → group by component → baseline → time range → fetch logs → write to dedicated folder
(colorized errors). If Ollama is available, send the log content and ask: what processes do you see,
did they complete successfully or raise errors? Summary is saved in the same folder.
Run from LogToolMain or directly.
"""

import os
import sys
import datetime
import time as time_module
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
    print(common.c(_CYAN, '[1/6] Pod list'))
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
    try:
        choice = input(common.c(_DIM, 'Choice [1-{}]: ').format(num_options)).strip()
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
    print(common.c(_CYAN, '[2/6] Baseline timestamp'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_DIM, 'Getting latest log timestamp (oc logs --tail=10 per pod)...'), flush=True)
    baseline = get_baseline_quick(selected_pods)
    if baseline is None:
        print(common.c(_YELLOW, 'Could not detect any timestamp. Using "since" = 24h ago.'))
        since_dt = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    else:
        baseline_str = baseline.strftime('%Y-%m-%d %H:%M:%S')
        print('Last logged message was at: ' + common.c(_CYAN, baseline_str) + '.')
        print(common.c(_DIM, 'Choose time range (logs from this point back will be extracted):'))
        print('  1) 2h back')
        print('  2) 1h back')
        print('  3) 30m back')
        print('  4) Custom (enter minutes, e.g. 45)')
        try:
            choice = input(common.c(_DIM, 'Choice [1-4]: ')).strip() or '1'
        except EOFError:
            choice = '1'
        if choice == '1':
            delta = datetime.timedelta(hours=2)
        elif choice == '2':
            delta = datetime.timedelta(hours=1)
        elif choice == '3':
            delta = datetime.timedelta(minutes=30)
        elif choice == '4':
            try:
                mins = int(input('Minutes back: ').strip())
                delta = datetime.timedelta(minutes=max(0, mins))
            except Exception:
                delta = datetime.timedelta(hours=1)
        else:
            delta = datetime.timedelta(hours=2)
        since_dt = baseline - delta
    since_iso = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    since_str = since_dt.strftime('%Y-%m-%d %H:%M:%S')
    print(common.c(_GREEN, 'Extracting logs since: ') + common.c(_CYAN, since_str) + '.')

    print('')
    print(common.c(_CYAN, '[3/6] Create output folder'))
    print(common.c(_DIM, '-' * 60))
    base = getattr(config, 'EXTRACTED_LOGS_BASE_DIR', os.path.join(config.BASE_DIR, 'extracted_logs'))
    os.makedirs(base, exist_ok=True)
    run_id = 'extracted_{}'.format(datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    out_dir = os.path.join(base, run_id)
    os.makedirs(out_dir, exist_ok=True)
    print(common.c(_DIM, 'Output directory: ') + common.c(_CYAN, out_dir))

    print('')
    print(common.c(_CYAN, '[4/6] Fetch and write logs (error strings colorized)'))
    print(common.c(_DIM, '-' * 60))
    n = len(selected_pods)
    n_workers = min(config.MAX_WORKERS, n)
    print(common.c(_DIM, '  Fetching logs for {} pods ({} workers)...').format(n, n_workers), flush=True)
    start = time_module.time()
    written = 0
    logs_for_ollama = []  # (ns, name, raw) for pods that had content
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_fetch_one_pod_log, ns, name, since_iso): (ns, name) for ns, name in selected_pods}
        for fut in as_completed(futures):
            try:
                ns, name, raw = fut.result()
                if not (raw or '').strip():
                    continue
                logs_for_ollama.append((ns, name, raw))
                out_path = os.path.join(out_dir, safe_filename(ns, name))
                with open(out_path, 'w') as f:
                    for line in (raw or '').splitlines():
                        f.write(common.highlight_error_keywords(line + '\n'))
                written += 1
                if written % 5 == 0 or written == n:
                    print(common.c(_DIM, '  [write] {}/{} pods...').format(written, n), flush=True)
            except Exception:
                pass
    print(common.c(_GREEN, '  Done in {:.1f}s. {} log files written.').format(time_module.time() - start, written))

    summary_response = None
    if written > 0 and getattr(config, 'OLLAMA_HOST', '').strip() and common.ollama_reachable():
        print('')
        print(common.c(_CYAN, '[5/6] Ollama summary (what processes, success or errors?)'))
        print(common.c(_DIM, '-' * 60))
        resolved_model = (config.OLLAMA_MODEL or '').strip()
        if not resolved_model:
            if sys.stdin.isatty():
                resolved_model = common.ollama_choose_model_interactive(config.OLLAMA_HOST)
            else:
                resolved_model = common.ollama_pick_best_model(config.OLLAMA_HOST)
        if resolved_model:
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
                'We are troubleshooting: we want to know if everything went OK or if there were issues detected and logged.\n\n'
                'Log source names (pods): {}.\n\n'
                'Below are the log contents. Each pod is delimited by "--- BEGIN POD: namespace / podname ---" and "--- END POD ---". '
                'Answer in 3–8 short sentences: (1) What processes or operations do you see in these logs? '
                '(e.g. zone creation, API calls, startup). (2) Based on the messages, did they complete successfully or did any raise errors? '
                'Use plain language. Start directly with what you see—no preamble like "Based on the logs".\n\n'
                'Logs:\n\n'
            ).format(selected_group_name, pod_list) + log_text
            print(common.c(_DIM, '  Sending {} chars to Ollama (model: {})...').format(len(log_text), resolved_model), flush=True)
            summary_response = common.ollama_custom_prompt(prompt, model=resolved_model)
            if summary_response:
                print(common.c(_GREEN, '  Ollama summary:') + '\n  ' + summary_response.replace('\n', '\n  '))
                summary_path = os.path.join(out_dir, 'ollama_summary.txt')
                with open(summary_path, 'w') as f:
                    f.write('Ollama summary (time range: from {} to now)\n'.format(since_str))
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
            print(common.c(_CYAN, '[5/6] Ollama summary'))
            print(common.c(_DIM, '  Ollama not configured or unreachable — skipping.'))

    print('')
    print(common.c(_CYAN, '[6/6] Summary'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_GREEN, 'Logs extracted to: ') + common.c(_CYAN, out_dir))
    print(common.c(_DIM, 'Time range: from ') + since_str + common.c(_DIM, ' to now.'))
    print(common.c(_DIM, 'View with: ') + 'less -R <file>' + common.c(_DIM, ' to see colorized errors.'))


if __name__ == '__main__':
    main()
