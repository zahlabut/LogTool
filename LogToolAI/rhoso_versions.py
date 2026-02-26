#!/usr/bin/python3
"""
LogToolAI — RHOSO / Octavia / Designate version check.
Runs oc get openstackversion and execs into Octavia/Designate pods to report package versions.
Read-only, display-only: no log collection, no reports to disk.
"""

import re
import sys

import logtool_common as common

# Reuse common's color names (they are module-level).
_CYAN = '\033[36m'
_GREEN = '\033[32m'
_YELLOW = '\033[33m'
_DIM = '\033[2m'
_BOLD = '\033[1m'
_RED = '\033[31m'
_RESET = '\033[0m'


def _header(title):
    return common.c(_BOLD + _CYAN, '\n' + title + '\n' + '─' * min(60, len(title) + 4))


def _version_line(label, value, ok=True):
    style = _GREEN if ok else _RED
    return '  {} {}'.format(
        common.c(_YELLOW, label + ':'),
        common.c(style, value) if value else common.c(_DIM, '(not found)')
    )


def _get_first_pod(pattern):
    """Return (namespace, pod_name) for first pod whose name matches pattern, or (None, None)."""
    ok, out = common.run(
        "oc get pods -A --no-headers -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name 2>/dev/null",
        timeout=30
    )
    if not ok:
        return (None, None)
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.search(pattern, parts[1], re.I):
            return (parts[0], parts[1])
    return (None, None)


def _exec_rpm_grep(namespace, pod, container_name, grep_pattern):
    """Exec into pod in namespace, run rpm -qa | grep -E <grep_pattern>, return (ok, output)."""
    if not namespace or not pod:
        return (False, '')
    extra = ' -c {}'.format(container_name) if container_name else ''
    cmd = "oc exec -n {} {}{} -- rpm -qa 2>/dev/null | grep -E '{}' || true".format(
        namespace, pod, extra, grep_pattern.replace("'", "'\"'\"'")
    )
    ok, out = common.run(cmd, timeout=15)
    return (ok, (out or '').strip())


def _extract_version_from_rpm_line(line):
    """Extract version-release from a line like 'python3-ovn-octavia-provider-4.0.3-18.0...'."""
    # Last token before .noarch or .x86_64 is often version-release; or match known pattern
    m = re.search(r'-(\d+\.\d+\.\d+[-.]\S+?)(?:\.noarch|\.x86_64)?\s*$', line)
    if m:
        return m.group(1).strip()
    m = re.search(r'-(\d+\.\d+\.\d+[^\s]*)', line)
    if m:
        return m.group(1).strip()
    return line.strip()


def main():
    print(common.c(_BOLD, 'RHOSO / Octavia / Designate — version check'))
    print(common.c(_DIM, 'Requires: oc logged in, permission to get openstackversion and exec into pods.'))

    # --- 1) OpenStack version (RHOSO in general) ---
    print(_header('OpenStack version (RHOSO)'))
    ok, out = common.run('oc get openstackversion -A 2>/dev/null', timeout=15)
    if not ok:
        print(_version_line('openstackversion', 'oc failed or CRD not found', ok=False))
        print(common.c(_DIM, '  (run: oc get openstackversion -A)'))
    else:
        out = (out or '').strip()
        if not out:
            print(_version_line('openstackversion', 'no resources found', ok=False))
        else:
            for line in out.splitlines():
                print('  ', line if not line.startswith('NAME') else common.c(_YELLOW, line))

    # --- 2) Octavia (OVN Octavia provider) ---
    print(_header('Octavia (OVN Octavia provider)'))
    ns, pod = _get_first_pod(r'octavia-api')
    if not pod:
        print(_version_line('Octavia API pod', 'no octavia-api pod found', ok=False))
    else:
        print(_version_line('Pod', '{} / {}'.format(ns, pod)))
        ok, rpm_out = _exec_rpm_grep(ns, pod, 'octavia-api', r'python3-ovn-octavia|ovn-octavia')
        if not rpm_out:
            print(_version_line('Package', 'no python3-ovn-octavia* package in pod', ok=False))
        else:
            # Prefer the line with ovn-octavia-provider
            lines = [l for l in rpm_out.splitlines() if 'ovn-octavia' in l]
            if lines:
                ver = _extract_version_from_rpm_line(lines[0])
                print(_version_line('python3-ovn-octavia-provider', ver))
            else:
                print(_version_line('rpm', rpm_out.splitlines()[0][:80] if rpm_out else '(none)'))

    # --- 3) Designate ---
    print(_header('Designate'))
    ns, pod = _get_first_pod(r'designate')
    if not pod:
        print(_version_line('Designate pod', 'no designate pod found', ok=False))
    else:
        print(_version_line('Pod', '{} / {}'.format(ns, pod)))
        ok, rpm_out = _exec_rpm_grep(ns, pod, None, r'designate')
        if not rpm_out:
            print(_version_line('Package', 'no designate* package in pod', ok=False))
        else:
            # Show first designate package version
            lines = [l for l in rpm_out.splitlines() if l.strip()]
            if lines:
                ver = _extract_version_from_rpm_line(lines[0])
                print(_version_line('designate (rpm)', ver))
            else:
                print(_version_line('rpm', rpm_out[:80] if rpm_out else '(none)'))

    print()
    print(common.c(_DIM, 'Done.'))


if __name__ == '__main__':
    main()
    sys.exit(0)
