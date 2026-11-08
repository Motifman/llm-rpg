from __future__ import annotations

from collections.abc import Mapping

import pytest

from ai_rpg_world.game_world.domain.exception.rules_exception import (
    ActionDurationNotApplicableException,
    MissingActionDurationException,
)
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel, SoundLoss
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    FatigueAmount,
    HitPoints,
    HungerAmount,
    Multiplier,
    Probability,
    Ticks,
)

_KINDS_WITHOUT_DEFAULT_DURATION = (
    ActionKind.SPEAK,
    ActionKind.WAIT,
    ActionKind.TRAVEL,
    ActionKind.ATTACK_MONSTER,
)
_KINDS_WITH_DEFAULT_DURATION = (
    ActionKind.LISTEN,
    ActionKind.PICK_UP,
    ActionKind.DROP,
    ActionKind.HAND_OVER,
    ActionKind.ENTER_SECTION,
    ActionKind.LEAVE_SECTION,
    ActionKind.CAST_BALLOT,
    ActionKind.HOLD,
    ActionKind.PUT_AWAY,
    ActionKind.INTERACT_WITH_OBJECT,
    ActionKind.INTERACT_WITH_CARRIED_ITEM,
    ActionKind.INTERACT_WITH_PERSON,
    ActionKind.USE_ITEM,
    ActionKind.SEARCH,
    ActionKind.TEND,
)


def _durations() -> dict[ActionKind, Ticks]:
    return {kind: Ticks(1) for kind in _KINDS_WITH_DEFAULT_DURATION}


def _rules(action_durations: Mapping[ActionKind, Ticks]) -> WorldRules:
    return WorldRules(
        tend=NoTending(),
        fatigue=FatigueRule(
            per_exertion=FatigueAmount(2),
            limit=FatigueAmount(100),
            levels=(FatigueLevel(FatigueAmount(0), FatigueLevelName("元気")),),
        ),
        hunger=HungerRule(
            per_tick=HungerAmount(1),
            limit=HungerAmount(100),
            starvation_damage=NoStarvationDamage(),
            levels=(HungerLevel(HungerAmount(0), HungerLevelName("満腹")),),
        ),
        death=DeathRule(grace=Ticks(30)),
        departed_persons_act=False,
        name_tags=False,
        hearing=HearingValues(
            loudness={
                Loudness.WHISPER: SoundLevel(30),
                Loudness.NORMAL: SoundLevel(60),
                Loudness.LOUD: SoundLevel(75),
                Loudness.VERY_LOUD: SoundLevel(90),
            },
            loss_per_passage=SoundLoss(15),
            clear_from=SoundLevel(50),
            muffled_from=SoundLevel(35),
            faint_from=SoundLevel(20),
            attentive_allowance=SoundLoss(15),
        ),
        stealth=StealthRule(
            notice_by_bystander={
                SeesClearly(): Probability(0.4),
                SeesShapes(): Probability(0.15),
                SeesNothing(): Probability(0.0),
            },
            notice_by_target={
                SeesClearly(): Probability(0.6),
                SeesShapes(): Probability(0.3),
                SeesNothing(): Probability(0.0),
            },
            attentive_bonus=Probability(0.2),
            duration_multiplier=Multiplier(2.0),
        ),
        action_durations=action_durations,
        person_max_hp=HitPoints(100, 100),
        pack_capacity=Capacity(20),
    )


class TestWorldRulesActionDurations:
    """WorldRules.action_durations が、行っているあいだを作る行為の既定の長さをすべて持ち、ほかの行為の長さを持たないことを保証する。"""

    def test_test_lists_split_every_action_kind(self) -> None:
        """ActionKind のうち、行っているあいだを作る行為と作らない行為の 2 つの並びで、すべての種類を漏れなく分けている。"""
        assert set(_KINDS_WITH_DEFAULT_DURATION) | set(_KINDS_WITHOUT_DEFAULT_DURATION) == set(ActionKind)
        assert not set(_KINDS_WITH_DEFAULT_DURATION) & set(_KINDS_WITHOUT_DEFAULT_DURATION)

    def test_holds_the_declared_duration_of_each_kind(self) -> None:
        """探すに 3 tick を宣言すると、action_durations[SEARCH] は 3 tick を答える。"""
        durations = _durations() | {ActionKind.SEARCH: Ticks(3)}

        rules = _rules(durations)

        assert rules.action_durations[ActionKind.SEARCH] == Ticks(3)

    @pytest.mark.parametrize("missing", _KINDS_WITH_DEFAULT_DURATION)
    def test_lacking_a_kind_with_default_duration_is_refused(self, missing: ActionKind) -> None:
        """行っているあいだを作る行為の長さが 1 つでも欠けていると MissingActionDurationException を投げる。"""
        durations = {kind: ticks for kind, ticks in _durations().items() if kind != missing}

        with pytest.raises(MissingActionDurationException):
            _rules(durations)

    @pytest.mark.parametrize("extra", _KINDS_WITHOUT_DEFAULT_DURATION)
    def test_duration_for_a_kind_without_default_duration_is_refused(self, extra: ActionKind) -> None:
        """話す・待つ・移動する・モンスターを攻撃するの長さを書くと、読まれない値なので ActionDurationNotApplicableException を投げる。"""
        durations = _durations() | {extra: Ticks(1)}

        with pytest.raises(ActionDurationNotApplicableException):
            _rules(durations)

    def test_changing_the_passed_mapping_later_does_not_change_the_rules(self) -> None:
        """作ったあとに渡した dict を書き換えても、WorldRules の長さは変わらない。"""
        durations = _durations()
        rules = _rules(durations)

        durations[ActionKind.PICK_UP] = Ticks(9)

        assert rules.action_durations[ActionKind.PICK_UP] == Ticks(1)
