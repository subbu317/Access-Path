from datetime import timedelta

from app.db import connect, iso, utcnow

AUTH = {"X-Admin-Key": "demo-admin-key"}


def test_health_geojson_and_network(client):
    assert client.get("/health").json()["ok"]
    net = client.get("/api/network").json()
    assert len(net["nodes"]) == 20
    assert "Synthetic" in net["disclaimer"]
    json_data = client.get("/api/network.geojson").json()
    assert json_data["type"] == "FeatureCollection"
    assert len(json_data["features"]) == len(net["nodes"]) + len(net["edges"])


def test_routes_persist_anonymously(client):
    response = client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                 "profile": "wheelchair", "algorithm": "astar",
                                                 "risk_aversion": 65})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["routes"]) >= 2
    assert result["routes"][0]["distance_m"] >= result["shortest"]["distance_m"]
    assert "safe-route certification" in result["disclaimer"]
    assert client.get("/api/admin/overview", headers=AUTH).json()["anonymous_route_requests"] == 1
    assert client.get("/api/admin/overview").status_code == 403


def test_invalid_route_requests(client):
    assert client.post("/api/routes", json={"start_id": "N1", "end_id": "N1"}).status_code == 422
    assert client.post("/api/routes", json={"start_id": "NO", "end_id": "N5"}).status_code == 404
    assert client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                  "risk_aversion": 900}).status_code == 422
    assert client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                  "profile": "plane"}).status_code == 422


def test_pending_verified_resolved_report_changes_routes(client):
    original = client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                 "profile": "wheelchair"}).json()
    segment = original["routes"][0]["edge_ids"][0]
    created = client.post("/api/reports", json={"edge_id": segment,
        "obstacle_type": "blocked", "severity": 3,
        "description": "Synthetic test: barrier across the walkway"})
    assert created.status_code == 201
    report = created.json()["report"]
    assert report["status"] == "pending"
    assert client.post(f"/api/admin/reports/{report['id']}/moderate",
                       json={"action": "verify"}).status_code == 403
    unconfirmed = client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                    "profile": "wheelchair"}).json()
    # Pending reports raise uncertainty but cannot create a confirmed hard block.
    assert unconfirmed["network_revision"] > original["network_revision"]
    verified = client.post(f"/api/admin/reports/{report['id']}/moderate",
                           headers=AUTH, json={"action": "verify", "note": "Examined synthetic image"})
    assert verified.status_code == 200
    assert verified.json()["report"]["status"] == "verified"
    new_route = client.post("/api/routes", json={"start_id": "N1", "end_id": "N5",
                                                 "profile": "wheelchair"}).json()
    assert segment not in new_route["routes"][0]["edge_ids"]
    assert new_route["network_revision"] > unconfirmed["network_revision"]
    resolved = client.post(f"/api/admin/reports/{report['id']}/moderate",
                           headers=AUTH, json={"action": "resolve", "note": "Removed"})
    assert resolved.status_code == 200
    assert resolved.json()["report"]["status"] == "resolved"
    assert client.post(f"/api/admin/reports/{report['id']}/moderate",
                       headers=AUTH, json={"action": "verify"}).status_code == 409


def test_report_transitions_and_validation(client):
    bad = client.post("/api/reports", json={"edge_id": "BAD", "obstacle_type": "stairs",
                                                   "description": "There are several steps"})
    assert bad.status_code == 404
    posted = client.post("/api/reports", json={"edge_id": "E01", "obstacle_type": "stairs",
                                                       "description": "Observed steps at this location"}).json()["report"]
    url = f"/api/admin/reports/{posted['id']}/moderate"
    assert client.post(url, json={"action": "review"}, headers=AUTH).json()["report"]["status"] == "reviewed"
    assert client.post(url, json={"action": "reject"}, headers=AUTH).json()["report"]["status"] == "rejected"
    assert client.post(url, json={"action": "verify"}, headers=AUTH).status_code == 409
    statuses = {r["status"] for r in client.get("/api/reports").json()["reports"]}
    assert {"verified", "pending", "resolved", "rejected"}.issubset(statuses)
    assert len(client.get("/api/admin/overview", headers=AUTH).json()["audit"]) >= 2


def test_expiration_releases_verified_block(client, db_path):
    posted = client.post("/api/reports", json={"edge_id": "E01", "obstacle_type": "blocked",
                         "description": "Synthetic barrier expires tomorrow"}).json()["report"]
    client.post(f"/api/admin/reports/{posted['id']}/moderate", headers=AUTH, json={"action": "verify"})
    with connect(db_path) as db:
        db.execute("UPDATE reports SET expires_at=? WHERE id=?", (iso(utcnow() - timedelta(hours=1)), posted["id"]))
    assert client.get("/api/reports").json()["reports"][0]["status"] == "expired"


def test_evaluation_is_computed_and_saved(client):
    assert client.post("/api/evaluations/run").status_code == 403
    result = client.post("/api/evaluations/run", headers=AUTH)
    assert result.status_code == 200, result.text
    data = result.json()["results"]
    assert data["case_count"] == 48
    assert data["feasible_cases"] >= 30
    assert data["mean_accesspath_unsuitable"] == 0
    assert data["confidence_calibration"]["synthetic_outcomes"] > 0
    assert 0 <= data["confidence_calibration"]["brier_score"] <= 1
    assert len(client.get("/api/evaluations").json()["runs"]) == 1
