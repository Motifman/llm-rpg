"""interact の前提条件失敗が、そのまま surface され助言が付くことを保証する。

## この試験は何を測っていたか (経緯)

実験 #25 の N2 問題として書かれた。採取枯渇後の retry が generic な
「LLM ツール実行に失敗しました」に潰され、LLM が同じ枯渇 resource に何度も retry
していた。そこで `failure_message` をそのまま surface し、**枯渇系の reason には
「同じ object に retry しない」旨の remediation を選ぶ**ようにした。

判定は日本語キーワードの部分一致だった。

    _INTERACTION_EXHAUST_HINTS = ("採り尽く", "枯渇", "もう空", "もう開い",
                                  "すでに", "今は", "燃え上が")

この試験はその分岐を 1 件ずつ固定していた。

## なぜ書き換えたか (#380)

`failure_message` は**シナリオ作者が自由に書く文**で、「エージェントに読ませる文」
として書かれている。それを分類キーとしても使うと、作者は自分の言い回しがシステム
の分岐を変えることを知らないまま挙動を変えてしまう。「集めた」を「採り尽くした」
に直すだけで違う助言が出る。

さらに実 run 43 本を測ると、**当たっても外れても害だった**。

    時間で回復  251 件 ... うちキーワード当たり 31 件 (**その 31 件は全部誤り**)
    恒久的      154 件 ... うち当たり 43 件 (28%)
    前提不足    216 件 ... 当たらず (正しい)

「時間で回復」の 88% を取りこぼし、当たった 31 件には**逆の助言**を出していた。
作者が「風がまた運んでくるのを待つしかない」と書いた上から「別の場所を選べ」を
重ねていた。実 run では同じ壁に **96 回**当たっている。

そこで区分を**シナリオ宣言から導く**形に変えた (`precondition_failure_kind`)。
キーワード表は消えたので、この試験も「キーワードで分岐する」ではなく
「**宣言から正しい助言が出る**」を見る形にする。

区分そのものの試験は
`tests/application/world_graph/test_precondition_failure_kind.py`。ここは
**executor が実際にその助言を返すか**という配線を見る。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.precondition_failure_kind import (
    REMEDIATION_BY_KIND,
    PreconditionFailureKind,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
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

_BUSH = SpotObjectId.create(3)


def _executor(*, bindings: tuple = ()) -> SpotGraphToolExecutor:
    return SpotGraphToolExecutor(
        spot_graph_world_services=MagicMock(),
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        reactive_object_state_bindings=bindings,
    )


def _object_state_failure(message: str) -> InteractionNotAllowedException:
    return InteractionNotAllowedException(
        message,
        failed_condition=InteractionCondition(
            condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
            target_object_id=_BUSH,
            required_state={"available": True},
            failure_message=message,
        ),
    )


def _time_binding() -> ReactiveObjectStateBinding:
    return ReactiveObjectStateBinding(
        target_object_id=_BUSH,
        predicate=ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=_BUSH.value,
            state_key="last_harvest_tick",
            ticks_offset=8,
        ),
        on_true_state_updates=(("available", True),),
        on_false_state_updates=(("available", False),),
    )


class TestTheAuthorsMessageIsSurfacedVerbatim:
    """作者が書いた文がそのままエージェントへ届く。"""

    def test_the_failure_message_is_kept(self) -> None:
        """`failure_message` が message にそのまま乗る。

        generic な失敗に潰さない、という #25 の成果はそのまま保つ。
        """
        result = _executor()._precondition_failure_result(
            _object_state_failure("近くの蔓は採り尽くした。")
        )

        assert "近くの蔓は採り尽くした。" in result.message

    def test_the_error_code_is_unchanged(self) -> None:
        """`error_code` は据え置き。

        実 run 最多 (679 件) のコードなので、分割すると過去 run との比較が切れる。
        区分は `trace_payload` で測る。
        """
        result = _executor()._precondition_failure_result(
            _object_state_failure("近くの蔓は採り尽くした。")
        )

        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"


class TestTheAdviceComesFromTheDeclarationNotTheWording:
    """助言は宣言から決まり、作者の言い回しには依存しない。"""

    def test_a_time_restored_object_is_told_to_wait(self) -> None:
        """時間で戻る物体なら「待て」と伝える。

        **以前はここで「別の場所を選べ」と逆を言っていた。** 実 run で 96 回
        反復した形がこれである。
        """
        result = _executor(bindings=(_time_binding(),))._precondition_failure_result(
            _object_state_failure("ここの枯れ葉はもう集めた。風がまた運んでくる。")
        )

        assert result.remediation == REMEDIATION_BY_KIND[
            PreconditionFailureKind.TIME_RECOVERING
        ]
        assert "待" in result.remediation

    def test_an_object_with_no_binding_is_told_to_move_on(self) -> None:
        """戻す宣言が無ければ「別の対象へ」と伝える。"""
        result = _executor()._precondition_failure_result(
            _object_state_failure("ここの漂着物は調べ尽くした。")
        )

        assert result.remediation == REMEDIATION_BY_KIND[
            PreconditionFailureKind.PERMANENT
        ]

    def test_the_same_wording_gets_different_advice_by_declaration(self) -> None:
        """**同じ文でも、宣言が違えば助言が変わる。**

        これがキーワード判定との決定的な違い。以前は文が同じなら必ず同じ助言に
        なり、宣言を見ていなかった。
        """
        message = "もう採り尽くした。"

        waiting = _executor(bindings=(_time_binding(),))._precondition_failure_result(
            _object_state_failure(message)
        )
        permanent = _executor()._precondition_failure_result(
            _object_state_failure(message)
        )

        assert waiting.remediation != permanent.remediation

    def test_the_wording_no_longer_changes_the_advice(self) -> None:
        """**言い回しを変えても助言は変わらない。**

        以前は「採り尽くした」が「集めた」に変わるだけで分岐が変わった。作者は
        その結合を知らない。宣言が同じなら助言は同じでなければならない。
        """
        binding = (_time_binding(),)
        a = _executor(bindings=binding)._precondition_failure_result(
            _object_state_failure("採り尽くした。")
        )
        b = _executor(bindings=binding)._precondition_failure_result(
            _object_state_failure("ここの枯れ葉はもう集めた。")
        )

        assert a.remediation == b.remediation

    def test_a_non_object_condition_asks_to_satisfy_the_prerequisite(self) -> None:
        """持ち物などの前提不足は「揃えてから」と伝える。"""
        exc = InteractionNotAllowedException(
            "松明を持っていない。",
            failed_condition=InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM
            ),
        )

        result = _executor()._precondition_failure_result(exc)

        assert result.remediation == REMEDIATION_BY_KIND[
            PreconditionFailureKind.MISSING_PREREQUISITE
        ]


class TestTheKindIsMeasurableFromTraces:
    """区分が trace に残り、run 分析で測れる。"""

    def test_the_kind_is_recorded_in_the_trace_payload(self) -> None:
        """`trace_payload` に区分が載る。

        `error_code` を据え置く代わりに、run 分析はこの値で区分ごとの反復回数を
        測る。載っていないと「助言が効いたか」を後から確かめられない。
        """
        result = _executor(bindings=(_time_binding(),))._precondition_failure_result(
            _object_state_failure("もう集めた。")
        )

        assert (result.trace_payload or {}).get("precondition_failure_kind") == (
            PreconditionFailureKind.TIME_RECOVERING.value
        )


class TestTheKeywordTableIsGone:
    """キーワード判定が戻っていない。"""

    def test_the_exhaust_hint_table_no_longer_exists(self) -> None:
        """`_INTERACTION_EXHAUST_HINTS` が復活していない。

        戻すと、シナリオ作者の言い回しが再びシステムの分岐を決める。
        """
        from ai_rpg_world.application.llm.services.executors import interact_helpers

        assert not hasattr(interact_helpers, "_INTERACTION_EXHAUST_HINTS")
        assert not hasattr(interact_helpers, "interact_remediation_for_reason")
