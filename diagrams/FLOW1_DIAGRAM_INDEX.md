# 🎯 FLOW 1: Import Repos & Extract Features - Complete Package

## 📋 Document Index

| # | Document | Type | Purpose | File |
|----|----------|------|---------|------|
| 1 | **Flow 1 Complete Documentation** | Reference | Comprehensive guide with architecture, DB schema, API endpoints | `FLOW1_COMPLETE_DOCUMENTATION.md` |
| 2 | **Flow 1 Detailed Guide** | Reference | Detailed breakdown of use cases, swimlanes, and phases | `FLOW1_DETAILED_GUIDE.md` |
| 3 | **Astah Step-by-Step Guide** | Tutorial | Step-by-step instructions to create diagrams in Astah UML | `ASTAH_STEP_BY_STEP_GUIDE.md` |
| 4 | **Use Case Diagram** | Diagram | UML use case diagram (PlantUML) | `flow1_use_case.puml` |
| 5 | **Activity Diagram** | Diagram | Activity diagram with 5 swimlanes (PlantUML) | `flow1_activity_swimlanes.puml` |
| 6 | **Sequence Diagram** | Diagram | Detailed sequence of interactions (PlantUML) | `flow1_sequence_diagram.puml` |

---

## 🚀 Quick Start

### Option 1: View PlantUML Diagrams Online
1. Open https://www.plantuml.com/plantuml/uml/
2. Copy content from `.puml` files
3. Paste into editor
4. View rendered diagrams

### Option 2: View in VS Code
1. Install PlantUML extension: `jebbs.plantuml`
2. Open `.puml` file
3. Right-click → PlantUML: Preview Current Diagram
4. View inline

### Option 3: Import into Astah UML (Recommended for Thesis)
1. Download/Install Astah: https://www.change-vision.com/astah-download/
2. Follow instructions in `ASTAH_STEP_BY_STEP_GUIDE.md`
3. Create diagrams in Astah native format
4. Export to SVG/PNG for thesis document

---

## 📊 Diagram Summary

### 1️⃣ Use Case Diagram (`flow1_use_case.puml`)
- **Actors**: 2 (Developer, System)
- **Use Cases**: 9 (Search, Select, Configure, Import, Clone, Fetch, Extract, View Progress, View Metrics)
- **Relationships**: Include, Extend, Association
- **Purpose**: High-level overview of system interactions

**Key Use Cases:**
```
Developer:
- UC1: Search GitHub Repos
- UC2: Select Repositories
- UC3: Configure Import Settings
- UC4: Import Repositories
- UC8: View Import Progress
- UC9: View Build Metrics

System:
- UC5: Clone Repository
- UC6: Fetch Builds from CI
- UC7: Extract Features
```

### 2️⃣ Activity Diagram (`flow1_activity_swimlanes.puml`)
- **Swimlanes**: 5 (UI, API, Celery Tasks, Database, External)
- **Phases**: 3 (Search & Select, Import, Feature Extraction)
- **Activities**: 40+ detailed steps
- **Purpose**: Detailed workflow with component interactions

**Swimlane Colors:**
```
🔵 UI / Frontend: #E1F5FE (Light Blue)
🟣 API Layer: #F3E5F5 (Light Purple)
🟢 Celery Tasks: #E8F5E9 (Light Green)
🟠 Database: #FFF3E0 (Light Orange)
🔴 External: #FCE4EC (Light Pink)
```

**Three Phases:**
1. **Phase 1**: Search & Select (Synchronous, < 5 seconds)
2. **Phase 2**: Import (Mostly Async, 10-60 minutes)
3. **Phase 3**: Feature Extraction (Per Build, 1-5 minutes)

### 3️⃣ Sequence Diagram (`flow1_sequence_diagram.puml`)
- **Participants**: 6 (UI, API, GitHub API, Database, Celery, Git, CI Provider)
- **Sequences**: 6 phases with message flows
- **Details**: Method calls, parameters, return values
- **Purpose**: Understand temporal order of operations

**Sequence Phases:**
1. Search Repositories
2. Configure & Import
3. Async Import Chain
4. Fetch Builds from CI
5. Dispatch Feature Extraction
6. Feature Extraction (Per Build)

---

## 📚 Documentation Structure

### Core Components

**Frontend (UI)**
- Import modal with search and configuration
- Real-time progress display via WebSocket
- Build metrics and feature visualization

**API Layer**
- POST /repos/search - Search GitHub repositories
- POST /repos/import/bulk - Import multiple repositories
- GET /repos/languages - Detect repository languages
- GET /repos/test-frameworks - List supported frameworks

**Celery Tasks (Asynchronous)**
```
import_repo (Orchestrator)
├─ clone_repo
├─ fetch_and_save_builds
├─ dispatch_processing
└─ process_workflow_run (per build)
```

