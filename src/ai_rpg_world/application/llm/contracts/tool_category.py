"""ツールのカテゴリ（世界作用 vs メタ認知 vs 補助）。"""

from __future__ import annotations

from enum import Enum


class ToolCategory(str, Enum):
    """オーケストレータが ActionExperienceTrace 等を切り替えるための分類。"""

    WORLD_ACTION = "world_action"
    META_COGNITIVE = "meta_cognitive"
    AUXILIARY = "auxiliary"
