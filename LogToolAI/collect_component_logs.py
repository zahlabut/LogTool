#!/usr/bin/python3
"""
Collect full pod logs for one or more OpenShift components (no grep/analysis).
User picks components (e.g. octavia,cinder), oc logs each pod, ZIP + SSH download.
Run from LogToolMain or directly.
"""

import os
import sys
import shutil
import datetime
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import logtool_common as common
from collect_and_analyze_pod_logs import get_pods, group_pods_by_component


def _pod_log_filename(ns, name, used_names):
    """Primary name: pod_name.log; add namespace prefix if duplicate pod name."""
    base = name.replace('/', '-') + '.log'
    if base not in used_names:
        used_names.add(base)
        return base
    alt = (ns + '_' + name).replace('/', '-') + '.log'
    used_names.add(alt)
    return alt


def _parse_component_selection(raw, groups):
    """Parse comma-separated menu numbers or component names. Returns list of (component, pods)."""
    if not raw or not raw.strip():
        return []
    selected = []
    comp_by_name = {comp.lower(): (comp, pods) for comp, pods in groups}
    for token in raw.split(','):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(groups):
                selected.append(groups[idx - 1])
            continue
        key = token.lower()
        if key in comp_by_name:
            selected.append(comp_by_name[key])
    seen = set()
    unique = []
    for comp, pods in selected:
        if comp in seen:
            continue
        seen.add(comp)
        unique.append((comp, pods))
    return unique


def _collect_one_pod(args):
    ns, name, path = args
    cmd = 'oc logs -n {} {} --timestamps --all-containers > {} 2>/dev/null'.format(
        ns, name, path
    )
    common.run(cmd, timeout=120)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    return None


def _collect_pod_logs(logs_dir, pods):
    os.makedirs(logs_dir, exist_ok=True)
    n = len(pods)
    n_workers = min(config.MAX_WORKERS, n)
    print(common.c('\033[2m', '  Collecting logs for {} pods ({} workers)...').format(n, n_workers), flush=True)
    start = time_module.time()
    created = []
    done = 0
    used_names = set()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        tasks = [
            (ns, name, os.path.join(logs_dir, _pod_log_filename(ns, name, used_names)))
            for ns, name in pods
        ]
        futures = {ex.submit(_collect_one_pod, t): t for t in tasks}
        for fut in as_completed(futures):
            done += 1
            if done % 5 == 0 or done == n:
                print(common.c('\033[2m', '  [collect] {}/{} pods...').format(done, n), flush=True)
            try:
                path = fut.result()
                if path:
                    created.append(path)
            except Exception:
                pass
    print(common.c('\033[32m', '  Done in {:.1f}s. {} log file(s) written.').format(
        time_module.time() - start, len(created)))
    return created


