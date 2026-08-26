from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.financing import build_financing_quotes
from src.financing.official_sources import (
    _annuity,
    _kuveyt_limits,
    albaraka_quote,
    emlak_katilim_quote,
    fetch_official_quotes,
    financing_campaign_catalog,
    hayat_finans_quote,
    kuveyt_turk_quote,
    tom_katilim_quote,
    turkiye_finans_product_catalog,
    turkiye_finans_quote,
    ziraat_katilim_quote,
)


@pytest.fixture(autouse=True)
def isolate_albaraka_catalog(monkeypatch):
    """Unrelated catalog tests must not depend on Albaraka's public homepage."""
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_albaraka_products", lambda: []
    )


BANKS = [
    {"slug": "bank-a", "name": "Banka A", "website": "https://a.example"},
    {"slug": "bank-b", "name": "Banka B", "website": "https://b.example"},
]


def record(*, rate: float, max_amount: float = 100_000, months: int = 24):
    return {
        "id": "rate-record",
        "bank_slug": "bank-a",
        "bank_name": "Banka A",
        "title": "İhtiyaç Finansmanı",
        "source_url": "https://a.example/official-calculator",
        "scraped_at": "2026-08-25T08:00:00+00:00",
        "end_date": "2026-12-31",
        "structured": {
            "product_type": "financing",
            "financing_type": "consumer",
            "profit_share_rate": rate,
            "term_months": months,
            "max_amount": {"amount": max_amount, "currency": "TRY"},
        },
    }


def test_lists_every_catalog_bank_and_calculates_sourced_offer():
    result = build_financing_quotes(
        records=[record(rate=2.5)],
        banks=BANKS,
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        now=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )

    assert result["coverage"] == {
        "catalog_bank_count": 2,
        "available": 1,
        "unsupported": 1,
    }
    assert [quote["bank_slug"] for quote in result["quotes"]] == ["bank-a", "bank-b"]
    offer = result["quotes"][0]
    assert offer["status"] == "available"
    assert offer["monthly_installment"] == pytest.approx(4874.36)
    assert offer["total_repayment"] == pytest.approx(58492.32)
    assert offer["source_url"] == "https://a.example/official-calculator"


def test_rejects_rate_when_amount_or_term_exceeds_source_conditions():
    result = build_financing_quotes(
        records=[record(rate=2.5, max_amount=25_000, months=3)],
        banks=BANKS,
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        now=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )

    assert result["coverage"]["available"] == 0
    assert all(quote["status"] == "unsupported" for quote in result["quotes"])


def test_zero_profit_campaign_uses_equal_principal_installments():
    result = build_financing_quotes(
        records=[record(rate=0)],
        banks=BANKS[:1],
        financing_type="consumer",
        amount=12_000,
        term_months=12,
        now=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )

    assert result["quotes"][0]["monthly_installment"] == 1000
    assert result["quotes"][0]["total_repayment"] == 12_000


def test_official_quote_takes_priority_over_campaign_fallback():
    official = {
        "bank-a": {
            "bank_slug": "bank-a",
            "bank_name": "Banka A",
            "status": "available",
            "monthly_installment": 4321.0,
            "source_url": "https://a.example/live",
            "message": "Canlı",
        }
    }
    result = build_financing_quotes(
        records=[record(rate=2.5)],
        banks=BANKS[:1],
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        official_quotes=official,
    )

    assert result["quotes"][0]["monthly_installment"] == 4321.0
    assert result["quotes"][0]["source_url"] == "https://a.example/live"


