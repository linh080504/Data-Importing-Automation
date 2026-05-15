# Thiết kế Luồng Tự động hóa n8n & AI Cross-Validation

Tài liệu này mô tả luồng chạy tự động hóa (Automation Workflow) trên n8n, cơ chế dùng 2 AI đánh giá chéo bằng JSON, và chiến lược cập nhật dữ liệu liên tục (UPSERT).

## 1. Đánh giá về việc sử dụng JSON (Structured Output)
Nhận định của bạn về việc "quy về JSON sẽ chính xác hơn" là **hoàn toàn chính xác và là Best Practice hiện tại**.
- Các mô hình AI hiện đại (GPT-4o, Claude 3.5) được huấn luyện rất sâu về cấu trúc JSON/Code.
- Khi ép AI trả về dữ liệu theo một **JSON Schema cố định** (chức năng Structured Output), AI không bị lan man, không sinh ra text giải thích rác, và bắt buộc phải tư duy theo từng trường (field). 
- JSON giúp n8n dễ dàng nội suy (parse/map) dữ liệu từ node này sang node khác mà không cần viết code regex phức tạp.

## 2. Chiến lược xử lý Dữ liệu làm mới liên tục (Continuous Updates)
Vì dữ liệu luôn thay đổi (công ty đổi địa chỉ, đổi số điện thoại...), luồng hệ thống KHÔNG THỂ chỉ là INSERT (thêm mới), mà phải là **UPSERT** (Cập nhật nếu đã có, Thêm mới nếu chưa có).
- **Unique Key (Khóa định danh):** Để cập nhật đúng, hệ thống phải xác định được 1-2 trường làm "khóa". Ví dụ: `tax_code` (Mã số thuế) hoặc `company_id`.
- **Hash/Fingerprint so sánh:** Hệ thống tạo ra một mã băm (MD5/SHA) của toàn bộ record json. Lần sau crawl lại, nếu mã băm không đổi -> Dữ liệu không đổi -> Bỏ qua không tốn phí chạy AI. Nếu mã băm đổi -> Chạy AI extract -> Update vào DB.

---

## 3. Sơ đồ Luồng n8n (n8n Workflow)

### Giai đoạn 1: Thu thập & Lọc trùng
1. **[Trigger] Cron Schedule:** Chạy định kỳ (ví dụ 1 lần/ngày). Hoặc **Webhook** gọi từ hệ thống khác.
2. **[HTTP Request Node] Crawler:** Gọi API hoặc fetch HTML từ nguồn dữ liệu.
3. **[Code Node] Format & Hash:** 
   - Chia nhỏ dữ liệu thành từng record (nếu lấy 1 list).
   - Tính toán `record_hash` (ví dụ Hash MD5 của toàn bộ chữ trong record).
4. **[Postgres Node] Check Hash (Deduplication):** 
   - Kiểm tra `record_hash` này đã có trong DB chưa? 
   - Nếu Có -> Bỏ qua (Data không đổi). 
   - Nếu Chưa/Khác -> Đi tiếp sang Giai đoạn AI.

### Giai đoạn 2: AI Cross-Validation (Đánh giá chéo)
5. **[LLM Node #1] AI Extractor (Giai đoạn Extract):**
   - **Input:** Raw Text/HTML.
   - **Task:** Yêu cầu AI bóc tách Critical Fields.
   - **Output Format:** Ép AI trả về chuẩn JSON.
   - *Ví dụ output JSON từ AI 1:*
     ```json
     {
       "tax_code": "0312345678",
       "company_name": "Công ty TNHH AI VN",
       "address": "123 Đường A, HCM"
     }
     ```

6. **[LLM Node #2] AI Validator (Giai đoạn Judge):**
   - Đây là điểm mấu chốt để đạt độ chính xác > 85%.
   - **Input:** Đưa cho AI #2 hai thứ: (1) Raw Text gốc + (2) Chuỗi JSON mà AI #1 vừa tạo ra.
   - **Task:** "Bạn là Data QA. Hãy đối chiếu JSON của AI #1 với Text Gốc. Từng trường (field) có chính xác không? Nếu sai, hãy sửa lại. Chấm điểm tự tin (0-100%)."
   - **Output Format:** JSON Strict Schema.
   - *Ví dụ output JSON từ AI 2:*
     ```json
     {
       "fields_validation": {
         "tax_code": { "is_correct": true, "corrected_value": null, "confidence": 98 },
         "company_name": { "is_correct": true, "corrected_value": null, "confidence": 95 },
         "address": { "is_correct": false, "corrected_value": "123 Đường A, Phường 2, HCM", "confidence": 88 }
       },
       "overall_confidence": 93,
       "status": "APPROVED"
     }
     ```

### Giai đoạn 3: Phân nhánh & UPSERT Database
7. **[Switch Node / If Node]:**
   - **Rule 1:** `json.overall_confidence >= 85` AND không có field nào bị thiếu trầm trọng.
   - **Route A (Auto Import):** Đi vào luồng tự động cập nhật Database.
   - **Route B (Human Review):** Đi vào DB nhưng đánh cờ `status = "NEEDS_REVIEW"` để hiển thị lên Dashboard cho người dùng duyệt.

8. **[Postgres Node] Database UPSERT:**
   - **Thao tác:** Thực hiện lệnh `INSERT INTO ... ON CONFLICT (tax_code) DO UPDATE SET ...`
   - Cập nhật các trường dữ liệu và `updated_at = NOW()`.

---

## 4. Ưu điểm của kiến trúc này
1. **Tiết kiệm Token (Chi phí):** Nhờ cơ chế băm (Hashing) ở Bước 3, ta chỉ tốn tiền chạy AI 1 & AI 2 khi dữ liệu của công ty đó THỰC SỰ có sự thay đổi.
2. **Không Hallucinate:** Nhờ ép JSON Schema chặt chẽ. AI không thể bịa ra cột mới hay viết dài dòng.
3. **Độ chính xác cao:** AI 2 đóng vai trò kiểm duyệt độc lập (Cross-check), tìm ra những lỗi sơ đẳng của AI 1 (ví dụ cắt thiếu chữ).
4. **Automation 100% (Cho dữ liệu sạch):** Với các record đạt >85% confidence, nó tự chui vào Database và update luôn mà con người không cần động tay, chỉ những case mập mờ mới đẩy lên giao diện Dashboard.