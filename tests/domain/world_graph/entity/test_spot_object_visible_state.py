"""Phase 4-E: SpotObject.visible_state が hidden_state_keys を除外することを検証する。

第三者プロンプトに「trap_armed」のような仕掛け値が漏れないようにするための
静的 visibility 属性。effect の visibility (HIDDEN) とは独立。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_object import (
    VISIBLE_STATE_TAGS_KEY,
    SpotObject,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotObjectValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
)


def _make(
    state: dict,
    hidden: frozenset = frozenset(),
    unavailable_hint: str | None = None,
    state_display: tuple[StateDisplayRule, ...] = (),
) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="燭台",
        description="",
        object_type=SpotObjectTypeEnum.OTHER,
        state=state,
        interactions=(),
        hidden_state_keys=hidden,
        unavailable_hint=unavailable_hint,
        state_display=state_display,
    )


class TestVisibleState:
    """SpotObject.visible_state が prompt に出してよい状態だけを返す挙動を保証する。"""

    def test_returns_full_state_by_default(self) -> None:
        """hidden_state_keys が空なら全キーを返す。"""
        obj = _make({"lit": True, "fuel": 5})
        assert obj.visible_state() == {"lit": True, "fuel": 5}

    def test_excludes_hidden_keys(self) -> None:
        """hidden_state_keys に列挙されたキーは visible_state から除外される。"""
        obj = _make(
            state={"lit": True, "trap_armed": True, "secret": "answer"},
            hidden=frozenset({"trap_armed", "secret"}),
        )
        assert obj.visible_state() == {"lit": True}

    def test_does_not_mutate_original_state(self) -> None:
        """visible_state() は元の state を破壊しない (重要: effect 適用は state 全体を見る)。"""
        original = {"lit": True, "trap_armed": True}
        obj = _make(state=original, hidden=frozenset({"trap_armed"}))
        _ = obj.visible_state()
        # オブジェクト自身の state は影響を受けない
        assert obj.state == {"lit": True, "trap_armed": True}
        # 元の dict も mutate されない
        assert original == {"lit": True, "trap_armed": True}

    def test_hides_available_when_true(self) -> None:
        """available=true は正常状態なので prompt 用 state には表示しない。"""
        obj = _make({"available": True, "opened": False})

        assert obj.visible_state() == {"opened": False}

    def test_renders_available_false_as_recovery_hint(self) -> None:
        """available=false は生 boolean でなく、中立の復帰ヒントへ変換する。"""
        obj = _make({"available": False, "opened": True})

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は採れない・時間を置けば戻る",),
            "opened": True,
        }

    def test_uses_author_defined_unavailable_hint(self) -> None:
        """unavailable_hint があれば、available=false の表示に作者指定文を使う。"""
        obj = _make(
            {"available": False},
            unavailable_hint="今は汲めない・時間を置けば戻る",
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は汲めない・時間を置けば戻る",)
        }

    def test_hides_last_harvest_tick(self) -> None:
        """last_harvest_tick は再生判定用の内部 tick なので prompt 用 state には表示しない。"""
        obj = _make({"available": False, "last_harvest_tick": 42})

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は採れない・時間を置けば戻る",)
        }

    def test_rejects_empty_unavailable_hint(self) -> None:
        """unavailable_hint が空白だけなら、次の一手が読める表示にならないため拒否する。"""
        with pytest.raises(SpotObjectValidationException):
            _make({"available": False}, unavailable_hint="  ")

    def test_state_display_rule_renders_matching_value_as_tag(self) -> None:
        """state_display に key/value が一致する rule があれば、生値ではなく作者文言だけを表示する。"""
        obj = _make(
            {"opened": False},
            state_display=(
                StateDisplayRule("opened", False, "蓋は閉じたまま"),
            ),
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("蓋は閉じたまま",)
        }

    def test_state_display_value_mismatch_remains_raw(self) -> None:
        """key に rule があっても現在値に対応する rule が無ければ、生値を残して宣言漏れを見える化する。"""
        obj = _make(
            {"opened": True},
            state_display=(
                StateDisplayRule("opened", False, "蓋は閉じたまま"),
            ),
        )

        assert obj.visible_state() == {"opened": True}

    def test_state_display_exact_match_wins_over_at_least_rule(self) -> None:
        """完全一致と at_least が同時に該当する値は、具体的な完全一致文を表示する。"""
        obj = _make(
            {"count": 3},
            state_display=(
                StateDisplayRule("count", 3, "ちょうど 3 個ある"),
                StateDisplayRule(
                    "count", None, "3 個以上ある", at_least=3
                ),
            ),
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("ちょうど 3 個ある",)
        }

    def test_state_display_uses_largest_matching_at_least_threshold(self) -> None:
        """完全一致が無い整数値は、該当する at_least のうち最大閾値の文を表示する。"""
        obj = _make(
            {"count": 6},
            state_display=(
                StateDisplayRule("count", None, "3 個以上ある", at_least=3),
                StateDisplayRule("count", None, "5 個以上ある", at_least=5),
            ),
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("5 個以上ある",)
        }

    def test_state_display_without_matching_at_least_rule_remains_raw(self) -> None:
        """完全一致も at_least も該当しない値は、生値を残して宣言漏れを見える化する。"""
        obj = _make(
            {"count": -1},
            state_display=(
                StateDisplayRule("count", None, "3 個以上ある", at_least=3),
            ),
        )

        assert obj.visible_state() == {"count": -1}

    def test_state_display_at_least_does_not_treat_bool_as_int(self) -> None:
        """bool state は int の一種として at_least に一致させず、生値で宣言漏れを示す。"""
        obj = _make(
            {"count": True},
            state_display=(
                StateDisplayRule("count", None, "1 個以上ある", at_least=1),
            ),
        )

        assert obj.visible_state() == {"count": True}

    def test_state_display_for_available_overrides_legacy_unavailable_hint(self) -> None:
        """available に明示 rule があれば、unavailable_hint より作者の state_display を優先する。"""
        obj = _make(
            {"available": False},
            unavailable_hint="今は採れない・時間を置けば戻る",
            state_display=(
                StateDisplayRule("available", False, "貝は採り尽くされている"),
            ),
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("貝は採り尽くされている",)
        }

    def test_hidden_state_key_suppresses_state_display_rule(self) -> None:
        """hidden_state_keys に含まれる key は、state_display rule があっても第三者 prompt に出さない。"""
        obj = _make(
            {"read": False},
            hidden=frozenset({"read"}),
            state_display=(
                StateDisplayRule("read", False, "まだ読まれていない"),
            ),
        )

        assert obj.visible_state() == {}

    def test_bool_state_display_rule_does_not_match_zero_or_one(self) -> None:
        """False/True 用 rule は、Python の等価性に引きずられて 0/1 の数値 state に当たらない。"""
        obj = _make(
            {"count": 0, "switch": 1},
            state_display=(
                StateDisplayRule("count", False, "数値 0 を false と誤認した"),
                StateDisplayRule("switch", True, "数値 1 を true と誤認した"),
            ),
        )

        assert obj.visible_state() == {"count": 0, "switch": 1}
