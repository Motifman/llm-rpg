"""環境がエージェントへ渡す観測 (``Observation``) の欄の段と、経路ごとの必須欄を保証する。"""

from __future__ import annotations

import dataclasses
from typing import Any, get_args, get_type_hints

import pytest

from ai_rpg_world.being.contract import (
    KNOWN_IF_POSSIBLE_FIELDS,
    UNKNOWN,
    ContractViolation,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
    Unknown,
)


def _fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "body": "カイが言った: 「水場は北だ」",
        "route": ToldOrWritten(),
        "time": ObservedTime(display="一日目の朝 7:00", seconds=25200),
        "subject_is_self": False,
        "subject_name": "カイ",
        "source": "カイ",
        "place": "浜辺",
        "addressed_to_self": UNKNOWN,
    }
    fields.update(overrides)
    return fields


class TestRequiredFields:
    """必須の欄 (本文・経路・時刻・主体が本人か) が欠けた観測は作れないことを保証する。"""

    @pytest.mark.parametrize("missing", ["body", "route", "time", "subject_is_self"])
    def test_missing_required_field_cannot_be_constructed(self, missing: str) -> None:
        """必須の欄を 1 つでも省くと、観測の生成は TypeError で失敗する。"""
        fields = _fields()
        del fields[missing]

        with pytest.raises(TypeError):
            Observation(**fields)

    @pytest.mark.parametrize("body", ["", "   "])
    def test_blank_body_is_rejected(self, body: str) -> None:
        """本文が空や空白だけの観測は ContractViolation で拒む。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(body=body))

    def test_required_field_does_not_accept_unknown(self) -> None:
        """必須の「主体が本人か」に「不明」は渡せない。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(subject_is_self=UNKNOWN))

    def test_route_must_be_one_of_the_five_routes(self) -> None:
        """経路に 5 つの選択肢以外の値を渡すと ContractViolation で拒む。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(route="told"))


class TestKnownIfPossibleFields:
    """「分かるなら書く」の欄が「不明」を受け付け、空と区別されることを保証する。"""

    @pytest.mark.parametrize(
        "name", ["subject_name", "source", "place", "addressed_to_self"]
    )
    def test_omitting_known_if_possible_field_cannot_be_constructed(
        self, name: str
    ) -> None:
        """「分かるなら書く」の欄を省くと TypeError になる。書かないときは「不明」を明示する。"""
        fields = _fields()
        del fields[name]

        with pytest.raises(TypeError):
            Observation(**fields)

    @pytest.mark.parametrize("name", ["subject_name", "source", "place"])
    def test_unknown_is_accepted_and_reported_as_unknown(self, name: str) -> None:
        """名前の欄に「不明」を渡すと観測は作れ、unknown_fields にその欄名が入る。"""
        observation = Observation(**_fields(**{name: UNKNOWN}))

        assert getattr(observation, name) is UNKNOWN
        assert name in observation.unknown_fields()

    @pytest.mark.parametrize("name", ["subject_name", "source", "place"])
    @pytest.mark.parametrize("blank", ["", "  "])
    def test_blank_name_is_rejected_instead_of_meaning_unknown(
        self, name: str, blank: str
    ) -> None:
        """名前の欄に空文字を渡すと拒む。空を「不明」の代わりに使えない。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(**{name: blank}))

    def test_addressed_to_self_rejects_none(self) -> None:
        """「自分宛てか」に None を渡すと拒む。分からないときは「不明」を渡す。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(addressed_to_self=None))

    def test_fully_known_observation_has_no_unknown_fields(self) -> None:
        """4 つの欄をすべて埋めた観測は unknown_fields が空になる。"""
        observation = Observation(**_fields(addressed_to_self=True))

        assert observation.unknown_fields() == ()

    def test_unknown_fields_lists_every_unknown_in_declaration_order(self) -> None:
        """4 つとも「不明」なら、unknown_fields は宣言順に 4 つの欄名を返す。"""
        observation = Observation(
            **_fields(
                subject_name=UNKNOWN,
                source=UNKNOWN,
                place=UNKNOWN,
                addressed_to_self=UNKNOWN,
            )
        )

        assert observation.unknown_fields() == (
            "subject_name",
            "source",
            "place",
            "addressed_to_self",
        )


class TestOptionalAdvice:
    """任意の助言「起こしてほしいか」が書かなくてよい欄であることを保証する。"""

    def test_wants_wake_defaults_to_none(self) -> None:
        """「起こしてほしいか」を省くと None になり、「不明」の数にも入らない。"""
        observation = Observation(**_fields())

        assert observation.wants_wake is None
        assert "wants_wake" not in observation.unknown_fields()

    def test_wants_wake_rejects_unknown(self) -> None:
        """任意の助言に「不明」は渡せない。書かないときは省く。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(wants_wake=UNKNOWN))


