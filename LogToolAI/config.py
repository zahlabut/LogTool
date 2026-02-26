# LogToolAI configuration.
# Edit this file to change paths, Ollama settings, error keywords, and other parameters.

import os

# Base directory for the tool (where config.py lives). Paths below are relative to this.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Paths & output ---
LOGS_DIR = os.path.join(BASE_DIR, 'collected_pod_logs')
REPORT_FILE = os.path.join(BASE_DIR, 'pod_logs_error_report.txt')

# --- Concurrency ---
MAX_WORKERS = 16

# --- Error detection (grep) ---
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
    'AnsibleUndefinedVariable', 'failed=', 'changed=false', 'skipping:',
    'UpgradeFailed', 'ResolutionFailed', 'ReconcileError', 'reconcile error',
    'ClusterOperator', 'ClusterVersion', 'Available=False', 'Failing', 'RetryExhausted',
    'BareMetalHost', 'provisioning error', 'power on failed', 'registration error', 'BMO ',
    'drain failed', 'pivot failed', 'machineconfig', 'MCO ',
    'CreateContainerError', 'FailedScheduling', 'InvalidImageName', 'NodeNotReady',
    'SandboxChanged', 'CreateContainerConfigError', 'PLEG', 'container runtime',
    'x509', 'TLS handshake', 'certificate', 'authentication failed', 'forbidden', 'token invalid',
    'blob unknown', 'manifest unknown', 'image pull failed',
    'etcd corrupt', 'leader election failed', 'raft ',
    'playbook failed', 'PLAY RECAP', 'TASK [', 'ok=0 ', 'ignored=',
    'host validation failed', 'insufficient', 'pending input', 'infra-env',
    'CNI failed', 'network not ready', 'backend down', 'reload failed',
    'scrape error', 'target down', 'rule evaluation failed',
    'level=error', ' ERRO ', 'no logs from conmon', 'container create failed',
    'failed to start container', 'oci runtime error', 'conmon failed', 'runc failed',
    'FailedMount', 'MountVolume', 'attach volume failed', 'Volume not attached',
    'ProgressDeadlineExceeded', 'BackoffLimitExceeded', 'Build failed',
    'disk pressure', 'memory pressure', 'pid pressure',
    'avc: denied', 'selinux',
    'context deadline exceeded', 'Too Many Requests', 'upstream connect error',
    'SyncError', 'sync failed', 'out of sync',
    'PipelineRun failed', 'TaskRun failed', 'Step failed', 'pipeline has failed',
    'Zuul job failed', 'job failed', 'workflow failed',
    'panic:', 'fatal error:', 'goroutine ', 'runtime error', 'runtime:',
    'nil pointer', 'index out of range', 'interface conversion',
    'recovered from panic', 'exit status ',
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
OLLAMA_TIMEOUT = 300
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

# --- Local directory mode (analyze_local_logs) ---
# Report file when analyzing logs in a user-provided local directory.
LOCAL_LOG_REPORT_FILE = os.path.join(BASE_DIR, 'local_logs_error_report.txt')

# --- Extract logs by time range (extract_logs_time_range) ---
# Base directory for extracted log runs; a timestamped subdir is created each run.
EXTRACTED_LOGS_BASE_DIR = os.path.join(BASE_DIR, 'extracted_logs')

# --- Display ---
NO_COLOR = False
