"""LLM wiring と escape episodic stack の共有ビルダー群。

Issue #227 後続: wiring factory 間で完全重複していた 4 ブロックを抽出した:

1. effective_view_distance の argument 解決
2. EpisodicPromotionFrontier + memory_link_bundle + semantic_promotion の構築
3. recall_buffer / reinterpretation_coord / episodic_coord の構築
4. game_time_label_provider クロージャ生成 (action_result の時刻ラベル用)

呼び出し側のロジックを薄くし、episodic/link/semantic 構築の挙動が drift しないことを保証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import WorldId

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    EpisodicMemoryLinkBundle,
    build_episodic_memory_link_bundle,
    default_link_and_semantic_stores_for_episode_store,
)


_DEFAULT_LLM_VIEW_DISTANCE = 5


def resolve_effective_view_distance(llm_view_distance: Optional[int]) -> int:
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
    semantic_memory_store: semantic promotion 先
    promotion_frontier: promotion 状態
    mem_bundle: link service / passive recall などのバンドル
    episodic_semantic_promotion: semantic cluster promotion service
    """

    shared_episode_store: EpisodicEpisodeRepository
    semantic_memory_store: Any
    promotion_frontier: EpisodicPromotionFrontier
    mem_bundle: EpisodicMemoryLinkBundle
    episodic_semantic_promotion: EpisodicSemanticClusterPromotionService


def build_episodic_memory_stack(
    episodic_episode_store: Optional[EpisodicEpisodeRepository],
    *,
    semantic_gist_service: Optional[Any] = None,
    semantic_persona_resolver: Optional[Any] = None,
    being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
    default_world_id: Optional["WorldId"] = None,
    belief_evidence_buffer_store: Optional[Any] = None,
    episodic_promotion_force_full_scan: bool = False,
    episodic_promotion_expansion_hops: int = 4,
) -> EpisodicMemoryStack:
    """共有 episode store と link / semantic / promotion を組み立てる。

    wiring factory 間で完全に同じロジックだった 5 連鎖を 1 か所に集約する。

    Phase 1b (semantic LLM gist):
    - ``semantic_gist_service`` を渡すと cluster 昇格時に LLM gist を試みる
      (失敗時は決定論 gist にフォールバック)。default の None なら従来の
      決定論 gist のみ
    - ``semantic_persona_resolver`` は ``Callable[[int], tuple[str, str]]``。
      LLM gist の prompt に persona を載せるために必要。gist service を
      渡したら基本的に併せて渡す

    U3b (固着パス):
    - ``belief_evidence_buffer_store`` を渡すと ``episodic_semantic_promotion``
      が FAMILIARITY 転用モードになる (store 直書き・recall_count ゲートを
      やめ、evidence buffer に emit する)。呼び出し側 (``episodic_stack.py``)
      が ``BELIEF_CONSOLIDATION_ENABLED`` を見て渡すかどうかを決める
      (「配線と有効化の分離」既存パターン)。
    """
    shared_episode_store = resolve_default_episodic_episode_store(episodic_episode_store)
    link_store, semantic_memory_store = default_link_and_semantic_stores_for_episode_store(
        shared_episode_store
    )
    promotion_frontier = EpisodicPromotionFrontier()
    mem_bundle = build_episodic_memory_link_bundle(
        shared_episode_store,
        link_store=link_store,
        promotion_frontier=promotion_frontier,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    episodic_semantic_promotion = EpisodicSemanticClusterPromotionService(
        episode_store=shared_episode_store,
        link_store=mem_bundle.link_store,
        semantic_store=semantic_memory_store,
        promotion_frontier=promotion_frontier,
        gist_service=semantic_gist_service,
        persona_resolver=semantic_persona_resolver,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
        belief_evidence_buffer_store=belief_evidence_buffer_store,
        force_full_scan=episodic_promotion_force_full_scan,
        expansion_hops=episodic_promotion_expansion_hops,
    )
    return EpisodicMemoryStack(
        shared_episode_store=shared_episode_store,
        semantic_memory_store=semantic_memory_store,
        promotion_frontier=promotion_frontier,
        mem_bundle=mem_bundle,
        episodic_semantic_promotion=episodic_semantic_promotion,
    )


def build_game_time_label_provider(
    game_time_provider: Any,
    world_time_config_service: Any,
) -> Optional[Callable[[], Optional[str]]]:
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

    def _build_game_time_label() -> Optional[str]:
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
