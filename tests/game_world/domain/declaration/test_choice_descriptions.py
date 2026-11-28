"""ChoiceDescriptions が、行動の種類ごとのツールの説明を、介抱だけは世界の規則の値を埋めて返し、書けない説明を読み込みで断ることを保証する。"""

from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.game_world.domain.action.offered_action import ActionChoiceKind
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import Rate, Ticks
from tests.game_world.support.world_design_for_tests import choice_descriptions, half_hour_ticks_from_midnight
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests


def _rules(tend: TendRule | NoTending, grace: int = 30) -> WorldRules:
    return dataclasses.replace(world_rules_for_tests(), tend=tend, death=DeathRule(grace=Ticks(grace)))


class TestDescriptionOf:
    """ChoiceDescriptions.description_of が、介抱の説明に起こしたときの HP の率と、倒れてから死ぬまでの時間を埋めることを保証する。"""

    def test_other_kinds_return_their_text_as_written(self) -> None:
        """行く (travel_to) は、書いた説明「行く。」をそのまま返す。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TRAVEL_TO, _rules(TendRule(Rate(0.6))), half_hour_ticks_from_midnight()
        )

        assert text == "行く。"

    def test_tending_fills_the_rate_and_the_hours_before_death(self) -> None:
        """1 日 48 tick の世界で、起こしたときの率 0.6・死ぬまで 30 tick なら、「60% で戻り、15 時間ほど で死ぬ。」になる。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TEND_TO_PLAYER, _rules(TendRule(Rate(0.6))), half_hour_ticks_from_midnight()
        )

        assert text == "60% で戻り、15 時間ほど で死ぬ。"

    def test_less_than_an_hour_is_told_in_minutes(self) -> None:
        """死ぬまで 1 tick (30 分) なら、時間ではなく「30 分ほど」と書く。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TEND_TO_PLAYER, _rules(TendRule(Rate(0.6)), grace=1), half_hour_ticks_from_midnight()
        )

        assert text == "60% で戻り、30 分ほど で死ぬ。"

    @pytest.mark.parametrize(("grace", "hours"), [(2, "1 時間ほど"), (3, "2 時間ほど"), (5, "3 時間ほど")])
    def test_hours_are_rounded_half_up(self, grace: int, hours: str) -> None:
        """1 日 48 tick の世界で死ぬまで 60 分・90 分・150 分なら、30 分を切り上げて「1 時間ほど」「2 時間ほど」「3 時間ほど」と書く。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TEND_TO_PLAYER, _rules(TendRule(Rate(0.6)), grace=grace), half_hour_ticks_from_midnight()
        )

        assert text == f"60% で戻り、{hours} で死ぬ。"

    def test_world_without_day_night_counts_turns(self) -> None:
        """昼夜の無い世界では、死ぬまでを tick の数で「30 ターンぶんほど」と書く。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TEND_TO_PLAYER, _rules(TendRule(Rate(0.6))), NoDayNight()
        )

        assert text == "60% で戻り、30 ターンぶんほど で死ぬ。"

    def test_world_without_tending_says_it_cannot_be_done(self) -> None:
        """介抱の無い世界では、介抱の説明は「介抱はできない。」になる。"""
        text = choice_descriptions().description_of(
            ActionChoiceKind.TEND_TO_PLAYER, _rules(NoTending()), half_hour_ticks_from_midnight()
        )

        assert text == "介抱はできない。"


class TestRefusedDescriptions:
    """ChoiceDescriptions が、説明の欠けた種類や、埋められない名前を書いた説明を断ることを保証する。"""

    def test_missing_kind_is_refused(self) -> None:
        """行く (travel_to) の説明が無いと、ValueOutOfRangeException を投げる。"""
        by_choice = dict(choice_descriptions().by_choice)
        del by_choice["travel_to"]

        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(choice_descriptions(), by_choice=by_choice)

    @pytest.mark.parametrize(
        ("kind", "text"),
        [
            ("travel_to", "{revive_percent}% で行く。"),
            ("tend_to_player", "{revive_percent}% で戻る。"),
            ("wait", " "),
            ("wait", "待つ"),
        ],
    )
    def test_text_writing_the_wrong_names_is_refused(self, kind: str, text: str) -> None:
        """介抱でない説明に率を書く・介抱の説明に死ぬまでの時間を書かない・空の説明・「。」で終わらない説明は、ValueOutOfRangeException を投げる。"""
        by_choice = dict(choice_descriptions().by_choice) | {kind: text}

        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(choice_descriptions(), by_choice=by_choice)

    @pytest.mark.parametrize(
        ("field", "text"),
        [
            ("tend_without_tending", "介抱はできない"),
            ("closing", "行動を 1 つ選んでください"),
            ("closing", "{tool} を 1 つ選んでください。"),
            ("duration_hours", "{minutes} 分ほど"),
            ("duration_turns", "ほど"),
        ],
    )
    def test_extra_text_writing_the_wrong_names_is_refused(self, field: str, text: str) -> None:
        """介抱の無い世界の説明や締めの一文が「。」で終わらない・締めの一文に名前を書く・時間の言い回しに別の名前を書く・名前を書かないと、ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(choice_descriptions(), **{field: text})  # type: ignore[arg-type]
