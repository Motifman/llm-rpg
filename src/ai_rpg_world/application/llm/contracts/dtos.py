"""LLM 向け表示・記憶層の DTO"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple


@dataclass(frozen=True)
class LlmCommandResultDto:
    """
    オーケストレータがツール実行結果を IActionResultStore に渡す際の標準形。
    成功時は message に成功メッセージ、失敗時は message にエラー内容、remediation に対処ヒントを入れる。
    """

    success: bool
    message: str
    error_code: Optional[str] = None
    remediation: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if not isinstance(self.message, str):
            raise TypeError("message must be str")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        if self.remediation is not None and not isinstance(self.remediation, str):
            raise TypeError("remediation must be str or None")


@dataclass(frozen=True)
class SystemPromptPlayerInfoDto:
    """システムプロンプト生成用のプレイヤー情報 DTO"""

    player_name: str
    role: str
    race: str
    element: str
    game_description: str

    def __post_init__(self) -> None:
        if not isinstance(self.player_name, str):
            raise TypeError("player_name must be str")
        if not isinstance(self.role, str):
            raise TypeError("role must be str")
        if not isinstance(self.race, str):
            raise TypeError("race must be str")
        if not isinstance(self.element, str):
            raise TypeError("element must be str")
        if not isinstance(self.game_description, str):
            raise TypeError("game_description must be str")


@dataclass(frozen=True)
class ActionResultEntry:
    """行動結果 1 件（直近の出来事のマージ用）"""

    occurred_at: datetime
    action_summary: str
    result_summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(self.result_summary, str):
            raise TypeError("result_summary must be str")


@dataclass(frozen=True)
class ToolDefinitionDto:
    """1 つのツール定義（OpenAI tools 形式の name / description / parameters 用）。"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be str")
        if not isinstance(self.description, str):
            raise TypeError("description must be str")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be dict")


# ToolAvailabilityContext は PlayerCurrentStateDto をそのまま利用する。
# ツールの利用可否判定に必要な現在地・接続先・視界・移動先等はすべて PlayerCurrentStateDto に含まれる。

# --- 記憶モジュール（Phase 4）---

EpisodeImportance = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class EpisodeMemoryEntry:
    """エピソード記憶 1 件（記憶抽出の出力・ストアの保存単位）。"""

    id: str
    context_summary: str
    action_taken: str
    outcome_summary: str
    entity_ids: Tuple[str, ...]
    location_id: Optional[str]
    timestamp: datetime
    importance: EpisodeImportance
    surprise: bool
    recall_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.context_summary, str):
            raise TypeError("context_summary must be str")
        if not isinstance(self.action_taken, str):
            raise TypeError("action_taken must be str")
        if not isinstance(self.outcome_summary, str):
            raise TypeError("outcome_summary must be str")
        if not isinstance(self.entity_ids, tuple):
            raise TypeError("entity_ids must be tuple")
        for x in self.entity_ids:
            if not isinstance(x, str):
                raise TypeError("entity_ids must contain only str")
        if self.location_id is not None and not isinstance(self.location_id, str):
            raise TypeError("location_id must be str or None")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime")
        if self.importance not in ("low", "medium", "high"):
            raise TypeError("importance must be 'low', 'medium', or 'high'")
        if not isinstance(self.surprise, bool):
            raise TypeError("surprise must be bool")
        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise TypeError("recall_count must be non-negative int")


@dataclass(frozen=True)
class LongTermFactEntry:
    """長期記憶（事実・教訓）1 件。"""

    id: str
    content: str
    player_id: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be datetime")


@dataclass(frozen=True)
class MemoryLawEntry:
    """長期記憶（法則・共起）1 件。主体–関係–対象＋強度。"""

    id: str
    subject: str
    relation: str
    target: str  # 対象
    strength: float
    player_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.subject, str):
            raise TypeError("subject must be str")
        if not isinstance(self.relation, str):
            raise TypeError("relation must be str")
        if not isinstance(self.target, str):
            raise TypeError("target must be str")
        if not isinstance(self.strength, (int, float)):
            raise TypeError("strength must be int or float")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
