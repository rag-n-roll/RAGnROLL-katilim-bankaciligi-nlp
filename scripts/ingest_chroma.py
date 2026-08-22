"""Düzeltilmiş kampanyaları ve terminolojiyi kalıcı Chroma indeksine yükler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.persistence import CampaignStore
from src.retrieval import ChromaIndexer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/ragnroll.sqlite3")
    parser.add_argument("--path", default="chroma_db")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    result = ChromaIndexer(
        CampaignStore(Path(args.database)), path=Path(args.path)
    ).build(batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
