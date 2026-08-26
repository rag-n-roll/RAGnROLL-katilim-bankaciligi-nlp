"""Düzeltilmiş kampanyaları ve terminolojiyi kalıcı Chroma indeksine yükler."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import sqrt
import os
from pathlib import Path

from dotenv import load_dotenv

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


def required_evren_exit_code(*, required: bool, status: str) -> int:
    """Zorunlu uzak indeks hazır değilse sessiz başarıyı engelle."""

    return 2 if required and status != "ready" else 0


def load_runtime_env(path: str | Path = ".env") -> bool:
    """CLI çalıştırmalarında proje `.env` dosyasını güvenli biçimde yükle."""

    return bool(load_dotenv(dotenv_path=path, override=False))


def main() -> int:
    load_runtime_env()
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
        help="EVREN uzak indeksi hazır değilse çıkış kodu 2 döndür",
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
            result["evren"] = {
                "status": "failed",
                "reason": type(exc).__name__,
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return required_evren_exit_code(
        required=args.require_evren,
        status=str(result["evren"].get("status", "failed")),
    )


if __name__ == "__main__":
    raise SystemExit(main())
