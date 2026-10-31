"""DefaultPromptBuilder 用の Config dataclass 群。

Issue #227 後続レビュー (HIGH-1) 改善: __init__ の 22 引数を 4 つの dataclass に
グループ化し、テスト fixture や wiring 側の組み立てを楽にする。各 dataclass は
「機能の塊」として独立しており、Optional な機能 (メモ帳など) は丸ごと省略できる。

API:
    DefaultPromptBuilder(
        core=PromptBuilderCoreServices(...),     # 必須インフラ
        sections=PromptSectionProviders(...),    # オプション section 群
        limits=PromptLimits(...),                # 数値設定・action_instruction
        ui_context_builder=ui_context_builder,
        current_tick_provider=None,
    )

各 dataclass は frozen で immutable。検証は DefaultPromptBuilder.__init__ で行う。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    ICurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.contract import Orientation
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
    from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery


DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"


class _PlayerCurrentStateSource(Protocol):
    """prompt 組み立てに要るのは現在状態の取得だけ。"""

    def get_player_current_state(self, query: GetPlayerCurrentStateQuery) -> PlayerCurrentStateDto | None: ...


@dataclass(frozen=True)
class PromptBuilderCoreServices:
    """DefaultPromptBuilder が必須とするインフラサービス群。

    全て non-Optional。wiring 側で対応する依存を解決して渡すことを想定する。
    """

    observation_buffer: IObservationContextBuffer
    # 取り出した観測を足す先。足すと写す処理が Being の短期記憶に書く (design_decisions D1824-7)。
    recent_event_store: UnifiedRecentEventStore
    # 本体の service ではなく、必要な 1 メソッドだけを要求する。
    # world_runtime は duck-type adapter を渡す (#1371)。
    world_query_service: _PlayerCurrentStateSource
    current_state_formatter: ICurrentStateFormatter
    available_tools_provider: IAvailableToolsProvider
    # Being の持ち物から区画の本文を集める問い合わせ (#1630)。
    working_memory: CurrentWorkingMemory
    # 環境が毎ターン渡し直す、入るときの案内。プレイヤーが環境に居なければ None。
    orientation_provider: Callable[[PlayerId], Orientation | None]
    # システムプロンプトの、案内の後に置く作法と環境の決まりの文。
    conduct_text_provider: Callable[[], str]


@dataclass(frozen=True)
class PromptSectionProviders:
    """環境が渡す任意の材料。"""

    # 環境が課す目的。空なら【現在の目的】を出さない。
    objective_text_provider: Callable[[PlayerId], str] | None = None


@dataclass(frozen=True)
class PromptLimits:
    """プロンプトに添える行動指示。"""

    default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION
