"""Düzeltilmiş kampanyaları ve terminolojiyi kalıcı Chroma indeksine yükler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.persistence import CampaignStore
from src.retrieval import ChromaIndexer, SemanticEmbeddingProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/ragnroll.sqlite3")
    parser.add_argument("--path", default="chroma_db")
    parser.add_argument("--collection")
    parser.add_argument("--embedding-model")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    provider = (
        SemanticEmbeddingProvider(args.embedding_model)
        if args.embedding_model
        else None
    )
    result = ChromaIndexer(
        CampaignStore(Path(args.database)),
        path=Path(args.path),
        collection_name=args.collection,
        provider=provider,
    ).build(batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
