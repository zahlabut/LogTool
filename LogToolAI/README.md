# LogToolAI — Log analysis tool (OpenShift pod logs, local directory, etc.)

Tool with multiple modes. The main mode **analyzes OpenShift pod logs**: collects logs via `oc`, greps for error-like content, optionally uses a **remote Ollama** server to classify each unique block as “real error” or not, and writes a readable report.

**Target:** RHOSO (Red Hat OpenStack on OpenShift) and similar OpenShift environments. Run on a host where `oc` is installed and you are logged in to the cluster.

---

## Structure

| File | Purpose |
|------|--------|
| **LogToolMain.py** | Main entry: asks which mode to run, then calls the chosen script. |
| **config.py** | All configurable parameters (paths, Ollama URL/timeout, error keywords, concurrency, etc.). Edit this file to change behavior. |
| **logtool_common.py** | Shared code used by modes: run(), colors, Ollama API, block extraction, report helpers. Imported by mode scripts. |
| **collect_and_analyze_pod_logs.py** | Mode: analyze OpenShift pod logs (grep + optional Ollama). Can be run from main or directly. |
| **must_gather_analyze.py** | Mode: run `oc adm must-gather`, discover log files in the output, group by component, then same analysis (grep + optional Ollama) and report. |
| **analyze_local_logs.py** | Mode: analyze logs in a user-provided local directory (recursive .log/.txt), same pipeline as pod/must-gather: baseline, since, grep, optional Ollama, report. |
| **rhoso_versions.py** | Mode: show RHOSO (OpenStack) version, Octavia OVN provider version, and Designate version (read-only, colorized output). |
| **extract_logs_time_range.py** | Mode: extract pod logs for a time range + Ollama summary; grouped by component; writes logs (colorized) to a dedicated folder; sends combined logs to Ollama to summarize what processes ran and whether they succeeded or errored. |
| **install_ollama_podman.sh** | Optional: run on the Ollama host to install Ollama with Podman, pull models, and verify. |

---

## Requirements

- **Python 3**
- **OpenShift CLI (`oc`)** — logged in, with permission to run `oc get pods -A` and `oc logs <pod> -n <namespace>`
- **Optional:** A reachable Ollama server (HTTP) for AI-based filtering and explanations. If `OLLAMA_HOST` is unset or the server is unreachable, the script skips the AI step and still produces a grep-based report.

---

## Installation

No system-wide install. Use the script from the `LogToolAI` directory.

1. Clone or copy the repo and go to the script directory:
   ```bash
   cd /path/to/LogTool/LogToolAI
   ```

