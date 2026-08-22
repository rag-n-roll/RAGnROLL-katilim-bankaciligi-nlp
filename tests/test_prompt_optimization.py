import json

from src.chatbot.prompt_config import DEFAULT_SYSTEM_PROMPT, load_prompt_config, render_prompt
from src.prompt_optimization.dataset import build_examples
from src.prompt_optimization.metrics import score_answer


def test_same_campaign_tasks_never_cross_splits():
    classifier = [{"id": "abc", "text": "Temiz kampanya", "annotations": {"product_category": "card"}}]
    ner = [{"id": "abc", "text": "Temiz kampanya", "entities": [{"label": "BANKA", "text": "Örnek Bank"}]}]
    examples = build_examples(classifier, ner)
    assert len(examples) == 2
    assert len({item["split"] for item in examples}) == 1


def test_dataset_uses_union_of_classifier_and_ner_records():
    classifier = [{"id": "only-cls", "text": "A", "annotations": {"product_category": "card"}}]
    ner = [{"id": "only-ner", "text": "B", "entities": [{"label": "BANKA", "text": "B Bank"}]}]
    examples = build_examples(classifier, ner)
    assert {item["campaign_id"] for item in examples} == {"only-cls", "only-ner"}


def test_metric_penalizes_invented_amount():
    good, _ = score_answer(answer="Ödül 500 TL.", gold_answer="Ödül 500 TL.", required_facts=["500 TL"], evidence="500 TL")
    bad, feedback = score_answer(answer="Ödül 900 TL.", gold_answer="Ödül 500 TL.", required_facts=["500 TL"], evidence="500 TL")
    assert good > bad
    assert "900" in feedback


def test_prompt_config_fallback_and_few_shot_rendering(tmp_path):
    assert load_prompt_config(tmp_path / "missing.json")["system_prompt"] == DEFAULT_SYSTEM_PROMPT
    config_path = tmp_path / "prompt.json"
    config_path.write_text(
        json.dumps(
            {
                "system_prompt": "Kanıta dayan.",
                "demonstrations": [{"campaign_text": "Metin", "question": "Soru?", "answer": "Cevap."}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    prompt = render_prompt(question="Yeni soru?", context="Yeni bağlam", config=load_prompt_config(config_path))
    assert "Kanıta dayan." in prompt
    assert "Örnek cevap: Cevap." in prompt
    assert "Yeni bağlam" in prompt
