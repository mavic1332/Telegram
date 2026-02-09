from fastapi.testclient import TestClient

from gateway.main import app


client = TestClient(app)


def test_gateway_requires_api_key():
    resp = client.post("/telegram/resolve", json={"identifier": "@ciao1234", "search_type": "Telegram"})
    assert resp.status_code == 401


def test_gateway_mock_endpoints_deterministic():
    headers = {"X-API-KEY": "change-me"}
    body = {"identifier": "@ciao1234", "search_type": "Telegram"}
    r1 = client.post("/telegram/resolve", headers=headers, json=body)
    r2 = client.post("/telegram/resolve", headers=headers, json=body)
    assert r1.status_code == 200
    assert r1.json() == r2.json()

    enrich_body = {
        "canonical_id": r1.json()["canonical_id"],
        "normalized_identifier": r1.json()["normalized_identifier"],
        "search_type": "Telegram",
    }
    e = client.post("/telegram/enrich", headers=headers, json=enrich_body)
    assert e.status_code == 200
    assert "service_a" in e.json() and "service_b" in e.json()
