from src.policy import Action, InputGuard


def test_input_guard_blocks_outbound_transactions_without_model_or_tool():
    decision = InputGuard().inspect("Hesabımdan 5.000 TL havale yap")
    assert decision is not None
    assert decision.action == Action.REDIRECT
    assert decision.reason_code == "transaction_execution"


def test_input_guard_redacts_sensitive_bank_identifiers():
    decision = InputGuard().inspect(
        "TR120006200000000000000001 IBAN hesabımı kontrol et"
    )
    assert decision is not None
    assert decision.action == Action.REDIRECT
    assert "TR120006200000000000000001" not in decision.safe_message


def test_input_guard_leaves_normal_domain_question_for_planner():
    assert InputGuard().inspect("Murabaha nedir?") is None
