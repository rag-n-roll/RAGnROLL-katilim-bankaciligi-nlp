import json
from argparse import Namespace

import pytest

from src.scraper.models import Campaign
from src.scraper import scraper
from src.scraper.scraper import run_campaigns, run_collect, run_validate


def campaign(
    *,
    bank_slug: str = "ornek",
    bank_name: str = "Örnek Katılım",
    source_url: str = "https://ornek.example/kampanya/1",
) -> Campaign:
    return Campaign(
        bank_slug=bank_slug,
        bank_name=bank_name,
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


def collect_args(tmp_path) -> Namespace:
    return Namespace(
        max_per_bank=20,
        banks_output=tmp_path / "banks.json",
        raw_output=tmp_path / "raw.json",
        processed_output=tmp_path / "processed.json",
        quality_report=tmp_path / "quality.json",
        delay=0,
        timeout=1,
        ignore_robots=True,
    )


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def catalog(*slugs: str):
    return {
        "source_url": "https://www.bddk.org.tr/Kurulus/Liste/77",
        "count": len(slugs),
        "banks": [
            {
                "slug": slug,
                "name": f"{slug} Katılım",
                "website": f"https://{slug}.example",
                "is_digital": False,
            }
            for slug in slugs
        ],
    }


def test_collect_uses_bddk_catalog_and_writes_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_participation_banks", lambda client: catalog("working"))
    monkeypatch.setattr(scraper, "SCRAPERS", {"working": WorkingScraper})
    args = collect_args(tmp_path)

    assert run_collect(args) == 0

    assert read_json(args.banks_output)["count"] == 1
    assert read_json(args.raw_output)["record_count"] == 1
    assert read_json(args.processed_output)["record_count"] == 1
    quality = read_json(args.quality_report)
    assert quality["coverage"]["complete"] is True
    assert quality["processed_coverage"]["bank_coverage"]["ratio"] == 1.0


def test_collect_reports_unsupported_bddk_bank_and_returns_partial_status(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        scraper,
        "fetch_participation_banks",
        lambda client: catalog("working", "missing-bank"),
    )
    monkeypatch.setattr(scraper, "SCRAPERS", {"working": WorkingScraper})
    args = collect_args(tmp_path)

    assert run_collect(args) == 2

    report = read_json(args.quality_report)
    assert report["coverage"]["unsupported"] == ["missing-bank"]


def test_collect_rejects_colliding_output_paths(tmp_path):
    args = collect_args(tmp_path)
    args.processed_output = args.raw_output

    with pytest.raises(ValueError, match="output paths must differ"):
        run_collect(args)


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
        return [
            campaign(
                bank_slug="working",
                bank_name="Working Katılım",
                source_url="https://working.example/kampanya/1",
            )
        ], []


class MissingConfigScraper:
    def __init__(self, *, client) -> None:
        raise RuntimeError("scraper configuration is unavailable")


class DuplicateScraper:
    config = Namespace(base_url="https://ornek.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        return [
            campaign(),
            campaign(source_url="https://ornek.example/kampanya/1?utm_source=bulten#kosullar"),
        ], []


class MixedValidityScraper:
    config = Namespace(base_url="https://mixed.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        return [
            campaign(
                bank_slug="mixed",
                bank_name="Mixed Katılım",
                source_url="https://mixed.example/kampanya/valid",
            ),
            Campaign(
                bank_slug="mixed",
                bank_name="Mixed Katılım",
                title="",
                content="",
                source_url="http://mixed.example/kampanya/invalid",
            ),
        ], []


class InvalidOnlyScraper:
    config = Namespace(base_url="https://invalid.example")

    def __init__(self, *, client) -> None:
        self.client = client

    def scrape(self, *, limit):
        return [
            Campaign(
                bank_slug="invalid",
                bank_name="Invalid Katılım",
                title="",
                content="",
                source_url="http://invalid.example/kampanya/1",
            )
        ], []


def scraper_returning(records):
    class StaticScraper:
        config = Namespace(base_url="https://static.example")

        def __init__(self, *, client) -> None:
            self.client = client

        def scrape(self, *, limit):
            return records, []

    return StaticScraper


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
    assert dataset["records"][0]["bank_slug"] == "working"
    assert dataset["records"][0]["source_url"] == "https://working.example/kampanya/1"
    assert report["fetch_failure_count"] == 1
    assert report["fetch_failures"][0]["bank_slug"] == "broken"
    assert report["fetch_failures"][0]["stage"] == "scrape"
    assert report["fetch_failures"][0]["url"] == "https://broken.example"
    assert report["fetch_failures"][0]["error_type"] == "RuntimeError"
    assert "scraper started" in caplog.text.lower()
    assert "scraper failed for broken" in caplog.text.lower()
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
    assert report["record_count"] == 1
    assert report["valid_record_count"] == 1
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 0
    assert report["quality_score"] == 1.0
    assert report["warning_count"] > 0
    assert report["duplicate_count"] == 1
    assert report["duplicates"][0]["duplicate_of"] == dataset["records"][0]["id"]
    assert {row["duplicate_of"] for row in report["duplicates"]} <= {
        row["id"] for row in dataset["records"]
    }
    assert "duplicates removed" in caplog.text.lower()
    assert "persist" in caplog.text.lower()


def test_campaigns_discards_error_invalid_records_but_reports_their_issues(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setitem(scraper.SCRAPERS, "mixed", MixedValidityScraper)
    args = campaign_args(tmp_path, "mixed")

    with caplog.at_level("INFO"):
        exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["source_url"].endswith("/valid")
    assert report["record_count"] == 1
    assert report["valid_record_count"] == 1
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 3
    assert report["quality_score"] == 0.5
    assert {issue["field"] for issue in report["issues"] if issue["severity"] == "error"} == {
        "title",
        "content",
        "source_url",
    }
    assert "discarded invalid campaign records: 1" in caplog.text.lower()


@pytest.mark.parametrize("valid_first", [False, True], ids=["invalid-first", "valid-first"])
def test_campaigns_validates_duplicate_candidates_before_selecting_persisted_record(
    tmp_path, monkeypatch, valid_first
):
    source_url = "https://duplicate.example/kampanya/1"
    valid = campaign(
        bank_slug="duplicate-order",
        bank_name="Duplicate Order Katılım",
        source_url=source_url,
    )
    invalid = Campaign(
        bank_slug="duplicate-order",
        bank_name="Duplicate Order Katılım",
        title="",
        content="",
        source_url=source_url,
        id="invalid-occurrence",
    )
    valid.id = "valid-representative"
    records = [valid, invalid] if valid_first else [invalid, valid]
    monkeypatch.setitem(
        scraper.SCRAPERS, "duplicate-order", scraper_returning(records)
    )
    args = campaign_args(tmp_path, "duplicate-order")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["title"] == "Geçerli Kampanya"
    assert report["record_count"] == 1
    assert report["valid_record_count"] == 1
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 2
    assert report["duplicate_count"] == 1
    assert report["duplicates"] == [
        {
            "record_id": "invalid-occurrence",
            "duplicate_of": "valid-representative",
            "bank_slug": "duplicate-order",
            "source_url": source_url,
        }
    ]
    assert {row["duplicate_of"] for row in report["duplicates"]} <= {
        row["id"] for row in dataset["records"]
    }
    assert report["quality_score"] == 0.5
    assert {issue["field"] for issue in report["issues"] if issue["severity"] == "error"} == {
        "title",
        "content",
    }


def test_campaigns_filters_validation_by_record_object_not_stringified_id(
    tmp_path, monkeypatch
):
    invalid = Campaign(
        bank_slug="id-types",
        bank_name="ID Types Katılım",
        title="",
        content="",
        source_url="https://id-types.example/kampanya/invalid",
        id=1,
    )
    valid = campaign(
        bank_slug="id-types",
        bank_name="ID Types Katılım",
        source_url="https://id-types.example/kampanya/valid",
    )
    valid.id = "1"
    monkeypatch.setitem(
        scraper.SCRAPERS, "id-types", scraper_returning([invalid, valid])
    )
    args = campaign_args(tmp_path, "id-types")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["source_url"].endswith("/valid")
    assert dataset["records"][0]["id"] == "1"
    assert report["record_count"] == 1
    assert report["valid_record_count"] == 1
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 2
    assert report["quality_score"] == 0.5


def test_campaigns_rejects_later_exact_id_collision_across_distinct_urls(
    tmp_path, monkeypatch
):
    first = campaign(
        bank_slug="id-collision",
        bank_name="ID Collision Katılım",
        source_url="https://id-collision.example/kampanya/first",
    )
    second = campaign(
        bank_slug="id-collision",
        bank_name="ID Collision Katılım",
        source_url="https://id-collision.example/kampanya/second",
    )
    first.id = second.id = "shared-id"
    monkeypatch.setitem(
        scraper.SCRAPERS, "id-collision", scraper_returning([first, second])
    )
    args = campaign_args(tmp_path, "id-collision")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["source_url"].endswith("/first")
    assert report["record_count"] == 1
    assert report["valid_record_count"] == 1
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 1
    assert report["issues"][-1]["field"] == "id"
    assert report["quality_score"] == 0.5


def test_campaigns_uses_noncolliding_fallback_in_duplicate_url_group(
    tmp_path, monkeypatch
):
    first = campaign(
        bank_slug="fallback",
        bank_name="Fallback Katılım",
        source_url="https://fallback.example/kampanya/a",
    )
    colliding = campaign(
        bank_slug="fallback",
        bank_name="Fallback Katılım",
        source_url="https://fallback.example/kampanya/b",
    )
    fallback = campaign(
        bank_slug="fallback",
        bank_name="Fallback Katılım",
        source_url="https://fallback.example/kampanya/b",
    )
    first.id = colliding.id = "X"
    fallback.id = "Y"
    monkeypatch.setitem(
        scraper.SCRAPERS,
        "fallback",
        scraper_returning([first, colliding, fallback]),
    )
    args = campaign_args(tmp_path, "fallback")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert [(row["source_url"], row["id"]) for row in dataset["records"]] == [
        ("https://fallback.example/kampanya/a", "X"),
        ("https://fallback.example/kampanya/b", "Y"),
    ]
    assert report["record_count"] == 2
    assert report["input_record_count"] == 3
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 1
    assert report["duplicates"] == [
        {
            "record_id": "X",
            "duplicate_of": "Y",
            "bank_slug": "fallback",
            "source_url": "https://fallback.example/kampanya/b",
        }
    ]
    assert {row["duplicate_of"] for row in report["duplicates"]} <= {
        row["id"] for row in dataset["records"]
    }


def test_campaigns_omits_duplicate_audit_when_duplicate_group_is_all_invalid(
    tmp_path, monkeypatch
):
    records = [
        Campaign(
            bank_slug="all-invalid-group",
            bank_name="All Invalid Group Katılım",
            title="",
            content="",
            source_url="https://all-invalid-group.example/kampanya/1",
            id=record_id,
        )
        for record_id in ("invalid-1", "invalid-2")
    ]
    monkeypatch.setitem(
        scraper.SCRAPERS,
        "all-invalid-group",
        scraper_returning(records),
    )
    args = campaign_args(tmp_path, "all-invalid-group")

    exit_code = run_campaigns(args)

    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert not args.output.exists()
    assert report["record_count"] == 0
    assert report["input_record_count"] == 2
    assert report["rejected_record_count"] == 2
    assert report["duplicate_count"] == 0
    assert report["duplicates"] == []


def test_campaigns_omits_audit_when_all_group_candidates_collide_with_prior_ids(
    tmp_path, monkeypatch
):
    first = campaign(
        bank_slug="all-collide",
        bank_name="All Collide Katılım",
        source_url="https://all-collide.example/kampanya/a",
    )
    second = campaign(
        bank_slug="all-collide",
        bank_name="All Collide Katılım",
        source_url="https://all-collide.example/kampanya/c",
    )
    collision_x = campaign(
        bank_slug="all-collide",
        bank_name="All Collide Katılım",
        source_url="https://all-collide.example/kampanya/b",
    )
    collision_y = campaign(
        bank_slug="all-collide",
        bank_name="All Collide Katılım",
        source_url="https://all-collide.example/kampanya/b",
    )
    first.id = collision_x.id = "X"
    second.id = collision_y.id = "Y"
    monkeypatch.setitem(
        scraper.SCRAPERS,
        "all-collide",
        scraper_returning([first, second, collision_x, collision_y]),
    )
    args = campaign_args(tmp_path, "all-collide")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert [row["id"] for row in dataset["records"]] == ["X", "Y"]
    assert report["record_count"] == 2
    assert report["input_record_count"] == 4
    assert report["rejected_record_count"] == 2
    assert report["error_count"] == 2
    assert report["duplicate_count"] == 0
    assert report["duplicates"] == []


def test_campaigns_preserves_existing_dataset_when_all_records_are_invalid(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setitem(scraper.SCRAPERS, "invalid", InvalidOnlyScraper)
    args = campaign_args(tmp_path, "invalid")
    sentinel = b'{"records": ["last-known-good"]}\n'
    args.output.write_bytes(sentinel)

    with caplog.at_level("INFO"):
        exit_code = run_campaigns(args)

    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert args.output.read_bytes() == sentinel
    assert report["record_count"] == 0
    assert report["valid_record_count"] == 0
    assert report["input_record_count"] == 1
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 3
    assert "all collected records rejected by validation" in caplog.text.lower()


def test_campaigns_does_not_create_dataset_when_all_records_are_invalid(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(scraper.SCRAPERS, "invalid", InvalidOnlyScraper)
    args = campaign_args(tmp_path, "invalid")

    exit_code = run_campaigns(args)

    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert not args.output.exists()
    assert report["record_count"] == 0
    assert report["valid_record_count"] == 0
    assert report["input_record_count"] == 1
    assert report["rejected_record_count"] == 1
    assert report["error_count"] == 3


def test_campaigns_isolates_missing_scraper_config_and_persists_later_bank(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(scraper.SCRAPERS, "missing-config", MissingConfigScraper)
    monkeypatch.setitem(scraper.SCRAPERS, "working", WorkingScraper)
    args = campaign_args(tmp_path, "missing-config,working")

    exit_code = run_campaigns(args)

    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["bank_slug"] == "working"
    assert report["fetch_failures"][0]["bank_slug"] == "missing-config"
    assert report["fetch_failures"][0]["stage"] == "scrape"
    assert report["fetch_failures"][0]["url"] == ""


def test_campaigns_preserves_last_known_good_dataset_when_all_banks_fail(
    tmp_path, monkeypatch, caplog, capsys
):
    monkeypatch.setitem(scraper.SCRAPERS, "broken", BrokenScraper)
    args = campaign_args(tmp_path, "broken")
    sentinel = b'{"records": ["last-known-good"]}\n'
    args.output.write_bytes(sentinel)

    with caplog.at_level("INFO"):
        exit_code = run_campaigns(args)

    report = json.loads(args.quality_report.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert args.output.read_bytes() == sentinel
    assert report["record_count"] == 0
    assert report["input_record_count"] == 0
    assert report["rejected_record_count"] == 0
    assert report["fetch_failure_count"] == 1
    assert report["fetch_failures"][0]["stage"] == "scrape"
    assert "no records collected" in caplog.text.lower()
    stdout = capsys.readouterr().out
    assert "0 kampanya" in stdout
    assert "yazılmadı" in stdout

    args.output.unlink()
    assert run_campaigns(args) == 2
    assert not args.output.exists()


@pytest.mark.parametrize(
    ("bank_slug", "scraper_class"),
    [("working", WorkingScraper), ("broken", BrokenScraper)],
)
def test_campaigns_rejects_colliding_output_paths_before_scraping(
    tmp_path, monkeypatch, bank_slug, scraper_class
):
    monkeypatch.setitem(scraper.SCRAPERS, bank_slug, scraper_class)
    args = campaign_args(tmp_path, bank_slug)
    shared_output = tmp_path / "shared-output.json"
    args.output = tmp_path / "aliases" / ".." / "shared-output.json"
    args.quality_report = shared_output
    sentinel = b'{"records": ["last-known-good"]}\n'
    shared_output.write_bytes(sentinel)

    with pytest.raises(
        ValueError, match="Campaign and quality report output paths must differ"
    ):
        run_campaigns(args)

    assert shared_output.read_bytes() == sentinel


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
