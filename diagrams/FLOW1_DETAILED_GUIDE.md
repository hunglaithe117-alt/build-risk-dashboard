# Hướng Dẫn Tạo Diagram cho Luồng 1: Import Repos & Extract Features

## 📋 Tổng Quan Luồng

**Luồng 1: Import GitHub Repositories → Extract Features**

Luồng này bao gồm 3 giai đoạn chính:
1. **Import Phase**: Người dùng tìm kiếm và chọn repos từ GitHub
2. **Processing Phase**: Hệ thống clone repo, fetch builds từ CI, lưu vào DB
3. **Feature Extraction Phase**: Hệ thống extract features sử dụng Hamilton DAG pipeline

---

## 🎯 Use Case Diagram

### Actors (Tác nhân)
1. **Developer** - Người dùng của hệ thống
2. **System (Backend)** - Hệ thống xử lý async

### Use Cases

| ID | Use Case Name | Actor | Description |
|----|---|---|---|
| UC1 | Search GitHub Repos | Developer | Tìm kiếm repos trên GitHub (public + private) qua GitHub API |
| UC2 | Select Repositories | Developer | Chọn nhiều repos từ kết quả tìm kiếm |
| UC3 | Configure Import Settings | Developer | Cấu hình test frameworks, source languages, CI provider, build limits |
| UC4 | Import Repositories | Developer/System | Khởi tạo import process |
| UC5 | Clone Repository | System | Clone/update git repository vào local storage (BARE clone) |
| UC6 | Fetch Builds from CI | System | Fetch builds và logs từ CI provider (GitHub Actions, Travis, Jenkins, etc.) |
| UC7 | Extract Features | System | Extract features sử dụng Hamilton DAG pipeline |
| UC8 | View Import Progress | Developer | Xem tiến độ import qua WebSocket real-time updates |
| UC9 | View Build Metrics | Developer | Xem metrics của builds sau khi extract features |

### Mối Quan Hệ (Relationships)
```
Developer → UC1 (Search)
UC1 → UC2 (Select)
UC2 → UC3 (Configure)
UC3 → UC4 (Import)

UC4 → UC5 (Clone) [System]
UC5 → UC6 (Fetch Builds) [System]
UC6 → UC7 (Extract) [System]

UC4 → UC8 (View Progress) [Developer]
UC7 → UC8 (Update Progress)
UC7 → UC9 (View Results) [Developer]
```

---

## 🏊 Activity Diagram với Swimlanes

### Swimlanes (5 cái)