def test_fee_priority_orders_known_lower_fees_before_lower_installment():
    official = {
        "bank-a": {
            "bank_slug": "bank-a",
            "bank_name": "Banka A",
            "status": "available",
            "monthly_installment": 4_000.0,
            "total_repayment": 48_000.0,
            "fees_total": 900.0,
            "source_url": "https://a.example/live",
            "message": "Canlı",
        },
        "bank-b": {
            "bank_slug": "bank-b",
            "bank_name": "Banka B",
            "status": "available",
            "monthly_installment": 4_100.0,
            "total_repayment": 49_200.0,
            "fees_total": 0.0,
            "source_url": "https://b.example/live",
            "message": "Canlı",
        },
    }

    result = build_financing_quotes(
        records=[],
        banks=BANKS,
        financing_type="consumer",
        amount=40_000,
        term_months=12,
        official_quotes=official,
        fee_priority=True,
    )

    assert [quote["bank_slug"] for quote in result["quotes"]] == ["bank-b", "bank-a"]


def test_official_annuity_includes_effective_taxed_rate():
    effective_rate = 3.8 / 100 * 1.30
    assert _annuity(100_000, effective_rate, 36) == pytest.approx(5996.94)


def test_turkiye_finans_catalog_and_selected_campaign_use_official_product(monkeypatch):
    products = [
        {
            "CreditID": 16,
            "Title": "İlk Konutunu Alan / Sigortalı Konut Finansmanı",
            "ShowInSubPage": True,
            "AllocationFee": 0.00575,
            "Bitt": 0,
            "Rusf": 0,
            "ExpertiseFee": 1000,
            "MortgageFee": 200,
            "FinanceCalculatorCreditList": [
                {
                    "Min": 1,
                    "Max": 120,
                    "TutarMin": 0,
                    "TutarMax": 0,
                    "Value": 2.88,
                    "SpecialAllocationFee": 0,
                    "Title": "İlk Konutunu Alan",
                }
            ],
        }
    ]
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_turkiye_finans_products",
        lambda: products,
    )

    catalog = turkiye_finans_product_catalog()
    assert catalog[0]["credit_id"] == 16
    assert catalog[0]["campaign_key"] == "housing-first-insured"
    assert catalog[0]["campaign_name"] == "İlk Konutunu Alan / Sigortalı Konut Finansmanı"
    assert catalog[0]["rate_bands"][0]["monthly_profit_rate"] == 2.88

    quote = turkiye_finans_quote(
        financing_type="housing",
        amount=500_000,
        term_months=120,
        credit_id=16,
    )
    assert quote is not None
    assert quote["product_name"] == "İlk Konutunu Alan / Sigortalı Konut Finansmanı"
    assert quote["monthly_profit_rate"] == 2.88
    assert quote["source_url"].endswith("?financeID=16")


def test_campaign_comparison_hides_banks_without_selected_campaign():
    official = {
        "bank-a": {
            "bank_slug": "bank-a",
            "bank_name": "Banka A",
            "status": "available",
            "monthly_installment": 4321.0,
            "source_url": "https://a.example/live",
            "message": "Canlı",
        }
    }
    result = build_financing_quotes(
        records=[record(rate=2.5)],
        banks=BANKS,
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        official_quotes=official,
        eligible_bank_slugs={"bank-a"},
    )

    assert result["coverage"] == {
        "catalog_bank_count": 1,
        "available": 1,
        "unsupported": 0,
    }
    assert [quote["bank_slug"] for quote in result["quotes"]] == ["bank-a"]


def test_vakif_products_join_the_common_campaign_catalog(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog",
        lambda: [
            {
                "campaign_key": "consumer-financing",
                "campaign_name": "İhtiyaç Finansmanı",
                "financing_type": "consumer",
                "credit_id": 1,
                "rate_bands": [],
                "source_url": "https://www.turkiyefinans.com.tr/",
            }
        ],
    )

    campaigns = financing_campaign_catalog()
    consumer = next(
        campaign for campaign in campaigns
        if campaign["campaign_key"] == "consumer-financing"
    )

    assert {product["bank_slug"] for product in consumer["bank_products"]} == {
        "turkiye-finans",
        "vakif-katilim",
    }
    assert next(
        campaign for campaign in campaigns
        if campaign["campaign_key"] == "housing-new"
    )["bank_products"][0]["external_product_id"] == "K"


