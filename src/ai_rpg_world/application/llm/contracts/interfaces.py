"""LLM 向け表示層のポート（インターフェース）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmUiContextDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import MemoFulfillmentContext
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ISlidingWindowMemory(ABC):
    """短期記憶: 直近観測を保持する抽象。

    Phase 2 (#356 後続) で 2 実装が並列に存在する:

    - ``DefaultSlidingWindowMemory``: 固定容量の sliding window (既定)
    - ``RollingSummaryShortTermMemory``: L1 raw + L4 mid summary 階層化

    本 interface 名は歴史的経緯 (旧名 ``ISlidingWindowMemory``) で残っており、
    将来 ``IShortTermMemory`` への改名候補がある (別 PR)。
    """

    @abstractmethod
    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        """指定プレイヤーの観測を 1 件追加する。"""
        pass

    @abstractmethod
    def append_all(
        self, player_id: PlayerId, entries: List[ObservationEntry]
    ) -> List[ObservationEntry]:
        """
        指定プレイヤーに観測を複数件追加する。
        戻り値は今回の追加によりウィンドウから溢れた（捨てられた）観測のリスト。
        """
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]:
        """指定プレイヤーの直近 limit 件の観測を新しい順で返す。"""
        pass

    def get_mid_summary_text(self, player_id: PlayerId) -> str:
        """Phase 2: 中期記憶 (L4 mid summary) を prompt 用テキストに整形する。

        ``RollingSummaryShortTermMemory`` のみ実体を返す。``DefaultSlidingWindowMemory``
        は default 実装の空文字を返し、prompt §「【最近の流れ】」section ごと出ない。

        prompt_builder はこのメソッドを直接呼んで context_format_strategy に
        渡す。実装差し替えは scenario / env で選ぶ。
        """
        return ""

    def get_long_summary_text(self, player_id: PlayerId) -> str:
        """Phase 3: 長期記憶 (L5 long summary / self_image + world_view) を
        prompt 用テキストに整形する。

        ``RollingSummaryShortTermMemory`` のみ実体を返す (L5 統合済みの場合)。
        ``DefaultSlidingWindowMemory`` は空文字 → §「【自己像と世界観】」非表示。
        """
        return ""


class IActionResultStore(ABC):
    """直近の LLM 行動結果を保持する。"""

    @abstractmethod
    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        *,
        success: bool = True,
        error_code: Optional[str] = None,
        tool_name: Optional[str] = None,
        argument_fingerprint: Optional[str] = None,
        should_reschedule: bool = False,
    ) -> None:
        """行動結果を 1 件追加する。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ActionResultEntry]:
        """指定プレイヤーの直近 limit 件の行動結果を新しい順で返す。"""
        pass


class IMemoStore(ABC):
    """プレイヤーごとの memo を保持する。

    Issue #188 Phase 1a で ``ITodoStore`` から改名。LLM が context に固定
    したい情報 (タスク / 目標 / 戦略メモ / 注意事項など) を扱う。

    ``add`` には optional な ``current_tick`` を渡せる: age 表示 / stale 判定
    用。``complete`` には fulfillment_context (周辺 sliding_window 抜粋) を
    渡せる: 後で episodic cue 経由で recall するときに「達成時の状況」を辿る
    情報源となる。
    """

    @abstractmethod
    def add(
        self,
        player_id: PlayerId,
        content: str,
        *,
        current_tick: Optional[int] = None,
    ) -> str:
        """memo を追加し、生成された ID を返す。"""
        pass

    @abstractmethod
    def list_uncompleted(self, player_id: PlayerId) -> List[MemoEntry]:
        """未完了 memo を新しい順で返す。"""
        pass

    @abstractmethod
    def complete(
        self,
        player_id: PlayerId,
        memo_id: str,
        *,
        fulfillment_context: Optional[MemoFulfillmentContext] = None,
    ) -> bool:
        """memo を完了する。存在しなければ False。"""
        pass

    @abstractmethod
    def remove(self, player_id: PlayerId, memo_id: str) -> bool:
        """memo を削除する。存在しなければ False。"""
        pass


