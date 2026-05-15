# User Flow Document

## 1. Flow 1: Create a New Crawl Job & Select Critical Fields
**Người thực hiện:** Standard User / Data Operator

1. Đăng nhập vào Dashboard, chọn menu **"Create Crawl Job"**.
2. **Chọn Quốc Gia (Country):** Mở dropdown và chọn "Vietnam".
3. **Chọn Nguồn (Source):** Hệ thống load danh sách nguồn tương ứng. Chọn "Government Registry".
4. **Xác định Critical Fields (Trường Trọng Tâm):** 
   - Hệ thống tự động tick các Rule-based fields bắt buộc.
   - Nếu có "Clean sample file", User upload file này.
   - Nhấn "Suggest Fields by AI". AI sẽ trả về top fields có giá trị phân tích/import cao.
   - User duyệt lại danh sách: Giữ lại hoặc tick thêm. Hệ thống báo lỗi nếu User chọn > 10 fields (MVP) hoặc < 3 fields.
5. **Xem trước (Preview Schema):** Bấm để xem cấu trúc dữ liệu Critical Fields sẽ trả về (Non-critical fields được ẩn để giảm rối).
6. **Bắt đầu (Start Crawl):** Bấm Start để khởi tạo Job.
7. **Theo dõi Tiến độ:** Hệ thống chuyển sang màn hình **Job Detail** hiển thị trạng thái `Queued` -> `Crawling` -> `Extracting` -> `Validating`.

## 2. Flow 2: Xử lý Review Queue (AI Verification)
**Người thực hiện:** Standard User / Data Operator hoặc Admin / System Configurator

1. Job chuyển sang trạng thái `Needs Review`.
2. User truy cập vào tab **"Review Queue"** của Job đó.
3. User thấy danh sách các bản ghi (records) bị đánh dấu cần kiểm tra:
   - Các issue có thể là: Thiếu dữ liệu, Confidence thấp (< 0.85), sai định dạng.
4. Nhấn vào một Record ID (VD: `VN-000124`) để mở form chi tiết:
   - Hiển thị giá trị gốc (Raw) vs Giá trị AI đề xuất (Suggested).
   - Hiển thị lý do cần review (Ví dụ: "Địa chỉ bị thiếu phường/xã").
5. User thực hiện hành động:
   - **Cách 1:** Bấm `Accept suggestion` nếu AI đề xuất đúng.
   - **Cách 2:** Chọn `Edit manually`, nhập lại text chính xác và lưu.
   - **Cách 3:** Bấm `Reject record` nếu thấy dữ liệu rác.
6. Chuyển sang record tiếp theo cho đến khi xử lý xong queue.

## 3. Flow 3: Clean Data & Compare
**Người thực hiện:** Data Analyst / Data Operator

1. Sau khi Queue được duyệt, Job chuyển qua trạng thái `Cleaning`.
2. Khi hoàn tất, User vào tab **"Clean Data"** / **"Compare"**.
3. Xem bảng so sánh:
   - Cột **Raw Value** (VD: `123 nvc, hcm`).
   - Cột **Clean Value** (VD: `123 Nguyễn Văn Cừ, Hồ Chí Minh`).
   - Cột **Status/Change Type** (VD: `Standardized`).
4. Xem **Data Quality Score** và tỷ lệ **Completeness**. Nếu điểm quá thấp (VD: <60), User có thể quyết định xuất báo cáo phân tích thay vì Import.

## 4. Flow 4: Export & Import Backend
**Người thực hiện:** Standard User / Data Operator (nếu được bật quyền import) hoặc Optional Import Approver

1. Vào tab **"Export/Import"** trong chi tiết Job đã hoàn thành clean.
2. Kiểm tra phần **Import Readiness** (chỉ dựa trên Critical Fields):
   - Xác nhận tất cả checklist xanh (Required critical fields đầy đủ, format chuẩn...).
3. **Thực hiện Action:**
   - **Lựa chọn 1 (Export File):**
     - Đánh dấu chọn format (`.xlsx` hoặc `.csv`).
     - Tick chọn xuất "Clean records only".
     - Bấm tải file về.
   - **Lựa chọn 2 (Direct API Import - Backend):**
     - Bấm `Import valid records only`.
     - Hệ thống gọi API gửi sang Backend chính.
     - Sau khi hoàn tất, hệ thống trả về màn hình **Logs/Report** với thống kê số record đã insert/update/thất bại.
4. Non-critical fields vẫn được giữ trong raw storage để phục vụ audit hoặc mở rộng fields trong lần chạy sau.

## 5. Flow 5: Sửa đổi Fields Job đang có
**Người thực hiện:** Admin / System Configurator

### Trường hợp 1: Thêm Field Mới (Ví dụ thêm "Email")
1. Mở Job cũ, chọn Edit Fields.
2. Tick thêm field "Email".
3. Hệ thống báo động: "Source hiện tại không hỗ trợ Email, cần thêm source Business Directory".
4. User thêm source mới.
5. Hệ thống hỏi: "Bạn muốn Crawl bổ sung (Incremental) hay Crawl lại toàn bộ (Re-crawl)?"
6. User chọn "Crawl bổ sung missing Email". Hệ thống chạy tiếp flow 1 cho riêng trường Email.

### Trường hợp 2: Bỏ Field Không Dùng
1. Mở Job, bỏ tick "Phone".
2. Bấm Save.
3. Hệ thống cảnh báo: "Trường này sẽ không được xử lý và xuất ra nữa. Có tiếp tục?"
4. User bấm Confirm. Data pipeline tự động cập nhật schema clean/export không bao gồm trường Phone (không cần re-crawl).
