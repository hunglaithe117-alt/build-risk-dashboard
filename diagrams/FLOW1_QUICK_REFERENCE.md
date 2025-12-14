# ⚡ FLOW 1 Quick Reference Card

## 🎯 Flow Overview

**Luồng 1: Import Repos từ GitHub & Extract Features**

- **Actors**: Developer, System
- **Duration**: 10-60 minutes (+ feature extraction)
- **Status Progression**: QUEUED → IMPORTING → IMPORTED → FAILED

---

## 📊 3 Phases

### Phase 1️⃣: Search & Configure (< 5 sec)
```
UI → API → GitHub API → Return results → Display → Select & Configure
```

### Phase 2️⃣: Import (10-60 min)
```
import_repo → clone_repo → fetch_and_save_builds → dispatch_processing
    ↓           ↓              ↓                        ↓
  Queue      Git ops        CI fetch               Task schedule
```

### Phase 3️⃣: Extract Features (1-5 min per build, parallel)
```
process_workflow_run (per build)
  ├─ build_hamilton_inputs()
  ├─ HamiltonPipeline.run()
  │  ├─ build_features
  │  ├─ git_features
  │  ├─ github_features
  │  ├─ repo_features
  │  └─ log_features
  └─ Save to DB
```

---

## 🏊 5 Swimlanes

| # | Swimlane | Color | Role |
|----|----------|-------|------|
| 1 | **UI / Frontend** | 🔵 #E1F5FE | User interactions, WebSocket listener |
| 2 | **API Layer** | 🟣 #F3E5F5 | REST endpoints, validation, DB ops |
| 3 | **Celery Tasks** | 🟢 #E8F5E9 | Async orchestration, processing |
| 4 | **Database** | 🟠 #FFF3E0 | MongoDB CRUD operations |
| 5 | **External** | 🔴 #FCE4EC | GitHub API, Git ops, CI providers |

---

## 9️⃣ Use Cases

```
UC1: Search GitHub Repos          → Find repos on GitHub
UC2: Select Repositories          → Multi-select from results
UC3: Configure Import Settings    → Set frameworks, languages, limits
UC4: Import Repositories          → Trigger import
UC5: Clone Repository             → Git clone --bare
UC6: Fetch Builds from CI         → Get builds from GitHub Actions/Travis
UC7: Extract Features             → Hamilton DAG feature extraction
UC8: View Import Progress         → Real-time WebSocket updates
UC9: View Build Metrics           → Display extracted features
```

---

## 📊 Database Entities

```
RawRepository
  ├─ full_name, github_repo_id, default_branch
  └─ is_private, main_lang, github_metadata

ModelRepoConfig (User's config)
  ├─ raw_repo_id → RawRepository
  ├─ test_frameworks, source_languages
  ├─ ci_provider, import_status
  └─ max_builds, since_days, only_with_logs

RawBuildRun
  ├─ build_id, build_number, branch, commit_sha
  ├─ status, conclusion, logs_available
  └─ raw_data, provider

ModelTrainingBuild (With features)
  ├─ raw_workflow_run_id → RawBuildRun
  ├─ extraction_status (PENDING → COMPLETED)
  ├─ features {} (extracted data)
  └─ build_conclusion, error_message
```

---

## 🔗 API Endpoints

```
GET  /repos/search?q=<query>
     → Returns: {private_matches[], public_matches[]}

POST /repos/import/bulk
     ← Payload: [{full_name, installation_id, test_frameworks, ...}]
     → Returns: RepoResponse[] {status: QUEUED}

GET  /repos/languages?full_name=owner/repo
     → Returns: [detected languages]

GET  /repos/test-frameworks
     → Returns: {frameworks[], by_language{}, languages[]}
```

---

## 🔄 Celery Task Chain

