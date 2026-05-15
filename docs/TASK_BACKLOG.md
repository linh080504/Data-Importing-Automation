# Implementation Task Backlog

Tài liệu này chuyển toàn bộ spec thành backlog triển khai nhỏ để AI Coder, AI Reviewer và AI QA có thể làm tuần tự, không bị vượt scope.

## Nguyên tắc chia task
- Mỗi task chỉ nên giải quyết một mục tiêu rõ ràng.
- Không đổi architecture/API contract nếu chưa có phê duyệt.
- Ưu tiên hoàn thành luồng MVP trước: crawl → review → clean → export.
- Direct import backend và tối ưu automation nâng cao làm sau khi core flow ổn định.
- AI chỉ xử lý Critical Fields; non-critical fields đi theo template mapping/default/rule-based.

## Sprint 0 — Foundation

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T00-01 | Khởi tạo backend skeleton | Tạo khung FastAPI app, config, healthcheck, env loading | backend/app | None | App chạy được, có `/health` | smoke test health endpoint | P0 |
| T00-02 | Khởi tạo frontend skeleton | Tạo khung Next.js dashboard, layout, routing cơ bản | frontend/app | None | Frontend chạy được với sidebar và route rỗng | render test layout | P0 |
| T00-03 | Tạo PostgreSQL schema nền | Tạo migration cho `data_sources`, `raw_records`, `clean_records`, `review_actions`, `ai_extraction_logs`, `import_logs` | backend/alembic | T00-01 | Migrate thành công trên DB trống | migration test | P0 |
| T00-04 | Tạo cấu hình shared schema | Định nghĩa enum/trạng thái job, review status, import status dùng chung | backend/app/core | T00-01 | Enum dùng được xuyên suốt backend | unit test enum serialization | P1 |
| T00-05 | Tạo .env.example và config loading | Chuẩn hóa biến môi trường cho DB, AI, storage, n8n webhook | root/backend | T00-01 | Có `.env.example`, app fail rõ khi thiếu env bắt buộc | config unit test | P0 |

## Sprint 1 — Source, Template, Critical Fields

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T01-01 | CRUD data sources | Tạo API quản lý nguồn dữ liệu theo country và supported fields | backend/api/sources | T00-03 | Tạo/sửa/xem source được | API integration test | P0 |
| T01-02 | Lưu clean template schema | Upload và parse template CSV mẫu như `University_Import_Clean-7.csv` để lưu schema cột | backend/api/templates | T00-03 | Lưu được tên cột, thứ tự cột, metadata template | file parsing test | P0 |
| T01-03 | API suggest critical fields | Tạo endpoint nhận template/schema và trả gợi ý critical fields | backend/api/fields | T01-02 | Trả danh sách gợi ý, min/max được validate | API test + validation test | P0 |
| T01-04 | Rule engine cho required fields | Xác định fields bắt buộc theo source/country | backend/services/rules | T01-01 | Rule-based required fields được merge với AI suggestion | unit test rules | P0 |
| T01-05 | UI create crawl job | Form chọn country, source, template, critical fields | frontend/app/create-job | T01-01,T01-02,T01-03 | User tạo job được từ UI | component + flow test | P0 |
| T01-06 | Validation critical field limits | Chặn dưới 3, trên 10 field trong MVP | frontend/backend | T01-05 | Không tạo job khi vượt giới hạn | unit + e2e validation test | P0 |

## Sprint 2 — Crawl Job và Raw Data

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T02-01 | Tạo crawl job API | Tạo `POST /crawl-jobs` và `GET /crawl-jobs/{id}` | backend/api/crawl_jobs | T01-05 | Job tạo được, status `QUEUED` | API integration test | P0 |
| T02-02 | Lưu job config | Persist source IDs, critical fields, template ID, ai_assist | backend/models | T02-01 | Job config đọc lại đúng | repository test | P0 |
| T02-03 | n8n webhook trigger | Endpoint để backend kích hoạt hoặc nhận callback từ n8n | backend/api/internal | T02-01 | Nhận payload hợp lệ, auth nội bộ cơ bản | webhook API test | P1 |
| T02-04 | Raw record ingestion | Lưu raw payload, unique key, record hash | backend/services/raw_ingest | T00-03 | Raw records được upsert đúng | service test | P0 |
| T02-05 | Hash change detection | Bỏ qua record không đổi, đánh dấu record thay đổi | backend/services/dedup | T02-04 | Record hash giống thì skip, khác thì process | unit test hash logic | P0 |
| T02-06 | Job detail progress API | Trả progress crawl/extract/review/clean/import | backend/api/crawl_jobs | T02-01 | UI đọc được progress | API test | P1 |

