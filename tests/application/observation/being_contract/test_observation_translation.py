"""ゲームの観測と行動結果を、契約の観測 (``Observation``) へ変換する規則を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.being_contract import (
    NotRepresentableReason,
    ObservationNotRepresentable,
    Observer,
    observation_from_action_result,
    observation_from_game,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationCategory,
    ObservationOutput,
)
from ai_rpg_world.being.contract import (
    UNKNOWN,
    EnvironmentNotice,
    ObservedTime,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_NOAH = Observer(
    player_id=PlayerId.create(2),
    name="ノア",
    place_name="浜辺",
    seconds_per_tick=300,
)


def _output(
    structured: dict[str, Any],
    *,
    category: ObservationCategory = "social",
    schedules_turn: bool = False,
    prose: str | None = None,
) -> ObservationOutput:
    """``prose`` を省くと、構造化データの文字列をすべて含む本文にする (名前を伏せない観測)。"""
    if prose is None:
        prose = "、".join(v for v in structured.values() if isinstance(v, str)) + "。"
    return ObservationOutput(
        prose=prose,
        structured=structured,
        observation_category=category,
        schedules_turn=schedules_turn,
    )


def _translate(output: ObservationOutput, observer: Observer = _NOAH) -> Any:
    return observation_from_game(
        output, tick=12, game_time_label="一日目の朝 1:00", observer=observer
    )


def _speech(channel: str = "say", **extra: Any) -> dict[str, Any]:
    return {
        "type": "player_spoke",
        "speaker": "カイ",
        "speaker_player_id": 4,
        "channel": channel,
        "content": "水場は北だ",
        "role": "other",
        **extra,
    }


class TestSubjectFromRole:
    """``role`` から「主体が本人か」と主体の名前を決める規則を保証する。"""

    def test_speech_of_another_player_has_speaker_as_subject_and_source(self) -> None:
        """role が other の発言は、主体が本人でなく、主体の名前と情報源に話者名が入り、経路は「言われた」になる。"""
        observation = _translate(
            _output(_speech(), schedules_turn=True, prose="カイが言った: 「水場は北だ」")
        )

        assert observation.subject_is_self is False
        assert observation.subject_name == "カイ"
        assert observation.source == "カイ"
        assert isinstance(observation.route, ToldOrWritten)
        assert observation.body == "カイが言った: 「水場は北だ」"

    def test_self_role_makes_subject_self(self) -> None:
        """role が self の観測は、主体が本人になり、主体の名前に本人の名前が入る。"""
        observation = _translate(
            _output({"type": "player_downed", "role": "self"}, category="self_only")
        )

        assert observation.subject_is_self is True
        assert observation.subject_name == "ノア"
        assert isinstance(observation.route, OwnBodyState)

    def test_actor_with_own_name_is_self(self) -> None:
        """role が無くても、行為者の名前が本人の名前なら主体は本人になる。"""
        observation = _translate(_output({"type": "spot_explored", "actor": "ノア"}))

        assert observation.subject_is_self is True

    def test_actor_hidden_from_prose_is_not_revealed(self) -> None:
        """構造化データに行為者があっても本文が伏せていれば、主体の名前は「不明」になる。"""
        observation = _translate(
            _output(
                {"type": "spot_public_effect_observed", "actor_name": "クゼ"},
                category="environment",
                prose="集会室の雰囲気が変わった。",
            )
        )

        assert observation.subject_name is UNKNOWN
        assert observation.subject_is_self is False

    def test_environment_event_without_actor_has_unknown_subject(self) -> None:
        """行為者を持たない環境の出来事は、主体が本人でなく、主体の名前が「不明」になる。"""
        observation = _translate(
            _output({"type": "weather_changed"}, category="environment")
        )

        assert observation.subject_is_self is False
        assert observation.subject_name is UNKNOWN


class TestWantsWake:
    """``schedules_turn`` を「起こしてほしいか」へ写す規則を保証する。"""

    def test_schedules_turn_true_means_wants_wake(self) -> None:
        """schedules_turn=True の観測は、起こしてほしいかが True になる。"""
        assert _translate(_output(_speech(), schedules_turn=True)).wants_wake is True

    def test_schedules_turn_false_means_does_not_want_wake(self) -> None:
        """schedules_turn=False の観測は、起こしてほしいかが False になり、省略と区別される。"""
        assert _translate(_output(_speech(), schedules_turn=False)).wants_wake is False


class TestRoute:
    """``observation_category`` と観測の種類から経路を決める規則を保証する。"""

    @pytest.mark.parametrize(
        ("structured", "category", "route_type"),
        [
            ({"type": "entity_entered_spot", "actor": "カイ", "spot_name": "浜辺"}, "social", SeenOrHeard),
            ({"type": "item_added_to_inventory", "item_name": "貝"}, "self_only", OwnBodyState),
            ({"type": "scenario_event", "message": "鐘が鳴った"}, "environment", EnvironmentNotice),
            ({"type": "game_phase_changed", "initiator_display_name": "モリ"}, "social", EnvironmentNotice),
            ({"type": "meeting_vote_cast", "voter_display_name": "モリ"}, "social", EnvironmentNotice),
            ({"type": "weather_changed"}, "environment", SeenOrHeard),
            ({"type": "time_of_day_changed"}, "environment", SeenOrHeard),
            ({"kind": "player_revived_post_hoc"}, "self_only", OwnBodyState),
        ],
    )
    def test_route_is_decided_by_type_then_category(
        self,
        structured: dict[str, Any],
        category: ObservationCategory,
        route_type: type,
    ) -> None:
        """種類ごとの上書きがあればそれを、無ければ observation_category の既定を経路にする。"""
        observation = _translate(_output(structured, category=category))

        assert isinstance(observation.route, route_type)

    def test_monster_attack_on_self_is_own_body_state(self) -> None:
        """自分が標的のモンスターの攻撃は「自分の体の状態」になり、自分宛てになる。"""
        observation = _translate(
            _output(
                {"type": "monster_attacked_player", "monster_name": "大型カニ", "target_player_id": 2}
            )
        )

        assert isinstance(observation.route, OwnBodyState)
        assert observation.subject_name == "大型カニ"
        assert observation.subject_is_self is False
        assert observation.addressed_to_self is True

    def test_monster_attack_on_another_is_seen(self) -> None:
        """他人が標的のモンスターの攻撃は「見た・聞いた」になり、自分宛てでない。"""
        observation = _translate(
            _output(
                {"type": "monster_attacked_player", "monster_name": "大型カニ", "target_player_id": 4}
            )
        )

        assert isinstance(observation.route, SeenOrHeard)
        assert observation.addressed_to_self is False

    @pytest.mark.parametrize(
        "structured",
        [
            {"type": "goal_reflect", "verdict": "stalled"},
            {"type": "goal_revision"},
            {"loop_guard": True, "tool_name": "wait"},
        ],
    )
    def test_being_inner_records_are_not_representable(
        self, structured: dict[str, Any]
    ) -> None:
        """目的の振り返り・改訂とループ警告は、環境からの観測ではないので変換を拒む。"""
        with pytest.raises(ObservationNotRepresentable) as raised:
            _translate(_output(structured, category="self_only"))

        assert raised.value.reason is NotRepresentableReason.BEING_INNER_RECORD

    def test_blank_prose_is_not_representable(self) -> None:
        """目撃文との重複を避けて本文を空にした観測は、必須の本文が無いので変換を拒む。"""
        with pytest.raises(ObservationNotRepresentable) as raised:
            _translate(_output({"type": "player_downed", "actor": "モリ"}, prose=""))

        assert raised.value.reason is NotRepresentableReason.EMPTY_BODY


class TestKnownIfPossibleFields:
    """情報源・場所・自分宛てかを、分かるときだけ埋める規則を保証する。"""

    def test_whisper_is_addressed_to_self(self) -> None:
        """囁きは相手にしか届かないので、自分宛てになる。"""
        assert _translate(_output(_speech("whisper"))).addressed_to_self is True

    def test_say_has_unknown_addressee(self) -> None:
        """場の全員に届く発言は、自分宛てかが「不明」になる。"""
        assert _translate(_output(_speech("say"))).addressed_to_self is UNKNOWN

    def test_interaction_reports_whether_self_is_target(self) -> None:
        """対人行為は is_target から自分宛てかを決める。"""
        observation = _translate(
            _output({"type": "player_interacted_with_player", "actor": "カイ", "is_target": True})
        )

        assert observation.addressed_to_self is True

    def test_first_hand_perception_has_self_as_source(self) -> None:
        """「見た・聞いた」の観測は、情報源が本人になる。"""
        observation = _translate(_output({"type": "spot_explored", "actor": "カイ"}))

        assert observation.source == "ノア"

    def test_environment_notice_has_unknown_source_and_place(self) -> None:
        """環境からの知らせは、情報源と場所が「不明」になる。"""
        observation = _translate(
            _output({"type": "player_outcome_resolved", "label": "脱落"}, category="environment")
        )

        assert observation.source is UNKNOWN
        assert observation.place is UNKNOWN

    def test_place_defaults_to_where_the_observer_is(self) -> None:
        """出来事の場所が観測に書かれていなければ、観測者がいる場所を場所にする。"""
        assert _translate(_output(_speech())).place == "浜辺"

    def test_place_written_in_the_event_wins(self) -> None:
        """隣の場所から聞こえた発言は、その隣の場所を場所にする。"""
        observation = _translate(_output(_speech(source_adjacent_spot_name="岩場")))

        assert observation.place == "岩場"

    def test_adjacent_place_hidden_from_prose_is_unknown(self) -> None:
        """隣の場所から聞こえた発言でも、本文がその場所を書いていなければ場所は「不明」になる。"""
        observation = _translate(
            _output(
                _speech(source_adjacent_spot_name="岩場"),
                prose="どこからかカイの声が聞こえた: 「水場は北だ」",
            )
        )

        assert observation.place is UNKNOWN

    def test_entered_spot_uses_the_spot_name(self) -> None:
        """誰かが入ってきた観測は、入った場所を場所にする。"""
        observation = _translate(
            _output({"type": "entity_entered_spot", "actor": "カイ", "spot_name": "洞窟"})
        )

        assert observation.place == "洞窟"

    def test_unknown_observer_place_becomes_unknown(self) -> None:
        """観測者の居場所が分からず、観測にも場所が無ければ、場所は「不明」になる。"""
        observer = Observer(
            player_id=PlayerId.create(2), name="ノア", place_name=None, seconds_per_tick=300
        )

        assert _translate(_output(_speech()), observer).place is UNKNOWN


class TestTime:
    """世界の tick と時刻のラベルを、時刻の数値 (秒) と表示の文へ写す規則を保証する。"""

    def test_tick_becomes_seconds_and_label_becomes_display(self) -> None:
        """tick 12 は 1 tick 300 秒の世界で 3600 秒になり、ラベルが表示の文になる。"""
        observation = _translate(_output(_speech()))

        assert observation.time == ObservedTime(display="一日目の朝 1:00", seconds=3600)

    def test_seconds_is_none_when_tick_length_is_unknown(self) -> None:
        """1 tick の長さが分からない世界では、数値を省いて表示の文だけにする。"""
        observer = Observer(
            player_id=PlayerId.create(2), name="ノア", place_name="浜辺", seconds_per_tick=None
        )

        assert _translate(_output(_speech()), observer).time.seconds is None

    def test_missing_time_label_is_rejected(self) -> None:
        """時刻のラベルが無い観測は、必須の時刻を埋められないので変換を拒む。"""
        with pytest.raises(ObservationNotRepresentable) as raised:
            observation_from_game(
                _output(_speech()), tick=12, game_time_label=None, observer=_NOAH
            )

        assert raised.value.reason is NotRepresentableReason.MISSING_TIME_LABEL


class TestActionResult:
    """ツールの結果を、経路「自分の行動の結果」の観測へ変換する規則を保証する。"""

    def _entry(self, **overrides: Any) -> ActionResultEntry:
        fields: dict[str, Any] = {
            "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "action_summary": "通信室へ移動しようとした",
            "result_summary": "通路が塞がっていて進めない。",
            "success": False,
            "error_code": "CONNECTION_BLOCKED",
            "tool_name": "travel_to",
            "game_time_label": "一日目の朝 0:10",
            "occurred_tick": 2,
        }
        fields.update(overrides)
        return ActionResultEntry(**fields)

    def test_failed_result_has_call_id_and_failure(self) -> None:
        """失敗したツールの結果は、成否が失敗で、渡した呼び出しの ID が付いた観測になる。"""
        observation = observation_from_action_result(
            self._entry(), call_id="call-9", observer=_NOAH
        )

        assert observation.route == OwnActionResult(call_id="call-9", succeeded=False)
        assert observation.body == "通路が塞がっていて進めない。"

    def test_result_is_about_self_and_addressed_to_self(self) -> None:
        """ツールの結果は、主体も情報源も本人で、自分宛てになる。"""
        observation = observation_from_action_result(
            self._entry(success=True), call_id="call-9", observer=_NOAH
        )

        assert observation.subject_is_self is True
        assert observation.subject_name == "ノア"
        assert observation.source == "ノア"
        assert observation.addressed_to_self is True
        assert observation.place == "浜辺"
        assert observation.time == ObservedTime(display="一日目の朝 0:10", seconds=600)

    def test_reschedule_flag_becomes_wants_wake(self) -> None:
        """should_reschedule の値が、そのまま起こしてほしいかになる。"""
        observation = observation_from_action_result(
            self._entry(should_reschedule=True), call_id="call-9", observer=_NOAH
        )

        assert observation.wants_wake is True

    def test_result_without_time_label_is_not_representable(self) -> None:
        """時刻のラベルが無いツールの結果は、必須の時刻を埋められないので変換を拒む。"""
        with pytest.raises(ObservationNotRepresentable) as raised:
            observation_from_action_result(
                self._entry(game_time_label=None), call_id="call-9", observer=_NOAH
            )

        assert raised.value.reason is NotRepresentableReason.MISSING_TIME_LABEL

    def test_blank_result_summary_falls_back_to_action_summary(self) -> None:
        """結果の文が空なら、行動の要約を本文にする。"""
        observation = observation_from_action_result(
            self._entry(result_summary=""), call_id="call-9", observer=_NOAH
        )

        assert observation.body == "通信室へ移動しようとした"
