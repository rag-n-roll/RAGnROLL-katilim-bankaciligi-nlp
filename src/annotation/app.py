"""Streamlit UI for two-person campaign annotation and review."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.annotation.store import (
    CAMPAIGN_LABELS,
    SPLITS,
    ConcurrentUpdateError,
    approve_annotation,
    dataset_progress,
    load_records,
    reject_annotation,
    save_records,
    submit_annotation,
)


DEFAULT_DATASET = Path("data/annotations/campaign_type_review.jsonl")


def _query_dataset() -> Path:
    import streamlit as st

    value = st.query_params.get("dataset", str(DEFAULT_DATASET))
    return Path(value)


def _save(path: Path, records: list[dict[str, Any]], digest: str) -> str:
    import streamlit as st

    try:
        return save_records(path, records, expected_digest=digest)
    except ConcurrentUpdateError as exc:
        st.error(str(exc))
        st.stop()
    raise AssertionError("unreachable")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="RAGnROLL Etiketleme", layout="wide")
    st.title("RAGnROLL Kampanya Etiketleme")
    dataset = _query_dataset()
    try:
        records, digest = load_records(dataset)
    except (OSError, ValueError) as exc:
        st.error(f"Veri seti açılamadı: {exc}")
        st.stop()

    progress = dataset_progress(records)
    first, second, third = st.columns(3)
    first.metric("Toplam", progress["total"])
    second.metric("Onaylanan", progress["verified"])
    third.metric("Tamamlanma", f"%{progress['verified_percent'] * 100:.1f}")

    with st.sidebar:
        st.header("Oturum")
        user = st.text_input("Ad soyad", key="annotation_user").strip()
        role = st.radio("Rol", ("Etiketleyici", "Reviewer"))
        status_options = ("all", "pending", "awaiting_review", "changes_requested", "approved")
        status_filter = st.selectbox("Durum", status_options)
        label_filter = st.selectbox("Etiket", ("all",) + CAMPAIGN_LABELS)
        st.caption(f"Dosya: {dataset}")

    def visible(record: dict[str, Any]) -> bool:
        status = record.get("review_status", "pending")
        return (status_filter == "all" or status == status_filter) and (
            label_filter == "all" or record.get("label") == label_filter
        )

    filtered = [record for record in records if visible(record)]
    if not filtered:
        st.info("Bu filtrelerde kayıt bulunamadı.")
        return
    index = st.number_input("Kayıt", min_value=1, max_value=len(filtered), value=1) - 1
    record = filtered[index]
    st.subheader(record.get("id", "Kayıt"))
    st.caption(
        f"Banka: {record.get('bank_slug') or '-'} | "
        f"Durum: {record.get('review_status', 'pending')} | "
        f"Kaynak: {record.get('source_url') or '-'}"
    )
    st.text_area("Kampanya metni", record.get("text", ""), height=320, disabled=True)
    current_label = record.get("label", "needs_review")
    current_split = record.get("split") or "train"
    label = st.selectbox(
        "Kampanya türü", CAMPAIGN_LABELS, index=CAMPAIGN_LABELS.index(current_label)
    )
    split = st.selectbox("Veri bölümü", SPLITS, index=SPLITS.index(current_split))
    evidence = record.get("weak_label_evidence") or []
    if evidence:
        st.caption("Ön etiket kanıtı: " + ", ".join(evidence))

    if role == "Etiketleyici":
        if st.button("Etiketi kaydet", type="primary", disabled=not user):
            submit_annotation(
                records, record["id"], annotator=user, label=label, split=split
            )
            _save(dataset, records, digest)
            st.success("Etiket kaydedildi ve reviewer kuyruğuna gönderildi.")
            st.rerun()
    else:
        note = st.text_input("Değişiklik notu")
        approve, reject = st.columns(2)
        if approve.button("Onayla", type="primary", disabled=not user):
            approve_annotation(records, record["id"], reviewer=user)
            _save(dataset, records, digest)
            st.success("Kayıt insan doğrulamalı olarak onaylandı.")
            st.rerun()
        if reject.button("Değişiklik iste", disabled=not user or not note.strip()):
            reject_annotation(records, record["id"], reviewer=user, note=note)
            _save(dataset, records, digest)
            st.warning("Kayıt düzeltme için etiketleyiciye gönderildi.")
            st.rerun()

    with st.expander("İlerleme ayrıntıları"):
        st.json(progress)
    with st.expander("Annotation geçmişi"):
        st.json(record.get("annotation_history", []))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    main()
