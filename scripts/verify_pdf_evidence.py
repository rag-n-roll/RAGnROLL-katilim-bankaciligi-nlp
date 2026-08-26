"""PDF kanıt paketi doğrulama CLI'ı."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pdf_verify import verify_pdf_packet


def default_packet_paths() -> tuple[Path, Path, Path]:
    packet_dir = Path(__file__).resolve().parents[1] / "data" / "source_documents"
    return (
        packet_dir / "pdf_evidence.manifest.json",
        packet_dir / "pdf_evidence.jsonl",
        packet_dir / "pdf_extraction_report.json",
    )


def main() -> int:
    default_manifest, default_evidence, default_report = default_packet_paths()
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=default_manifest)
    parser.add_argument("--evidence", type=Path, default=default_evidence)
    parser.add_argument("--report", type=Path, default=default_report)
    args = parser.parse_args()
    result = verify_pdf_packet(
        manifest_path=args.manifest,
        evidence_path=args.evidence,
        report_path=args.report,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
