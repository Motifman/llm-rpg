"""想起の手がかりが、表示文ではなく欲求の値から決まることを保証する。

## なぜこの試験が要るか

`prompt_builder` は意味記憶の検索語を決めるのに、**自分たちが組み立てた表示文を
読み直していた**。

    for line in snap.need_lines:                    # "空腹: 危険（68/100、前回 +3）"
        if line.startswith("空腹") and ("高い" in line or "危険" in line):
            out.extend(("空腹", "食料"))

判定に必要な値はドメインに既にある。

    AgentNeed.need_type          -> 「空腹で始まるか」で代用していた
    AgentNeed.is_high (>= 0.6)   -> 「高い or 危険 を含むか」で代用していた

``("高い" in line or "危険" in line)`` は `is_high` と**完全に等価**である
(`describe` の tier が 0.6 以上で「高い」、0.8 以上で「危険」)。つまり既にある述語を
文字列で再実装していた。

## 静かに壊れる形

**表示の言い回しを変えると検索語が消える。** `describe` の tier を「高い」から
「強い」に直すリファクタリングで、想起の手がかりが黙って出なくなる。テストは通る。

#380 (系統1) と同じ形である。あちらはシナリオ作者の自由文に依存していた。こちらは
自分の表示文に依存している。**どちらも「値を持っているのに文字列から読み直す」。**

## この試験が見ないこと

呼び名 (「空腹」「疲労」) の所有者は変えない。それは #1054 の判断待ち。ここは
「文字列を読み直さない」ことだけを固定する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.prompt_builder import (
    _gather_semantic_topic_words_for_recall,
)
from ai_rpg_world.application.llm.services.recall_need_cues import (
    RECALL_CUES_BY_NEED_TYPE,
    recall_cues_for_needs,
)
from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType


class _Snapshot:
    """`spot_graph_snapshot` の必要な部分だけを持つ最小の器。"""

    def __init__(self, *, need_states: tuple = (), need_lines: tuple = ()) -> None:
        self.need_states = need_states
        self.need_lines = need_lines
        self.current_spot_name = None
        self.objects = ()
        self.inventory_items = ()
        self.ground_items = ()
        self.nearby_entities = ()
        self.monsters_at_spot = ()


class _CurrentState:
    def __init__(self, snapshot: Any) -> None:
        self.spot_graph_snapshot = snapshot
        self.current_spot_name = None
        self.area_names = ()
        self.visible_objects = ()
        self.inventory_items = ()


_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v4_coop.json"
)


def _need(need_type: NeedType, value: int, *, max_value: int = 100) -> AgentNeed:
    return AgentNeed(need_type=need_type, value=value, max_value=max_value)


class TestTheCueTableCoversEveryNeedType:
    """検索語の表が `NeedType` 全件を持つ。"""

    def test_no_need_type_is_missing_its_cues(self) -> None:
        """`NeedType` を 1 つ足して表に載せ忘れたら落ちる。

        載せ忘れると、その欲求が危険域でも想起の手がかりが黙って出なくなる。
        `world_vocabulary` の網羅試験と同じ形で縛る。
        """
        missing = sorted(
            n.name for n in NeedType if n not in RECALL_CUES_BY_NEED_TYPE
        )

        assert missing == [], missing

    def test_no_table_entry_is_stale(self) -> None:
        """表に、enum から消えた欲求のキーが残っていない。"""
        known = set(NeedType)
        stale = sorted(n.name for n in RECALL_CUES_BY_NEED_TYPE if n not in known)

        assert stale == [], stale

    def test_every_entry_has_at_least_one_cue(self) -> None:
        """どの欲求にも空でない検索語がある。

        空タプルを置くと、表に載っているのに手がかりが出ない状態になる。
        """
        empty = sorted(
            n.name for n, cues in RECALL_CUES_BY_NEED_TYPE.items() if not cues
        )

        assert empty == [], empty


class TestTheDisplayLabelTableCoversEveryNeedType:
    """表示上の呼び名の表も `NeedType` 全件を持つ。

    以前は ``"空腹" if need_type == HUNGER else "疲労"`` の 2 分岐で、**HUNGER 以外を
    全部「疲労」と表示していた**。NeedType が 2 つしかないから偶然正しかっただけで、
    渇き (THIRST) を足したら「疲労: 危険」と出る。

    検索語の表 (`RECALL_CUES_BY_NEED_TYPE`) と**同じ enum を回す**ので、片方だけ
    足す形も落ちる。
    """

    def test_no_need_type_is_missing_its_label(self) -> None:
        """`NeedType` 全件に呼び名がある。"""
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        missing = sorted(n.name for n in NeedType if n not in _NEED_LABELS)

        assert missing == [], missing

    def test_every_need_type_describes_with_its_own_label(self) -> None:
        """どの欲求も自分の呼び名で表示される。

        2 分岐が戻ったら (= 既定で「疲労」に倒れたら) ここで落ちる。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        for need_type in NeedType:
            described = _need(need_type, 90).describe()
            assert described.startswith(_NEED_LABELS[need_type]), (
                need_type.name,
                described,
            )

    def test_an_unregistered_need_type_fails_loudly(self) -> None:
        """表に無い欲求は**黙って別の呼び名へ倒れず**、その場で落ちる。

        これが 2 分岐との決定的な違い。``"空腹" if HUNGER else "疲労"`` は表に無い
        欲求を**静かに「疲労」と表示する**。表引きなら `KeyError` で落ちる。

        `NeedType` が 2 つしかない今、2 分岐へ戻す変異は挙動が同じなので他の試験
        では捕まえられない (実際に変異で確認した: 25 passed)。**倒れ方の違い**だけが
        検出できる差である。

        ここで落ちるのは「新しい欲求を足した人が、呼び名を書くまで気づく」形。
        表示に嘘が出るより、起動時に落ちる方がよい。
        """
        class _Unregistered:
            name = "THIRST"

        need = AgentNeed(
            need_type=_Unregistered(),  # type: ignore[arg-type]
            value=90,
            max_value=100,
        )

        with pytest.raises(KeyError):
            need.describe()

    def test_the_labels_are_distinct(self) -> None:
        """呼び名が欲求ごとに違う。

        同じ呼び名を 2 つの欲求に付けると、表示から区別できなくなる。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        labels = list(_NEED_LABELS.values())

        assert len(set(labels)) == len(labels), labels

    def test_the_cue_table_and_the_label_table_cover_the_same_enum(self) -> None:
        """検索語の表と呼び名の表が同じ集合を覆っている。

        片方だけ足すと、呼び名はあるのに手がかりが出ない (または逆) になる。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        assert set(_NEED_LABELS) == set(RECALL_CUES_BY_NEED_TYPE)


