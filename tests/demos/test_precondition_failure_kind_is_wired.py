"""前提条件の区分が、実シナリオの宣言まで届いていることを保証する。

## なぜこの試験が要るか

`classify_precondition_failure` は `reactive_object_state_bindings` を材料にする。
**渡らなければ「時間で回復」は永久に判別できず**、実測 251 件に「別の対象へ」という
逆の助言が出る。しかも渡らなくても例外は出ない (既定が空タプル) ので、配線が抜けた
ことは誰にも見えない。

#853 で同じ形を踏んだ。`time_provider=getattr(runtime, "_time_provider", None)` は
属性名が変われば静かに None になり、「準備をした」と嘘を返していた。ここも
``getattr(scenario, "reactive_object_state_bindings", ())`` で渡しているので、同じ
壊れ方をする。

だから**実シナリオを読み込んで、区分が実際に付くところまで**を見る。単体試験は
分類器の論理を見るが、論理が正しくても材料が届かなければ意味がない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.precondition_failure_kind import (
    PreconditionFailureKind,
    classify_precondition_failure,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"

#: 時間で戻る資源を宣言しているシナリオ。**実測でこの 4 本が該当する。**
_TIME_RECOVERING_SCENARIOS = (
    "survival_island_v2.json",
    "survival_island_v2_short.json",
    "survival_island_v3_coop.json",
    "survival_island_v4_coop.json",
)


def _load(name: str):
    return ScenarioLoader().load_from_file(str(_SCENARIOS / name))


def _classified_kinds(loaded) -> dict:
    """そのシナリオの全前提条件を区分して数える。"""
    counts: dict = {}
    for interior in (loaded.interiors or {}).values():
        for obj in interior.objects:
            for interaction in obj.interactions:
                for condition in interaction.preconditions:
                    kind = classify_precondition_failure(
                        condition, bindings=loaded.reactive_object_state_bindings
                    )
                    counts[kind] = counts.get(kind, 0) + 1
    return counts


class TestTheDeclarationsReachTheClassifier:
    """シナリオ宣言が分類器へ届いている。"""

    @pytest.mark.parametrize("name", _TIME_RECOVERING_SCENARIOS)
    def test_the_scenario_declares_reactive_bindings(self, name: str) -> None:
        """対象シナリオが reactive object binding を宣言している。

        宣言が 0 件になったら以下の試験は「材料が無いので判別できない」を
        「配線が壊れた」と区別できなくなる。前提をここで固定する。
        """
        loaded = _load(name)

        assert loaded.reactive_object_state_bindings, (
            f"{name} が reactive_object_state_bindings を宣言していません。"
        )

    @pytest.mark.parametrize("name", _TIME_RECOVERING_SCENARIOS)
    def test_time_recovering_conditions_are_recognised(self, name: str) -> None:
        """「待てば戻る」条件が 1 件以上見つかる。

        材料が届いていないと、この区分は 0 件になり全部 PERMANENT へ倒れる。
        **その状態でも例外は出ない**ので、件数で見張る。
        """
        counts = _classified_kinds(_load(name))

        assert counts.get(PreconditionFailureKind.TIME_RECOVERING, 0) > 0, counts

    @pytest.mark.parametrize("name", _TIME_RECOVERING_SCENARIOS)
    def test_permanent_conditions_also_exist(self, name: str) -> None:
        """同じシナリオに「もう変わらない」条件も存在する (正の対照)。

        全部 TIME_RECOVERING になる実装でも上の試験は通る。両方あることを見る。
        """
        counts = _classified_kinds(_load(name))

        assert counts.get(PreconditionFailureKind.PERMANENT, 0) > 0, counts


class TestTheExecutorReceivesTheBindings:
    """executor まで材料が渡っている。"""

    def test_the_runtime_manager_passes_the_bindings(self) -> None:
        """ターン実行の tool_dispatch が executor へ bindings を渡している。

        ソースを読んで確かめる。実行時に組み立てると LLM 経路まで通す必要があり
        重いので、**渡し忘れ**という 1 点だけを構造で見る。

        `getattr(scenario, "reactive_object_state_bindings", ())` の形なので、
        属性名が変われば静かに空になる。ここが消えたら落ちる。
        """
        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "ai_rpg_world"
            / "application"
            / "llm"
            / "services"
            / "world_llm_turn"
            / "tool_dispatch.py"
        ).read_text(encoding="utf-8")

        assert "reactive_object_state_bindings=" in source, (
            "tool_dispatch が executor へ reactive_object_state_bindings を"
            " 渡していません。渡さないと「待てば戻る」が判別できず、"
            " 逆の助言が出ます。"
        )

    def test_the_executor_stores_them(self) -> None:
        """executor が受け取った bindings を保持している。"""
        from unittest.mock import MagicMock

        from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501
            SpotGraphToolExecutor,
        )

        loaded = _load("survival_island_v4_coop.json")
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=MagicMock(),
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            reactive_object_state_bindings=loaded.reactive_object_state_bindings,
        )

        assert executor._reactive_object_state_bindings == (
            loaded.reactive_object_state_bindings
        )


class TestTheAuthorsWordingNoLongerDecides:
    """作者の言い回しが判定に使われていない。"""

    def test_the_declared_message_does_not_change_the_kind(self) -> None:
        """実シナリオの条件で、`failure_message` を書き換えても区分が変わらない。

        以前は「採り尽く」を含むかどうかで分岐した。宣言が同じなら区分は同じ、を
        実データで確かめる。
        """
        import dataclasses

        loaded = _load("survival_island_v4_coop.json")
        bindings = loaded.reactive_object_state_bindings
        target = next(
            condition
            for interior in (loaded.interiors or {}).values()
            for obj in interior.objects
            for interaction in obj.interactions
            for condition in interaction.preconditions
            if condition.condition_type is InteractionConditionTypeEnum.OBJECT_STATE
            and classify_precondition_failure(condition, bindings=bindings)
            is PreconditionFailureKind.TIME_RECOVERING
        )

        rewritten = dataclasses.replace(target, failure_message="ぜんぜん違う言い方。")

        assert classify_precondition_failure(rewritten, bindings=bindings) is (
            PreconditionFailureKind.TIME_RECOVERING
        )
