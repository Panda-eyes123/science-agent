"""Deterministic policy for Wiki-guided versus raw-first retrieval."""

from science_agent.knowledge.types import KnowledgeQueryPlan

_RAW_FIRST_HINTS = (
    "多少",
    "数值",
    "数据",
    "来源",
    "引用",
    "原文",
    "最新",
    "目前",
    "哪篇",
    "图",
    "表",
    "score",
    "metric",
    "source",
    "citation",
    "latest",
    "figure",
    "table",
    "when",
    "date",
)
_WIKI_GUIDED_HINTS = (
    "概览",
    "总结",
    "关系",
    "区别",
    "比较",
    "主题",
    "共识",
    "演化",
    "overview",
    "relationship",
    "compare",
    "difference",
    "synthesize",
    "consensus",
)


class KnowledgeQueryPolicy:
    def plan(self, query: str) -> KnowledgeQueryPlan:
        normalized = query.casefold()
        raw_score = sum(hint in normalized for hint in _RAW_FIRST_HINTS)
        wiki_score = sum(hint in normalized for hint in _WIKI_GUIDED_HINTS)
        if raw_score > wiki_score:
            return KnowledgeQueryPlan(
                mode="raw_first",
                reasons=["query contains factual, source, temporal, or visual signals"],
                expand_links=False,
            )
        reasons = ["personal knowledge synthesis is the default route"]
        if wiki_score:
            reasons = ["query contains overview or relationship signals"]
        return KnowledgeQueryPlan(mode="wiki_guided", reasons=reasons)
