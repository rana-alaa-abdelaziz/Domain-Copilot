from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

class MockSession:
    def execute(self, *args, **kwargs):
        pass
    def commit(self):
        pass
    def query(self, *args, **kwargs):
        class MockQuery:
            def filter(self, *args, **kwargs):
                return self
            def first(self):
                return None
        return MockQuery()

app.state.db_session = MockSession()

print("--- Secure Headers Check ---")
resp = client.get("/health")
for header in ["x-content-type-options", "x-frame-options", "referrer-policy"]:
    print(f"{header}: {resp.headers.get(header)}")

print("\n--- Rate Limiting Check ---")
for i in range(1, 11):
    resp = client.post("/api/auth/token", data={"username": "test", "password": "x"})
    print(f"Request {i}: {resp.status_code}")
