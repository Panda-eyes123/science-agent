"""Human- and LLM-facing rendering for retrieval evidence."""

from science_agent.rag.types import EvidencePack


def render_evidence(evidence: EvidencePack, *, max_chars: int = 8000) -> str:
    """Format an EvidencePack as a compact, budget-aware text block.

    Prefer the parent chunk text (larger context window) when it exists,
    otherwise fall back to the reranked hit's own text. Stop appending
    once the remaining budget cannot fit the next block whole.
    """
    parts: list[str] = []
    budget = max_chars
    for hit in evidence.hits:
        parent = evidence.parents.get(hit.parent_chunk_id or "")
        context = parent.text if parent else hit.text
        source_ids = parent.source_element_ids if parent else []
        page_range = (
            f"{parent.page_start}-{parent.page_end}"
            if parent and parent.page_start is not None and parent.page_end is not None
            else "unknown"
        )
        header = (
            f"[{hit.paper_id or 'unknown'} | "
            f"{hit.section_kind or 'other'} | "
            f"pages={page_range} | "
            f"elements={','.join(source_ids) or 'unknown'} | "
            f"score={hit.score:.3f}]"
        )
        block = f"{header}\n{context}\n"
        if len(block) > budget:
            break
        parts.append(block)
        budget -= len(block)
    return "\n---\n".join(parts)
