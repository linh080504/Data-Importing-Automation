# System Architecture Document

## 1. Mục tiêu kiến trúc
Hệ thống được thiết kế theo hướng **Data Operations Platform**, hỗ trợ tự động hóa toàn bộ vòng đời dữ liệu: crawl -> extract -> validate -> human review -> clean -> export/import. Kiến trúc phải đảm bảo:
- Dễ mở rộng cho nhiều quốc gia / nhiều nguồn.
- AI chỉ tập trung vào các `Critical Fields` để giảm hallucination.
- Cho phép Human-in-the-loop ở các bước confidence thấp.
- Hỗ trợ dữ liệu luôn thay đổi bằng cơ chế `Hash Change Detection` + `UPSERT`.
- Có thể điều phối workflow trên **n8n**.

## 2. Kiến trúc tổng thể
```text
[Next.js Dashboard]
       ↓
[FastAPI Backend]
       ↓
[PostgreSQL] ←→ [n8n Workflow Engine] ←→ [Crawler/HTTP Sources]
       ↓                         ↓
[File Storage]              [AI Model #1 Extractor]
       ↓                         ↓
[Export Files]              [AI Model #2 Validator/Judge]
```

## 3. Các module chính

### 3.1. Frontend Dashboard (Next.js)
Các màn hình chính:
- Dashboard Home
- Create Crawl Job
- Job List
- Job Detail (Overview / Raw / Review / Clean / Compare / Export-Import / Logs)
- Review Queue
- Data Sources
- Field Configuration
- Settings

### 3.2. Backend API (FastAPI)
Chịu trách nhiệm:
- Quản lý CRUD cho Crawl Jobs.
- Quản lý template/schema mapping.
- Quản lý review actions của user.
- Sinh file export theo template đích.
- Kết nối import API vào backend chính.
- Lưu audit trail và trạng thái job.

### 3.3. n8n Workflow Engine
n8n là bộ điều phối tự động hóa chính cho các tác vụ nền:
- Scheduler/Cron chạy crawling định kỳ.
- Gọi nguồn dữ liệu qua HTTP/API/file.
- Tính hash của record để phát hiện thay đổi.
- Gọi AI #1 để extract Critical Fields.
- Gọi AI #2 để validate/chấm confidence.
- Tự động đẩy record confidence >= threshold vào DB.
- Đẩy các record không chắc chắn vào Review Queue.

### 3.4. AI Layer
#### AI #1 – Extractor
- Input: raw HTML/text/API payload.
- Output: JSON chứa chỉ các Critical Fields.
- Có schema cứng để tránh sinh text tự do.

#### AI #2 – Validator/Judge
- Input: raw content + JSON từ AI #1.
- Output: JSON đánh giá từng field + confidence score + corrected value nếu cần.
- Dùng để cross-check độ chính xác trước khi import.

### 3.5. Data Storage
- `raw_records`: lưu toàn bộ dữ liệu gốc (critical + non-critical).
- `clean_records`: lưu dữ liệu đã qua AI/review và dùng để export/import.
- `ai_extraction_logs`: lưu kết quả AI #1, AI #2 để audit/debug.
- `review_actions`: lịch sử chỉnh sửa của user.
- `import_logs`: kết quả import cuối cùng.

## 4. Luồng dữ liệu chuẩn
1. User tạo Crawl Job, chọn country/source.
2. Upload file clean mẫu nếu cần.
3. AI + Rule + User xác định 5-10 Critical Fields.
4. n8n chạy crawl lấy raw data.
5. Hệ thống tính hash, bỏ qua các record không đổi.
6. AI #1 extract Critical Fields ra JSON.
7. Rule-based validation chạy trước.
8. AI #2 cross-check + chấm confidence.
9. Nếu confidence đạt ngưỡng -> UPSERT vào `clean_records`.
10. Nếu confidence thấp -> đưa vào `Review Queue`.
11. User review xong -> update lại `clean_records`.
12. Backend sinh file export cuối cùng theo đúng template import (vd: 21 cột của `University_Import_Clean-7.csv`).
13. User export file hoặc import API trực tiếp.

## 5. Kiến trúc Export Mapping
Đây là phần rất quan trọng:
- **Clean Template Schema** là schema đích để import vào hệ thống.
- **Critical Fields** là tập nhỏ field AI và User tập trung xử lý.
- Khi export:
  - Các cột tương ứng với Critical Fields: lấy từ `clean_records`.
  - Các cột không thuộc Critical Fields: 
    - fill mặc định (0/null/false), hoặc
    - sinh bằng rule-based script (vd `slug` từ `name`).
- Nhờ vậy file cuối cùng luôn đúng schema import nhưng AI không bị ép suy luận mọi cột.

## 6. Quy tắc Confidence & Auto-Approval
Đề xuất:
- Field-level confidence: mỗi field có điểm riêng.
- Record-level confidence: tính trọng số từ các Critical Fields.
- Chỉ auto-approve nếu:
  - `overall_confidence >= 0.85`
  - không có required critical field nào dưới `0.80`
  - không vi phạm hard validation rules
- Nếu không đạt, record phải vào Review Queue.

## 7. Khả năng mở rộng
- Thêm nguồn mới bằng cách thêm cấu hình source + mapping fields.
- Thêm quốc gia mới bằng rules/template riêng.
- Có thể thay AI model ở lớp Extractor/Validator mà không đổi kiến trúc tổng.
- Có thể chuyển từ export-file MVP sang direct import production mà không phải viết lại toàn bộ pipeline.