## Sprint 3 — AI Extraction và Validation

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T03-01 | JSON schema cho AI output | Định nghĩa schema cứng cho extractor/validator outputs | backend/app/schemas | T02-04 | Validate được output AI | schema unit test | P0 |
| T03-02 | AI extractor service | Gọi AI #1 chỉ extract critical fields | backend/services/ai_extractor | T03-01 | Output JSON hợp lệ, không có non-critical fields | mocked service test | P0 |
| T03-03 | Rule-based validation service | Validate email/phone/url/required field | backend/services/validator | T03-02 | Hard rules chạy trước AI judge | unit test rule cases | P0 |
| T03-04 | AI validator/judge service | Gọi AI #2 cross-check raw text với AI #1 output | backend/services/ai_judge | T03-02,T03-03 | Trả field confidence + overall confidence | mocked service test | P0 |
| T03-05 | Confidence scoring engine | Tính weighted record confidence từ critical fields | backend/services/scoring | T03-04 | Có rule >=0.85 overall và required fields >=0.80 | unit test weighted score | P0 |
| T03-06 | AI extraction logs | Lưu ai_1_payload, ai_2_validation, confidence | backend/services/logging | T03-04 | Audit/debug xem được từng lần AI chạy | repository test | P1 |

## Sprint 4 — Review Queue và Human-in-the-loop

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T04-01 | Review queue API | Tạo `GET /crawl-jobs/{id}/review-queue` | backend/api/review | T03-05 | Trả record cần review theo field | API integration test | P0 |
| T04-02 | Submit review action API | Tạo `POST /review-actions` | backend/api/review | T04-01 | Lưu accept/edit/reject/unknown | API integration test | P0 |
| T04-03 | Review UI list + detail | Màn hình review queue, mở record chi tiết | frontend/app/review | T04-01 | User xem và thao tác review được | component + e2e test | P0 |
| T04-04 | Update clean record after review | Đồng bộ giá trị user duyệt vào `clean_records` | backend/services/review_apply | T04-02 | Clean record cập nhật đúng sau review | service test | P0 |
| T04-05 | Bulk approve action | Duyệt hàng loạt record confidence cao | frontend/backend | T04-03 | Bulk approve hoạt động với bộ lọc phù hợp | API + UI test | P1 |

## Sprint 5 — Clean Data, Compare, Quality Score

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T05-01 | Generate clean data service | Tạo `clean_records` từ AI + review + rules | backend/services/cleaner | T03-05,T04-04 | Clean records sinh ra đúng payload | service test | P0 |
| T05-02 | Compare API | Tạo `GET /crawl-jobs/{id}/compare` | backend/api/compare | T05-01 | Trả before/after theo record/field | API test | P1 |
| T05-03 | Quality score engine | Tính completeness, validity, consistency, uniqueness, review completion | backend/services/quality | T05-01 | Trả điểm tổng và theo field | unit test scoring | P1 |
| T05-04 | Clean/Compare UI | Màn hình clean overview + before/after comparison | frontend/app/compare | T05-02,T05-03 | User xem quality score và thay đổi dữ liệu | component + e2e test | P1 |

## Sprint 6 — Export theo Clean Template Schema

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T06-01 | Template mapping engine | Map critical fields vào clean template schema | backend/services/export_mapping | T01-02,T05-01 | Field được map đúng tên cột/thứ tự cột | unit test mapping | P0 |
| T06-02 | Default/rule-based filler | Fill non-critical columns bằng default hoặc rule-based logic | backend/services/export_mapping | T06-01 | Không dùng AI cho non-critical fields | unit test filler cases | P0 |
| T06-03 | CSV/XLSX export service | Sinh file export đúng schema template | backend/services/exporter | T06-01,T06-02 | File giống schema template đích | golden file test | P0 |
| T06-04 | Export API | Tạo `POST /crawl-jobs/{id}/export` | backend/api/export | T06-03 | Trả download URL và metadata export | API test | P0 |
| T06-05 | Export UI | Form chọn format/include metadata và tải file | frontend/app/export | T06-04 | User export được file hợp lệ | e2e export flow | P1 |

