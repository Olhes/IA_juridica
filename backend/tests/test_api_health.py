from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_api_starts():
    """Verify FastAPI starts correctly"""
    response = client.get("/")

    # Puede ser 200 o 404 dependiendo si tienes root endpoint
    assert response.status_code in [200, 404]