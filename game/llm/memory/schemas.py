from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional


MessageType = Literal["observation", "action", "outcome"]


@dataclass
class MessageBase:
    """LLMコンテキスト用の共通メッセージ型。

    - type: メッセージの種別（観測・行動・結果）
    - content: 本文（自然言語）
    - metadata: 任意メタ情報（例: spot_id, target_id, tags など）
    - timestamp: 生成時刻（UTC）
    - tokens_estimate: 概算トークン数（簡易推定）。選別や予算管理用
    - importance: 重要度（0-10）。削除・要約の優先度に利用
    """

    type: MessageType
    content: str
    metadata: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_estimate: int = 0
    importance: int = 5

    def ensure_estimates(self) -> None:
        """概算トークン数が未設定の場合は簡易推定を行う。"""
        if self.tokens_estimate <= 0 and self.content:
            # ざっくり: 1トークン ≒ 4文字（日本語も混在前提の粗い推定）
            self.tokens_estimate = max(1, len(self.content) // 4)


@dataclass
class ObservationMessage(MessageBase):
    type: MessageType = "observation"


@dataclass
class ActionMessage(MessageBase):
    type: MessageType = "action"
    action_name: Optional[str] = None
    action_args: Optional[Dict[str, str]] = None


@dataclass
class OutcomeMessage(MessageBase):
    type: MessageType = "outcome"
    success: Optional[bool] = None
    error: Optional[str] = None


def total_tokens(messages: List[MessageBase]) -> int:
    for m in messages:
        m.ensure_estimates()
    return sum(m.tokens_estimate for m in messages)


