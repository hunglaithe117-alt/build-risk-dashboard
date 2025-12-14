# Hướng Dẫn Chi Tiết: Tạo Diagram trong Astah UML

## 📌 Part 1: USE CASE DIAGRAM

### Actors (Tác Nhân)

| # | Actor Name | Type | Description |
|---|-----------|------|-------------|
| 1 | Developer | Human | Người dùng import repositories |
| 2 | System | System | Backend system thực hiện xử lý async |

**Cách vẽ trong Astah:**
1. Left palette → Drag "Actor" shape
2. Đặt Actor phía trái (Developer)
3. Drag "Actor" shape khác phía phải (System)
4. Rename: right-click → Edit Name

---

### Use Cases

| # | UC ID | Name | Actor(s) | Description |
|---|-------|------|----------|-------------|
| 1 | UC1 | Search GitHub Repos | Developer | User tìm kiếm repositories trên GitHub |
| 2 | UC2 | Select Repositories | Developer | User chọn multiple repositories |
| 3 | UC3 | Configure Import Settings | Developer | User cấu hình test frameworks, languages, CI provider |
| 4 | UC4 | Import Repositories | Developer/System | Trigger import process |
| 5 | UC5 | Clone Repository | System | Clone/update repo về local (BARE clone) |
| 6 | UC6 | Fetch Builds from CI | System | Fetch builds from GitHub Actions/Travis/Jenkins |
| 7 | UC7 | Extract Features | System | Extract features using Hamilton DAG |
| 8 | UC8 | View Import Progress | Developer | Real-time progress via WebSocket |
| 9 | UC9 | View Build Metrics | Developer | Display extracted build metrics |

**Cách vẽ trong Astah:**
1. Center palette → Drag "Oval/Ellipse" shape (Use Case)
2. Double-click → Type "Search GitHub Repos"
3. Arrange all 9 use cases (UC1-UC9)

---

### Associations & Relationships

```
SEQUENTIAL FLOW (Developer interactions):
┌─────────────────────────────┐
│  Developer                  │
│  - Search Repos             │ (UC1)
│  - Select Repos             │ (UC2)
│  - Configure Settings       │ (UC3)
│  - Click Import             │ (UC4)
│  - View Progress [async]    │ (UC8)
│  - View Results             │ (UC9)
└─────────────────────────────┘
        ↓
    Association
        ↓
┌──────────────────────────────┐
│  System                      │
│  - Clone Repository          │ (UC5)
│  - Fetch Builds              │ (UC6)
│  - Extract Features          │ (UC7)
└──────────────────────────────┘
```

**Cách vẽ trong Astah:**
1. Connection tool → Draw line từ Developer actor đến UC1
2. Type: "Association" (simple arrow)
3. Repeat cho UC2, UC3, UC4
4. UC4 → UC5, UC6, UC7 (System side)
5. UC7 → UC8, UC9 (Developer side)

**Association Types:**
- UC1 → UC2: Include (Developer must search before selecting)
- UC2 → UC3: Include (Must configure after selecting)
- UC3 → UC4: Include (Must configure before importing)
- UC4 → UC5: Solid line (Sequential)
- UC5 → UC6: Include (Clone before fetch)
- UC6 → UC7: Include (Fetch before extract)
- UC4 ↔ UC8: Async (View progress during import)
- UC7 → UC9: Result (Extract before viewing metrics)

---

### Notes/Comments

Thêm notes cho mỗi use case:

**UC1: Search GitHub Repos**
```
Uses GitHub API v3 endpoint:
- GET /search/repositories?q=<query>
- GET /user/repos (private)
- GET /user/installation/repositories

Returns: RepoSuggestion[] with metadata
```

**UC3: Configure Import Settings**
```
Settings to configure:
- test_frameworks: ["pytest", "junit", ...]
- source_languages: ["python", "java", ...]
- ci_provider: "github_actions" (or travis, jenkins)
- max_builds: max number of builds to ingest
- since_days: fetch builds from last N days
- only_with_logs: fetch only builds with logs
```

**UC5: Clone Repository**
```
Async Task: clone_repo()
- Check if repo_path exists in REPOS_DIR/repo_id/
- If exists: git fetch --all --prune
- If new: git clone --bare
  https://x-access-token:TOKEN@github.com/owner/repo.git
- Duration: 1-10 minutes depending on repo size
```

