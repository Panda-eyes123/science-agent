"""Rule-based section and query routing for scientific papers."""

import re

from science_agent.rag.types import SectionKind

_SECTION_RULES: list[tuple[SectionKind, tuple[str, ...]]] = [
    (
        "background",
        (
            "abstract",
            "introduction",
            "background",
            "related work",
            "literature review",
            "motivation",
        ),
    ),
    (
        "method",
        ("method", "methods", "methodology", "model", "approach", "algorithm", "material"),
    ),
    (
        "experiment",
        ("experiment", "experimental", "setup", "implementation", "dataset", "protocol"),
    ),
    (
        "result",
        ("result", "results", "evaluation", "analysis", "ablation", "benchmark", "performance"),
    ),
    (
        "discussion",
        ("discussion", "conclusion", "conclusions", "limitation", "future work", "outlook"),
    ),
]

_QUERY_HINTS: dict[SectionKind, tuple[str, ...]] = {
    "background": ("why", "background", "motivation", "related", "prior work", "什么背景", "为什么", "相关工作"),
    "method": ("how", "method", "approach", "algorithm", "model", "formula", "方法", "模型", "算法", "怎么做"),
    "experiment": ("experiment", "setup", "dataset", "training", "hyperparameter", "实验", "数据集", "训练", "参数", "设置"),
    "result": ("result", "performance", "metric", "ablation", "compare", "结果", "性能", "指标", "消融", "对比"),
    "discussion": ("limitation", "conclusion", "future", "discussion", "局限", "结论", "未来"),
}


def classify_section(heading: str | None) -> SectionKind:
    """Classify a paper heading without relying on a model at ingest time."""
    normalized = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", (heading or "").lower()).strip()
    for section_kind, keywords in _SECTION_RULES:
        if any(keyword in normalized for keyword in keywords):
            return section_kind
    return "other"


def route_query(query: str) -> SectionKind | None:
    """Return a section preference when the query has a clear scientific intent."""
    normalized = query.lower()
    scores = {
        section_kind: sum(hint in normalized for hint in hints)
        for section_kind, hints in _QUERY_HINTS.items()
    }
    best_kind, best_score = max(scores.items(), key=lambda item: item[1])
    return best_kind if best_score else None
