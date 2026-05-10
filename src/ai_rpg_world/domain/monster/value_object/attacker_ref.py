"""攻撃者の参照を統一型で表す値オブジェクト。

モンスターを攻撃する主体は player と monster の 2 種類があり得る。
両者を 1 つの型で扱いつつ ID 取り違えを防ぐため discriminated union 形式
で定義する。

Phase 4a で `MonsterAggregate.last_attacker_ref` として保持し、反撃 (CHASE)
や逃走方向の判断材料にする。

Examples:
    monster→monster 攻撃:
        AttackerRef.of_monster(MonsterId(101))
    player→monster 攻撃:
        AttackerRef.of_player(PlayerId(1))
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_rpg_world.domain.common.exception import ValidationException
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterDomainException,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class AttackerRefValidationException(MonsterDomainException, ValidationException):
    """AttackerRef のバリデーション例外。"""

    error_code = "MONSTER.ATTACKER_REF_VALIDATION"


class AttackerKind(Enum):
    """攻撃者の種別。"""

    PLAYER = "player"
    MONSTER = "monster"


@dataclass(frozen=True)
class AttackerRef:
    """攻撃者の identity 参照。種別 + ID の discriminated union。

    `kind` に応じて `monster_id` または `player_id` のどちらか **だけ** が
    設定されている。両方 None / 両方非 None はバリデーションで弾く。
    """

    kind: AttackerKind
    monster_id: Optional[MonsterId] = None
    player_id: Optional[PlayerId] = None

    def __post_init__(self) -> None:
        if self.kind == AttackerKind.MONSTER:
            if self.monster_id is None:
                raise AttackerRefValidationException(
                    "AttackerRef(kind=MONSTER) requires monster_id"
                )
            if self.player_id is not None:
                raise AttackerRefValidationException(
                    "AttackerRef(kind=MONSTER) must not set player_id"
                )
        elif self.kind == AttackerKind.PLAYER:
            if self.player_id is None:
                raise AttackerRefValidationException(
                    "AttackerRef(kind=PLAYER) requires player_id"
                )
            if self.monster_id is not None:
                raise AttackerRefValidationException(
                    "AttackerRef(kind=PLAYER) must not set monster_id"
                )
        else:
            raise AttackerRefValidationException(f"Unknown kind: {self.kind}")

    @classmethod
    def of_monster(cls, monster_id: MonsterId) -> "AttackerRef":
        return cls(kind=AttackerKind.MONSTER, monster_id=monster_id)

    @classmethod
    def of_player(cls, player_id: PlayerId) -> "AttackerRef":
        return cls(kind=AttackerKind.PLAYER, player_id=player_id)

    @property
    def is_monster(self) -> bool:
        return self.kind == AttackerKind.MONSTER

    @property
    def is_player(self) -> bool:
        return self.kind == AttackerKind.PLAYER
