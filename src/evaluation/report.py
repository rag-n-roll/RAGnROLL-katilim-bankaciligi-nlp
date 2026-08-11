"""Build a single PRD KPI summary from NER and classifier metric files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KPI_TARGETS = {
    "ner_precision": 0.85,
    "ner_recall": 0.80,
    "ner_f1": 0.82,
    "classification_accuracy": 0.85,
}


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _classifier_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("evaluation", report)


def build_report(
    ner_report: dict[str, Any], classifier_report: dict[str, Any]
) -> dict[str, Any]:
    ner_metrics = ner_report.get("metrics", ner_report)
    classifier_metrics = _classifier_metrics(classifier_report)
    values = {
        "ner_precision": ner_metrics.get("precision"),
        "ner_recall": ner_metrics.get("recall"),
        "ner_f1": ner_metrics.get("f1"),
        "classification_accuracy": classifier_metrics.get("accuracy"),
    }
    kpis = {}
    for name, target in KPI_TARGETS.items():
        value = values[name]
        kpis[name] = {
            "value": value,
            "target": target,
            "passed": value is not None and value >= target,
        }
    synthetic_warning = bool(
        ner_report.get("synthetic_data_warning")
        or classifier_report.get("synthetic_data_warning")
    )
    return {
        "kpis": kpis,
        "all_targets_met": all(item["passed"] for item in kpis.values()),
        "synthetic_data_warning": synthetic_warning,
        "competition_metric_eligible": not synthetic_warning,
        "notes": (
            "Synthetic results are baseline diagnostics and must not be reported as "
            "competition performance. Use a human-verified, source-separated test set."
            if synthetic_warning
            else "Metrics were built from reports not marked as synthetic."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ner_report")
    parser.add_argument("classifier_report")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_report(_read(args.ner_report), _read(args.classifier_report))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