## Sprint 7 — Import và Incremental Update

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T07-01 | Import readiness check | Kiểm tra required critical fields, duplicates, schema match | backend/services/import_readiness | T05-01,T06-01 | Chặn import nếu chưa sẵn sàng | unit test rules | P0 |
| T07-02 | Direct import API | Tạo `POST /crawl-jobs/{id}/import` | backend/api/import | T07-01 | Trả import task/process status | API test | P1 |
| T07-03 | Import upsert service | Upsert dữ liệu vào backend đích theo unique key | backend/services/importer | T07-02 | Insert/update đúng record | integration test with DB | P0 |
| T07-04 | Import logs | Lưu imported_records, failed_records, error_summary | backend/services/importer | T07-03 | Có import report đầy đủ | service test | P1 |
| T07-05 | Import UI | Hiển thị readiness, trigger import, xem history | frontend/app/import | T07-02,T07-04 | User import/xem lịch sử được | e2e import flow | P1 |

## Sprint 8 — n8n Automation

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T08-01 | Thiết kế workflow n8n bản đầu | Tạo flow cron/webhook → crawl → hash → AI1 → AI2 → route | n8n | T03-05,T02-05 | Workflow chạy end-to-end trên môi trường dev | workflow smoke test | P0 |
| T08-02 | Secure webhook/auth nội bộ | Bảo vệ endpoint nội bộ cho n8n | backend/n8n | T02-03 | Chỉ n8n hợp lệ mới gọi được | auth integration test | P1 |
| T08-03 | Retry & error branch | Retry crawl/AI call, route lỗi vào logs/review | n8n | T08-01 | Có nhánh retry hợp lý | workflow test | P1 |
| T08-04 | Schedule refresh jobs | Tự động làm mới dữ liệu theo lịch | n8n/backend | T08-01 | Dữ liệu cũ được refresh incremental | integration test | P1 |

## Sprint 9 — QA, Security, Ops

| ID | Task | Mục tiêu | Module | Phụ thuộc | Acceptance Criteria | Test cần viết | Ưu tiên |
|---|---|---|---|---|---|---|---|
| T09-01 | Unit test suite nền | Phủ test cho services cốt lõi | backend/tests | nhiều task trước | Coverage đạt ngưỡng nội bộ | unit tests | P0 |
| T09-02 | Integration test API | Test create job → review → clean → export | backend/tests | T06-04 | Flow API chạy đúng | integration tests | P0 |
| T09-03 | Security review hard rules | Check secrets, input validation, authz, logging sensitive data | toàn hệ thống | T07-02,T08-02 | Không lộ secrets, auth hợp lý | security test checklist | P0 |
| T09-04 | Docker & compose | Đóng gói app + db + redis + n8n dev stack | root/devops | T00-01,T00-02 | `docker-compose` chạy local được | smoke test compose | P1 |
| T09-05 | CI pipeline | Chạy lint, test, build trên PR | .github / CI | T09-01,T09-02 | CI pass ổn định | CI verification | P1 |

## Thứ tự đề xuất cho AI Teams
1. **AI Product/BA**: giữ PRD/AC/User Flow nhất quán khi có thay đổi yêu cầu.
2. **AI Architect**: kiểm soát architecture, template mapping, incremental update, n8n boundaries.
3. **AI Tech Lead**: giao task theo đúng backlog này, không giao nguyên dự án cho AI Coder.
4. **AI Coder**: mỗi lần chỉ làm 1 task nhỏ.
5. **AI Reviewer**: review logic + security + contract consistency cho từng task.
6. **AI QA**: viết test cases và test flow theo acceptance criteria.
7. **AI DevOps**: setup local/prod automation sau khi core flow ổn định.

## Gợi ý task đầu tiên nên làm
Nếu bắt đầu từ MVP thực dụng nhất, nên làm theo chuỗi:
1. T00-01 → T00-03
2. T01-02 → T01-05
3. T02-01 → T02-05
4. T03-01 → T03-05
5. T04-01 → T04-04
6. T05-01
7. T06-01 → T06-04

Chuỗi này sẽ giúp bạn sớm có demo: chọn template + chọn critical fields + crawl raw + AI extract/review + export CSV đúng schema mẫu.