"""#356 後続: ReactiveObjectStateBinding の narrative 配線検証。

旧コードは reactive_binding で state が flip するたび
"available が False から True に変わった" を機械生成して prompt に流して
いた (内部 vocab の漏洩)。

修正後の仕様:
- binding に `narrative_on_true` / `narrative_on_false` を宣言できる
- stage service は flip 方向に応じた narrative を SpotObjectStateChangedEvent
  に乗せる
- formatter は narrative がある時だけ observation を emit する (無ければ silent)

本テストはこれら 3 層の配線を順に確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)


class TestReactiveBindingNarrativeFields:
    """`ReactiveObjectStateBinding` が narrative を保持できる。"""

    def test_両方向_narrative_を_保持できる(self) -> None:
        from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
            ScenarioEventCondition,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=100),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(("available", False),),
            narrative_on_true="ベリーがまた生っている",
            narrative_on_false=None,
        )
        assert b.narrative_on_true == "ベリーがまた生っている"
        assert b.narrative_on_false is None

    def test_narrative_未指定なら_None_default(self) -> None:
        from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
            ScenarioEventCondition,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=ScenarioEventCondition(
                condition_type="TICK_AT_LEAST", tick=100,
            ),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(),
        )
        assert b.narrative_on_true is None
        assert b.narrative_on_false is None


class TestSpotObjectStateChangedEventNarrativeField:
    """`SpotObjectStateChangedEvent` が narrative を保持できる。"""

    def test_narrative_default_None(self) -> None:
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

        ev = SpotObjectStateChangedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(1),
            old_state={"a": False}, new_state={"a": True},
        )
        assert ev.narrative is None

    def test_narrative_明示指定で_event_に_乗る(self) -> None:
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

        ev = SpotObjectStateChangedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(1),
            old_state={"a": False}, new_state={"a": True},
            narrative="花が咲いた",
        )
        assert ev.narrative == "花が咲いた"


class TestScenarioLoaderParsesNarrative:
    """survival_island_v2.json の harvest cooldown binding に narrative_on_true が載っている。"""

    SCENARIO_PATH = (
        Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2.json"
    )

    def test_v2_の_全_harvest_binding_に_narrative_on_true_が_付与済み(self) -> None:
        """資源 cooldown の reset (false→true) は narrative が出る前提に揃える。

        これが無いと、採取資源の自然回復が agent に伝わらない (silent) ため、
        scenario 設計と整合しない。
        """
        raw = json.loads(self.SCENARIO_PATH.read_text(encoding="utf-8"))
        for i, b in enumerate(raw["reactive_bindings"]["objects"]):
            assert b.get("narrative_on_true"), (
                f"reactive_bindings.objects[{i}] target={b['target']} に "
                f"narrative_on_true が無い。資源回復が silent になり LLM に "
                "伝わらない"
            )
            # 内部 vocab を narrative に含めるのは NG (再発防止)
            assert "available" not in b["narrative_on_true"]
            assert "True" not in b["narrative_on_true"]
            assert "False" not in b["narrative_on_true"]

    def test_loader_が_narrative_を_読み込む(self) -> None:
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        loaded = ScenarioLoader().load_from_file(str(self.SCENARIO_PATH))
        # 1 件以上の binding に narrative_on_true がパースされていること
        with_narrative = [
            b for b in loaded.reactive_object_state_bindings
            if b.narrative_on_true is not None
        ]
        assert len(with_narrative) == 12, (
            f"narrative_on_true 付きの binding 数が想定と異なる: {len(with_narrative)}"
            " (survival_island_v2.json の harvest cooldown は 12 件)"
        )


# Note: formatter の silent 動作は tests/application/observation/
# test_spot_graph_formatter.py::TestSpotObjectStateChanged で別途検証する。
# こちらでは domain / scenario_loader 層に絞って配線を確認する。
