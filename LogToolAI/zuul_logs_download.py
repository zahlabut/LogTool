#!/usr/bin/python3
"""
Download all logs and artifacts from a Zuul job logs page URL.
Use when Zuul's "download artifacts" does not include all logs (e.g. tempest results).
PSI/Red Hat: Kerberos + cookies, download-zuul-logs.py (ci-framework-tools), then wget tempest/tobiko.
Else: Zuul build API + HTML scraper (requires no auth for public Zuul).
Saves files under a local directory; then run mode 6 (analyze) on that directory.
"""

import json
import os
import re
import subprocess
import sys
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import config
import logtool_common as common

# Default request timeout (seconds).
FETCH_TIMEOUT = 60
# User-Agent so we are not blocked.
USER_AGENT = 'LogToolAI-Zuul-Download/1.0'
# Max depth when recursing into directory listings (avoid infinite loops).
MAX_DEPTH = 20
# PSI: timeout for download-zuul-logs.py run (seconds).
PSI_SCRIPT_TIMEOUT = 600
# PSI: auth.redhat.com URL for Kerberos cookie
PSI_AUTH_URL = 'https://auth.redhat.com'
# Skip following links that look like these (path segments or full URLs).
SKIP_PATTERNS = (
    re.compile(r'^javascript:', re.I),
    re.compile(r'^mailto:', re.I),
    re.compile(r'^#', re.I),
    re.compile(r'^data:', re.I),
)


def _normalize_zuul_url(url):
    """
    If URL is a Zuul build or buildset URL without /logs, append /logs so downstream can use it.
    Accepts base URL like .../build/<uuid> or .../buildset/<uuid>.
    """
    url = (url or '').strip()
    if not url or not url.startswith(('http://', 'https://')):
        return url
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or '').rstrip('/')
    if '/build/' in path or '/buildset/' in path:
        if not path.endswith('/logs'):
            return url.rstrip('/') + '/logs'
    return url


def _parse_build_url(url):
    """
    Extract (base_url, tenant, build_uuid, buildset_uuid) from a Zuul build or buildset URL.
    Build: .../build/<uuid> or .../build/<uuid>/logs -> build_uuid set, buildset_uuid None.
    Buildset: .../buildset/<uuid> or .../buildset/<uuid>/logs -> buildset_uuid set, build_uuid None.
    """
    parsed = urllib.parse.urlparse(url)
    base = '{}://{}'.format(parsed.scheme or 'https', parsed.netloc or '')
    path = (parsed.path or '').strip('/')
    parts = path.split('/')
    tenant = None
    build_uuid = None
    buildset_uuid = None
    for i, p in enumerate(parts):
        if p == 't' and i + 1 < len(parts):
            tenant = parts[i + 1]
        if p == 'build' and i + 1 < len(parts):
            build_uuid = parts[i + 1]
            break
        if p == 'buildset' and i + 1 < len(parts):
            buildset_uuid = parts[i + 1]
            break
    return (base, tenant, build_uuid, buildset_uuid)


def _is_psi_style_host(host):
    """True if this looks like PSI/Red Hat Zuul (needs Kerberos + download-zuul-logs.sh)."""
    if not host:
        return False
    h = host.lower()
    return ('psi.redhat.com' in h or 'sf.apps' in h) and ('redhat' in h or 'gpc' in h)


def _psi_logs_base_and_script_url(host, tenant, build_uuid, use_https=True):
    """
    Build PSI-style logs base URL and download script URL.
    Pattern: https://host/logs/<uuid_first3>/<tenant>/<uuid>/ and .../download-zuul-logs.sh
    """
    if not tenant or not build_uuid:
        return (None, None)
    scheme = 'https' if use_https else 'http'
    prefix = build_uuid[:3]  # e.g. 65a
    base = '{}://{}/logs/{}/{}/{}'.format(scheme, host, prefix, tenant, build_uuid)
    script_url = base + '/download-zuul-logs.sh'
    return (base + '/', script_url)


