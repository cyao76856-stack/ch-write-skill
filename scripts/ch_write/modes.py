"""Request-mode routing for CH-Write.

The skill routes each natural-language request into one main mode:
``generate``, ``assist``, ``decompose``, or ``ambiguous``.  This module is
intentionally small and keyword-based: the actual conversation flow and
Socratic questioning remain in ``SKILL.md`` and its references.
"""

_GENERATE_MARKERS = (
    "生成剧本",
    "创作剧本",
    "写剧本",
    "编写剧本",
    "生成",
    "创作",
)
_ASSIST_MARKERS = (
    "辅写",
    "修改剧本",
    "优化剧本",
    "加一场",
    "加一段",
    "续写",
    "扩写",
    "改写",
    "重写",
    "缩写",
    "改进",
    "修改",
    "润色",
    "优化",
)
_DECOMPOSE_MARKERS = (
    "拆解",
    "分解",
    "人物图谱",
    "人物关系图",
    "时间线",
    "地图",
    "提取人物",
    "分析剧本",
    "叙事分析",
)


def classify_request(text: str) -> str:
    """Return the main mode for ``text``.

    Explicit assist markers take precedence over the generic generation
    marker ``写剧本`` so phrasings like ``改写剧本`` are routed to ``assist``.
    Generic requests with no mode signal return ``"ambiguous"``.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    normalized = text.strip()
    if not normalized:
        return "ambiguous"

    if any(marker in normalized for marker in _DECOMPOSE_MARKERS):
        return "decompose"
    if any(marker in normalized for marker in _ASSIST_MARKERS):
        return "assist"
    if any(marker in normalized for marker in _GENERATE_MARKERS):
        return "generate"
    return "ambiguous"