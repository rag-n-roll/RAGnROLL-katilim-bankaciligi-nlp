"""High-value backend contracts across API, storage, comparison, and refresh."""

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.main import PROJECT_ROOT, RefreshManager, create_app
from src.comparison import ComparisonQuery, compare_records
from src.persistence import CampaignStore
from src.scraper.models import Campaign


def _campaign(identifier: str, *, bank_slug: str = "ornek") -> dict:
    return Campaign(
        id=identifier,
        bank_slug=bank_slug,
        bank_name=f"{bank_slug.title()} Katılım",
        title=f"{identifier} finansman kampanyası",
        content="100.000 TL'ye kadar 12 ay vadeli masrafsız finansman.",
        source_url=f"https://{bank_slug}.example/{identifier}",
    ).to_dict()


def test_upsert_rows_rolls_back_the_entire_batch_when_a_later_row_is_invalid(
    tmp_path,
):
    store = CampaignStore(tmp_path / "atomic.sqlite3")
    invalid = _campaign("invalid")
    invalid.pop("bank_slug")

    with pytest.raises(ValueError, match="bank_slug, bank_name ve id zorunludur"):
        store.upsert_rows([_campaign("valid"), invalid], run_status="success")

    assert store.list_campaigns() == []
    assert store.latest_scrape_run() is None
    assert store.bank_summary() == []


def test_import_dataset_rejects_non_list_records_without_touching_database(
    tmp_path,
):
    store = CampaignStore(tmp_path / "invalid-import.sqlite3")

    with pytest.raises(ValueError, match="'records' listesi"):
        store.import_dataset({"records": {"id": "not-a-list"}})

    assert not store.path.exists()


def test_empty_database_dashboard_and_filter_api_contracts_are_stable(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "empty.sqlite3")) as client:
        summary = client.get("/api/v1/dashboard/summary")
        snapshot = client.get("/api/v1/dashboard/snapshot")
        filters = client.get("/api/v1/filters")

    assert summary.status_code == snapshot.status_code == filters.status_code == 200
    assert summary.json() == {
        "campaign_count": 0,
        "product_count": 0,
        "bank_count": 0,
        "record_count": 0,
        "average_profit_share_rate": None,
        "last_updated_at": None,
        "campaigns_by_product_type": {},
        "latest_scrape_run": None,
    }
    assert snapshot.json()["distributions"] == {"banks": [], "product_types": []}
    assert snapshot.json()["recent_campaigns"] == []
    assert filters.json() == {"banks": [], "product_types": [], "currencies": []}


def test_comparison_endpoint_rejects_truncated_candidate_sets(tmp_path):
    store = CampaignStore(tmp_path / "comparison-limit.sqlite3")
    store.upsert_rows(
        [_campaign("one"), _campaign("two"), _campaign("three")],
        run_status="success",
    )

    with TestClient(create_app(database_path=store.path)) as client:
        response = client.post(
            "/api/v1/comparisons",
            json={"product_type": "financing", "currency": "try", "limit": 2},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Karşılaştırma 2 kayıtla sınırlı; filtreleri daraltın"
    }


def test_comparison_empty_iterable_has_a_complete_deterministic_contract():
    result = compare_records(
        iter(()),
        ComparisonQuery(product_type="financing", currency="TRY"),
    )

    assert result.to_dict() == {
        "included": [],
        "excluded": [],
        "pair_cache_keys": [],
    }


