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
    shout_level: int  # (0: 通常, 1: シャウト)


@dataclass(frozen=True)
class PendingMessage:
    sender_id: str
    spot_id: str
    content: str
    audience_kind: AudienceKind
    audience_ids: Optional[List[str]]
    shout_level: int  # (0: 通常, 1: シャウト)
    created_at: datetime.datetime


@dataclass(frozen=True)
class ReceivedMessage:
    message_id: str
    sender_id: str
    spot_id: str
    content: str
    created_at: datetime.datetime
    is_direct: bool