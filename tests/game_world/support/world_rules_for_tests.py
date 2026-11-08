from __future__ import annotations

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
from ai_rpg_world.game_world.domain.value_object import FatigueAmount, HungerAmount, Multiplier, Probability, Ticks

_KINDS_WITHOUT_DEFAULT_DURATION = frozenset(
    {ActionKind.SPEAK, ActionKind.WAIT, ActionKind.TRAVEL, ActionKind.ATTACK_MONSTER}
)


def world_rules_for_tests() -> WorldRules:
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
        action_durations={kind: Ticks(1) for kind in frozenset(ActionKind) - _KINDS_WITHOUT_DEFAULT_DURATION},
    )
