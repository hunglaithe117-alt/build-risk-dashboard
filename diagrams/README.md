# 📖 README - Flow 1 Diagrams & Documentation

## 📌 Overview

This folder contains **complete documentation and diagrams** for **Flow 1: Import Repositories from GitHub & Extract Features**.

All materials are ready for:
- ✅ Viewing in PlantUML online editor
- ✅ Importing into Astah UML
- ✅ Including in thesis document
- ✅ Presenting to advisor

---

## 📁 What's Inside

### 📊 PlantUML Diagrams (7 files)

| File | Diagram Type | Purpose | Key Elements |
|------|-------------|---------|--------------|
| `flow1_use_case.puml` | Use Case Diagram | High-level system overview | 2 Actors, 9 Use Cases |
| `flow1_activity_swimlanes.puml` | Activity Diagram | Detailed workflow with swimlanes | 5 Swimlanes, 3 Phases |
| `flow1_sequence_diagram.puml` | Sequence Diagram | Temporal interactions | 6 Participants, 6 Sequences |
| `functional_overview_use_case.puml` | Use Case Diagram | Functional overview: Admin vs Authenticated User | Actors: Admin, Repository Member |
| `functional_overview_component.puml` | Component Diagram | High-level system components & integrations | Frontend, Backend, DB, SonarQube, GitHub |
| `functional_overview_sequence_flow1.puml` | Sequence Diagram | Live repo integration flow (register → enrich → infer → notify) | 8 Participants, async tasks |
| `functional_overview_sequence_flow2.puml` | Sequence Diagram | Dataset enrichment flow (upload → enrich → versions) | 6 Participants, batch processing |

### 📚 Documentation (5 files)

| File | Type | Content | Audience |
|------|------|---------|----------|
| `FLOW1_QUICK_REFERENCE.md` | Quick Ref | 1-page cheat sheet | Everyone |
| `FLOW1_DIAGRAM_INDEX.md` | Index | Navigation & overview | Thesis writers |
| `FLOW1_DETAILED_GUIDE.md` | Reference | Detailed breakdown of all components | Developers |
| `FLOW1_COMPLETE_DOCUMENTATION.md` | Reference | Comprehensive guide with all details | Thesis writers |
| `ASTAH_STEP_BY_STEP_GUIDE.md` | Tutorial | How to create diagrams in Astah | Diagram creators |

---

## 🚀 Quick Start (Choose Your Path)

### 👤 Path 1: I want a quick overview
```
1. Read: FLOW1_QUICK_REFERENCE.md (5 min)
2. View: flow1_use_case.puml (2 min)
Done! ✅
```

### 📊 Path 2: I want to create diagrams in Astah
```
1. Read: ASTAH_STEP_BY_STEP_GUIDE.md (30 min)
2. Open Astah UML
3. Follow step-by-step instructions
4. Use .puml files as reference
Done! ✅
```

### 📖 Path 3: I want to write in thesis
```
1. Read: FLOW1_COMPLETE_DOCUMENTATION.md (30 min)
2. Review: flow1_use_case.puml (5 min)
3. Review: flow1_activity_swimlanes.puml (10 min)
4. Create diagrams in Astah (60 min)
5. Export to SVG/PNG
6. Include in thesis
Done! ✅
```

### 💻 Path 4: I want to understand implementation
```
1. Read: FLOW1_DETAILED_GUIDE.md (45 min)
2. Review: flow1_sequence_diagram.puml (20 min)
3. Study API endpoints section
4. Study database schema section
5. Study Celery task chain section
Done! ✅
```

---

## 📊 Document Map

```
FLOW1_QUICK_REFERENCE.md (⭐ Start here!)
├─ 3 Phases overview
├─ 5 Swimlanes
├─ 9 Use Cases
├─ 4 DB Entities
├─ 4 API Endpoints
└─ 5 Celery Tasks

        │
        ▼

FLOW1_DIAGRAM_INDEX.md (Navigation)
├─ Document index
├─ Workflow flowchart
├─ Key entities & relationships
├─ Configuration reference
└─ Statistics

        │
        ▼

FLOW1_DETAILED_GUIDE.md (Deep dive)
├─ Use Case Diagram (in detail)
├─ Activity Diagram (phase by phase)
├─ Swimlane definition
├─ Feature extraction details
└─ Astah creation tips

        │
        ▼

FLOW1_COMPLETE_DOCUMENTATION.md (Reference)
├─ Architecture overview
├─ Database schema (detailed)
├─ API endpoints (detailed)
├─ Celery task chain (detailed)
├─ Hamilton DAG features
├─ Performance considerations
└─ Error handling

        │
        ▼

ASTAH_STEP_BY_STEP_GUIDE.md (Implementation)
├─ Use Case Diagram tutorial
├─ Activity Diagram tutorial
├─ Swimlane setup
├─ Activity placement
├─ Sequence Diagram tutorial
└─ Final checklist
```

