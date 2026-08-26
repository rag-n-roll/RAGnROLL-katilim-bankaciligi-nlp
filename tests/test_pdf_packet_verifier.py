import json
from pathlib import Path

import pytest

from src.ingestion.pdf_verify import PdfPacketVerificationError, verify_pdf_packet
from scripts.verify_pdf_evidence import default_packet_paths


def test_verifier_requires_every_manifest_page_to_be_accounted_for(tmp_path: Path):
    manifest = tmp_path / "pdf_evidence.manifest.json"
    evidence = tmp_path / "pdf_evidence.jsonl"
    report = tmp_path / "pdf_extraction_report.json"
    manifest.write_text(
        json.dumps([{"document_id": "guide", "page_count": 10, "sha256": "a" * 64}]),
        encoding="utf-8",
    )
    evidence.write_text("", encoding="utf-8")
    report.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "document_id": "guide",
                        "manifest_page_count": 10,
                        "attempted": 9,
                        "complete": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PdfPacketVerificationError, match="tam sayfa"):
        verify_pdf_packet(manifest_path=manifest, evidence_path=evidence, report_path=report)


def test_verifier_cli_defaults_to_project_source_packet():
    manifest, evidence, report = default_packet_paths()

    assert manifest.name == "pdf_evidence.manifest.json"
    assert evidence.name == "pdf_evidence.jsonl"
    assert report.name == "pdf_extraction_report.json"
    assert manifest.parent == evidence.parent == report.parent
