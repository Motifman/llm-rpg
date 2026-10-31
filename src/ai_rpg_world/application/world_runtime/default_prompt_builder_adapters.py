"""world_runtime runtime が本家 DefaultPromptBuilder を直接利用するためのアダプタ群。

Issue #227 後続レビュー HIGH-3 Part 2:
    world_runtime の独自 prompt 経路 (build_full_prompt) を廃止し、本家
    DefaultPromptBuilder.build に統合する。本家側の依存契約に world_runtime の
    既存サービスを橋渡しする小さなアダプタクラスを集約する。

各アダプタは「本家の Protocol/ABC を満たす最小限の wrapper」で、world_runtime
固有のロジック (build_llm_context / _build_minimal_player_state_dto /
get_tool_definitions) に委譲する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName

if TYPE_CHECKING:
    from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime


class WorldRuntimeQueryAdapter:
    """get_player_current_state 1 メソッドだけを満たす duck-type adapter。

    DefaultPromptBuilder は world_query_service の 1 メソッドしか呼ばないため、
    タイル用の問い合わせ本体を構築する代わりにこの adapter を渡す
    (Issue #227 HIGH-3 Part 2 で isinstance チェックを hasattr に緩めたため)。

    内部では runtime._build_minimal_player_state_dto を呼び、world_runtime 固有の
    time_label / tick_budget_remaining / spot_graph_snapshot を含む DTO を返す。
    """

    def __init__(self, runtime: WorldRuntime) -> None:
        self._runtime = runtime

    def get_player_current_state(self, query: GetPlayerCurrentStateQuery) -> PlayerCurrentStateDto | None:
        pid = PlayerId(query.player_id)
        snap = self._runtime._state_builder.build_snapshot(int(pid))
        if snap is None:
            return None
        return self._runtime._build_minimal_player_state_dto(pid, snap)


class WorldAvailableToolsProvider(IAvailableToolsProvider):
    """DefaultPromptBuilder への tools 渡し用 adapter。

    build_full_prompt の return shape では "tools" は tool 名の list だが、
    DefaultPromptBuilder は OpenAI tool schema を期待する。本 adapter は
    DefaultPromptBuilder 側を満たすために空 list を返し、shape 変換は
    runtime.build_full_prompt 側で行う (実 LLM 呼び出しは run_world_runtime.py
    で tools を再構築するため、ここでの値は不要)。
    """

    def get_available_tools(self, context: PlayerCurrentStateDto | None) -> list[dict[str, Any]]:
        del context
        return []