---

## 🎯 By Role

### 👨‍🎓 Thesis Writer
**Goal**: Include diagrams and explanations in thesis

**Reading Order**:
1. FLOW1_QUICK_REFERENCE.md
2. FLOW1_COMPLETE_DOCUMENTATION.md
3. ASTAH_STEP_BY_STEP_GUIDE.md
4. Create diagrams → Export SVG/PNG → Include in thesis

**Time Estimate**: 2-3 hours

---

### 👨‍💻 Backend Developer
**Goal**: Understand implementation details

**Reading Order**:
1. FLOW1_QUICK_REFERENCE.md
2. FLOW1_DETAILED_GUIDE.md
3. flow1_sequence_diagram.puml
4. FLOW1_COMPLETE_DOCUMENTATION.md (API & DB sections)

**Time Estimate**: 1-2 hours

---

### 🎨 Diagram Creator
**Goal**: Create professional diagrams in Astah

**Reading Order**:
1. FLOW1_QUICK_REFERENCE.md
2. ASTAH_STEP_BY_STEP_GUIDE.md
3. View .puml files as reference
4. Create in Astah → Export SVG/PNG

**Time Estimate**: 2-4 hours

---

### 👔 Advisor/Reviewer
**Goal**: Understand overall system flow

**Reading Order**:
1. FLOW1_QUICK_REFERENCE.md
2. flow1_use_case.puml (2 min)
3. flow1_activity_swimlanes.puml (5 min)
4. FLOW1_DIAGRAM_INDEX.md (workflow section)

**Time Estimate**: 15-20 minutes

---

## 🔄 Workflow at a Glance

```
SEARCH & SELECT (< 5 seconds)
    ↓
    Developer searches GitHub → API queries → Results displayed
    ↓
    Developer selects repos → Configures settings → Clicks Import

IMPORT (10-60 minutes) [ASYNC]
    ↓
    import_repo (orchestrator)
    ├─→ clone_repo (git operations)
    ├─→ fetch_and_save_builds (CI integration)
    └─→ dispatch_processing (task scheduling)

FEATURE EXTRACTION (1-5 min per build, parallel)
    ↓
    For each build (50 per batch):
        process_workflow_run
        ├─ build_hamilton_inputs()
        ├─ HamiltonPipeline.run()
        │  ├─ build_features
        │  ├─ git_features
        │  ├─ github_features
        │  ├─ repo_features
        │  └─ log_features
        └─ Save to DB

RESULT
    ↓
    Features extracted and displayed in UI ✅
```

---

## 📊 Key Metrics

| Category | Value |
|----------|-------|
| **Use Cases** | 9 |
| **Actors** | 2 |
| **Swimlanes** | 5 |
| **Phases** | 3 |
| **Celery Tasks** | 6 |
| **DB Entities** | 4 |
| **Feature Modules** | 5 |
| **API Endpoints** | 4+ |
| **Total Features** | 50+ |

---

## 🎨 Swimlane Colors (for Astah)

Copy these hex codes for swimlane backgrounds:

```
UI / Frontend:     #E1F5FE    (Light Blue)
API Layer:         #F3E5F5    (Light Purple)
Celery Tasks:      #E8F5E9    (Light Green)
Database:          #FFF3E0    (Light Orange)
External (GitHub): #FCE4EC    (Light Pink)
```