def test_refresh_manager_success_records_output_command_and_releases_slot(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("RAGNROLL_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.delenv("RAGNROLL_REFRESH_DATASET", raising=False)
    manager = RefreshManager()
    first = manager.create(7)
    calls = []

    def successful_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="3 kayıt güncellendi\n", stderr="")

    monkeypatch.setattr("src.api.main.subprocess.run", successful_run)
    database = tmp_path / "refresh.sqlite3"
    manager.run(first["id"], database)

    status = manager.get(first["id"])
    assert status["status"] == "completed"
    assert status["return_code"] == 0
    assert status["message"] == "3 kayıt güncellendi"
    command, kwargs = calls[0]
    assert command[:5] == [
        sys.executable,
        "-m",
        "src.scraper.scraper",
        "--verbose",
        "collect",
    ]
    options = dict(zip(command[5::2], command[6::2]))
    assert options == {
        "--max-per-bank": "7",
        "--database": str(database),
        "--banks-output": str(runtime_root / "data/raw/participation_banks.json"),
        "--raw-output": str(runtime_root / "data/raw/campaigns.json"),
        "--processed-output": str(runtime_root / "data/processed/campaigns.json"),
        "--quality-report": str(runtime_root / "outputs/quality_report.json"),
    }
    assert kwargs == {
        "cwd": PROJECT_ROOT,
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 1800,
    }
    assert status["created_at"] <= status["started_at"] <= status["completed_at"]
    assert manager.create(1) is not None


def test_refresh_manager_supports_offline_container_refresh_and_index_smoke(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "runtime"
    dataset = tmp_path / "bootstrap.json"
    dataset.write_text('{"records": []}', encoding="utf-8")
    monkeypatch.setenv("RAGNROLL_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("RAGNROLL_REFRESH_DATASET", str(dataset))
    monkeypatch.setenv("RAGNROLL_INDEX_SMOKE", "true")
    calls = []

    def successful_run(command, **kwargs):
        calls.append(command)
        if "scripts.ingest_chroma" in command:
            return SimpleNamespace(
                returncode=0,
                stdout='{"embedded": 1, "smoke": true}\n',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="snapshot içe aktarıldı\n", stderr="")

    manager = RefreshManager(runner=successful_run, auto_index=True)
    job = manager.create(1)
    database = tmp_path / "runtime.sqlite3"
    manager.run(job["id"], database)

    assert calls[0][:6] == [
        sys.executable,
        "-m",
        "src.scraper.scraper",
        "db",
        "import-json",
        str(dataset),
    ]
    assert "--raw-output" in calls[0]
    assert "--processed-output" in calls[0]
    assert calls[1][-1] == "--smoke"
    assert manager.get(job["id"])["index_status"] == "completed"


def test_refresh_manager_maps_cli_partial_status_and_keeps_both_output_streams(
    tmp_path,
):
    def partial_run(command, **kwargs):
        return SimpleNamespace(
            returncode=2,
            stdout="4 kayıt veritabanına yazıldı\n",
            stderr="bir banka geçici olarak erişilemedi\n",
        )

    manager = RefreshManager(runner=partial_run)
    job = manager.create(4)
    manager.run(job["id"], tmp_path / "refresh.sqlite3")

    status = manager.get(job["id"])
    assert status["status"] == "partial"
    assert status["return_code"] == 2
    assert status["message"] == (
        "4 kayıt veritabanına yazıldı\n"
        "bir banka geçici olarak erişilemedi"
    )
    assert status["output_truncated"] is False


def test_refresh_manager_runs_incremental_index_after_successful_update(tmp_path):
    calls = []

    def successful_run(command, **kwargs):
        calls.append(command)
        if "scripts.ingest_chroma" in command:
            return SimpleNamespace(
                returncode=0,
                stdout='{"embedded": 1, "unchanged": 1711}\n',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="1 kayıt güncellendi\n", stderr="")

    manager = RefreshManager(runner=successful_run, auto_index=True)
    job = manager.create(1)
    database = tmp_path / "refresh.sqlite3"
    manager.run(job["id"], database)

    status = manager.get(job["id"])
    assert len(calls) == 2
    assert "scripts.ingest_chroma" in calls[1]
    assert status["status"] == "completed"
    assert status["index_status"] == "completed"
    assert status["index_return_code"] == 0
    assert '"embedded": 1' in status["index_message"]


def test_refresh_manager_skips_index_when_scrape_fails(tmp_path):
    calls = []

    def failed_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="kaynak hatası")

    manager = RefreshManager(runner=failed_run, auto_index=True)
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "refresh.sqlite3")

    status = manager.get(job["id"])
    assert len(calls) == 1
    assert status["status"] == "failed"
    assert status["index_status"] == "skipped"
    assert "çalıştırılmadı" in status["index_message"]


def test_refresh_manager_timeout_is_failed_and_releases_the_active_slot(tmp_path):
    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output=b"son tamamlanan banka: ornek\n",
            stderr=b"uzak sunucu yanit vermedi\n",
        )

    manager = RefreshManager(timeout_seconds=12, runner=timed_out)
    job = manager.create(2)
    manager.run(job["id"], tmp_path / "refresh.sqlite3")

    status = manager.get(job["id"])
    assert status["status"] == "failed"
    assert status["return_code"] is None
    assert "son tamamlanan banka: ornek" in status["message"]
    assert "uzak sunucu yanit vermedi" in status["message"]
    assert status["message"].endswith("12 saniye sonra zaman aşımına uğradı")
    assert status["completed_at"] is not None
    assert manager.create(1) is not None