def test_ziraat_catalog_uses_official_product_limits(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.vakif_katilim_quote", lambda **_: None
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products",
        lambda: [
            {
                "product_id": "64356287",
                "campaign_key": "consumer-financing-36",
                "financing_type": "consumer",
                "campaign_name": "İhtiyaç Finansmanı (1–36 Ay)",
            }
        ],
    )
    monkeypatch.setattr(
        "src.financing.official_sources._ziraat_product_info",
        lambda _: {
            "range": list(range(1, 37)),
            "ratio": "4.99",
            "minimum_amount": "1",
            "maximum_amount": "124999",
        },
    )

    campaign = next(
        item
        for item in financing_campaign_catalog(amount=50_000, term_months=12)
        if item["campaign_key"] == "consumer-financing-36"
    )
    product = campaign["bank_products"][0]
    assert product["bank_slug"] == "ziraat-katilim"
    assert product["external_product_id"] == "64356287"
    assert product["monthly_profit_rate"] == 4.99
    assert product["rate_bands"][0]["max_amount"] == 124_999


def test_ziraat_quote_uses_selected_official_product_and_rate(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources._ziraat_product_info",
        lambda _: {
            "range": list(range(1, 37)),
            "ratio": "4.99",
            "minimum_amount": "1",
            "maximum_amount": "124999",
        },
    )
    request_body = {}

    def fake_request(url, **kwargs):
        request_body["value"] = kwargs["data"].decode()
        return [
            {
                "command": "insert",
                "selector": ".finansman-taksit-tutar",
                "data": "6.124,10",
            },
            {
                "command": "insert",
                "selector": ".finansman-toplam-tutar",
                "data": "73.489,20",
            },
        ]

    monkeypatch.setattr("src.financing.official_sources._request_json", fake_request)
    quote = ziraat_katilim_quote(
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        product_id="64356287",
    )

    assert quote is not None
    assert quote["monthly_profit_rate"] == 4.99
    assert quote["monthly_installment"] == 6124.10
    assert quote["total_repayment"] == 73489.20
    assert "finans_type=64356287" in request_body["value"]
    assert "finansman_is_bank_ratio=false" in request_body["value"]


def test_kuveyt_limits_follow_amount_thresholds_from_official_settings():
    product = {
        "parameters": {
            "MaturityTermMin": {"Value": "1"},
            "MaturityTermMax": {"Value": "36"},
            "MaturityTermMin2": {"Value": "1"},
            "MaturityTermMax2": {"Value": "24", "Description": "125000"},
            "MaturityTermMin3": {"Value": "1"},
            "MaturityTermMax3": {"Value": "12", "Description": "250000"},
            "DefaultAmountMin": {"Value": "1000"},
            "DefaultAmountMax": {"Value": "5000000"},
        }
    }

    assert _kuveyt_limits(product, 125_000)["max_term_months"] == 36
    assert _kuveyt_limits(product, 125_001)["max_term_months"] == 24
    assert _kuveyt_limits(product, 250_001)["max_term_months"] == 12


def test_kuveyt_quote_uses_selected_calculator_product(monkeypatch):
    product = {
        "product_code": "ECOMMERCE",
        "external_product_id": "26319|ECOMMERCE",
        "campaign_key": "shopping-financing",
        "financing_type": "consumer",
        "campaign_name": "Alışveriş Finansmanı",
        "parameters": {
            "MaturityTermMin": {"Value": "1"},
            "MaturityTermMax": {"Value": "36"},
            "DefaultAmountMin": {"Value": "1000"},
            "DefaultAmountMax": {"Value": "5000000"},
        },
        "note": "",
    }
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: [product]
    )
    request = {}

    def fake_request(url, **kwargs):
        request["url"] = url
        request["body"] = kwargs["data"].decode("utf-8")
        return {
            "Meta": {
                "ProfitRate": 3.49,
                "InstallmentPayment": 5100.25,
                "TotalAmount": 61203.0,
                "YearlyCost": 52.4,
                "AllocationAmount": 250.0,
            }
        }

    monkeypatch.setattr("src.financing.official_sources._request_json", fake_request)
    quote = kuveyt_turk_quote(
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        product_code="26319|ECOMMERCE",
    )

    assert quote is not None
    assert quote["product_name"] == "Alışveriş Finansmanı"
    assert quote["monthly_profit_rate"] == 3.49
    assert '"p4": "ECOMMERCE"' in request["body"]


