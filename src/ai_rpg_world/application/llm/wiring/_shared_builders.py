"""LLM wiring と escape episodic stack の共有ビルダー群。

Issue #227 後続: wiring factory 間で完全重複していたブロックを抽出した:

1. effective_view_distance の argument 解決
2. memory_link_bundle と意味記憶の store の構築
3. game_time_label_provider クロージャ生成 (action_result の時刻ラベル用)

呼び出し側のロジックを薄くし、episodic/link/semantic 構築の挙動が drift しないことを保証する。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    EpisodicMemoryLinkBundle,
    build_episodic_memory_link_bundle,
    default_link_and_semantic_stores_for_episode_store,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)

_DEFAULT_LLM_VIEW_DISTANCE = 5


def resolve_effective_view_distance(llm_view_distance: int | None) -> int:
    """tile-map view distance の解決。

    引数 → default の順で解決し、未指定なら固定既定値を返す。
    """
    if llm_view_distance is not None:
        return llm_view_distance
    return _DEFAULT_LLM_VIEW_DISTANCE


@dataclass(frozen=True)
class EpisodicMemoryStack:
    """episodic memory の中核コンポーネント束。

    shared_episode_store: 全 coordinator が共有する episode store
    semantic_memory_store: 意味記憶の store (snapshot 用に公開)
    mem_bundle: link service / passive recall などのバンドル
    """

    shared_episode_store: EpisodicEpisodeRepository
    semantic_memory_store: Any
    mem_bundle: EpisodicMemoryLinkBundle


def build_episodic_memory_stack(
    episodic_episode_store: EpisodicEpisodeRepository | None,
    *,
    subjective_episode_db_path: str | None = None,
) -> EpisodicMemoryStack:
    """共有 episode store と link / semantic の store を組み立てる。

    クラスタ昇格と gist は #1631 で消した。
    """
    shared_episode_store = resolve_default_episodic_episode_store(
        episodic_episode_store, db_path=subjective_episode_db_path
    )
    link_store, semantic_memory_store = default_link_and_semantic_stores_for_episode_store(
        shared_episode_store
    )
    mem_bundle = build_episodic_memory_link_bundle(
        shared_episode_store,
        link_store=link_store,
    )
    return EpisodicMemoryStack(
        shared_episode_store=shared_episode_store,
        semantic_memory_store=semantic_memory_store,
        mem_bundle=mem_bundle,
    )


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
