"""Düzeltilmiş kampanyaları ve terminolojiyi kalıcı Chroma indeksine yükler."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import sqrt
import os
from pathlib import Path

from src.persistence import CampaignStore
from src.retrieval import (
    ChromaIndexer,
    EvrenQdrantIndexer,
    EvrenQdrantRetriever,
    SemanticEmbeddingProvider,
)


class SmokeEmbeddingProvider:
    """Container sözleşmesi için ağ/model indirmeyen deterministik embedding."""

    model_name = "ragnroll-smoke-hash-v1"

    @staticmethod
    def _embed(text: str) -> list[float]:
        values = [float(value) - 127.5 for value in sha256(text.encode("utf-8")).digest()]
        norm = sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts) -> list[list[float]]:
        return [self._embed(str(text)) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(str(text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", default=os.getenv("RAGNROLL_DB_PATH", "data/ragnroll.sqlite3")
    )
    parser.add_argument("--path")
    parser.add_argument("--collection")
    parser.add_argument("--embedding-model")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("RAGNROLL_INDEX_BATCH_SIZE", "8")),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Model indirmeden Chroma yazma sözleşmesini doğrula; arama için kullanma",
    )
    parser.add_argument(
        "--require-evren",
        action="store_true",
        help="EVREN yapılandırılmışsa uzak indeks başarısızlığında çıkış kodu 2 döndür",
    )
    args = parser.parse_args()
    if args.smoke and args.embedding_model:
        parser.error("--smoke ile --embedding-model birlikte kullanılamaz")
    provider = SmokeEmbeddingProvider() if args.smoke else (
        SemanticEmbeddingProvider(args.embedding_model) if args.embedding_model else None
    )
    store = CampaignStore(Path(args.database))
    result = ChromaIndexer(
        store,
        path=Path(args.path) if args.path else None,
        collection_name=args.collection,
        provider=provider,
    ).build(batch_size=args.batch_size)
    result["smoke"] = args.smoke
    evren_retriever = EvrenQdrantRetriever()
    evren_failure = False
    if args.smoke:
        result["evren"] = {"status": "skipped", "reason": "smoke_mode"}
    elif not evren_retriever.enabled:
        result["evren"] = {"status": "disabled", "reason": "credentials_missing"}
    else:
        try:
            result["evren"] = EvrenQdrantIndexer(
                store, retriever=evren_retriever
            ).build(batch_size=args.batch_size)
        except Exception as exc:
            evren_failure = True
            result["evren"] = {
                "status": "failed",
                "reason": type(exc).__name__,
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if args.require_evren and evren_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
