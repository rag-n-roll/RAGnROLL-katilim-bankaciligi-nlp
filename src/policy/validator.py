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
        if decision.intent == "product_comparison":
            missing = tuple(decision.criteria.missing())
            if missing:
                return replace(
                    decision,
                    action=Action.CLARIFY,
                    missing_criteria=missing,
                    tool_calls=(),
                    reason_code="missing_comparison_criteria",
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
        if decision.action != Action.ANSWER:
            return replace(decision, tool_calls=())
        return decision
