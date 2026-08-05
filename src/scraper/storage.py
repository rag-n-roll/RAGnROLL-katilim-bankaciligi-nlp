"""JSON veri seti okuma/yazma yardimcilari."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Campaign, SCHEMA_VERSION


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(target)
    return target


def campaign_dataset(records: list[Campaign]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": [record.to_dict() for record in records],
    }
