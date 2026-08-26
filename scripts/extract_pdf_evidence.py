"""Kayıtlı PDF'lerin tamamından doğrulanmış RAG kanıt paketi üretir."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pdf_evidence import extract_pdf_document
from src.ingestion.pdf_registry import PdfSourceRegistry
from src.ingestion.pdf_sources import build_pdf_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROJECT_ROOT / "data" / "source_documents" / "pdf_source_registry.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-tokens", type=int, default=450)
    parser.add_argument("--overlap-tokens", type=int, default=50)
    args = parser.parse_args()

    registry = PdfSourceRegistry.from_path(args.registry)
    verified = [registry.verify(path) for path in args.pdf]
    manifest = build_pdf_manifest(args.pdf, registry=registry)
    chunks: list[dict] = []
    reports: list[dict] = []
    for source in verified:
        result = extract_pdf_document(
            source,
            max_tokens=args.max_tokens,
            overlap_tokens=args.overlap_tokens,
            max_pages=args.max_pages,
        )
        chunks.extend(result.chunks)
        expected_pages = next(
            item["page_count"]
            for item in manifest
            if item["document_id"] == source.document_id
        )
        reports.append(
            {
                **result.report,
                "manifest_page_count": expected_pages,
                "complete": result.report["attempted"] == expected_pages,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output.with_suffix(".manifest.json")
    report_path = args.report or args.output.with_name("pdf_extraction_report.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in chunks),
        encoding="utf-8",
    )
    report_payload = {
        "schema_version": 1,
        "documents": reports,
        "totals": {
            "documents": len(reports),
            "manifest_pages": sum(item["manifest_page_count"] for item in reports),
            "attempted_pages": sum(item["attempted"] for item in reports),
            "extracted_pages": sum(item["extracted"] for item in reports),
            "empty_pages": sum(item["empty"] for item in reports),
            "failed_pages": sum(item["failed"] for item in reports),
            "chunks": len(chunks),
        },
    }
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report_payload["totals"], ensure_ascii=False))
    return 0 if all(item["complete"] for item in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
