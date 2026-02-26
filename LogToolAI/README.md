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
| **analyze_local_logs.py** | Mode: analyze logs in a local directory (stub for future implementation). |

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
- **2)** Analyze logs in local directory (not implemented yet)
- **0)** Exit

You can also run the pod-logs mode directly:

```bash
python3 collect_and_analyze_pod_logs.py
```

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

To use the script’s AI filtering, Ollama must be running on a host reachable from where you run the script (e.g. `http://<server>:11434`). Below: run Ollama with **Podman** on a remote server, pull models, and verify.

### 1. Run Ollama with Podman

On the **remote server** (RHEL/Fedora or similar with Podman):

```bash
# Create a volume for model data (persists across container restarts)
podman volume create ollama-data

# Run Ollama (CPU). Expose port 11434 so the script can call the API.
podman run -d \
  --name ollama \
  -v ollama-data:/root/.ollama \
  -p 11434:11434 \
  ollama/ollama
```

To listen on all interfaces (for access from other hosts), bind to `0.0.0.0`:

```bash
podman run -d \
  --name ollama \
  -v ollama-data:/root/.ollama \
  -p 0.0.0.0:11434:11434 \
  ollama/ollama
```

**With NVIDIA GPU:**

```bash
podman run -d \
  --name ollama \
  --gpus=all \
  -v ollama-data:/root/.ollama \
  -p 0.0.0.0:11434:11434 \
  ollama/ollama
```

### 2. Pull models

Containers start with no models. Pull one or more from inside the container:

```bash
# List already pulled models
podman exec -it ollama ollama list

# Pull a model (examples)
podman exec -it ollama ollama pull llama3.2
podman exec -it ollama ollama pull llama3.1:8b
podman exec -it ollama ollama pull mistral
```

To pull several in one go:

```bash
for model in llama3.2 llama3.1:8b mistral; do
  podman exec ollama ollama pull "$model"
done
```

Browse [Ollama Library](https://ollama.com/library) for model names. There is no single “install all” command; choose the models you need.

### 3. Verify Ollama is up and running

From the **same server**:

```bash
# Health / API
curl -s http://localhost:11434/api/tags
```

You should get JSON with a `"models"` array (possibly empty before any pull). Example:

```json
{"models":[{"name":"llama3.2","model":"...","size":...}]}
```

From **another host** (e.g. where you run the script), replace `localhost` with the server’s IP or hostname:

```bash
curl -s http://<SERVER_IP>:11434/api/tags
```

Then in the script set:

```python
OLLAMA_HOST = 'http://<SERVER_IP>:11434'
```

(Or leave the default if it already points to your server.)

### 4. Restart and persistence

- **Restart container:** `podman restart ollama`
- **Start after reboot:** Run the `podman run` command above with your preferred options, or use a systemd unit (e.g. Quadlet) to start the container on boot. Models stay in the `ollama-data` volume.

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
