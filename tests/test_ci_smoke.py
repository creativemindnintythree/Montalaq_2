def test_ci_smoke():
    assert True
import json
from django.test import Client

def test_healthz_liveness():
    c = Client()
    resp = c.get("/healthz")
    assert resp.status_code == 200
    data = json.loads(resp.content.decode("utf-8"))
    assert data.get("status") == "ok"
