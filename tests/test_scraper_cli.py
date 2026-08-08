import json
from argparse import Namespace

from src.scraper.models import Campaign
from src.scraper import scraper
from src.scraper.scraper import run_campaigns, run_validate


def campaign(*, source_url: str = "https://ornek.example/kampanya/1") -> Campaign:
    return Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Geçerli Kampanya",
        content=(
            "Kalite doğrulamasını geçecek kadar uzun bir kampanya açıklaması "
            "burada bulunmaktadır ve koşulları anlatır."
        ),
        summary="Kısa özet",
        source_url=source_url,
    )


def campaign_args(tmp_path, banks: str) -> Namespace:
    return Namespace(
        banks=banks,
        max_per_bank=20,
        output=tmp_path / "campaigns.json",
        quality_report=tmp_path / "quality.json",
        delay=0,
        timeout=1,
        ignore_robots=True,
    )


class BrokenScraper:
    config = Namespace(base_url="https://broken.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        raise RuntimeError("scrape failed")


class WorkingScraper:
    config = Namespace(base_url="https://working.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        return [campaign()], []


class DuplicateScraper:
    config = Namespace(base_url="https://ornek.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        return [
            campaign(),
            campaign(source_url="https://ornek.example/kampanya/1?utm_source=bulten#kosullar"),
        ], []


def test_campaigns_isolates_scrape_failure_and_persists_later_bank(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setitem(scraper.SCRAPERS, "broken", BrokenScraper)
    monkeypatch.setitem(scraper.SCRAPERS, "working", WorkingScraper)
    args = campaign_args(tmp_path, "broken,working")

    with caplog.at_level("INFO"):
        exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert report["fetch_failure_count"] == 1
    assert report["fetch_failures"][0]["bank_slug"] == "broken"
    assert report["fetch_failures"][0]["stage"] == "scrape"
    assert report["fetch_failures"][0]["url"] == "https://broken.example"
    assert report["fetch_failures"][0]["error_type"] == "RuntimeError"
    assert "scraper started" in caplog.text.lower()
    assert "bank completed" in caplog.text.lower()
    assert "validation completed" in caplog.text.lower()
    assert "data persisted" in caplog.text.lower()


def test_campaigns_removes_duplicates_and_logs_milestones(tmp_path, monkeypatch, caplog):
    monkeypatch.setitem(scraper.SCRAPERS, "duplicate", DuplicateScraper)
    args = campaign_args(tmp_path, "duplicate")

    with caplog.at_level("INFO"):
        exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert dataset["record_count"] == 1
    assert report["duplicate_count"] == 1
    assert report["duplicates"][0]["duplicate_of"] == dataset["records"][0]["id"]
    assert "duplicates removed" in caplog.text.lower()
    assert "persist" in caplog.text.lower()


def test_validate_separates_conversion_errors_from_fetch_failures(tmp_path):
    valid = Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Geçerli Kampanya",
        content=(
            "Kalite doğrulamasını geçecek kadar uzun bir kampanya açıklaması "
            "burada bulunmaktadır ve koşulları anlatır."
        ),
        summary="Kısa özet",
        source_url="https://ornek.example/kampanya/1",
    ).to_dict()
    invalid = dict(valid)
    invalid["source_url"] = "https://ornek.example/kampanya/2"
    invalid["start_date"] = "geçersiz-tarih"
    input_path = tmp_path / "campaigns.json"
    output_path = tmp_path / "quality.json"
    input_path.write_text(
        json.dumps({"records": [valid, invalid]}, ensure_ascii=False), encoding="utf-8"
    )

    exit_code = run_validate(Namespace(input=input_path, output=output_path))
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert report["input_record_count"] == 2
    assert report["conversion_error_count"] == 1
    assert report["conversion_errors"][0]["record_index"] == 1
    assert report["fetch_failure_count"] == 0
    assert report["fetch_failures"] == []
    assert report["overall_quality_score"] == 0.5
