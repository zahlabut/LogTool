#!/usr/bin/python3
"""
LogToolAI — main entry. Run this script to choose a mode (e.g. analyze OpenShift pod logs, analyze local directory).
"""

import os
import sys

# Ensure mode scripts in this directory are importable (e.g. when cwd is not LogToolAI).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import logtool_common as common

MODES = [
    (1, 'Analyze OpenShift pod logs (grep + optional Ollama)', 'collect_and_analyze_pod_logs'),
    (2, 'Run must-gather, then analyze collected logs (grep + optional Ollama)', 'must_gather_analyze'),
    (3, 'Analyze logs in local directory', 'analyze_local_logs'),
    (4, 'Show RHOSO / Octavia / Designate versions', 'rhoso_versions'),
    (5, 'Extract pod logs for time range + Ollama summary (processes, success/errors)', 'extract_logs_time_range'),
    (6, 'Analyze Zuul job (run locally: URL or path, download then console, tempest, report)', 'zuul_job_analyze'),
    (7, 'Trace ID in pod logs (collect on controller, chronological timeline, error highlight)', 'trace_id_in_logs'),
    (8, 'Collect pod logs by component(s) (raw oc logs, ZIP download)', 'collect_component_logs'),
]

_BOLD = '\033[1m'
_CYAN = '\033[36m'
_GREEN = '\033[32m'
_YELLOW = '\033[33m'
_DIM = '\033[2m'


def main():
    print(common.c(_BOLD + _CYAN, 'LogToolAI') + common.c(_BOLD, ' — choose mode:\n'))
    for num, label, _ in MODES:
        print('  ' + common.c(_GREEN, str(num) + ')') + ' ' + label)
    print('  ' + common.c(_DIM, '0) Exit'))
    print()
    try:
        choice = input(common.c(_DIM, 'Choice [0-{}]: ').format(len(MODES))).strip()
        idx = int(choice)
    except (ValueError, EOFError):
        idx = 0
    if idx == 0:
        print(common.c(_DIM, 'Bye.'))
        sys.exit(0)
    if idx < 1 or idx > len(MODES):
        print(common.c(_YELLOW, 'Invalid choice.'))
        sys.exit(1)
    module_name = MODES[idx - 1][2]
    if module_name == 'collect_and_analyze_pod_logs':
        from collect_and_analyze_pod_logs import main as run_mode
    elif module_name == 'must_gather_analyze':
        from must_gather_analyze import main as run_mode
    elif module_name == 'analyze_local_logs':
        from analyze_local_logs import main as run_mode
    elif module_name == 'rhoso_versions':
        from rhoso_versions import main as run_mode
    elif module_name == 'extract_logs_time_range':
        from extract_logs_time_range import main as run_mode
    elif module_name == 'zuul_job_analyze':
        from zuul_job_analyze import main as run_mode
    elif module_name == 'trace_id_in_logs':
        trace_script = os.path.join(_SCRIPT_DIR, 'trace_id_in_logs.py')
        if not os.path.isfile(trace_script):
            print(common.c(_YELLOW, 'Mode 7 requires trace_id_in_logs.py in the LogToolAI directory.'))
            print(common.c(_DIM, 'Expected: ') + trace_script)
            print(common.c(_DIM, 'Copy the file from your repo to controller-0, then run again.'))
            sys.exit(1)
        try:
            from trace_id_in_logs import main as run_mode
        except ImportError as e:
            print(common.c(_YELLOW, 'Could not load mode 7 (trace_id_in_logs): ') + str(e))
            sys.exit(1)
    elif module_name == 'collect_component_logs':
        from collect_component_logs import main as run_mode
    else:
        print('Unknown mode.')
        sys.exit(1)
    run_mode()


if __name__ == '__main__':
    main()