def _write_manifest(report_path, html_path, components, pods, log_paths):
    comp_list = ', '.join(c for c, _ in components)
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('Component log collection\n')
        f.write('Collected at: {}\n'.format(ts))
        f.write('Components: {}\n'.format(comp_list))
        f.write('Pods requested: {}\n'.format(len(pods)))
        f.write('Log files written: {}\n\n'.format(len(log_paths)))
        for path in sorted(log_paths):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            f.write('  {} ({} bytes)\n'.format(os.path.basename(path), size))

    lines = []
    lines.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    lines.append('<title>Component logs: {}</title>'.format(common.html_escape(comp_list)))
    lines.append('<style>body{font-family:system-ui,sans-serif;margin:1rem 2rem;max-width:900px;}')
    lines.append('.meta{color:#666;} ul{line-height:1.6;}</style></head><body>')
    lines.append('<h1>Component log collection</h1>')
    lines.append('<p class="meta"><strong>Components:</strong> {}</p>'.format(common.html_escape(comp_list)))
    lines.append('<p class="meta"><strong>Collected:</strong> {} &middot; {} pod(s) &middot; {} file(s)</p>'.format(
        common.html_escape(ts), len(pods), len(log_paths)))
    lines.append('<p class="meta">Unzip the archive; pod logs are under <code>logs/</code>.</p>')
    if log_paths:
        lines.append('<h2>Files</h2><ul>')
        for path in sorted(log_paths):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            lines.append('<li>{} <span class="meta">({} bytes)</span></li>'.format(
                common.html_escape(os.path.basename(path)), size))
        lines.append('</ul>')
    else:
        lines.append('<p class="meta">(No log content collected.)</p>')
    lines.append('</body></html>')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'
    _timeout = getattr(config, 'PROMPT_TIMEOUT_SEC', 0)

    print(common.c(_CYAN, '=' * 60))
    print(common.c(_CYAN, '[1/3] Choose components to collect'))
    print(common.c(_CYAN, '=' * 60))
    print(common.c(_DIM, 'Collecting pod list (oc get pods -A)...'), flush=True)
    pods = get_pods()
    if not pods:
        print(common.c(_YELLOW, 'No pods found or oc not available. Exiting.'))
        sys.exit(1)
    print(common.c(_GREEN, 'Found {} pods.').format(len(pods)))

    groups = group_pods_by_component(pods)
    print(common.c(_DIM, 'Components (alphabetical by pod name prefix):'))
    menu_items = []
    for i, (component, group_pods) in enumerate(groups, 1):
        n = len(group_pods)
        menu_items.append((i, '{} ({} pod{})'.format(component, n, 's' if n != 1 else '')))
    common.print_menu_columns(menu_items, num_columns=3, cell_width=38)
    print('')
    print(common.c(_DIM, 'Enter one or more components — menu numbers or names, comma-separated.'))
    print(common.c(_DIM, 'Examples: 5,12   or   octavia,cinder   or   nova,octavia,cinder'))
    raw = common.timed_input(
        common.c(_CYAN, 'Components to collect: '),
        '',
        timeout_sec=_timeout,
    ).strip()
    selected = _parse_component_selection(raw, groups)
    if not selected:
        print(common.c(_YELLOW, 'No valid components selected. Exiting.'))
        sys.exit(1)

    selected_pods = []
    for comp, group_pods in selected:
        selected_pods.extend(group_pods)
    comp_names = [c for c, _ in selected]
    print(common.c(_GREEN, 'Selected {} component(s): {} ({} pods).').format(
        len(selected), ', '.join(comp_names), len(selected_pods)))

    print('')
    print(common.c(_CYAN, '[2/3] Collect pod logs (oc logs, full available log)'))
    print(common.c(_DIM, '-' * 60))
    run_dir = config.timestamped_report_dir('component_logs')
    os.makedirs(run_dir, exist_ok=True)
    logs_dir = os.path.join(run_dir, 'collected_logs')
    print(common.c(_DIM, 'Run directory: ') + common.c(_CYAN, run_dir))
    log_paths = _collect_pod_logs(logs_dir, selected_pods)
    if not log_paths:
        print(common.c(_YELLOW, 'No log content collected (pods empty or oc logs failed).'))

    print('')
    print(common.c(_CYAN, '[3/3] Create download archive'))
    print(common.c(_DIM, '-' * 60))
    report_path = os.path.join(run_dir, 'component_logs_manifest.txt')
    html_path = os.path.join(run_dir, 'component_logs_index.html')
    _write_manifest(report_path, html_path, selected, selected_pods, log_paths)
    common.print_download_prompt(
        html_path,
        report_path,
        report_logs_dir=None,
        log_paths_to_include=log_paths or None,
        show_ssh_download=True,
    )
    if os.path.isdir(logs_dir):
        try:
            shutil.rmtree(logs_dir)
        except OSError:
            pass
    print(common.c(_DIM, 'Components: ') + ', '.join(comp_names))


if __name__ == '__main__':
    main()
