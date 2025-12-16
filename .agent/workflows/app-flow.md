---
description: Quy tắc kiến trúc cho Build Risk Dashboard
---

# Architecture Rules

## 1. Backend Layers

```
API (app/api/)  →  Service (app/services/)  →  Repository (app/repositories/)
     ↓                    ↓                           ↓
   Routes            Business Logic              DB Queries
     ↓                    ↓                           ↓
   DTOs              Entity ↔ DTO              Entity models
```

### API Layer (`app/api/`)
- ✅ Chỉ define routes (`@router.get`, `@router.post`)
- ✅ Dùng `Depends()` cho DB, Auth
- ✅ Validate input qua DTOs
- ✅ Gọi Service để xử lý logic
- ❌ KHÔNG viết business logic
- ❌ KHÔNG query DB trực tiếp

```python
@router.get("/", response_model=DatasetListResponse)
def list_datasets(
    skip: int = Query(default=0),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetService(db)
    return service.list_datasets(str(current_user["_id"]), skip=skip)
```

### Service Layer (`app/services/`)
- ✅ Chứa business logic
- ✅ Dùng Repository để query DB
- ✅ Raise HTTPException cho lỗi
- ✅ Convert Entity → DTO trước khi return
- ❌ KHÔNG query DB trực tiếp

```python
class DatasetService:
    def __init__(self, db: Database):
        self.repo = DatasetRepository(db)

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetResponse:
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or str(dataset.user_id) != user_id:
            raise HTTPException(status_code=404, detail="Not found")
        return DatasetResponse.model_validate(dataset.model_dump(by_alias=True))
```

### Repository Layer (`app/repositories/`)
- ✅ Kế thừa `BaseRepository[T]`
- ✅ Chỉ chứa MongoDB queries
- ✅ Trả về Entity models
- ❌ KHÔNG chứa business logic
- ❌ KHÔNG raise HTTPException

```python
class DatasetRepository(BaseRepository[DatasetProject]):
    def __init__(self, db: Database):
        super().__init__(db, "datasets", DatasetProject)

    def list_by_user(self, user_id: str, skip: int, limit: int):
        query = {"user_id": self._to_object_id(user_id)}
        return self.paginate(query, skip=skip, limit=limit)
```

**BaseRepository methods:** `find_by_id`, `find_one`, `find_many`, `paginate`, `insert_one`, `update_one`, `delete_one`

### DTO Layer (`app/dtos/`)
- ✅ Pydantic BaseModel
- ✅ Dùng `PyObjectIdStr` cho ObjectId
- ✅ Pattern: `*Request`, `*Response`

```python
class DatasetResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
    name: str
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class DatasetCreateRequest(BaseModel):
    name: str
    file_name: str
```

### Entity Layer (`app/entities/`)
- ✅ Kế thừa `BaseEntity`
- ✅ Dùng `PyObjectId` (không phải `PyObjectIdStr`)
- ✅ Enum cho status fields

```python
class DatasetProject(BaseEntity):
    user_id: Optional[PyObjectId] = None
    name: str
    validation_status: DatasetValidationStatus = DatasetValidationStatus.PENDING
```

### Task Layer (`app/tasks/`)
- ✅ Kế thừa `PipelineTask`
- ✅ Access DB qua `self.db`
- ✅ Gọi bằng `.delay()` hoặc `.apply_async()`

```python
@celery_app.task(bind=True, base=PipelineTask)
def validate_dataset_task(self, dataset_id: str):
    service = DatasetValidationService(self.db)
    return service.run_validation(dataset_id)
```

---

## 2. Frontend Layers

| Layer | Path | Mục đích |
|-------|------|----------|
| Pages | `src/app/` | Routes (App Router) |
| Components | `src/components/` | UI components |
| API Client | `src/lib/api.ts` | Axios calls |
| Types | `src/types/` | TypeScript interfaces |
| Contexts | `src/contexts/` | Global state |
| Hooks | `src/hooks/` | Custom hooks |

### Components Structure
```
components/
├── ui/       # shadcn/ui components
├── layout/   # Sidebar, Topbar, AppShell
├── auth/     # Auth components
└── sonar/    # Feature-specific
```

### API Client Pattern
```typescript
export const datasetApi = {
  list: async (params?: { skip?: number }) => {
    const response = await api.get<DatasetListResponse>("/datasets", { params });
    return response.data;
  },
};
```

---

## 3. Naming Conventions

### Backend
| Type | File | Class |
|------|------|-------|
| API | `datasets.py` | - |
| Service | `dataset_service.py` | `DatasetService` |
| Repository | `dataset_repository.py` | `DatasetRepository` |
| Entity | `dataset.py` | `DatasetProject` |
| DTO Request | `dataset.py` | `DatasetCreateRequest` |
| DTO Response | `dataset.py` | `DatasetResponse` |

### Frontend
| Type | Pattern |
|------|---------|
| Page | `page.tsx` |
| Component | `{name}.tsx` |
| Hook | `use-{name}.ts` |
| Context | `{name}-context.tsx` |

### Variable Naming Rules (Class-bound variables)

- Variables instantiated from a class MUST be named as a concise,
  lowercase, snake_case derivative of the class name.
- The variable name MUST preserve the domain context of the class.
- The role suffix MUST match the layer or responsibility:
  - Repository → *_repo
  - Service → *_service
  - Task → *_task
  - Client / Adapter → *_client

## 4. New Feature Checklist

### Backend
- [ ] `app/entities/{resource}.py`
- [ ] `app/dtos/{resource}.py`
- [ ] `app/repositories/{resource}_repository.py`
- [ ] `app/services/{resource}_service.py`
- [ ] `app/api/{resource}.py`
- [ ] Update `app/main.py` (register router)
- [ ] Update `app/dtos/__init__.py`

### Frontend
- [ ] `src/types/index.ts`
- [ ] `src/lib/api.ts`
- [ ] `src/app/(app)/{resource}/page.tsx`

---

## 5. Import Rules

```python
# 1. Standard library
from datetime import datetime
from typing import Optional

# 2. Third-party
from fastapi import HTTPException
from pymongo.database import Database

# 3. Local entities
from app.entities.dataset import DatasetProject

# 4. Local repositories
from app.repositories.dataset_repository import DatasetRepository

# 5. Local dtos
from app.dtos import DatasetResponse
```

**Avoid Circular Imports:**
- Entity ❌ DTO
- Repository ❌ Service
- DTO ❌ Entity (chỉ dùng base types)