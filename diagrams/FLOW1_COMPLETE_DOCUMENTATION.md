# 📊 FLOW 1: Import Repos & Extract Features - Complete Documentation

## 🎯 Executive Summary

**Flow 1** là quy trình nhập repositories từ GitHub và extract features từ các build runs để đưa vào mô hình Bayesian risk prediction.

### Key Metrics
- **Phases**: 3 pha (Search & Configure → Import → Feature Extraction)
- **Actors**: 2 (Developer, System)
- **Use Cases**: 9
- **Swimlanes**: 5
- **Celery Tasks**: 5 (import_repo, clone_repo, fetch_and_save_builds, download_build_logs, dispatch_processing, process_workflow_run)
- **External APIs**: GitHub API, CI Providers (GitHub Actions, Travis, Jenkins)
- **DB Entities**: 4 main (RawRepository, ModelRepoConfig, RawBuildRun, ModelTrainingBuild)

---

## 📁 Generated Diagrams

Tất cả diagrams được tạo dưới dạng PlantUML (.puml) files:

| File | Type | Purpose |
|------|------|---------|
| `flow1_use_case.puml` | Use Case Diagram | High-level overview của luồng |
| `flow1_activity_swimlanes.puml` | Activity Diagram + Swimlanes | Chi tiết từng bước với 5 swimlanes |
| `flow1_sequence_diagram.puml` | Sequence Diagram | Tương tác chi tiết giữa các components |

### Cách xem PlantUML files:
1. Online: https://www.plantuml.com/plantuml/uml/
2. VS Code: PlantUML extension (jebbs.plantuml)
3. Astah UML: Import từ file

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (UI)                        │
│  - Search Repos                                         │
│  - Select & Configure                                  │
│  - View Progress (WebSocket)                           │
│  - Display Metrics                                      │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP/REST
┌──────────────────▼──────────────────────────────────────┐
│                  API LAYER (FastAPI)                    │
│  - /repos/search                                        │
│  - /repos/import/bulk                                  │
│  - /repos/{id}/...                                     │
└──────────────────┬──────────────────────────────────────┘
                   │ Queue Tasks
┌──────────────────▼──────────────────────────────────────┐
│          CELERY WORKERS (Async Tasks)                   │
│  - import_repo (orchestrator)                          │
│  - clone_repo (git)                                    │
│  - fetch_and_save_builds (CI)                          │
│  - dispatch_processing (scheduler)                     │
│  - process_workflow_run (extraction)                   │
└──────────────────┬──────────────────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼
  [Database]  [GitHub]   [CI Providers]
   MongoDB     API       (Actions/Travis)
```

---

## 📊 Use Case Diagram Summary

### Actors
1. **Developer** - User interacting with the system
2. **System** - Backend system processing asynchronously

### Use Cases (9 total)

```
┌─────────────────────────────────────────────────────────┐
│                 DEVELOPER INTERACTIONS                  │
├─────────────────────────────────────────────────────────┤
│ UC1: Search GitHub Repos                               │
│   ├─ Description: Search GitHub via API                │
│   ├─ Actor: Developer                                  │
│   └─ Precondition: User logged in, GitHub token valid │
│                                                         │
│ UC2: Select Repositories                               │
│   ├─ Description: Multi-select from search results     │
│   ├─ Actor: Developer                                  │
│   └─ Include: UC1                                      │
│                                                         │
│ UC3: Configure Import Settings                         │
│   ├─ Description: Set test frameworks, languages, etc  │
│   ├─ Actor: Developer                                  │
│   └─ Include: UC2                                      │
│                                                         │
│ UC4: Import Repositories                               │
│   ├─ Description: Trigger import process               │
│   ├─ Actor: Developer                                  │
│   └─ Include: UC3                                      │
│                                                         │
│ UC8: View Import Progress                              │
│   ├─ Description: Real-time progress updates           │
│   ├─ Actor: Developer                                  │
│   ├─ Mechanism: WebSocket events                       │
│   └─ Trigger: After UC4                                │
│                                                         │
│ UC9: View Build Metrics                                │
│   ├─ Description: Display extracted features           │
│   ├─ Actor: Developer                                  │
│   └─ Trigger: After feature extraction                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 SYSTEM OPERATIONS                       │
├─────────────────────────────────────────────────────────┤
│ UC5: Clone Repository                                  │
│   ├─ Description: Clone/update git repository          │
│   ├─ Actor: System                                     │
│   ├─ Method: git clone --bare                          │
│   ├─ Duration: 1-10 minutes                            │
│   └─ Include: UC4                                      │
│                                                         │
│ UC6: Fetch Builds from CI                              │
│   ├─ Description: Fetch builds from CI provider        │
│   ├─ Actor: System                                     │
│   ├─ Providers: GitHub Actions, Travis, Jenkins       │
│   └─ Include: UC5                                      │
│                                                         │
│ UC7: Extract Features                                  │
│   ├─ Description: Extract features using Hamilton DAG  │
│   ├─ Actor: System                                     │
│   ├─ Modules: build, git, github, repo, log            │
│   └─ Include: UC6                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🏊 Activity Diagram with Swimlanes

