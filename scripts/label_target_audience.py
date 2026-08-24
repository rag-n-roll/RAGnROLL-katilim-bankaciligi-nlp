"""Label campaign target-audience entities with grounded EVREN output."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

from src.annotation.taxonomy import TARGET_SEGMENTS
from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM
from src.llm.decisions import _json_object
from src.nlp_runtime.advisory import RUNTIME_CONTRACT, field_is_missing
from src.persistence import CampaignStore
from src.training.dataset_contract import is_synthetic, record_provenance


ALLOWED_SEGMENTS = tuple(label for label in TARGET_SEGMENTS if label != "other")
SEGMENT_PRIORITY = (
    "new_customer",
    "existing_customer",
    "individual_customer",
    "digital_customer",
    "salary_customer",
    "retired_customer",
    "youth_student",
    "commercial_sme",
    "farmer",
    "private_banking_customer",
    "cardholder",
)
LABEL_PATTERNS = {
    "new_customer": re.compile(
        r"\b(?:yeni\s+müşteri|ilk\s+kez\s+(?:bankamızın\s+)?müşteri|"
        r"müşterimiz\s+olmayan)\w*",
        re.I,
    ),
    "existing_customer": re.compile(
        r"\b(?:mevcut\s+müşteri|halihazırdaki\s+müşteri|"
        r"müşterimiz\s+olan)\w*",
        re.I,
    ),
    "individual_customer": re.compile(
        r"\b(?:bireysel\s+(?:müşteri|kart\s+sahib))\w*",
        re.I,
    ),
    "salary_customer": re.compile(r"\bmaaş\s+müşteri\w*", re.I),
    "retired_customer": re.compile(r"\bemekli(?:lik)?\s+müşteri\w*", re.I),
    "youth_student": re.compile(
        r"\b(?:genç\s+müşteri\w*|öğrenci\w*|üniversite\s+öğrenci\w*)", re.I
    ),
    "commercial_sme": re.compile(
        r"\b(?:ticari\s+müşteri|KOBİ|esnaf|işletme\s+sahibi)\w*", re.I
    ),
    "farmer": re.compile(r"\b(?:çiftçi|tarım\s+müşteri)\w*", re.I),
    "cardholder": re.compile(
        r"\b(?:(?:kart|Bankkart|Sağlam\s+Kart|Paraf)\s+sahib)\w*", re.I
    ),
    "digital_customer": re.compile(r"\bdijital\s+müşteri\w*", re.I),
    "private_banking_customer": re.compile(
        r"\bözel\s+bankacılık\s+(?:segment\s+)?müşteri\w*", re.I
    ),
}
EXCLUSION_PATTERN = re.compile(
    r"(?:dahil|kapsamında|geçerli)\s+(?:değil|değildir)|"
    r"(?:yararlanamaz|faydalanamaz|hariç tutul|kapsam dışı)",
    re.I,
)
CARD_ELIGIBILITY_PATTERN = re.compile(
    r"(?:kampanya|faydalan|yararlan|dahil|özel|geçerli|katıl|için|sunul)",
    re.I,
)


class TargetAudienceLabelError(RuntimeError):
    """Raised when a model response violates the target-audience contract."""


def _anchor_evidence(text: str, evidence: dict[str, Any]) -> tuple[int, int] | None:
    evidence_text = evidence.get("text")
    start = evidence.get("char_start")
    end = evidence.get("char_end")
    if (
        isinstance(evidence_text, str)
        and evidence_text
        and isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start < end <= len(text)
        and text[start:end] == evidence_text
    ):
        return start, end
    if not isinstance(evidence_text, str) or not evidence_text:
        return None
    anchored = text.find(evidence_text)
    if anchored < 0 or text.find(evidence_text, anchored + 1) >= 0:
        return None
    return anchored, anchored + len(evidence_text)


def validate_entities(payload: dict[str, Any], *, text: str) -> list[dict[str, Any]]:
    if set(payload) != {"entities"} or not isinstance(payload.get("entities"), list):
        raise TargetAudienceLabelError("Hedef kitle üst sözleşmesi geçersiz")
    accepted: list[dict[str, Any]] = []
    occupied: set[tuple[str, int, int]] = set()
    for item in payload["entities"]:
        if not isinstance(item, dict) or set(item) != {"label", "evidence"}:
            continue
        label = item.get("label")
        evidence = item.get("evidence")
        if label not in ALLOWED_SEGMENTS or not isinstance(evidence, dict):
            continue
        anchored = _anchor_evidence(text, evidence)
        if anchored is None:
            continue
        start, end = anchored
        evidence_text = text[start:end]
        pattern = LABEL_PATTERNS[label]
        if pattern.search(evidence_text) is None:
            continue
        sentence_start = max(
            text.rfind(".", 0, start),
            text.rfind("!", 0, start),
            text.rfind("?", 0, start),
            text.rfind("\n", 0, start),
        ) + 1
        sentence_ends = [
            position
            for marker in (".", "!", "?", "\n")
            if (position := text.find(marker, end)) >= 0
        ]
        sentence_end = min(sentence_ends) + 1 if sentence_ends else len(text)
        context = text[sentence_start:sentence_end]
        if EXCLUSION_PATTERN.search(context):
            continue
        if label == "cardholder" and CARD_ELIGIBILITY_PATTERN.search(context) is None:
            continue
        key = (label, start, end)
        if key in occupied:
            continue
        occupied.add(key)
        accepted.append(
            {
                "label": label,
                "context_kind": (
                    "card_eligibility" if label == "cardholder" else "customer_segment"
                ),
                "evidence": {
                    "text": evidence_text,
                    "char_start": start,
                    "char_end": end,
                },
            }
        )
    return sorted(
        accepted,
        key=lambda item: (
            item["evidence"]["char_start"],
            item["evidence"]["char_end"],
            item["label"],
        ),
    )


class TargetAudienceLabeler:
    def __init__(self, client: OpenAICompatibleLLM | None = None) -> None:
        settings = replace(
            LLMSettings.evren_from_env(),
            model=os.getenv("EVREN_NLP_MODEL", "llm-large").strip(),
            max_tokens=int(os.getenv("EVREN_TARGET_AUDIENCE_MAX_TOKENS", "1024")),
            temperature=0.0,
        )
        self.client = client or OpenAICompatibleLLM(settings)

    @staticmethod
    def _chunks(text: str, *, limit: int = 6000, overlap: int = 300):
        if len(text) <= limit:
            return [(0, text)]
        chunks = []
        start = 0
        while start < len(text):
            target_end = min(len(text), start + limit)
            end = target_end
            if target_end < len(text):
                boundary = max(
                    text.rfind(". ", start + limit // 2, target_end),
                    text.rfind("\n", start + limit // 2, target_end),
                )
                if boundary > start:
                    end = boundary + 1
            chunks.append((start, text[start:end]))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
        return chunks

    def _label_chunk(self, text: str) -> list[dict[str, Any]]:
        system = (
            "Katılım bankacılığı kampanya metnindeki hedef müşteri segmentlerini çıkar. "
            "Yalnız kampanyaya uygunluğu açıkça belirten ifadeleri etiketle; kanal, kart adı "
            "veya bankanın genel hitabı tek başına hedef kitle değildir. Mobil/web kullanımı "
            "digital_customer değildir; yalnız 'dijital müşteri' gibi açık ifade kabul edilir. "
            "'kartınızla' cardholder değildir; 'kart sahipleri' gibi açık ifade gerekir. "
            "Kampanyaya dahil olmayan, yararlanamayan veya kapsam dışı bırakılan grupları "
            "etiketleme. Olumsuz/dışlayıcı cümledeki segment hedef kitle değildir. "
            "Metinde açık hedef kitle yoksa boş entities döndür. Yalnız şu JSON'u döndür: "
            '{"entities":[{"label":"new_customer","evidence":{"text":"...",'
            '"char_start":0,"char_end":1}}]}. '
            "İzinli label değerleri: " + ", ".join(ALLOWED_SEGMENTS)
        )
        try:
            raw = "".join(
                self.client.stream_chat(system_prompt=system, user_prompt=text)
            ).strip()
        except LLMUnavailableError as exc:
            raise TargetAudienceLabelError("EVREN hedef kitle çağrısı başarısız") from exc
        payload = _json_object(raw)
        if payload is None:
            raise TargetAudienceLabelError("EVREN hedef kitle JSON çıktısı geçersiz")
        return validate_entities(payload, text=text)

    def label(self, text: str) -> list[dict[str, Any]]:
        accepted = []
        seen = set()
        for offset, chunk in self._chunks(text):
            for item in self._label_chunk(chunk):
                evidence = item["evidence"]
                start = offset + evidence["char_start"]
                end = offset + evidence["char_end"]
                key = (item["label"], start, end)
                if key in seen:
                    continue
                seen.add(key)
                accepted.append(
                    {
                        **item,
                        "evidence": {
                            "text": text[start:end],
                            "char_start": start,
                            "char_end": end,
                        },
                    }
                )
        return sorted(
            accepted,
            key=lambda item: (
                item["evidence"]["char_start"],
                item["evidence"]["char_end"],
                item["label"],
            ),
        )


def _read_completed(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") == "completed":
            rows[str(row["record_id"])] = row
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def label_database(
    database: str | Path,
    output: str | Path,
    *,
    max_records: int | None = None,
    labeler: TargetAudienceLabeler | None = None,
) -> dict[str, Any]:
    store = CampaignStore(database)
    candidates = store.nlp_enrichment_candidates()
    output_path = Path(output)
    completed = _read_completed(output_path)
    pending_all = [
        row
        for row in candidates
        if completed.get(row["id"], {}).get("content_hash") != row["content_hash"]
    ]
    pending = pending_all
    if max_records is not None:
        pending = pending[:max_records]
    labeler = labeler or TargetAudienceLabeler()
    labeled = empty = failed = 0
    for index, candidate in enumerate(pending, start=1):
        try:
            entities = labeler.label(candidate["text"])
            row = {
                "status": "completed",
                "record_id": candidate["id"],
                "content_hash": candidate["content_hash"],
                "text_sha256": sha256(candidate["text"].encode("utf-8")).hexdigest(),
                "entities": entities,
                "review_status": "auto_high_confidence" if entities else "no_explicit_target",
            }
            labeled += bool(entities)
            empty += not entities
        except (OSError, ValueError, TargetAudienceLabelError) as exc:
            row = {
                "status": "failed",
                "record_id": candidate["id"],
                "content_hash": candidate["content_hash"],
                "error": type(exc).__name__,
            }
            failed += 1
        _append_jsonl(output_path, row)
        print(
            f"[{index}/{len(pending)}] {candidate['id']} {row['status']} "
            f"entities={len(row.get('entities', []))}",
            flush=True,
        )
    final_completed = _read_completed(output_path)
    current_ids = {
        candidate["id"]
        for candidate in candidates
        if final_completed.get(candidate["id"], {}).get("content_hash")
        == candidate["content_hash"]
    }
    if len(current_ids) == len(candidates):
        _write_jsonl(
            output_path,
            (final_completed[record_id] for record_id in sorted(current_ids)),
        )
    return {
        "campaigns": len(candidates),
        "already_completed": len(candidates) - len(pending_all),
        "remaining": len(pending_all) - len(pending),
        "processed": len(pending),
        "labeled": labeled,
        "no_explicit_target": empty,
        "failed": failed,
        "output": str(output_path),
    }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def merge_training_datasets(
    database: str | Path,
    labels_path: str | Path,
    classifier_path: str | Path,
    ner_path: str | Path,
) -> dict[str, Any]:
    import spacy

    tokenizer = spacy.blank("tr")
    store = CampaignStore(database)
    candidates = {row["id"]: row for row in store.nlp_enrichment_candidates()}
    labels = _read_completed(Path(labels_path))
    classifier_file = Path(classifier_path)
    ner_file = Path(ner_path)
    classifier_rows = [json.loads(line) for line in classifier_file.read_text().splitlines()]
    ner_rows = [json.loads(line) for line in ner_file.read_text().splitlines()]
    classifier_updated = ner_updated = skipped_overlaps = 0
    for row in classifier_rows:
        record_id = str(row.get("source_id") or row.get("id") or "")
        label_row = labels.get(record_id)
        if (
            label_row is None
            or is_synthetic(row)
            or record_provenance(row) != "auto"
        ):
            continue
        segments = sorted({item["label"] for item in label_row["entities"]})
        row["annotations"]["target_segments"] = segments
        row["ai_reviewer"] = "evren-grounded-target-audience"
        row["ai_confidence"] = 1.0 if segments else 0.99
        classifier_updated += 1
    for row in ner_rows:
        record_id = str(row.get("source_id") or row.get("id") or "")
        label_row = labels.get(record_id)
        candidate = candidates.get(record_id)
        if (
            label_row is None
            or candidate is None
            or is_synthetic(row)
            or record_provenance(row) != "auto"
        ):
            continue
        entities = [item for item in row.get("entities", []) if item["label"] != "HEDEF_KITLE"]
        occupied = {
            position
            for item in entities
            for position in range(int(item["start"]), int(item["end"]))
        }
        base = row["text"].find(candidate["text"])
        if base < 0:
            continue
        doc = tokenizer.make_doc(row["text"])
        added = 0
        for item in label_row["entities"]:
            evidence = item["evidence"]
            start = base + evidence["char_start"]
            end = base + evidence["char_end"]
            span = doc.char_span(start, end)
            if span is None:
                span = doc.char_span(start, end, alignment_mode="expand")
                if span is None:
                    skipped_overlaps += 1
                    continue
                start, end = span.start_char, span.end_char
            positions = set(range(start, end))
            if occupied & positions:
                skipped_overlaps += 1
                continue
            occupied |= positions
            entities.append(
                {
                    "start": start,
                    "end": end,
                    "text": row["text"][start:end],
                    "label": "HEDEF_KITLE",
                    "segment": item["label"],
                }
            )
            added += 1
        row["entities"] = sorted(entities, key=lambda item: (item["start"], item["end"]))
        row.setdefault("metadata", {})["target_audience_reviewer"] = (
            "evren-grounded-target-audience"
        )
        ner_updated += int(added > 0 or not label_row["entities"])
    _write_jsonl(classifier_file, classifier_rows)
    _write_jsonl(ner_file, ner_rows)
    return {
        "labels": len(labels),
        "classifier_updated": classifier_updated,
        "ner_updated": ner_updated,
        "ner_skipped_overlaps": skipped_overlaps,
    }


def prune_label_file(database: str | Path, labels_path: str | Path) -> dict[str, Any]:
    candidates = {
        row["id"]: row for row in CampaignStore(database).nlp_enrichment_candidates()
    }
    path = Path(labels_path)
    rows = _read_completed(path)
    removed = 0
    for record_id, row in rows.items():
        candidate = candidates.get(record_id)
        if candidate is None:
            continue
        payload = {
            "entities": [
                {"label": item["label"], "evidence": item["evidence"]}
                for item in row["entities"]
            ]
        }
        validated = validate_entities(payload, text=candidate["text"])
        removed += len(row["entities"]) - len(validated)
        row["entities"] = validated
        row["review_status"] = (
            "auto_high_confidence" if validated else "no_explicit_target"
        )
    _write_jsonl(path, (rows[record_id] for record_id in sorted(rows)))
    return {"records": len(rows), "removed": removed}


def _grounded_analysis(
    analysis: dict[str, Any] | None,
    *,
    candidate: dict[str, Any],
    label_row: dict[str, Any],
) -> dict[str, Any]:
    """Replace target entities with the strictly validated grounded set."""

    result = deepcopy(analysis) if isinstance(analysis, dict) else {}
    result.update(
        contract=RUNTIME_CONTRACT,
        record={
            "id": candidate["id"],
            "source_content_hash": candidate["content_hash"],
            "source_version": candidate["source_version"],
            "text_sha256": candidate["text_sha256"],
        },
    )
    entities = [
        item
        for item in result.get("entities", [])
        if isinstance(item, dict) and item.get("label") != "HEDEF_KITLE"
    ]
    grounded = label_row["entities"]
    for item in grounded:
        evidence = item["evidence"]
        entities.append(
            {
                "label": "HEDEF_KITLE",
                "segment": item["label"],
                "context_kind": item["context_kind"],
                "text": evidence["text"],
                "start": evidence["char_start"],
                "end": evidence["char_end"],
            }
        )
    result["entities"] = sorted(
        entities,
        key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0))),
    )
    suggestions = result.get("suggestions")
    suggestions = deepcopy(suggestions) if isinstance(suggestions, dict) else {}
    suggestions.pop("target_audience", None)
    if grounded and field_is_missing(candidate["structured"], "target_audience"):
        by_label: dict[str, dict[str, Any]] = {}
        for item in grounded:
            by_label.setdefault(item["label"], item)
        selected = next(
            (by_label[label] for label in SEGMENT_PRIORITY if label in by_label),
            grounded[0],
        )
        suggestions["target_audience"] = {
            "value": selected["label"],
            "evidence": selected["evidence"],
            "method": "grounded_target_audience",
            "advisory": True,
        }
    result["suggestions"] = suggestions
    quality = result.get("quality")
    quality = deepcopy(quality) if isinstance(quality, dict) else {}
    quality["entity_count"] = len(result["entities"])
    quality["suggestion_count"] = len(suggestions)
    quality["grounded_target_entity_count"] = len(grounded)
    result["quality"] = quality
    provenance = result.get("provenance")
    provenance = deepcopy(provenance) if isinstance(provenance, dict) else {}
    provenance["target_audience"] = {
        "method": "grounded_llm_with_deterministic_pruning",
        "review_status": label_row["review_status"],
    }
    result["provenance"] = provenance
    return result


def apply_labels_to_database(
    database: str | Path, labels_path: str | Path
) -> dict[str, Any]:
    store = CampaignStore(database)
    candidates = {row["id"]: row for row in store.nlp_enrichment_candidates()}
    labels = _read_completed(Path(labels_path))
    missing = sorted(set(candidates) - set(labels))
    stale = sorted(
        record_id
        for record_id, candidate in candidates.items()
        if labels.get(record_id, {}).get("content_hash") != candidate["content_hash"]
    )
    if missing or stale:
        raise TargetAudienceLabelError(
            "Hedef kitle etiketi eksik veya güncel değil; önce label ve prune çalıştırılmalı"
        )
    analyses = []
    labeled = entity_count = suggested = 0
    for record_id in sorted(candidates):
        candidate = candidates[record_id]
        label_row = labels[record_id]
        record = store.get_campaign(record_id) or {}
        analysis = _grounded_analysis(
            record.get("nlp_analysis"),
            candidate=candidate,
            label_row=label_row,
        )
        analyses.append(analysis)
        labeled += bool(label_row["entities"])
        entity_count += len(label_row["entities"])
        suggested += "target_audience" in analysis["suggestions"]
    changed = store.apply_nlp_analyses(analyses)
    return {
        "campaigns": len(candidates),
        "changed": changed,
        "labeled_campaigns": labeled,
        "grounded_entities": entity_count,
        "target_suggestions": suggested,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    label = commands.add_parser("label")
    label.add_argument("--database", default="data/ragnroll.sqlite3")
    label.add_argument(
        "--output", default="data/model_training_data/target_audience_llm_large.jsonl"
    )
    label.add_argument("--max-records", type=int)
    merge = commands.add_parser("merge-training")
    merge.add_argument("--database", default="data/ragnroll.sqlite3")
    merge.add_argument(
        "--labels", default="data/model_training_data/target_audience_llm_large.jsonl"
    )
    merge.add_argument(
        "--classifier", default="data/model_training_data/classifier_dataset_final.jsonl"
    )
    merge.add_argument("--ner", default="data/model_training_data/ner_dataset_final.jsonl")
    prune = commands.add_parser("prune")
    prune.add_argument("--database", default="data/ragnroll.sqlite3")
    prune.add_argument(
        "--labels", default="data/model_training_data/target_audience_llm_large.jsonl"
    )
    apply_database = commands.add_parser("apply-database")
    apply_database.add_argument("--database", default="data/ragnroll.sqlite3")
    apply_database.add_argument(
        "--labels", default="data/model_training_data/target_audience_llm_large.jsonl"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "label":
            report = label_database(
                args.database,
                args.output,
                max_records=args.max_records,
            )
        elif args.command == "merge-training":
            report = merge_training_datasets(
                args.database,
                args.labels,
                args.classifier,
                args.ner,
            )
        elif args.command == "prune":
            report = prune_label_file(args.database, args.labels)
        else:
            report = apply_labels_to_database(args.database, args.labels)
    except (OSError, ValueError, TargetAudienceLabelError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "completed", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
