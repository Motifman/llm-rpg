"""escape_game runtime が本家 DefaultPromptBuilder を直接利用するためのアダプタ群。

Issue #227 後続レビュー HIGH-3 Part 2:
    escape_game の独自 prompt 経路 (build_full_prompt) を廃止し、本家
    DefaultPromptBuilder.build に統合する。本家側の依存契約に escape_game の
    既存サービスを橋渡しする小さなアダプタクラスを集約する。

各アダプタは「本家の Protocol/ABC を満たす最小限の wrapper」で、escape_game
固有のロジック (build_llm_context / _build_minimal_player_state_dto /
build_escape_system_prompt / get_tool_definitions) に委譲する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    ISystemPromptBuilder,
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
    from ai_rpg_world.application.escape_game.escape_game_runtime import EscapeGameRuntime


class EscapeGameWorldQueryAdapter:
    """get_player_current_state 1 メソッドだけを満たす duck-type adapter。

    DefaultPromptBuilder は world_query_service の 1 メソッドしか呼ばないため、
    WorldQueryService 本体を構築する代わりにこの adapter を渡す
    (Issue #227 HIGH-3 Part 2 で isinstance チェックを hasattr に緩めたため)。

    内部では runtime._build_minimal_player_state_dto を呼び、escape_game 固有の
    time_label / tick_budget_remaining / spot_graph_snapshot を含む DTO を返す。
    """

    def __init__(self, runtime: "EscapeGameRuntime") -> None:
        self._runtime = runtime

    def get_player_current_state(
        self, query: GetPlayerCurrentStateQuery
    ) -> Optional[PlayerCurrentStateDto]:
        pid = PlayerId(query.player_id)
        snap = self._runtime._state_builder.build_snapshot(int(pid))
        if snap is None:
            return None
        return self._runtime._build_minimal_player_state_dto(pid, snap)


class EscapeGameProfileRepositoryAdapter:
    """find_by_id 1 メソッドだけを満たす player_profile_repository adapter。

    DefaultPromptBuilder は profile から name/role/race/element を取り出して
    SystemPromptPlayerInfoDto に渡すため、最低限のフィールドを持つ
    PlayerProfileAggregate を返す。escape_game ではシナリオ player 名のみ
    重要で、role/race/element は default で十分。
    """

    def __init__(self, runtime: "EscapeGameRuntime") -> None:
        self._runtime = runtime

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerProfileAggregate]:
        name_str = self._runtime.get_player_name(player_id)
        if not name_str:
            return None
        return PlayerProfileAggregate.create(
            player_id=player_id,
            name=PlayerName(name_str),
            role=Role.CITIZEN,
            race=Race.HUMAN,
            element=Element.NEUTRAL,
        )


class EscapeGameSystemPromptBuilder(ISystemPromptBuilder):
    """escape_game の per-player system prompt 文字列を返す。

    Issue #264 第16回実験 (player 2 が自呼びする) で発見された persona 混入バグの
    fix: runtime.build_system_prompt(player_id) 経由で player ごとの persona が
    埋まった system prompt を取得する。player_id は player_info.player_name から
    runtime.get_player_ids() / get_player_name() で逆引きする。

    一致する player_id が無ければ runtime._escape_llm_system_prompt にフォールバック
    (旧挙動: 単体プレイ用 shared prompt)。
    """

    def __init__(self, runtime: "EscapeGameRuntime") -> None:
        self._runtime = runtime

    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        # player_info.player_name から player_id を逆引き。escape_game では
        # player 名は scenario.player_spawns に対して unique。
        for pid in self._runtime.get_player_ids():
            if self._runtime.get_player_name(pid) == player_info.player_name:
                return self._runtime.build_system_prompt(pid)
        # 一致なし: shared prompt にフォールバック
        return self._runtime._escape_llm_system_prompt


class EscapeGameAvailableToolsProvider(IAvailableToolsProvider):
    """DefaultPromptBuilder への tools 渡し用 adapter。

    build_full_prompt の return shape では "tools" は tool 名の list だが、
    DefaultPromptBuilder は OpenAI tool schema を期待する。本 adapter は
    DefaultPromptBuilder 側を満たすために空 list を返し、shape 変換は
    runtime.build_full_prompt 側で行う (実 LLM 呼び出しは run_escape_game.py
    で tools を再構築するため、ここでの値は不要)。
    """

    def get_available_tools(
        self, context: Optional[PlayerCurrentStateDto]
    ) -> List[Dict[str, Any]]:
        del context
        return []
