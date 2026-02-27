# LogToolAI configuration.
# Edit this file to change paths, Ollama settings, error keywords, and other parameters.

import os

# Base directory for the tool (where config.py lives). Paths below are relative to this.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Paths & output ---
LOGS_DIR = os.path.join(BASE_DIR, 'collected_pod_logs')
REPORT_FILE = os.path.join(BASE_DIR, 'pod_logs_error_report.txt')
REPORT_HTML = os.path.join(BASE_DIR, 'pod_logs_error_report.html')

# --- Concurrency ---
MAX_WORKERS = 16

# --- Error detection (grep) ---
# Avoid broad terms that match normal output: e.g. 'TASK [', 'skipping:', 'ignored=',
# 'ClusterOperator', 'BMO ', 'MCO ', 'certificate', 'selinux', 'recovered from panic'.
ERROR_KEYWORDS = [
    ' ERROR ', ' CRITICAL ', ' FATAL ', ' STDERR ', ' FAILED ', '|ERR|', ' failure ', ' failure:',
    ' Traceback ', 'Traceback (most recent', ' Exception', 'Exception:', 'Error:', 'Error ',
    'SyntaxError', 'RuntimeError', 'ImportError', 'AttributeError', 'KeyError', 'ValueError',
    'TypeError', 'NameError', 'IndexError', 'OSError', 'UnicodeError', 'UnboundLocalError',
    'ModuleNotFoundError', 'FileNotFoundError', 'ConnectionError', 'TimeoutError',
    'AssertionError', 'ZeroDivisionError', 'RecursionError', 'IndentationError',
    'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull', 'OOMKilled', 'Evicted',
    'LivenessProbeFailure', 'ReadinessProbeFailure', 'Back-off ',
    'Degraded', ' Unhealthy ', 'Error syncing', 'EXCEPTION', 'ABORT', 'DENIED', 'UNAUTHORIZED',
    'QUOTA_EXCEEDED', 'Resource exhausted', 'Rate limit', 'Connection refused',
    'ValidationError', 'NotFound', 'Malformed', 'Conflict',
    ' fatal: ', 'FATAL:', ' ERROR! ', ' unreachable', 'task failed', 'AnsibleError',
    'AnsibleUndefinedVariable', 'failed=', 'changed=false',
    'UpgradeFailed', 'ResolutionFailed', 'ReconcileError', 'reconcile error',
    'Available=False', 'Failing', 'RetryExhausted',
    'provisioning error', 'power on failed', 'registration error',
    'drain failed', 'pivot failed',
    'CreateContainerError', 'FailedScheduling', 'InvalidImageName', 'NodeNotReady',
    'SandboxChanged', 'CreateContainerConfigError', 'PLEG', 'container runtime',
    'x509', 'TLS handshake', 'authentication failed', 'forbidden', 'token invalid',
    'blob unknown', 'manifest unknown', 'image pull failed',
    'etcd corrupt', 'leader election failed',
    'playbook failed', 'PLAY RECAP', 'ok=0 ',
    'host validation failed', 'insufficient', 'pending input',
    'CNI failed', 'network not ready', 'backend down', 'reload failed',
    'scrape error', 'target down', 'rule evaluation failed',
    'level=error', ' ERRO ', 'no logs from conmon', 'container create failed',
    'failed to start container', 'oci runtime error', 'conmon failed', 'runc failed',
    'FailedMount', 'MountVolume', 'attach volume failed', 'Volume not attached',
    'ProgressDeadlineExceeded', 'BackoffLimitExceeded', 'Build failed',
    'disk pressure', 'memory pressure', 'pid pressure',
    'avc: denied',
    'context deadline exceeded', 'Too Many Requests', 'upstream connect error',
    'SyncError', 'sync failed', 'out of sync',
    'PipelineRun failed', 'TaskRun failed', 'Step failed', 'pipeline has failed',
    'Zuul job failed', 'job failed', 'workflow failed',
    'panic:', 'fatal error:', 'goroutine ', 'runtime error', 'runtime:',
    'nil pointer', 'index out of range', 'interface conversion',
    'exit status ',
]
CONTEXT_BEFORE = 3
CONTEXT_AFTER = 7
SINGLE_LINE_CONTEXT_BEFORE = 3
SINGLE_LINE_CONTEXT_AFTER = 3

