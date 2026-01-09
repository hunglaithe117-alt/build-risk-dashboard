# Dataset Enrichment Pipeline - Mô Tả Chi Tiết Toàn Bộ Luồng

## 📋 Mục Lục
1. [Tổng Quan Kiến Trúc](#tổng-quan-kiến-trúc)
2. [Phase 1: Validation](#phase-1-validation)
3. [Phase 2: Ingestion](#phase-2-ingestion)
4. [Phase 3: Processing](#phase-3-processing)
5. [Scan Metrics Integration](#scan-metrics-integration)
6. [API Endpoints](#api-endpoints)
7. [Frontend UI Flow](#frontend-ui-flow)
8. [Entities & Data Model](#entities--data-model)
9. [Error Handling & Recovery](#error-handling--recovery)
10. [Performance Optimization](#performance-optimization)

---

## Tổng Quan Kiến Trúc

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATASET ENRICHMENT PIPELINE                  │
└─────────────────────────────────────────────────────────────────────┘

User Upload CSV
       │
       ▼
┌──────────────────────────────────────┐
│  PHASE 1: VALIDATION (dataset_validation.py)
│  ✓ Validate repos trên GitHub API
│  ✓ Validate builds trên CI API
│  ✓ Apply build filters
│  ✓ Cache RawRepository & RawBuildRun
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  PHASE 2: INGESTION (enrichment_ingestion.py)
│  ✓ Clone/update git repositories
│  ✓ Create git worktrees cho commits
│  ✓ Download build logs từ CI
│  ✓ Fork commit replay (nếu cần)
│  ✓ Per-resource status tracking
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  PHASE 3: PROCESSING (enrichment_processing.py)
│  ├─ Async: Dispatch scans (Trivy, SonarQube)
│  └─ Sequential: Extract features (oldest → newest)
│      ├─ Hamilton DAG computation
│      ├─ Backfill scan metrics
│      └─ Temporal features support
└──────────────────────────────────────┘
       │
       ▼
DatasetVersion (Enriched) + Scan Metrics
```

### Queue Architecture

```
┌────────────────────────┐
│  Celery Queue System   │
├────────────────────────┤
│ validation     │ Validation tasks
│ ingestion      │ Clone, worktree, logs
│ trivy_scan     │ Trivy security scans
│ sonar_scan     │ SonarQube code quality
│ processing     │ Feature extraction, aggregation
└────────────────────────┘
```

---

## Phase 1: Validation

**File**: [backend/app/tasks/dataset_validation.py](backend/app/tasks/dataset_validation.py)

**Mục đích**: Xác minh tất cả repos và builds từ CSV thực sự tồn tại và có thể truy cập

### 1.1 Tasks Overview

| Task | Queue | Timeout | Retries | Mô Tả |
|------|-------|---------|---------|-------|
| `dataset_validation_orchestrator` | validation | 3660s | N/A | Đọc CSV chunks, dispatch workers |
| `validate_repo_chunk` | validation | 660s | N/A | Validate batch repos qua GitHub API |
| `validate_builds_chunk` | validation | 360s | N/A | Validate batch builds qua CI API |
| `aggregate_validation_results` | validation | 360s | N/A | Tổng hợp results (chord callback) |

### 1.2 Validation Flow Diagram

```
dataset_validation_orchestrator
│
├─ Read CSV in chunks (SCAN_BUILDS_PER_QUERY=1000)
│
├─ For each chunk:
│     ├─ validate_repo_chunk (parallel)
│     │   ├─ Check repo exists trên GitHub
│     │   ├─ Cache RawRepository
│     │   ├─ Check repo is not private (unless authorized)
│     │   └─ Create DatasetRepoStats (ci_provider, status)
│     │
│     └─ validate_builds_chunk (parallel per repo)
│         ├─ Fetch build data từ CI provider (GitHub Actions, CircleCI, Travis)
│         ├─ Apply build filters:
│         │   - status (success, failure, etc.)
│         │   - event_type (push, pull_request, etc.)
│         │   - branch_patterns (regex)
│         ├─ Cache RawBuildRun
│         ├─ Create DatasetBuild (if not exists)
│         └─ Mark as FOUND (if CI returned data)
│
└─ aggregate_validation_results (chord callback)
    ├─ Collect validation stats
    ├─ Update Dataset.validation_status → READY
    └─ Publish WebSocket event to frontend
```

### 1.3 Build Filters

Các filter được apply trong validation phase:

```python
# From DatasetBuild entity
build_filters = {
    "status": ["success", "failure"],  # Only these statuses
    "event_types": ["push", "pull_request"],
    "branch_patterns": ["main", "develop", "release-*"]
}

# In validate_builds_chunk:
should_filter = should_filter_build(build_data)
if should_filter:
    build.status = "filtered"  # Không include trong enrichment
else:
    build.status = "found"
```

### 1.4 Data Structures Created

**DatasetBuild** (per CSV row):
```python
{
    dataset_id: ObjectId,
    build_id_from_csv: str,
    status: "found" | "not_found" | "filtered",
    raw_repo_id: ObjectId,      # Cache từ validation
    raw_run_id: ObjectId,        # Cache từ validation
    ci_provider: str,            # GitHub Actions, CircleCI, etc.
}
```

**RawRepository** (cache):
```python
{
    full_name: "owner/repo",
    github_repo_id: int,
    is_private: bool,
    ci_provider: str,
}
```

**RawBuildRun** (cache):
```python
{
    raw_repo_id: ObjectId,
    build_id_from_csv: str,
    ci_run_id: str,
    commit_sha: str,
    effective_sha: str,  # Updated if fork commit replay
    created_at: datetime,
    ci_provider: str,
}
```

**DatasetRepoStats**:
```python
{
    dataset_id: ObjectId,
    raw_repo_id: ObjectId,
    ci_provider: str,
    total_builds: int,
    found_builds: int,
    not_found_builds: int,
    filtered_builds: int,
}
```

### 1.5 Progress & Error Handling

- **Progress**: Publish tới Redis + WebSocket cho frontend
- **Timeouts**: Soft time limit + error callback
- **Chunking**: MapReduce pattern với aggregation

---

## Phase 2: Ingestion

**File**: [backend/app/tasks/enrichment_ingestion.py](backend/app/tasks/enrichment_ingestion.py)

**Mục đích**: Thu thập tất cả resources cần thiết cho feature extraction

### 2.1 Concepts Chính

#### 2.1.1 DatasetImportBuild Status Flow

```
                     ┌─ INGESTING ─┐
                     │             │
PENDING ─────────────┤             ├─── INGESTED
                     │             │
                     └─ ERROR ─────┘
                          │
                          ▼
                  MISSING_RESOURCE (graceful)
```

- **PENDING**: Chờ ingestion
- **INGESTING**: Đang clone, worktree, download logs
- **INGESTED**: Tất cả required resources đã sẵn sàng
- **MISSING_RESOURCE**: Một số resources bị lỗi nhưng vẫn có thể process (graceful degradation)

#### 2.1.2 Resource DAG

```
clone_repo (git bare clone)
    │
    ├─ create_worktrees (requires clone_repo)
    │
    └─ download_build_logs (parallel, independent)
```

**Task Dependencies**:
```python
TASK_DEPENDENCIES = {
    "clone_repo": [],
    "create_worktrees": ["clone_repo"],
    "download_build_logs": [],
}
```

#### 2.1.3 Dynamic Resource Calculation

Resources được tính từ `selected_features`:

```python
# Từ feature_dag/_metadata.py
required_resources = get_required_resources_for_features(feature_set)

# Ví dụ:
# Nếu selected_features = ["build_logs_duration", "git_diff_lines"]
# → required_resources = {"build_logs", "git_worktree"}

# Nếu có scan metrics → FORCE git_worktree (needed for scans)
if has_sonarqube or has_trivy:
    required_resources.add("git_worktree")
```

### 2.2 Tasks Overview

| Task | Queue | Timeout | Retries | Mô Tả |
|------|-------|---------|---------|-------|
| `start_enrichment` | processing | 180s | N/A | Orchestrator: build chains, dispatch chord |
| `clone_repo` | ingestion | 660s | 3 | Clone/update bare git repo |
| `create_worktree_chunk` | ingestion | 660s | 2 | Create worktrees cho commits (sequential) |
| `download_logs_chunk` | ingestion | 300s | 2 | Download logs từ CI (parallel chunks) |
| `aggregate_ingestion_results` | processing | 60s | N/A | Aggregate results (chord callback) |
| `aggregate_logs_results` | ingestion | 120s | N/A | Aggregate log chunk results (chord callback) |
| `reingest_failed_builds` | processing | 360s | N/A | Retry FAILED builds (not MISSING_RESOURCE) |

### 2.3 Ingestion Workflow Diagram

```
start_enrichment
│
├─ Validate version exists
├─ Create DatasetImportBuild records (one per validated build)
├─ Get required resources from feature selection
│
└─ Build & dispatch CHORD:
    │
    ├─ GROUP of CHAINS (parallel repos):
    │   │
    │   ├─ Repo 1: chain(clone_repo → create_worktrees → download_logs)
    │   ├─ Repo 2: chain(clone_repo → create_worktrees → download_logs)
    │   └─ Repo N: chain(clone_repo → create_worktrees → download_logs)
    │
    └─ CALLBACK: aggregate_ingestion_results
        │
        ├─ Parse results from all repos
        ├─ Update per-resource status in DatasetImportBuild
        ├─ Mark builds as INGESTED or MISSING_RESOURCE
        ├─ Publish WebSocket event
        └─ User can now start Phase 3 processing
```

### 2.4 Per-Resource Status Tracking

```python
# In DatasetImportBuild entity
resource_status = {
    "git_history": {
        "status": "completed|failed|pending|skipped",
        "error": "optional error message",
        "started_at": datetime,
        "completed_at": datetime,
    },
    "git_worktree": {
        "status": "completed",
        "error": None,
        ...
    },
    "build_logs": {
        "status": "failed",
        "error": "Log expired on CI provider",
        ...
    }
}
```

**Status Update Logic**:
1. Clone fails → ALL builds: git_history = FAILED
2. Worktree fails for commit X → Builds with commit X: git_worktree = FAILED
3. Log download fails for build Y → Build Y: build_logs = FAILED

### 2.5 Clone Repository Task

**File**: [backend/app/tasks/shared/ingestion_tasks.py](backend/app/tasks/shared/ingestion_tasks.py)

```python
clone_repo(
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    correlation_id: str,
)
```

**Flow**:
1. Acquire Redis lock (repo-level) - prevent concurrent clones
2. Check if repo already cloned → use git fetch --all --prune
3. If not cloned → git clone --bare (bare repo for efficiency)
4. For org repos (configured GITHUB_INSTALLATION_ID):
   - Get installation token từ GitHub App
   - Use token authentication (higher rate limits)
5. Timeout 600s, max retries 3

**Result**:
```python
{
    "resource": "git_history",
    "status": "cloned|failed|timeout",
    "path": "/data/repos/<github_repo_id>.git",
    "error": "optional error message",
}
```

### 2.6 Worktree Creation Task

**File**: [backend/app/tasks/shared/ingestion_tasks.py](backend/app/tasks/shared/ingestion_tasks.py)

```python
create_worktree_chunk(
    raw_repo_id: str,
    github_repo_id: int,
    commit_shas: List[str],  # Chunk of commits
    chunk_index: int,
    total_chunks: int,
    correlation_id: str,
)
```

**Flow**:
1. For each commit in chunk:
   - Check if worktree already exists → skip
   - Check if commit exists locally: `git cat-file -e <sha>`
   - If not exists locally → Fork commit replay (special handling)
   - Create worktree: `git worktree add --detach <path> <sha>`
2. Return with created/skipped/failed counts
3. Timeout 600s, max retries 2 (due to fork replay complexity)

#### Fork Commit Replay
Xử lý commits từ fork PRs mà không có trong base repo:

```
Scenario: User creates PR từ fork, commit SHA không trong base repo

1. _commit_exists_locally(repo_path, sha) → False
2. ensure_commit_exists(repo_path, commit_sha, repo_slug, github_client)
   ├─ Fetch patch từ GitHub API
   ├─ Apply patch lên base repo
   ├─ Create synthetic commit
   └─ Return synthetic_sha (có thể khác original)
3. Update RawBuildRun.effective_sha = synthetic_sha
4. Create worktree sử dụng synthetic_sha
```

**Result**:
```python
{
    "resource": "git_worktree",
    "chunk_index": 0,
    "worktrees_created": 150,
    "worktrees_skipped": 50,
    "worktrees_failed": 5,
    "fork_commits_replayed": 3,
    "failed_commits": ["abc123", ...],
    "created_commits": ["def456", ...],
}
```

### 2.7 Log Download Task

**File**: [backend/app/tasks/shared/ingestion_tasks.py](backend/app/tasks/shared/ingestion_tasks.py)

```python
download_logs_chunk(
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    build_ids: List[str],  # Chunk of builds
    ci_provider: str,
    chunk_index: int,
    total_chunks: int,
    correlation_id: str,
)
```

**Flow**:
1. Fetch build details từ CI provider (async/concurrent)
2. For each build:
   - Check if logs already exist locally
   - Download logs từ CI API
   - Parse logs (extract durations, errors, stages)
   - Save to: `/data/repos/<github_repo_id>/logs/<ci_run_id>/`
3. Return with downloaded/skipped/failed counts
4. Timeout 300s, max retries 2

**Log Aggregation** (chord callback):
```python
aggregate_logs_results(
    chunk_results: List[Dict],
)
```

Tổng hợp results từ tất cả parallel chunks.

**Result**:
```python
{
    "resource": "build_logs",
    "chunk_index": 0,
    "logs_downloaded": 500,
    "logs_skipped": 100,
    "logs_failed": 20,
    "expired_log_ids": ["build_5", ...],  # Expired on CI
    "failed_log_ids": ["build_6", ...],
}
```

### 2.8 Aggregation Logic

**aggregate_ingestion_results** (chord callback):

```python
def aggregate_ingestion_results(
    results: List[Dict],
    version_id: str,
    correlation_id: str,
):
    # Parse results từ tất cả ingestion chains
    clone_failed = check_if_clone_failed(results)
    failed_commits = collect_failed_commits(results)
    failed_log_ids = collect_failed_logs(results)
    
    # Update per-resource status cho tất cả builds
    if clone_failed:
        # Tất cả builds: git_history = FAILED
        update_resource_status_batch(
            version_id,
            "git_history",
            ResourceStatus.FAILED,
            error_msg
        )
    else:
        # Tất cả builds: git_history = COMPLETED
        update_resource_status_batch(
            version_id,
            "git_history",
            ResourceStatus.COMPLETED
        )
    
    # Worktree failures
    if failed_commits:
        # Only builds with these commits: git_worktree = FAILED
        update_resource_by_commits(
            version_id,
            "git_worktree",
            failed_commits,
            ResourceStatus.FAILED
        )
    
    # Log failures
    if failed_log_ids:
        # Only these builds: build_logs = FAILED
        update_resource_by_build_ids(
            version_id,
            "build_logs",
            failed_log_ids,
            ResourceStatus.FAILED
        )
    
    # Mark final status
    if clone_failed:
        # All builds cannot proceed
        mark_all_as(version_id, MISSING_RESOURCE)
    else:
        # Mark by resource status
        if has_failed_resources:
            mark_as_missing_resource(version_id)
        else:
            mark_as_ingested(version_id)
    
    # Publish event
    publish_enrichment_update(version_id, "ingested")
```

### 2.9 Graceful Degradation

**Design Philosophy**: "Bất kỳ build nào cũng có thể được processed, ngay cả thiếu resources"

- Build có tất cả resources → Extract tất cả features
- Build missing git_worktree → Không thể extract git_diff features, nhưng vẫn có log features
- Build missing build_logs → Không thể extract log features, nhưng vẫn có git features
- Build missing git_history → Chỉ có metadata features

**Matching Model Pipeline**: Cùng design pattern với model_pipeline

### 2.10 Retry Failed Builds

**reingest_failed_builds** task:

```python
def reingest_failed_builds(version_id: str):
    # Find FAILED builds (retryable - actual errors like timeout, network)
    # Does NOT retry MISSING_RESOURCE (not retryable - logs expired)
    failed = find_by_status(version_id, FAILED)
    
    # Reset them to PENDING, clear error fields
    for build in failed:
        update_status(build.id, PENDING)
        clear_error_fields(build.id)
    
    # Re-trigger ingestion
    start_enrichment.delay(version_id)
```

Cho phép user thử lại ingestion cho builds có transient errors (timeout, network).

---

## Phase 3: Processing

**File**: [backend/app/tasks/enrichment_processing.py](backend/app/tasks/enrichment_processing.py)

**Mục đích**: Extract features từ ingested resources + backfill scan metrics

### 3.1 Overview

```
User manually triggers start_enrichment_processing
    │
    ├─ Validate version status = INGESTED
    │
    └─ dispatch_scans_and_processing
        ├─ dispatch_version_scans (async, fire & forget)
        │   └─ Scan only unique commits (once per version)
        │
        └─ dispatch_enrichment_batches (sequential)
            └─ chain(B1 → B2 → ... → Bn → finalize)
```

### 3.2 Why Sequential Processing?

**Temporal Features**: Một số features phụ thuộc vào builds trước đó:

```
build_history_failure_rate = (failures_in_last_N_builds / N)
author_commit_count = tổng commits từ author tính đến build này
build_duration_trend = xu hướng thời gian build qua các builds
```

Nếu build N fail → tất cả builds sau đó sẽ có temporal features không chính xác!

**Solution**: Process tuần tự từ cũ → mới:
```
1. B1 (oldest) → complete → update DB
2. B2 → use B1's results → complete → update DB
3. B3 → use B1, B2's results → complete
...
n. Bn (newest) → use all previous → complete
n+1. finalize_enrichment → aggregate from DB
```

### 3.3 Tasks Overview

| Task | Queue | Timeout | Mô Tả |
|------|-------|---------|-------|
| `start_enrichment_processing` | processing | 120s | User entry point, validate status |
| `dispatch_scans_and_processing` | processing | 60s | Dispatch scans async + processing sequential |
| `dispatch_version_scans` | processing | 600s | Paginate builds, collect unique commits, dispatch scans |
| `dispatch_scan_for_commit` | processing | 120s | Dispatch Trivy + SonarQube cho 1 commit |
| `dispatch_enrichment_batches` | processing | 180s | Create enrichment builds, dispatch chain |
| `process_single_enrichment` | processing | 600s | Extract features cho 1 build (sequential) |
| `finalize_enrichment` | processing | 60s | Aggregate results, mark completed |
| `reprocess_failed_enrichment_builds` | processing | 360s | Retry failed builds |
| `process_version_export_job` | processing | 900s | Export version thành CSV/JSON |
| `start_trivy_scan_for_version_commit` | trivy_scan | 900s | Run Trivy CLI scan |
| `start_sonar_scan_for_version_commit` | sonar_scan | 2100s | Submit SonarQube scan |
| `export_metrics_from_webhook` | processing | 180s | Handle SonarQube webhook callback |

### 3.4 Feature Extraction Pipeline

**extract_features_for_build** (shared helper):

```python
result = extract_features_for_build(
    db=db,
    raw_repo=raw_repo,
    feature_config=dataset_version.feature_configs,
    raw_build_run=raw_build_run,
    selected_features=selected_features,
    output_build_id=enrichment_build_id,
    category=AuditLogCategory.DATASET_ENRICHMENT,
)

# Returns:
{
    "status": "completed|partial|failed",
    "feature_vector_id": ObjectId,
    "feature_count": int,
    "errors": List[str],
}
```

**Hamilton DAG Execution**:

```python
# From hamilton_runner.py
pipeline = HamiltonPipeline(...)

# Inputs (prepared by input_preparer.py):
inputs = {
    "repo": raw_repo,
    "build_run": raw_build_run,
    "feature_config": feature_config,
    "git_history": git_history_obj,        # if available
    "git_worktree": git_worktree_obj,      # if available
    "build_logs": build_logs_obj,          # if available
    "raw_build_runs": collection,          # for temporal features
    "feature_vectors": collection,         # for temporal features
}

# Execute
features = pipeline.execute(
    selected_features=selected_features,
    inputs=inputs,
    config=feature_config,
)

# Store in FeatureVector (single source of truth)
feature_vector = FeatureVectorRepository.upsert(
    build_id=raw_build_run.id,
    version_id=version_id,
    features=features,
    category=AuditLogCategory.DATASET_ENRICHMENT,
)
```

**Feature Categories** (from _metadata.py):
- BUILD_LOG: Duration, status, stages
- GIT_HISTORY: Commits, authors, deletions
- GIT_DIFF: Lines changed, complexity
- REPO_SNAPSHOT: Language, stars, watchers
- PR_INFO: Title, description, comments
- DISCUSSION: Comments, reviews
- TEAM: Authors, reviewers
- METADATA: Timestamp, build number
- WORKFLOW: Triggers, matrix builds
- DEVOPS: DevOps files (GitHub Actions, etc.)
- BUILD_HISTORY: Previous build features
- COMMITTER: Commit author experience
- COOPERATION: Distinct authors, revisions

### 3.5 Scan Metrics Integration

#### 3.5.1 Trivy Vulnerability Scanning

**File**: [backend/app/tasks/trivy.py](backend/app/tasks/trivy.py)

```
dispatch_scan_for_commit
    └─ dispatch_scan_for_commit.delay(
        version_id, raw_repo_id, github_repo_id,
        commit_sha, repo_full_name
    )
        └─ start_trivy_scan_for_version_commit
            ├─ Create/get TrivyCommitScan record
            ├─ Get worktree path từ github_repo_id + commit_sha
            ├─ Run TrivyTool.scan(target_path, scan_types, config_file)
            │   └─ Trivy CLI: --format json --server mode hoặc standalone
            ├─ Parse metrics (vuln_total, critical, high, medium, low)
            ├─ Filter metrics based on selected_metrics config
            ├─ Backfill to FeatureVector.scan_metrics:
            │   {
            │       "trivy_vuln_total": 42,
            │       "trivy_vuln_critical": 3,
            │       "trivy_vuln_high": 8,
            │       "trivy_scan_duration_ms": 1250,
            │   }
            │   (via DatasetEnrichmentBuild → FeatureVector reference)
            ├─ Mark TrivyCommitScan as COMPLETED
            └─ Return results
```

**Trivy Config**:
```python
trivy_config = {
    "scanners": ["vuln", "config", "secret"],  # default
    "trivyYaml": "...",  # Custom config content
    "extraArgs": "--severity HIGH,CRITICAL",
}

# Per-repo override:
scan_config = {
    "repos": {
        "12345": {  # github_repo_id
            "scanners": ["vuln"],
            "trivyYaml": "...",
        }
    },
    # default for other repos
    "scanners": ["vuln", "config"],
}
```

#### 3.5.2 SonarQube Code Quality Analysis

**File**: [backend/app/tasks/sonar.py](backend/app/tasks/sonar.py)

```
dispatch_scan_for_commit
    └─ start_sonar_scan_for_version_commit
        ├─ Create/get SonarCommitScan record
        ├─ Generate component_key = "<version>_<repo>_<commit>"
        ├─ Run sonar-scanner CLI:
        │   sonar-scanner \
        │     -Dsonar.projectKey=<component_key> \
        │     -Dsonar.sources=. \
        │     ...
        ├─ Mark SonarCommitScan as SCANNING
        └─ Return (don't wait for results)

Then (async, via webhook):
        ├─ SonarQube completes analysis...
        │
        └─ SonarQube → POST /api/webhook/sonarqube
                       ├─ export_metrics_from_webhook
                       │   ├─ Find SonarCommitScan by component_key
                       │   ├─ Fetch metrics từ SonarQube API
                       │   │   (blocks, duplicates, complexity, coverage)
                       │   ├─ Filter by selected_metrics
                       │   ├─ Backfill to FeatureVector.scan_metrics:
                       │   │   {
                       │   │       "sonar_bugs": 5,
                       │   │       "sonar_code_smells": 12,
                       │   │       "sonar_coverage": 75.5,
                       │   │       "sonar_complexity": 42,
                       │   │   }
                       │   │   (via DatasetEnrichmentBuild → FeatureVector reference)
                       │   ├─ Mark SonarCommitScan as COMPLETED
                       │   └─ Return results
```

**SonarQube Config**:
```python
sonar_config = {
    "projectKey": "my_project",
    "extraProperties": "sonar.java.coveragePlugin=jacoco",
}

# Per-repo override:
scan_config = {
    "repos": {
        "12345": {
            "projectKey": "my_repo_12345",
            "extraProperties": "...",
        }
    },
    # default
    "projectKey": "default_key",
}
```

#### 3.5.3 Backfill Pattern

Scan results được **backfill** tới tất cả builds có cùng commit:

```python
# In TrivyTool hoặc SonarQube callback
updated_count = enrichment_build_repo.backfill_by_commit_in_version(
    version_id=ObjectId(version_id),
    commit_sha=commit_sha,
    scan_features={
        "vuln_total": 42,
        "vuln_critical": 3,
        ...
    },
    prefix="trivy_",  # Tạo keys như "trivy_vuln_total"
)

# Flow:
# 1. Find all DatasetEnrichmentBuilds with this commit in version
# 2. For each build, get feature_vector_id
# 3. Update FeatureVector.scan_metrics["trivy_vuln_total"] = 42
# 
# Result: All FeatureVectors for builds with this commit get scan metrics
```

#### 3.5.4 Scan Dispatch Strategy

**dispatch_version_scans** (per-commit, not per-build):

```
1. Paginate through all builds in version (SCAN_BUILDS_PER_QUERY=1000)
2. For each page:
   ├─ Batch query RawBuildRuns (fetch commit SHAs)
   ├─ Collect unique (repo_id, commit_sha) pairs
   ├─ If reach SCAN_COMMITS_PER_BATCH=100:
   │   └─ dispatch_scan_batch(batch_100_commits)
   │       └─ group(dispatch_scan_for_commit, ...)
   │
3. Dispatch remaining commits
4. Return stats
```

**Why per-commit**: Tránh duplicate scans nếu nhiều builds có cùng commit

**Why async**: Scans có thể chạy lâu (10-30 phút cho SonarQube), không block feature extraction

### 3.6 Feature Extraction Task

**process_single_enrichment**:

```python
def process_single_enrichment(
    version_id: str,
    enrichment_build_id: str,
    selected_features: List[str],
    correlation_id: str,
):
    # Get entities
    enrichment_build = find_by_id(enrichment_build_id)
    raw_build_run = find_by_id(enrichment_build.raw_build_run_id)
    raw_repo = find_by_id(raw_build_run.raw_repo_id)
    
    # Skip if already processed
    if enrichment_build.extraction_status != PENDING:
        return {"status": "skipped"}
    
    # Extract features
    result = extract_features_for_build(
        db=db,
        raw_repo=raw_repo,
        feature_config=dataset_version.feature_configs,
        raw_build_run=raw_build_run,
        selected_features=selected_features,
        output_build_id=enrichment_build_id,
        category=AuditLogCategory.DATASET_ENRICHMENT,
    )
    
    # Update enrichment build
    enrichment_build_repo.update_one(enrichment_build_id, {
        "feature_vector_id": result["feature_vector_id"],
        "extraction_status": result["status"],  # completed|partial|failed
        "extraction_error": result.get("errors"),
        "enriched_at": datetime.now(),
    })
    
    # Update version progress
    version_repo.increment_builds_features_extracted(version_id)
    
    return {"status": result["status"], "feature_count": result.get("feature_count")}
```

### 3.7 Finalization Task

**finalize_enrichment** (end of sequential chain):

```python
def finalize_enrichment(
    version_id: str,
    created_count: int,
    correlation_id: str,
):
    # Get aggregated stats from DB (no Redis tracker)
    stats = enrichment_build_repo.aggregate_stats_by_version(version_id)
    # {completed: X, partial: Y, failed: Z}
    
    # Determine final status
    if failed > 0 and completed == 0:
        final_status = FAILED
    else:
        final_status = PROCESSED
    
    # Update version with feature_extraction_completed flag
    version_repo.update_one(version_id, {
        "status": final_status,
        "builds_features_extracted": completed + partial,
        "builds_extraction_failed": failed,
        "feature_extraction_completed": True,  # Mark features done
    })
    
    # Auto quality evaluation
    if final_status == PROCESSED:
        quality_service.evaluate_version(version_id)
    
    # Check if enrichment fully complete (features + scans)
    check_and_notify_enrichment_completed(version_id)
    
    # Publish event
    publish_enrichment_update(version_id, final_status, feature_extraction_completed=True)
```

### 3.8 Error Handling

**handle_enrichment_processing_chain_error** (error callback):

```
Chain fails (worker crash, timeout, unhandled exception)
    ├─ Mark all IN_PROGRESS builds as FAILED
    ├─ Count completed vs failed
    ├─ Update version status (PROCESSED if some completed, else FAILED)
    └─ Publish event to frontend
```

**Temporal Feature Integrity**: Nếu build N fail, tất cả builds sau sẽ không có correct temporal features. Design yêu cầu user review và reprocess nếu cần.

### 3.9 Retry Failed Builds

**reprocess_failed_enrichment_builds**:

```python
def reprocess_failed_enrichment_builds(version_id: str):
    # Find FAILED enrichment builds
    failed = find_by_status(version_id, FAILED)
    
    # Reset to PENDING
    for build in failed:
        update_status(build.id, PENDING)
    
    # Dispatch sequential chain again
    # (same as normal processing, but for failed builds only)
    
    # Dispatch chain: B_failed1 → B_failed2 → ... → finalize
```

### 3.10 Export Job

**process_version_export_job**:

```python
def process_version_export_job(job_id: str):
    job = find_by_id(job_id)
    
    # Validate
    assert job.dataset_id and job.version_id
    
    # Get enriched builds cursor (with FeatureVector join)
    cursor = enrichment_build_repo.get_enriched_for_export(
        dataset_id=job.dataset_id,
        version_id=job.version_id,
    )
    # Returns: DatasetEnrichmentBuild joined with FeatureVector
    # Each row contains: build metadata + features + scan_metrics
    
    # Get all feature keys (for CSV headers)
    all_feature_keys = enrichment_build_repo.get_all_feature_keys(...)
    # Includes: FeatureVector.features keys + FeatureVector.scan_metrics keys
    
    # Write CSV or JSON
    if job.format == "csv":
        write_csv_file(
            file_path=EXPORTS_DIR / filename,
            cursor=cursor,
            features=job.features,
            all_feature_keys=all_feature_keys,
            progress_callback=update_progress,
        )
    
    # Mark completed
    job_repo.update_status(job_id, "completed", file_path=file_path)
```

---

## Scan Metrics Integration

### Scan Tools Configuration

#### Trivy Tool

**File**: [backend/app/integrations/tools/trivy/tool.py](backend/app/integrations/tools/trivy/tool.py)

```python
class TrivyTool:
    def scan(
        self,
        target_path: str,
        scan_types: List[str] = None,  # ["vuln", "config", "secret"]
        config_file_path: Path = None,
    ) -> Dict[str, Any]:
        """
        Run Trivy scan on target directory/image.
        
        Returns:
        {
            "status": "success|failed",
            "metrics": {
                "vuln_total": int,
                "vuln_critical": int,
                "vuln_high": int,
                "vuln_medium": int,
                "vuln_low": int,
                "config_issues": int,
                "secret_issues": int,
            },
            "scan_duration_ms": int,
        }
        """
```

**Modes**:
- **Server mode** (recommended): Uses Trivy server via `--server` flag
- **Standalone**: Runs Trivy Docker image directly

**Configuration**:
- Load từ DB settings (SettingsService)
- Fallback to ENV vars (TRIVY_SERVER_URL)
- Custom config file per repo/version

#### SonarQube Tool

**File**: [backend/app/integrations/tools/sonarqube/tool.py](backend/app/integrations/tools/sonarqube/tool.py)

```python
class SonarQubeTool:
    def scan_commit(
        self,
        commit_sha: str,
        full_name: str,
        config_file_path: Path = None,
        shared_worktree_path: str = None,
    ) -> None:
        """
        Initiate SonarQube scan using sonar-scanner CLI.
        
        Results delivered via webhook callback (async).
        Does not wait for completion.
        """
```

**Modes**:
- **Async via webhook**: Submit scan, wait for webhook callback
- Token authentication (from DB settings or ENV)

**Configuration**:
- Load từ DB settings (SettingsService)
- Fallback to ENV vars (SONAR_HOST_URL, SONAR_TOKEN)
- Custom config per repo/version

#### Metrics Exporter

**File**: [backend/app/integrations/tools/sonarqube/exporter.py](backend/app/integrations/tools/sonarqube/exporter.py)

```python
class MetricsExporter:
    def collect_metrics(
        self,
        component_key: str,
        selected_metrics: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch metrics from SonarQube API.
        
        Returns only selected metrics if specified.
        """
```

### Scan Metrics Selection

**In DatasetVersion**:
```python
scan_metrics = {
    "trivy": ["vuln_total", "vuln_critical"],
    "sonarqube": ["bugs", "code_smells", "coverage"],
}

scan_config = {
    "trivy": {
        "scanners": ["vuln"],
        "trivyYaml": "...",
    },
    "sonarqube": {
        "projectKey": "...",
        "extraProperties": "...",
    },
}
```

### Metrics Filtering

```python
# In start_trivy_scan_for_version_commit
filtered_metrics = _filter_trivy_metrics(
    raw_metrics={
        "vuln_total": 42,
        "vuln_critical": 3,
        "config_issues": 5,
        "secret_issues": 0,
    },
    selected_metrics=["vuln_total", "vuln_critical"],
)
# Result: {"vuln_total": 42, "vuln_critical": 3}
```

---

## API Endpoints

**File**: [backend/app/api/dataset_versions.py](backend/app/api/dataset_versions.py)

> [!NOTE]
> Prefix: `/datasets/{dataset_id}/versions`

### Version Management

| Method | Endpoint | Mô Tả |
|--------|----------|-------|
| `GET` | `/` | List versions for a dataset |
| `POST` | `/` | Create new version (triggers validation & ingestion) |
| `GET` | `/{version_id}` | Get version details |
| `DELETE` | `/{version_id}` | Delete version (cascade deletes builds) |

### Ingestion & Processing

| Method | Endpoint | Mô Tả |
|--------|----------|-------|
| `GET` | `/{version_id}/import-builds` | List DatasetImportBuild records |
| `GET` | `/{version_id}/enrichment-builds` | List DatasetEnrichmentBuild records |
| `GET` | `/{version_id}/builds/{build_id}` | Get build detail with features |
| `POST` | `/{version_id}/start-processing` | Start processing phase (requires INGESTED status) |
| `POST` | `/{version_id}/retry-ingestion` | Retry FAILED ingestion builds |
| `POST` | `/{version_id}/retry-processing` | Retry FAILED processing builds |

### Scan Metrics

| Method | Endpoint | Mô Tả |
|--------|----------|-------|
| `GET` | `/{version_id}/scan-status` | Get scan status summary (Trivy/SonarQube) |
| `GET` | `/{version_id}/commit-scans` | List commit scans with pagination |
| `GET` | `/{version_id}/commit-scans/{commit_sha}` | Get scan detail for specific commit |
| `POST` | `/{version_id}/commit-scans/{commit_sha}/retry` | Retry scan for commit (tool_type param) |

### Data & Export

| Method | Endpoint | Mô Tả |
|--------|----------|-------|
| `GET` | `/{version_id}/data` | Get paginated data with column stats |
| `GET` | `/{version_id}/preview` | Preview exportable data |
| `GET` | `/{version_id}/export` | Stream export (CSV/JSON) - small datasets |
| `POST` | `/{version_id}/export/async` | Create async export job - large datasets |
| `GET` | `/{version_id}/export/jobs` | List export jobs |
| `GET` | `/export/jobs/{job_id}` | Get export job status |
| `GET` | `/export/jobs/{job_id}/download` | Download completed export file |

### Quality Evaluation

| Method | Endpoint | Mô Tả |
|--------|----------|-------|
| `POST` | `/{version_id}/evaluate` | Start quality evaluation |
| `GET` | `/{version_id}/quality-report` | Get latest quality report |

---

## Frontend UI Flow

**Files**: [frontend/src/app/(app)/projects/](frontend/src/app/(app)/projects/)

### Page Structure

```
/projects
├── page.tsx                    # Dataset list page
├── layout.tsx                  # Main layout
├── _components/
│   └── StatusBadge.tsx         # Dataset status badge component
├── upload/
│   ├── page.tsx                # CSV upload wizard
│   └── _components/
│       └── ...                 # Upload-related components
└── [datasetId]/
    ├── page.tsx                # Dataset detail (version history)
    ├── layout.tsx              # Dataset layout with tabs
    ├── _components/
    │   ├── CorrelationMatrixModal.tsx
    │   ├── DatasetHeader.tsx
    │   ├── FeatureDistributionModal.tsx
    │   ├── VersionHistory.tsx
    │   ├── VersionHistoryTable.tsx
    │   ├── FeatureSelection/
    │   │   └── ...             # Feature selection components
    │   └── tabs/
    │       └── ...             # Tab components
    ├── builds/
    │   └── page.tsx            # Builds by dataset
    └── versions/
        ├── new/
        │   └── page.tsx        # Create new version wizard
        └── [versionId]/
            ├── layout.tsx      # Version layout with tabs
            ├── page.tsx        # Version dashboard
            ├── _components/
            │   ├── VersionDashboard.tsx
            │   ├── VersionMiniStepper.tsx    # 2-phase stepper (Ingestion → Processing)
            │   ├── VersionIngestionCard.tsx
            │   ├── VersionProcessingCard.tsx
            │   ├── AnalysisSection.tsx
            │   ├── ExportSection.tsx
            │   ├── PreprocessingSection.tsx
            │   ├── ScanMetricsSection.tsx
            │   ├── FeatureDistributionChart.tsx
            │   ├── FeatureDistributionCarousel.tsx
            │   └── CorrelationMatrixChart.tsx
            ├── _hooks/
            │   └── ...                       # Version-related hooks
            ├── builds/
            │   ├── layout.tsx
            │   ├── page.tsx
            │   ├── ingestion/
            │   │   └── page.tsx              # Ingestion builds table
            │   ├── processing/
            │   │   └── page.tsx              # Processing builds table
            │   └── scans/
            │       └── ...                   # Scan results pages
            ├── analysis/
            │   └── page.tsx                  # Feature analysis page
            └── export/
                └── page.tsx                  # Export configuration page
```

### Upload Flow UI

```
Step 1: Upload CSV
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│           ┌───────────────────────────────────┐             │
│           │    📄 Drag & Drop CSV file        │             │
│           │    or click to browse             │             │
│           └───────────────────────────────────┘             │
│                                                              │
│    CSV Format: repo_name, build_id, ...                     │
│                                                              │
│                                               [Next →]       │
└──────────────────────────────────────────────────────────────┘

Step 2: Configure Dataset
┌──────────────────────────────────────────────────────────────┐
│    Dataset Name: [___________________]                       │
│                                                              │
│    Description: [___________________]                        │
│                                                              │
│    Template: [Risk Prediction ▼]                            │
│                                                              │
│                                       [← Back] [Create]      │
└──────────────────────────────────────────────────────────────┘
```

### Version Dashboard Components

```
### Version Dashboard Page (`page.tsx`)
├── VersionMiniStepper     # 2-phase indicator
├── Status Cards Row
│   ├── VersionIngestionCard   # Ingestion stats & controls
│   └── VersionProcessingCard  # Processing stats & scan progress
└── VersionDashboard       # KPI Cards & Charts
    ├── KPI Cards (Builds, Enriched, Quality, Features)
    ├── Build Status Bar
    └── Top Issues List
├── AnalysisSection        # Feature analysis & Scan Metrics
│   ├── Quality Scores (Completeness, Validity, etc.)
│   ├── Scan Metrics (Trivy/SonarQube results)
│   ├── Feature distribution charts
│   ├── Correlation matrix
│   └── Statistics overview

└── ExportSection          # Export configuration
    ├── Format selection (CSV/JSON)
    ├── Feature selection
    └── [Export] button
```

### Version Builds Page

```
VersionBuildsPage (in builds/page.tsx)
├── Tab Navigation
│   ├── Ingestion tab → /builds/ingestion
│   ├── Processing tab → /builds/processing
│   └── Scans tab → /builds/scans
│       ├── Tabs: SonarQube, Trivy
│       └── Components: ScanTable (Commit, Status, Builds, Duration, Actions)

└── Content Area
    ├── IngestionBuildsTable (per-build ingestion status)
    │   ├── Build info (ID, repo, commit)
    │   ├── Resource status (git_history, git_worktree, build_logs)
    │   └── Final status (ingested, missing_resource, failed)
    └── ProcessingBuildsTable (per-build extraction status)
        ├── Build info
        ├── Extraction status
        ├── Feature count
        └── Scan metrics status
```

### Key Differences from Model Pipeline UI

| Aspect | Model Pipeline (repositories) | Dataset Enrichment (projects) |
|--------|------------------------------|-------------------------------|
| Entry Point | Import GitHub repos | Upload CSV file |
| Stepper Phases | 4 phases (Fetch, Ingest, Extract, Predict) | 2 phases (Ingestion, Processing) |
| Prediction | Yes (ML model) | No (feature extraction only) |
| Scan Metrics | No | Yes (Trivy, SonarQube) |
| Feature Analysis | No | Yes (distribution, correlation) |
| Export | Basic | Advanced (preprocessing, format options) |

---

## Entities & Data Model

### Core Entities

#### DatasetVersion
```python
{
    _id: ObjectId,
    dataset_id: ObjectId,
    user_id: ObjectId,
    version_number: int,
    name: str,
    description: str,
    
    # Feature selection
    selected_features: List[str],
    scan_metrics: {
        "sonarqube": List[str],
        "trivy": List[str],
    },
    scan_config: {
        "sonarqube": Dict,
        "trivy": Dict,
    },
    
    # Status & progress (aligned with ModelRepoConfig)
    status: "queued|ingesting|ingested|processing|processed|failed",
    builds_total: int,              # Total builds to process
    builds_ingested: int,           # Successfully ingested builds
    builds_missing_resource: int,   # Builds with missing resources (not retryable)
    builds_ingestion_failed: int,   # Builds that failed ingestion (retryable)
    builds_features_extracted: int,   # Successfully extracted builds
    builds_extraction_failed: int,    # Failed during feature extraction
    # Timestamps
    started_at: datetime,
    completed_at: datetime,
    error_message: str,
    task_id: str,
}
```

#### DatasetImportBuild
```python
{
    _id: ObjectId,
    dataset_version_id: ObjectId,
    dataset_build_id: ObjectId,
    raw_repo_id: ObjectId,
    raw_build_run_id: ObjectId,
    
    # Status
    status: "pending|ingesting|ingested|missing_resource|failed",
    resource_status: {
        "git_history": {"status": "...", "error": "..."},
        "git_worktree": {...},
        "build_logs": {...},
    },
    required_resources: List[str],
    
    # Error tracking
    ingestion_error: str,  # Detailed error message
    
    # Denormalized fields
    ci_run_id: str,
    commit_sha: str,
    repo_full_name: str,
    
    # Tracking
    created_at: datetime,
    updated_at: datetime,
}
```

#### DatasetEnrichmentBuild
```python
{
    _id: ObjectId,
    dataset_version_id: ObjectId,
    dataset_build_id: ObjectId,
    dataset_id: ObjectId,
    raw_repo_id: ObjectId,
    raw_build_run_id: ObjectId,
    
    # ** FEATURE VECTOR REFERENCE (single source of truth) **
    feature_vector_id: ObjectId,  # Points to FeatureVector
    # All features stored in FeatureVector.features
    # All scan metrics stored in FeatureVector.scan_metrics
    
    # Status (mirrored from FeatureVector for quick queries)
    extraction_status: "pending|completed|partial|failed",
    extraction_error: str,
    enriched_at: datetime,
    
    # Tracking
    created_at: datetime,
    updated_at: datetime,
}
```

#### FeatureVector
```python
{
    _id: ObjectId,
    raw_repo_id: ObjectId,
    raw_build_run_id: ObjectId,  # 1:1 relationship (unique)
    
    # Version tracking
    dag_version: str,
    computed_at: datetime,
    
    # Temporal feature chain
    tr_prev_build: str,  # CI run ID of previous build
    
    # Status
    extraction_status: "pending|completed|partial|failed",
    extraction_error: str,
    
    # Graceful degradation
    is_missing_commit: bool,
    missing_resources: List[str],  # ["git_worktree", "build_logs"]
    skipped_features: List[str],   # Features skipped due to missing resources
    
    # ** FEATURES - Hamilton DAG extracted features **
    features: {
        "build_duration_ms": 1250,
        "build_logs_errors_count": 3,
        "git_diff_lines_added": 125,
        "git_diff_lines_deleted": 45,
        "tr_build_history_failure_rate": 0.15,
        "gh_author_commit_count": 42,
        ...
    },
    feature_count: int,
    
    # ** SCAN METRICS - Backfilled asynchronously **
    scan_metrics: {
        "trivy_vuln_total": 42,
        "trivy_vuln_critical": 3,
        "trivy_vuln_high": 8,
        "sonar_bugs": 5,
        "sonar_code_smells": 12,
        "sonar_coverage": 75.5,
        ...
    },
    
    # ** NORMALIZED FEATURES - For model prediction **
    normalized_features: {
        "build_duration_ms_scaled": 0.75,
        "git_diff_lines_scaled": 1.2,
        ...
    },
    
    # Tracking
    created_at: datetime,
    updated_at: datetime,
}
```

#### TrivyCommitScan
```python
{
    _id: ObjectId,
    dataset_version_id: ObjectId,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: ObjectId,
    
    # Status
    status: "pending|scanning|completed|failed",
    error_message: str,
    
    # Config
    scan_config: Dict,
    selected_metrics: List[str],
    
    # Results
    metrics: Dict,
    builds_affected: int,
    
    # Tracking
    started_at: datetime,
    completed_at: datetime,
    created_at: datetime,
    retry_count: int,
}
```

#### SonarCommitScan
```python
{
    _id: ObjectId,
    dataset_version_id: ObjectId,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: ObjectId,
    component_key: str,  # SonarQube project key
    
    # Status
    status: "pending|scanning|completed|failed",
    error_message: str,
    
    # Results
    metrics: Dict,
    builds_affected: int,
    
    # Tracking
    started_at: datetime,
    completed_at: datetime,
    created_at: datetime,
    retry_count: int,
}
```

### Repositories

Key repositories for enrichment:
- **DatasetVersionRepository**: Version tracking
- **DatasetImportBuildRepository**: Ingestion tracking
- **DatasetEnrichmentBuildRepository**: Processing tracking
- **FeatureVectorRepository**: Feature storage (single source of truth)
- **TrivyCommitScanRepository**: Trivy scan tracking
- **SonarCommitScanRepository**: SonarQube scan tracking
- **FeatureAuditLogRepository**: Audit trail

---

## Error Handling & Recovery

### Phase 1: Validation Errors

| Error | Handling | Recovery |
|-------|----------|----------|
| Repo not found on GitHub | Mark DatasetBuild.status = "not_found" | User reviews, removes from CSV |
| Build not found on CI | Mark DatasetBuild.status = "not_found" | User reviews, removes from CSV |
| Build filtered (doesn't match filter) | Mark DatasetBuild.status = "filtered" | User adjusts filters |
| CI API rate limit | Retry with exponential backoff | Automatic retry |
| GitHub API timeout | Retry with exponential backoff | Automatic retry |

### Phase 2: Ingestion Errors

**Error Classification:**
- **FAILED**: Actual error (timeout, network, exception) - **Retryable**
- **MISSING_RESOURCE**: Expected condition (logs expired 90+ days) - **Not retryable**

| Error | Status | Retryable | Recovery |
|------|--------|-----------|----------|
| Clone timeout | FAILED | ✅ | Automatic retry, then `reingest_failed_builds` |
| Worktree creation fail | FAILED | ✅ | `reingest_failed_builds` |
| Log download failed | FAILED | ✅ | `reingest_failed_builds` |
| Logs expired (90+ days) | MISSING_RESOURCE | ❌ | Cannot retry - logs permanently unavailable |
| Fork commit replay fail | MISSING_RESOURCE | ❌ | User can retry if fork is updated |
| Chord failure (worker crash) | FAILED | ✅ | `reingest_failed_builds` |

**Chord Error Callback**:
```
If ANY task in chord fails:
    ├─ Mark all IN_PROGRESS builds as FAILED (retryable)
    ├─ Store error details (ingestion_error)
    ├─ Check if any builds made it to INGESTED
    ├─ If yes → Version status = INGESTED (can proceed)
    ├─ If no → Version status = FAILED (cannot proceed)
    └─ Publish error event
```

### Phase 3: Processing Errors

| Error | Handling | Recovery |
|------|----------|----------|
| Feature extraction fails | Mark build as FAILED | reprocess_failed_enrichment_builds |
| Trivy scan timeout | Retry up to 2 times | Automatic retry, builds marked missing trivy metrics |
| SonarQube scan fails | Mark SonarCommitScan as FAILED | User can retry scans manually |
| Temporal feature calculation error | Skip that feature | Mark as partial (feature_count reduced) |
| Chain failure (worker crash) | handle_enrichment_processing_chain_error | Mark IN_PROGRESS as FAILED |

**Chain Error Callback**:
```
If ANY task in chain fails:
    ├─ Mark all IN_PROGRESS builds as FAILED
    ├─ Count completed vs failed
    ├─ Update version status
    ├─ Publish error event
    └─ User can retry with reprocess_failed_enrichment_builds
```

### Retry Strategies

**Exponential Backoff**:
```python
countdown = min(60 * (2**retry_count), max_countdown)
```

**Max Retries by Task**:
- clone_repo: 3 retries
- create_worktree_chunk: 2 retries (fork replay is complex)
- download_logs_chunk: 2 retries
- start_trivy_scan: 2 retries
- start_sonar_scan: 2 retries

**User-Triggered Retries**:
- `reingest_failed_builds` - Retry FAILED ingestion builds (not MISSING_RESOURCE)
- `reprocess_failed_enrichment_builds` - Retry failed processing
- Manual scan retry via UI (for SonarQube)

---

## Performance Optimization

### 1. Chunking Strategy

**CSV Validation**:
```python
VALIDATION_REPOS_PER_CHUNK = 50
VALIDATION_BUILDS_PER_CHUNK = 100
```

**Worktree Creation**:
```python
INGESTION_WORKTREES_PER_CHUNK = 200  # Sequential chunks
```

**Log Download**:
```python
INGESTION_LOGS_PER_CHUNK = 500  # Parallel chunks
```

**Scan Dispatch**:
```python
SCAN_BUILDS_PER_QUERY = 1000
SCAN_COMMITS_PER_BATCH = 100
SCAN_BATCH_DELAY_SECONDS = 0.5
```

### 2. Caching

- **RawRepository**: Cache GitHub metadata (prevents re-fetching)
- **RawBuildRun**: Cache CI metadata (prevents re-fetching)
- **Git bare repos**: Reuse across versions
- **Git worktrees**: Reuse if commit already exists
- **Build logs**: Cache on disk (don't re-download)

### 3. Database Optimization

**Indexing**:
- DatasetImportBuild: (dataset_version_id, status)
- DatasetEnrichmentBuild: (dataset_version_id, extraction_status)
- FeatureVector: (build_id, version_id, category)
- TrivyCommitScan: (dataset_version_id, commit_sha)
- SonarCommitScan: (dataset_version_id, commit_sha)

**Bulk Operations**:
- `bulk_insert` for DatasetImportBuild creation
- `bulk_update` for status changes
- `batch_update` for per-resource status

### 4. Redis Optimization

- **RedisLock**: Prevent concurrent operations (clone, worktree)

> **Note**: Tracking kết quả (ingestion, enrichment) sử dụng trực tiếp database queries để đảm bảo data durability

### 5. Parallelization

**Validation Phase**:
- Repo chunks in parallel (group)
- Build chunks per repo in parallel (group)

**Ingestion Phase**:
- Repo chains in parallel (group of chains)
- Log chunks per repo in parallel (chord with aggregate callback)
- Worktree chunks per repo sequential (chain for ordering)

**Processing Phase**:
- Scans for commits in parallel (group)
- Builds sequential (chain for temporal features)

**Scan Phase**:
- Trivy scans in parallel (trivy_scan queue)
- SonarQube scans in parallel (sonar_scan queue)

### 6. Resource Utilization

**Celery Workers**:
- validation: 2-4 workers
- ingestion: 4-8 workers (heavy I/O)
- trivy_scan: 2-4 workers (CPU-intensive)
- sonar_scan: 2-4 workers (network wait)
- processing: 4-8 workers (I/O + CPU)

**Git Resources**:
- Bare repos shared across versions
- Worktrees ephemeral (can be cleaned up)
- Disk space: ~2-5GB per repo (depends on history)

**Memory**:
- Feature extraction: ~500MB per build
- Scan execution: ~1-2GB per container

---

## Summary

### Key Design Principles

1. **Graceful Degradation**: Partial features better than no features
2. **Temporal Correctness**: Sequential processing for accurate temporal features
3. **Async Scans**: Don't block feature extraction
4. **Fault Tolerance**: Retry with exponential backoff, graceful fallbacks
5. **Auditability**: Track all operations in FeatureAuditLog
6. **Scalability**: Chunking, parallelization, caching
7. **Flexibility**: Dynamic resource calculation, per-repo config

### Processing Flow Summary

```
VALIDATION PHASE (validate repos & builds)
    ↓
INGESTION PHASE (clone, worktree, logs)
    ├─ Success: INGESTED
    ├─ Actual error: FAILED (retryable via reingest_failed_builds)
    └─ Expected: MISSING_RESOURCE (not retryable - logs expired)
    ↓
PROCESSING PHASE (extract features)
    ├─ Async: Scan metrics (Trivy, SonarQube)
    ├─ Sequential: Feature extraction (temporal features)
    ├─ Backfill: Scan results to all builds with commit
    └─ Auto: Quality evaluation on completion
    ↓
DATASET VERSION (enriched with features + scan metrics)
    ├─ Can export: CSV/JSON
    └─ Can retry: reprocess_failed_enrichment_builds
```

---

**Last Updated**: December 31, 2025
**Version**: 1.0
