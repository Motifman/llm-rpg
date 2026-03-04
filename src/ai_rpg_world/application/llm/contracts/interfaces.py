"""LLM 向け表示・記憶層のポート（インターフェース）"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ISlidingWindowMemory(ABC):
    """観測のスライディングウィンドウ記憶。直近 N 件を返す。"""

    @abstractmethod
    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        """指定プレイヤーの観測を 1 件追加する。"""
        pass

    @abstractmethod
    def append_all(self, player_id: PlayerId, entries: List[ObservationEntry]) -> None:
        """指定プレイヤーに観測を複数件追加する。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]:
        """指定プレイヤーの直近 limit 件の観測を新しい順で返す。"""
        pass


class IActionResultStore(ABC):
    """行動要約＋結果要約の記録。直近 M 件を返す。"""

    @abstractmethod
    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        """1 件の行動結果を追加する。occurred_at は省略時は現在時刻。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ActionResultEntry]:
        """指定プレイヤーの直近 limit 件の行動結果を新しい順で返す。"""
        pass


class ICurrentStateFormatter(ABC):
    """PlayerCurrentStateDto を現在状態のプロンプト用テキストに変換する。"""

    @abstractmethod
    def format(self, dto: PlayerCurrentStateDto) -> str:
        """現在状態の 1 本のテキストを返す。"""
        pass


class IRecentEventsFormatter(ABC):
    """観測リストと行動結果リストを「直近の出来事」テキストに変換する。"""

    @abstractmethod
    def format(
        self,
        observations: List[ObservationEntry],
        action_results: List[ActionResultEntry],
    ) -> str:
        """観測と行動結果を時刻でマージした直近の出来事テキストを返す。"""
        pass


class IContextFormatStrategy(ABC):
    """現在状態・直近の出来事・関連記憶を 1 本のコンテキスト文字列にフォーマットする。"""

    @abstractmethod
    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str,
    ) -> str:
        """3 つのセクションを結合したコンテキスト文字列を返す。"""
        pass


class ISystemPromptBuilder(ABC):
    """プレイヤー情報 DTO からシステムプロンプト文字列を生成する。"""

    @abstractmethod
    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        """システムプロンプト文字列を返す。"""
        pass


class IPromptBuilder(ABC):
    """1 ターン分のプロンプト（OpenAI 互換 messages）を組み立てる。"""

    @abstractmethod
    def build(
        self,
        player_id: PlayerId,
        action_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        OpenAI 互換の辞書を返す。
        {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}], "tools": [], "tool_choice": "required"}
        action_instruction は user 末尾に付与する行動選択の説明。省略時はデフォルト文言。
        """
        pass


# --- ツール利用可否・ツール一覧（ToolAvailabilityContext = PlayerCurrentStateDto） ---


class IAvailabilityResolver(ABC):
    """あるツールが現在のコンテキストで利用可能かどうかを判定する。"""

    @abstractmethod
    def is_available(
        self, context: Optional[PlayerCurrentStateDto]
    ) -> bool:
        """context でこのツールを提示するか。未配置時は context が None のことがある。"""
        pass


class IGameToolRegistry(ABC):
    """全ツール定義の登録・取得。"""

    @abstractmethod
    def register(
        self,
        definition: ToolDefinitionDto,
        resolver: IAvailabilityResolver,
    ) -> None:
        """ツール定義とその利用可否リゾルバを登録する。"""
        pass

    @abstractmethod
    def get_definitions_with_resolvers(
        self,
    ) -> List[Tuple[ToolDefinitionDto, "IAvailabilityResolver"]]:
        """登録済みの (ToolDefinitionDto, IAvailabilityResolver) のリストを返す。"""
        pass


class IAvailableToolsProvider(ABC):
    """現在状況から利用可能なツールのリスト（OpenAI tools 形式）を返す。"""

    @abstractmethod
    def get_available_tools(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> List[Dict[str, Any]]:
        """context に応じて利用可能なツールだけを OpenAI の tools 形式で返す。"""
        pass


# --- LLM ターン駆動（スケジュール＋実行） ---


class ILLMPlayerResolver(ABC):
    """プレイヤーが LLM 制御かどうかを判定するポート。"""

    @abstractmethod
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        """指定プレイヤーが LLM 制御なら True。"""
        pass


class ILlmTurnTrigger(ABC):
    """LLM ターンのスケジュールと一括実行のポート。観測到着時に schedule_turn、ループ/ティックで run_scheduled_turns を呼ぶ。"""

    @abstractmethod
    def schedule_turn(self, player_id: PlayerId) -> None:
        """指定プレイヤーのターン実行を 1 回スケジュールする（重複は 1 回にまとまる）。"""
        pass

    @abstractmethod
    def run_scheduled_turns(self) -> None:
        """スケジュール済みの全プレイヤーについて run_turn を 1 回ずつ実行し、キューをクリアする。"""
        pass


# --- LLM API 抽象化 ---


class ILLMClient(ABC):
    """LLM API 呼び出しのポート。messages + tools を送り、1 つの tool_call を受け取る。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        """
        1 回の LLM 呼び出しを行い、tool_call があればそれを返す。
        戻り値: {"name": str, "arguments": dict} または tool_call が無い場合 None。
        """
        pass
