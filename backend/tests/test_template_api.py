from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.templates import router
from app.main import app

client = TestClient(app)


def test_upload_template_rejects_non_csv() -> None:
    response = client.post(
        "/api/v1/templates/upload",
        data={"template_name": f"template-{uuid4()}"},
        files={"file": ("template.txt", BytesIO(b"id,name\n1,test\n"), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV template files are supported"
