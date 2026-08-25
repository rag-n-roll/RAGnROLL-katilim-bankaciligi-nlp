from dataclasses import replace

from src.policy.contracts import Action, PolicyDecision


ALLOWED_TOOLS = {"structured_sql", "hybrid_rag", "comparison", "ontology"}


class PolicyValidator:
    def validate(self, decision: PolicyDecision) -> PolicyDecision:
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
        if any(call.get("name") not in ALLOWED_TOOLS for call in decision.tool_calls):
            return replace(
                decision,
                action=Action.REFUSE,
                tool_calls=(),
                reason_code="invalid_tool_plan",
            )
        return decision
