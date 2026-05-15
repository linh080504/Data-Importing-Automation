# System API Contract

Tài liệu này định nghĩa các endpoint REST API chính mà hệ thống (Backend FastAPI) sẽ cung cấp cho Frontend (Dashboard) và hệ thống n8n Workflow.

## 1. Cơ bản
- **Base URL**: `/api/v1`
- **Authentication**: Bearer Token (JWT) trong Header `Authorization`
- **Content-Type**: `application/json`

## 2. Quản lý Nguồn & Field Cấu Hình

### Lấy danh sách nguồn theo quốc gia
```http
GET /sources?country={country_code}
```
**Response (200 OK):**
```json
{
  "sources": [
    {
      "id": "src_123",
      "name": "Government Registry",
      "supported_fields": ["name", "tax_code", "address", "website"]
    }
  ]
}
```

### AI Đề xuất Critical Fields (Dựa trên template mẫu)
```http
POST /fields/suggest
```
**Request:**
- File upload (CSV template mẫu) hoặc schema JSON.

**Response (200 OK):**
```json
{
  "suggested_critical_fields": [
    "name", "location", "website", "description", "financials", "admissions_contact"
  ],
  "reasoning": "These fields contain high-value unstructured data that require AI extraction."
}
```

## 3. Crawl Jobs

### Tạo mới Crawl Job
```http
POST /crawl-jobs
```
**Request:**
```json
{
  "country": "Vietnam",
  "source_ids": ["src_123"],
  "critical_fields": ["name", "location", "website", "description"],
  "clean_template_id": "tpl_456", 
  "ai_assist": true
}
```
**Response (201 Created):**
```json
{
  "job_id": "job_789",
  "status": "QUEUED",
  "message": "Job created successfully"
}
```

### Lấy thông tin chi tiết Job
```http
GET /crawl-jobs/{job_id}
```
**Response (200 OK):**
```json
{
  "job_id": "job_789",
  "status": "EXTRACTING",
  "progress": {
    "total_records": 10000,
    "crawled": 10000,
    "extracted": 5000,
    "needs_review": 200,
    "cleaned": 4800
  }
}
```

## 4. Quản lý Review Queue

### Lấy danh sách Record cần Review
```http
GET /crawl-jobs/{job_id}/review-queue?page=1&limit=50
```
**Response (200 OK):**
```json
{
  "total": 200,
  "items": [
    {
      "record_id": "rec_001",
      "fields_to_review": [
        {
          "field_name": "admissions_contact",
          "raw_value": "Contact us at info@univ.edu or +123",
          "suggested_value": "info@univ.edu",
          "confidence": 0.75,
          "reason": "Multiple contact methods found"
        }
      ]
    }
  ]
}
```

### Submit kết quả Review của User
```http
POST /review-actions
```
**Request:**
```json
{
  "record_id": "rec_001",
  "field_name": "admissions_contact",
  "action": "EDIT", 
  "new_value": "info@univ.edu",
  "note": "Verified manually"
}
```
**Response (200 OK):**
```json
{
  "status": "SUCCESS",
  "message": "Review saved and record updated to clean_records"
}
```

## 5. Clean Data & So Sánh

### Xem dữ liệu Before/After
```http
GET /crawl-jobs/{job_id}/compare?page=1&limit=20
```
**Response (200 OK):**
```json
{
  "items": [
    {
      "record_id": "rec_002",
      "company_name": {
        "raw": "vietnam nat univ",
        "clean": "Vietnam National University",
        "change_type": "STANDARDIZED",
        "status": "AUTO_APPROVED"
      }
    }
  ]
}
```

## 6. Export & Import

### Yêu cầu Export File (Theo chuẩn Schema Template)
```http
POST /crawl-jobs/{job_id}/export
```
**Request:**
```json
{
  "format": "csv",
  "include_metadata": false 
}
```
**Response (200 OK):**
```json
{
  "download_url": "https://storage.internal/exports/job_789_clean.csv",
  "schema_used": "University_Import_Clean-7",
  "total_exported": 9800
}
```

### Kích hoạt Direct Import Backend
```http
POST /crawl-jobs/{job_id}/import
```
**Request:**
```json
{
  "target_system": "MAIN_DB_PROD",
  "mode": "VALID_ONLY"
}
```
**Response (202 Accepted):**
```json
{
  "import_task_id": "imp_999",
  "status": "PROCESSING"
}
```

## 7. Webhook cho n8n Workflow (Nội bộ)

### n8n báo cáo kết quả AI Cross-Validation
Đây là endpoint n8n gọi về FastAPI để UPSERT dữ liệu sau khi 2 con AI chấm điểm xong.
```http
POST /internal/webhook/n8n/upsert-record
```
**Request:**
```json
{
  "job_id": "job_789",
  "source_id": "src_123",
  "unique_key": "uni_12345",
  "record_hash": "a1b2c3d4...",
  "raw_payload": { ... },
  "critical_fields_extracted": {
    "name": "Tech University",
    "location": "USA"
  },
  "overall_confidence": 92,
  "status": "APPROVED" 
}
```
**Response (200 OK):**
```json
{
  "action": "UPSERTED",
  "record_id": "rec_003"
}
```