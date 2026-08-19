"""Dashboard API'si için kararlı ve SQL destekli veri sözleşmesi."""

from __future__ import annotations

from typing import Any

from .store import CampaignStore


class DashboardDataService:
    """Dashboard bileşenlerinin ihtiyaç duyduğu agregasyonları birleştirir."""

    def __init__(self, store: CampaignStore) -> None:
        self.store = store

    def snapshot(self, *, recent_limit: int = 5) -> dict[str, Any]:
        """Özet, dağılım, güncellik ve son kampanyaları tek sözleşmede döndürür."""
        return {
            "summary": self.store.dashboard_summary(),
            "distributions": {
                "banks": self.store.bank_distribution(),
                "product_types": self.store.product_type_distribution(),
            },
            "freshness": self.store.freshness_summary(),
            "recent_campaigns": self.store.recent_campaigns(limit=recent_limit),
        }
