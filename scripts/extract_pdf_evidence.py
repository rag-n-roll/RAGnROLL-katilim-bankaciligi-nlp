"""Kullanıcı PDF'lerinden sayfa numaralı kanıt JSONL'i üretir."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ingestion.pdf_evidence import extract_pdf_evidence
from src.ingestion.pdf_sources import build_pdf_manifest

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=80)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_pdf_manifest(args.pdf)
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        row for path in args.pdf
        for row in extract_pdf_evidence(path, max_pages=args.max_pages)
    ]
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"documents": len(manifest), "evidence_rows": len(rows)}, ensure_ascii=False))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