def test_hayat_finans_catalog_adds_published_shopping_financing(monkeypatch):
    product = {
        "product_code": "BANA-BUNU-AL",
        "campaign_key": "shopping-financing",
        "campaign_name": "Bana Bunu Al Finansmanı",
        "financing_type": "consumer",
        "source_url": "https://hayatfinans.com.tr/krediler/bana-bunu-al",
        "monthly_profit_rate": 4.25,
        "allowed_terms": [6, 12, 18],
        "min_amount": 500.0,
        "max_amount": 50_000.0,
    }
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: [product]
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )

    campaign = next(
        item
        for item in financing_campaign_catalog(amount=10_000, term_months=12)
        if item["campaign_key"] == "shopping-financing"
    )
    bank_product = campaign["bank_products"][0]
    assert bank_product["bank_slug"] == "hayat-finans"
    assert bank_product["monthly_profit_rate"] == 4.25
    assert [band["min_term_months"] for band in bank_product["rate_bands"]] == [6, 12, 18]


def test_hayat_finans_quote_rejects_products_without_published_rate(monkeypatch):
    products = [
        {
            "product_code": "BANA-BUNU-AL",
            "campaign_name": "Bana Bunu Al Finansmanı",
            "financing_type": "consumer",
            "source_url": "https://hayatfinans.com.tr/krediler/bana-bunu-al",
            "monthly_profit_rate": 4.25,
            "allowed_terms": [6, 12, 18],
            "min_amount": 500.0,
            "max_amount": 50_000.0,
        },
        {
            "product_code": "XIAOMI-FINANSMAN",
            "campaign_name": "Xiaomi Ürünlerinde Finansman",
            "financing_type": "consumer",
            "source_url": (
                "https://hayatfinans.com.tr/kampanyalar/"
                "xiaomi-urunlerinde-finansman-avantaji"
            ),
            "monthly_profit_rate": None,
            "allowed_terms": [1, 2, 3],
            "min_amount": None,
            "max_amount": 40_000.0,
        },
    ]
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: products
    )

    quote = hayat_finans_quote(
        financing_type="consumer",
        amount=10_000,
        term_months=12,
        product_code="BANA-BUNU-AL",
    )
    assert quote is not None
    assert quote["monthly_profit_rate"] == 4.25
    assert quote["calculation_origin"] == "official_published_rate"
    assert hayat_finans_quote(
        financing_type="consumer",
        amount=10_000,
        term_months=3,
        product_code="XIAOMI-FINANSMAN",
    ) is None


def test_dunya_products_join_matching_common_campaigns(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products",
        lambda: [
            {
                "product_code": "ARACBINEKYENITUKETICI",
                "official_name": "Araç Binek Yeni",
                "campaign_key": "vehicle-new",
                "financing_type": "vehicle",
                "campaign_name": "Araç Binek Yeni",
            }
        ],
    )
    monkeypatch.setattr(
        "src.financing.official_sources.dunya_katilim_quote",
        lambda **_: {
            "monthly_profit_rate": 3.79,
            "_limits": {
                "min_term_months": 1,
                "max_term_months": 48,
                "min_amount": 1_000,
                "max_amount": 2_000_000,
            },
        },
    )

    campaign = next(
        item
        for item in financing_campaign_catalog(amount=50_000, term_months=12)
        if item["campaign_key"] == "vehicle-new"
    )
    dunya = next(
        product for product in campaign["bank_products"]
        if product["bank_slug"] == "dunya-katilim"
    )
    assert dunya["external_product_id"] == "ARACBINEKYENITUKETICI"
    assert dunya["monthly_profit_rate"] == 3.79
    assert dunya["rate_bands"][0]["max_term_months"] == 48


