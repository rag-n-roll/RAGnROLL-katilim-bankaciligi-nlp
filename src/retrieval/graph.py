"""Ontoloji ilişkilerini yalnız ilişkisel sorgularda kullanan hafif graph katmanı."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Iterable

from src.knowledge import TerminologyService
from src.preprocessing.clean_text import turkish_lower


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELATIONAL_INTENTS = {
    "application_requirements",
    "trade_finance_query",
    "agriculture_finance_query",
    "product_comparison",
    "relationship_query",
}
RELATION_MARKERS = (
    "hangi belge",
    "hangi koşul",
    "hangi şart",
    "gerektir",
    "ilişkili",
    "bağlantılı",
    "kapsar",
    "taraflar",
    "teminat",
)


@dataclass(frozen=True, slots=True)
class GraphExpansion:
    terms: tuple[str, ...] = ()
    term_ids: tuple[str, ...] = ()
    edges: tuple[dict[str, Any], ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.edges)


@lru_cache(maxsize=4)
def _load_graph(
    path_value: str,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, str],
    dict[str, dict[str, str]],
]:
    payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    aliases = json.loads(
        (PROJECT_ROOT / "data" / "ontology" / "alias_dictionary.json").read_text(
            encoding="utf-8"
        )
    )
    attributes = {
        str(item.get("term_id")): {
            "entity": str(item.get("entity") or ""),
            "category": str(item.get("category") or ""),
        }
        for item in aliases.values()
        if isinstance(item, dict) and item.get("term_id")
    }
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for edge in payload.get("edges", []):
        if not isinstance(edge, dict) or float(edge.get("confidence") or 0.0) < 0.8:
            continue
        source_id = str(edge.get("source_id") or "")
        target_id = str(edge.get("target_id") or "")
        if not source_id or not target_id:
            continue
        labels[source_id] = str(edge.get("source_term") or source_id)
        labels[target_id] = str(edge.get("target_term") or target_id)
        adjacency[source_id].append({**edge, "neighbor_id": target_id})
        adjacency[target_id].append({**edge, "neighbor_id": source_id, "reverse": True})
    ordered = {
        node_id: sorted(
            edges,
            key=lambda item: (
                -float(item.get("confidence") or 0.0),
                str(item.get("relation") or ""),
                str(item.get("neighbor_id") or ""),
            ),
        )
        for node_id, edges in adjacency.items()
    }
    return ordered, labels, attributes


class KnowledgeGraphRetriever:
    """Kaynaklı ontoloji kenarlarında sınırlı ve deterministik komşuluk arar."""

    def __init__(
        self,
        terminology: TerminologyService | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self.terminology = terminology or TerminologyService()
        self.path = Path(path or PROJECT_ROOT / "data" / "ontology" / "relation_graph.json")

    @staticmethod
    def should_expand(query: str, intent: str | None) -> bool:
        normalized = turkish_lower(query)
        return bool(
            intent in RELATIONAL_INTENTS
            or any(marker in normalized for marker in RELATION_MARKERS)
        )

    def expand(
        self,
        query: str,
        *,
        intent: str | None = None,
        max_hops: int = 1,
        limit: int = 12,
    ) -> GraphExpansion:
        if not self.should_expand(query, intent):
            return GraphExpansion()
        if not 1 <= max_hops <= 2:
            raise ValueError("max_hops 1 ile 2 arasında olmalıdır")
        if not 1 <= limit <= 50:
            raise ValueError("limit 1 ile 50 arasında olmalıdır")
        seeds = tuple(
            dict.fromkeys(
                str(item.get("term_id"))
                for item in self.terminology.find_terms(query, limit=12)
                if item.get("term_id")
            )
        )
        if not seeds:
            return GraphExpansion()
        adjacency, labels, attributes = _load_graph(str(self.path.resolve()))
        normalized_query = turkish_lower(query)

        def relation_score(edge: dict[str, Any]) -> tuple[int, float, str]:
            neighbor_id = str(edge.get("neighbor_id") or "")
            attribute = attributes.get(neighbor_id, {})
            entity = attribute.get("entity", "").casefold()
            category = turkish_lower(attribute.get("category", ""))
            score = 0
            if "teminat" in normalized_query and (
                entity == "collateral" or "teminat" in category
            ):
                score += 20
            if "belge" in normalized_query and (
                entity == "document" or "belge" in category
            ):
                score += 20
            if "taraf" in normalized_query and "organization" in entity:
                score += 20
            if any(
                marker in normalized_query
                for marker in ("koşul", "şart", "gerektir")
            ) and entity in {"document", "collateral", "down_payment"}:
                score += 8
            if turkish_lower(labels.get(neighbor_id, "")) in normalized_query:
                score += 4
            return (
                score,
                float(edge.get("confidence") or 0.0),
                neighbor_id,
            )

        queue = deque((seed, 0) for seed in seeds)
        seed_set = set(seeds)
        visited = set(seeds)
        related: list[str] = []
        selected_edges: list[dict[str, Any]] = []
        selected_edge_keys: set[tuple[str, str, str]] = set()
        while queue and len(related) < limit:
            node_id, depth = queue.popleft()
            if depth >= max_hops:
                continue
            edges = sorted(
                adjacency.get(node_id, []),
                key=lambda edge: (
                    -relation_score(edge)[0],
                    -relation_score(edge)[1],
                    relation_score(edge)[2],
                ),
            )
            for edge in edges:
                neighbor_id = str(edge["neighbor_id"])
                if neighbor_id in visited:
                    if node_id in seed_set and neighbor_id in seed_set:
                        edge_key = (
                            min(node_id, neighbor_id),
                            str(edge.get("relation") or ""),
                            max(node_id, neighbor_id),
                        )
                        if edge_key not in selected_edge_keys:
                            selected_edge_keys.add(edge_key)
                            selected_edges.append(
                                {
                                    key: value
                                    for key, value in edge.items()
                                    if key not in {"neighbor_id", "reverse"}
                                }
                            )
                    continue
                visited.add(neighbor_id)
                related.append(neighbor_id)
                selected_edge_keys.add(
                    (
                        min(node_id, neighbor_id),
                        str(edge.get("relation") or ""),
                        max(node_id, neighbor_id),
                    )
                )
                selected_edges.append(
                    {
                        key: value
                        for key, value in edge.items()
                        if key not in {"neighbor_id", "reverse"}
                    }
                )
                queue.append((neighbor_id, depth + 1))
                if len(related) >= limit:
                    break
        ranked_term_ids = (*seeds, *related) if len(seeds) > 1 else tuple(related)
        return GraphExpansion(
            terms=tuple(labels[node_id] for node_id in related if labels.get(node_id)),
            term_ids=tuple(ranked_term_ids),
            edges=tuple(selected_edges),
        )

    @staticmethod
    def rank_documents(
        documents: Iterable[dict[str, Any]], expansion: GraphExpansion
    ) -> list[dict[str, Any]]:
        positions = {term_id: index for index, term_id in enumerate(expansion.term_ids)}
        relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in expansion.edges:
            for term_id in (str(edge.get("source_id") or ""), str(edge.get("target_id") or "")):
                if term_id:
                    relations[term_id].append(edge)
        return sorted(
            (
                {
                    **document,
                    "metadata": {
                        **document.get("metadata", {}),
                        "graph_relations": relations.get(
                            str(document.get("metadata", {}).get("term_id") or ""),
                            [],
                        ),
                    },
                }
                for document in documents
                if str(document.get("metadata", {}).get("term_id") or "") in positions
            ),
            key=lambda item: positions[str(item["metadata"]["term_id"])],
        )
