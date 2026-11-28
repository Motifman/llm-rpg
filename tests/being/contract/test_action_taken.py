"""環境が呼び出し 1 つに返す「その行動をどう行ったか」(``ActionTaken``) の欄を保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import (
    ActionTaken,
    ContractViolation,
    ObservedTime,
    OccurrenceOrder,
    PersonInText,
    TextWithPeople,
)

_TIME = ObservedTime(display="1 日目 06:00")
_TO_SAYO = TextWithPeople(
    template="「{target}」に囁いた",
    people={"target": PersonInText(handle=2, appearance="髪を結った娘", visible_name="サヨ")},
)


class TestActionTaken:
    """ActionTaken が、呼び出しの ID・要約・通ったか・時刻・起きた順を持ち、要約の人の穴を呼び名で埋めることを保証する。"""

    def test_summary_may_be_absent(self) -> None:
        """環境が要約を組み立てられなかったときは、要約を None で持てる。"""
        taken = ActionTaken(call_id="call-1", action_summary=None, accepted=True, time=_TIME)

        assert (taken.action_summary, taken.order) == (None, None)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("call_id", " "), ("action_summary", " "), ("accepted", "yes"), ("time", "朝"), ("order", 3.0)],
    )
    def test_invalid_field_is_rejected(self, field: str, value: object) -> None:
        """空の呼び出しの ID や要約、真偽値でない accepted、型の違う時刻や順を渡すと ContractViolation で拒む。"""
        fields: dict[str, object] = {"call_id": "call-1", "action_summary": "待った", "accepted": True, "time": _TIME}
        fields[field] = value

        with pytest.raises(ContractViolation):
            ActionTaken(**fields)  # type: ignore[arg-type]

    def test_people_in_the_summary_are_named(self) -> None:
        """要約が人の穴つきの文のとき、呼び名で埋めると「「サヨ」に囁いた」になり、ほかの欄は変わらない。"""
        order = OccurrenceOrder(environment="廃坑の山村", value=1.0)
        taken = ActionTaken(call_id="call-1", action_summary=_TO_SAYO, accepted=True, time=_TIME, order=order)

        named = taken.with_people_named(lambda text: text.template.replace("{target}", "サヨ"))

        assert named == ActionTaken(
            call_id="call-1", action_summary="「サヨ」に囁いた", accepted=True, time=_TIME, order=order
        )

    def test_summary_with_people_placeholders_cannot_be_read_as_text(self) -> None:
        """人の穴が残った要約を文として読むと ContractViolation を投げる。"""
        taken = ActionTaken(call_id="call-1", action_summary=_TO_SAYO, accepted=True, time=_TIME)

        with pytest.raises(ContractViolation):
            taken.summary_text()