**Database Entities**
- RawRepository - Raw GitHub repo data
- ModelRepoConfig - User's repo configuration
- RawBuildRun - Individual build from CI
- ModelTrainingBuild - Build with extracted features

**External Services**
- GitHub API (search, repo info, installation token)
- CI Providers (GitHub Actions, Travis, Jenkins)
- Git repositories (clone, fetch, history)

---

## 🔄 Workflow Flow Chart

```
┌────────────────────────────────────────────────────────┐
│ PHASE 1: SEARCH & SELECT (Synchronous)               │
├────────────────────────────────────────────────────────┤
│ 1. User enters search query                           │
│ 2. API calls GitHub API                              │
│ 3. Results displayed (public + private)              │
│ 4. User selects multiple repos                        │
│ 5. User configures settings                           │
│ 6. Click Import button                                │
│                                                        │
│ Duration: < 5 seconds                                 │
│ Status: QUEUED                                        │
└─────────────────┬──────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────┐
│ PHASE 2: IMPORT (Mostly Async)                        │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Celery Chain:                                          │
│ 1. import_repo (orchestrator)                         │
│    ├─ Update status = IMPORTING                       │
│    └─ Start chain                                      │
│                                                        │
│ 2. clone_repo                                          │
│    ├─ Check if repo_path exists                       │
│    ├─ If new: git clone --bare URL                    │
│    └─ If exists: git fetch --all                      │
│    └─ Return: repo_id                                  │
│                                                        │
│ 3. fetch_and_save_builds                              │
│    ├─ Get CI provider instance                        │
│    ├─ ci_instance.fetch_builds(...)                   │
│    ├─ For each build: Create RawBuildRun             │
│    └─ Return: build_ids[]                              │
│                                                        │
│ 4. dispatch_processing                                │
│    ├─ For batch in build_ids (size=50):              │
│    │  └─ Create group of process_workflow_run tasks  │
│    ├─ Update status = IMPORTED                        │
│    └─ Return: dispatched count                        │
│                                                        │
│ Duration: 10-60 minutes                               │
│ Status: QUEUED → IMPORTING → IMPORTED → FAILED       │
└─────────────────┬──────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────┐
│ PHASE 3: FEATURE EXTRACTION (Per Build)               │
├────────────────────────────────────────────────────────┤
│                                                        │
│ For each build (parallel via group tasks):            │
│                                                        │
│ 1. process_workflow_run(repo_id, build_id)            │
│    ├─ Validate build exists                           │
│    ├─ Fetch RawRepository, RawBuildRun               │
│    └─ Status: in_progress                             │
│                                                        │
│ 2. build_hamilton_inputs()                            │
│    ├─ repo_path = REPOS_DIR / repo_id                │
│    ├─ Get git history                                 │
│    └─ Prepare all inputs                              │
│                                                        │
│ 3. HamiltonPipeline.run()                             │
│    ├─ build_features (test results)                   │
│    ├─ git_features (commit history)                   │
│    ├─ github_features (PR reviews)                    │
│    ├─ repo_features (metadata)                        │
│    └─ log_features (log analysis)                     │
│                                                        │
│ 4. Update ModelTrainingBuild                          │
│    ├─ features = {...}                                │
│    ├─ extraction_status = COMPLETED                   │
│    └─ Status: completed                               │
│                                                        │
│ Duration: 1-5 minutes per build                       │
│ Total: 100-500 minutes for 100 builds (parallel)      │
│ Status: PENDING → COMPLETED → FAILED                 │
└────────────────────────────────────────────────────────┘
```

---

## 🔧 Implementation Checklist

### Phase 1: Design & Planning ✅
- [x] Identify actors and use cases
- [x] Define swimlanes and phases
- [x] Create PlantUML diagrams
- [x] Document all flows

### Phase 2: Create Diagrams in Astah (TODO)
- [ ] Create Use Case Diagram
- [ ] Create Activity Diagram with 5 swimlanes
- [ ] Create Sequence Diagram
- [ ] Add detailed notes and descriptions
- [ ] Color-code swimlanes
- [ ] Export to SVG/PNG

### Phase 3: Documentation (TODO)
- [ ] Update thesis with diagrams
- [ ] Add architecture explanation
- [ ] Document API endpoints
- [ ] Document database schema
- [ ] Add configuration guide

### Phase 4: Testing & Validation (TODO)
- [ ] Verify workflow with real imports
- [ ] Test error scenarios
- [ ] Performance testing
- [ ] Update documentation based on findings

---

## 📖 How to Use This Package

### For Thesis Writing
1. Read `FLOW1_COMPLETE_DOCUMENTATION.md` for comprehensive overview
2. Use diagrams from PlantUML or Astah for thesis figures
3. Reference specific sections for implementation details
4. Include diagrams in appropriate sections of thesis

### For Development/Implementation
1. Read `FLOW1_DETAILED_GUIDE.md` for workflow details
2. Use swimlane diagram to understand component interactions
3. Reference API endpoints section for endpoint implementation
4. Reference database schema for data modeling