class TestCuesAreDecidedByTheValueNotTheText:
    """検索語は値で決まり、表示文には依存しない。"""

    def test_a_high_need_produces_its_cues(self) -> None:
        """`is_high` (60% 以上) の欲求は検索語を出す。"""
        cues = recall_cues_for_needs((_need(NeedType.HUNGER, 68),))

        assert set(cues) == set(RECALL_CUES_BY_NEED_TYPE[NeedType.HUNGER])

    def test_a_critical_need_also_produces_its_cues(self) -> None:
        """`is_critical` (80% 以上) も出す。

        以前は「危険」という語を含むかで判定していた。閾値の側で見れば
        「高い」も「危険」も同じ 1 つの述語 (`is_high`) で足りる。
        """
        cues = recall_cues_for_needs((_need(NeedType.HUNGER, 90),))

        assert set(cues) == set(RECALL_CUES_BY_NEED_TYPE[NeedType.HUNGER])

    def test_a_need_below_the_threshold_produces_nothing(self) -> None:
        """60% 未満なら検索語を出さない (正の対照)。"""
        cues = recall_cues_for_needs((_need(NeedType.HUNGER, 40),))

        assert cues == ()

    def test_the_boundary_is_inclusive(self) -> None:
        """ちょうど 60% は出す。

        `is_high` が ``>= 0.6`` なので、境界の扱いを実装と揃える。
        """
        cues = recall_cues_for_needs((_need(NeedType.HUNGER, 60),))

        assert cues != ()

    def test_each_high_need_contributes(self) -> None:
        """複数の欲求が同時に高いとき、両方の検索語が出る。"""
        cues = recall_cues_for_needs(
            (_need(NeedType.HUNGER, 70), _need(NeedType.FATIGUE, 85))
        )

        assert set(RECALL_CUES_BY_NEED_TYPE[NeedType.HUNGER]) <= set(cues)
        assert set(RECALL_CUES_BY_NEED_TYPE[NeedType.FATIGUE]) <= set(cues)