### Swimlane Definition (5 lanes)

```
┌─────────────────────────────────────────────────────────┐
│ SWIMLANE 1: UI / Frontend (Light Blue #E1F5FE)         │
│ ├─ Search input                                        │
│ ├─ Repository selection                                │
│ ├─ Settings configuration                              │
│ ├─ Progress display                                    │
│ └─ WebSocket listener                                  │
├─────────────────────────────────────────────────────────┤
│ SWIMLANE 2: API Layer (Light Purple #F3E5F5)           │
│ ├─ /repos/search endpoint                             │
│ ├─ /repos/import/bulk endpoint                        │
│ ├─ Request validation                                  │
│ ├─ Database operations                                 │
│ └─ Celery task queuing                                │
├─────────────────────────────────────────────────────────┤
│ SWIMLANE 3: Celery Tasks (Light Green #E8F5E9)        │
│ ├─ import_repo (orchestrator)                         │
│ ├─ clone_repo (git operations)                        │
│ ├─ fetch_and_save_builds (CI integration)            │
│ ├─ dispatch_processing (task scheduling)              │
│ └─ process_workflow_run (feature extraction)          │
├─────────────────────────────────────────────────────────┤
│ SWIMLANE 4: Database (Light Orange #FFF3E0)           │
│ ├─ RawRepository                                       │
│ ├─ ModelRepoConfig                                     │
│ ├─ RawBuildRun                                         │
│ ├─ ModelTrainingBuild                                  │
│ └─ Feature storage                                    │
├─────────────────────────────────────────────────────────┤
│ SWIMLANE 5: External (Light Pink #FCE4EC)             │
│ ├─ GitHub API                                          │
│ ├─ Git repository                                      │
│ ├─ CI Providers                                        │
│ └─ Build logs                                          │
└─────────────────────────────────────────────────────────┘
```

### Phase-by-Phase Flow

#### Phase 1: Search & Configure (Synchronous)
- **Duration**: < 5 seconds
- **Flow**:
  1. User enters search query
  2. API calls GitHub API
  3. Results displayed
  4. User selects repos
  5. User configures settings
  6. Click Import

#### Phase 2: Import (Mostly Async)
- **Duration**: 10-60 minutes
- **Celery Chain**:
  1. import_repo (orchestrator)
  2. clone_repo (git clone)
  3. fetch_and_save_builds (CI integration)
  4. dispatch_processing (task scheduling)

#### Phase 3: Feature Extraction (Per Build)
- **Duration**: 1-5 minutes per build
- **Process**:
  1. fetch build data
  2. build Hamilton inputs
  3. Execute Hamilton DAG
  4. Save features to DB
  5. Send WebSocket update

---

## 🔄 Celery Task Chain Details

### Import Task Chain

```
import_repo()
├─ Input: user_id, full_name, installation_id, ci_provider, max_builds, since_days
├─ Purpose: Orchestrator - starts the entire workflow
├─ Output: {status: "queued", repo_id, message}
│
└─ chain(
    clone_repo.s(repo_id, full_name, installation_id),
    ├─ Purpose: Clone/update git repository
    ├─ Input: repo_id, full_name, installation_id
    ├─ Operations:
    │  ├─ Check if repo_path exists
    │  ├─ If exists: git fetch --all --prune
    │  └─ If new: git clone --bare <URL>
    ├─ Output: {repo_id, status: "cloned"}
    │
    fetch_and_save_builds.s(...),
    ├─ Purpose: Fetch builds from CI and save to DB
    ├─ Input: clone_result, repo_id, full_name, installation_id, ci_provider, max_builds, since_days, only_with_logs
    ├─ Operations:
    │  ├─ Get CI provider instance
    │  ├─ ci_instance.fetch_builds(full_name, since=since_dt, limit=max_builds, ...)
    │  ├─ For each build: Create RawBuildRun and ModelTrainingBuild
    │  └─ Return build_ids list
    ├─ Output: {build_ids[], build_count, ...}
    │
    dispatch_processing.s(repo_id)
    ├─ Purpose: Schedule feature extraction tasks in batches
    ├─ Input: fetch_result, repo_id, batch_size=50
    ├─ Operations:
    │  ├─ For each batch of 50 builds:
    │  │  └─ Create group of process_workflow_run tasks
    │  ├─ Update ModelRepoConfig status=IMPORTED
    │  └─ Return {dispatched count}
    ├─ Output: {repo_id, dispatched, status}
   )
```

### Feature Extraction Task

