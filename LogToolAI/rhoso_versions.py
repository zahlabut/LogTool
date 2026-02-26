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


def _print_cmd(cmd):
    """Print the final command used (dim, so user can copy-paste)."""
    print(common.c(_DIM, '  Command: ') + common.c(_DIM, cmd))


def _get_pods_by_label(label_selector):
    """Return list of (namespace, pod_name) for pods matching the label selector."""
    ok, out = common.run(
        "oc get pods -A -l {} --no-headers -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name 2>/dev/null".format(
            label_selector
        ),
        timeout=30
    )
    if not ok or not (out or '').strip():
        return []
    result = []
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            result.append((parts[0], parts[1]))
    return result


def _get_all_pods():
    """Return list of (namespace, pod_name) for all pods."""
    ok, out = common.run(
        "oc get pods -A --no-headers -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name 2>/dev/null",
        timeout=30
    )
    if not ok:
        return []
    result = []
    for line in (out or '').strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            result.append((parts[0], parts[1]))
    return result


def _find_octavia_api_pod():
    """Find a pod that runs the Octavia API workload (not the operator). Prefer label, then name."""
    # Try common RHOSO/OpenStack labels first (pod names have random suffixes)
    for label in [
        'app.kubernetes.io/name=octavia-api',
        'app=octavia-api',
        'component=octavia-api',
    ]:
        pods = _get_pods_by_label(label)
        if pods:
            return pods[0]
    # Fallback: name contains octavia-api but not operator
    for ns, name in _get_all_pods():
        if re.search(r'octavia-api', name, re.I) and 'operator' not in name.lower():
            return (ns, name)
    return (None, None)


def _find_designate_workload_pod():
    """Find a pod that runs Designate services (api/central/worker), not the designate-operator."""
    # Try labels first so we get workload pods, not operator
    for label in [
        'app.kubernetes.io/name=designate-api',
        'app=designate-api',
        'component=designate-api',
        'app.kubernetes.io/name=designate-central',
        'app=designate-central',
    ]:
        pods = _get_pods_by_label(label)
        if pods:
            return pods[0]
    # Fallback: name contains 'designate' but not 'operator' (skip designate-operator-controller-manager)
    for ns, name in _get_all_pods():
        if not re.search(r'designate', name, re.I):
            continue
        if 'operator' in name.lower():
            continue
        return (ns, name)
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
    openstack_cmd = 'oc get openstackversion -A'
    ok, out = common.run(openstack_cmd + ' 2>/dev/null', timeout=15)
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
    _print_cmd(openstack_cmd)

    # --- 2) Octavia (OVN Octavia provider) ---
    print(_header('Octavia (OVN Octavia provider)'))
    ns, pod = _find_octavia_api_pod()
    if not pod:
        print(_version_line('Octavia API pod', 'no octavia-api pod found', ok=False))
    else:
        print(_version_line('Pod', '{} / {}'.format(ns, pod)))
        # One exec for all octavia-related packages (OVN provider + core/Amphora)
        ok, rpm_out = _exec_rpm_grep(ns, pod, 'octavia-api', r'octavia')
        if not rpm_out:
            print(_version_line('Package', 'no octavia* package in pod', ok=False))
        else:
            lines = [l.strip() for l in rpm_out.splitlines() if l.strip()]
            ovn_lines = [l for l in lines if 'ovn-octavia' in l or 'ovn-octavia-provider' in l]
            # Core Octavia (Amphora provider / API): python3-octavia, octavia-common, etc. (exclude OVN-only)
            core_lines = [l for l in lines if 'ovn-octavia' not in l and 'ovn-octavia-provider' not in l]
            if ovn_lines:
                ver = _extract_version_from_rpm_line(ovn_lines[0])
                print(_version_line('python3-ovn-octavia-provider (OVN)', ver))
            if core_lines:
                # Prefer python3-octavia as the Amphora/core version
                preferred = next((l for l in core_lines if 'python3-octavia' in l and 'ovn' not in l), core_lines[0])
                ver = _extract_version_from_rpm_line(preferred)
                print(_version_line('Octavia core / Amphora provider', ver))
            if not ovn_lines and not core_lines:
                print(_version_line('rpm', lines[0][:80] if lines else '(none)'))
        octavia_cmd = "oc exec -n {} {} -c octavia-api -- rpm -qa | grep -E 'octavia'".format(ns, pod)
        _print_cmd(octavia_cmd)
        print(common.c(_DIM, "  (OVN Octavia provider + Octavia core versions from the command above.)"))

    # --- 3) Designate ---
    print(_header('Designate'))
    ns, pod = _find_designate_workload_pod()
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
        _print_cmd("oc exec -n {} {} -- rpm -qa | grep -E 'designate'".format(ns, pod))

    print()
    print(common.c(_DIM, 'Done.'))


if __name__ == '__main__':
    main()
    sys.exit(0)
