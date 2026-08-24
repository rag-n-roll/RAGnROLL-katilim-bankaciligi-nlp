"""Kalıcı runtime volume'unu hazırlar ve API sürecini başlatır."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
from typing import Sequence

from src.persistence import CampaignStore


DEFAULT_COMMAND = (
    "uvicorn",
    "src.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
)


def _enabled(value: str | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    return value.casefold() not in {"0", "false", "off", "hayır", "hayir"}


def bootstrap_runtime(
    *,
    database: Path,
    runtime_root: Path,
    seed_dataset: Path,
    seed_on_empty: bool = True,
) -> dict[str, object]:
    """Boş volume'u seed eder; mevcut SQLite verisini hiçbir zaman silmez."""

    runtime_root.mkdir(parents=True, exist_ok=True)
    for directory in (
        runtime_root / "data" / "raw",
        runtime_root / "data" / "processed",
        runtime_root / "outputs",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    store = CampaignStore(database)
    summary = store.dashboard_summary()
    imported = 0
    if seed_on_empty and summary["record_count"] == 0:
        if not seed_dataset.is_file():
            raise FileNotFoundError(f"Başlangıç veri seti bulunamadı: {seed_dataset}")
        payload = json.loads(seed_dataset.read_text(encoding="utf-8"))
        imported = store.import_dataset(payload)

    processed_snapshot = runtime_root / "data" / "processed" / "campaigns.json"
    if (
        seed_dataset.is_file()
        and not processed_snapshot.exists()
        and seed_dataset.resolve() != processed_snapshot.resolve()
    ):
        shutil.copyfile(seed_dataset, processed_snapshot)

    return {
        "database": str(database),
        "runtime_root": str(runtime_root),
        "seeded_records": imported,
        "record_count": store.dashboard_summary()["record_count"],
        "processed_snapshot": str(processed_snapshot),
    }


def main(argv: Sequence[str] | None = None) -> int:
    database = Path(os.getenv("RAGNROLL_DB_PATH", "/app/runtime/ragnroll.sqlite3"))
    runtime_root = Path(os.getenv("RAGNROLL_RUNTIME_ROOT", "/app/runtime"))
    seed_dataset = Path(
        os.getenv("RAGNROLL_BOOTSTRAP_DATASET", "/app/bootstrap/campaigns.json")
    )
    result = bootstrap_runtime(
        database=database,
        runtime_root=runtime_root,
        seed_dataset=seed_dataset,
        seed_on_empty=_enabled(os.getenv("RAGNROLL_BOOTSTRAP_ON_EMPTY")),
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)

    command = list(argv if argv is not None else sys.argv[1:]) or list(DEFAULT_COMMAND)
    os.execvp(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
