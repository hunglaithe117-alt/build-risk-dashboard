---
description: Quy tắc kiến trúc cho Build Risk Dashboard
---

# 📘 Project Instruction Manual & Anti-Gravity Rules

Tài liệu này là nguồn sự thật duy nhất (Single Source of Truth) cho các quy tắc kiến trúc và tiêu chuẩn code trong dự án.

## 🛠 1. Nguyên tắc Anti-Gravity (Thực thi tức thì)

Đây là luật quan trọng nhất để duy trì tốc độ phát triển và chất lượng code:

* **Check-First Policy**: Trước khi tạo bất kỳ hàm mới nào, hãy quét codebase để đảm bảo không tái phát minh bánh xe.
* **No Stubs/Placeholders**: Cấm sử dụng `pass`, `...`, hoặc `raise NotImplementedError`.
* **Full Implementation**: Khi một hàm được khai báo, logic xử lý bên trong **phải được viết hoàn chỉnh ngay lập tức**.
* **Context Awareness**: AI không được phép tạo ra các hàm "rỗng" để chờ người dùng điền vào. Nếu thiếu thông tin logic, phải yêu cầu người dùng làm rõ trước khi viết code.

---

## 🏗 2. Cấu trúc Lớp Backend (Layered Architecture)

Luồng dữ liệu: **API ↔ Service ↔ Repository ↔ Database**

### **API Layer (`app/api/`)**

* **Nhiệm vụ**: Routes, Validation (DTOs), Authentication.
* **Quy tắc**: Chỉ gọi Service. Tuyệt đối không query DB hoặc xử lý logic tại đây.

### **Service Layer (`app/services/`)**

* **Nhiệm vụ**: Chứa toàn bộ Business Logic. Điều phối các Repository.
* **Quy tắc**: Chuyển đổi Entity sang DTO tại đây. Xử lý lỗi bằng `HTTPException`.

### **Repository Layer (`app/repositories/`)**

* **Nhiệm vụ**: Chỉ chứa truy vấn MongoDB. Kế thừa từ `BaseRepository`.
* **Quy tắc**: Trả về Entity Model. Không xử lý logic nghiệp vụ.

---

## 🏷️ 3. Quy tắc đặt tên biến TƯỜNG MINH (Explicit Naming)

Nghiêm cấm đặt tên biến chung chung hoặc viết tắt. Tên biến phải tự giải thích được ý nghĩa và phạm vi của nó.

### **A. Biến Logic & Thực thể (Entities)**

* ❌ **Sai**: `data`, `res`, `obj`, `item`, `d`, `temp`.
* ✅ **Đúng**: `dataset_list`, `user_profile`, `validation_result`, `pending_task`.

### **B. Quản lý ID (Critical)**

Tuyệt đối không dùng tên `id` đơn lẻ. Phải dùng tên định danh cụ thể để tránh nhầm lẫn giữa các loại ID:

* **Dạng ObjectId (MongoDB)**: `{entity}_id` (ví dụ: `raw_build_run_id`, `user_id`).
* **Dạng chuỗi hệ thống ngoài**: `{provider}_{entity}_id` (ví dụ: `github_run_id`, `circleci_job_id`).
* **ID Logic/Phụ**: `model_training_id`, `config_version_id`.

### **C. Biến Class (Class-bound variables)**

Tên biến thực thể hóa từ Class phải có hậu tố phản ánh Layer:

* **Repository**: `{domain}_repo` (ví dụ: `dataset_repo`, `auth_repo`).
* **Service**: `{domain}_service` (ví dụ: `dataset_service`, `email_service`).
* **Task/Worker**: `{domain}_task` (ví dụ: `sync_github_task`).
* **Client/Adapter**: `{domain}_client` (ví dụ: `s3_client`, `slack_client`).

---

## 📂 4. Cấu trúc File & Thư mục

| Path | Loại File | Quy tắc đặt tên Class |
| --- | --- | --- |
| `app/entities/` | Entity | `NameProject` (e.g., `DatasetProject`) |
| `app/dtos/` | DTO | `NameRequest` / `NameResponse` |
| `app/services/` | Service | `NameService` |
| `app/repositories/` | Repository | `NameRepository` |
| `src/components/` | Frontend | `{Name}.tsx` (PascalCase) |
| `src/hooks/` | Hooks | `use-{name}.ts` (kebab-case) |

---

## 🤖 5. Hướng dẫn cho AI Partner (Prompting)

Khi thực hiện yêu cầu từ người dùng, AI phải:

1. **Read Context**: Đọc file architecture rules này trước khi viết dòng code đầu tiên.
2. **Verify Presence**: Kiểm tra xem class/method đã tồn tại trong các file tương ứng chưa để tránh viết đè hoặc duplicate.
3. **Explicit Refactoring**: Nếu người dùng đưa vào mã giả hoặc tên biến sai quy tắc (như `id`), AI phải tự động sửa lại thành tên tường minh (`dataset_id`) trong kết quả cuối cùng.
4. **Full Implementation**: Viết code hoàn chỉnh cho các lớp (API, Service, Repo) trong một lần phản hồi. **Tuyệt đối không dùng `pass` hoặc `// Logic here**`. Nếu không biết logic, AI phải hỏi để hiểu trước khi viết.