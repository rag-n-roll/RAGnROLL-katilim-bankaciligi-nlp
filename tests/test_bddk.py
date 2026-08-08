from src.scraper.bddk import BDDK_BANKS_URL, fetch_participation_banks


class FakeClient:
    def get_text(self, url: str) -> str:
        return """
        <div class="card">
          <button>Katılım Bankaları <small>(2)</small></button>
          <div class="accordionBody"><ul>
            <li class="row">
              <div class="baslikContainer">1. DÜNYA KATILIM BANKASI A.Ş.</div>
              <div class="webAdresiContainer"><a href="https://dunyakatilim.com.tr/">web</a></div>
              <button class="detayliGor" data-isDijital="(Dijital Banka)"></button>
            </li>
            <li class="row">
              <div class="baslikContainer">2. HAYAT FİNANS KATILIM BANKASI A.Ş.</div>
              <div class="webAdresiContainer"><a href="https://hayatfinans.com.tr/">web</a></div>
              <button class="detayliGor" data-isDijital=""></button>
            </li>
          </ul></div>
        </div>
        """


def test_bddk_parser_extracts_bank_rows():
    payload = fetch_participation_banks(FakeClient())
    assert payload["count"] == 2
    assert payload["banks"][0] == {
        "slug": "dunya-katilim",
        "name": "DÜNYA KATILIM BANKASI A.Ş.",
        "website": "https://dunyakatilim.com.tr/",
        "is_digital": True,
    }


def test_bddk_uses_normative_turkish_participation_bank_page():
    assert BDDK_BANKS_URL == "https://www.bddk.org.tr/Kurulus/Liste/77"
