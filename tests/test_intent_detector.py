import pytest

from src.intent.intent_detector import IntentDetector


@pytest.fixture()
def detector():
    return IntentDetector()


def test_detects_bank_information_intent(detector):
    assert detector.detect("Türkiye'deki katılım bankaları hangileri?") == "BANKA_BILGISI"
    assert detector.detect("Ziraat Katılım hakkında bilgi ver") == "BANKA_BILGISI"


def test_detects_product_information_intent(detector):
    assert detector.detect("Murabaha nedir?") == "URUN_BILGISI"
    assert detector.detect("Müşaraka ile ev finansmanı olur mu?") == "URUN_BILGISI"


def test_detects_campaign_intent(detector):
    assert detector.detect("Bu ayki kampanyalar neler?") == "KAMPANYA_SORUSU"
    assert detector.detect("Kredi kartında indirim var mı?") == "KAMPANYA_SORUSU"


def test_detects_general_question_intent(detector):
    assert detector.detect("Katılım bankacılığı nasıl denetlenir?") == "GENEL_SORU"
    assert detector.detect("Kâr payı ne demek?") == "GENEL_SORU"


def test_returns_unknown_for_unrelated_text(detector):
    assert detector.detect("Bugün hava çok güzel") == "BILINMEYEN"
    assert detector.detect("") == "BILINMEYEN"


def test_detection_is_case_insensitive(detector):
    assert detector.detect("MURABAHA NEDIR") == "URUN_BILGISI"


def test_first_matching_intent_wins_in_definition_order(detector):
    assert detector.detect("hangi bankalarda kampanya var") == "BANKA_BILGISI"


def test_module_main_prints_detected_intents():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "src.intent.intent_detector"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "URUN_BILGISI" in result.stdout
