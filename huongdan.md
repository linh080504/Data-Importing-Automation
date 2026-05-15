 Mình chia làm 2 mức:

  1. Chạy nhanh để xem giao diện
  2. Chạy full backend + frontend

  ---
  1) Chạy nhanh để xem giao diện trước

  Bước 1: mở terminal ở root project

  cd "D:\work\New folder\beyond2"

  Bước 2: chạy frontend

  npm --prefix "D:\work\New folder\beyond2\frontend" install
  npm --prefix "D:\work\New folder\beyond2\frontend" run dev

  Nếu thành công, bạn sẽ thấy kiểu:

  Local: http://localhost:3000

  Bước 3: mở trình duyệt

  Mở:

  - http://localhost:3000/dashboard
  - http://localhost:3000/crawl-jobs

  Kết quả mong đợi

  Bạn sẽ xem được UI dashboard/job detail bằng mock data fallback dù backend chưa chạy.

  ---
  2) Nếu frontend không chạy

  Kiểm tra Node.js

  Chạy:

  node -v
  npm -v

  Nếu không ra version, bạn cần cài Node.js LTS trước.

  Khuyên dùng Node 20 hoặc 22.

  ---
  3) Chạy backend sau

  Backend này là Python/FastAPI.

  Bước 1: vào thư mục backend

  cd "D:\work\New folder\beyond2\backend"

  Bước 2: tạo hoặc activate venv đúng của project này

  Nếu chưa có venv:

  python -m venv .venv

  Activate:

  .\.venv\Scripts\Activate.ps1

  Bước 3: cài dependencies backend

  pip install -r requirements.txt

  Bước 4: chạy backend

  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  Bước 5: test health endpoint

  Mở trình duyệt:

  - http://127.0.0.1:8000/api/v1/health

  Nếu chạy được, bạn sẽ thấy JSON kiểu:

  {"status":"ok","app_name":"Data Import Automation API","environment":"development"}

  ---
  4) Vấn đề thật của backend hiện tại

  Backend của bạn không chỉ cần Python, mà còn cần PostgreSQL đang chạy.

  Nghĩa là:

  - backend có thể boot
  - nhưng các API như:
    - /api/v1/crawl-jobs
    - /api/v1/crawl-jobs/job_001
  - sẽ lỗi nếu Postgres chưa có / chưa chạy

  Cho nên nếu mục tiêu của bạn là:

  A. Chỉ muốn xem dự án chạy giao diện

  => chỉ cần chạy frontend là đủ.

  B. Muốn full data thật từ API

  => phải chạy thêm Postgres.

  ---
  5) Cách chạy dự án dễ nhất cho bạn lúc này

  Cách dễ nhất:

  Mở 2 terminal

  Terminal 1

  cd "D:\work\New folder\beyond2"
  npm --prefix "D:\work\New folder\beyond2\frontend" install
  npm --prefix "D:\work\New folder\beyond2\frontend" run dev

  Terminal 2

  cd "D:\work\New folder\beyond2\backend"
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  Sau đó mở:

  - Frontend: http://localhost:3000
  - Backend health: http://127.0.0.1:8000/api/v1/health

  ---
  6) Nếu backend báo thiếu package

  Chạy lại:

  pip install -r requirements.txt

  Nếu vẫn lỗi uvicorn:

  pip install uvicorn fastapi

  ---
  7) Nếu frontend báo lỗi package

  Chạy:

  npm --prefix "D:\work\New folder\beyond2\frontend" install

  rồi chạy lại:

  npm --prefix "D:\work\New folder\beyond2\frontend" run dev

  ---
  8) Nếu bạn chỉ muốn “một lệnh là chạy”

  Bây giờ project đã có docker-compose cho local dev.

  Chạy ở root project:

  docker compose up --build

  Các địa chỉ chính:

  - Frontend: http://localhost:3000
  - Backend: http://localhost:8000
  - Backend health: http://localhost:8000/api/v1/health
  - n8n: http://localhost:5678
  - Postgres: localhost:5432

  Muốn truyền secret thật thay vì placeholder, set trước các biến môi trường này trong shell của bạn:

  - GEMINI_API_KEY
  - N8N_WEBHOOK_SECRET

  Nếu không dùng Docker thì cách ổn nhất vẫn là:

  - 1 terminal chạy frontend
  - 1 terminal chạy backend

  ---
  9) Mình khuyên bạn làm ngay thế này

  Trước mắt chỉ để thấy dự án chạy:

  Chạy đúng 2 lệnh này:

  cd "D:\work\New folder\beyond2"
  npm --prefix "D:\work\New folder\beyond2\frontend" run dev

  Nếu lên localhost:3000 thì dự án UI đã chạy.

  ---
  Sau đó mới chạy backend:

  cd "D:\work\New folder\beyond2\backend"
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  ---
  10) Nói ngắn gọn

  Muốn chạy được ngay:

  Chạy frontend trước:
  npm --prefix "D:\work\New folder\beyond2\frontend" run dev

  Muốn đủ cả API:

  Chạy backend thêm:
  cd "D:\work\New folder\beyond2\backend"
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  ---
  Nếu bạn muốn, ở tin nhắn tiếp theo mình sẽ viết cho bạn đúng kiểu:

  - Terminal 1 gõ gì
  - Terminal 2 gõ gì
  - thấy lỗi nào thì xử lý câu nào

  theo format cực ngắn, copy-paste được luôn.