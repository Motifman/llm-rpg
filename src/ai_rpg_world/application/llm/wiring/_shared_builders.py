"""LLM wiring と escape episodic stack の共有ビルダー群。

Issue #227 後続: wiring factory 間で完全重複していたブロックを抽出した:

1. effective_view_distance の argument 解決
2. game_time_label_provider クロージャ生成 (action_result の時刻ラベル用)

呼び出し側のロジックを薄くし、構築の挙動が drift しないことを保証する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_DEFAULT_LLM_VIEW_DISTANCE = 5


def resolve_effective_view_distance(llm_view_distance: int | None) -> int:
    """tile-map view distance の解決。

    引数 → default の順で解決し、未指定なら固定既定値を返す。
    """
    if llm_view_distance is not None:
        return llm_view_distance
    return _DEFAULT_LLM_VIEW_DISTANCE


def build_game_time_label_provider(
    game_time_provider: Any,
    world_time_config_service: Any,
) -> Callable[[], str | None] | None:
    """action_result の時刻ラベル用 provider を組み立てる。

    Issue #188 改善: action_result に観測と同じ時刻ラベルを乗せる。
    game_time_provider と world_time_config_service が両方注入されていれば、
    tick を game_date_time に変換して display 用ラベルを返す。

    どちらかが None なら None を返す (= ラベルなしで orchestrator に渡される)。

    NOTE: Issue #227 後続のレビュー (MEDIUM-6) で、tile-map 版 create_llm_agent_wiring
    から本 provider が抜けていた潜在バグを発見したため、共通 helper にして両 factory で
    一貫して使うようにした。
    """
    if game_time_provider is None or world_time_config_service is None:
        return None

    from ai_rpg_world.domain.world.value_object.game_date_time import (
        game_date_time_from_tick,
    )

    def _build_game_time_label() -> str | None:
        try:
            tick = game_time_provider.get_current_tick().value
            game_dt = game_date_time_from_tick(
                tick,
                world_time_config_service.get_ticks_per_day(),
                world_time_config_service.get_days_per_month(),
                world_time_config_service.get_months_per_year(),
            )
            return game_dt.format_for_display()
        except Exception:
            return None

    return _build_game_time_label
