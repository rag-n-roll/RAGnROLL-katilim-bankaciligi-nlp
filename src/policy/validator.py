from dataclasses import replace

from src.policy.contracts import Action, PolicyDecision
from src.policy.tool_policy import valid_tool_call


class PolicyValidator:
    def validate(
        self, decision: PolicyDecision, *, allowed_banks: set[str] | None = None
    ) -> PolicyDecision:
        if not decision.in_domain:
            return replace(
                decision,
                action=Action.REFUSE,
                tool_calls=(),
                reason_code="out_of_domain",
                safe_message=(
                    "Yalnız katılım bankacılığı, finansman, kart, hesap ve "
                    "kampanyalar hakkında yardımcı olabilirim."
                ),
            )
        if any(
            not valid_tool_call(decision.intent, call, allowed_banks=allowed_banks)
            for call in decision.tool_calls
        ):
            return replace(
                decision,
                action=Action.REFUSE,
                tool_calls=(),
                reason_code="invalid_tool_plan",
            )
        # Clarification must never weaken an explicit terminal safety action.
        if decision.action in {Action.REFUSE, Action.REDIRECT}:
            return replace(decision, tool_calls=())
        if decision.intent == "product_comparison":
            is_financing = any(
                call.get("name") == "financing_quote"
                or (
                    call.get("name") == "comparison"
                    and (
                        call.get("arguments", {}).get("product_type") == "financing"
                        or call.get("arguments", {}).get("financing_type") is not None
                    )
                )
                for call in decision.tool_calls
            )
            missing = tuple(decision.criteria.missing())
            if missing and (
                decision.action == Action.CLARIFY
                or is_financing
                or not decision.tool_calls
            ):
                return replace(
                    decision,
                    action=Action.CLARIFY,
                    missing_criteria=missing,
                    tool_calls=(),
                    reason_code="missing_comparison_criteria",
                )
        if decision.action != Action.ANSWER:
            return replace(decision, tool_calls=())
        return decision