2. (Optional) Use a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Linux/macOS; Windows: .venv\Scripts\activate
   ```

3. Run the script (see [Usage](#usage)). No `pip install` is required; the script uses the Python standard library only.

---

## Usage

**Recommended:** run the main script and choose a mode:

```bash
python3 LogToolMain.py
```

Then select:
- **1)** Analyze OpenShift pod logs (grep + optional Ollama)
- **2)** Run must-gather, then analyze collected logs (grep + optional Ollama)
- **3)** Analyze logs in local directory (path → discover, baseline, since, grep + Ollama, report)
- **4)** Show RHOSO / Octavia / Designate versions
- **5)** Extract pod logs for time range + Ollama summary (processes, success/errors)
- **0)** Exit

You can also run the pod-logs mode directly:

```bash
python3 collect_and_analyze_pod_logs.py
```

**Mode 3 (local directory):** Run `python3 analyze_local_logs.py` or choose **3** from the main menu. You are prompted for a directory path; the tool recursively finds all `.log` and `.txt` files, groups by subfolder, then runs the same pipeline as must-gather: baseline timestamp, “since” choice (2h/1h/30m/custom), threaded block extraction, optional Ollama filter, and report to `local_logs_error_report.txt` (configurable via `LOCAL_LOG_REPORT_FILE`). No `oc` required.

**Mode 4 (versions):** Run `python3 rhoso_versions.py` or choose **4** from the main menu. The script runs `oc get openstackversion -A`, finds an Octavia API pod and execs `rpm -qa | grep ovn-octavia`, and finds a Designate pod and execs `rpm -qa | grep designate`, then prints a short colorized summary. No log collection or reports; requires `oc` and permission to exec into pods.

**Mode 5 (extract logs + Ollama summary):** Run `python3 extract_logs_time_range.py` or choose **5** from the main menu. Pod logs only: same grouping by component as mode 1, then baseline and time range (2h/1h/30m/custom). Fetches `oc logs --since-time` for each selected pod and writes log files into `extracted_logs/extracted_YYYYMMDD_HHMMSS/` with error keywords **colorized**. If Ollama is available, the combined log content (truncated to `EXTRACT_OLLAMA_MAX_CHARS`) is sent with a prompt asking: what processes or operations do you see, and did they complete successfully or raise errors? The reply is printed and saved as `ollama_summary.txt` in the same folder. Config: `EXTRACTED_LOGS_BASE_DIR`, `EXTRACT_OLLAMA_MAX_CHARS`, `EXTRACT_OLLAMA_MAX_PREDICT`.

The pod-logs mode is interactive:

1. **Pod list** — Fetches all pods (`oc get pods -A`), groups them by component, and asks you to choose a group or “all pods”.
2. **Baseline timestamp** — Reads the latest log line from pods to infer “now”; then asks how far back to analyze (e.g. 2h, 1h, 30m, or custom minutes).
3. **Collect logs** — Runs `oc logs` for each selected pod since the chosen time and saves raw logs under `collected_pod_logs/` (path is configurable).
4. **Analyze** — Greps logs for error-related phrases (see [Error detection](#error-detection)), groups matches into blocks with context, fuzzy-dedupes blocks, and optionally sends each unique block to Ollama for “real error? + short explanation”. If Ollama is enabled and no model is set in the script, it lists models on the server and lets you pick one (with a note that smaller models are faster, larger more accurate but slower).
5. **Report** — Writes `pod_logs_error_report.txt` with unique error blocks, optional Ollama explanations, and counts. View with:
   ```bash
   less -R pod_logs_error_report.txt
   ```

Edit **config.py** (not the script) for:
- **Paths:** `LOGS_DIR`, `REPORT_FILE`
- **Concurrency:** `MAX_WORKERS`, `OLLAMA_MAX_CONCURRENT`
- **Ollama:** `OLLAMA_HOST` (default `http://10.9.95.129:11434`; set to `''` to disable), `OLLAMA_MODEL` (empty = interactive model choice or auto-pick), `OLLAMA_TIMEOUT`, `OLLAMA_DEBUG`, etc.
- **Error detection:** `ERROR_KEYWORDS`, `CONTEXT_BEFORE`, `CONTEXT_AFTER`, `FUZZY_MATCH_RATIO`, etc.
- **Must-gather mode:** `MUST_GATHER_BASE_DIR`, `MUST_GATHER_IMAGE` (empty = default OpenShift image; for RHOSO set to the OpenStack must-gather image), `MUST_GATHER_REPORT_FILE`.
- **Local directory mode:** `LOCAL_LOG_REPORT_FILE` (report path when analyzing a user-provided folder).
- **Extract logs by time range:** `EXTRACTED_LOGS_BASE_DIR`, `EXTRACT_OLLAMA_MAX_CHARS` (max log chars sent to Ollama), `EXTRACT_OLLAMA_MAX_PREDICT` (max summary length).

---

## Logic (high level)

- **Collection:** For each selected pod, `oc logs --timestamps` since the user-chosen time → one file per pod in `LOGS_DIR`.
- **Blocks:** Each log line is checked for any of the `ERROR_KEYWORDS` (grep -F -i). A “block” is the matching line plus `CONTEXT_BEFORE`/`CONTEXT_AFTER` lines. Blocks are filtered by a “since” time derived from the baseline and your choice.
- **Deduplication:** Blocks are turned into text signatures; signatures that are fuzzy-similar (ratio ≥ `FUZZY_MATCH_RATIO`) are treated as one. One representative block per signature is kept for the report.
- **Ollama (optional):** If `OLLAMA_HOST` is set and reachable, the script sends each unique block (truncated to `AI_MAX_BLOCK_CHARS`) to Ollama with a prompt: “Is this a real error? Reply YES/NO and if YES give a short explanation.” Blocks marked NO are dropped from the report; for YES, the explanation is included. If `OLLAMA_MODEL` is empty, the script lists models on the server and lets you choose (or auto-picks the largest when not interactive).
- **Report:** For each kept block: file, line range, block text (with error phrases highlighted in ANSI red for `less -R`), optional “Ollama — not from log” explanation, and occurrence count.

