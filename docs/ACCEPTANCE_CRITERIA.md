# Acceptance Criteria (AC)

## Phase 1: Core Crawling & Export (MVP)

**Feature 1: Quản lý Crawl Job Cơ Bản & Xác định Critical Fields**
- **AC1:** Người dùng Admin có thể tạo một Crawl Job mới từ giao diện "Create Crawl Job".
- **AC2:** Hệ thống hỗ trợ chức năng "Suggest Fields by AI" bằng cách tải file clean mẫu để AI đề xuất Critical Fields.
- **AC3:** Người dùng bắt buộc phải chốt danh sách **Critical Fields**. Số lượng fields giới hạn: Minimum 3, Maximum 10 (MVP) / 15 (Production).
- **AC4:** Nếu Nguồn dữ liệu không hỗ trợ trường được chọn, hệ thống phải hiển thị cảnh báo chặn hoặc disable trường đó trên giao diện.
- **AC5:** Sau khi bấm Start, Job phải chuyển trạng thái thành `Queued` và hiển thị trên màn hình danh sách Jobs.

**Feature 2: Crawling & Raw Data Storage**
- **AC1:** Hệ thống (Backend worker) nhận cấu hình job và thực thi việc lấy dữ liệu (crawling).
- **AC2:** **Tất cả dữ liệu** bao gồm Critical và Non-critical fields đều được lưu trữ trong Database dưới dạng JSON (bảng `raw_records`) với đầy đủ các trường `job_id`, `country`, `source_name`, `raw_payload`.
- **AC3:** Màn hình Job Detail hiển thị tổng số records crawl được và hiển thị bảng preview `raw_payload`.
- **AC4:** Hỗ trợ tính năng Retry nếu crawl gặp lỗi (timeout, captcha) cơ bản.

**Feature 3: Export MVP**
- **AC1:** Trên Job Detail, người dùng có thể xuất dữ liệu thành file `.csv` hoặc `.xlsx`.
- **AC2:** File export phải khớp với **Clean Template Schema** đã cấu hình cho job, bao gồm: tên cột, thứ tự cột và kiểu dữ liệu cơ bản.
- **AC3:** Các Critical Fields đã chọn ở Feature 1 phải được map hợp lệ vào Clean Template Schema trước khi export.
- **AC4:** Nếu có field được chọn nhưng không tồn tại trong Clean Template Schema, hệ thống phải chặn export hoặc yêu cầu người dùng cập nhật template/schema mapping trước khi tiếp tục.
- **AC5:** Các cột metadata như `confidence_score`, `review_status`, `source_url` chỉ được thêm vào file export khi người dùng bật tùy chọn include metadata.

---

## Phase 2: AI Review & Validation

**Feature 4: AI Extraction & Confidence Scoring (Dành riêng cho Critical Fields)**
- **AC1:** Khi Job ở trạng thái `Extracting`, hệ thống sử dụng AI model trích xuất **chỉ các Critical Fields** từ `raw_payload`. (Bỏ qua non-critical fields để tránh hallucination).
- **AC2:** Mỗi giá trị trường trích xuất phải đính kèm một `confidence_score` từ 0.0 đến 1.0.
- **AC3:** Các bản ghi được lưu vào bảng `extracted_fields` bao gồm `raw_value` và `extracted_value`.

**Feature 5: Rule-based Validation**
- **AC1:** Sau khi trích xuất, dữ liệu Critical Fields phải qua bước Validation Engine (kiểm tra định dạng email, phone, độ dài tax code...).
- **AC2:** Các bản ghi không hợp lệ hoặc có `confidence_score` dưới ngưỡng cho phép (VD: <0.85) phải bị đánh dấu trạng thái `needs_review`.

**Feature 6: Review Queue Interface**
- **AC1:** Màn hình Review Queue hiển thị danh sách các bản ghi `needs_review` cùng với lý do (VD: "Missing ward", "Format error").
- **AC2:** Người dùng vận hành (Standard User / Data Operator) hoặc Admin có thể bấm `Accept suggestion`, `Edit manually` (và nhập giá trị mới), hoặc `Reject record`.
- **AC3:** Lịch sử hành động review (action, old_value, new_value, user_id) phải được ghi vào bảng `review_actions`.
- **AC4:** Khi 100% bản ghi `needs_review` được xử lý, trạng thái Job tự động chuyển sang `Cleaning`.

---

## Phase 3: Clean Data & Compare

**Feature 7: Generate Clean Data**
- **AC1:** Khi Job ở trạng thái `Cleaning`, hệ thống tạo bản ghi sạch (Clean record) bằng cách ghép nối các trường đã được AI trích xuất (và User duyệt).
- **AC2:** Lưu bản ghi sạch vào bảng `clean_records` với `quality_score` được tính toán.

**Feature 8: Before/After Comparison**
- **AC1:** Màn hình "Clean Data" hiển thị bảng so sánh giá trị Raw (trước) và Clean (sau) của các bản ghi.
- **AC2:** Hệ thống hiển thị rõ ràng loại thay đổi (`Standardized`, `Normalized`, `User verified`, v.v.).
- **AC3:** Bảng tóm tắt Data Quality Score hiển thị tỷ lệ % Completeness của từng trường.

---

## Phase 4: Backend Import Automation

**Feature 9: Import Readiness Check**
- **AC1:** Trước khi import, hệ thống phải thực hiện checklist: Các trường bắt buộc (Required fields) không bị null, format ID không trùng lặp (No duplicate PK).
- **AC2:** Nếu checklist thất bại, trạng thái Import báo "Not Ready", nút Import bị mờ.
- **AC3:** Nếu checklist thành công (hoặc có cảnh báo nhẹ), trạng thái báo "Ready with warnings" và cho phép Import.

**Feature 10: Import Backend API**
- **AC1:** Khi người dùng bấm `Import valid records only`, hệ thống gọi API `POST` đến Backend đích (target system) với tập dữ liệu Clean Data.
- **AC2:** API phải xử lý idempotency (VD: skip on duplicate hoặc upsert dựa vào ID/Tax code).
- **AC3:** Sau khi gọi xong, hệ thống lưu kết quả (tổng import, thành công, lỗi) vào bảng `import_logs`.
- **AC4:** Màn hình Logs hiển thị báo cáo chi tiết về tiến trình import và lỗi API nếu có.
