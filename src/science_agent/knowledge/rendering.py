"""Render combined Wiki and raw evidence for an answering model."""

from science_agent.knowledge.types import KnowledgeEvidence
from science_agent.rag.rendering import render_evidence


def render_knowledge_evidence(
    evidence: KnowledgeEvidence, *, max_chars: int = 12_000
) -> str:
    wiki_budget = max_chars // 2
    wiki_parts: list[str] = []
    remaining = wiki_budget
    for hit in evidence.wiki.hits:
        page = evidence.wiki.pages.get(hit.page_id)
        if page is None:
            continue
        claims = "\n".join(
            f"- [{claim.status}] {claim.text}" for claim in page.claims
        )
        block = (
            f"[wiki page={page.page_id} status={page.status} "
            f"revision={page.revision} score={hit.score:.3f}]\n"
            f"{page.body}\n{claims}\n"
        )
        if len(block) > remaining:
            break
        wiki_parts.append(block)
        remaining -= len(block)
    wiki_text = "\n---\n".join(wiki_parts) or "No usable Wiki context."
    raw_text = render_evidence(evidence.raw, max_chars=max_chars - len(wiki_text))
    warnings = "\n".join(f"- {warning}" for warning in evidence.warnings) or "- none"
    citations = "\n".join(
        (
            f"- {item.page_id}#{item.claim_id} -> "
            f"paper={item.reference.paper_id} element={item.reference.element_id} "
            f"verified={str(item.verified_in_raw_results).lower()}"
        )
        for item in evidence.citations
    ) or "- none"
    return (
        f"QUERY ROUTE: {evidence.plan.mode}\n"
        f"ROUTE REASONS: {'; '.join(evidence.plan.reasons)}\n\n"
        f"WIKI CONTEXT (secondary synthesis):\n{wiki_text}\n\n"
        f"RAW EVIDENCE (primary evidence):\n{raw_text}\n\n"
        f"WARNINGS:\n{warnings}\n\n"
        f"CITATIONS:\n{citations}"
    )
