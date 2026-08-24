"""Kalıcı runtime volume'unu hazırlar ve API sürecini başlatır."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
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


def _database_is_healthy(database: Path) -> bool:
    if not database.is_file():
        return False
    try:
        with sqlite3.connect(database) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError:
        return False
    return bool(result and result[0] == "ok")


def _write_last_good_database(database: Path, snapshot: Path) -> None:
    """SQLite backup API'siyle tutarlı bir snapshot'ı atomik yayımlar."""

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    temporary = snapshot.with_name(f".{snapshot.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with sqlite3.connect(database) as source:
            with sqlite3.connect(temporary) as target:
                source.backup(target)
        if not _database_is_healthy(temporary):
            raise RuntimeError("Son iyi SQLite snapshot doğrulanamadı")
        os.replace(temporary, snapshot)
    finally:
        temporary.unlink(missing_ok=True)


def bootstrap_runtime(
    *,
    database: Path,
    runtime_root: Path,
    seed_dataset: Path,
    seed_on_empty: bool = True,
    last_good_database: Path | None = None,
) -> dict[str, object]:
    """Boş volume'u seed eder; bozuk aktif SQLite'ı son iyi kopyadan kurtarır."""

    runtime_root.mkdir(parents=True, exist_ok=True)
    for directory in (
        runtime_root / "data" / "raw",
        runtime_root / "data" / "processed",
        runtime_root / "outputs",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    last_good_database = last_good_database or (
        runtime_root / "last-good" / "ragnroll.sqlite3"
    )
    recovered = False
    if database.exists() and not _database_is_healthy(database):
        if not _database_is_healthy(last_good_database):
            raise RuntimeError(
                "Aktif SQLite bozuk ve doğrulanmış son iyi snapshot bulunamadı"
            )
        database.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(last_good_database, database)
        recovered = True

    store = CampaignStore(database)
    summary = store.dashboard_summary()
    imported = 0
    if seed_on_empty and summary["record_count"] == 0:
        if not seed_dataset.is_file():
            raise FileNotFoundError(f"Başlangıç veri seti bulunamadı: {seed_dataset}")
        payload = json.loads(seed_dataset.read_text(encoding="utf-8"))
        imported = store.import_dataset(payload)

    record_count = store.dashboard_summary()["record_count"]
    if record_count > 0:
        _write_last_good_database(database, last_good_database)

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
        "record_count": record_count,
        "processed_snapshot": str(processed_snapshot),
        "last_good_database": str(last_good_database),
        "recovered_from_last_good": recovered,
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
