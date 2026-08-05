"""BDDK'nin resmi kurulus listesinden katilim bankalarini ceker."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from .http import HttpClient

BDDK_BANKS_URL = "https://www.bddk.gov.tr/Kurulus/Liste/90"


def fetch_participation_banks(client: HttpClient | None = None) -> dict[str, Any]:
    client = client or HttpClient()
    soup = BeautifulSoup(client.get_text(BDDK_BANKS_URL), "html.parser")
    heading = next(
        (
            button
            for button in soup.select("button")
            if "katılım bankaları" in button.get_text(" ", strip=True).lower()
            or "participation banks" in button.get_text(" ", strip=True).lower()
        ),
        None,
    )
    if heading is None:
        raise ValueError("BDDK sayfasinda katilim bankalari bolumu bulunamadi")
    card = heading.find_parent(class_="card")
    if card is None:
        raise ValueError("BDDK katilim bankalari karti bulunamadi")

    banks: list[dict[str, Any]] = []
    for item in card.select(".accordionBody li.row"):
        name_element = item.select_one(".baslikContainer")
        if not name_element:
            continue
        name = re.sub(r"^\s*\d+\.\s*", "", name_element.get_text(" ", strip=True)).strip()
        website_element = item.select_one(".webAdresiContainer a[href]")
        detail = item.select_one("button.detayliGor")
        if detail:
            digital_text = str(detail.get("data-isdijital", ""))
        else:
            digital_text = item.get_text(" ", strip=True)
        banks.append(
            {
                "name": name,
                "website": str(website_element["href"]).strip() if website_element else None,
                "is_digital": "dijital" in digital_text.lower(),
            }
        )
    if not banks:
        raise ValueError("BDDK sayfasindan banka kaydi ayiklanamadi")
    return {
        "source_url": BDDK_BANKS_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(banks),
        "banks": banks,
    }