def test_albaraka_products_join_matching_common_campaigns(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.vakif_katilim_quote", lambda **_: None
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_albaraka_products",
        lambda: [
            {
                "campaign_code": "KMPARAC",
                "campaign_key": "vehicle-new",
                "financing_type": "vehicle",
                "campaign_name": "SIFIR KM TAŞIT FİNANSMANI",
                "monthly_profit_rate": 3.75,
                "min_amount": 1.0,
                "max_amount": 9_999_999.0,
                "min_term_months": 1,
                "max_term_months": 48,
                "source_url": "https://www.albaraka.com.tr/tr",
            }
        ],
    )

    campaign = next(
        item
        for item in financing_campaign_catalog(amount=50_000, term_months=12)
        if item["campaign_key"] == "vehicle-new"
    )
    product = next(
        item for item in campaign["bank_products"]
        if item["bank_slug"] == "albaraka-turk"
    )
    assert product["external_product_id"] == "KMPARAC"
    assert product["monthly_profit_rate"] == 3.75
    assert product["rate_bands"][0]["max_term_months"] == 48


def test_albaraka_quote_uses_selected_published_product(monkeypatch):
    product = {
        "campaign_code": "KMPARAC",
        "campaign_key": "vehicle-new",
        "financing_type": "vehicle",
        "campaign_name": "SIFIR KM TAŞIT FİNANSMANI",
        "monthly_profit_rate": 3.75,
        "min_amount": 1.0,
        "max_amount": 9_999_999.0,
        "min_term_months": 1,
        "max_term_months": 48,
        "source_url": "https://www.albaraka.com.tr/tr",
    }
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_albaraka_products", lambda: [product]
    )

    quote = albaraka_quote(
        financing_type="vehicle",
        amount=50_000,
        term_months=12,
        product_code="KMPARAC",
    )
    assert quote is not None
    assert quote["monthly_profit_rate"] == 3.75
    assert quote["calculation_origin"] == "official_published_rate"
    assert quote["monthly_installment"] == _annuity(50_000, 0.0375 * 1.30, 12)
    assert albaraka_quote(
        financing_type="vehicle",
        amount=50_000,
        term_months=49,
        product_code="KMPARAC",
    ) is None


def test_official_quote_failure_uses_same_recent_verified_result(monkeypatch):
    live_quote = {
        "bank_slug": "albaraka-turk",
        "bank_name": "Albaraka Türk",
        "product_name": "Sıfır Km Taşıt Finansmanı",
        "status": "available",
        "monthly_profit_rate": 3.99,
        "monthly_installment": 5_500.0,
        "total_repayment": 66_000.0,
        "calculation_origin": "official_calculator_live",
        "message": "Canlı sonuç",
    }
    monkeypatch.setattr(
        "src.financing.official_sources.albaraka_quote", lambda **_: live_quote
    )
    params = {
        "financing_type": "vehicle",
        "amount": 54_321,
        "term_months": 12,
        "eligible_bank_slugs": {"albaraka-turk"},
        "selected_product_ids": {"albaraka-turk": "KMPARAC"},
    }
    first = fetch_official_quotes(**params)
    assert first["albaraka-turk"]["calculation_origin"] == "official_calculator_live"

    def unavailable(**_):
        raise TimeoutError("service unavailable")

    monkeypatch.setattr("src.financing.official_sources.albaraka_quote", unavailable)
    fallback = fetch_official_quotes(**params)["albaraka-turk"]
    assert fallback["calculation_origin"] == "last_verified_official_rate"
    assert fallback["message"] == "Son doğrulanmış resmî %3,99 oranı kullanıldı."