# --- Deduplication & report layout ---
FUZZY_MATCH_RATIO = 0.55
LINE_SIMILARITY_COLLAPSE = 0.90
SIGNATURE_LEN = 1200
MAX_BLOCK_LINES_SHOWN = 9
BLOCK_TRUNCATE_HEAD = 3
BLOCK_TRUNCATE_TAIL = 3

# --- AI filter (Ollama) ---
OLLAMA_HOST = 'http://10.9.95.129:11434'
OLLAMA_CHECK_TIMEOUT = 5
AI_MAX_BLOCK_CHARS = 900
OLLAMA_MODEL = ''
# Seconds to wait for Ollama response. Large prompts (e.g. extract-mode summary with 50k chars) or 70B models may need 900–1800.
OLLAMA_TIMEOUT = 1800
OLLAMA_MAX_PREDICT = 320
OLLAMA_MAX_PREDICT_DETAILED = 450
AI_MAX_EXPLANATION_CHARS = 8000
OLLAMA_MAX_CONCURRENT = 6
OLLAMA_DEBUG = True

# --- Must-gather (for must_gather_analyze mode) ---
# Directory for must-gather output. A timestamped subdir will be created each run.
MUST_GATHER_BASE_DIR = os.path.join(BASE_DIR, 'must_gather_output')
# Must-gather image. Empty = default OpenShift image. For RHOSO/OpenStack use e.g.:
# MUST_GATHER_IMAGE = 'quay.io/openstack-k8s-operators/openstack-must-gather'
# or registry.redhat.io/rhoso-operators/openstack-must-gather-rhel9
MUST_GATHER_IMAGE = ''
# Report file for must-gather analysis (default: next to REPORT_FILE).
MUST_GATHER_REPORT_FILE = os.path.join(BASE_DIR, 'must_gather_error_report.txt')
MUST_GATHER_REPORT_HTML = os.path.join(BASE_DIR, 'must_gather_error_report.html')

# --- Local directory mode (analyze_local_logs) ---
# Report file when analyzing logs in a user-provided local directory.
LOCAL_LOG_REPORT_FILE = os.path.join(BASE_DIR, 'local_logs_error_report.txt')
LOCAL_LOG_REPORT_HTML = os.path.join(BASE_DIR, 'local_logs_error_report.html')

# --- Extract logs by time range (extract_logs_time_range) ---
# Base directory for extracted log runs; a timestamped subdir is created each run.
EXTRACTED_LOGS_BASE_DIR = os.path.join(BASE_DIR, 'extracted_logs')
# Max characters of combined log content to send to Ollama for summary (0 = no limit; very large may time out).
EXTRACT_OLLAMA_MAX_CHARS = 50000
# Max tokens for Ollama summary response.
EXTRACT_OLLAMA_MAX_PREDICT = 1024

# --- Zuul job analysis (zuul_job_analyze) ---
# Report files when analyzing Zuul job logs (local directory).
ZUUL_JOB_REPORT_FILE = os.path.join(BASE_DIR, 'zuul_job_analysis_report.txt')
# HTML report (main report with links to console, tempest, deployment sections).
ZUUL_JOB_REPORT_HTML = os.path.join(BASE_DIR, 'zuul_job_analysis_report.html')
# Base directory for downloaded Zuul logs (zuul_logs_download.py); each run creates a subdir.
ZUUL_DOWNLOAD_DIR = os.path.join(BASE_DIR, 'zuul_downloaded')
# PSI/Red Hat: ci-framework-tools GitLab (download-zuul-logs.py). Script is run with --api, --tenant, --build-id, --download-dir.
ZUUL_PSI_REQUIREMENTS_URL = 'https://gitlab.cee.redhat.com/ci-framework/ci-framework-tools/-/raw/main/download/requirements.txt'
ZUUL_PSI_SCRIPT_URL = 'https://gitlab.cee.redhat.com/ci-framework/ci-framework-tools/-/raw/main/download/download-zuul-logs.py'
# --- Report HTML: log viewer (link to original log at line) ---
# Number of lines before/after each error block to include in the "view in log" viewer HTML.
REPORT_VIEWER_CONTEXT_LINES = 80

# --- Display ---
NO_COLOR = False