**How to apply in Astah**:
1. Right-click swimlane → Edit → Style → Background Color
2. Input hex code (without #)
3. Click OK

---

## 🔗 External Resources

### PlantUML Online Editor
https://www.plantuml.com/plantuml/uml/

**How to use**:
1. Go to URL
2. Copy-paste .puml file content
3. View rendered diagram
4. Export to SVG/PNG

### Astah UML
https://www.change-vision.com/astah-download/

**Download & Install**:
1. Choose your OS (Windows/Mac/Linux)
2. Download
3. Install
4. Follow ASTAH_STEP_BY_STEP_GUIDE.md

### PlantUML Extension (VS Code)
Extension: `jebbs.plantuml`

**How to use**:
1. Install extension
2. Open .puml file
3. Right-click → PlantUML: Preview Current Diagram
4. View inline

---

## ✅ Verification Checklist

Before submitting/presenting:

- [ ] Read FLOW1_QUICK_REFERENCE.md
- [ ] Viewed all 3 PlantUML diagrams
- [ ] Read at least one detailed documentation file
- [ ] Understood 3 phases of the workflow
- [ ] Identified 5 swimlanes correctly
- [ ] Can explain 9 use cases
- [ ] Know the 4 main database entities
- [ ] Familiar with Celery task chain
- [ ] Can describe Hamilton DAG feature extraction
- [ ] Ready to discuss or present

---

## 🚀 Next Steps

### Option A: For Thesis Writers
1. [ ] Create diagrams in Astah (follow ASTAH_STEP_BY_STEP_GUIDE.md)
2. [ ] Export to SVG/PNG
3. [ ] Include in thesis document
4. [ ] Add captions and explanations

### Option B: For Developers
1. [ ] Read FLOW1_DETAILED_GUIDE.md
2. [ ] Study sequence diagram
3. [ ] Review API endpoint documentation
4. [ ] Implement or verify each component

### Option C: For Presenting
1. [ ] Review quick reference
2. [ ] Prepare diagrams (either PlantUML images or Astah export)
3. [ ] Create presentation slides with diagrams
4. [ ] Practice explanation

---

## 📞 FAQ

### Q: Can I edit the .puml files?
**A**: Yes! PlantUML files are text files. Edit them in any text editor. Changes render immediately online.

### Q: How do I convert .puml to image?
**A**: 
- Online: Use PlantUML online editor → Export
- Locally: Use PlantUML CLI or VS Code extension
- Astah: Create in Astah → Export to SVG/PNG

### Q: Should I use PlantUML images or Astah diagrams?
**A**: For professional thesis: Use Astah diagrams. For quick reference/presentation: PlantUML images are fine.

### Q: Can I customize the diagrams?
**A**: Yes! Both .puml files (edit text) and Astah diagrams (edit visually) are customizable.

### Q: Which file should I read first?
**A**: FLOW1_QUICK_REFERENCE.md - it's designed as an entry point.

---

## 📝 Document Statistics

| File | Lines | Words | Size |
|------|-------|-------|------|
| FLOW1_QUICK_REFERENCE.md | 180 | 1,200 | 8 KB |
| FLOW1_DIAGRAM_INDEX.md | 280 | 2,000 | 14 KB |
| FLOW1_DETAILED_GUIDE.md | 450 | 3,200 | 22 KB |
| FLOW1_COMPLETE_DOCUMENTATION.md | 700 | 5,500 | 35 KB |
| ASTAH_STEP_BY_STEP_GUIDE.md | 550 | 4,000 | 28 KB |
| flow1_use_case.puml | 80 | 400 | 2 KB |
| flow1_activity_swimlanes.puml | 400 | 1,800 | 12 KB |
| flow1_sequence_diagram.puml | 250 | 1,200 | 8 KB |

**Total**: ~3,000 lines, ~19,900 words, ~130 KB of documentation

---

## 🎓 Learning Path

```
Beginner (0-30 min)
└─ FLOW1_QUICK_REFERENCE.md
   └─ View use_case.puml

Intermediate (30-90 min)
├─ FLOW1_DIAGRAM_INDEX.md
├─ flow1_use_case.puml
└─ flow1_activity_swimlanes.puml

Advanced (90-180 min)
├─ FLOW1_DETAILED_GUIDE.md
├─ FLOW1_COMPLETE_DOCUMENTATION.md
└─ flow1_sequence_diagram.puml

Expert (180+ min)
├─ ASTAH_STEP_BY_STEP_GUIDE.md
├─ Create diagrams in Astah
└─ Customize for specific needs
```

---

## 💾 Version History

| Date | Changes |
|------|---------|
| 2025-12-14 | Initial creation - All diagrams and documentation generated |

---

## 📧 Support

For questions about:
- **PlantUML syntax**: https://plantuml.com/guide
- **Astah UML**: https://www.change-vision.com/
- **Thesis diagrams**: Follow ASTAH_STEP_BY_STEP_GUIDE.md

---

**Created**: 2025-12-14  
**Status**: ✅ Complete and ready for use  
**Last Modified**: 2025-12-14

---

**🎉 Thank you for using Flow 1 Documentation Package! Good luck with your thesis! 🎉**