1. **UI / Frontend** (Màu xanh nhạt - #E1F5FE)
   - Giao diện nhập liệu
   - Hiển thị kết quả
   - Cập nhật real-time qua WebSocket

2. **API Layer** (Màu tím nhạt - #F3E5F5)
   - FastAPI routes
   - Authentication
   - Request validation
   - Database operations

3. **Celery Tasks** (Màu xanh lá nhạt - #E8F5E9)
   - Async task orchestration
   - import_repo, clone_repo, fetch_and_save_builds, dispatch_processing, process_workflow_run

4. **Database** (Màu cam nhạt - #FFF3E0)
   - MongoDB operations
   - RawRepository
   - ModelRepoConfig
   - RawBuildRun
   - ModelTrainingBuild
   - Features storage

5. **External (GitHub/CI)** (Màu hồng nhạt - #FCE4EC)
   - GitHub API
   - Git operations
   - CI Providers API

### Chi Tiết Các Giai Đoạn

#### **Giai Đoạn 1: SEARCH & SELECT (Synchronous)**

**Step 1-1: Tìm kiếm Repositories**
```
UI: User enters search query → Click Search
API: POST /repos/search?q=query
  ↓ Get user's GitHub client
External: Query GitHub API
  ↓ Return public + private matches
API: Return RepoSuggestion[]
UI: Display search results
```

**Step 1-2: Chọn & Cấu Hình**
```
UI: Select repositories from results
UI: Configure settings:
    - test_frameworks: ["pytest", "junit"]
    - source_languages: ["python", "java"]
    - ci_provider: "github_actions"
    - max_builds: 100
    - since_days: 180
    - only_with_logs: true
UI: Click Import button
```

#### **Giai Đoạn 2: IMPORT (Mostly Async)**

**Step 2-1: Create Records & Queue Task**
```
API: POST /repos/import/bulk with payload[]
  ↓ For each repo:
    - Verify repo exists on GitHub
    - Create RawRepository
    - Create ModelRepoConfig (status=QUEUED)
API: Queue celery task: import_repo.delay()
API: Return RepoResponse[] with status=QUEUED
UI: Show confirmation, subscribe to WebSocket
```

**Step 2-2: Celery Chain - import_repo → clone_repo → fetch_and_save_builds → dispatch_processing**

```
Celery: import_repo() triggered
  └─ Update ModelRepoConfig status=IMPORTING
  └─ Publish REPO_UPDATE event to Redis
UI: Receive update: "Importing..."
  
Celery: clone_repo() starts
  ├─ Check if repo_path exists in REPOS_DIR/repo_id/
  ├─ If exists: git fetch --all --prune
  └─ If new: 
      ├─ Get installation token
      └─ git clone --bare https://x-access-token:TOKEN@github.com/owner/repo.git
  └─ Return repo_id
UI: Receive update: "Cloned successfully"

Celery: fetch_and_save_builds() starts
  ├─ Calculate since_dt = now - since_days
  ├─ Get CI provider instance
  ├─ ci_instance.fetch_builds(
  │   full_name, 
  │   since=since_dt,
  │   limit=max_builds,
  │   exclude_bots=True,
  │   only_with_logs=only_with_logs
  │ )
  ├─ For each build in results:
  │   ├─ Find/Create RawBuildRun
  │   └─ Create ModelTrainingBuild (status=PENDING)
  ├─ Update ModelRepoConfig with build_count
  └─ Return build_ids list
UI: Receive update: "Found N builds"

Celery: dispatch_processing() starts
  ├─ For batch in build_ids (batch_size=50):
  │   └─ Create group of tasks:
  │       └─ celery_app.signature("app.tasks.processing.process_workflow_run", 
  │           args=[repo_id, build_id])
  │       └─ tasks.apply_async()
  ├─ Update ModelRepoConfig status=IMPORTED
  └─ Publish "Import completed" event
UI: Mark repo as IMPORTED
```

#### **Giai Đoạn 3: FEATURE EXTRACTION (Per Build)**

**Step 3-1: Process Workflow Run**
```
Celery: process_workflow_run(repo_id, build_id) triggered
  ├─ Publish BUILD_UPDATE: "in_progress"
  └─ Fetch RawRepository, RawBuildRun, ModelRepoConfig
  
Celery: build_hamilton_inputs()
  ├─ repo_path = REPOS_DIR / repo_id
  ├─ Git history from repo_path
  ├─ Git worktree operations
  └─ Prepare workflow_run, repo_config, repo inputs

Celery: HamiltonPipeline.run(
    git_history=...,
    git_worktree=...,
    repo=...,
    workflow_run=...,
    repo_config=...,
    github_client=None,
    features_filter=template.feature_names
  )

Hamilton DAG Execution:
  ├─ build_features extractor
  ├─ git_features extractor
  ├─ github_features extractor
  ├─ repo_features extractor
  └─ log_features extractor (nếu có logs)

Celery: Collect features → Format for storage

DB: Update ModelTrainingBuild
  ├─ features: {...}
  ├─ extraction_status: COMPLETED
  └─ Save extracted features

Celery: Publish BUILD_UPDATE: "completed"

UI: Receive WebSocket update
  ├─ Show build extraction status
  └─ Display extracted features in Build Details
```

---

## 📊 Entities & Relationships

### Main Entities

```
RawRepository
├─ id
├─ full_name (github: owner/repo)
├─ github_repo_id
├─ default_branch
├─ is_private
├─ main_lang
└─ github_metadata

ModelRepoConfig
├─ id
├─ user_id
├─ full_name
├─ provider (github)
├─ raw_repo_id → RawRepository
├─ installation_id
├─ test_frameworks []
├─ source_languages []
├─ ci_provider
├─ import_status (QUEUED → IMPORTING → IMPORTED → FAILED)
├─ max_builds_to_ingest
├─ since_days
├─ only_with_logs
└─ last_sync_status

RawBuildRun
├─ id
├─ raw_repo_id → RawRepository
├─ build_id (CI provider build ID)
├─ build_number
├─ repo_name
├─ branch
├─ commit_sha
├─ status (COMPLETED)
├─ conclusion (SUCCESS/FAILURE/CANCELLED)
├─ created_at
├─ logs_available
├─ logs_path
├─ provider
└─ raw_data

ModelTrainingBuild
├─ id
├─ raw_repo_id → RawRepository
├─ raw_workflow_run_id → RawBuildRun
├─ model_repo_config_id → ModelRepoConfig
├─ head_sha
├─ build_number
├─ build_created_at
├─ build_conclusion
├─ extraction_status (PENDING → COMPLETED → FAILED)
├─ features {} (extracted features)
├─ error_message
└─ is_missing_commit
```

---

## 🔄 Celery Task Chain

### Orchestration Chain

```
import_repo (ORCHESTRATOR)
  │
  └─→ chain(
      clone_repo.s(repo_id, full_name, installation_id),
      fetch_and_save_builds.s(repo_id, full_name, ..., ci_provider, ...),
      dispatch_processing.s(repo_id)
    )

dispatch_processing
  │
  └─→ group([
      process_workflow_run.s(repo_id, build_id_1),
      process_workflow_run.s(repo_id, build_id_2),
      ...
    ])
```

### Queue Configuration
- **import_repo queue**: clone_repo, fetch_and_save_builds, dispatch_processing
- **data_processing queue**: process_workflow_run

---

## 🌐 Real-time Updates (WebSocket)

### Events Published to Redis

**REPO_UPDATE**
```json
{
  "type": "REPO_UPDATE",
  "payload": {
    "repo_id": "...",
    "status": "importing | cloned | imported | failed",
    "message": "..."
  }
}
```

**BUILD_UPDATE**
```json
{
  "type": "BUILD_UPDATE",
  "payload": {
    "repo_id": "...",
    "build_id": "...",
    "status": "in_progress | completed | failed"
  }
}
```

---

## 📝 API Endpoints (Synchronous Part)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/repos/search?q=query` | Search repos (returns private + public) |
| POST | `/repos/import/bulk` | Import multiple repositories |
| GET | `/repos/languages?full_name=owner/repo` | Detect repo languages |
| GET | `/repos/test-frameworks` | List supported test frameworks |
| GET | `/repos/` | List user's tracked repos |

---

## 🔑 Key Concepts

### Feature Extraction Pipeline (Hamilton DAG)

Features được extract từ 5 modules:
1. **build_features** - Test results, build time, failures
2. **git_features** - Commit history, branching patterns
3. **github_features** - PR reviews, issue stats
4. **repo_features** - Repository metadata
5. **log_features** - Build log analysis (test logs, compiler output)

### Swimlane Diagram Best Practice for Astah

1. **Swimlane width**: Tùy proportional hoặc equal
2. **Activity shape**: Rounded rectangles
3. **Decision diamond**: For if/else conditions
4. **Merge/fork bar**: For parallel processing
5. **Timeline**: Top to bottom flow
6. **Cross-lane arrows**: Show interactions between lanes

### Warna Swimlane Recommendations

| Swimlane | Color | RGB |
|----------|-------|-----|
| UI / Frontend | Light Blue | #E1F5FE |
| API Layer | Light Purple | #F3E5F5 |
| Celery Tasks | Light Green | #E8F5E9 |
| Database | Light Orange | #FFF3E0 |
| External (GitHub/CI) | Light Pink | #FCE4EC |

---

## 💡 Astah UML Cách Tạo

### Step 1: Create Use Case Diagram
1. Open Astah → New Project
2. Create Use Case Diagram
3. Add Actors:
   - Draw "Developer" actor
   - Draw "System" actor
4. Add Use Cases (UC1-UC9)
5. Draw Associations
6. Add Notes for descriptions

### Step 2: Create Activity Diagram
1. Create Activity Diagram
2. Add Swimlanes (5 cái):
   - Right-click → Insert Swimlane
   - Rename: UI / Frontend, API Layer, Celery Tasks, Database, External
3. Add Activities:
   - Double-click each swimlane area
   - Insert activities (rectangles)
   - Add decision points (diamonds)
4. Draw Flows:
   - Use arrows between activities
   - Cross-swimlane flows để show interactions

### Step 3: Add Details
1. Add notes/comments
2. Use guards `[condition]` on decision flows
3. Mark parallel flows with fork/join bars
4. Color-code activities if needed

---

## 🎓 Chi tiết API Flow

### 1. Search Repositories - `/repos/search`

```python
# Frontend
POST /api/repos/search?q="pytorch"

# Backend - RepositoryService.search_repositories()
User's GitHub Token → GitHub API /search/repositories
                  → /user/repos (private)
                  → /user/installation/repositories (GitHub App)

# Response
{
  "private_matches": [
    {
      "id": 123,
      "name": "pytorch",
      "full_name": "pytorch/pytorch",
      "is_private": False,
      "description": "..."
    }
  ],
  "public_matches": [...]
}
```

### 2. Import Repositories - `/repos/import/bulk`

```python
# Frontend
POST /api/repos/import/bulk

Body:
[
  {
    "full_name": "pytorch/pytorch",
    "installation_id": "123456",
    "test_frameworks": ["pytest"],
    "source_languages": ["python"],
    "ci_provider": "github_actions",
    "max_builds": 100,
    "since_days": 180,
    "only_with_logs": true
  }
]

# Backend - RepositoryService.bulk_import_repositories()
for payload in payloads:
  1. Verify repo exists on GitHub
  2. Create/Update RawRepository
  3. Create/Update ModelRepoConfig
  4. celery: import_repo.delay()

Response:
[
  {
    "id": "...",
    "full_name": "pytorch/pytorch",
    "import_status": "QUEUED",
    "created_at": "..."
  }
]
```

---

## 🚀 Next Steps

1. Tạo Use Case Diagram trong Astah UML
2. Tạo Activity Diagram với 5 Swimlanes
3. Tạo Sequence Diagram cho chi tiết API flows
4. Tạo Class Diagram cho entities
5. Update thesis document

---

## 📌 PlantUML Files Generated

✅ `diagrams/flow1_use_case.puml` - Use Case Diagram
✅ `diagrams/flow1_activity_swimlanes.puml` - Activity Diagram with Swimlanes

Bạn có thể:
- Mở `.puml` files trong PlantUML editor để preview
- Export to SVG/PNG
- Import structure vào Astah UML

