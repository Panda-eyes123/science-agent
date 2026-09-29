"""Compact evidence shared by model responses and source cards."""

from science_agent.rag.types import (
    EvidenceItem,
    EvidencePack,
    EvidenceSource,
    EvidenceView,
)


def evidence_view(evidence: EvidencePack, *, max_chars: int = 8000) -> EvidenceView:
    items = []
    budget = max_chars
    for hit in evidence.hits:
        if budget <= 0:
            break
        parent = evidence.parents.get(hit.parent_chunk_id or "")
        context = parent.text if parent else hit.text
        # 摘录总量受限，结构化卡片和模型看到同一批命中，不展示模型未获得的额外来源。
        excerpt = context[: min(2000, budget)]
        budget -= len(excerpt)
        ids = (
            parent.source_element_ids
            if parent
            else hit.metadata.get("source_element_ids", [])
        )
        sources = []
        for element_id in dict.fromkeys(ids):
            element = evidence.source_elements.get(element_id)
            if element is not None:
                sources.append(
                    EvidenceSource(
                        element_id=element.element_id,
                        page_no=element.page_no,
                        element_type=element.element_type,
                        text=(element.table_markdown or element.text)[:1200],
                    )
                )
        paper = evidence.papers.get(hit.paper_id or "")
        items.append(
            EvidenceItem(
                chunk_id=hit.chunk_id,
                paper_id=hit.paper_id,
                title=paper.title if paper else None,
                section_kind=hit.section_kind,
                score=hit.score,
                excerpt=excerpt,
                sources=sources,
            )
        )
    return EvidenceView(query=evidence.query, route=evidence.route, items=items)


def render_evidence(evidence: EvidencePack, *, max_chars: int = 8000) -> str:
    return render_evidence_view(evidence_view(evidence, max_chars=max_chars))


def render_evidence_view(view: EvidenceView) -> str:
    blocks = []
    for item in view.items:
        pages = sorted(
            {source.page_no for source in item.sources if source.page_no is not None}
        )
        location = ",".join(str(page) for page in pages) or "unknown"
        header = f"[{item.paper_id or 'unknown'} | {item.title or ''} | {item.section_kind or 'other'} | pages={location}]"
        blocks.append(f"{header}\n{item.excerpt}")
    return "\n---\n".join(blocks)