**UC7: Extract Features**
```
Uses Hamilton DAG Pipeline:
Modules:
- build_features (test results, build time)
- git_features (commit history)
- github_features (PR reviews, issues)
- repo_features (metadata)
- log_features (test log analysis)

Features extracted per build
```

---

## 📌 Part 2: ACTIVITY DIAGRAM WITH SWIMLANES

### Swimlane Setup

**5 Swimlanes to create:**

1. **UI / Frontend** (Color: #E1F5FE - Light Blue)
   - React/Next.js components
   - User interactions
   - WebSocket listeners

2. **API Layer** (Color: #F3E5F5 - Light Purple)
   - FastAPI endpoints
   - Request validation
   - Service methods

3. **Celery Tasks** (Color: #E8F5E9 - Light Green)
   - Async task orchestration
   - Task chain: import_repo → clone_repo → fetch_and_save_builds → dispatch_processing
   - process_workflow_run tasks

4. **Database** (Color: #FFF3E0 - Light Orange)
   - MongoDB operations
   - CRUD operations
   - Entity storage

5. **External (GitHub/CI)** (Color: #FCE4EC - Light Pink)
   - GitHub API
   - CI Provider APIs
   - Git operations

**Cách vẽ trong Astah:**
1. Open Activity Diagram
2. Right-click on diagram → Insert → Swimlane
3. Drag to create 5 horizontal swimlanes
4. Rename mỗi swimlane:
   - Swimlane 1: "UI / Frontend"
   - Swimlane 2: "API Layer"
   - Swimlane 3: "Celery Tasks"
   - Swimlane 4: "Database"
   - Swimlane 5: "External (GitHub/CI)"

---

### Phase 1: SEARCH & SELECT (Synchronous)

#### Activity Flow for Phase 1

```
┌─────────────────────────────────────────────────────────────────┐
│ UI / Frontend                                                   │
├─────────────────────────────────────────────────────────────────┤
(Start)
  ↓
[User opens Import Modal]
  ↓
[User enters search query]
  ↓
{Click Search button}
  │
  ├─────────────────────────────────────────────────────────────→
  │ API Layer
  ├─────────────────────────────────────────────────────────────┤
  │ POST /repos/search?q=query
  │   ↓
  │ Get User GitHub Client
  │   │
  │   ├──────────────────────────────────────────────────────→
  │   │ External (GitHub/CI)
  │   ├──────────────────────────────────────────────────────┤
  │   │ Query GitHub API
  │   │   ↓
  │   │ Return search results
  │   │   (public + private repos)
  │   │   │
  │   └───┴──────────────────────────────────────────────────→
  │ 
  │ Format RepoSuggestion[]
  │   ↓
  │ Return response
  │   │
  └─────┴────────────────────────────────────────────────────→
│ 
│ Display search results
│   ↓
│ {User selects repositories}
│   ↓
│ {Configure settings:}
│   - test_frameworks
│   - source_languages
│   - ci_provider
│   - max_builds
│   - since_days
│   - only_with_logs
│   ↓
│ {Click Import button}
│   ↓
│ (Continue to Phase 2)
│
└─────────────────────────────────────────────────────────────────┘
```

**Cách vẽ trong Astah:**
1. Drag "Start" circle vào UI / Frontend swimlane
2. Add activities:
   - [User opens Import Modal]
   - [User enters search query]
   - [Click Search button]
3. Cross-lane arrow đến API Layer
4. Activities:
   - [POST /repos/search?q=query]
   - [Get User GitHub Client]
5. Cross-lane arrow đến External
6. Activities:
   - [Query GitHub API]
   - [Return search results]
7. Cross-lane arrow kembali ke API
8. Activity: [Format RepoSuggestion[]]
9. Cross-lane arrow kembali ke UI
10. Activities:
    - [Display search results]
    - {User selects repositories}
    - [Configure settings]
    - [Click Import button]

**Decision Point:**
```
{Click Import?}
  ├─ YES → [Continue to Phase 2]
  └─ NO → [Cancel] → (End)
```

---

### Phase 2: IMPORT (Mostly Async)

#### Activity Flow for Phase 2

```
┌─────────────────────────────────────────────────────────────────┐
│ UI / Frontend                                                   │
├─────────────────────────────────────────────────────────────────┤
(From Phase 1: [Click Import])
  ↓
{Show "Importing..." status}
  │
  ├─────────────────────────────────────────────────────────────→
  │ API Layer
  ├─────────────────────────────────────────────────────────────┤
  │ POST /repos/import/bulk
  │   ↓
  │ Extract payload[]
  │   ↓
  │ for each repo in payload:
  │   │
  │   ├────────────────────────────────────────────────────────→
  │   │ External (GitHub/CI)
  │   ├────────────────────────────────────────────────────────┤
  │   │ Verify repo exists on GitHub
  │   │   ↓
  │   │ Return repo metadata
  │   │   (id, default_branch, language)
  │   │   │
  │   └───┴─────────────────────────────────────────────────→
  │
  │   ↓
  │   ├──────────────────────────────────────────────────────→
  │   │ Database
  │   ├──────────────────────────────────────────────────────┤
  │   │ [Create/Update RawRepository]
  │   │ [Create/Update ModelRepoConfig]
  │   │   status = QUEUED
  │   │   │
  │   └───┴──────────────────────────────────────────────────→
  │
  │ ↓
  │ Queue async task: import_repo.delay()
  │ ↓
  │ Return RepoResponse[]
  │ status = QUEUED
  │   │
  └─────┴────────────────────────────────────────────────────→
│
│ Show import confirmation
│   ↓
│ Update repo status to QUEUED
│   ↓
│ Subscribe WebSocket for updates
│   ↓
├─────────────────────────────────────────────────────────────→
│ Celery Tasks
├─────────────────────────────────────────────────────────────┤
│
│ import_repo.delay() triggered
│   ↓
│ Update status to IMPORTING
│   │
│   ├──────────────────────────────────────────────────────→
│   │ Database
│   ├──────────────────────────────────────────────────────┤
│   │ Update ModelRepoConfig
│   │   status = IMPORTING
│   │   │
│   └───┴───────────────────────────────────────────────→
│
│ ↓
│ clone_repo.s(repo_id, full_name, installation_id)
│   ↓
│   [Check if repo_path exists]
│   ↓
│   ◇ repo exists?
│   ├─ YES: [git fetch --all --prune]
│   └─ NO:  [Get installation token]
│           [git clone --bare URL]
│   ↓
│   ├────────────────────────────────────────────────────→
│   │ External (GitHub/CI)
│   ├────────────────────────────────────────────────────┤
│   │ Clone/fetch repository
│   │   ↓
│   │ Return success/error
│   │   │
│   └───┴─────────────────────────────────────────────→
│
│ ↓
│ [Return repo_id]
│   │
│   ├──────────────────────────────────────────────────→
│   │ UI / Frontend
│   ├──────────────────────────────────────────────────┤
│   │ Receive WebSocket update
│   │   ↓
│   │ {Show "Cloned successfully"}
│   │   │
│   └───┴───────────────────────────────────────────→
│
│ ↓ (continue chain)
│ fetch_and_save_builds.s(...)
│   ↓
│   [Prepare parameters]
│   ↓
│   [Calculate since_dt from since_days]
│   ↓
│   [Get CI provider instance]
│   ↓
│   ├────────────────────────────────────────────────────→
│   │ External (GitHub/CI)
│   ├────────────────────────────────────────────────────┤
│   │ await ci_instance.fetch_builds(
│   │   full_name, since=since_dt,
│   │   limit=max_builds,
│   │   exclude_bots=True,
│   │   only_with_logs=only_with_logs
│   │ )
│   │ ↓
│   │ Return Build[] list
│   │   │
│   └───┴────────────────────────────────────────────→
│
│ ↓
│ for each build in results:
│   │
│   ├─────────────────────────────────────────────────→
│   │ Database
│   ├─────────────────────────────────────────────────┤
│   │ [Create RawBuildRun]
│   │ [Create ModelTrainingBuild]
│   │   status = PENDING
│   │   │
│   └───┴──────────────────────────────────────────→
│
│ ↓
│ [Update ModelRepoConfig with build_count]
│ ↓
│ [Return build_ids list]
│   │
│   ├──────────────────────────────────────────────────→
│   │ UI / Frontend
│   ├──────────────────────────────────────────────────┤
│   │ Receive update
│   │   ↓
│   │ {Show "Found N builds"}
│   │   │
│   └───┴──────────────────────────────────────────→
│
│ ↓ (continue chain)
│ dispatch_processing.s(repo_id=repo_id)
│   ↓
│   ◇ any builds?
│   ├─ NO: [Skip processing]
│   │       [Mark IMPORTED]
│   │       [Publish "No builds"]
│   │
│   └─ YES: [For batch in build_ids (size=50)]
│            [Create group of tasks]
│            [process_workflow_run.s(repo_id, build_id)]
│            [tasks.apply_async()]
│            ↓
│   [Update status = IMPORTED]
│   ↓
│   ├─────────────────────────────────────────────────→
│   │ Database
│   ├─────────────────────────────────────────────────┤
│   │ Update ModelRepoConfig
│   │   status = IMPORTED
│   │   │
│   └───┴─────────────────────────────────────────→
│
│ ↓
│ [Publish "Dispatched N builds" status]
│   │
│   ├──────────────────────────────────────────────────→
│   │ UI / Frontend
│   ├──────────────────────────────────────────────────┤
│   │ Receive update
│   │   ↓
│   │ {Show "Import completed"}
│   │   ↓
│   │ {Mark repo as IMPORTED}
│   │   │
│   └───┴──────────────────────────────────────────→
│
│ (End Phase 2)
│
└─────────────────────────────────────────────────────────────────┘
```

**Cách vẽ trong Astah:**
1. Sắp xếp các activities theo thứ tự từ trên xuống dưới
2. Dùng cross-lane arrows để hiển thị tương tác giữa swimlanes
3. Dùng decision diamonds cho `if` statements
4. Dùng fork/join bars cho parallel processing
5. Dùng merge bars để join multiple flows

---

### Phase 3: FEATURE EXTRACTION (Per Build)

#### Activity Flow for Phase 3

```
┌─────────────────────────────────────────────────────────────────┐
│ Celery Tasks                                                    │
├─────────────────────────────────────────────────────────────────┤
process_workflow_run.delay(repo_id, build_id) triggered
  ↓
[Publish BUILD_UPDATE: "in_progress"]
  │
  ├──────────────────────────────────────────────────────────────→
  │ UI / Frontend
  ├──────────────────────────────────────────────────────────────┤
  │ Receive WebSocket update
  │   ↓
  │ {Show build extraction starting}
  │   │
  └───┴──────────────────────────────────────────────────────────→
│
│ ↓
│ [Fetch RawRepository, RawBuildRun, ModelRepoConfig]
│   │
│   ├──────────────────────────────────────────────────────────→
│   │ Database
│   ├──────────────────────────────────────────────────────────┤
│   │ Query RawRepository
│   │ Query RawBuildRun
│   │ Query ModelRepoConfig
│   │   │
│   └───┴──────────────────────────────────────────────────────→
│
│ ↓
│ [build_hamilton_inputs()]
│   ├─ repo_path = REPOS_DIR / repo_id
│   ├─ Clone git history from repo_path
│   ├─ Prepare git_worktree
│   ├─ Prepare workflow_run input
│   ├─ Prepare repo_config input
│   ├─ Prepare repo input
│   ↓
│   ├───────────────────────────────────────────────────────→
│   │ External (GitHub/CI)
│   ├───────────────────────────────────────────────────────┤
│   │ Git operations (if needed)
│   │ Clone history, worktree setup
│   │   │
│   └───┴──────────────────────────────────────────────────→
│
│ ↓
│ [HamiltonPipeline.run()]
│   ├─ Pass inputs:
│   │  ├─ git_history
│   │  ├─ git_worktree
│   │  ├─ repo
│   │  ├─ workflow_run
│   │  ├─ repo_config
│   │  ├─ github_client = None
│   │  └─ features_filter = template.feature_names
│   ↓
│   ◆═══ HAMILTON DAG EXECUTION ═══◆
│   │
│   ├─ [build_features extractor]
│   │   ├─ Test results
│   │   ├─ Build time
│   │   ├─ Failures
│   │   └─ ...
│   │
│   ├─ [git_features extractor]
│   │   ├─ Commit history
│   │   ├─ Branching patterns
│   │   ├─ Author info
│   │   └─ ...
│   │
│   ├─ [github_features extractor]
│   │   ├─ PR reviews
│   │   ├─ Issue stats
│   │   ├─ Contribution patterns
│   │   └─ ...
│   │
│   ├─ [repo_features extractor]
│   │   ├─ Repository metadata
│   │   ├─ Stars, forks
│   │   ├─ Size
│   │   └─ ...
│   │
│   └─ [log_features extractor] (if logs available)
│       ├─ Test log analysis
│       ├─ Compiler output analysis
│       ├─ Error patterns
│       └─ ...
│
│   ↓
│   [Collect extracted features]
│   ↓
│   [Format for storage]
│   ↓
│   ├──────────────────────────────────────────────────────→
│   │ Database
│   ├──────────────────────────────────────────────────────┤
│   │ Update ModelTrainingBuild:
│   │   features = {...}
│   │   extraction_status = COMPLETED
│   │   error_message = (if error)
│   │   │
│   └───┴───────────────────────────────────────────────→
│
│ ↓
│ [Publish BUILD_UPDATE: "completed"]
│   │
│   ├──────────────────────────────────────────────────────→
│   │ UI / Frontend
│   ├──────────────────────────────────────────────────────┤
│   │ Receive WebSocket update
│   │   ↓
│   │ {Show build extraction completed}
│   │   ↓
│   │ {Display extracted features}
│   │ {in Build Details page}
│   │   │
│   └───┴──────────────────────────────────────────────→
│
│ (End Phase 3)
│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎨 Color Coding for Swimlanes

| Swimlane | Hex Color | RGB Value | Usage |
|----------|-----------|-----------|-------|
| UI / Frontend | #E1F5FE | 225, 245, 254 | Light Blue |
| API Layer | #F3E5F5 | 243, 229, 245 | Light Purple |
| Celery Tasks | #E8F5E9 | 232, 245, 233 | Light Green |
| Database | #FFF3E0 | 255, 243, 224 | Light Orange |
| External (GitHub/CI) | #FCE4EC | 252, 228, 236 | Light Pink |

**Cách apply color trong Astah:**
1. Right-click on swimlane → Edit → Style → Background Color
2. Input hex color code

---

## 📊 Decision Points & Guards

### Decision Diamonds

| Decision | Options |
|----------|---------|
| [repo exists?] | YES: git fetch; NO: git clone |
| [any builds?] | YES: dispatch; NO: mark IMPORTED |
| [logs available?] | YES: download; NO: skip |

**Cách vẽ trong Astah:**
1. Use "Decision" shape (diamond)
2. Add guard text:
   - `[YES]` for true path
   - `[NO]` for false path
3. Label on arrows để indicate conditions

---

## 📋 Activity Shape Types

| Shape | Purpose | Example |
|-------|---------|---------|
| Circle | Start/End | (Start), (End) |
| Rectangle | Action/Activity | [Clone repository] |
| Diamond | Decision | ◇ repo exists? |
| Bar | Fork/Join | ═══ FORK ═══ |
| Arrow | Flow | → |
| Dashed Arrow | Async/Event | ⇢ |

---

## ✅ Final Checklist

- [ ] Created Use Case Diagram with 2 actors and 9 use cases
- [ ] Added all associations between use cases
- [ ] Created Activity Diagram with 5 swimlanes
- [ ] Swimlane 1: UI / Frontend (Light Blue)
- [ ] Swimlane 2: API Layer (Light Purple)
- [ ] Swimlane 3: Celery Tasks (Light Green)
- [ ] Swimlane 4: Database (Light Orange)
- [ ] Swimlane 5: External (GitHub/CI) (Light Pink)
- [ ] Added Phase 1 activities (Search & Select)
- [ ] Added Phase 2 activities (Import)
- [ ] Added Phase 3 activities (Feature Extraction)
- [ ] Added cross-swimlane arrows
- [ ] Added decision points with guards
- [ ] Added notes/comments for details
- [ ] Color-coded swimlanes
- [ ] Exported diagrams to SVG/PNG

