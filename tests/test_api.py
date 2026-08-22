from fastapi.testclient import TestClient

from src.api.main import RefreshManager, create_app
from src.main import app as integrated_app
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import Campaign


def campaign(identifier: str, title: str = "İhtiyaç finansmanı") -> dict:
    row = Campaign(
        id=identifier,
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title=title,
        content="100.000 TL'ye kadar 3 ay vadeli masrafsız finansman.",
        source_url=f"https://ornek.example/kampanya/{identifier}",
    )
    return preprocess_record(row.to_dict())


def client_with_data(tmp_path) -> TestClient:
    database = tmp_path / "api.sqlite3"
    CampaignStore(database).upsert_rows(
        [campaign("one"), campaign("two", "Taşıt finansmanı")],
        run_status="success",
    )
    return TestClient(create_app(database_path=database))


def test_main_application_mounts_versioned_data_api():
    paths = {route.path for route in integrated_app.routes}

    assert "/api/v1/dashboard/summary" in paths
    assert "/api/v1/dashboard/snapshot" in paths
    assert "/api/v1/filters" in paths
    assert "/api/v1/data-refresh" in paths


def test_openapi_exposes_versioned_response_contracts(tmp_path):
    with client_with_data(tmp_path) as client:
        schema = client.get("/openapi.json").json()

    responses = schema["paths"]["/api/v1/campaigns"]["get"]["responses"]
    response_schema = responses["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/CampaignListResponse")
    assert "FilterOptionsResponse" in schema["components"]["schemas"]


def test_health_dashboard_and_bank_services(tmp_path):
    with client_with_data(tmp_path) as client:
        assert client.get("/api/v1/health").json() == {
            "status": "ok",
            "database": "ready",
        }
        summary = client.get("/api/v1/dashboard/summary").json()
        banks = client.get("/api/v1/banks").json()

    assert summary["campaign_count"] == 2
    assert summary["bank_count"] == 1
    assert summary["latest_scrape_run"]["status"] == "success"
    assert banks["items"][0]["slug"] == "ornek"
    assert banks["items"][0]["campaign_count"] == 2


def test_dashboard_snapshot_combines_chart_freshness_and_recent_data(tmp_path):
    with client_with_data(tmp_path) as client:
        response = client.get(
            "/api/v1/dashboard/snapshot", params={"recent_limit": 1}
        )

    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["summary"]["record_count"] == 2
    assert snapshot["distributions"]["banks"][0]["record_count"] == 2
    assert snapshot["freshness"]["latest_scrape_run"]["status"] == "success"
    assert len(snapshot["recent_campaigns"]) == 1


def test_campaign_list_filters_pages_and_returns_detail(tmp_path):
    with client_with_data(tmp_path) as client:
        response = client.get(
            "/api/v1/campaigns",
            params={"bank_slug": "ornek", "search": "Taşıt", "limit": 1},
        )
        detail = client.get("/api/v1/campaigns/two")
        missing = client.get("/api/v1/campaigns/missing")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == "two"
    assert detail.json()["title"] == "Taşıt finansmanı"
    assert missing.status_code == 404


def test_filter_options_are_counted_and_data_driven(tmp_path):
    with client_with_data(tmp_path) as client:
        response = client.get("/api/v1/filters")

    assert response.status_code == 200
    filters = response.json()
    assert filters["banks"] == [
        {"value": "ornek", "label": "Örnek Katılım", "count": 2}
    ]
    assert {item["value"] for item in filters["product_types"]} == {"financing"}
    assert {item["value"] for item in filters["currencies"]} == {"TRY"}


def test_comparison_endpoint_returns_explainable_ranking(tmp_path):
    with client_with_data(tmp_path) as client:
        response = client.post(
            "/api/v1/comparisons",
            json={"product_type": "financing", "currency": "try"},
        )

    assert response.status_code == 200
    assert len(response.json()["included"]) == 2
    assert "criteria" in response.json()["included"][0]


class PassiveRefreshManager(RefreshManager):
    def run(self, job_id, database):
        self._update(job_id, status="running", message="test")


def test_refresh_endpoint_rejects_parallel_jobs_and_reports_status(tmp_path):
    app = create_app(database_path=tmp_path / "refresh.sqlite3")
    app.state.refresh_manager = PassiveRefreshManager()
    with TestClient(app) as client:
        first = client.post("/api/v1/data-refresh", json={"max_per_bank": 3})
        second = client.post("/api/v1/data-refresh", json={"max_per_bank": 3})
        status = client.get(f"/api/v1/data-refresh/{first.json()['id']}")

    assert first.status_code == 202
    assert second.status_code == 409
    assert status.json()["status"] == "running"


def test_api_validation_rejects_unbounded_requests(tmp_path):
    with client_with_data(tmp_path) as client:
        too_many = client.get("/api/v1/campaigns", params={"limit": 101})
        invalid_refresh = client.post(
            "/api/v1/data-refresh", json={"max_per_bank": 0}
        )

    assert too_many.status_code == 422
    assert invalid_refresh.status_code == 422


class FakeNLPPipeline:
    def analyze(self, text, **metadata):
        return {
            "schema_version": "campaign-nlp-v1",
            "record": {"id": metadata["record_id"], "title": metadata["title"]},
            "classification": {"product_category": {"value": "card"}},
            "entities": [],
        }


def test_nlp_analyze_endpoint_uses_unified_pipeline(tmp_path):
    app = create_app(database_path=tmp_path / "nlp.sqlite3")
    app.state.nlp_pipeline = FakeNLPPipeline()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nlp/analyze",
            json={"text": "Kart ile %10 indirim.", "record_id": "sample", "title": "Örnek"},
        )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "campaign-nlp-v1"
    assert response.json()["record"]["id"] == "sample"