```
import_repo(repo_id, full_name, installation_id, ci_provider, ...)
  │
  ├─→ clone_repo.s(repo_id, full_name, installation_id)
  │   │
  │   ├─ git fetch --all --prune (if exists)
  │   └─ git clone --bare URL (if new)
  │
  ├─→ fetch_and_save_builds.s(repo_id, full_name, ci_provider, ...)
  │   │
  │   ├─ ci_instance.fetch_builds(...)
  │   └─ for each build: Create RawBuildRun + ModelTrainingBuild
  │
  └─→ dispatch_processing.s(repo_id)
      │
      └─ for batch in build_ids (50 per batch):
         └─ group([process_workflow_run.s(...) for each build])
```

---

## 💾 Hamilton DAG Features

### 5 Extractors

1. **build_features** - Test results, build time, failures
2. **git_features** - Commit history, branching patterns
3. **github_features** - PR reviews, issue statistics
4. **repo_features** - Repository metadata, size
5. **log_features** - Test log analysis, compiler output

### Feature Examples
```
build_features:     tr_build_duration, tr_test_count, tr_test_failed
git_features:       g_num_commits, g_num_authors, gi_num_large_files
github_features:    gh_pr_review_count, gh_issue_count
repo_features:      r_lines_of_code, r_num_files
log_features:       log_test_error_count, log_warning_count
```

---

## 🔌 WebSocket Events

```
REPO_UPDATE
{
  "type": "REPO_UPDATE",
  "payload": {
    "repo_id": "...",
    "status": "importing|cloned|imported|failed",
    "message": "..."
  }
}

BUILD_UPDATE
{
  "type": "BUILD_UPDATE",
  "payload": {
    "repo_id": "...",
    "build_id": "...",
    "status": "in_progress|completed|failed"
  }
}
```

---

## ⚙️ Configuration Options

```
test_frameworks:      ["pytest", "junit", ...]
source_languages:     ["python", "java", ...]
ci_provider:          "github_actions" (or travis, jenkins)
max_builds:           1-1000 (default: 100)
since_days:           1-3650 (default: 180 days)
only_with_logs:       true/false (default: true)
```

---

## 📈 Timeline

```
T+0s:    User clicks Import
T+0-60s: Phase 1 (Search & Config) [UI]
T+60s:   import_repo queued
T+1m:    Phase 2 starts (Import) [Async]
T+5-30m: clone_repo
T+10-40m: fetch_and_save_builds
T+40m:   dispatch_processing
T+45m:   Phase 3 starts (Feature Extraction) [Parallel]
T+45-90m: process_workflow_run (50-100 builds)
T+90m:   Complete!
```

---

## ✅ Files Generated

```
✅ flow1_use_case.puml
   └─ 2 actors, 9 use cases, associations

✅ flow1_activity_swimlanes.puml
   └─ 5 swimlanes, 3 phases, 40+ activities

✅ flow1_sequence_diagram.puml
   └─ 6 participants, 6 sequence phases

📄 FLOW1_COMPLETE_DOCUMENTATION.md
   └─ Comprehensive reference (architecture, API, DB, performance)

📄 FLOW1_DETAILED_GUIDE.md
   └─ Use cases, swimlanes, phases, API flows

📄 ASTAH_STEP_BY_STEP_GUIDE.md
   └─ How to create diagrams in Astah UML

📄 FLOW1_DIAGRAM_INDEX.md
   └─ Document index and navigation
```

---

## 🚀 Next Steps

1. **View PlantUML**: Open `.puml` files at https://www.plantuml.com/plantuml/uml/
2. **Create in Astah**: Follow `ASTAH_STEP_BY_STEP_GUIDE.md`
3. **Export Diagrams**: SVG/PNG for thesis
4. **Update Thesis**: Include diagrams in appropriate sections
5. **Present**: Show to advisor with complete documentation

---

## 💡 Key Insights

✨ **Asynchronous**: All heavy operations run via Celery  
✨ **Real-time**: WebSocket updates keep UI synchronized  
✨ **Scalable**: Batch processing and parallelization  
✨ **Resilient**: Error handling and retry logic  
✨ **Flexible**: Customizable frameworks, languages, CI providers  
✨ **Modular**: 5 separate feature extractors (Hamilton DAG)

---

**Status**: ✅ Ready for Astah Import  
**Last Update**: 2025-12-14

