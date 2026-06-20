"""world_runtime runtime に最小限の episodic memory pipeline を組み込む補助。

# 移行履歴 (PR #330)

本モジュールの中身は ``application/llm/wiring/episodic_stack.py`` に持ち
上げられ、シナリオ非依存の builder になった (survival_island_v2 等から
も同じ paradigm で使えるように)。

本ファイルは:

- ``WorldEpisodicStack`` / ``build_world_episodic_stack`` の **後方互換 alias**
  (既存テスト / 外部依存を壊さないため)
- 新規コードは ``EpisodicStack`` / ``build_episodic_stack`` を直接使うこと

詳細な設計は ``docs/episodic_memory_overview.md`` 参照。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.wiring.episodic_stack import (
    EpisodicStack,
    build_episodic_stack,
    build_scenario_noun_matcher,
    is_episodic_enabled,
    is_episodic_subjective_enabled,
)

# 後方互換: 旧名 (WorldEpisodicStack / build_world_episodic_stack) を alias。
# 新規コードは EpisodicStack / build_episodic_stack を直接 import すること。
WorldEpisodicStack = EpisodicStack
build_world_episodic_stack = build_episodic_stack


__all__ = [
    # 推奨 (シナリオ非依存)
    "EpisodicStack",
    "build_episodic_stack",
    "build_scenario_noun_matcher",
    "is_episodic_enabled",
    "is_episodic_subjective_enabled",
    # 後方互換 alias (旧コード / テスト用)
    "WorldEpisodicStack",
    "build_world_episodic_stack",
]