class TestOwnActionResultRoute:
    """経路が「自分の行動の結果」のときだけ、呼び出しの ID と成否が必須になることを保証する。"""

    def test_own_action_result_requires_call_id_and_success(self) -> None:
        """呼び出しの ID か成否のどちらかを省くと「自分の行動の結果」は作れない。"""
        with pytest.raises(TypeError):
            OwnActionResult(call_id="call-1")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            OwnActionResult(succeeded=True)  # type: ignore[call-arg]

    def test_own_action_result_rejects_blank_call_id(self) -> None:
        """呼び出しの ID が空文字なら拒む。"""
        with pytest.raises(ContractViolation):
            OwnActionResult(call_id=" ", succeeded=True)

    def test_own_action_result_rejects_non_bool_success(self) -> None:
        """成否が bool でなければ拒む。"""
        with pytest.raises(ContractViolation):
            OwnActionResult(call_id="call-1", succeeded="ok")  # type: ignore[arg-type]

    def test_observation_carries_call_id_and_success_through_route(self) -> None:
        """「自分の行動の結果」の観測は、経路から呼び出しの ID と成否を読める。"""
        observation = Observation(
            **_fields(route=OwnActionResult(call_id="call-7", succeeded=False))
        )

        assert isinstance(observation.route, OwnActionResult)
        assert observation.route.call_id == "call-7"
        assert observation.route.succeeded is False

    @pytest.mark.parametrize(
        "route", [SeenOrHeard(), ToldOrWritten(), OwnBodyState(), EnvironmentNotice()]
    )
    def test_other_routes_have_no_call_id(self, route: object) -> None:
        """「自分の行動の結果」以外の経路は、呼び出しの ID を持たない。"""
        assert not hasattr(route, "call_id")


class TestObservedTime:
    """時刻が表示の文と、任意の比べられる数値 (秒) を持つことを保証する。"""

    def test_seconds_is_optional(self) -> None:
        """数値を省いた時刻は seconds が None になる。"""
        assert ObservedTime(display="夕方").seconds is None

    @pytest.mark.parametrize("display", ["", "  "])
    def test_blank_display_is_rejected(self, display: str) -> None:
        """表示の文が空なら拒む。"""
        with pytest.raises(ContractViolation):
            ObservedTime(display=display, seconds=0)

    @pytest.mark.parametrize("seconds", [True, "300", float("nan"), float("inf")])
    def test_non_numeric_seconds_is_rejected(self, seconds: object) -> None:
        """秒に bool・文字列・非有限の数を渡すと拒む。"""
        with pytest.raises(ContractViolation):
            ObservedTime(display="朝", seconds=seconds)  # type: ignore[arg-type]


class TestClosedContract:
    """観測の欄が契約で閉じていて、環境が欄を足したり後から書き換えたりできないことを保証する。"""

    def test_fields_are_exactly_the_contract(self) -> None:
        """観測の欄は、必須 4・分かるなら書く 4・任意の助言 1・主体を知らない受け手向けの本文 1 の 10 個だけである。"""
        names = {f.name for f in dataclasses.fields(Observation)}

        assert names == {
            "body", "route", "time", "subject_is_self",
            "subject_name", "source", "place", "addressed_to_self",
            "wants_wake", "body_if_subject_unknown",
        }

    def test_unexpected_field_cannot_be_added(self) -> None:
        """契約に無い欄を渡すと、観測の生成は TypeError で失敗する。"""
        with pytest.raises(TypeError):
            Observation(**_fields(mood="嬉しい"))

    def test_observation_cannot_be_rewritten(self) -> None:
        """作った観測の欄に代入すると FrozenInstanceError になる。"""
        observation = Observation(**_fields())

        with pytest.raises(dataclasses.FrozenInstanceError):
            observation.place = "洞窟"  # type: ignore[misc]

    def test_known_if_possible_fields_match_annotations_that_accept_unknown(self) -> None:
        """「分かるなら書く」の欄の一覧は、注釈が「不明」を受け付ける欄とちょうど一致する。"""
        hints = get_type_hints(Observation)
        accepts_unknown = tuple(
            f.name
            for f in dataclasses.fields(Observation)
            if any(Unknown.UNKNOWN in get_args(arg) for arg in get_args(hints[f.name]))
        )

        assert KNOWN_IF_POSSIBLE_FIELDS == accepts_unknown
        assert len(accepts_unknown) == 4


class TestBodyIfSubjectUnknown:
    """話し手を知らない受け手向けの本文を、話し手が分かる観測にだけ持たせられることを保証する。"""

    def test_body_if_subject_unknown_defaults_to_none(self) -> None:
        """省けば None で、話し手を知っているかで描き方が変わらない観測になる。"""
        assert Observation(**_fields()).body_if_subject_unknown is None

    def test_body_if_subject_unknown_is_kept(self) -> None:
        """名前を伏せた本文を渡すと、そのまま読める。"""
        observation = Observation(**_fields(body_if_subject_unknown="誰かが言った: 「水場は北だ」"))

        assert observation.body_if_subject_unknown == "誰かが言った: 「水場は北だ」"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"body_if_subject_unknown": " "},
            {"body_if_subject_unknown": "誰かが言った", "subject_name": UNKNOWN},
            {"body_if_subject_unknown": "誰かが言った", "subject_is_self": True},
        ],
        ids=["blank", "unknown_subject", "self_subject"],
    )
    def test_body_if_subject_unknown_needs_a_known_other_subject(self, overrides) -> None:
        """空の本文、話し手が不明な観測、自分が主体の観測には持たせられない (ContractViolation)。"""
        with pytest.raises(ContractViolation):
            Observation(**_fields(**overrides))