def _build_api_url(base_url, tenant, build_uuid):
    """Build Zuul REST API URL for build info: GET /api/tenant/{tenant}/build/{uuid}"""
    if not tenant or not build_uuid:
        return None
    # Some Zuul UIs use /zuul at base; API might be at same host at /zuul/api or /api
    base = base_url.rstrip('/')
    for prefix in [base + '/api', base.replace('/zuul', '') + '/zuul/api', base]:
        url = '{}/tenant/{}/build/{}'.format(prefix, tenant, build_uuid)
        yield url


def _fetch_url(url, method='GET', timeout=FETCH_TIMEOUT):
    """Fetch URL; return (bytes_content, content_type_header, error_str). On success error_str is None."""
    req = urllib.request.Request(url, method=method)
    req.add_header('User-Agent', USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get('Content-Type', '')
            return (resp.read(), ct, None)
    except urllib.error.HTTPError as e:
        return (None, None, 'HTTP {} {}'.format(e.code, e.reason))
    except urllib.error.URLError as e:
        return (None, None, 'URL error: {}'.format(e.reason or type(e).__name__))
    except OSError as e:
        return (None, None, 'OS error: {}'.format(e))


def _is_html_content_type(ct):
    return ct and 'text/html' in ct.split(';')[0].lower()


def _links_from_html(html_bytes, base_url):
    """Parse HTML and return list of (href, resolved_url) for all http(s) links (including cross-origin)."""
    class LinkParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() != 'a':
                return
            for k, v in attrs:
                if k.lower() == 'href' and v:
                    v = v.strip()
                    if not v or any(skip.search(v) for skip in SKIP_PATTERNS):
                        continue
                    try:
                        resolved = urllib.parse.urljoin(base_url, v)
                    except Exception:
                        continue
                    parsed = urllib.parse.urlparse(resolved)
                    if parsed.scheme not in ('http', 'https'):
                        continue
                    self.links.append((v, resolved))
                    break

    try:
        text = html_bytes.decode('utf-8', errors='replace')
        parser = LinkParser()
        parser.feed(text)
        return parser.links
    except Exception:
        return []


def _path_from_url(url, base_url):
    """Return a relative path to save the file under (same-origin: strip base path)."""
    base_parsed = urllib.parse.urlparse(base_url)
    parsed = urllib.parse.urlparse(url)
    base_path = (base_parsed.path or '/').rstrip('/')
    path = (parsed.path or '').strip('/')
    if not path:
        return None
    if base_path and path.startswith(base_path):
        path = path[len(base_path):].lstrip('/')
    return path.split('?')[0].split('#')[0] or None


def _local_path_for_url(url, base_url):
    """Return a safe relative path for saving url. Cross-origin -> external/<netloc>/<path>."""
    base_parsed = urllib.parse.urlparse(base_url)
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc and parsed.netloc != base_parsed.netloc:
        # Cross-origin: save under external/<host>/<path>
        safe_host = (parsed.netloc or 'unknown').replace(':', '_').replace('/', '_')
        path = (parsed.path or '').strip('/')
        path = path.split('?')[0].split('#')[0]
        return 'external/{}/{}'.format(safe_host, path or 'index.html')
    rel = _path_from_url(url, base_url)
    if not rel:
        rel = (parsed.path or '').strip('/').split('/')[-1].split('?')[0] or 'index.html'
    return rel


def _safe_local_path(rel_path):
    """Build a safe local path; avoid path traversal."""
    if not rel_path:
        return None
    parts = []
    for p in rel_path.replace('\\', '/').split('/'):
        if p in ('', '.'):
            continue
        if p == '..':
            if parts:
                parts.pop()
            continue
        parts.append(p)
    return os.path.join(*parts) if parts else None


def _download_file(url, local_path, timeout=FETCH_TIMEOUT):
    """Download url to local_path. Return True on success."""
    data, _, _ = _fetch_url(url, timeout=timeout)
    if data is None:
        return False
    try:
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(data)
        return True
    except OSError:
        return False


def _crawl_and_download(base_url, out_dir, visited_urls, depth=0, _cyan='\033[36m', _green='\033[32m', _dim='\033[2m'):
    """
    Fetch base_url. If HTML directory listing, recurse into same-path links.
    Otherwise treat as file and download to out_dir preserving path.
    visited_urls: set of URLs we already fetched (avoid loops).
    Returns (files_saved_count, dirs_entered_count).
    """
    if depth > MAX_DEPTH:
        return (0, 0)
    base_url_norm = base_url.rstrip('/')
    if base_url_norm in visited_urls:
        return (0, 0)
    visited_urls.add(base_url_norm)

    data, content_type, fetch_err = _fetch_url(base_url_norm)
    if data is None:
        if depth == 0:
            print(common.c(_dim, '  Could not fetch page (check URL, network, or login).'))
            if fetch_err:
                print(common.c(_dim, '  Reason: {}').format(fetch_err))
            print(common.c(_dim, '  URL tried: {}').format(base_url_norm))
        return (0, 0)

    if _is_html_content_type(content_type):
        links = _links_from_html(data, base_url_norm)
        files_saved = 0
        dirs_entered = 0
        if not links and depth == 0:
            print(common.c(_dim, '  No links found in page (may require login or load via JavaScript).'))
        # For each link: fetch once; if HTML recurse, else save as file (handles dirs without trailing /)
        for _href, resolved in links:
            resolved = resolved.rstrip('/')
            if resolved in visited_urls:
                continue
            rel = _local_path_for_url(resolved, base_url_norm)
            if not rel:
                continue
            local_path = _safe_local_path(rel)
            if not local_path:
                continue
            full_local = os.path.join(out_dir, local_path)
            link_data, link_ct, _ = _fetch_url(resolved)
            if link_data is None:
                continue
            if _is_html_content_type(link_ct):
                nf, nd = _crawl_and_download(
                    resolved,
                    out_dir,
                    visited_urls,
                    depth + 1,
                    _cyan,
                    _green,
                    _dim,
                )
                files_saved += nf
                dirs_entered += nd + 1
            else:
                try:
                    os.makedirs(os.path.dirname(full_local) or '.', exist_ok=True)
                    with open(full_local, 'wb') as f:
                        f.write(link_data)
                    files_saved += 1
                    print(common.c(_green, '  saved: ') + common.c(_dim, local_path))
                except OSError:
                    pass
        return (files_saved, dirs_entered)
    else:
        # Treat as single file
        rel = _path_from_url(base_url_norm, base_url_norm)
        if not rel:
            # Use last path segment as filename
            rel = base_url_norm.split('/')[-1].split('?')[0] or 'index.html'
        local_path = _safe_local_path(rel)
        if not local_path:
            return (0, 0)
        full_local = os.path.join(out_dir, local_path)
        if _download_file(base_url_norm, full_local):
            print(common.c(_green, '  saved: ') + common.c(_dim, local_path))
            return (1, 0)
        return (0, 0)


def _try_api_download(base_url, tenant, build_uuid, out_dir, _cyan, _green, _dim):
    """
    Try to get build info from Zuul API; if success, download log_url and artifacts.
    Returns number of files downloaded, or 0 if API not used.
    """
    import json
    for api_url in _build_api_url(base_url, tenant, build_uuid):
        data, _, _ = _fetch_url(api_url)
        if not data:
            continue
        try:
            build = json.loads(data.decode('utf-8'))
        except Exception:
            continue
        count = 0
        log_url = build.get('log_url')
        if log_url:
            # log_url might be a container/directory URL; try to download as-is first
            name = 'job-output.txt'
            if log_url.rstrip('/').split('/')[-1]:
                name = log_url.rstrip('/').split('/')[-1]
            local = os.path.join(out_dir, name)
            if _download_file(log_url, local):
                count += 1
                print(common.c(_green, '  saved (log_url): ') + common.c(_dim, name))
        for art in build.get('artifacts') or []:
            url = art.get('url')
            name = art.get('name') or url.split('/')[-1].split('?')[0] or 'artifact'
            if not url:
                continue
            local = os.path.join(out_dir, _safe_local_path(name) or name)
            if _download_file(url, local):
                count += 1
                print(common.c(_green, '  saved (artifact): ') + common.c(_dim, name))
        if count > 0:
            return count
    return 0


def _psi_get_cookies(out_dir):
    """
    Run Kerberos (kinit) and curl auth.redhat.com to obtain cookies. Write to out_dir/.zuul_cookies.
    Returns (True, path) on success, (False, None) on failure.
    """
    cookies_path = os.path.join(out_dir, '.zuul_cookies')
    try:
        open(cookies_path, 'a').close()
    except OSError:
        return (False, None)
    try:
        r = subprocess.run(['klist', '-s'], capture_output=True, timeout=10)
        if r.returncode != 0:
            subprocess.run(['kinit'], timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return (False, None)
    try:
        r = subprocess.run([
            'curl', '--fail', '-s', '--negotiate', '-u', ':',
            '-b', cookies_path, '-c', cookies_path, '-L',
            PSI_AUTH_URL, '-o', os.devnull,
        ], cwd=out_dir, timeout=30, capture_output=True)
        if r.returncode != 0:
            return (False, None)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return (False, None)
    return (True, cookies_path)


def _fetch_buildset_builds(host, tenant, buildset_uuid, cookies_path):
    """
    GET Zuul API buildset details and return list of build UUIDs. Uses cookies for PSI auth.
    Returns [] on failure or if no builds.
    """
    url = 'https://{}/zuul/api/tenant/{}/buildset/{}'.format(host, tenant, buildset_uuid)
    try:
        r = subprocess.run([
            'curl', '-s', '-S', '-b', cookies_path, '-c', cookies_path, '-L', url,
        ], timeout=30, capture_output=True)
        if r.returncode != 0 or not r.stdout:
            return []
        data = json.loads(r.stdout.decode('utf-8', errors='replace'))
        builds = data.get('builds') if isinstance(data, dict) else None
        if not builds:
            return []
        return [b.get('uuid') for b in builds if b.get('uuid')]
    except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired):
        return []


def _run_psi_download(host, tenant, build_uuid, out_dir, _cyan, _green, _dim, cookies_path=None):
    """
    PSI/Red Hat flow: kinit + cookies (or use cookies_path if provided), pip install,
    download-zuul-logs.py, then wget tempest/ and tobiko/. Returns (success, file_count).
    """
    scheme = 'https'
    api_base = '{}://{}/zuul/api'.format(scheme, host)
    logs_base, _ = _psi_logs_base_and_script_url(host, tenant, build_uuid)
    if not logs_base:
        return (False, 0)
    if cookies_path is None or not os.path.isfile(cookies_path):
        cookies_path = os.path.join(out_dir, '.zuul_cookies')
        open(cookies_path, 'a').close()
        do_auth = True
    else:
        do_auth = False

    if do_auth:
        # 1) Kerberos: klist -s || kinit
        print(common.c(_dim, '  Checking Kerberos (klist -s || kinit)...'))
        try:
            r = subprocess.run(['klist', '-s'], capture_output=True, timeout=10)
            if r.returncode != 0:
                subprocess.run(['kinit'], timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            print(common.c(_dim, '  Kerberos check failed: {}').format(e))
            return (False, 0)

        # 2) Get cookies via auth.redhat.com
        print(common.c(_dim, '  Getting cookies (curl --negotiate auth.redhat.com)...'))
        try:
            r = subprocess.run([
                'curl', '--fail', '-s', '--negotiate', '-u', ':',
                '-b', cookies_path, '-c', cookies_path, '-L',
                PSI_AUTH_URL, '-o', os.devnull,
            ], cwd=out_dir, timeout=30, capture_output=True)
            if r.returncode != 0 and r.stderr:
                print(common.c(_dim, '  Auth failed: {}').format(r.stderr.decode('utf-8', errors='replace')[:200]))
                return (False, 0)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            print(common.c(_dim, '  curl auth failed: {}').format(e))
            return (False, 0)

    # 3) Pip install requirements for download-zuul-logs.py (ci-framework-tools)
    req_url = getattr(config, 'ZUUL_PSI_REQUIREMENTS_URL', '')
    if req_url:
        print(common.c(_dim, '  Installing deps (pip install -r ci-framework-tools/requirements.txt)...'))
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-q', '-r', req_url],
                timeout=120, capture_output=True,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # 4) Download and run download-zuul-logs.py from GitLab (same as official script)
    script_url = getattr(config, 'ZUUL_PSI_SCRIPT_URL', '')
    if not script_url:
        return (False, 0)
    script_path = os.path.join(out_dir, 'download-zuul-logs.py')
    print(common.c(_dim, '  Fetching download-zuul-logs.py and running it...'))
    try:
        r = subprocess.run([
            'curl', '-s', '-L', '-b', cookies_path, '-c', cookies_path,
            '-o', script_path, script_url,
        ], timeout=60, capture_output=True)
        if r.returncode == 0 and os.path.isfile(script_path):
            r2 = subprocess.run([
                sys.executable, script_path,
                '--api', api_base,
                '--tenant', tenant,
                '--build-id', build_uuid,
                '--download-dir', os.path.abspath(out_dir),
            ], timeout=PSI_SCRIPT_TIMEOUT, capture_output=True)
            if r2.returncode != 0 and r2.stderr:
                print(common.c(_dim, '  download-zuul-logs.py stderr: {}').format(
                    r2.stderr.decode('utf-8', errors='replace')[:400]))
            try:
                os.remove(script_path)
            except OSError:
                pass
    except (subprocess.TimeoutExpired, OSError):
        pass

    # 5) Supplement: wget tempest/ and tobiko/ into job dir (official script often omits these)
    # Script may create out_dir/<build_id>/ or put files directly in out_dir; find where job-output.txt landed
    job_root = out_dir
    for _root, _dirs, filenames in os.walk(out_dir):
        if 'job-output.txt' in filenames:
            job_root = _root
            break
    print(common.c(_dim, '  Fetching tempest/ and tobiko/ into job dir (often missing from script)...'))
    for sub in ('tempest', 'tobiko'):
        sub_url = logs_base + sub + '/'
        try:
            subprocess.run([
                'wget', '--load-cookies', cookies_path,
                '-r', '-l', '5', '-np', '-nH', '--cut-dirs=5', '-q',
                '-P', os.path.abspath(job_root),
                sub_url,
            ], timeout=120, capture_output=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    try:
        n = sum(1 for _root, _dirs, files in os.walk(out_dir) for _ in files)
    except OSError:
        n = 0
    return (True, n)


def run_zuul_download(url_in):
    """
    Download logs from a Zuul job logs page URL. Returns the output directory path (str).
    Used by zuul_job_analyze when user provides a URL.
    """
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    url_in = _normalize_zuul_url(url_in)
    base_url, tenant, build_uuid, buildset_uuid = _parse_build_url(url_in)
    out_base = getattr(config, 'ZUUL_DOWNLOAD_DIR', None) or os.path.join(config.BASE_DIR, 'zuul_downloaded')
    if build_uuid:
        out_dir = os.path.join(out_base, build_uuid[:8] + '_' + time_module.strftime('%Y%m%d_%H%M%S'))
    elif buildset_uuid:
        out_dir = os.path.join(out_base, 'buildset_' + buildset_uuid[:8] + '_' + time_module.strftime('%Y%m%d_%H%M%S'))
    else:
        out_dir = os.path.join(out_base, 'zuul_' + time_module.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(out_dir, exist_ok=True)
    print(common.c(_GREEN, 'Downloading to: ') + common.c(_CYAN, out_dir))
    print()

    start = time_module.time()
    total = 0
    parsed = urllib.parse.urlparse(url_in)
    host = parsed.netloc or ''

    # (1a) PSI buildset: get cookies, fetch build list, download each build into a subdir
    if _is_psi_style_host(host) and tenant and buildset_uuid:
        print(common.c(_CYAN, 'PSI buildset URL: resolving builds then downloading each...'))
        ok, cookies_path = _psi_get_cookies(out_dir)
        if not ok or not cookies_path:
            print(common.c(_DIM, '  Could not get cookies (kinit + auth.redhat.com).'))
        else:
            build_uuids = _fetch_buildset_builds(host, tenant, buildset_uuid, cookies_path)
            if not build_uuids:
                print(common.c(_DIM, '  Could not fetch buildset build list (API returned no builds).'))
            else:
                print(common.c(_GREEN, '  Buildset has {} build(s).').format(len(build_uuids)))
                for i, buid in enumerate(build_uuids):
                    subdir = os.path.join(out_dir, buid[:8] + '_' + str(i + 1))
                    os.makedirs(subdir, exist_ok=True)
                    print(common.c(_CYAN, '  [{}] {}...').format(i + 1, buid[:8]))
                    psi_ok, psi_count = _run_psi_download(host, tenant, buid, subdir, _CYAN, _GREEN, _DIM, cookies_path=cookies_path)
                    if psi_ok and psi_count > 0:
                        total += psi_count
                        print(common.c(_GREEN, '      {} file(s).').format(psi_count))

    # (1b) PSI single build: Kerberos + download-zuul-logs + wget tempest/tobiko
    elif _is_psi_style_host(host) and tenant and build_uuid:
        print(common.c(_CYAN, 'PSI/Red Hat URL detected: Kerberos + download script + tempest/tobiko...'))
        psi_ok, psi_count = _run_psi_download(host, tenant, build_uuid, out_dir, _CYAN, _GREEN, _DIM)
        if psi_ok and psi_count > 0:
            total = psi_count
            print(common.c(_GREEN, '  Downloaded {} file(s).').format(psi_count))

    if total == 0:
        if _is_psi_style_host(host) and tenant and not build_uuid and not buildset_uuid:
            print(common.c(_DIM, '  PSI URL but could not parse tenant/build or buildset.'))
        # (2) Try Zuul build API (single build only)
        api_count = _try_api_download(base_url, tenant, build_uuid, out_dir, _CYAN, _GREEN, _DIM)
        total = api_count
        if api_count > 0:
            print(common.c(_DIM, '  (downloaded {} file(s) from API)').format(api_count))
        # (3) Python scrape
        print(common.c(_CYAN, 'Scraping logs page for links...'))
        visited = set()
        n_files, _n_dirs = _crawl_and_download(url_in.rstrip('/'), out_dir, visited, 0, _CYAN, _GREEN, _DIM)
        total += n_files

    elapsed = time_module.time() - start
    print(common.c(_GREEN, 'Downloaded {} file(s) in {:.1f}s.').format(total, elapsed))
    print()
    return out_dir


def main():
    _CYAN = '\033[36m'
    _GREEN = '\033[32m'
    _YELLOW = '\033[33m'
    _DIM = '\033[2m'

    print(common.c(_CYAN, 'Zuul logs download — paste the job URL (base URL is fine, /logs is added if missing)'))
    print(common.c(_DIM, 'Example: https://.../zuul/t/components-integration/build/<uuid>'))
    print()
    try:
        url_in = input(common.c(_DIM, 'Zuul logs URL: ')).strip()
    except EOFError:
        print(common.c(_YELLOW, 'No input. Exiting.'))
        sys.exit(1)
    if not url_in:
        print(common.c(_YELLOW, 'Empty URL. Exiting.'))
        sys.exit(1)

    out_dir = run_zuul_download(url_in)
    print(common.c(_DIM, 'Run mode 6 (Analyze Zuul job) on path: ') + common.c(_CYAN, out_dir))


if __name__ == '__main__':
    main()