class TestThePromptBuilderUsesTheValues:
    """`prompt_builder` が値を読んでいる。"""

    def test_cues_come_from_need_states(self) -> None:
        """`need_states` から手がかりが出る。"""
        snapshot = _Snapshot(need_states=(_need(NeedType.HUNGER, 90),))

        words = _gather_semantic_topic_words_for_recall(_CurrentState(snapshot))

        for cue in RECALL_CUES_BY_NEED_TYPE[NeedType.HUNGER]:
            assert cue in words

    def test_the_display_wording_does_not_matter(self) -> None:
        """**表示文を書き換えても手がかりは変わらない。**

        以前は `need_lines` の「高い」「危険」という語に依存していたので、tier の
        言い回しを変えると手がかりが消えた。値だけを見るなら影響しない。
        """
        snapshot = _Snapshot(
            need_states=(_need(NeedType.HUNGER, 90),),
            need_lines=("腹の底が冷たい……（90/100）",),
        )

        words = _gather_semantic_topic_words_for_recall(_CurrentState(snapshot))

        for cue in RECALL_CUES_BY_NEED_TYPE[NeedType.HUNGER]:
            assert cue in words

    def test_display_text_alone_produces_nothing(self) -> None:
        """**表示文だけがあっても手がかりを出さない。**

        再パースが戻ったらここで落ちる。`need_lines` に「空腹: 危険」があっても、
        値が無ければ手がかりは出ない。
        """
        snapshot = _Snapshot(need_lines=("空腹: 危険（90/100）",))

        words = _gather_semantic_topic_words_for_recall(_CurrentState(snapshot))

        assert "食料" not in words

    def test_a_low_need_adds_nothing(self) -> None:
        """低い欲求では手がかりを増やさない (正の対照)。"""
        snapshot = _Snapshot(need_states=(_need(NeedType.HUNGER, 10),))

        words = _gather_semantic_topic_words_for_recall(_CurrentState(snapshot))

        assert "食料" not in words


class TestTheOldBehaviourIsPreserved:
    """挙動不変: 以前と同じ入力で同じ検索語が出る。"""

    @pytest.mark.parametrize(
        "need_type,value,expected",
        [
            (NeedType.HUNGER, 90, ("空腹", "食料")),
            (NeedType.HUNGER, 70, ("空腹", "食料")),
            (NeedType.FATIGUE, 90, ("疲労", "休息")),
            (NeedType.FATIGUE, 70, ("疲労", "休息")),
        ],
    )
    def test_the_same_cues_as_before(
        self, need_type: NeedType, value: int, expected: tuple
    ) -> None:
        """旧実装が出していた検索語と一致する。

        旧実装は「空腹で始まり、高い or 危険 を含む」なら ``("空腹", "食料")``、
        疲労なら ``("疲労", "休息")`` を出した。閾値も語彙も変えていないことを
        ここで固定する。**これが挙動不変の根拠。**
        """
        cues = recall_cues_for_needs((_need(need_type, value),))

        assert cues == expected


class TestTheValuesReachTheSnapshot:
    """実 runtime の snapshot に欲求の値が載っている。"""

    def test_the_builder_fills_need_states(self) -> None:
        """`SpotGraphCurrentStateBuilder` が `need_states` を埋める。

        分類の論理をいくら固めても、**材料が snapshot に載らなければ手がかりは
        永久に出ない**。しかも空タプルでも例外は出ないので、抜けても見えない。
        #1050 で同じ形を踏んだ (失敗条件を運ぶ経路が抜けても 39 passed で素通り
        した) ので、ここは実 runtime を通して見る。
        """
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        runtime = create_world_runtime(str(_SCENARIO))
        snapshot = runtime._state_builder.build_snapshot(1)

        assert snapshot is not None
        assert snapshot.need_states, "need_states が空です (配線が抜けています)"

    def test_the_states_expose_the_threshold_predicate(self) -> None:
        """載っている値が `need_type` と `is_high` を持つ。

        文字列や dict に変換して渡すと閾値の述語が失われ、また閾値を書き写す
        ことになる。値オブジェクトのまま渡すことをここで固定する。
        """
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        runtime = create_world_runtime(str(_SCENARIO))
        snapshot = runtime._state_builder.build_snapshot(1)

        for need in snapshot.need_states:
            assert isinstance(need.need_type, NeedType)
            assert isinstance(need.is_high, bool)

    def test_every_need_type_is_present(self) -> None:
        """全 `NeedType` が snapshot に載る (取りこぼしが無い)。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        runtime = create_world_runtime(str(_SCENARIO))
        snapshot = runtime._state_builder.build_snapshot(1)

        assert {n.need_type for n in snapshot.need_states} == set(NeedType)
