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
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IShortTermMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
    from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
    from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate


DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"


class _PlayerCurrentStateSource(Protocol):
    """prompt 組み立てに要るのは現在状態の取得だけ。"""

    def get_player_current_state(self, query: GetPlayerCurrentStateQuery) -> PlayerCurrentStateDto | None: ...


class _PlayerProfileSource(Protocol):
    """prompt 組み立てに要るのは profile の取得だけ。"""

    def find_by_id(self, player_id: PlayerId) -> PlayerProfileAggregate | None: ...


@dataclass(frozen=True)
class PromptBuilderCoreServices:
    """DefaultPromptBuilder が必須とするインフラサービス群。

    全て non-Optional。wiring 側で対応する依存を解決して渡すことを想定する。
    """

    observation_buffer: IObservationContextBuffer
    short_term_memory: IShortTermMemory
    # 本体の service ではなく、必要な 1 メソッドだけを要求する。
    # world_runtime は duck-type adapter を渡す (#1371)。
    world_query_service: _PlayerCurrentStateSource
    player_profile_repository: _PlayerProfileSource
    current_state_formatter: ICurrentStateFormatter
    context_format_strategy: IContextFormatStrategy
    system_prompt_builder: ISystemPromptBuilder
    available_tools_provider: IAvailableToolsProvider
    # 【直近の出来事】と【ここまでのいきさつ】の本文。Being の短期記憶から作る (#1824)。
    recent_events_text_provider: Callable[[BeingId], str]
    backstory_text_provider: Callable[[BeingId], str]


@dataclass(frozen=True)
class PromptSectionProviders:
    """各 prompt section の任意 provider 群。

    未設定なら該当 section は省略される。world_runtime runtime のような独自の
    objective / inventory section を持つ runtime はこれらを注入する。
    """

    persona_block_provider: Callable[[PlayerId], str] | None = None
    objective_text_provider: Callable[[PlayerId], str] | None = None
    inventory_text_provider: Callable[[PlayerId], str] | None = None
    # #1520: Being が描いた【知っている人】。system prompt ではなく毎ターンの
    # メッセージの、目的の直後に置く。
    known_people_text_provider: Callable[[PlayerId], str] | None = None
    # #1623: エピソードの目次【思い出せる出来事】。目次を出す設定では空でも文を返す。
    episode_index_text_provider: Callable[[PlayerId], str] | None = None
    # #1628: Being のメモ帳。毎ターン同じ位置に、空の分類の見出しも含めて出す。
    being_memo_text_provider: Callable[[PlayerId], str] | None = None


@dataclass(frozen=True)
class PromptLimits:
    """プロンプトに添える行動指示。"""

    default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION
