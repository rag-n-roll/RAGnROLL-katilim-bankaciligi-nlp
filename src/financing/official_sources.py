"""Resmî banka hesaplayıcılarından doğrulanmış canlı teklifler üretir."""

from __future__ import annotations

import base64
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.cookiejar import CookieJar
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


TURKIYE_FINANS_PAGE = (
    "https://www.turkiyefinans.com.tr/tr-tr/hesaplama-araclari/"
    "sayfalar/finansman-odeme-plani.aspx"
)
TURKIYE_FINANS_API = (
    "https://www.turkiyefinans.com.tr/_vti_bin/TurkiyeFinansServices/"
    "FrontEndService.svc/GetFinanceCalculatorCreditTypeItems"
)
KUVEYT_TURK_PAGE = (
    "https://www.kuveytturk.com.tr/hesaplama-araclari/finansman-hesaplama"
)
KUVEYT_TURK_API = (
    "https://www.kuveytturk.com.tr/ck0d84?30134915811C6D92B8F34A01FCF910EE"
)
KUVEYT_TURK_SETTINGS_API = (
    "https://www.kuveytturk.com.tr/ck0d84?9592031673D7885E535AEF67BC5D9213"
)
ZIRAAT_KATILIM_PAGE = "https://www.ziraatkatilim.com.tr/"
EMLAK_KATILIM_PAGE = "https://www.emlakkatilim.com.tr/tr"
TOM_BANK_PAGE = "https://www.tombank.com.tr/hesaplama-araclari.html"
DUNYA_KATILIM_PAGE = "https://dunyakatilim.com.tr/"
ALBARAKA_PAGE = "https://www.albaraka.com.tr/tr"
HAYAT_FINANS_PRODUCTS_PAGE = "https://hayatfinans.com.tr/krediler"
HAYAT_FINANS_CAMPAIGNS_PAGE = "https://hayatfinans.com.tr/kampanyalar"

_PRODUCT_IDS = {
    "consumer": 1,
    "vehicle": 14,
    "housing": 16,
    "commercial": 18,
}
_TURKIYE_FINANS_PRODUCT_TYPES = {
    1: "consumer",
    999: "consumer",
    14: "vehicle",
    120: "vehicle",
    121: "vehicle",
    122: "vehicle",
    1000: "vehicle",
    1001: "vehicle",
    16: "housing",
    115: "housing",
    116: "housing",
    118: "housing",
    17: "commercial",
    540: "commercial",
    18: "commercial",
    550: "commercial",
}
_TURKIYE_FINANS_CAMPAIGN_KEYS = {
    1: "consumer-financing",
    999: "consumer-financing-uninsured",
    14: "vehicle-new-insured",
    120: "vehicle-used-insured",
    121: "vehicle-new-uninsured",
    122: "vehicle-used-uninsured",
    1000: "motorcycle-insured",
    1001: "motorcycle-uninsured",
    16: "housing-first-insured",
    116: "housing-existing-insured",
    115: "housing-first-uninsured",
    118: "housing-existing-uninsured",
    17: "land-insured",
    540: "land-uninsured",
    18: "workplace-insured",
    550: "workplace-uninsured",
}
_KUVEYT_PRODUCTS = {
    "consumer": ("SAGLIKFINANSMANI", "İhtiyaç Finansmanı"),
    "vehicle": ("DIJITALARACBINEK", "Binek Dijital Araç Finansmanı"),
    "housing": ("GMENKULKONUTYENI", "Konut Finansmanı"),
    "commercial": ("GMENKULISYERIYENI", "İş Yeri Finansmanı"),
}
_KUVEYT_CAMPAIGN_KEYS = {
    "ECOMMERCE": ("shopping-financing", "consumer"),
    "SAGLIKFINANSMANI": ("consumer-financing", "consumer"),
    "IHTIYACKART": ("need-card", "consumer"),
    "DIJITALARACBINEK": ("digital-vehicle-passenger", "vehicle"),
    "DIJITALARACTICARI": ("digital-vehicle-commercial", "commercial"),
    "ARACBINEKYENI": ("vehicle-new", "vehicle"),
    "ARACTICARIYENI": ("vehicle-new-commercial", "commercial"),
    "ARACBINEK2EL": ("vehicle-used", "vehicle"),
    "ARACTICARI2EL": ("vehicle-used-commercial", "commercial"),
    "GMENKULKONUTYENI": ("housing-new", "housing"),
    "GMENKULARSA": ("land", "commercial"),
    "GMENKULISYERIYENI": ("workplace", "commercial"),
    "ELKTRARACSARJUNITE": ("electric-mobility", "consumer"),
    "EGITIMFINANSMANI": ("education-financing", "consumer"),
    "HACFINANSMANI": ("hajj-umrah", "consumer"),
    "KIRAFINANSMANI": ("rent-financing", "consumer"),
    "SEYAHATFINANSMANI": ("travel-financing", "consumer"),
    "TEKNEFINANSMANI": ("boat-financing", "consumer"),
}
_DUNYA_PRODUCTS = {
    "consumer": ("TUKETICIIHTIYAC", "Tüketici İhtiyaç Finansmanı"),
    "vehicle": ("ARACBINEKYENITUKETICI", "Araç Binek Yeni"),
    "housing": ("KONUTTUKETICI", "Konut Yeni"),
}
_DUNYA_CATALOG_DEFINITIONS = {
    "ARACBINEK2ELTUKETICI": ("vehicle-used", "vehicle", "Araç Binek 2. El"),
    "ARACBINEKYENITUKETICI": ("vehicle-new", "vehicle", "Araç Binek Yeni"),
    "ARSATUKETICI": ("land", "commercial", "Arsa Finansmanı"),
    "2ELKONUTTUKETICI": ("housing-used", "housing", "Konut 2. El"),
    "KONUTTUKETICI": ("housing-new", "housing", "Konut Yeni"),
    "TUKETICIIHTIYAC": (
        "consumer-financing",
        "consumer",
        "Tüketici İhtiyaç Finansmanı",
    ),
}
_ALBARAKA_CAMPAIGN_KEYS = {
    "KMPARAC": ("vehicle-new", "vehicle"),
    "2.ELTŞT": ("vehicle-used", "vehicle"),
    "SBSZARC": ("digital-vehicle-passenger", "vehicle"),
    "ISYERII": ("workplace", "commercial"),
    "ARSABIR": ("land", "commercial"),
    "EĞİTİM": ("education-financing", "consumer"),
    "KNTKIRA": ("housing-rent-financing", "consumer"),
    "YURTH": ("dormitory-service-financing", "consumer"),
    "TEKNO": ("technology-financing", "consumer"),
    "CEPFİN": ("mobile-phone-financing", "consumer"),
    "ENGLFİN": ("accessible-life-financing", "consumer"),
    "PRFBFİN": ("prefabricated-financing", "consumer"),
    "MOTOFİN": ("motorcycle-financing", "consumer"),
    "PRTKRT": ("practical-financing-card", "consumer"),
    "YKKNT0B": ("housing-first-home", "housing"),
    "VRKNT0B": ("housing-existing-home", "housing"),
}
_ALBARAKA_CAMPAIGN_NAMES = {
    "KMPARAC": "Sıfır Km Taşıt Finansmanı",
    "2.ELTŞT": "2. El Taşıt Finansmanı",
    "SBSZARC": "Dijital Araç Finansmanı",
    "ISYERII": "İşyeri Finansmanı",
    "ARSABIR": "Arsa Finansmanı",
    "EĞİTİM": "Eğitim Finansmanı",
    "KNTKIRA": "Konut Kira Finansmanı",
    "YURTH": "Yurt Hizmeti Finansmanı",
    "TEKNO": "Diğer Teknoloji Finansmanı",
    "CEPFİN": "Cep Telefonu Finansmanı",
    "ENGLFİN": "Engelsiz Hayat Finansmanı",
    "PRFBFİN": "Prefabrik Finansmanı",
    "MOTOFİN": "Diğer Taşıt Finansmanı (Motosiklet)",
    "PRTKRT": "Pratik Finansman Kart",
    "YKKNT0B": "İlk Evim Konut Finansmanı",
    "VRKNT0B": "2. ve Sonraki Konut Finansmanı",
}
_VAKIF_PRODUCTS = {
    "consumer": ("IF", "İhtiyaç Finansmanı"),
    "vehicle": ("BO", "Taşıt Finansmanı 0 km"),
    "housing": ("K", "Sıfır Konut Finansmanı"),
    "commercial": ("I", "İşyeri Finansmanı"),
}
_VAKIF_CATALOG_PRODUCTS = {
    "IF": ("consumer-financing", "consumer", "İhtiyaç Finansmanı"),
    "K": ("housing-new", "housing", "Sıfır Konut Finansmanı"),
    "K2": ("housing-used", "housing", "2. El Konut Finansmanı"),
    "BO": ("vehicle-new", "vehicle", "Taşıt Finansmanı 0 km"),
    "BO2": ("vehicle-used", "vehicle", "Taşıt Finansmanı 2. El"),
    "I": ("workplace", "commercial", "İşyeri Finansmanı"),
    "A": ("land", "commercial", "Arsa Finansmanı"),
}
_ZIRAAT_PRODUCTS = {
    "consumer": ("64356287", "İhtiyaç Finansmanı"),
    "vehicle": ("64445628", "Taşıt Finansmanı"),
    "housing": ("25961206", "Konut Finansmanı"),
    "commercial": ("20539017", "Bireysel İşyeri Finansmanı"),
}
_ZIRAAT_CATALOG_DEFINITIONS = {
    "48671069": ("housing-campaign-package", "housing", "Konut Finansmanı Kampanya Paketi"),
    "25961206": ("housing-financing", "housing", "Konut Finansmanı (0–10.000.000 TL / 1–120 Ay)"),
    "64445635": ("hajj-umrah-24", "consumer", "Hac / Umre İhtiyaç Finansmanı (1–24 Ay)"),
    "62744752": ("hajj-umrah-12", "consumer", "Hac / Umre İhtiyaç Finansmanı (1–12 Ay)"),
    "64445632": ("hajj-umrah-36", "consumer", "Hac / Umre İhtiyaç Finansmanı (1–36 Ay)"),
    "64356289": ("consumer-financing-12", "consumer", "İhtiyaç Finansmanı (1–12 Ay)"),
    "64356288": ("consumer-financing-24", "consumer", "İhtiyaç Finansmanı (1–24 Ay)"),
    "64356287": ("consumer-financing-36", "consumer", "İhtiyaç Finansmanı (1–36 Ay)"),
    "63871915": ("easy-fund-12", "consumer", "Kolay Fon Finansmanı Kampanya Paketi (1–12 Ay)"),
    "63871914": ("easy-fund-24", "consumer", "Kolay Fon Finansmanı Kampanya Paketi (13–24 Ay)"),
    "63871913": ("easy-fund-36", "consumer", "Kolay Fon Finansmanı Kampanya Paketi (25–36 Ay)"),
    "59244341": ("vehicle-financing-12", "vehicle", "Taşıt Finansmanı (1–12 Ay)"),
    "65492134": ("vehicle-financing-24", "vehicle", "Taşıt Finansmanı (1–24 Ay)"),
    "64445628": ("vehicle-financing-36", "vehicle", "Taşıt Finansmanı (1–36 Ay)"),
    "64445629": ("vehicle-financing-48", "vehicle", "Taşıt Finansmanı (1–48 Ay)"),
    "20539018": ("land", "commercial", "Arsa Finansmanı"),
    "20539017": ("workplace", "commercial", "Bireysel İşyeri Finansmanı"),
}
_EMLAK_PRODUCTS = {
    "consumer": ("EVOFISGERECLERI", "İhtiyaç Finansmanı"),
    "vehicle": ("ARACBINEKYENI", "0 Km Taşıt Finansmanı"),
    "housing": ("GMENKULKONUTYENI", "Yeni Konut Finansmanı"),
}
_EMLAK_CATALOG_DEFINITIONS = {
    "ARACBINEK2EL": ("vehicle-used", "vehicle", "2. El Taşıt Finansmanı", 1),
    "ARACBINEKYENI": ("vehicle-new", "vehicle", "0 Km Taşıt Finansmanı", 1),
    "EVOFISGERECLERI": ("consumer-financing", "consumer", "İhtiyaç Finansmanı", 2),
    "GMENKULKONUTYENI": ("housing-new", "housing", "Yeni Konut Finansmanı", 2),
}
_TOM_CATALOG_DEFINITIONS = {
    "TKTCDGRFNS": (
        "consumer-financing",
        "consumer",
        "Taksitli Alışveriş Finansmanı",
    ),
}
_HAYAT_CATALOG_DEFINITIONS = {
    "BANA-BUNU-AL": {
        "campaign_key": "shopping-financing",
        "campaign_name": "Bana Bunu Al Finansmanı",
        "financing_type": "consumer",
        "path": "/krediler/bana-bunu-al",
        "source_url": "https://hayatfinans.com.tr/krediler/bana-bunu-al",
        "monthly_profit_rate": 4.25,
        "allowed_terms": [6, 12, 18],
        "min_amount": 500.0,
        "max_amount": 50_000.0,
    },
    "BANA-BUNU-AL-IS-ORTAGIM": {
        "campaign_key": "shopping-financing-partner",
        "campaign_name": "Bana Bunu Al İş Ortağım (24 aya kadar)",
        "financing_type": "consumer",
        "path": "/finansmanlar/bana-bunu-al-is-ortagim",
        "source_url": "https://hayatfinans.com.tr/finansmanlar/bana-bunu-al-is-ortagim",
        "monthly_profit_rate": None,
        "allowed_terms": [],
        "min_amount": None,
        "max_amount": None,
    },
    "EGITIM-FINANSMANI": {
        "campaign_key": "education-financing",
        "campaign_name": "Eğitim Finansmanı (vade farksız / 600.000 TL'ye kadar)",
        "financing_type": "consumer",
        "path": "/krediler/hayat-finans-egitim-finansmani-sistemi",
        "source_url": "https://hayatfinans.com.tr/krediler/hayat-finans-egitim-finansmani-sistemi",
        "monthly_profit_rate": None,
        "allowed_terms": [],
        "min_amount": None,
        "max_amount": 600_000.0,
    },
    "XIAOMI-FINANSMAN": {
        "campaign_key": "shopping-xiaomi",
        "campaign_name": "Xiaomi Ürünlerinde Finansman (3 ay / 40.000 TL'ye kadar)",
        "financing_type": "consumer",
        "path": "/kampanyalar/xiaomi-urunlerinde-finansman-avantaji",
        "source_url": (
            "https://hayatfinans.com.tr/kampanyalar/"
            "xiaomi-urunlerinde-finansman-avantaji"
        ),
        "monthly_profit_rate": None,
        "allowed_terms": [1, 2, 3],
        "min_amount": None,
        "max_amount": 40_000.0,
        "end_date": "2026-08-31",
    },
    "TROY-FINANSMAN": {
        "campaign_key": "shopping-troy",
        "campaign_name": "Troy Mağazalarında Finansman (3 ay / 80.000 TL'ye kadar)",
        "financing_type": "consumer",
        "path": "/kampanyalar/bana-bunu-al-is-ortagim-ile-troy-magaza-firsatlari",
        "source_url": (
            "https://hayatfinans.com.tr/kampanyalar/"
            "bana-bunu-al-is-ortagim-ile-troy-magaza-firsatlari"
        ),
        "monthly_profit_rate": None,
        "allowed_terms": [1, 2, 3],
        "min_amount": None,
        "max_amount": 80_000.0,
        "end_date": "2026-08-31",
    },
}
_CACHE_TTL = timedelta(minutes=15)
_cache_lock = Lock()
_cached_at: datetime | None = None
_cached_products: list[dict[str, Any]] | None = None
_ziraat_cache_lock = Lock()
_cached_ziraat_at: datetime | None = None
_cached_ziraat_products: list[dict[str, Any]] | None = None
_cached_ziraat_info: dict[str, tuple[datetime, dict[str, Any]]] = {}
_emlak_cache_lock = Lock()
_cached_emlak_at: datetime | None = None
_cached_emlak_products: list[dict[str, Any]] | None = None
_cached_emlak_limits: dict[str, tuple[datetime, dict[str, int]]] = {}
_tom_cache_lock = Lock()
_cached_tom_at: datetime | None = None
_cached_tom_products: list[dict[str, Any]] | None = None
_kuveyt_cache_lock = Lock()
_cached_kuveyt_at: datetime | None = None
_cached_kuveyt_products: list[dict[str, Any]] | None = None
_hayat_cache_lock = Lock()
_cached_hayat_at: datetime | None = None
_cached_hayat_products: list[dict[str, Any]] | None = None
_dunya_cache_lock = Lock()
_cached_dunya_at: datetime | None = None
_cached_dunya_products: list[dict[str, Any]] | None = None
_albaraka_cache_lock = Lock()
_cached_albaraka_at: datetime | None = None
_cached_albaraka_products: list[dict[str, Any]] | None = None
_verified_quote_cache_lock = Lock()
_verified_quote_cache: dict[
    tuple[str, str, str, float, int], tuple[datetime, dict[str, Any]]
] = {}


def _fetch_turkiye_finans_products(timeout: float = 8.0) -> list[dict[str, Any]]:
    global _cached_at, _cached_products
    now = datetime.now(timezone.utc)
    with _cache_lock:
        if _cached_products is not None and _cached_at and now - _cached_at < _CACHE_TTL:
            return _cached_products

    request = Request(
        TURKIYE_FINANS_API,
        headers={
            "Accept": "application/json",
            "Referer": TURKIYE_FINANS_PAGE,
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("GetFinanceCalculatorCreditTypeItemsResult", {})
    products = result.get("Data")
    if not isinstance(products, list):
        raise ValueError("Türkiye Finans hesaplayıcısı beklenen veri yapısını döndürmedi")

    with _cache_lock:
        _cached_at = now
        _cached_products = products
    return products


def _fetch_kuveyt_products(timeout: float = 8.0) -> list[dict[str, Any]]:
    """Kuveyt Türk hesaplayıcısında o anda yayınlanan tüm ürünleri okur."""
    global _cached_kuveyt_at, _cached_kuveyt_products
    now = datetime.now(timezone.utc)
    with _kuveyt_cache_lock:
        if (
            _cached_kuveyt_products is not None
            and _cached_kuveyt_at
            and now - _cached_kuveyt_at < _CACHE_TTL
        ):
            return _cached_kuveyt_products

    payload = _request_json(
        KUVEYT_TURK_SETTINGS_API + "&p1=LoanCalculator",
        headers={
            "Accept": "application/json",
            "Referer": "https://www.kuveytturk.com.tr/",
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
            "X-Bone-Language": "TR",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=timeout,
    )
    if not isinstance(payload, list):
        raise ValueError("Kuveyt Türk hesaplayıcı ayarları beklenen yapıda değil")

    products: list[dict[str, Any]] = []
    for item in payload:
        parameters = {
            str(parameter.get("Key")): parameter
            for parameter in item.get("Parameters") or []
            if parameter.get("Key")
        }
        product_code = str((parameters.get("ProductCode") or {}).get("Value") or "")
        definition = _KUVEYT_CAMPAIGN_KEYS.get(product_code)
        if not product_code or definition is None:
            continue
        title = re.sub(r"\s+", " ", str(item.get("Title") or "Finansman")).strip()
        campaign_key, financing_type = definition
        if product_code == "ELKTRARACSARJUNITE":
            campaign_key = (
                "bicycle-financing" if title == "Bisiklet Finansmanı"
                else "ev-charging-financing"
            )
        products.append(
            {
                "product_code": product_code,
                "external_product_id": f"{item.get('ContentBaseId') or ''}|{product_code}",
                "campaign_key": campaign_key,
                "financing_type": financing_type,
                "campaign_name": title,
                "parameters": parameters,
                "note": html.unescape(
                    re.sub(r"<[^>]+>", " ", str(item.get("Note") or ""))
                ).strip(),
            }
        )
    if not products:
        raise ValueError("Kuveyt Türk hesaplayıcı ürün listesi boş döndü")
    with _kuveyt_cache_lock:
        _cached_kuveyt_at = now
        _cached_kuveyt_products = products
    return products


def _kuveyt_limits(product: dict[str, Any], amount: float) -> dict[str, Any]:
    parameters = product["parameters"]

    def value(key: str) -> float:
        return _tr_number((parameters.get(key) or {}).get("Value"))

    min_term = int(value("MaturityTermMin"))
    max_term = int(value("MaturityTermMax"))
    threshold2 = _tr_number((parameters.get("MaturityTermMax2") or {}).get("Description"))
    threshold3 = _tr_number((parameters.get("MaturityTermMax3") or {}).get("Description"))
    if threshold3 and amount > threshold3:
        min_term = int(value("MaturityTermMin3") or min_term)
        max_term = int(value("MaturityTermMax3") or max_term)
    elif threshold2 and amount > threshold2:
        min_term = int(value("MaturityTermMin2") or min_term)
        max_term = int(value("MaturityTermMax2") or max_term)
    return {
        "min_term_months": min_term,
        "max_term_months": max_term,
        "min_amount": value("DefaultAmountMin") or None,
        "max_amount": value("DefaultAmountMax") or None,
    }


def _fetch_hayat_products(timeout: float = 8.0) -> list[dict[str, Any]]:
    """Hayat Finans'ın güncel ürün ve kampanya listelerinde yayınlanan finansmanları okur."""
    global _cached_hayat_at, _cached_hayat_products
    now = datetime.now(timezone.utc)
    with _hayat_cache_lock:
        if (
            _cached_hayat_products is not None
            and _cached_hayat_at
            and now - _cached_hayat_at < _CACHE_TTL
        ):
            return _cached_hayat_products

    headers = {"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"}

    def page(url: str) -> str:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return response.read().decode("utf-8")

    products_html = page(HAYAT_FINANS_PRODUCTS_PAGE).lower()
    campaigns_html = page(HAYAT_FINANS_CAMPAIGNS_PAGE).lower()
    products: list[dict[str, Any]] = []
    for product_id, definition in _HAYAT_CATALOG_DEFINITIONS.items():
        listing_html = (
            campaigns_html if definition["path"].startswith("/kampanyalar/")
            else products_html
        )
        slug = definition["path"].rsplit("/", 1)[-1].lower()
        if slug not in listing_html:
            continue
        if definition.get("end_date"):
            end_date = datetime.fromisoformat(definition["end_date"]).replace(
                tzinfo=timezone.utc
            )
            if now > end_date + timedelta(days=1):
                continue
        products.append({"product_code": product_id, **definition})

    bana_bunu_al = next(
        (item for item in products if item["product_code"] == "BANA-BUNU-AL"),
        None,
    )
    if bana_bunu_al:
        detail = html.unescape(page(bana_bunu_al["source_url"]))
        table_index = detail.lower().find("maliyet tablosu")
        rate_match = re.search(
            r"%\s*(\d+[.,]\d+)",
            detail[table_index:] if table_index >= 0 else detail,
        )
        if rate_match:
            bana_bunu_al["monthly_profit_rate"] = _tr_number(rate_match.group(1))
    if not products:
        raise ValueError("Hayat Finans finansman ürün listesi boş döndü")
    with _hayat_cache_lock:
        _cached_hayat_at = now
        _cached_hayat_products = products
    return products


def _fetch_dunya_products(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Dünya Katılım ana sayfa hesaplayıcısındaki aktif finansmanları okur."""
    global _cached_dunya_at, _cached_dunya_products
    now = datetime.now(timezone.utc)
    with _dunya_cache_lock:
        if (
            _cached_dunya_products is not None
            and _cached_dunya_at
            and now - _cached_dunya_at < _CACHE_TTL
        ):
            return _cached_dunya_products

    request = Request(
        DUNYA_KATILIM_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        page_html = response.read().decode("utf-8")
    form = re.search(
        r'<form[^>]+id=["\']loanForm["\'][^>]*>(.*?)</form>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if form is None:
        raise ValueError("Dünya Katılım finansman hesaplama formu bulunamadı")
    products: list[dict[str, Any]] = []
    for product_code, official_name in re.findall(
        r'<option[^>]+value=["\']([^"\']+)["\'][^>]*>(.*?)</option>',
        form.group(1),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        definition = _DUNYA_CATALOG_DEFINITIONS.get(product_code)
        if definition is None:
            continue
        campaign_key, financing_type, campaign_name = definition
        products.append(
            {
                "product_code": product_code,
                "official_name": html.unescape(
                    re.sub(r"<[^>]+>", "", official_name)
                ).strip(),
                "campaign_key": campaign_key,
                "financing_type": financing_type,
                "campaign_name": campaign_name,
            }
        )
    if not products:
        raise ValueError("Dünya Katılım finansman ürün listesi boş döndü")
    with _dunya_cache_lock:
        _cached_dunya_at = now
        _cached_dunya_products = products
    return products


def _fetch_albaraka_products(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Albaraka Türk ana sayfa hesaplayıcısındaki aktif ürünleri okur."""
    global _cached_albaraka_at, _cached_albaraka_products
    now = datetime.now(timezone.utc)
    with _albaraka_cache_lock:
        if (
            _cached_albaraka_products is not None
            and _cached_albaraka_at
            and now - _cached_albaraka_at < _CACHE_TTL
        ):
            return _cached_albaraka_products

    request = Request(
        ALBARAKA_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        page_html = response.read().decode("utf-8")
    select = re.search(
        r'<select[^>]+id=["\']slcfinansmanTuru["\'][^>]*>(.*?)</select>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if select is None:
        raise ValueError("Albaraka Türk finansman ürün listesi bulunamadı")

    def first(data: dict[str, Any], *names: str) -> Any:
        lowered = {str(key).lower(): value for key, value in data.items()}
        return next(
            (lowered[name.lower()] for name in names if name.lower() in lowered),
            None,
        )

    products: list[dict[str, Any]] = []
    for option in re.findall(
        r"<option\b[^>]*>.*?</option>", select.group(1), re.I | re.S
    ):
        value_match = re.search(r"\bvalue\s*=\s*(['\"])(.*?)\1", option, re.I | re.S)
        if value_match is None:
            continue
        try:
            data = json.loads(html.unescape(value_match.group(2)))
        except (json.JSONDecodeError, TypeError):
            continue
        campaign_code = str(
            first(data, "CampaingCode", "CampaignCode") or ""
        ).strip()
        definition = _ALBARAKA_CAMPAIGN_KEYS.get(campaign_code)
        if definition is None:
            continue
        name_match = re.search(r">(.*?)</option>", option, re.I | re.S)
        official_option_name = html.unescape(
            re.sub(r"<[^>]+>", "", name_match.group(1) if name_match else "")
        ).strip()
        campaign_name = _ALBARAKA_CAMPAIGN_NAMES.get(
            campaign_code,
            str(first(data, "CampaignName") or official_option_name or campaign_code),
        )
        project_par_match = re.search(
            r"\bprojectparcode\s*=\s*(['\"])(.*?)\1", option, re.I | re.S
        )
        campaign_key, financing_type = definition
        min_term = max(
            1,
            int(
                _tr_number(
                    first(
                        data,
                        "MaturityMinValue",
                        "DefaultMaturityMin",
                        "MaturityMin",
                        "MinMaturity",
                    )
                )
                or 1
            ),
        )
        max_term = int(
            _tr_number(
                first(
                    data,
                    "MaturityMaxValue",
                    "DefaultMaturityMax",
                    "MaturityMax",
                    "MaxMaturity",
                )
            )
            or 0
        )
        products.append(
            {
                "campaign_code": campaign_code,
                "product_code": str(first(data, "ProductCode", "FinanceType") or ""),
                "product_par_code": str(first(data, "ProductParCode") or ""),
                "project_par_code": (
                    html.unescape(project_par_match.group(2)).strip()
                    if project_par_match else ""
                ),
                "project_code": str(first(data, "ProjectCode") or ""),
                "campaign_key": campaign_key,
                "financing_type": financing_type,
                "campaign_name": campaign_name or campaign_code,
                "monthly_profit_rate": _tr_number(
                    first(data, "ProfitRate", "Rate", "ProfitShareRate")
                ),
                "min_amount": _tr_number(
                    first(
                        data,
                        "AmountMinValue",
                        "DefaultAmountMin",
                        "AmountMin",
                        "MinAmount",
                    )
                )
                or 1.0,
                "max_amount": _tr_number(
                    first(
                        data,
                        "AmountMaxValue",
                        "DefaultAmountMax",
                        "AmountMax",
                        "MaxAmount",
                    )
                )
                or None,
                "min_term_months": min_term,
                "max_term_months": max_term,
                "source_url": ALBARAKA_PAGE,
            }
        )
    if not products:
        raise ValueError("Albaraka Türk finansman ürün listesi boş döndü")
    with _albaraka_cache_lock:
        _cached_albaraka_at = now
        _cached_albaraka_products = products
    return products


def _fetch_ziraat_products(timeout: float = 12.0) -> list[dict[str, Any]]:
    """Ziraat Katılım ana sayfasındaki aktif finansman seçeneklerini okur."""
    global _cached_ziraat_at, _cached_ziraat_products
    now = datetime.now(timezone.utc)
    with _ziraat_cache_lock:
        if (
            _cached_ziraat_products is not None
            and _cached_ziraat_at
            and now - _cached_ziraat_at < _CACHE_TTL
        ):
            return _cached_ziraat_products

    request = Request(
        ZIRAAT_KATILIM_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        page_html = response.read().decode("utf-8")
    select = re.search(
        r'<select[^>]+name=["\']finansman_type["\'][^>]*>(.*?)</select>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if select is None:
        raise ValueError("Ziraat Katılım finansman ürün listesi bulunamadı")

    products: list[dict[str, Any]] = []
    for product_id, official_name in re.findall(
        r'<option[^>]+value=["\'](\d+)["\'][^>]*>(.*?)</option>',
        select.group(1),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        definition = _ZIRAAT_CATALOG_DEFINITIONS.get(product_id)
        if definition is None:
            continue
        campaign_key, financing_type, display_name = definition
        products.append(
            {
                "product_id": product_id,
                "official_name": html.unescape(re.sub(r"<[^>]+>", "", official_name)).strip(),
                "campaign_key": campaign_key,
                "financing_type": financing_type,
                "campaign_name": display_name,
            }
        )
    if not products:
        raise ValueError("Ziraat Katılım finansman ürün listesi boş döndü")

    with _ziraat_cache_lock:
        _cached_ziraat_at = now
        _cached_ziraat_products = products
    return products


def _ziraat_product_info(product_id: str, timeout: float = 8.0) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with _ziraat_cache_lock:
        cached = _cached_ziraat_info.get(product_id)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

    info_response = _request_json(
        "https://www.ziraatkatilim.com.tr/ajax/get-vade",
        data=urlencode({"eid": product_id}).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": ZIRAAT_KATILIM_PAGE,
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
        timeout=timeout,
    )
    info = info_response.get("data") or {}
    if not info_response.get("status") or not _tr_number(info.get("ratio")):
        raise ValueError("Ziraat Katılım ürün bilgisi alınamadı")
    with _ziraat_cache_lock:
        _cached_ziraat_info[product_id] = (now, info)
    return info


def _fetch_emlak_products(timeout: float = 12.0) -> list[dict[str, Any]]:
    """Emlak Katılım ana sayfasındaki aktif finansman seçeneklerini okur."""
    global _cached_emlak_at, _cached_emlak_products
    now = datetime.now(timezone.utc)
    with _emlak_cache_lock:
        if (
            _cached_emlak_products is not None
            and _cached_emlak_at
            and now - _cached_emlak_at < _CACHE_TTL
        ):
            return _cached_emlak_products

    request = Request(
        EMLAK_KATILIM_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        page_html = response.read().decode("utf-8")
    select = re.search(
        r'<select[^>]+id=["\']js-productType["\'][^>]*>(.*?)</select>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if select is None:
        raise ValueError("Emlak Katılım finansman ürün listesi bulunamadı")

    products: list[dict[str, Any]] = []
    for product_code, official_name in re.findall(
        r'<option[^>]+value=["\']([^"\']+)["\'][^>]*>(.*?)</option>',
        select.group(1),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        definition = _EMLAK_CATALOG_DEFINITIONS.get(product_code)
        if definition is None:
            continue
        campaign_key, financing_type, display_name, segment_id = definition
        products.append(
            {
                "product_code": product_code,
                "official_name": html.unescape(re.sub(r"<[^>]+>", "", official_name)).strip(),
                "campaign_key": campaign_key,
                "financing_type": financing_type,
                "campaign_name": display_name,
                "segment_id": segment_id,
            }
        )
    if not products:
        raise ValueError("Emlak Katılım finansman ürün listesi boş döndü")

    with _emlak_cache_lock:
        _cached_emlak_at = now
        _cached_emlak_products = products
    return products


def _emlak_product_limits(product_code: str) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    with _emlak_cache_lock:
        cached = _cached_emlak_limits.get(product_code)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
    payload = _request_json(
        "https://www.emlakkatilim.com.tr/Plugins/SelectLoansProperty?"
        + urlencode({"ProductTypeId": product_code}),
        headers={
            "Referer": EMLAK_KATILIM_PAGE,
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        },
    )
    data = payload.get("Data") or {}
    if not payload.get("Success") or not data.get("MaturityMax"):
        raise ValueError("Emlak Katılım vade sınırları alınamadı")
    limits = {
        "min_term_months": int(data.get("MaturityMin") or 0) + 1,
        "max_term_months": int(data["MaturityMax"]),
    }
    with _emlak_cache_lock:
        _cached_emlak_limits[product_code] = (now, limits)
    return limits


def _fetch_tom_products(timeout: float = 12.0) -> list[dict[str, Any]]:
    """TOM Bank hesaplayıcısında aktif olarak listelenen ürünleri okur."""
    global _cached_tom_at, _cached_tom_products
    now = datetime.now(timezone.utc)
    with _tom_cache_lock:
        if (
            _cached_tom_products is not None
            and _cached_tom_at
            and now - _cached_tom_at < _CACHE_TTL
        ):
            return _cached_tom_products

    request = Request(
        TOM_BANK_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        page_html = response.read().decode("utf-8")
    option_codes = set(
        re.findall(
            r'<option[^>]+value=["\']([^"\']+)["\']',
            page_html,
            flags=re.IGNORECASE,
        )
    )
    products = [
        {
            "product_code": product_code,
            "campaign_key": definition[0],
            "financing_type": definition[1],
            "campaign_name": definition[2],
        }
        for product_code, definition in _TOM_CATALOG_DEFINITIONS.items()
        if product_code in option_codes
    ]
    if not products:
        raise ValueError("TOM Bank finansman ürün listesi boş döndü")
    with _tom_cache_lock:
        _cached_tom_at = now
        _cached_tom_products = products
    return products


def _annuity(amount: float, monthly_rate: float, months: int) -> float:
    if monthly_rate == 0:
        return round(amount / months, 2)
    factor = (1 + monthly_rate) ** months
    return round(amount * monthly_rate * factor / (factor - 1), 2)


def _tr_number(value: Any) -> float:
    text = re.sub(r"[^0-9,.-]", "", str(value or "0"))
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return float(text or 0)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain_amount(value: float) -> str:
    """Türk banka formlarının 50000.0 değerini 500000 olarak okumasını önler."""
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def _request_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
    opener: Any = None,
    timeout: float = 8.0,
) -> Any:
    request = Request(url, data=data, headers=headers or {}, method=method)
    open_request = opener.open if opener is not None else urlopen
    with open_request(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def turkiye_finans_product_catalog() -> list[dict[str, Any]]:
    """Resmî hesaplayıcıda kullanıcıya açık Türkiye Finans ürünlerini döndürür."""
    catalog: list[dict[str, Any]] = []
    for product in _fetch_turkiye_finans_products():
        credit_id = int(product.get("CreditID") or 0)
        financing_type = _TURKIYE_FINANS_PRODUCT_TYPES.get(credit_id)
        if financing_type is None or not product.get("ShowInSubPage"):
            continue
        rate_bands = []
        for band in product.get("FinanceCalculatorCreditList") or []:
            rate_bands.append(
                {
                    "min_term_months": int(band.get("Min") or 0),
                    "max_term_months": int(band.get("Max") or 0),
                    "min_amount": float(band.get("TutarMin") or 0) or None,
                    "max_amount": float(band.get("TutarMax") or 0) or None,
                    "monthly_profit_rate": float(band.get("Value") or 0),
                }
            )
        title = re.sub(r"\s+", " ", str(product.get("Title") or "Finansman")).strip()
        catalog.append(
            {
                "credit_id": credit_id,
                "campaign_key": _TURKIYE_FINANS_CAMPAIGN_KEYS[credit_id],
                "financing_type": financing_type,
                "campaign_name": title,
                "rate_bands": rate_bands,
                "source_url": f"{TURKIYE_FINANS_PAGE}?financeID={credit_id}",
            }
        )
    return catalog


def _catalog_rate(
    product: dict[str, Any], amount: float | None, term_months: int | None
) -> float | None:
    if amount is None or term_months is None:
        return None
    band = next(
        (
            item
            for item in product.get("rate_bands") or []
            if item["min_term_months"] <= term_months <= item["max_term_months"]
            and (item.get("min_amount") is None or amount >= item["min_amount"])
            and (item.get("max_amount") is None or amount <= item["max_amount"])
        ),
        None,
    )
    return float(band["monthly_profit_rate"]) if band else None


def _fetch_catalog_sources() -> dict[str, list[dict[str, Any]] | None]:
    """Bağımsız banka ürün listelerini aynı anda yükler."""
    fetchers = {
        "turkiye": turkiye_finans_product_catalog,
        "kuveyt": _fetch_kuveyt_products,
        "hayat": _fetch_hayat_products,
        "dunya": _fetch_dunya_products,
        "albaraka": _fetch_albaraka_products,
        "ziraat": _fetch_ziraat_products,
        "emlak": _fetch_emlak_products,
        "tom": _fetch_tom_products,
    }
    products: dict[str, list[dict[str, Any]] | None] = {
        name: None for name in fetchers
    }
    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        jobs = {executor.submit(fetcher): name for name, fetcher in fetchers.items()}
        for job in as_completed(jobs):
            try:
                result = job.result()
            except Exception:
                result = None
            products[jobs[job]] = result
    return products


def financing_campaign_catalog(
    *, amount: float | None = None, term_months: int | None = None
) -> list[dict[str, Any]]:
    """Banka ürünlerini ortak kampanya anahtarları altında birleştirir."""
    campaigns: dict[str, dict[str, Any]] = {}
    catalog_sources = _fetch_catalog_sources()
    for product in catalog_sources["turkiye"] or []:
        key = str(product["campaign_key"])
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        campaign["bank_products"].append(
            {
                "bank_slug": "turkiye-finans",
                "bank_name": "Türkiye Finans",
                "external_product_id": str(product["credit_id"]),
                "campaign_name": product["campaign_name"],
                "rate_bands": product["rate_bands"],
                "monthly_profit_rate": _catalog_rate(product, amount, term_months),
                "source_url": product["source_url"],
            }
        )

    kuveyt_products = catalog_sources["kuveyt"] or []
    kuveyt_quotes: dict[str, dict[str, Any]] = {}
    if kuveyt_products and amount is not None and term_months is not None:
        eligible_products = []
        for product in kuveyt_products:
            limits = _kuveyt_limits(product, amount)
            if (
                limits["min_term_months"] <= term_months <= limits["max_term_months"]
                and (limits["min_amount"] is None or amount >= limits["min_amount"])
                and (limits["max_amount"] is None or amount <= limits["max_amount"])
            ):
                eligible_products.append(product)
        if eligible_products:
            with ThreadPoolExecutor(max_workers=len(eligible_products)) as executor:
                jobs = {
                    executor.submit(
                        kuveyt_turk_quote,
                        financing_type=product["financing_type"],
                        amount=amount,
                        term_months=term_months,
                        product_code=product["external_product_id"],
                    ): product["external_product_id"]
                    for product in eligible_products
                }
                for job in as_completed(jobs):
                    try:
                        quote = job.result()
                    except Exception:
                        quote = None
                    if quote:
                        kuveyt_quotes[jobs[job]] = quote

    for product in kuveyt_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        limits = _kuveyt_limits(product, amount or 1_000)
        quote = kuveyt_quotes.get(product["external_product_id"])
        rate = float(quote["monthly_profit_rate"]) if quote else None
        rate_bands = [{**limits, "monthly_profit_rate": rate}] if rate is not None else []
        campaign["bank_products"].append(
            {
                "bank_slug": "kuveyt-turk",
                "bank_name": "Kuveyt Türk",
                "external_product_id": product["external_product_id"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": rate,
                "source_url": KUVEYT_TURK_PAGE,
                "note": product["note"],
            }
        )

    hayat_products = catalog_sources["hayat"] or []
    for product in hayat_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        published_rate = product.get("monthly_profit_rate")
        allowed_terms = [int(term) for term in product.get("allowed_terms") or []]
        eligible = bool(
            amount is not None
            and term_months is not None
            and published_rate is not None
            and term_months in allowed_terms
            and (
                product.get("min_amount") is None
                or amount >= product["min_amount"]
            )
            and (
                product.get("max_amount") is None
                or amount <= product["max_amount"]
            )
        )
        rate_bands = [
            {
                "min_term_months": term,
                "max_term_months": term,
                "min_amount": product.get("min_amount"),
                "max_amount": product.get("max_amount"),
                "monthly_profit_rate": float(published_rate),
            }
            for term in allowed_terms
            if published_rate is not None
        ]
        campaign["bank_products"].append(
            {
                "bank_slug": "hayat-finans",
                "bank_name": "Hayat Finans",
                "external_product_id": product["product_code"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": float(published_rate) if eligible else None,
                "source_url": product["source_url"],
            }
        )
        if published_rate is None:
            campaign["availability_message"] = "Resmî kâr oranı yayımlanmamış"

    dunya_products = catalog_sources["dunya"] or []
    dunya_quotes: dict[str, dict[str, Any]] = {}
    if dunya_products and amount is not None and term_months is not None:
        with ThreadPoolExecutor(max_workers=len(dunya_products)) as executor:
            jobs = {
                executor.submit(
                    dunya_katilim_quote,
                    financing_type=product["financing_type"],
                    amount=amount,
                    term_months=term_months,
                    product_code=product["product_code"],
                ): product["product_code"]
                for product in dunya_products
            }
            for job in as_completed(jobs):
                try:
                    quote = job.result()
                except Exception:
                    quote = None
                if quote:
                    dunya_quotes[jobs[job]] = quote

    for product in dunya_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        quote = dunya_quotes.get(product["product_code"])
        rate = float(quote["monthly_profit_rate"]) if quote else None
        limits = quote.get("_limits") if quote else None
        rate_bands = (
            [{**limits, "monthly_profit_rate": rate}]
            if limits and rate is not None
            else []
        )
        campaign["bank_products"].append(
            {
                "bank_slug": "dunya-katilim",
                "bank_name": "Dünya Katılım",
                "external_product_id": product["product_code"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": rate,
                "source_url": DUNYA_KATILIM_PAGE,
            }
        )

    albaraka_products = catalog_sources["albaraka"] or []
    for product in albaraka_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        eligible = bool(
            amount is not None
            and term_months is not None
            and product["min_term_months"] <= term_months <= product["max_term_months"]
            and amount >= product["min_amount"]
            and (
                product.get("max_amount") is None
                or amount <= product["max_amount"]
            )
        )
        rate = float(product["monthly_profit_rate"])
        campaign["bank_products"].append(
            {
                "bank_slug": "albaraka-turk",
                "bank_name": "Albaraka Türk",
                "external_product_id": product["campaign_code"],
                "campaign_name": product["campaign_name"],
                "rate_bands": [
                    {
                        "min_term_months": product["min_term_months"],
                        "max_term_months": product["max_term_months"],
                        "min_amount": product["min_amount"],
                        "max_amount": product.get("max_amount"),
                        "monthly_profit_rate": rate,
                    }
                ],
                "monthly_profit_rate": rate if eligible else None,
                "source_url": product["source_url"],
            }
        )

    vakif_quotes: dict[str, dict[str, Any]] = {}
    if amount is not None and term_months is not None:
        with ThreadPoolExecutor(max_workers=len(_VAKIF_CATALOG_PRODUCTS)) as executor:
            jobs = {
                executor.submit(
                    vakif_katilim_quote,
                    financing_type=definition[1],
                    amount=amount,
                    term_months=term_months,
                    product_code=code,
                ): code
                for code, definition in _VAKIF_CATALOG_PRODUCTS.items()
            }
            for job in as_completed(jobs):
                try:
                    quote = job.result()
                except Exception:
                    quote = None
                if quote:
                    vakif_quotes[jobs[job]] = quote

    for code, (key, financing_type, campaign_name) in _VAKIF_CATALOG_PRODUCTS.items():
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": campaign_name,
                "financing_type": financing_type,
                "bank_products": [],
            },
        )
        quote = vakif_quotes.get(code)
        campaign["bank_products"].append(
            {
                "bank_slug": "vakif-katilim",
                "bank_name": "Vakıf Katılım",
                "external_product_id": code,
                "campaign_name": campaign_name,
                "rate_bands": [],
                "monthly_profit_rate": (
                    float(quote["monthly_profit_rate"]) if quote else None
                ),
                "source_url": (
                    "https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/"
                    "hesaplama-araclari/finansman-hesaplama"
                ),
            }
        )

    ziraat_products = catalog_sources["ziraat"]
    if ziraat_products is None:
        ziraat_products = [
            {
                "product_id": product_id,
                "official_name": campaign_name,
                "campaign_key": key,
                "financing_type": financing_type,
                "campaign_name": campaign_name,
            }
            for product_id, (
                key,
                financing_type,
                campaign_name,
            ) in _ZIRAAT_CATALOG_DEFINITIONS.items()
        ]

    ziraat_infos: dict[str, dict[str, Any]] = {}
    if ziraat_products and amount is not None and term_months is not None:
        with ThreadPoolExecutor(max_workers=len(ziraat_products)) as executor:
            jobs = {
                executor.submit(_ziraat_product_info, product["product_id"]): product[
                    "product_id"
                ]
                for product in ziraat_products
            }
            for job in as_completed(jobs):
                try:
                    info = job.result()
                except Exception:
                    info = None
                if info:
                    ziraat_infos[jobs[job]] = info

    for product in ziraat_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        info = ziraat_infos.get(product["product_id"])
        allowed_terms = [int(value) for value in (info or {}).get("range") or []]
        minimum_amount = _tr_number((info or {}).get("minimum_amount")) if info else None
        maximum_amount = _tr_number((info or {}).get("maximum_amount")) if info else None
        if minimum_amount == 0:
            minimum_amount = None
        rate = _tr_number((info or {}).get("ratio")) if info else None
        eligible = bool(
            info
            and term_months in allowed_terms
            and (minimum_amount is None or amount >= minimum_amount)
            and (maximum_amount is None or amount <= maximum_amount)
        )
        rate_bands = []
        if info and allowed_terms:
            rate_bands.append(
                {
                    "min_term_months": min(allowed_terms),
                    "max_term_months": max(allowed_terms),
                    "min_amount": minimum_amount,
                    "max_amount": maximum_amount,
                    "monthly_profit_rate": rate,
                }
            )
        campaign["bank_products"].append(
            {
                "bank_slug": "ziraat-katilim",
                "bank_name": "Ziraat Katılım",
                "external_product_id": product["product_id"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": rate if eligible else None,
                "source_url": ZIRAAT_KATILIM_PAGE,
            }
        )

    emlak_products = catalog_sources["emlak"]
    if emlak_products is None:
        emlak_products = [
            {
                "product_code": product_code,
                "official_name": campaign_name,
                "campaign_key": key,
                "financing_type": financing_type,
                "campaign_name": campaign_name,
                "segment_id": segment_id,
            }
            for product_code, (
                key,
                financing_type,
                campaign_name,
                segment_id,
            ) in _EMLAK_CATALOG_DEFINITIONS.items()
        ]

    emlak_limits: dict[str, dict[str, int]] = {}
    emlak_quotes: dict[str, dict[str, Any]] = {}
    if emlak_products and amount is not None and term_months is not None:
        with ThreadPoolExecutor(max_workers=len(emlak_products)) as executor:
            jobs = {
                executor.submit(
                    _emlak_product_limits, product["product_code"]
                ): product["product_code"]
                for product in emlak_products
            }
            for job in as_completed(jobs):
                try:
                    limits = job.result()
                except Exception:
                    limits = None
                if limits:
                    emlak_limits[jobs[job]] = limits
        with ThreadPoolExecutor(max_workers=len(emlak_products)) as executor:
            jobs = {
                executor.submit(
                    emlak_katilim_quote,
                    financing_type=product["financing_type"],
                    amount=amount,
                    term_months=term_months,
                    product_code=product["product_code"],
                ): product["product_code"]
                for product in emlak_products
            }
            for job in as_completed(jobs):
                try:
                    quote = job.result()
                except Exception:
                    quote = None
                if quote:
                    emlak_quotes[jobs[job]] = quote

    for product in emlak_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        limits = emlak_limits.get(product["product_code"])
        quote = emlak_quotes.get(product["product_code"])
        rate = float(quote["monthly_profit_rate"]) if quote else None
        rate_bands = []
        if limits and rate is not None:
            if product["product_code"] == "EVOFISGERECLERI":
                rate_bands = [
                    {
                        **limits,
                        "min_amount": 1_000,
                        "max_amount": 50_000,
                        "monthly_profit_rate": rate,
                    },
                    {
                        "min_term_months": limits["min_term_months"],
                        "max_term_months": min(24, limits["max_term_months"]),
                        "min_amount": 50_000.01,
                        "max_amount": 9_999_999,
                        "monthly_profit_rate": rate,
                    },
                ]
            else:
                rate_bands = [
                    {
                        **limits,
                        "min_amount": 1_000,
                        "max_amount": 9_999_999,
                        "monthly_profit_rate": rate,
                    }
                ]
        campaign["bank_products"].append(
            {
                "bank_slug": "emlak-katilim",
                "bank_name": "Emlak Katılım",
                "external_product_id": product["product_code"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": rate,
                "source_url": EMLAK_KATILIM_PAGE,
            }
        )

    tom_products = catalog_sources["tom"]
    if tom_products is None:
        tom_products = [
            {
                "product_code": product_code,
                "campaign_key": definition[0],
                "financing_type": definition[1],
                "campaign_name": definition[2],
            }
            for product_code, definition in _TOM_CATALOG_DEFINITIONS.items()
        ]

    tom_quotes: dict[str, dict[str, Any]] = {}
    if tom_products and amount is not None and term_months is not None:
        with ThreadPoolExecutor(max_workers=len(tom_products)) as executor:
            jobs = {
                executor.submit(
                    tom_katilim_quote,
                    financing_type=product["financing_type"],
                    amount=amount,
                    term_months=term_months,
                    product_code=product["product_code"],
                ): product["product_code"]
                for product in tom_products
            }
            for job in as_completed(jobs):
                try:
                    quote = job.result()
                except Exception:
                    quote = None
                if quote:
                    tom_quotes[jobs[job]] = quote

    for product in tom_products:
        key = product["campaign_key"]
        campaign = campaigns.setdefault(
            key,
            {
                "campaign_key": key,
                "display_name": product["campaign_name"],
                "financing_type": product["financing_type"],
                "bank_products": [],
            },
        )
        quote = tom_quotes.get(product["product_code"])
        rate = float(quote["monthly_profit_rate"]) if quote else None
        rate_bands = []
        if rate is not None:
            rate_bands = [
                {
                    "min_term_months": 1,
                    "max_term_months": 36,
                    "min_amount": 5_000,
                    "max_amount": 50_000,
                    "monthly_profit_rate": rate,
                },
                {
                    "min_term_months": 1,
                    "max_term_months": 24,
                    "min_amount": 50_000.01,
                    "max_amount": 100_000,
                    "monthly_profit_rate": rate,
                },
                {
                    "min_term_months": 1,
                    "max_term_months": 12,
                    "min_amount": 100_000.01,
                    "max_amount": 150_000,
                    "monthly_profit_rate": rate,
                },
            ]
        campaign["bank_products"].append(
            {
                "bank_slug": "tom-katilim",
                "bank_name": "TOM Katılım",
                "external_product_id": product["product_code"],
                "campaign_name": product["campaign_name"],
                "rate_bands": rate_bands,
                "monthly_profit_rate": rate,
                "source_url": TOM_BANK_PAGE,
            }
        )
    return list(campaigns.values())


def turkiye_finans_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    credit_id: int | None = None,
) -> dict[str, Any] | None:
    """Türkiye Finans'ın sayfada kullandığı resmî oran tablosuyla teklif üretir."""
    selected_credit_id = credit_id or _PRODUCT_IDS.get(financing_type)
    if (
        selected_credit_id is None
        or _TURKIYE_FINANS_PRODUCT_TYPES.get(selected_credit_id) != financing_type
    ):
        return None

    products = _fetch_turkiye_finans_products()
    product = next(
        (
            item
            for item in products
            if int(item.get("CreditID", -1)) == selected_credit_id
            and item.get("ShowInSubPage")
        ),
        None,
    )
    if product is None:
        return None
    rate_band = next(
        (
            item
            for item in product.get("FinanceCalculatorCreditList", [])
            if int(item.get("Min", 0)) <= term_months <= int(item.get("Max", 0))
            and (not item.get("TutarMin") or amount >= float(item["TutarMin"]))
            and (not item.get("TutarMax") or amount <= float(item["TutarMax"]))
        ),
        None,
    )
    if rate_band is None:
        return None

    monthly_profit_rate = float(rate_band["Value"])
    bsmv = float(product.get("Bitt") or 0)
    kkdf = float(product.get("Rusf") or 0)
    effective_monthly_rate = monthly_profit_rate / 100 * (1 + bsmv + kkdf)
    installment = _annuity(amount, effective_monthly_rate, term_months)
    allocation_rate = float(product.get("AllocationFee") or 0)
    special_fee_rate = float(rate_band.get("SpecialAllocationFee") or 0)
    fixed_fees = float(product.get("ExpertiseFee") or 0) + float(
        product.get("MortgageFee") or 0
    )
    fees_total = round(amount * (allocation_rate + special_fee_rate) + fixed_fees, 2)

    return {
        "bank_slug": "turkiye-finans",
        "bank_name": "Türkiye Finans",
        "product_name": product.get("Title") or rate_band.get("Title") or "Finansman",
        "status": "available",
        "monthly_profit_rate": monthly_profit_rate,
        "monthly_installment": installment,
        "total_repayment": round(installment * term_months, 2),
        "annual_cost_rate": round(((1 + effective_monthly_rate) ** 12 - 1) * 100, 2),
        "fees_total": fees_total,
        "source_url": f"{TURKIYE_FINANS_PAGE}?financeID={selected_credit_id}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "calculation_origin": "official_calculator_live",
        "message": (
            "Oran Türkiye Finans'ın resmî hesaplayıcı servisinden canlı alındı; "
            "taksitte BSMV ve KKDF etkisi hesaplandı."
        ),
    }


def kuveyt_turk_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    """Kuveyt Türk'ün resmî sayfasının döndürdüğü hesap sonucunu aynen kullanır."""
    product_name = ""
    resolved_code = ""
    if product_code:
        selected = next(
            (
                item
                for item in _fetch_kuveyt_products()
                if item["external_product_id"] == product_code
            ),
            None,
        )
        if selected is None or selected["financing_type"] != financing_type:
            return None
        resolved_code = selected["product_code"]
        product_name = selected["campaign_name"]
        limits = _kuveyt_limits(selected, amount)
        if not (
            limits["min_term_months"] <= term_months <= limits["max_term_months"]
            and (limits["min_amount"] is None or amount >= limits["min_amount"])
            and (limits["max_amount"] is None or amount <= limits["max_amount"])
        ):
            return None
    else:
        product = _KUVEYT_PRODUCTS.get(financing_type)
        if product is None:
            return None
        resolved_code, product_name = product
    request_body = json.dumps(
        {
            "i": False,
            "p1": "1",
            "p2": str(amount),
            "p3": str(term_months),
            "p4": resolved_code,
            "p5": resolved_code,
            "p6": "0.00",
            "p7": "",
            "p8": product_name,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    payload = _request_json(
        KUVEYT_TURK_API,
        data=request_body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": KUVEYT_TURK_PAGE,
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
            "X-Bone-Language": "TR",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
    )
    meta = payload.get("Meta")
    if not isinstance(meta, dict):
        return None

    return {
        "bank_slug": "kuveyt-turk",
        "bank_name": "Kuveyt Türk",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": float(meta["ProfitRate"]),
        "monthly_installment": float(meta["InstallmentPayment"]),
        "total_repayment": float(meta["TotalAmount"]),
        "annual_cost_rate": float(meta["YearlyCost"]),
        "fees_total": float(meta.get("TotalCost") or meta.get("AllocationAmount") or 0),
        "source_url": KUVEYT_TURK_PAGE,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "calculation_origin": "official_calculator_live",
        "message": "Sonuç Kuveyt Türk'ün resmî hesaplayıcı servisinden canlı alındı.",
    }


def tom_katilim_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    """TOM Bank'ın resmî hesaplayıcısındaki oran ve ödeme planını kullanır."""
    product_code = product_code or "TKTCDGRFNS"
    definition = _TOM_CATALOG_DEFINITIONS.get(product_code)
    if definition is None or definition[1] != financing_type:
        return None
    if financing_type != "consumer" or not 5_000 <= amount <= 150_000:
        return None
    max_term = 36 if amount <= 50_000 else 24 if amount <= 100_000 else 12
    if not 1 <= term_months <= max_term:
        return None
    page = TOM_BANK_PAGE
    api = "https://webintegration.tombank.com.tr/webintegration/api/LoanCalculation"
    token = base64.b64encode(
        b"TBOnlineIntegrationUser:kOdWObHamEZkPe7UigsetQ=="
    ).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Referer": page,
        "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
    }
    rates = _request_json(
        f"{api}/LoanRateList",
        data=json.dumps({"ProductCode": product_code}).encode(),
        headers=headers,
        method="POST",
    )
    rate_data = rates.get("Data") or rates.get("data") or {}
    rate_rows = (
        rate_data.get("LoanRateList") if isinstance(rate_data, dict) else rate_data
    ) or []
    rate_row = next(
        (
            row
            for row in rate_rows
            if int(
                row.get("InstallmentsCount")
                or row.get("InstallmentCount")
                or row.get("MaturityCount")
                or 0
            )
            == term_months
        ),
        None,
    )
    if not rate_row:
        return None
    rate = float(
        rate_row.get("LoanRate") or rate_row.get("Rate") or rate_row.get("ProfitRate")
    )
    plan = _request_json(
        f"{api}/GetLoanPayBackPlan",
        data=json.dumps(
            {
                "CustomRate": rate,
                "FundingAmount": amount,
                "InstallmentCount": term_months,
                "IsTotalAmountByInstallmentAmount": False,
                "ProductCode": product_code,
            }
        ).encode(),
        headers=headers,
        method="POST",
    )
    data = plan.get("Data") or plan.get("data") or {}
    installments = data.get("installmentList") or data.get("InstallmentList") or []
    if not installments:
        return None
    installment = _tr_number(installments[0].get("Amount"))
    total = _tr_number(data.get("TotalAmount")) or round(installment * term_months, 2)
    return {
        "bank_slug": "tom-katilim",
        "bank_name": "TOM Katılım",
        "product_name": definition[2],
        "status": "available",
        "monthly_profit_rate": rate,
        "monthly_installment": installment,
        "total_repayment": total,
        "annual_cost_rate": _tr_number(data.get("TotalCost")) or None,
        "fees_total": (
            _tr_number(
                data.get("CommissionAmount")
                or data.get("CommisionAmount")
                or data.get("AllocationFee")
            )
            or round(amount * 0.005, 2)
        ),
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": (
            "Sonuç TOM Bank'ın resmî hesaplayıcı servisinden canlı alındı. "
            "Tahsis ücreti %0,5 olup BSMV hariçtir."
        ),
    }


def _csrf_token(html: str) -> str:
    match = re.search(
        r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)',
        html,
    ) or re.search(
        r'value=["\']([^"\']+)["\'][^>]*name=["\']__RequestVerificationToken',
        html,
    )
    if not match:
        raise ValueError("Doğrulama anahtarı bulunamadı")
    return match.group(1)


def dunya_katilim_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    if product_code:
        selected = next(
            (
                item for item in _fetch_dunya_products()
                if item["product_code"] == product_code
            ),
            None,
        )
        if selected is None or selected["financing_type"] != financing_type:
            return None
        product_name = selected["official_name"]
    else:
        product = _DUNYA_PRODUCTS.get(financing_type)
        if product is None:
            return None
        product_code, product_name = product
    page = DUNYA_KATILIM_PAGE
    base = "https://dunyakatilim.com.tr"
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    common = {
        "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        "Referer": page,
        "X-Requested-With": "XMLHttpRequest",
    }
    with opener.open(Request(page, headers=common), timeout=8.0) as response:
        token = _csrf_token(response.read().decode("utf-8"))
    form_headers = {**common, "Content-Type": "application/x-www-form-urlencoded"}
    values = _request_json(
        f"{base}/LoanInstallmentValues?lang=tr",
        data=urlencode(
            {"productCode": product_code, "__RequestVerificationToken": token}
        ).encode(),
        headers=form_headers,
        method="POST",
        opener=opener,
    )
    min_amount = _tr_number(values.get("minAmount"))
    max_amount = _tr_number(values.get("maxAmount"))
    min_term = int(
        values.get("minInstallment")
        or values.get("minInstallmentCount")
        or values.get("minMaturity")
        or 1
    )
    max_term = int(
        values.get("maxInstallment")
        or values.get("maxInstallmentCount")
        or values.get("maxMaturity")
        or 0
    )
    if (min_amount and amount < min_amount) or (max_amount and amount > max_amount):
        return None
    if term_months < min_term or (max_term and term_months > max_term):
        return None
    payload = _request_json(
        f"{base}/LoanCheckRate?lang=tr",
        data=urlencode(
            {
                "productName": product_name,
                "productCode": product_code,
                "productCategory": values.get("productCategory") or values.get("category") or "",
                "amount": str(amount).replace(".", ","),
                "installmentCount": term_months,
                "userRate": "0,00",
                "userSelected": "false",
                "__RequestVerificationToken": token,
            }
        ).encode(),
        headers=form_headers,
        method="POST",
        opener=opener,
    )
    installment = _tr_number(payload.get("monthlyInterest"))
    if not installment:
        return None
    html = str(payload.get("paymentPlanHTML") or "")
    annual_match = re.search(r"Yıllık\s+kar\s+oranı.*?([0-9]+(?:[.,][0-9]+)?)", html, re.I | re.S)
    return {
        "bank_slug": "dunya-katilim",
        "bank_name": "Dünya Katılım",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": _tr_number(payload.get("rate")),
        "monthly_installment": installment,
        "total_repayment": _tr_number(payload.get("totalPayment")),
        "annual_cost_rate": _tr_number(annual_match.group(1)) if annual_match else None,
        "fees_total": round(amount * 0.005, 2),
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": "Sonuç Dünya Katılım'ın resmî hesaplayıcı servisinden canlı alındı.",
        "_limits": {
            "min_term_months": min_term,
            "max_term_months": max_term,
            "min_amount": min_amount or None,
            "max_amount": max_amount or None,
        },
    }


def albaraka_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    if product_code:
        selected = next(
            (
                item for item in _fetch_albaraka_products()
                if item["campaign_code"] == product_code
            ),
            None,
        )
        if selected is None or selected["financing_type"] != financing_type:
            return None
        if (
            term_months < selected["min_term_months"]
            or term_months > selected["max_term_months"]
            or amount < selected["min_amount"]
            or (
                selected.get("max_amount") is not None
                and amount > selected["max_amount"]
            )
        ):
            return None
        rate = float(selected["monthly_profit_rate"])
        tax_factor = 1.0
        if financing_type in {"consumer", "vehicle"}:
            tax_factor = 1.30
        elif financing_type == "commercial":
            tax_factor = 1.15
        elif product_code == "VRKNT0B":
            tax_factor = 1.15
        effective_rate = rate / 100 * tax_factor
        installment = _annuity(amount, effective_rate, term_months)
        return {
            "bank_slug": "albaraka-turk",
            "bank_name": "Albaraka Türk",
            "product_name": selected["campaign_name"],
            "status": "available",
            "monthly_profit_rate": rate,
            "monthly_installment": installment,
            "total_repayment": round(installment * term_months, 2),
            "annual_cost_rate": round(((1 + effective_rate) ** 12 - 1) * 100, 2),
            "fees_total": round(amount * 0.005 * 1.15, 2),
            "source_url": selected["source_url"],
            "retrieved_at": _timestamp(),
            "calculation_origin": "official_published_rate",
            "message": (
                "Kâr oranı ve ürün sınırları Albaraka Türk'ün resmî ana sayfa "
                "hesaplayıcısından alındı; taksit yayımlanan oranla hesaplandı."
            ),
        }

    products = {
        "consumer": ("003", "148", "Eşya Finansmanı"),
        "vehicle": ("002", "176", "Sıfır Taşıt Finansmanı"),
        "housing": ("001", "171", "İlk Evim Konut Finansmanı"),
    }
    product = products.get(financing_type)
    if product is None:
        return None
    financing_code, sub_code, product_name = product
    page = "https://basvur.albaraka.com.tr/jet-finansman"
    sale_price = amount * 2 if financing_type in {"vehicle", "housing"} else amount
    payload = _request_json(
        "https://basvur.albaraka.com.tr/ws/wsPaymentPlan",
        data=json.dumps(
            {
                "CustomerBranchCode": "9900",
                "CustomerNumber": "",
                "FinancingType": financing_code,
                "SubFinancingType": sub_code,
                "FinancingAmount": _plain_amount(amount),
                "FinancingInstallmentAmount": "0",
                "MaturityCount": str(term_months),
                "CalculationMethod": "T",
                "SalePrice": _plain_amount(sale_price),
            }
        ).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": page,
            "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        },
        method="POST",
    )
    if not isinstance(payload, dict) or payload.get("ErrorMessage"):
        return None
    expenses = payload.get("PaymentPlanExpense") or {}
    return {
        "bank_slug": "albaraka-turk",
        "bank_name": "Albaraka Türk",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": _tr_number(payload.get("ProfitRate")),
        "monthly_installment": _tr_number(payload.get("InstallmentAmount")),
        "total_repayment": _tr_number(payload.get("TotalProjectAmount")),
        "annual_cost_rate": _tr_number(payload.get("AnnualCostRate")) or None,
        "fees_total": _tr_number(expenses.get("TotalExpenseAmount")),
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": "Sonuç Albaraka Türk'ün resmî Jet Finansman servisinden canlı alındı.",
    }


def ziraat_katilim_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_id: str | None = None,
) -> dict[str, Any] | None:
    if product_id:
        definition = _ZIRAAT_CATALOG_DEFINITIONS.get(product_id)
        if definition is None or definition[1] != financing_type:
            return None
        product_name = definition[2]
    else:
        product = _ZIRAAT_PRODUCTS.get(financing_type)
        if product is None:
            return None
        product_id, product_name = product
    page = ZIRAAT_KATILIM_PAGE
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": page,
        "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        "X-Requested-With": "XMLHttpRequest",
    }
    info = _ziraat_product_info(product_id)
    allowed_terms = [int(value) for value in info.get("range") or []]
    minimum_amount = _tr_number(info.get("minimum_amount"))
    maximum_amount = _tr_number(info.get("maximum_amount"))
    if (
        term_months not in allowed_terms
        or amount < minimum_amount
        or (maximum_amount and amount > maximum_amount)
    ):
        return None
    rate = _tr_number(info.get("ratio"))
    if not rate:
        return None
    result = _request_json(
        "https://www.ziraatkatilim.com.tr/ajax/finansmanhesapla",
        data=urlencode(
            {
                "lang": "tr",
                # Oran resmî get-vade servisinden alındı. Hesaplama servisine
                # açıkça göndermek, bankanın zaman zaman %0'a düşen otomatik
                # oran çözümlemesini devre dışı bırakır.
                "finansman_is_bank_ratio": "false",
                "finans_type": product_id,
                "finans_kar_orani": rate,
                "finans_vade": term_months,
                "finans_tutari": amount,
            }
        ).encode(),
        headers=headers,
        method="POST",
    )
    commands = result if isinstance(result, list) else result.get("commands", [])
    inserts = {
        str(row.get("selector")): row.get("data")
        for row in commands
        if isinstance(row, dict)
    }
    installment = _tr_number(inserts.get(".finansman-taksit-tutar"))
    total = _tr_number(inserts.get(".finansman-toplam-tutar"))
    if not installment:
        return None
    return {
        "bank_slug": "ziraat-katilim",
        "bank_name": "Ziraat Katılım",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": rate,
        "monthly_installment": installment,
        "total_repayment": total or round(installment * term_months, 2),
        "annual_cost_rate": None,
        "fees_total": None,
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": (
            "Güncel oran ve ödeme planı Ziraat Katılım'ın resmî hesaplama "
            "servislerinden canlı alındı."
        ),
    }


def vakif_katilim_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    if product_code:
        catalog_product = _VAKIF_CATALOG_PRODUCTS.get(product_code)
        if catalog_product is None or catalog_product[1] != financing_type:
            return None
        product_name = catalog_product[2]
    else:
        product = _VAKIF_PRODUCTS.get(financing_type)
        if product is None:
            return None
        product_code, product_name = product
    page = (
        "https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/"
        "hesaplama-araclari/finansman-hesaplama"
    )
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    common = {
        "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)",
        "Referer": page,
    }
    with opener.open(Request(page, headers=common), timeout=8.0) as response:
        token = _csrf_token(response.read().decode("utf-8"))
    query = urlencode(
        {
            "langId": 1055,
            "language": "tr-TR",
            "financingType": product_code,
            "amount": _plain_amount(amount),
            "numberOfInstallments": term_months,
            "profitRate": "",
            "calculateType": 1,
        }
    )
    payload = _request_json(
        f"https://www.vakifkatilim.com.tr/plugins/FinancingComputationExecute?{query}",
        data=urlencode({"__RequestVerificationToken": token}).encode(),
        headers={**common, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
        opener=opener,
    )
    if payload.get("isErrorFriendly") or not _tr_number(payload.get("installmentAmount")):
        return None
    fixed_fees = _tr_number(payload.get("appraisementFee")) + _tr_number(
        payload.get("mortgageReleaseFee")
    )
    return {
        "bank_slug": "vakif-katilim",
        "bank_name": "Vakıf Katılım",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": _tr_number(payload.get("profitRate")),
        "monthly_installment": _tr_number(payload.get("installmentAmount")),
        "total_repayment": _tr_number(payload.get("totalAmount")),
        "annual_cost_rate": None,
        "fees_total": round(fixed_fees + amount * 0.005, 2),
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": "Sonuç Vakıf Katılım'ın resmî hesaplayıcı servisinden canlı alındı.",
    }


def emlak_katilim_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    if product_code:
        definition = _EMLAK_CATALOG_DEFINITIONS.get(product_code)
        if definition is None or definition[1] != financing_type:
            return None
        product_name = definition[2]
        segment_id = definition[3]
    else:
        product = _EMLAK_PRODUCTS.get(financing_type)
        if product is None:
            return None
        product_code, product_name = product
        segment_id = _EMLAK_CATALOG_DEFINITIONS[product_code][3]
    limits = _emlak_product_limits(product_code)
    if not 1_000 <= amount <= 9_999_999:
        return None
    if not limits["min_term_months"] <= term_months <= limits["max_term_months"]:
        return None
    if product_code == "EVOFISGERECLERI" and amount > 50_000 and term_months > 24:
        return None
    page = EMLAK_KATILIM_PAGE
    query = urlencode(
        {
            "CalculationTypeId": 1,
            "ProductTypeId": product_code,
            "LoanSegmentId": segment_id,
            "LoanAmount": amount,
            "LoanMaturity": term_months,
            "CustomRate": 0,
        }
    )
    payload = _request_json(
        f"https://www.emlakkatilim.com.tr/Plugins/CalculateLoansProduct?{query}",
        headers={"Referer": page, "User-Agent": "Mozilla/5.0 (compatible; RAGnROLL/1.0)"},
    )
    if not payload.get("Success"):
        return None
    data = payload.get("Data") or {}
    installments = data.get("InstallmentContractList") or []
    if not installments:
        return None
    return {
        "bank_slug": "emlak-katilim",
        "bank_name": "Emlak Katılım",
        "product_name": product_name,
        "status": "available",
        "monthly_profit_rate": _tr_number(data.get("ProfitRate")),
        "monthly_installment": _tr_number(installments[0].get("Amount")),
        "total_repayment": _tr_number(data.get("TotalInstallmentAmount")),
        "annual_cost_rate": _tr_number(data.get("TotalCost")) or None,
        "fees_total": _tr_number(data.get("TotalExpense")),
        "source_url": page,
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_calculator_live",
        "message": "Sonuç Emlak Katılım'ın resmî hesaplayıcı servisinden canlı alındı.",
    }


def hayat_finans_quote(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    product_code: str | None = None,
) -> dict[str, Any] | None:
    """Hayat Finans'ın resmî maliyet tablosunda açıkça yayımlanan vadeleri kullanır."""
    product_code = product_code or "BANA-BUNU-AL"
    try:
        product = next(
            item for item in _fetch_hayat_products()
            if item["product_code"] == product_code
        )
    except (StopIteration, ValueError):
        return None
    allowed_terms = set(product.get("allowed_terms") or [])
    if (
        financing_type != product["financing_type"]
        or product_code != "BANA-BUNU-AL"
        or term_months not in allowed_terms
        or (product.get("min_amount") is not None and amount < product["min_amount"])
        or (product.get("max_amount") is not None and amount > product["max_amount"])
    ):
        return None
    rate = float(product["monthly_profit_rate"])
    effective_rate = rate / 100 * 1.30
    installment = _annuity(amount, effective_rate, term_months)
    return {
        "bank_slug": "hayat-finans",
        "bank_name": "Hayat Finans",
        "product_name": product["campaign_name"],
        "status": "available",
        "monthly_profit_rate": rate,
        "monthly_installment": installment,
        "total_repayment": round(installment * term_months, 2),
        "annual_cost_rate": round(((1 + effective_rate) ** 12 - 1) * 100, 2),
        "fees_total": 0.0,
        "source_url": product["source_url"],
        "retrieved_at": _timestamp(),
        "calculation_origin": "official_published_rate",
        "message": (
            "Oran Hayat Finans'ın resmî maliyet tablosundan alındı; "
            "taksit bu oranla hesaplandı."
        ),
    }


def _verified_quote_key(
    slug: str, financing_type: str, amount: float, term_months: int, kwargs: dict[str, Any]
) -> tuple[str, str, str, float, int]:
    product_id = str(
        kwargs.get("product_code")
        or kwargs.get("product_id")
        or kwargs.get("credit_id")
        or ""
    )
    return slug, financing_type, product_id, round(float(amount), 2), term_months


def _remember_verified_quote(
    key: tuple[str, str, str, float, int], quote: dict[str, Any]
) -> None:
    if quote.get("monthly_profit_rate") is None:
        return
    with _verified_quote_cache_lock:
        _verified_quote_cache[key] = (datetime.now(timezone.utc), dict(quote))


def _last_verified_quote(
    key: tuple[str, str, str, float, int]
) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with _verified_quote_cache_lock:
        cached = _verified_quote_cache.get(key)
        if cached is None or now - cached[0] >= _CACHE_TTL:
            if cached is not None:
                _verified_quote_cache.pop(key, None)
            return None
        quote = dict(cached[1])
    rate_text = f"{float(quote['monthly_profit_rate']):.2f}".replace(".", ",")
    quote["calculation_origin"] = "last_verified_official_rate"
    quote["message"] = f"Son doğrulanmış resmî %{rate_text} oranı kullanıldı."
    return quote


def fetch_official_quotes(
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    turkiye_finans_credit_id: int | None = None,
    eligible_bank_slugs: set[str] | None = None,
    selected_product_ids: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Bir banka hatasının diğer teklifleri engellememesi için kaynakları izole eder."""
    quotes: dict[str, dict[str, Any]] = {}
    selected_product_ids = selected_product_ids or {}
    sources = (
        ("turkiye-finans", turkiye_finans_quote),
        ("kuveyt-turk", kuveyt_turk_quote),
        ("tom-katilim", tom_katilim_quote),
        ("dunya-katilim", dunya_katilim_quote),
        ("albaraka-turk", albaraka_quote),
        ("ziraat-katilim", ziraat_katilim_quote),
        ("vakif-katilim", vakif_katilim_quote),
        ("emlak-katilim", emlak_katilim_quote),
        ("hayat-finans", hayat_finans_quote),
    )
    if eligible_bank_slugs is not None:
        sources = tuple(item for item in sources if item[0] in eligible_bank_slugs)
    if not sources:
        return quotes
    failed: list[
        tuple[str, Any, dict[str, Any], tuple[str, str, str, float, int]]
    ] = []
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        jobs = {}
        for slug, source in sources:
            kwargs = {
                "financing_type": financing_type,
                "amount": amount,
                "term_months": term_months,
            }
            if slug == "turkiye-finans":
                selected_tf_id = selected_product_ids.get(slug)
                kwargs["credit_id"] = (
                    int(selected_tf_id) if selected_tf_id else turkiye_finans_credit_id
                )
            elif slug == "kuveyt-turk":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "dunya-katilim":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "albaraka-turk":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "tom-katilim":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "vakif-katilim":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "ziraat-katilim":
                kwargs["product_id"] = selected_product_ids.get(slug)
            elif slug == "emlak-katilim":
                kwargs["product_code"] = selected_product_ids.get(slug)
            elif slug == "hayat-finans":
                kwargs["product_code"] = selected_product_ids.get(slug)
            cache_key = _verified_quote_key(
                slug, financing_type, amount, term_months, kwargs
            )
            jobs[executor.submit(source, **kwargs)] = (
                slug,
                source,
                kwargs,
                cache_key,
            )
        for job in as_completed(jobs):
            slug, source, kwargs, cache_key = jobs[job]
            try:
                quote = job.result()
            except Exception:
                quote = None
                failed.append((slug, source, kwargs, cache_key))
            if quote:
                _remember_verified_quote(cache_key, quote)
                quotes[str(quote["bank_slug"])] = quote
    # Bankaların WAF katmanı eşzamanlı çağrıyı bazen tek seferlik reddedebiliyor.
    # Yalnızca hata veren kaynakları bir kez ardışık denemek eksik kartları azaltır.
    for slug, source, kwargs, cache_key in failed:
        try:
            quote = source(**kwargs)
        except Exception:
            quote = _last_verified_quote(cache_key)
        if quote:
            if quote.get("calculation_origin") != "last_verified_official_rate":
                _remember_verified_quote(cache_key, quote)
            quotes[slug] = quote
    return quotes
