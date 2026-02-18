"""
種族・勢力間の関係（Disposition）を判定するドメインサービス。
敵対・獲物・脅威を統一した関係タイプで表現する。
"""

from abc import ABC, abstractmethod
from typing import Dict, Set

from ai_rpg_world.domain.world.enum.world_enum import Disposition
from ai_rpg_world.domain.world.exception.behavior_exception import (
    ComponentRequiredForDispositionException,
)


def _require_component(actor_comp, target_comp) -> None:
    """関係判定に必要な component が揃っていることを検証する。WorldObject は component を持つ前提。"""
    if actor_comp is None:
        raise ComponentRequiredForDispositionException(
            "actor_comp must not be None for disposition check"
        )
    if target_comp is None:
        raise ComponentRequiredForDispositionException(
            "target_comp must not be None for disposition check"
        )


class HostilityService(ABC):
    """
    アクター間の関係タイプを判定するサービスのインターフェース。
    get_disposition を主とし、is_hostile / is_threat / is_prey はその派生。
    """

    @abstractmethod
    def get_disposition(self, actor_comp, target_comp) -> Disposition:
        """
        actor_comp から target_comp への関係タイプを返す。
        """
        pass

    def is_hostile(self, actor_comp, target_comp) -> bool:
        """敵対（攻撃・CHASE の対象）かどうか。HOSTILE または PREY のとき True。"""
        _require_component(actor_comp, target_comp)
        return self.get_disposition(actor_comp, target_comp) in (
            Disposition.HOSTILE,
            Disposition.PREY,
        )

    def is_threat(self, actor_comp, target_comp) -> bool:
        """脅威（視界内にいれば FLEE）かどうか。"""
        _require_component(actor_comp, target_comp)
        return self.get_disposition(actor_comp, target_comp) == Disposition.THREAT

    def is_prey(self, actor_comp, target_comp) -> bool:
        """獲物（ターゲット選択で優先）かどうか。"""
        _require_component(actor_comp, target_comp)
        return self.get_disposition(actor_comp, target_comp) == Disposition.PREY


class ConfigurableHostilityService(HostilityService):
    """
    設定可能な関係テーブルを持つ実装。
    コンポーネントの threat_races / prey_races（テンプレート由来）を最優先し、
    次に勢力(faction)の敵対テーブル、種族(race)の Disposition テーブルで判定する。
    """

    def __init__(
        self,
        race_disposition_table: Dict[str, Dict[str, Disposition]] = None,
        faction_hostility_table: Dict[str, Set[str]] = None,
    ):
        # 種族 -> (対象種族 -> Disposition)
        self._race_disposition = race_disposition_table or {}
        # 勢力 -> 敵対する勢力のセット（HOSTILE として扱う）
        self._faction_hostility = faction_hostility_table or {}

    def get_disposition(self, actor_comp, target_comp) -> Disposition:
        _require_component(actor_comp, target_comp)
        target_race = getattr(target_comp, "race", None)
        if target_race is not None:
            # 1. コンポーネントの threat_races（テンプレート由来）を最優先
            threat_races = getattr(actor_comp, "threat_races", None)
            if threat_races and target_race in threat_races:
                return Disposition.THREAT
            # 2. コンポーネントの prey_races（テンプレート由来）
            prey_races = getattr(actor_comp, "prey_races", None)
            if prey_races and target_race in prey_races:
                return Disposition.PREY

        # 3. 勢力による判定
        if actor_comp.faction in self._faction_hostility:
            if target_comp.faction in self._faction_hostility[actor_comp.faction]:
                return Disposition.HOSTILE

        # 4. 種族の Disposition テーブル
        if actor_comp.race in self._race_disposition:
            by_target = self._race_disposition[actor_comp.race]
            if target_comp.race in by_target:
                return by_target[target_comp.race]

        return Disposition.NEUTRAL
