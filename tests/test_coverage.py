from src.scraper.coverage import build_coverage_report


def test_coverage_reports_supported_unsupported_and_stale():
    catalog = [{"slug": "a"}, {"slug": "b"}]

    report = build_coverage_report(catalog, {"a": object, "c": object})

    assert report == {
        "catalog_count": 2,
        "supported_count": 1,
        "supported": ["a"],
        "unsupported": ["b"],
        "stale": ["c"],
        "complete": False,
    }