### For Creating Diagrams in Astah
1. Follow `ASTAH_STEP_BY_STEP_GUIDE.md` step-by-step
2. Use PlantUML diagrams as reference
3. Apply recommended colors to swimlanes
4. Add notes for each activity

### For Presenting to Advisor
1. Use completed Astah diagrams
2. Reference `FLOW1_COMPLETE_DOCUMENTATION.md` for explanations
3. Show PlantUML sequence diagram for detailed interactions
4. Highlight key components and phases

---

## 🎯 Key Entities & Relationships

```
┌─────────────────────────────┐
│   ModelRepoConfig (User's)  │
│  - full_name                │
│  - test_frameworks          │
│  - source_languages         │
│  - ci_provider              │
│  - import_status            │
│  - max_builds_to_ingest     │
│  - since_days               │
│  - only_with_logs           │
└──────────┬──────────────────┘
           │ raw_repo_id (FK)
           ▼
┌─────────────────────────────┐
│   RawRepository             │
│  - full_name (owner/repo)   │
│  - github_repo_id           │
│  - default_branch           │
│  - is_private               │
│  - main_lang                │
│  - github_metadata          │
└──────────┬──────────────────┘
           │ (1 to Many)
           ▼
┌─────────────────────────────┐
│   RawBuildRun              │
│  - build_id                 │
│  - build_number             │
│  - branch                   │
│  - commit_sha               │
│  - status                   │
│  - conclusion               │
│  - logs_available           │
└──────────┬──────────────────┘
           │ raw_workflow_run_id (FK)
           ▼
┌─────────────────────────────┐
│   ModelTrainingBuild        │
│  - head_sha                 │
│  - build_number             │
│  - extraction_status        │
│  - features {}              │
│  - build_conclusion         │
│  - error_message            │
└─────────────────────────────┘
```

---

## 🔐 Configuration Reference

### Test Frameworks by Language
```
Python:     pytest, unittest, nose, tox
Java:       junit, testng, maven-surefire
JavaScript: jest, mocha, jasmine, karma
Go:         testing, testify
Ruby:       minitest, rspec
C/C++:      gtest, cppunit, catch
```

### Supported CI Providers
```
GitHub Actions (default)
Travis CI
Jenkins
CircleCI
GitLab CI
AppVeyor
Azure Pipelines
```

### Build Filters
```
max_builds: 1-1000 (default: 100)
since_days: 1-3650 (default: 180)
only_with_logs: true/false (default: true)
exclude_bots: true/false (default: true)
```

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| Total Use Cases | 9 |
| Actors | 2 |
| Swimlanes | 5 |
| Phases | 3 |
| Celery Tasks | 6 |
| Database Entities | 4 |
| API Endpoints | 4+ |
| Feature Modules | 5 |
| PlantUML Files | 3 |
| Documentation Pages | 6 |

---

## 🔗 File Locations

All files are located in: `/diagrams/`

```
diagrams/
├── FLOW1_COMPLETE_DOCUMENTATION.md      (This file)
├── FLOW1_DETAILED_GUIDE.md
├── ASTAH_STEP_BY_STEP_GUIDE.md
├── flow1_use_case.puml
├── flow1_activity_swimlanes.puml
├── flow1_sequence_diagram.puml
└── FLOW1_DIAGRAM_INDEX.md              (This file)
```

---

## 📞 Questions & Clarifications

### Q: Why 3 types of diagrams?
**A**: 
- Use Case: High-level overview
- Activity: Detailed workflow with swimlanes
- Sequence: Temporal order of interactions

### Q: What's the difference between RawBuildRun and ModelTrainingBuild?
**A**:
- RawBuildRun: Direct data from CI provider
- ModelTrainingBuild: Enriched with extracted features for ML model

### Q: Can I customize test frameworks and languages?
**A**: Yes, during import configuration. Frameworks are auto-detected from logs during processing.

### Q: How long does the entire flow take?
**A**: 
- Search & Config: < 5 seconds
- Import: 10-60 minutes
- Feature Extraction: 1-5 minutes per build (parallel)

### Q: What happens if a build fails?
**A**: Error is logged, extraction_status set to FAILED, error_message saved to DB, and WebSocket event published to UI.

---

## ✅ Verification Checklist

- [x] All 9 use cases documented
- [x] All 5 swimlanes described
- [x] 3 phases clearly separated
- [x] Database schema defined
- [x] API endpoints specified
- [x] Celery task chain documented
- [x] Error handling explained
- [x] Configuration options listed
- [x] Performance considerations noted
- [x] PlantUML diagrams generated
- [x] Step-by-step Astah guide provided
- [x] Complete documentation written

---

**Last Updated**: 2025-12-14  
**Status**: Ready for Astah UML Import & Thesis Documentation  
**Next Step**: Follow `ASTAH_STEP_BY_STEP_GUIDE.md` to create diagrams in Astah

