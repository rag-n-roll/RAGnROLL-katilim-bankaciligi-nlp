from src.scraper.bddk import fetch_participation_banks


class FakeClient:
    def get_text(self, url: str) -> str:
        return """
        <div class="card">
          <button>Katılım Bankaları <small>(2)</small></button>
          <div class="accordionBody"><ul>
            <li class="row">
              <div class="baslikContainer">1. ÖRNEK KATILIM BANKASI A.Ş.</div>
              <div class="webAdresiContainer"><a href="https://ornek.example/">web</a></div>
              <button class="detayliGor" data-isDijital="(Dijital Banka)"></button>
            </li>
            <li class="row">
              <div class="baslikContainer">2. İKİNCİ KATILIM BANKASI A.Ş.</div>
              <div class="webAdresiContainer"><a href="https://ikinci.example/">web</a></div>
              <button class="detayliGor" data-isDijital=""></button>
            </li>
          </ul></div>
        </div>
        """


def test_bddk_parser_extracts_bank_rows():
    payload = fetch_participation_banks(FakeClient())
    assert payload["count"] == 2
    assert payload["banks"][0] == {
        "name": "ÖRNEK KATILIM BANKASI A.Ş.",
        "website": "https://ornek.example/",
        "is_digital": True,
    }