```
process_workflow_run(repo_id, build_id)
├─ Input: repo_id, build_id (workflow_run_id)
├─ Purpose: Extract features for a single build
├─ Operations:
│  ├─ Validate build exists
│  ├─ Fetch RawRepository, RawBuildRun, ModelRepoConfig
│  ├─ build_hamilton_inputs()
│  │  ├─ repo_path = REPOS_DIR / repo_id
│  │  ├─ Get git history
│  │  ├─ Create git worktree
│  │  └─ Prepare all inputs (repo, workflow_run, repo_config, etc)
│  ├─ HamiltonPipeline.run()
│  │  ├─ build_features (test results, durations, failures)
│  │  ├─ git_features (commit history, branching)
│  │  ├─ github_features (PR reviews, issues)
│  │  ├─ repo_features (metadata)
│  │  └─ log_features (log analysis)
│  ├─ Format features for storage
│  ├─ Update ModelTrainingBuild with features
│  └─ Publish WebSocket update
├─ Output: {status, build_id, feature_count, errors}
└─ Error Handling: Save error_message to DB, publish failed status
```

---

## 📊 Database Schema

### RawRepository
```
{
  _id: ObjectId,
  full_name: String,           // "owner/repo"
  github_repo_id: Integer,
  default_branch: String,      // "main" or "master"
  is_private: Boolean,
  main_lang: String,           // Primary programming language
  github_metadata: Object      // Full GitHub API response
}
```

### ModelRepoConfig
```
{
  _id: ObjectId,
  user_id: ObjectId,
  full_name: String,
  provider: String,            // "github"
  raw_repo_id: ObjectId,       // Reference to RawRepository
  installation_id: String,     // GitHub App installation ID
  test_frameworks: [String],   // ["pytest", "junit"]
  source_languages: [String],  // ["python", "java"]
  ci_provider: String,         // "github_actions"
  import_status: String,       // "QUEUED", "IMPORTING", "IMPORTED", "FAILED"
  max_builds_to_ingest: Integer,
  since_days: Integer,
  only_with_logs: Boolean,
  created_at: DateTime,
  last_sync_at: DateTime,
  last_sync_error: String,
  build_count: Integer         // Number of builds fetched
}
```

### RawBuildRun
```
{
  _id: ObjectId,
  raw_repo_id: ObjectId,       // Reference to RawRepository
  build_id: String,            // CI provider's build ID
  build_number: Integer,
  repo_name: String,
  branch: String,
  commit_sha: String,
  commit_message: String,
  commit_author: String,
  status: String,              // "COMPLETED"
  conclusion: String,          // "SUCCESS", "FAILURE", "CANCELLED"
  created_at: DateTime,
  started_at: DateTime,
  completed_at: DateTime,
  duration_seconds: Integer,
  web_url: String,
  logs_url: String,
  logs_available: Boolean,
  logs_path: String,           // Path to downloaded logs
  provider: String,            // CI provider enum
  raw_data: Object,            // Provider-specific data
  is_bot_commit: Boolean
}
```

### ModelTrainingBuild
```
{
  _id: ObjectId,
  raw_repo_id: ObjectId,                  // Reference to RawRepository
  raw_workflow_run_id: ObjectId,          // Reference to RawBuildRun
  model_repo_config_id: ObjectId,         // Reference to ModelRepoConfig
  head_sha: String,
  build_number: Integer,
  build_created_at: DateTime,
  build_conclusion: String,               // ModelBuildConclusion enum
  extraction_status: String,              // "PENDING", "COMPLETED", "PARTIAL", "FAILED"
  features: Object,                       // {feature_name: value, ...}
  error_message: String,
  is_missing_commit: Boolean,
  extracted_at: DateTime
}
```

---

## 🔌 API Endpoints

### Search Repositories
```
GET /repos/search?q=<query>

Response:
{
  "private_matches": [RepoSuggestion],
  "public_matches": [RepoSuggestion]
}

RepoSuggestion:
{
  "id": Integer,
  "name": String,
  "full_name": String,
  "is_private": Boolean,
  "description": String,
  "url": String,
  "installation_id": String (if private)
}
```

### Import Repositories
```
POST /repos/import/bulk

Request:
[
  {
    "full_name": "owner/repo",
    "installation_id": "string",
    "test_frameworks": ["pytest"],
    "source_languages": ["python"],
    "ci_provider": "github_actions",
    "max_builds": 100,
    "since_days": 180,
    "only_with_logs": true
  }
]

Response:
[
  {
    "id": "ObjectId",
    "full_name": "owner/repo",
    "import_status": "QUEUED",
    "created_at": "DateTime"
  }
]
```

---

## 🔐 Configuration Options

