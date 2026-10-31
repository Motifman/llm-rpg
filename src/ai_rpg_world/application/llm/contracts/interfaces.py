"""LLM 向け表示層のポート（インターフェース）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmUiContextDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class IActionResultStore(ABC):
    """直近の LLM 行動結果を保持する。"""

    @abstractmethod
    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        occurred_at: datetime | None = None,
        *,
        success: bool = True,
        error_code: str | None = None,
        tool_name: str | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        argument_fingerprint: str | None = None,
        should_reschedule: bool = False,
        game_time_label: str | None = None,
        omit_result_in_prompt: bool = False,
        inner_thought: str | None = None,
        occurred_tick: int | None = None,
        execution_provenance: ExecutionProvenance | None = None,
    ) -> None:
        """行動結果を 1 件追加する。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> list[ActionResultEntry]:
        """指定プレイヤーの直近 limit 件の行動結果を新しい順で返す。"""
        pass


class ICurrentStateFormatter(ABC):
    """現在状態 DTO を LLM 向けテキストに整形する。"""

    @abstractmethod
    def format(self, state: PlayerCurrentStateDto) -> str:
        """現在状態を文字列化する。"""
        pass


class ILlmUiContextBuilder(ABC):
    """現在状態テキストと tool runtime context を同時に組み立てる。"""

    @abstractmethod
    def build(
        self,
        base_current_state_text: str,
        state: PlayerCurrentStateDto | None,
    ) -> LlmUiContextDto:
        """LLM 用 UI コンテキストを構築する。"""
        pass


class IRecentEventsFormatter(ABC):
    """観測と行動結果を「直近の出来事」テキストに整形する。"""

    @abstractmethod
    def format(
        self,
        observations: list[ObservationEntry],
        action_results: list[ActionResultEntry],
    ) -> str:
        """観測と行動結果を統合して文字列化する。"""
        pass

    @abstractmethod
    def format_unified_entries(self, entries: list[UnifiedRecentEventEntry]) -> str:
        """記録時に統一済みの時系列を文字列化する。"""
        pass


class IPromptBuilder(ABC):
    """LLM API に渡す prompt request を組み立てる。"""

    @abstractmethod
    def build(
        self,
        acting: ActingBeing,
        action_instruction: str | None = None,
    ) -> dict[str, Any]:
        """messages/tools/tool_choice 等を含むリクエスト辞書を返す。"""
        pass


class IAvailabilityResolver(ABC):
    """ツール利用可否を現在状態から判定する。"""

    @abstractmethod
    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        """現在状態でツールを出してよいなら True。"""
        pass


class IGameToolRegistry(ABC):
    """ゲームツール定義と利用可否 resolver を登録・列挙する。"""

    @abstractmethod
    def register(
        self,
        definition: ToolDefinitionDto,
        availability_resolver: IAvailabilityResolver,
    ) -> None:
        """ツール定義を登録する。"""
        pass

    @abstractmethod
    def get_definitions_with_resolvers(
        self,
    ) -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
        """登録済みのツール定義と resolver を返す。"""
        pass


class IAvailableToolsProvider(ABC):
    """LLM API に渡す tools 配列を返す。"""

    @abstractmethod
    def get_available_tools(
        self,
        context: PlayerCurrentStateDto | None,
    ) -> list[dict[str, Any]]:
        """利用可能ツールを OpenAI tool schema 形式で返す。"""
        pass


class IToolArgumentResolver(ABC):
    """LLM が返した引数をドメインコマンド用の正規化引数へ変換する。"""

    @abstractmethod
    def resolve(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> dict[str, Any]:
        """tool_name ごとの引数補完・正規化を行う。"""
        pass


class ILLMPlayerResolver(ABC):
    """LLM 操作対象プレイヤーを解決する。"""

    @abstractmethod
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        """指定プレイヤーが LLM 制御なら True。"""
        pass


class ILlmTurnTrigger(ABC):
    """観測イベントから LLM ターンをスケジュール・実行する。"""

    @abstractmethod
    def schedule_turn(self, player_id: PlayerId) -> None:
        """指定プレイヤーの LLM ターンを予約する。"""
        pass

    @abstractmethod
    def run_scheduled_turns(self) -> None:
        """予約された LLM ターンを実行する。"""
        pass


# NOTE (Issue #470 Phase 1 cleanup A3):
# ``ILLMClient`` は ``application/llm/ports/llm_client_port.py`` に移動した。
# 本ファイルから直接 import していたコードは ports/ から import すること。
