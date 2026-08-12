import json
from dataclasses import dataclass, field
from typing import Any

from src.scraper.banks import (
    AlbarakaScraper,
    DunyaKatilimScraper,
    KuveytTurkScraper,
)


@dataclass
class StubResponse:
    payload: Any
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return json.dumps(self.payload)


class PaginationClient:
    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents
        self.requests: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.handler = None

    def get_text(self, url: str) -> str:
        return self.documents[url]

    def get(self, url: str, *, params=None, headers=None):
        params = dict(params or {})
        headers = dict(headers or {})
        self.requests.append((url, params, headers))
        assert self.handler is not None
        return self.handler(url, params, headers)


def test_albaraka_uses_robots_safe_json_pagination_without_slug_queries():
    listing = AlbarakaScraper.config.listing_urls[0]
    client = PaginationClient(
        {
            listing: """
                <script>var UNIGATE={current:{langId:'lang-id'}};</script>
                <div class="kampanyalar-card">
                  <a href="/tr/kampanyalar/detay/ilk">İlk</a>
                </div>
                <a class="btn-outline-kampanyalar-primary">Daha Fazla</a>
            """,
        }
    )

    def respond(_url, params, headers):
        assert params["PageIndex"] == 2
        assert "Slug" not in params
        assert "searchUrl" not in params
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        return StubResponse(
            {
                "Result": True,
                "Data": {
                    "TotalCount": 2,
                    "Campaigns": [
                        {"Link": "/tr/kampanyalar/detay/ikinci"},
                    ],
                },
            }
        )

    client.handler = respond
    urls, failures = AlbarakaScraper(client)._discover_urls_for_scrape()

    assert failures == []
    assert urls == [
        "https://www.albaraka.com.tr/tr/kampanyalar/detay/ilk",
        "https://www.albaraka.com.tr/tr/kampanyalar/detay/ikinci",
    ]


def test_dunya_katilim_paginates_personal_and_business_campaigns():
    listing = DunyaKatilimScraper.config.listing_urls[0]
    client = PaginationClient(
        {
            listing: """
                <div class="notification-popup">
                  <a href="/kampanyalar/ilk">İlk</a>
                </div>
                <a id="moreCampaigns">Daha Fazla</a>
            """,
        }
    )

    def respond(_url, params, _headers):
        campaign_type = params["campaignType"]
        slug = "kisisel" if campaign_type == 1 else "ticari"
        return StubResponse(
            {
                "view": f'<a href="/kampanyalar/{slug}">{slug}</a>',
                "allRead": True,
            }
        )

    client.handler = respond
    urls, failures = DunyaKatilimScraper(client)._discover_urls_for_scrape()

    assert failures == []
    assert urls == [
        "https://dunyakatilim.com.tr/kampanyalar/ilk",
        "https://dunyakatilim.com.tr/kampanyalar/kisisel",
        "https://dunyakatilim.com.tr/kampanyalar/ticari",
    ]


def test_kuveyt_turk_follows_load_more_api_for_each_configured_category():
    first_listing, second_listing = KuveytTurkScraper.config.listing_urls

    def listing_html(category_id: str, slug: str) -> str:
        return f"""
            <select class="sub-cat">
              <option selected data-id="{category_id}">Kategori</option>
            </select>
            <div class="campaign-item">
              <a href="/kampanyalar/kendim-icin/{slug}/ilk">İlk</a>
            </div>
            <a class="load-more-btn">Daha Fazla Yükle</a>
            <script src="/magiclick.core.min.js?v=test"></script>
        """

    client = PaginationClient(
        {
            first_listing: listing_html("11", "kart-kampanyalari"),
            second_listing: listing_html("22", "musteri-ol-kampanyalari"),
            "https://www.kuveytturk.com.tr/magiclick.core.min.js?v=test": (
                'var ApiEndpoints={ck:"ck0d84?TOKEN"};'
            ),
        }
    )

    def respond(url, _params, headers):
        assert headers == {"Page": "2", "PageSize": "9"}
        if "p1=11" in url:
            slug = "kart-kampanyalari"
        else:
            assert "p1=22" in url
            slug = "musteri-ol-kampanyalari"
        return StubResponse(
            [
                {
                    "Url": f"/kampanyalar/kendim-icin/{slug}/ikinci",
                }
            ],
            headers={"Totalcount": "10"},
        )

    client.handler = respond
    urls, failures = KuveytTurkScraper(client)._discover_urls_for_scrape()

    assert failures == []
    assert len(urls) == 4
    assert len(set(urls)) == 4
    assert urls[-1].endswith("/musteri-ol-kampanyalari/ikinci")
