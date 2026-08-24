"""Extract grounded channel, card-name and customer-reference entities with EVREN."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import re
from threading import local
from typing import Any, Iterable

from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM
from src.llm.decisions import _json_object
from src.nlp_runtime.advisory import RUNTIME_CONTRACT, field_is_missing
from src.persistence import CampaignStore
from src.training.dataset_contract import is_synthetic, record_provenance


LABELS = ("APPLICATION_CHANNEL", "CARD_NAME", "CUSTOMER_REFERENCE")
CONTEXT_LABELS = frozenset({"UYGULAMA_KANALI", "KART_ADI", "MUSTERI_HITABI"})
TRAINING_LABEL_MAP = {
    "APPLICATION_CHANNEL": "UYGULAMA_KANALI",
    "CARD_NAME": "KART_ADI",
    "CUSTOMER_REFERENCE": "MUSTERI_HITABI",
}
CHANNEL_RULES = (
    ("video_call", re.compile(r"\b(?:görüntülü|goruntulu)\s+görüşme\b", re.I)),
    ("internet_branch", re.compile(r"\binternet\s+şube(?:si|sinden|sine)?\b", re.I)),
    (
        "mobile",
        re.compile(
            r"\b(?:(?:Albaraka|Kuveyt\s+Türk|Türkiye\s+Finans|Vakıf\s+Katılım|"
            r"Ziraat\s+Katılım|Emlak\s+Katılım|Hayat\s+Finans)\s+Mobil|"
            r"mobil\s+(?:uygulama|şube)\w*)\b",
            re.I,
        ),
    ),
    (
        "call_center",
        re.compile(
            r"\b(?:çağrı\s+merkezi|müşteri\s+(?:iletişim|hizmetleri)\s+merkezi)\b",
            re.I,
        ),
    ),
    ("atm", re.compile(r"\b(?:ATM|bankamatik)\b", re.I)),
    ("card_pos", re.compile(r"\b(?:POS|üye\s+iş\s*yeri)\b", re.I)),
    (
        "ecommerce",
        re.compile(
            r"\b(?:e-ticaret|online|internet|web)\s+"
            r"(?:sitesi|mağaza|alışveriş)\b",
            re.I,
        ),
    ),
    (
        "physical_branch",
        re.compile(
            r"\b(?:fiziksel\s+)?şube(?:si|sinden|sine|lerimizden|lerden)?\b",
            re.I,
        ),
    ),
)
CARD_NAME_PATTERN = re.compile(
    r"\b(?:(?:Dünya\s+Katılım\s+)?Paraf(?:ly|ree|\s+Genç|\s+Premium)?|"
    r"(?:Ziraat\s+Katılım\s+)?Bankkart(?:\s+(?:Aile|Genç|Bağımsız))?|"
    r"Sağlam\s+(?:Kart(?:\s+(?:Kampüs|Genç))?|Nakit(?:\s+Kart)?)|"
    r"Albaraka\s+World|Worldcard|"
    r"Miles&Smiles(?:\s+Kuveyt\s+Türk)?|"
    r"Hadi\s+Black(?:\s+Kredi\s+Kartı)?|World\s+Elite\s+Kart|"
    r"Pratik\s+Finansman\s+Kart|Bağımsız(?:\s+Kredi)?\s+Kart|Biz\s+Kart|"
    r"(?:Happy\s+)?Bonus(?:\s+kredi\s+kartı)?|Âlâ\s+Kart|"
    r"Trend\s+Kredi\s+Kart|Dkart\s+Debit\s+Kart|İhtiyaç\s+Kart|"
    r"Eflatun\s+Kredi\s+Kart|(?:Emlak\s+Katılım\s+)?Debit\s+Kart|"
    r"Master\s+Gold\s+Kart|TROY(?:\s+logolu)?(?:\s+(?:banka|kredi))?\s+Kart|"
    r"(?:Aile|Genç|Tarım|Business|Esnaf|Gold|Platinum)\s+Kart)\b",
    re.I,
)
OPEN_CARD_NAME_PATTERN = re.compile(
    r"\b(?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü&'’.-]+\s+){1,3}"
    r"(?:Kredi\s+)?Kart\b"
)
GENERIC_CARD_MODIFIERS = frozenset(
    {
        "asıl",
        "banka",
        "bireysel",
        "ek",
        "hediye",
        "kredi",
        "sanal",
        "temassız",
        "ticari",
        "ücretsiz",
    }
)
CUSTOMER_PATTERN = re.compile(
    r"\b(?:(?:(?:yeni|mevcut|bireysel|ticari|dijital|maaş|emekli|genç|"
    r"öğrenci|kamu|özel\s+bankacılık|KOBİ|tarım|her|tüm)\s+){1,3})?"
    r"müşteri(?:lerimiz|leriniz|lerine|leri|ler|miz|niz|si|ye|yi)?\b",
    re.I,
)
EXCLUSION_PATTERN = re.compile(
    r"(?:dahil|kapsamında|geçerli)\s+(?:değil|değildir)|"
    r"(?:yararlanamaz|faydalanamaz|hariç|kapsam dışı)",
    re.I,
)
ELIGIBILITY_PATTERN = re.compile(
    r"(?:faydalan|yararlan|özel|geçerli|katıl|kapsam|için)", re.I
)
CHANNEL_ACTION_PATTERN = re.compile(
    r"(?:başvur|katıl|giriş|işlem|ödeme|harcama|alışveriş|satın\s+al|"
    r"kullan|tamamla|gerçekleştir|yap)",
    re.I,
)


class ContextEntityError(RuntimeError):
    """Raised when grounded context extraction cannot be completed safely."""


def _entity_payload(raw: str) -> dict[str, Any] | None:
    payload = _json_object(raw)
    if payload is not None:
        return payload
    cleaned = raw.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    array_start = cleaned.find("[")
    array_end = cleaned.rfind("]")
    if array_start < 0 or array_end <= array_start:
        return None
    try:
        entities = json.loads(cleaned[array_start : array_end + 1])
    except json.JSONDecodeError:
        return None
    return {"entities": entities} if isinstance(entities, list) else None


def _anchor(text: str, evidence: Any) -> tuple[int, int] | None:
    if not isinstance(evidence, dict):
        return None
    value = evidence.get("text")
    start = evidence.get("char_start")
    end = evidence.get("char_end")
    if (
        isinstance(value, str)
        and value
        and isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start < end <= len(text)
        and text[start:end] == value
    ):
        return start, end
    if not isinstance(value, str) or not value:
        return None
    start = text.find(value)
    if start < 0 or text.find(value, start + 1) >= 0:
        return None
    return start, start + len(value)


def _sentence(text: str, start: int, end: int) -> str:
    sentence_start = max(
        text.rfind(".", 0, start),
        text.rfind("!", 0, start),
        text.rfind("?", 0, start),
        text.rfind("\n", 0, start),
    ) + 1
    endings = [
        position
        for marker in (".", "!", "?", "\n")
        if (position := text.find(marker, end)) >= 0
    ]
    sentence_end = min(endings) + 1 if endings else len(text)
    return text[sentence_start:sentence_end]


def _channel(value: str) -> tuple[str, re.Match[str]] | None:
    for normalized, pattern in CHANNEL_RULES:
        match = pattern.search(value)
        if match:
            if normalized == "physical_branch" and re.search(
                r"(?:internet|mobil)\s+şube", value, re.I
            ):
                continue
            return normalized, match
    return None


def _customer_kind(sentence: str) -> str:
    if EXCLUSION_PATTERN.search(sentence):
        return "exclusion"
    if ELIGIBILITY_PATTERN.search(sentence):
        return "eligibility"
    return "generic_address"


def _card_name_match(value: str) -> re.Match[str] | None:
    known = CARD_NAME_PATTERN.search(value)
    open_match = OPEN_CARD_NAME_PATTERN.search(value)
    if open_match is None:
        return known
    words = {
        word.casefold()
        for word in re.findall(r"[\wÇĞİÖŞÜçğıöşü]+", open_match.group(0))
        if word.casefold() not in {"kart", "kredi"}
    }
    if not words or words <= GENERIC_CARD_MODIFIERS:
        return known
    if known is None or len(open_match.group(0)) > len(known.group(0)):
        return open_match
    return known


def validate_entities(payload: dict[str, Any], *, text: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        keys = sorted(payload) if isinstance(payload, dict) else []
        raise ContextEntityError(
            "Bağlam entity üst sözleşmesi geçersiz; anahtarlar=" + ",".join(keys)
        )
    result = []
    seen = set()
    for item in payload["entities"]:
        if not isinstance(item, dict) or not {"label", "evidence"} <= set(item):
            continue
        label = item.get("label")
        if label not in LABELS:
            continue
        anchored = _anchor(text, item.get("evidence"))
        if anchored is None:
            continue
        start, end = anchored
        value = text[start:end]
        sentence = _sentence(text, start, end)
        normalized = None
        kind = None
        if label == "APPLICATION_CHANNEL":
            channel = _channel(value)
            if channel is None:
                continue
            normalized, match = channel
            start += match.start()
            end = start + len(match.group(0))
            value = match.group(0)
            kind = (
                "application_or_transaction_channel"
                if CHANNEL_ACTION_PATTERN.search(sentence)
                else "information_channel"
            )
        elif label == "CARD_NAME":
            match = _card_name_match(value)
            if match is None:
                continue
            normalized = re.sub(r"\s+", " ", match.group(0)).strip()
            start += match.start()
            end = start + len(match.group(0))
            value = match.group(0)
            if normalized.casefold() == "bonus" and not re.search(
                r"\b(?:kredi\s+)?kart(?:ı|lar|ınız)?\b", sentence, re.I
            ):
                continue
            if normalized.casefold().endswith("bankkart") and re.match(
                r"\s+(?:Lira|POS|anlaşmalı|üye|yetkili)\b",
                text[end : end + 25],
                re.I,
            ):
                continue
            kind = "named_card_product"
        else:
            match = CUSTOMER_PATTERN.search(value.strip())
            if match is None:
                continue
            stripped_offset = len(value) - len(value.lstrip())
            start += stripped_offset + match.start()
            end = start + len(match.group(0))
            value = match.group(0)
            normalized = "customer_reference"
            kind = _customer_kind(sentence)
        key = (label, start, end)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "label": label,
                "normalized": normalized,
                "context_kind": kind,
                "evidence": {
                    "text": value,
                    "char_start": start,
                    "char_end": end,
                },
            }
        )
    deduped = []
    occupied: dict[str, set[int]] = {}
    for item in sorted(
        result,
        key=lambda candidate: (
            candidate["label"],
            -(candidate["evidence"]["char_end"] - candidate["evidence"]["char_start"]),
            candidate["evidence"]["char_start"],
        ),
    ):
        evidence = item["evidence"]
        positions = set(range(evidence["char_start"], evidence["char_end"]))
        label_positions = occupied.setdefault(item["label"], set())
        if label_positions & positions:
            continue
        label_positions |= positions
        deduped.append(item)
    return sorted(
        deduped,
        key=lambda item: (
            item["evidence"]["char_start"],
            item["evidence"]["char_end"],
            item["label"],
        ),
    )


def deterministic_candidates(text: str) -> list[dict[str, Any]]:
    """Recover known explicit surfaces when the generative pass omits one."""

    raw = []
    channel_positions: set[int] = set()
    for _normalized, pattern in CHANNEL_RULES:
        for match in pattern.finditer(text):
            positions = set(range(match.start(), match.end()))
            if channel_positions & positions:
                continue
            channel_positions |= positions
            raw.append(
                {
                    "label": "APPLICATION_CHANNEL",
                    "evidence": {
                        "text": match.group(0),
                        "char_start": match.start(),
                        "char_end": match.end(),
                    },
                }
            )
    for label, pattern in (
        ("CARD_NAME", CARD_NAME_PATTERN),
        ("CUSTOMER_REFERENCE", CUSTOMER_PATTERN),
    ):
        for match in pattern.finditer(text):
            raw.append(
                {
                    "label": label,
                    "evidence": {
                        "text": match.group(0),
                        "char_start": match.start(),
                        "char_end": match.end(),
                    },
                }
            )
    return validate_entities({"entities": raw}, text=text)


class ContextEntityLabeler:
    def __init__(self, client: OpenAICompatibleLLM | None = None) -> None:
        settings = LLMSettings.evren_from_env()
        settings = replace(
            settings,
            model=os.getenv("EVREN_CONTEXT_MODEL", "llm-large").strip(),
            max_tokens=int(os.getenv("EVREN_CONTEXT_MAX_TOKENS", "4096")),
            temperature=0.0,
        )
        self.client = client or OpenAICompatibleLLM(settings)

    @staticmethod
    def _chunks(text: str, limit: int = 6000, overlap: int = 300):
        if len(text) <= limit:
            return [(0, text)]
        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + limit)
            if end < len(text):
                boundary = max(
                    text.rfind(". ", start + limit // 2, end),
                    text.rfind("\n", start + limit // 2, end),
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
            "Kampanya metninden üç tür yüzey ifadesi çıkar: APPLICATION_CHANNEL "
            "(mobil uygulama/şube, internet şubesi, görüntülü görüşme, fiziksel şube, "
            "ATM, POS, çağrı merkezi veya açık web/e-ticaret kanalı), CARD_NAME "
            "(Paraf, Bankkart, Sağlam Kart, Albaraka World gibi özel kart ürün adı; "
            "yalnız 'kartınız' veya 'kredi kartı' değildir), CUSTOMER_REFERENCE "
            "(müşteri/müşteriler/müşterilerimiz hitabını sıfatlarıyla birlikte). "
            "Her evidence metinde birebir geçmeli ve offsetler tam olmalı. Çıkarılacak "
            "ifade yoksa boş liste döndür. Yalnız şu JSON'u döndür: "
            '{"entities":[{"label":"CARD_NAME","evidence":{"text":"Paraf",'
            '"char_start":0,"char_end":5}}]}'
        )
        try:
            raw = "".join(
                self.client.stream_chat(system_prompt=system, user_prompt=text)
            ).strip()
        except LLMUnavailableError as exc:
            raise ContextEntityError("EVREN bağlam entity çağrısı başarısız") from exc
        payload = _entity_payload(raw)
        if payload is None:
            raise ContextEntityError("EVREN bağlam entity JSON çıktısı geçersiz")
        if {"label", "evidence"} <= set(payload):
            payload = {"entities": [payload]}
        return validate_entities(payload, text=text)

    def label(self, text: str) -> list[dict[str, Any]]:
        result = []
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
                result.append(
                    {
                        **item,
                        "evidence": {
                            "text": text[start:end],
                            "char_start": start,
                            "char_end": end,
                        },
                    }
                )
        for item in deterministic_candidates(text):
            evidence = item["evidence"]
            key = (item["label"], evidence["char_start"], evidence["char_end"])
            if key not in seen:
                seen.add(key)
                result.append(item)
        return sorted(result, key=lambda item: (item["evidence"]["char_start"], item["label"]))


def _read_completed(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("status") == "completed":
                rows[str(row["record_id"])] = row
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def label_database(
    database: str | Path,
    output: str | Path,
    *,
    max_records: int | None = None,
    labeler: ContextEntityLabeler | None = None,
    workers: int = 4,
) -> dict[str, Any]:
    candidates = CampaignStore(database).nlp_enrichment_candidates()
    path = Path(output)
    completed = _read_completed(path)
    pending_all = [
        row
        for row in candidates
        if completed.get(row["id"], {}).get("content_hash") != row["content_hash"]
    ]
    pending = pending_all[:max_records] if max_records else pending_all
    if workers < 1:
        raise ValueError("workers pozitif olmalıdır")
    worker_state = local()

    def process(candidate: dict[str, Any]) -> dict[str, Any]:
        active_labeler = labeler
        if active_labeler is None:
            active_labeler = getattr(worker_state, "labeler", None)
            if active_labeler is None:
                active_labeler = ContextEntityLabeler()
                worker_state.labeler = active_labeler
        try:
            entities = active_labeler.label(candidate["text"])
            return {
                "status": "completed",
                "record_id": candidate["id"],
                "content_hash": candidate["content_hash"],
                "text_sha256": candidate["text_sha256"],
                "entities": entities,
            }
        except (OSError, ValueError, ContextEntityError) as exc:
            return {
                "status": "failed",
                "record_id": candidate["id"],
                "content_hash": candidate["content_hash"],
                "error": type(exc).__name__,
                "message": str(exc),
            }

    failed = 0
    effective_workers = 1 if labeler is not None else workers
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {executor.submit(process, candidate): candidate for candidate in pending}
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            failed += row["status"] == "failed"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(
                f"[{index}/{len(pending)}] {row['record_id']} {row['status']} "
                f"entities={len(row.get('entities', []))}",
                flush=True,
            )
    current = _read_completed(path)
    valid_ids = {
        row["id"]
        for row in candidates
        if current.get(row["id"], {}).get("content_hash") == row["content_hash"]
    }
    if len(valid_ids) == len(candidates):
        _write_jsonl(path, (current[record_id] for record_id in sorted(valid_ids)))
    return {
        "campaigns": len(candidates),
        "already_completed": len(candidates) - len(pending_all),
        "processed": len(pending),
        "remaining": len(pending_all) - len(pending),
        "failed": failed,
    }


def _date_is_known(structured: dict[str, Any], field: str) -> bool:
    if structured.get(field) not in (None, ""):
        return True
    fields = structured.get("fields")
    contract = fields.get(field) if isinstance(fields, dict) else None
    return isinstance(contract, dict) and contract.get("value") not in (None, "")


def _overlay(
    analysis: dict[str, Any] | None,
    *,
    candidate: dict[str, Any],
    label_row: dict[str, Any],
) -> dict[str, Any]:
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
        if isinstance(item, dict) and item.get("label") not in CONTEXT_LABELS
    ]
    label_map = {
        "APPLICATION_CHANNEL": "UYGULAMA_KANALI",
        "CARD_NAME": "KART_ADI",
        "CUSTOMER_REFERENCE": "MUSTERI_HITABI",
    }
    for item in label_row["entities"]:
        evidence = item["evidence"]
        entities.append(
            {
                "label": label_map[item["label"]],
                "normalized": item["normalized"],
                "context_kind": item["context_kind"],
                "text": evidence["text"],
                "start": evidence["char_start"],
                "end": evidence["char_end"],
                "source": "grounded_context_extraction",
            }
        )
    result["entities"] = sorted(
        entities,
        key=lambda item: (
            int(item.get("start", 0)),
            int(item.get("end", 0)),
            str(item.get("label")),
        ),
    )
    suggestions = result.get("suggestions")
    suggestions = deepcopy(suggestions) if isinstance(suggestions, dict) else {}
    suggestions.pop("application_channel", None)
    channels = [
        item
        for item in label_row["entities"]
        if item["label"] == "APPLICATION_CHANNEL"
        and item["context_kind"] == "application_or_transaction_channel"
    ]
    if channels and field_is_missing(candidate["structured"], "application_channel"):
        selected = channels[0]
        suggestions["application_channel"] = {
            "value": selected["normalized"],
            "evidence": selected["evidence"],
            "method": "grounded_context_extraction",
            "advisory": True,
        }
    result["suggestions"] = suggestions
    observed_at = candidate.get("scraped_at") or ""
    start_known = _date_is_known(candidate["structured"], "campaign_start_date")
    end_known = _date_is_known(candidate["structured"], "campaign_end_date")
    if observed_at and (not start_known or not end_known):
        date = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).date().isoformat()
        result["temporal_observation"] = {
            "observed_at": observed_at,
            "statement": f"Kampanya {date} tarihinde kaynakta mevcuttu.",
            "campaign_start_date_known": start_known,
            "campaign_end_date_known": end_known,
            "method": "scrape_lineage",
            "advisory": True,
        }
    else:
        result.pop("temporal_observation", None)
    quality = result.get("quality")
    quality = deepcopy(quality) if isinstance(quality, dict) else {}
    quality["entity_count"] = len(result["entities"])
    quality["suggestion_count"] = len(suggestions)
    quality["grounded_context_entity_count"] = len(label_row["entities"])
    result["quality"] = quality
    provenance = result.get("provenance")
    provenance = deepcopy(provenance) if isinstance(provenance, dict) else {}
    provenance["context_entities"] = {
        "method": "llm_grounded_with_deterministic_validation",
        "text_sha256": candidate["text_sha256"],
    }
    result["provenance"] = provenance
    return result


def apply_database(database: str | Path, labels_path: str | Path) -> dict[str, Any]:
    store = CampaignStore(database)
    candidates = {row["id"]: row for row in store.nlp_enrichment_candidates()}
    labels = _read_completed(Path(labels_path))
    if any(
        labels.get(record_id, {}).get("content_hash") != candidate["content_hash"]
        for record_id, candidate in candidates.items()
    ):
        raise ContextEntityError("Bağlam etiketi eksik veya güncel değil")
    analyses = []
    counts = {label: 0 for label in LABELS}
    temporal = channel_suggestions = 0
    for record_id in sorted(candidates):
        candidate = candidates[record_id]
        label_row = labels[record_id]
        for item in label_row["entities"]:
            counts[item["label"]] += 1
        record = store.get_campaign(record_id) or {}
        analysis = _overlay(
            record.get("nlp_analysis"), candidate=candidate, label_row=label_row
        )
        temporal += "temporal_observation" in analysis
        channel_suggestions += "application_channel" in analysis["suggestions"]
        analyses.append(analysis)
    changed = store.apply_nlp_analyses(analyses)
    return {
        "campaigns": len(candidates),
        "changed": changed,
        "entity_counts": counts,
        "channel_suggestions": channel_suggestions,
        "temporal_observations": temporal,
    }


def reconcile_label_file(
    database: str | Path, labels_path: str | Path
) -> dict[str, Any]:
    """Revalidate model output and union deterministic high-precision surfaces."""

    candidates = {
        row["id"]: row for row in CampaignStore(database).nlp_enrichment_candidates()
    }
    rows = _read_completed(Path(labels_path))
    if set(candidates) - set(rows):
        raise ContextEntityError("Bağlam etiketi eksik; batch tamamlanmadan uzlaştırılamaz")
    added = removed = 0
    for record_id, candidate in candidates.items():
        row = rows[record_id]
        payload = {
            "entities": [
                {"label": item["label"], "evidence": item["evidence"]}
                for item in row["entities"]
            ]
        }
        validated = validate_entities(payload, text=candidate["text"])
        removed += len(row["entities"]) - len(validated)
        keys = {
            (
                item["label"],
                item["evidence"]["char_start"],
                item["evidence"]["char_end"],
            )
            for item in validated
        }
        for item in deterministic_candidates(candidate["text"]):
            key = (
                item["label"],
                item["evidence"]["char_start"],
                item["evidence"]["char_end"],
            )
            if key not in keys:
                keys.add(key)
                validated.append(item)
                added += 1
        row["entities"] = sorted(
            validated,
            key=lambda item: (item["evidence"]["char_start"], item["label"]),
        )
    _write_jsonl(
        Path(labels_path), (rows[record_id] for record_id in sorted(candidates))
    )
    return {"records": len(candidates), "added": added, "removed": removed}


def merge_training_dataset(
    database: str | Path,
    labels_path: str | Path,
    ner_path: str | Path,
) -> dict[str, Any]:
    """Merge grounded spans into auto-labelled real NER records.

    Existing entities win overlaps because spaCy's NER cannot represent
    overlapping spans. Human and synthetic records are never enriched here.
    """

    import spacy

    tokenizer = spacy.blank("tr")
    candidates = {
        row["id"]: row for row in CampaignStore(database).nlp_enrichment_candidates()
    }
    labels = _read_completed(Path(labels_path))
    missing = sorted(set(candidates) - set(labels))
    stale = sorted(
        record_id
        for record_id, candidate in candidates.items()
        if labels.get(record_id, {}).get("content_hash") != candidate["content_hash"]
    )
    if missing or stale:
        raise ContextEntityError(
            "Bağlam etiketi eksik veya güncel değil; eğitim birleştirmesi durduruldu"
        )

    ner_file = Path(ner_path)
    rows = [
        json.loads(line)
        for line in ner_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    added = {label: 0 for label in TRAINING_LABEL_MAP.values()}
    skipped_overlaps = {label: 0 for label in TRAINING_LABEL_MAP.values()}
    updated = unanchored = token_expanded = 0
    for row in rows:
        record_id = str(row.get("source_id") or row.get("id") or "")
        candidate = candidates.get(record_id)
        label_row = labels.get(record_id)
        if (
            candidate is None
            or label_row is None
            or is_synthetic(row)
            or record_provenance(row) != "auto"
        ):
            continue
        base = row["text"].find(candidate["text"])
        if base < 0:
            unanchored += 1
            continue
        entities = [
            item
            for item in row.get("entities", [])
            if item.get("label") not in CONTEXT_LABELS
        ]
        occupied = {
            position
            for item in entities
            for position in range(int(item["start"]), int(item["end"]))
        }
        doc = tokenizer.make_doc(row["text"])
        pending = []
        for item in label_row["entities"]:
            evidence = item["evidence"]
            start = base + int(evidence["char_start"])
            end = base + int(evidence["char_end"])
            span = doc.char_span(start, end)
            if span is None:
                span = doc.char_span(start, end, alignment_mode="expand")
                if span is None:
                    skipped_overlaps[TRAINING_LABEL_MAP[item["label"]]] += 1
                    continue
                start, end = span.start_char, span.end_char
                token_expanded += 1
            pending.append((start, end, TRAINING_LABEL_MAP[item["label"]], item))
        pending.sort(key=lambda value: (value[0], -(value[1] - value[0])))
        for start, end, training_label, item in pending:
            positions = set(range(start, end))
            if occupied & positions:
                skipped_overlaps[training_label] += 1
                continue
            occupied |= positions
            entities.append(
                {
                    "start": start,
                    "end": end,
                    "text": row["text"][start:end],
                    "label": training_label,
                    "context_kind": item["context_kind"],
                    "normalized": item["normalized"],
                }
            )
            added[training_label] += 1
        row["entities"] = sorted(
            entities, key=lambda item: (int(item["start"]), int(item["end"]))
        )
        row.setdefault("metadata", {})["context_entity_reviewer"] = (
            "evren-grounded-context-entities"
        )
        updated += 1
    _write_jsonl(ner_file, rows)
    return {
        "labels": len(labels),
        "ner_updated": updated,
        "ner_unanchored": unanchored,
        "token_expanded": token_expanded,
        "entities_added": added,
        "entities_skipped_overlaps": skipped_overlaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    label = commands.add_parser("label")
    label.add_argument("--database", default="data/ragnroll.sqlite3")
    label.add_argument("--output", default="data/enrichment/context_entities_llm_large.jsonl")
    label.add_argument("--max-records", type=int)
    label.add_argument("--workers", type=int, default=4)
    apply = commands.add_parser("apply-database")
    apply.add_argument("--database", default="data/ragnroll.sqlite3")
    apply.add_argument("--labels", default="data/enrichment/context_entities_llm_large.jsonl")
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--database", default="data/ragnroll.sqlite3")
    reconcile.add_argument(
        "--labels", default="data/enrichment/context_entities_llm_large.jsonl"
    )
    merge = commands.add_parser("merge-training")
    merge.add_argument("--database", default="data/ragnroll.sqlite3")
    merge.add_argument(
        "--labels", default="data/enrichment/context_entities_llm_large.jsonl"
    )
    merge.add_argument("--ner", default="data/model_training_data/ner_dataset_final.jsonl")
    args = parser.parse_args(argv)
    try:
        if args.command == "label":
            report = label_database(
                args.database,
                args.output,
                max_records=args.max_records,
                workers=args.workers,
            )
        elif args.command == "apply-database":
            report = apply_database(args.database, args.labels)
        elif args.command == "reconcile":
            report = reconcile_label_file(args.database, args.labels)
        else:
            report = merge_training_dataset(args.database, args.labels, args.ner)
    except (OSError, ValueError, ContextEntityError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "completed", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
