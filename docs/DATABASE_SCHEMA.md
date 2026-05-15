# Database Schema Thiết kế cho Automation & Upsert

Dưới đây là thiết kế các bảng (PostgreSQL) đảm bảo đáp ứng được tính năng UPSERT (cập nhật liên tục khi dữ liệu làm mới) và quản lý tiến trình của n8n + AI.

## 1. Table `data_sources` (Quản lý Nguồn)
Lưu thông tin về nguồn dữ liệu để n8n lấy config gọi API/Crawl.

```sql
CREATE TABLE data_sources (
    id UUID PRIMARY KEY,
    country VARCHAR(50) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    config JSONB, -- Cấu hình n8n dùng để crawl
    critical_fields JSONB, -- Mảng các fields trọng tâm
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 2. Table `raw_records` (Lưu Dữ liệu Thô - Không sợ mất mát)
Dùng để lưu tất cả dữ liệu crawl về. Cung cấp cơ chế Hashing để chống chạy lại AI dư thừa.

```sql
CREATE TABLE raw_records (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES data_sources(id),
    unique_key VARCHAR(100) NOT NULL, -- VD: tax_code, url hash
    record_hash VARCHAR(64) NOT NULL, -- MD5 của raw_payload để check update
    raw_payload JSONB NOT NULL,       -- Toàn bộ data (critical + non-critical)
    crawled_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (source_id, unique_key)    -- Quan trọng cho UPSERT
);
```

## 3. Table `ai_extraction_logs` (Lịch sử đánh giá chéo của 2 AI)
Table này lưu lại quá trình làm việc của n8n, hỗ trợ debug xem vì sao AI chấm điểm thấp.

```sql
CREATE TABLE ai_extraction_logs (
    id UUID PRIMARY KEY,
    raw_record_id UUID REFERENCES raw_records(id),
    ai_1_payload JSONB,       -- Kết quả AI Extract
    ai_2_validation JSONB,    -- Kết quả AI Judge
    overall_confidence INT,   -- Thang 0-100
    processed_at TIMESTAMP DEFAULT NOW()
);
```

## 4. Table `clean_records` (Bảng Dữ liệu Cuối Cùng - Import/Export)
Bảng này sẽ liên tục nhận thao tác UPSERT từ n8n (khi >= 85%) hoặc từ Dashboard (khi user sửa tay).

```sql
CREATE TABLE clean_records (
    id UUID PRIMARY KEY,
    raw_record_id UUID REFERENCES raw_records(id),
    unique_key VARCHAR(100) NOT NULL, -- Khóa chính nghiệp vụ (VD: tax_code)
    
    -- Các cột dữ liệu chính (được map từ critical fields)
    company_name VARCHAR(255),
    tax_code VARCHAR(50),
    address TEXT,
    email VARCHAR(100),
    phone VARCHAR(50),
    clean_payload JSONB, -- Chứa các data linh hoạt khác sau clean
    
    -- Quản lý luồng
    quality_score INT,              -- Lấy từ overall_confidence
    status VARCHAR(20) DEFAULT 'NEEDS_REVIEW', -- 'APPROVED', 'NEEDS_REVIEW', 'REJECTED'
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE (unique_key) -- Để thực hiện ON CONFLICT DO UPDATE
);
```

## 5. Cơ chế UPSERT trong Database (Từ góc nhìn n8n)

Khi n8n đẩy dữ liệu vào Postgres node, nó sẽ dùng lệnh tương tự như sau để đảm bảo dữ liệu luôn được "Làm mới":

```sql
INSERT INTO clean_records (unique_key, company_name, tax_code, address, quality_score, status)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (unique_key) 
DO UPDATE SET 
    company_name = EXCLUDED.company_name,
    address = EXCLUDED.address,
    quality_score = EXCLUDED.quality_score,
    status = EXCLUDED.status,
    updated_at = NOW();
```
*Lưu ý: Nếu một record chạy lại, điểm `quality_score` mới sẽ đè lên điểm cũ, đảm bảo hệ thống phản ánh đúng chất lượng của version dữ liệu mới nhất.*