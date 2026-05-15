# Product Requirements Document (PRD)

## 1. Mục tiêu hệ thống (Product Vision)
**Tên sản phẩm:** Automated Data Crawling, Cleaning, Review & Import Dashboard

Hệ thống cung cấp giải pháp end-to-end cho luồng dữ liệu (Data Pipeline), cho phép người dùng vận hành tự động quá trình thu thập (crawl), làm sạch (clean), kiểm tra (review) và xuất/nhập (export/import) dữ liệu từ nhiều quốc gia và nguồn khác nhau. 

Đặc điểm nổi bật:
- Dành cho non-technical users thông qua UI/UX trực quan.
- Có AI hỗ trợ trích xuất (extract) và mapping dữ liệu.
- Cho phép Human-in-the-loop (Người dùng review) để đảm bảo chất lượng dữ liệu cao nhất.

## 2. Đối tượng người dùng (User Personas)
Trong MVP, hệ thống ưu tiên mô hình role đơn giản theo mức độ thao tác thay vì phân vai chuyên môn phức tạp.

1. **Standard User / Data Operator:** Người dùng chính của hệ thống, có thể thực hiện toàn bộ luồng vận hành dữ liệu hằng ngày: tạo crawl job, chọn country/source/critical fields, chạy crawl, review/chỉnh dữ liệu, clean, compare, export, và import (nếu được bật quyền import).
2. **Admin / System Configurator:** Có toàn bộ quyền của Standard User, đồng thời quản trị cấu hình hệ thống: data source, field schema, validation rules, import mapping, tài khoản người dùng, và system logs.
3. **Optional Import Approver (không bắt buộc trong MVP):** Chỉ dùng nếu doanh nghiệp muốn tách quyền duyệt import. Role này chỉ kiểm tra import readiness, approve import, và theo dõi import history.
4. **Backend System:** Hệ thống lưu trữ cuối (Python/FastAPI/Django) nhận dữ liệu từ Dashboard này thông qua API.

## 3. Tổng quan luồng dữ liệu (Data Pipeline Overview)
1. **Setup:** Người dùng chọn Quốc gia -> Nguồn -> Trường dữ liệu (Fields).
2. **Crawl:** Crawler thu thập dữ liệu thô (Raw Data).
3. **Extract & Validate:** AI trích xuất thông tin. Validation Engine kiểm tra theo rules chuẩn.
4. **Human Review:** Các dữ liệu không chắc chắn (low confidence, conflict, format error) đưa vào Queue cho người dùng đánh giá.
5. **Clean:** Pipeline tự động chuẩn hóa dữ liệu.
6. **Compare & Analytics:** So sánh Before/After, tính toán Data Quality Score.
7. **Action:** Import vào Backend nội bộ hoặc Export ra CSV/Excel.

## 4. Danh sách tính năng (Feature List)

### 4.1. Dashboard Điều khiển Crawl & Critical Fields Configuration
- Giao diện **Create Crawl Job** với tùy chọn Quốc gia, Nguồn (Sources).
- **Cơ chế xác định Critical Fields (Trường trọng tâm):**
  - **Rule cố định:** Tự động load các field bắt buộc theo từng quốc gia/source.
  - **AI gợi ý:** AI phân tích file clean mẫu/cấu trúc dữ liệu để đề xuất top fields có giá trị cao.
  - **User duyệt:** Người dùng quyết định cuối cùng việc chọn/bỏ chọn fields.
- **Giới hạn số lượng Critical Fields:**
  - Tối thiểu: 3 fields.
  - Tối đa (MVP): 10 fields.
  - Tối đa (Production): 15 fields.
- **Xử lý phân loại Fields:**
  - **Critical Fields:** Được AI extract sâu, tính confidence score, chạy qua validation, đưa vào review queue và clean triệt để.
  - **Non-critical Fields:** Vẫn được lưu trong `raw_payload` (để dùng sau này nếu cần thiết), nhưng bỏ qua AI extract/review để giảm hallucination và tối ưu tài nguyên.
- Hỗ trợ các Crawl mode: Mới (New), Toàn bộ (Re-crawl all), Bổ sung (Update missing fields).
- Toggle bật tắt AI Assist.
- Cảnh báo động khi thêm/bớt Fields (VD: Báo người dùng nếu nguồn không hỗ trợ field mới).

### 4.2. Khối AI Review & Validation
- Tự động gán `Confidence Score` (0.0 - 1.0) cho từng field sau khi extract bằng AI.
- Đưa các records có vấn đề (Missing, Low confidence, Format error, Duplicate, Conflict) vào **Review Queue**.
- Giao diện thao tác cho Reviewer:
  - Chấp nhận giá trị AI đề xuất (Accept suggestion).
  - Sửa tay (Edit manually).
  - Đánh dấu chưa rõ (Mark as unknown) hoặc Loại bỏ (Reject record/field).

