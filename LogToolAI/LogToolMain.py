#!/usr/bin/python3
"""
LogToolAI — main entry. Run this script to choose a mode (e.g. analyze OpenShift pod logs, analyze local directory).
"""

import sys

MODES = [
    (1, 'Analyze OpenShift pod logs (grep + optional Ollama)', 'collect_and_analyze_pod_logs'),
    (2, 'Run must-gather, then analyze collected logs (grep + optional Ollama)', 'must_gather_analyze'),
    (3, 'Analyze logs in local directory', 'analyze_local_logs'),
    (4, 'Show RHOSO / Octavia / Designate versions', 'rhoso_versions'),
]


def main():
    print('LogToolAI — choose mode:\n')
    for num, label, _ in MODES:
        print('  {}) {}'.format(num, label))
    print('  0) Exit')
    print()
    try:
        choice = input('Choice [0-{}]: '.format(len(MODES))).strip()
        idx = int(choice)
    except (ValueError, EOFError):
        idx = 0
    if idx == 0:
        print('Bye.')
        sys.exit(0)
    if idx < 1 or idx > len(MODES):
        print('Invalid choice.')
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
    else:
        print('Unknown mode.')
        sys.exit(1)
    run_mode()


if __name__ == '__main__':
    main()
