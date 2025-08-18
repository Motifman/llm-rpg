from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from src.domain.battle.battle_enum import StatusEffectType, BuffType


@dataclass(frozen=True)
class TurnStartResult:
    can_act: bool
    messages: List[str] = field(default_factory=list)
    # 状態異常による自分へのダメージ
    self_damage: int = 0
    # 回復した状態異常のリスト
    recovered_status_effects: List[StatusEffectType] = field(default_factory=list)


@dataclass(frozen=True)
class TurnEndResult:
    messages: List[str] = field(default_factory=list)
    is_attacker_defeated: bool = False
    # 状態異常によるダメージ・回復
    damage_from_status_effects: int = 0
    healing_from_status_effects: int = 0
    # 期限切れになった状態異常・バフ
    expired_status_effects: List[StatusEffectType] = field(default_factory=list)
    expired_buffs: List[BuffType] = field(default_factory=list)


@dataclass(frozen=True)
class BattleActionResult:
    success: bool
    messages: List[str] = field(default_factory=list)
    
    # ターゲット情報
    target_ids: List[int] = field(default_factory=list)
    
    # ダメージ・回復情報
    damages: List[int] = field(default_factory=list)
    healing_amounts: List[int] = field(default_factory=list)
    is_target_defeated: List[bool] = field(default_factory=list)
    
    # 状態変化情報
    applied_status_effects: List[Tuple[int, StatusEffectType, int]] = field(default_factory=list)
    applied_buffs: List[Tuple[int, BuffType, float, int]] = field(default_factory=list)
    
    # リソース消費
    hp_consumed: int = 0
    mp_consumed: int = 0
    
    # 特殊効果
    critical_hits: List[bool] = field(default_factory=list)
    compatibility_multipliers: List[float] = field(default_factory=list)
    
    # 失敗時の詳細
    failure_reason: Optional[str] = None

    def __post_init__(self):
        # バリデーション
        target_count = len(self.target_ids)
        if len(self.damages) != target_count:
            raise ValueError(f"damages length ({len(self.damages)}) must match target_ids length ({target_count})")
        if len(self.healing_amounts) != target_count:
            raise ValueError(f"healing_amounts length ({len(self.healing_amounts)}) must match target_ids length ({target_count})")
        if len(self.is_target_defeated) != target_count:
            raise ValueError(f"is_target_defeated length ({len(self.is_target_defeated)}) must match target_ids length ({target_count})")
        
        # critical_hitsとcompatibility_multipliersは空でも許可（オプション情報）
        if self.critical_hits and len(self.critical_hits) != target_count:
            raise ValueError(f"critical_hits length ({len(self.critical_hits)}) must match target_ids length ({target_count}) or be empty")
        if self.compatibility_multipliers and len(self.compatibility_multipliers) != target_count:
            raise ValueError(f"compatibility_multipliers length ({len(self.compatibility_multipliers)}) must match target_ids length ({target_count}) or be empty")
    
    @property
    def total_damage(self) -> int:
        return sum(self.damages)
    
    @property
    def total_healing(self) -> int:
        return sum(self.healing_amounts)
    
    @classmethod
    def create_success(
        cls,
        messages: List[str],
        target_ids: List[int] = None,
        damages: List[int] = None,
        healing_amounts: List[int] = None,
        is_target_defeated: List[bool] = None,
        applied_status_effects: List[Tuple[int, StatusEffectType, int]] = None,
        applied_buffs: List[Tuple[int, BuffType, float, int]] = None,
        hp_consumed: int = 0,
        mp_consumed: int = 0,
        critical_hits: List[bool] = None,
        compatibility_multipliers: List[float] = None,
    ) -> "BattleActionResult":
        """成功時のBattleActionResultを作成"""
        return cls(
            success=True,
            messages=messages,
            target_ids=target_ids or [],
            damages=damages or [],
            healing_amounts=healing_amounts or [],
            is_target_defeated=is_target_defeated or [],
            applied_status_effects=applied_status_effects or [],
            applied_buffs=applied_buffs or [],
            hp_consumed=hp_consumed,
            mp_consumed=mp_consumed,
            critical_hits=critical_hits or [],
            compatibility_multipliers=compatibility_multipliers or [],
            failure_reason=None,
        )
    
    @classmethod
    def create_failure(
        cls,
        messages: List[str],
        failure_reason: str,
        hp_consumed: int = 0,
        mp_consumed: int = 0,
    ) -> "BattleActionResult":
        """失敗時のBattleActionResultを作成"""
        return cls(
            success=False,
            messages=messages,
            target_ids=[],
            damages=[],
            healing_amounts=[],
            is_target_defeated=[],
            applied_status_effects=[],
            applied_buffs=[],
            hp_consumed=hp_consumed,
            mp_consumed=mp_consumed,
            critical_hits=[],
            compatibility_multipliers=[],
            failure_reason=failure_reason,
        )