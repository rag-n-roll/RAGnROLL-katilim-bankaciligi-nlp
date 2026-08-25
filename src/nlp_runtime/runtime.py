"""Üretim kampanya modelleri için küçük, doğrulanmış inference sınırı."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from src.nlp_runtime.advisory import analyze as analyze_advisory
from src.nlp_runtime.integrity import (
    DEFAULT_MANIFEST,
    REQUIRED_RUNTIME_PROVENANCE,
    verify_runtime,
)


class CampaignNlpRuntime:
    """Classifier ve spaCy NER modelini yalnız doğrulamadan sonra yükler."""

    def __init__(
        self,
        classifier: Any,
        ner: Any,
        *,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        self.classifier = classifier
        self.ner = ner
        self.provenance = provenance

    @classmethod
    def load(cls, manifest_path: str | Path = DEFAULT_MANIFEST) -> "CampaignNlpRuntime":
        artifacts = verify_runtime(manifest_path)
        joblib = importlib.import_module("joblib")
        spacy = importlib.import_module("spacy")
        return cls(
            joblib.load(artifacts.classifier),
            spacy.load(artifacts.ner),
            provenance=dict(REQUIRED_RUNTIME_PROVENANCE),
        )

    def analyze(
        self,
        text: str,
        *,
        structured: dict[str, Any] | None = None,
        record_id: str | None = None,
        content_hash: str | None = None,
        source_version: int | None = None,
    ) -> dict[str, Any]:
        return analyze_advisory(
            self.classifier,
            self.ner,
            text,
            structured=structured,
            record_id=record_id,
            content_hash=content_hash,
            source_version=source_version,
            provenance=self.provenance,
        )
