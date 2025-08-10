import abc
import uuid
import datetime
import json
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class AudienceKind(Enum):
    SPOT_ALL = "spot_all"
    PLAYERS = "players"


class DeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"


@dataclass(frozen=True)
class OutgoingMessage:
    sender_id: str
    spot_id: str
    content: str
    audience_kind: AudienceKind
    audience_ids: List[str]  # 作成時点で既に送信先は解決されている
    is_shout: bool = False


@dataclass(frozen=True)
class ReceivedMessage:
    message_id: str
    sender_id: str
    spot_id: str
    content: str
    audience_kind: AudienceKind
    is_shout: bool