# 後方互換: 旧名 ``ITodoStore`` は ``IMemoStore`` のエイリアス。
# 新規コードは IMemoStore を使うこと。
ITodoStore = IMemoStore


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
        state: Optional[PlayerCurrentStateDto],
    ) -> LlmUiContextDto:
        """LLM 用 UI コンテキストを構築する。"""
        pass


class IRecentEventsFormatter(ABC):
    """観測と行動結果を「直近の出来事」テキストに整形する。"""

    @abstractmethod
    def format(
        self,
        observations: List[ObservationEntry],
        action_results: List[ActionResultEntry],
    ) -> str:
        """観測と行動結果を統合して文字列化する。"""
        pass


class IContextFormatStrategy(ABC):
    """現在状態・直近出来事・LLM が固定した memo を user prompt 用コンテキストへ整形する。"""

    @abstractmethod
    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str = "",
        active_memos_text: str = "",
        objective_text: str = "",
        inventory_text: str = "",
        learned_text: str = "",
        mid_summary_text: str = "",
        long_summary_text: str = "",
    ) -> str:
        """user prompt に入れる文脈テキストを返す。

        ``active_memos_text`` は LLM が ``memo_add`` で固定した「進行中のメモ」
        section に表示するテキスト (Issue #188 Phase 1a)。空文字なら section を
        出さない。

        ``objective_text`` は実行ランタイムが固定の目的文を渡したい場合に使う
        (例: escape_game の「【現在の目的】この廃墟から外へ脱出する」)。空なら
        section を出さない (Issue #227 chore β: 経路統一)。

        ``inventory_text`` は所持物証の整形済テキスト。callable provider が
        生成して渡す。空なら section を出さない。

        ``learned_text`` は semantic memory の passive top-K を一覧化した
        「【関連する学び】」section の本体 (Phase 1c)。`SemanticPassiveRecallService`
        が状況連想で抽出した上位 K 件を箇条書きにする。空なら section を
        出さない。

        ``mid_summary_text`` は短期記憶 (L4 mid summary) を一覧化した
        「【最近の流れ】」section の本体 (Phase 2)。``RollingSummaryShortTermMemory``
        が直近 N 件 raw 観測から圧縮した 3 世代分を箇条書きにする。
        ``DefaultSlidingWindowMemory`` 利用時は空のままで section ごと省略。
        """
        pass


class ISystemPromptBuilder(ABC):
    """system prompt を組み立てる。"""

    @abstractmethod
    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        """プレイヤー情報から system prompt を返す。"""
        pass


class IPromptBuilder(ABC):
    """LLM API に渡す prompt request を組み立てる。"""

    @abstractmethod
    def build(
        self,
        player_id: PlayerId,
        action_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """messages/tools/tool_choice 等を含むリクエスト辞書を返す。"""
        pass


class IAvailabilityResolver(ABC):
    """ツール利用可否を現在状態から判定する。"""

    @abstractmethod
    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
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
    ) -> List[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
        """登録済みのツール定義と resolver を返す。"""
        pass


class IAvailableToolsProvider(ABC):
    """LLM API に渡す tools 配列を返す。"""

    @abstractmethod
    def get_available_tools(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> List[Dict[str, Any]]:
        """利用可能ツールを OpenAI tool schema 形式で返す。"""
        pass


class IToolArgumentResolver(ABC):
    """LLM が返した引数をドメインコマンド用の正規化引数へ変換する。"""

    @abstractmethod
    def resolve(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
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


class ILLMClient(ABC):
    """LLM 呼び出しクライアント。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
        *,
        metrics_sink: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        LLM を呼び出し、選択された tool_call を返す。
        返り値例: {"name": "move_to_destination", "arguments": "{...}"}

        ``metrics_sink`` (``LlmCallMetricsSink``) が渡されたら、呼び出し完了時に
        ``LlmCallMetrics`` で記録する (実装側の任意)。実 LLM クライアントは
        wall_latency + token usage を埋め、stub 系は best-effort で実装する。
        """
        pass