def test_emlak_products_join_matching_common_campaigns(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_dunya_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_kuveyt_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_hayat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources.turkiye_finans_product_catalog", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_ziraat_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_tom_products", lambda: []
    )
    monkeypatch.setattr(
        "src.financing.official_sources._fetch_emlak_products",
        lambda: [
            {
                "product_code": "ARACBINEK2EL",
                "campaign_key": "vehicle-used",
                "financing_type": "vehicle",
                "campaign_name": "2. El Taşıt Finansmanı",
                "segment_id": 1,
            },
            {
                "product_code": "EVOFISGERECLERI",
                "campaign_key": "consumer-financing",
                "financing_type": "consumer",
                "campaign_name": "İhtiyaç Finansmanı",
                "segment_id": 2,
            },
        ],
    )

    campaigns = financing_campaign_catalog()
    used_vehicle = next(
        item for item in campaigns if item["campaign_key"] == "vehicle-used"
    )
    consumer = next(
        item for item in campaigns if item["campaign_key"] == "consumer-financing"
    )

    assert {item["bank_slug"] for item in used_vehicle["bank_products"]} == {
        "vakif-katilim",
        "emlak-katilim",
    }
    assert consumer["bank_products"][-1]["external_product_id"] == "EVOFISGERECLERI"


def test_emlak_quote_uses_selected_product_and_official_expenses(monkeypatch):
    monkeypatch.setattr(
        "src.financing.official_sources._emlak_product_limits",
        lambda _: {"min_term_months": 1, "max_term_months": 48},
    )
    requested_url = {}

    def fake_request(url, **_):
        requested_url["value"] = url
        return {
            "Success": True,
            "Data": {
                "ProfitRate": 4.29,
                "TotalInstallmentAmount": 69_915.95,
                "TotalCost": 94.07,
                "TotalExpense": 287.5,
                "InstallmentContractList": [{"Amount": 5_826.32}],
            },
        }

    monkeypatch.setattr("src.financing.official_sources._request_json", fake_request)
    quote = emlak_katilim_quote(
        financing_type="vehicle",
        amount=50_000,
        term_months=12,
        product_code="ARACBINEK2EL",
    )

    assert quote is not None
    assert quote["product_name"] == "2. El Taşıt Finansmanı"
    assert quote["monthly_profit_rate"] == 4.29
    assert quote["monthly_installment"] == 5_826.32
    assert quote["total_repayment"] == 69_915.95
    assert quote["fees_total"] == 287.5
    assert "ProductTypeId=ARACBINEK2EL" in requested_url["value"]


def test_tom_quote_uses_live_rate_plan_and_published_fee(monkeypatch):
    responses = iter(
        [
            {
                "Data": {
                    "LoanRateList": [
                        {"InstallmentsCount": 12, "LoanRate": 3.99}
                    ]
                }
            },
            {
                "Data": {
                    "installmentList": [{"Amount": 5_700.92}],
                    "TotalAmount": 68_411.05,
                    "TotalCost": 83.46,
                }
            },
        ]
    )
    monkeypatch.setattr(
        "src.financing.official_sources._request_json", lambda *_, **__: next(responses)
    )

    quote = tom_katilim_quote(
        financing_type="consumer",
        amount=50_000,
        term_months=12,
        product_code="TKTCDGRFNS",
    )

    assert quote is not None
    assert quote["product_name"] == "Taksitli Alışveriş Finansmanı"
    assert quote["monthly_profit_rate"] == 3.99
    assert quote["monthly_installment"] == 5_700.92
    assert quote["total_repayment"] == 68_411.05
    assert quote["fees_total"] == 250


def test_tom_financing_respects_amount_dependent_term_limits():
    assert tom_katilim_quote(
        financing_type="consumer",
        amount=100_001,
        term_months=13,
        product_code="TKTCDGRFNS",
    ) is None


def test_financing_quotes_endpoint_keeps_ten_bank_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.main.fetch_official_quotes", lambda **_: {})
    client = TestClient(create_app(database_path=tmp_path / "empty.sqlite3"))

    response = client.post(
        "/api/v1/financing-quotes",
        json={
            "financing_type": "consumer",
            "amount": 50_000,
            "term_months": 3,
            "currency": "TRY",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"]["catalog_bank_count"] == 10
    assert len(payload["quotes"]) == 10
    assert all(quote["source_url"] for quote in payload["quotes"])
