import json
from argparse import Namespace

from src.scraper.models import Campaign
from src.scraper.scraper import run_validate


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