### 4.3. Khối Clean Data & So sánh
- Bảng Overview thống kê % Completeness, Số lượng hợp lệ (Valid)/lỗi (Invalid), Điểm chất lượng (Data Quality Score).
- Màn hình so sánh Before/After để xem rõ thay đổi do Clean pipeline/AI thực hiện.
- Import Readiness Check: Đảm bảo điều kiện bắt buộc (Required fields, No Duplicate, Format hợp lệ).

### 4.4. Export & Import Backend
- Export file ra định dạng: `.csv`, `.xlsx`, `.json`.
- **Cơ chế Export/Mapping:** File Export (ví dụ `.csv`) bắt buộc phải chứa đầy đủ tất cả các cột của định dạng Template đích (ví dụ: `University_Import_Clean-7.csv` có 21 cột). 
  - Hệ thống chỉ lấy giá trị từ các **Critical Fields** (đã được AI & User duyệt) để điền vào các cột tương ứng.
  - Các cột **Non-critical fields** sẽ được hệ thống tự động fill bằng giá trị mặc định (Default: `0`, `null`, `false`) hoặc sinh ra bằng Rule-based Script (vd: slugify từ name). Tuyệt đối không dùng AI để extract/suy luận các non-critical fields này để tránh hallucination.
- Export reports: Clean data, Review issue report, Import error report.
- Import API kết nối tới hệ thống Backend (FastAPI) trực tiếp.

### 4.5. Quản lý trạng thái và Audit Trail
- System Audit Logs: Lưu vết toàn bộ hành động (Người crawl, thay đổi của AI, người approve, giá trị cũ/mới).
- Job Tracking: Hiển thị tiến độ của job qua các trạng thái (Queued -> Crawling -> Extracting -> Validating -> Needs Review -> Cleaning -> Ready to Import -> Imported).

## 5. Scope Phân Giai Đoạn (MVP & Rollout)

### Phase 1 (MVP): Core Crawling & Critical Fields Config
- Cấu hình Quốc gia, Nguồn và xác định **Critical Fields** (Tối đa 10).
- Hệ thống hỗ trợ lấy field từ Rule + AI gợi ý + User chốt.
- Chạy Job thu thập Raw Data. Lưu giữ Non-critical fields ở dạng thô.
- Hiển thị bảng Raw Data.
- Tính năng xuất Export ra Excel/CSV.

### Phase 2: AI Review & Validation
- Tích hợp AI Extract field.
- Validation bằng Rule-based và AI (Confidence Score).
- Ra mắt **Review Queue** và các action xử lý lỗi dữ liệu.

### Phase 3: Clean Data & Compare
- Chuẩn hóa (Normalize) dữ liệu thành Clean Data.
- Bảng so sánh Before/After.
- Tính toán điểm Data Quality Score.

### Phase 4: Backend Import Automation
- Mapping Schema.
- Các điều kiện kiểm tra Import Readiness.
- API Direct Import vào Backend.
- Báo cáo lỗi/logs Import.

## 6. Permission Model (MVP)
Trong giai đoạn MVP, hệ thống không yêu cầu phân quyền phức tạp theo chức danh chuyên môn. Mục tiêu là để một người dùng vận hành có thể đi hết luồng crawl → review → clean → export/import mà không bị chặn bởi quá nhiều role trung gian.

### 6.1. Standard User / Data Operator
Quyền:
- Tạo crawl job
- Chọn country, source, critical fields
- Chạy crawl
- Xem raw data
- Xem dữ liệu AI extract
- Review field cần xác nhận
- Chỉnh sửa dữ liệu
- Xem dữ liệu sau clean
- So sánh before/after
- Export file
- Import nếu được bật quyền import

### 6.2. Admin / System Configurator
Quyền:
- Tất cả quyền của Standard User
- Thêm/sửa data source
- Cấu hình field schema
- Cấu hình validation rule
- Cấu hình backend import mapping
- Quản lý tài khoản
- Xem system logs

### 6.3. Optional Import Approver
Không bắt buộc trong MVP. Chỉ dùng khi doanh nghiệp muốn kiểm soát riêng bước import.

Quyền:
- Kiểm tra clean data
- Xem import readiness
- Approve import
- Xem import history

## 7. Kiến trúc hệ thống tham khảo (Technical Stack Suggestion)
- **Frontend:** React / Next.js.
- **Backend:** Python FastAPI.
- **Queue/Worker:** Celery + Redis (cho chạy ngầm Crawl/AI/Clean/Import).
- **Database:** PostgreSQL (Hỗ trợ JSONB lưu Raw payload tốt).
- **Storage:** Local cho MVP, AWS S3 / MinIO cho Production.

## 8. Ghi chú về Role Design
Phân quyền trong MVP nên được giữ ở mức tối thiểu để tránh làm phức tạp trải nghiệm người dùng. Nếu sau này quy trình import cần kiểm soát chặt hơn, có thể bật thêm role Optional Import Approver mà không cần thay đổi toàn bộ kiến trúc sản phẩm.
