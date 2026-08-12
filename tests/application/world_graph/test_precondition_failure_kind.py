"""前提条件の失敗を、シナリオ宣言から区分する。

## なぜこの試験が要るか

`interact` の失敗 remediation は、**シナリオ作者が書いた自由文**を日本語キーワードで
部分一致検索して切り替えていた。

    _INTERACTION_EXHAUST_HINTS = ("採り尽く", "枯渇", "もう空", "もう開い",
                                  "すでに", "今は", "燃え上が")

`failure_message` は「エージェントに読ませる文」として書かれているのに、**分類キー
としても二重に使われていた**。作者は自分の言い回しがシステムの分岐を変えることを
知らない。「集めた」を「採り尽くした」に直すだけで挙動が変わる。

## 実測: 当たっても外れても害だった

実 run 43 本の `INTERACTION_PRECONDITION_FAILED` 679 件を区分ごとに数えた。

    時間で回復  251 件 ... うちキーワード当たり  31 件 (**当たった 31 件は全部誤り**)
    前提不足    216 件 ... 当たらず (正しい)
    恒久的      154 件 ... うち当たり 43 件 (28%)
    照合できず   62 件 ... 引数不足 / クールダウン / 対人 action (別経路)

「時間で回復」251 件のうち当たるのは 12% だけで、**当たった 31 件はすべて誤った助言**
だった。「同じ object に再試行しても結果は変わらない。別の場所を選べ」と返すが、
実際は待てば回復する。作者は `failure_message` に「風がまた運んでくるのを待つしか
ない」と書いているのに、システムがその上から「待つな」を重ねていた。

実 run で同じ壁に **96 回**当たった例がこの形である。

## 区分は宣言から導ける

キーワードは要らない。失敗した条件と `reactive_bindings` を突き合わせれば決まる。

    失敗条件:  OBJECT_STATE / fallen_leaves / {"available": True} を要求
    binding :  OBJECT_STATE_TICK_AT_LEAST(fallen_leaves, last_harvest_tick, +24)
               → on_true_state_updates {"available": True}

**同じ物体・同じ state_key・要求値と一致**を時間述語が戻すなら「時間で回復」。
戻す binding が無ければ「恒久的」。`OBJECT_STATE` でなければ「前提不足」。
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.world_graph.precondition_failure_kind import (
    PreconditionFailureKind,
    classify_precondition_failure,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_LEAVES = SpotObjectId.create(7)
_ROCK = SpotObjectId.create(8)


def _object_state_condition(
    object_id: SpotObjectId, key: str, value: Any
) -> InteractionCondition:
    return InteractionCondition(
        condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
        target_object_id=object_id,
        required_state={key: value},
        failure_message="ここの枯れ葉はもう集めた。",
    )


def _time_binding(
    object_id: SpotObjectId, key: str, value: Any, *, offset: int = 24
) -> ReactiveObjectStateBinding:
    """時間経過でその state を戻す binding。"""
    return ReactiveObjectStateBinding(
        target_object_id=object_id,
        predicate=ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=object_id.value,
            state_key="last_harvest_tick",
            ticks_offset=offset,
        ),
        on_true_state_updates=((key, value),),
        on_false_state_updates=((key, not value if isinstance(value, bool) else value),),
    )


def _flag_binding(
    object_id: SpotObjectId, key: str, value: Any
) -> ReactiveObjectStateBinding:
    """フラグ (時間ではない) でその state を戻す binding。"""
    return ReactiveObjectStateBinding(
        target_object_id=object_id,
        predicate=ScenarioEventCondition(
            condition_type="FLAG_SET", flag_name="switch_on"
        ),
        on_true_state_updates=((key, value),),
        on_false_state_updates=(),
    )


class TestTimeRecoveringFailuresAreRecognised:
    """時間で戻る状態は「待てば回復」と区分される。"""

    def test_a_time_predicate_restoring_the_required_value_is_time_recovering(
        self,
    ) -> None:
        """要求値を時間述語が戻すなら TIME_RECOVERING。

        96 回反復した実例がこの形。`fallen_leaves` の ``{"available": True}`` を
        ``OBJECT_STATE_TICK_AT_LEAST`` の binding が戻す。
        """
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True),
            bindings=(_time_binding(_LEAVES, "available", True),),
        )

        assert kind is PreconditionFailureKind.TIME_RECOVERING

    def test_a_binding_on_another_object_does_not_count(self) -> None:
        """別の物体を戻す binding では「待てば回復」にならない。

        物体の照合を落とすと、どこかに時間 binding があるだけで全部が
        「待て」になる。
        """
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True),
            bindings=(_time_binding(_ROCK, "available", True),),
        )

        assert kind is PreconditionFailureKind.PERMANENT

    def test_a_binding_on_another_state_key_does_not_count(self) -> None:
        """別の state_key を戻す binding では「待てば回復」にならない。"""
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True),
            bindings=(_time_binding(_LEAVES, "wetness", True),),
        )

        assert kind is PreconditionFailureKind.PERMANENT

    def test_a_binding_restoring_a_different_value_does_not_count(self) -> None:
        """要求値と違う値を書く binding では「待てば回復」にならない。

        ``available: False`` へ倒す binding しか無いなら、待っても要求は満たされない。
        """
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True),
            bindings=(
                ReactiveObjectStateBinding(
                    target_object_id=_LEAVES,
                    predicate=ScenarioEventCondition(
                        condition_type="OBJECT_STATE_TICK_AT_LEAST",
                        object_id=_LEAVES.value,
                        state_key="last_harvest_tick",
                        ticks_offset=5,
                    ),
                    on_true_state_updates=(("available", False),),
                    on_false_state_updates=(),
                ),
            ),
        )

        assert kind is PreconditionFailureKind.PERMANENT

    def test_a_time_predicate_nested_in_a_composite_still_counts(self) -> None:
        """AND / OR の中に時間述語があっても見つける。

        実シナリオは ``AND(OBJECT_STATE(smelting), OBJECT_STATE_TICK_AT_LEAST(...))``
        のような合成述語を使う (cauldron_crafting)。leaf だけ見ると取りこぼす。
        """
        binding = ReactiveObjectStateBinding(
            target_object_id=_LEAVES,
            predicate=ScenarioEventCondition(
                condition_type="AND",
                children=(
                    ScenarioEventCondition(
                        condition_type="OBJECT_STATE",
                        object_id=_LEAVES.value,
                        required_state={"phase": "smelting"},
                    ),
                    ScenarioEventCondition(
                        condition_type="OBJECT_STATE_TICK_AT_LEAST",
                        object_id=_LEAVES.value,
                        state_key="started_at_tick",
                        ticks_offset=5,
                    ),
                ),
            ),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(),
        )

        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True), bindings=(binding,)
        )

        assert kind is PreconditionFailureKind.TIME_RECOVERING


class TestNonTimeRecoveringFailures:
    """時間で戻らない失敗の区分。"""

    def test_no_binding_at_all_is_permanent(self) -> None:
        """戻す binding が無ければ PERMANENT。別の対象へ向かうべき場合。"""
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True), bindings=()
        )

        assert kind is PreconditionFailureKind.PERMANENT

    def test_a_non_time_predicate_is_condition_recovering(self) -> None:
        """時間ではない述語が戻すなら CONDITION_RECOVERING。

        「待て」ではなく「条件を変えろ」が正しい助言になる。実 run では 2 件と
        少ないが、`relay_puzzle` の操作盤のように**他人の行動で戻る**形がある。
        """
        kind = classify_precondition_failure(
            _object_state_condition(_LEAVES, "available", True),
            bindings=(_flag_binding(_LEAVES, "available", True),),
        )

        assert kind is PreconditionFailureKind.CONDITION_RECOVERING

    @pytest.mark.parametrize(
        "condition_type",
        [
            InteractionConditionTypeEnum.HAS_ITEM,
            InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            InteractionConditionTypeEnum.WEATHER_IS,
        ],
    )
    def test_a_non_object_state_condition_is_missing_prerequisite(
        self, condition_type: InteractionConditionTypeEnum
    ) -> None:
        """物体状態でない条件は MISSING_PREREQUISITE。

        実 run で 216 件。持ち物 / 体力 / 天候などは「揃えてから再試行」が
        正しい助言で、`reactive_bindings` とは関係がない。
        """
        kind = classify_precondition_failure(
            InteractionCondition(condition_type=condition_type), bindings=()
        )

        assert kind is PreconditionFailureKind.MISSING_PREREQUISITE

    def test_an_unknown_condition_falls_back_to_missing_prerequisite(self) -> None:
        """区分の判断材料が無い条件は MISSING_PREREQUISITE へ倒す。

        「揃えてから再試行」は最も無害な助言。**「待て」や「別の対象へ」を既定に
        すると、成立しうる行動を諦めさせる。**
        """
        kind = classify_precondition_failure(None, bindings=())

        assert kind is PreconditionFailureKind.MISSING_PREREQUISITE


class TestEveryKindHasWording:
    """全区分に助言文がある。"""

    def test_no_kind_is_missing_its_remediation(self) -> None:
        """`PreconditionFailureKind` の全件に助言文が対応している。

        区分を 1 つ足して文を書き忘れると、その区分だけ助言が空になる。enum から
        引いて縛る (`world_vocabulary` と同じ形)。
        """
        from ai_rpg_world.application.world_graph.precondition_failure_kind import (
            REMEDIATION_BY_KIND,
        )

        missing = sorted(k.name for k in PreconditionFailureKind if k not in REMEDIATION_BY_KIND)

        assert missing == [], missing

    def test_the_wordings_differ_between_kinds(self) -> None:
        """区分ごとに違う文が出る。

        同じ文なら区分した意味が無い。とくに TIME_RECOVERING と PERMANENT は
        **正反対の助言**でなければならない (待つ / 別の対象へ)。
        """
        from ai_rpg_world.application.world_graph.precondition_failure_kind import (
            REMEDIATION_BY_KIND,
        )

        texts = list(REMEDIATION_BY_KIND.values())

        assert len(set(texts)) == len(texts), texts

    def test_time_recovering_tells_the_agent_to_wait(self) -> None:
        """「時間で回復」の助言は待つことを促す。

        以前はここで「別の場所・別 object を選ぶか」と**逆の助言**をしていた。
        """
        from ai_rpg_world.application.world_graph.precondition_failure_kind import (
            REMEDIATION_BY_KIND,
        )

        text = REMEDIATION_BY_KIND[PreconditionFailureKind.TIME_RECOVERING]

        assert "待" in text
        assert "別の場所" not in text

    def test_no_remediation_leaks_an_internal_identifier(self) -> None:
        """助言文に内部識別子が出ない。

        `action_name` / `object` のような英字の識別子を混ぜると、#1043 で閉じた
        「ID をプロンプトに出さない」方針の裏口になる。
        """
        import re

        from ai_rpg_world.application.world_graph.precondition_failure_kind import (
            REMEDIATION_BY_KIND,
        )

        leaked = {
            kind.name: text
            for kind, text in REMEDIATION_BY_KIND.items()
            if re.search(r"[A-Za-z_]{4,}", text)
        }

        assert leaked == {}, leaked
