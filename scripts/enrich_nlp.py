"""SQLite kampanyalarını doğrulanmış modellerle tek atomik batch halinde zenginleştir."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

from src.nlp_runtime import (
    CampaignNlpRuntime,
    EvrenAdvisoryAugmenter,
    EvrenAdvisoryError,
)
from src.nlp_runtime.integrity import DEFAULT_MANIFEST
from src.persistence import CampaignStore


def enrich_database(
    database: str | Path,
    *,
    manifest: str | Path = DEFAULT_MANIFEST,
    max_records: int | None = None,
    runtime_loader: Callable[[str | Path], Any] = CampaignNlpRuntime.load,
    augmenter: EvrenAdvisoryAugmenter | None = None,
) -> dict[str, Any]:
    """Analyze every selected snapshot before opening the single write transaction."""

    store = CampaignStore(database)
    candidates = store.nlp_enrichment_candidates(max_records=max_records)
    if not candidates:
        return {
            "candidates": 0,
            "analyzed": 0,
            "changed": 0,
            "database": str(Path(database)),
        }
    runtime = runtime_loader(manifest)
    augmenter = augmenter or EvrenAdvisoryAugmenter()
    analyses = []
    evren_augmented = 0
    evren_failed = 0
    for candidate in candidates:
        analysis = runtime.analyze(
            candidate["text"],
            structured=candidate["structured"],
            record_id=candidate["id"],
            content_hash=candidate["content_hash"],
            source_version=candidate["source_version"],
        )
        if augmenter.enabled:
            try:
                analysis = augmenter.augment(
                    analysis,
                    text=candidate["text"],
                    structured=candidate["structured"],
                )
                evren_augmented += int(
                    analysis.get("augmentation", {}).get("accepted_suggestions", 0) > 0
                )
            except EvrenAdvisoryError:
                evren_failed += 1
        analyses.append(analysis)
    changed = store.apply_nlp_analyses(analyses)
    return {
        "candidates": len(candidates),
        "analyzed": len(analyses),
        "changed": changed,
        "evren_enabled": augmenter.enabled,
        "evren_augmented": evren_augmented,
        "evren_failed": evren_failed,
        "database": str(Path(database)),
    }


def _environment_limit() -> int | None:
    raw = os.getenv("RAGNROLL_NLP_MAX_RECORDS", "").strip()
    if not raw or raw == "0":
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("RAGNROLL_NLP_MAX_RECORDS tam sayı olmalıdır") from exc
    if value < 1:
        raise ValueError("RAGNROLL_NLP_MAX_RECORDS pozitif olmalıdır")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", default=os.getenv("RAGNROLL_DB_PATH", "data/ragnroll.sqlite3")
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        max_records = (
            args.max_records if args.max_records is not None else _environment_limit()
        )
        if max_records is not None and max_records < 1:
            raise ValueError("--max-records pozitif olmalıdır")
        report = enrich_database(
            args.database,
            manifest=args.manifest,
            max_records=max_records,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        error = json.dumps(
            {"status": "failed", "error": str(exc)}, ensure_ascii=False
        )
        print(error, file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