All behaviour is controlled by **config.py** (paths, `OLLAMA_HOST`, `OLLAMA_MODEL`, `ERROR_KEYWORDS`, timeouts, etc.). No environment variables are used.

---

## Error detection

Error blocks are found by **grep -F -i** over a list of phrases in `ERROR_KEYWORDS`. The list includes (among others):

- Generic: `ERROR`, `CRITICAL`, `FATAL`, `FAILED`, `Traceback`, `Exception`, `Error:`, common Python exception names.
- Kubernetes/OpenShift: `CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`, `Evicted`, `LivenessProbeFailure`, `ReadinessProbeFailure`, `Degraded`, `Unhealthy`, `FailedScheduling`, `CreateContainerError`, etc.
- Ansible: `fatal:`, `task failed`, `AnsibleError`, `failed=`, `playbook failed`, `PLAY RECAP`, `TASK [`, etc.
- RHOSO: operators (e.g. `ReconcileError`, `UpgradeFailed`), bare metal, MCO, auth/certs, registry, etcd, GitOps, CI-framework/Tekton/Zuul.
- Podman/container runtime: `level=error`, `ERRO`, `container create failed`, `oci runtime error`, etc.
- Go: `panic:`, `fatal error:`, `goroutine`, `runtime error`, `nil pointer`, `index out of range`, etc.
- Storage, node pressure, SELinux, timeouts, and others.

You can extend or trim `ERROR_KEYWORDS` in the script to match your environment.

---

## Installing Ollama on a remote server (Podman)

To use the tool's AI filtering, Ollama must be running on a host reachable from where you run LogToolAI (e.g. `http://<server>:11434`). You can either run the automated script or install manually.

---

### Option A: Automated script (recommended)

On the **host where Ollama should run** (RHEL/Fedora or similar with Podman installed):

```bash
cd /path/to/LogTool/LogToolAI
chmod +x install_ollama_podman.sh
./install_ollama_podman.sh
```

The script will:

- Create a Podman volume and run the Ollama container (port 11434, bound to all interfaces).
- Wait for Ollama to be ready, then pull a default small model (e.g. `llama3.2:1b`).
- Verify with `curl http://localhost:11434/api/tags`.

**Optional environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_GPU` | (unset) | Set to `1` to use NVIDIA GPU: `OLLAMA_GPU=1 ./install_ollama_podman.sh` |
| `OLLAMA_MODELS` | `llama3.2:1b` | Space-separated list of models to pull, e.g. `OLLAMA_MODELS="llama3.2 mistral" ./install_ollama_podman.sh` |
| `OLLAMA_PORT` | `11434` | Host port to expose. |

Then set `OLLAMA_HOST` in **config.py** to `http://<this-server-ip>:11434` (or leave the default if you run LogToolAI on the same host).

---

### Option B: Manual install

On the **remote server** (with Podman):

**1. Run Ollama (CPU, all interfaces):**

```bash
podman volume create ollama-data
podman run -d \
  --name ollama \
  -v ollama-data:/root/.ollama \
  -p 0.0.0.0:11434:11434 \
  ollama/ollama
```

**With NVIDIA GPU:** add `--gpus=all` to the `podman run` command.

**2. Pull models:**

```bash
podman exec ollama ollama pull llama3.2:1b
# or: podman exec ollama ollama list   then   podman exec ollama ollama pull <model>
```

**3. Verify:**

```bash
curl -s http://localhost:11434/api/tags
```

You should see JSON with a `"models"` array. From another host, use `http://<SERVER_IP>:11434` and set `OLLAMA_HOST` in **config.py** to that URL.

**4. Restart / persistence:** `podman restart ollama`. Models persist in the `ollama-data` volume. Use a systemd unit (e.g. Quadlet) to start the container on boot if needed.

---

## Report output

- **Path:** `pod_logs_error_report.txt` by default (override with `REPORT_FILE` in the script).
- **Content:** Section “Pod logs error report”, then for each unique error block: log file, line numbers, block text (ANSI-highlighted), optional Ollama explanation, and count of similar occurrences.
- **View:** `less -R pod_logs_error_report.txt` so ANSI colors display correctly.

---

## Files and directories (defaults)

| Item | Default |
|------|--------|
| Collected logs | `LogToolAI/collected_pod_logs/` |
| Report file | `LogToolAI/pod_logs_error_report.txt` |

Both are under `config.BASE_DIR` and can be changed in **config.py**.