### Test Frameworks (by Language)
- **Python**: pytest, unittest, nose
- **Java**: junit, testng
- **JavaScript**: jest, mocha, jasmine
- **Go**: testing
- **Ruby**: minitest, rspec
- **C/C++**: gtest, cppunit

### Source Languages
Auto-detected from GitHub repo metadata or specified manually

### CI Providers
- GitHub Actions (default)
- Travis CI
- Jenkins
- CircleCI
- GitLab CI
- etc.

### Build Filters
- `max_builds`: Limit number of builds to ingest (e.g., 100)
- `since_days`: Only fetch builds from last N days (e.g., 180)
- `only_with_logs`: Only fetch builds with available logs

---

## 📡 Real-time Updates (WebSocket)

### Event Types

**REPO_UPDATE**
```json
{
  "type": "REPO_UPDATE",
  "payload": {
    "repo_id": "ObjectId",
    "status": "importing|cloned|imported|failed",
    "message": "Progress message"
  }
}
```

**BUILD_UPDATE**
```json
{
  "type": "BUILD_UPDATE",
  "payload": {
    "repo_id": "ObjectId",
    "build_id": "ObjectId",
    "status": "in_progress|completed|failed"
  }
}
```

### WebSocket Connection
1. Frontend connects to `/ws` endpoint
2. Subscribes to repo updates
3. Receives events in real-time
4. Updates UI accordingly

---

## 📈 Performance Considerations

### Timeouts
- Git clone: 10 minutes max
- Build fetch: 5 minutes max per batch
- Feature extraction: 10 minutes max per build
- Total workflow: Typically 30-60 minutes for 100 builds

### Resource Requirements
- **CPU**: 2+ cores (for parallel feature extraction)
- **Memory**: 8GB+ (for git operations and feature extraction)
- **Disk**: 100GB+ (for repository clones)
- **Network**: High bandwidth (GitHub/CI API calls, git clone)

### Batch Processing
- Builds are processed in batches of 50
- Feature extraction is parallelized
- Redis pubsub for event distribution

---

## ❌ Error Handling

### Common Errors

| Error | Cause | Resolution |
|-------|-------|-----------|
| Repository not found | Invalid repo name | Verify repo exists on GitHub |
| Installation not found | Invalid installation_id | Re-authorize GitHub App |
| Rate limit exceeded | Too many API calls | Wait or upgrade token |
| Logs expired | Retention period exceeded | Adjust since_days |
| Git operation failed | Network or permission issue | Check git URL and token |
| Feature extraction failed | Missing dependencies | Check logs for details |

### Error Handling Strategy
1. Log error with context
2. Update import_status to FAILED
3. Save error_message to DB
4. Publish error event to WebSocket
5. User can retry or investigate

---

## 🎓 Feature Extraction Details

### Hamilton DAG Pipeline

Hamilton is a Python framework for building modular, testable data pipelines.

#### Feature Modules

**build_features** - From CI build logs and metadata
- `tr_build_duration` - Build duration in seconds
- `tr_test_count` - Number of tests run
- `tr_test_passed` - Number of tests passed
- `tr_test_failed` - Number of tests failed
- `tr_test_skipped` - Number of tests skipped
- etc.

**git_features** - From Git history
- `g_num_commits` - Number of commits in build
- `g_num_authors` - Number of authors
- `gi_num_large_files` - Number of large files changed
- etc.

**github_features** - From GitHub API
- `gh_pr_review_count` - Number of PR reviews
- `gh_issue_count` - Number of issues
- `gh_contributor_count` - Number of contributors
- etc.

**repo_features** - Repository metadata
- `r_lines_of_code` - Total lines of code
- `r_num_files` - Number of files
- etc.

**log_features** - Build log analysis
- `log_test_error_count` - Number of test errors
- `log_compilation_warning_count` - Compilation warnings
- etc.

---

## 📌 Key Takeaways

✅ **Asynchronous Processing**: All heavy operations (clone, fetch, extract) run async via Celery
✅ **Real-time Updates**: WebSocket events keep UI updated during processing
✅ **Batch Processing**: Feature extraction is parallelized in batches
✅ **Error Resilience**: Failed tasks are logged and can be retried
✅ **Flexible Configuration**: Users can customize test frameworks, languages, build limits
✅ **Scalable**: Can handle thousands of repositories and millions of builds

---

## 📚 Related Documentation

- `flow1_use_case.puml` - Use Case Diagram in PlantUML
- `flow1_activity_swimlanes.puml` - Activity Diagram with Swimlanes
- `flow1_sequence_diagram.puml` - Sequence Diagram with detailed interactions
- `ASTAH_STEP_BY_STEP_GUIDE.md` - How to create diagrams in Astah UML

---

## 🚀 Next Steps

1. Review PlantUML diagrams
2. Import structure into Astah UML
3. Create additional diagrams (Class, Deployment, etc.)
4. Update thesis with final diagrams
5. Present to advisor