def test_refresh_manager_marks_index_failure_as_partial(tmp_path):
    def run_with_index_failure(command, **kwargs):
        if "scripts.ingest_chroma" in command:
            raise RuntimeError("model belleği kullanılamadı")
        return SimpleNamespace(returncode=0, stdout="1 kayıt güncellendi", stderr="")

    manager = RefreshManager(runner=run_with_index_failure, auto_index=True)
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "refresh.sqlite3")

    status = manager.get(job["id"])
    assert status["status"] == "partial"
    assert status["index_status"] == "failed"
    assert "model belleği kullanılamadı" in status["index_message"]


def test_refresh_manager_runs_enrichment_before_incremental_index(tmp_path):
    calls = []

    def successful_pipeline(command, **kwargs):
        calls.append(command)
        if "scripts.enrich_nlp" in command:
            return SimpleNamespace(
                returncode=0,
                stdout='{"status":"completed","changed":1}',
                stderr="",
            )
        if "scripts.ingest_chroma" in command:
            return SimpleNamespace(
                returncode=0,
                stdout='{"embedded":1}',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="1 kayıt güncellendi", stderr="")

    manager = RefreshManager(
        runner=successful_pipeline,
        auto_enrich=True,
        auto_index=True,
    )
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "ordered.sqlite3")

    assert [
        "scrape"
        if "src.scraper.scraper" in command
        else "enrich"
        if "scripts.enrich_nlp" in command
        else "index"
        for command in calls
    ] == ["scrape", "enrich", "index"]
    status = manager.get(job["id"])
    assert status["status"] == "completed"
    assert status["enrichment_status"] == "completed"
    assert status["index_status"] == "completed"


def test_enrichment_failure_is_partial_but_index_still_runs(tmp_path):
    calls = []

    def enrichment_failure(command, **kwargs):
        calls.append(command)
        if "scripts.enrich_nlp" in command:
            return SimpleNamespace(returncode=1, stdout="", stderr="manifest uyuşmuyor")
        if "scripts.ingest_chroma" in command:
            return SimpleNamespace(returncode=0, stdout='{"embedded":0}', stderr="")
        return SimpleNamespace(returncode=0, stdout="scrape tamamlandı", stderr="")

    manager = RefreshManager(
        runner=enrichment_failure,
        auto_enrich=True,
        auto_index=True,
    )
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "enrichment-failure.sqlite3")

    status = manager.get(job["id"])
    assert len(calls) == 3
    assert status["status"] == "partial"
    assert status["enrichment_status"] == "failed"
    assert status["enrichment_return_code"] == 1
    assert status["index_status"] == "completed"
    assert "manifest uyuşmuyor" in status["message"]


def test_scrape_failure_skips_both_enrichment_and_index(tmp_path):
    calls = []

    def scrape_failure(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="kaynak hatası")

    manager = RefreshManager(
        runner=scrape_failure,
        auto_enrich=True,
        auto_index=True,
    )
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "scrape-failure.sqlite3")

    status = manager.get(job["id"])
    assert len(calls) == 1
    assert status["status"] == "failed"
    assert status["enrichment_status"] == "skipped"
    assert status["index_status"] == "skipped"


def test_refresh_manager_bounds_reported_subprocess_output(tmp_path):
    def noisy_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="x" * 200, stderr="son-hata")

    manager = RefreshManager(output_limit=60, runner=noisy_run)
    job = manager.create(1)
    manager.run(job["id"], tmp_path / "refresh.sqlite3")

    status = manager.get(job["id"])
    assert status["status"] == "failed"
    assert status["output_truncated"] is True
    assert len(status["message"]) == 60
    assert status["message"].endswith("son-hata")


def test_refresh_manager_os_error_is_reported_and_does_not_deadlock(
    tmp_path, monkeypatch
):
    manager = RefreshManager()
    first = manager.create(3)

    def unavailable_process(*args, **kwargs):
        raise OSError("scraper process unavailable")

    monkeypatch.setattr("src.api.main.subprocess.run", unavailable_process)
    manager.run(first["id"], Path(tmp_path / "refresh.sqlite3"))

    status = manager.get(first["id"])
    assert status["status"] == "failed"
    assert status["return_code"] is None
    assert status["message"] == "scraper process unavailable"
    assert manager.create(2) is not None


@pytest.mark.parametrize("invalid_limit", [0, 101, True])
def test_refresh_manager_rejects_invalid_limits_without_reserving_slot(invalid_limit):
    manager = RefreshManager()

    with pytest.raises(ValueError, match="1 ile 100"):
        manager.create(invalid_limit)

    assert manager.create(1) is not None


def test_unknown_refresh_job_does_not_expose_internal_state(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "refresh.sqlite3")) as client:
        response = client.get("/api/v1/data-refresh/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Veri yenileme işi bulunamadı"}
