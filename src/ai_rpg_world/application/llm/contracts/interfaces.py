"""LLM 向け表示・記憶層のポート（インターフェース）"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
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
