#!/usr/bin/python3
"""
Extract pod logs for a given time range (no error analysis).
Pod list → group by component → choose group → baseline → time range (2h/1h/30m/custom)
→ fetch oc logs --since-time for each pod → write to a dedicated folder with error strings colorized.
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
    print(common.c(_CYAN, '[1/5] Pod list'))
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
        print(common.c(_GREEN, 'Selected all {} pods.').format(total))
    else:
        selected_pods = groups[idx - 1][1]
        print(common.c(_GREEN, 'Selected group "{}": {} pods.').format(groups[idx - 1][0], len(selected_pods)))

    print('')
    print(common.c(_CYAN, '[2/5] Baseline timestamp'))
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
    print(common.c(_CYAN, '[3/5] Create output folder'))
    print(common.c(_DIM, '-' * 60))
    base = getattr(config, 'EXTRACTED_LOGS_BASE_DIR', os.path.join(config.BASE_DIR, 'extracted_logs'))
    os.makedirs(base, exist_ok=True)
    run_id = 'extracted_{}'.format(datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    out_dir = os.path.join(base, run_id)
    os.makedirs(out_dir, exist_ok=True)
    print(common.c(_DIM, 'Output directory: ') + common.c(_CYAN, out_dir))

    print('')
    print(common.c(_CYAN, '[4/5] Fetch and write logs (error strings colorized)'))
    print(common.c(_DIM, '-' * 60))
    n = len(selected_pods)
    n_workers = min(config.MAX_WORKERS, n)
    print(common.c(_DIM, '  Fetching logs for {} pods ({} workers)...').format(n, n_workers), flush=True)
    start = time_module.time()
    written = 0
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_fetch_one_pod_log, ns, name, since_iso): (ns, name) for ns, name in selected_pods}
        for fut in as_completed(futures):
            try:
                ns, name, raw = fut.result()
                if not (raw or '').strip():
                    # No log lines in time range — skip this pod (no file written)
                    continue
                out_path = os.path.join(out_dir, safe_filename(ns, name))
                with open(out_path, 'w') as f:
                    for line in (raw or '').splitlines():
                        # Keep newline; colorize error keywords for viewing with less -R
                        f.write(common.highlight_error_keywords(line + '\n'))
                written += 1
                if written % 5 == 0 or written == n:
                    print(common.c(_DIM, '  [write] {}/{} pods...').format(written, n), flush=True)
            except Exception:
                pass
    print(common.c(_GREEN, '  Done in {:.1f}s. {} log files written.').format(time_module.time() - start, written))

    print('')
    print(common.c(_CYAN, '[5/5] Summary'))
    print(common.c(_DIM, '-' * 60))
    print(common.c(_GREEN, 'Logs extracted to: ') + common.c(_CYAN, out_dir))
    print(common.c(_DIM, 'Time range: from ') + since_str + common.c(_DIM, ' to now.'))
    print(common.c(_DIM, 'View with: ') + 'less -R <file>' + common.c(_DIM, ' to see colorized errors.'))


if __name__ == '__main__':
    main()
