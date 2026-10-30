"""段階のある作業を誰かが先に進めたとき、遅れた側に「いまできる手順」を返す。

station_drill の Gemma 4 31B run で、同じ部屋の 2 人が同じ tick に同じ段階を
選び、後の人が 4 回「取りかかる段ではない」で拒否された。拒否には「ここはもう
変わらない。別の場所か別の対象を選ぶこと」が添えられたが、実際には同じ物体の
次の手順が通る状態だった。prompt は tick の頭に作られるので、後の人の選択は
その時点では正しい。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.precondition_failure_kind import (
    REMEDIATION_BY_KIND,
    PreconditionFailureKind,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_SCENARIOS = Path(__file__).resolve().parents[5] / "data" / "scenarios"
_FIXTURES = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "scenarios"
_DRILL = _SCENARIOS / "station_drill.json"
_MORI, _AOI = PlayerId(1), PlayerId(4)
_CHART = "cable_label_chart"


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_DRILL)
    for player_id in (_MORI, _AOI):
        _move(rt, player_id, "corridor")
    return rt


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.teleport_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _executor(runtime) -> SpotGraphToolExecutor:
    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=runtime._speech_event_publisher,
        time_provider=runtime._time_provider,
        spot_graph_repository=runtime._spot_graph_repo,
        speech_service=runtime._speech_service,
        runtime=runtime,
    )


def _interact(runtime, executor, player_id: PlayerId, action: str, target: str = _CHART):
    return executor._interact(
        player_id.value,
        {
            "object_id": runtime.id_mapper.get_int("object", target),
            "action_name": action,
            "inner_thought": "配線番号を照合する",
        },
    )


class TestTheLaterHandIsToldWhatIsOpenNow:
    """先に進められた段階を選んだ人は、同じ物体でいま通る手順を教わる。"""

    def test_names_the_next_step_after_someone_else_advanced_it(self, runtime) -> None:
        """モリが第一段階を済ませた直後にアオイが第一段階を選ぶと、拒否文に第二段階の表示名と操作名が載る。"""
        executor = _executor(runtime)
        assert _interact(runtime, executor, _MORI, "verify_cable_labels").success

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.success is False
        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "配線番号を照合する（続き）" in result.message
        assert '"verify_cable_labels_2"' in result.message

    def test_advises_the_same_object_instead_of_another_place(self, runtime) -> None:
        """いま通る手順があるとき、助言は「別の場所か別の対象」ではなく同じ対象の手順を選ばせる。"""
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.remediation == REMEDIATION_BY_KIND[PreconditionFailureKind.STATE_MOVED_ON]
        assert result.trace_payload == {"precondition_failure_kind": "state_moved_on"}

    def test_does_not_leak_the_keepers_pretend_action(self, runtime) -> None:
        """いま通る手順の一覧に、キーパーの役割を前提条件にした偽装用の操作は載らない。"""
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert "pretend" not in result.message


class TestAFinishedObjectStillSaysItWillNotChange:
    """いま通る手順が 1 つも無いときは、従来どおり恒久的な失敗として扱う。"""

    def test_a_completed_chart_is_classified_as_permanent(self, runtime) -> None:
        """モリが 3 段階すべてを済ませたあと、アオイが仕上げを選ぶと恒久的な失敗になり、手順の案内は付かない。"""
        executor = _executor(runtime)
        for action in (
            "verify_cable_labels",
            "verify_cable_labels_2",
            "verify_cable_labels_3",
        ):
            assert _interact(runtime, executor, _MORI, action).success

        result = _interact(runtime, executor, _AOI, "verify_cable_labels_3")

        assert result.success is False
        assert result.trace_payload == {"precondition_failure_kind": "permanent"}
        assert "verify_cable_labels" not in result.message


class TestOnlyAStateConditionCanHaveMovedOn:
    """物体の状態の条件で落ちたときだけ「先に進んでいる」と扱う。"""

    def test_a_refusal_without_a_state_condition_keeps_its_kind(self, runtime) -> None:
        """待ち時間の拒否のように失敗条件を持たない拒否は、同じ物体に通る手順があっても先に進んだ扱いにしない。"""
        executor = _executor(runtime)
        open_now = runtime._interaction_service.interactions_open_now(
            _AOI,
            SpotObjectId.create(runtime.id_mapper.get_int("object", _CHART)),
        )
        assert open_now

        result = executor._precondition_failure_result(
            InteractionNotAllowedException("まだそれはできない。あと10分。"),
            open_now=open_now,
        )

        assert result.trace_payload == {"precondition_failure_kind": "missing_prerequisite"}
        assert "いまできるのは" not in result.message


def _make_dead(runtime, player_id: PlayerId, spot: str) -> None:
    _move(runtime, player_id, spot)
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", spot))
    runtime._fallen_body_registry.record(player_id, spot_id, WorldTick(runtime.current_tick()))
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(player_id, PlayerOutcomeEnum.DEAD)
    runtime._departed_position_store.place(player_id, spot_id)


def _open_action_names(runtime, player_id: PlayerId, object_str_id: str) -> list[str]:
    return [
        idef.action_name
        for idef in runtime._interaction_service.interactions_open_now(
            player_id,
            SpotObjectId.create(runtime.id_mapper.get_int("object", object_str_id)),
        )
    ]


class TestOpenNowFollowsWhatTheActorCanSee:
    """いま通る手順の一覧は、候補表示と同じく存在層で絞られる。"""

    def test_a_living_actor_sees_a_living_only_action(self, runtime) -> None:
        """生者は、生者専用で前提条件の無い配電盤の復旧を、いま通る手順として受け取る。"""
        _move(runtime, _AOI, "machine_room")

        assert _open_action_names(runtime, _AOI, "main_distribution_panel") == ["restore_power"]

    def test_a_departed_actor_is_not_offered_a_living_only_action(self, runtime) -> None:
        """死者には、前提条件を満たしていても生者専用の操作をいま通る手順として返さない。"""
        _make_dead(runtime, _AOI, "machine_room")

        assert _open_action_names(runtime, _AOI, "main_distribution_panel") == []


class TestTheRefusalSurvivesABrokenLookup:
    """いま通る手順を調べる処理が壊れても、元の拒否はそのまま返る。"""

    def test_a_failing_lookup_falls_back_to_the_plain_refusal(self, runtime, monkeypatch) -> None:
        """いま通る手順の問い合わせが例外を投げても、拒否文と区分は案内なしの従来どおりになり、例外は外へ出ない。"""
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")

        def broken(*_args, **_kwargs):
            raise RuntimeError("壊れた問い合わせ")

        monkeypatch.setattr(runtime._interaction_service, "interactions_open_now", broken)

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert result.trace_payload == {"precondition_failure_kind": "permanent"}
        assert result.message == "行動が拒否された: いまその手順に取りかかる段ではない。"


class TestOnlyAForwardStepCountsAsMovedOn:
    """同じ状態を先へ進める操作だけを、先に進んだ段階の次の手順として扱う。"""

    def test_a_toggle_does_not_suggest_undoing_what_someone_did(self) -> None:
        """仲間が操作盤の電源を入れた直後に電源を入れようとしても、電源を切る操作は案内されず恒久的な失敗になる。"""
        runtime = create_world_runtime(_FIXTURES / "control_panel_toggle.json")
        a, b = PlayerId(1), PlayerId(2)
        for player_id in (a, b):
            _move(runtime, player_id, "control_room")
        executor = _executor(runtime)
        assert _interact(runtime, executor, a, "power_on", "control_panel").success

        result = _interact(runtime, executor, b, "power_on", "control_panel")

        assert result.success is False
        assert result.trace_payload == {"precondition_failure_kind": "permanent"}
        assert "power_off" not in result.message

    def test_an_always_open_action_is_not_a_next_step(self) -> None:
        """錠が開いたあとに順番を奉じても、前提条件の無い「調べる」は次の手順として案内されない。"""
        runtime = create_world_runtime(_SCENARIOS / "forbidden_library_demo.json")
        a, b = PlayerId(1), PlayerId(2)
        for player_id in (a, b):
            _move(runtime, player_id, "decoding_room")
        executor = _executor(runtime)
        assert _interact(runtime, executor, a, "offer_order_2", "silence_lock").success

        result = _interact(runtime, executor, b, "offer_order_3", "silence_lock")

        assert result.success is False
        assert result.trace_payload == {"precondition_failure_kind": "permanent"}
        assert "examine" not in result.message

    def test_a_step_still_waiting_is_not_offered(self, runtime, monkeypatch) -> None:
        """次の段階の待ち時間が明けていなければ、次の手順として案内せず恒久的な失敗のままにする。"""
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")
        service = runtime._interaction_service
        monkeypatch.setattr(
            service,
            "remaining_cooldown_ticks",
            lambda _player, _object, idef, _tick: 3 if idef.action_name == "verify_cable_labels_2" else 0,
        )

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.trace_payload == {"precondition_failure_kind": "permanent"}
        assert "verify_cable_labels_2" not in result.message


def _rewrite_second_step_effect(runtime, **parameters) -> None:
    """配線番号表の第二段階の増分効果の引数を書き換える。"""
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", "corridor"))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    chart = interior.get_object(SpotObjectId.create(runtime.id_mapper.get_int("object", _CHART)))
    interactions = tuple(
        replace(
            interaction,
            effects=tuple(
                replace(effect, parameters={**effect.parameters, **parameters})
                if effect.effect_type is InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE
                else effect
                for effect in interaction.effects
            ),
        )
        if interaction.action_name == "verify_cable_labels_2"
        else interaction
        for interaction in chart.interactions
    )
    runtime._spot_interior_repo.save(spot_id, interior.replace_object(replace(chart, interactions=interactions)))


class TestTheNextStepMustMoveThisObjectForward:
    """次の手順とみなすのは、落ちた条件の物体の状態を増やす操作だけ。"""

    def test_a_step_that_counts_backward_is_not_offered(self, runtime) -> None:
        """第二段階の増分が負なら、状態を戻す操作なので次の手順として案内しない。"""
        _rewrite_second_step_effect(runtime, delta=-1)
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.trace_payload == {"precondition_failure_kind": "permanent"}

    def test_a_step_that_moves_another_object_is_not_offered(self, runtime) -> None:
        """第二段階が別の物体の状態を増やすなら、この物体の続きではないので案内しない。"""
        _rewrite_second_step_effect(
            runtime,
            object_id=runtime.id_mapper.get_int("object", "fire_door_latch"),
        )
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "verify_cable_labels")

        result = _interact(runtime, executor, _AOI, "verify_cable_labels")

        assert result.trace_payload == {"precondition_failure_kind": "permanent"}


class TestARecoveringKindIsNotOverridden:
    """待てば戻る・条件が変われば戻る区分は、次の手順があっても上書きしない。"""

    def test_time_recovering_wins_over_an_open_next_step(self) -> None:
        """失敗条件が時間で戻ると宣言されていれば、次の手順が渡されても区分は「時間で回復」のまま。"""
        from ai_rpg_world.application.world_graph.precondition_failure_kind import (
            classify_precondition_failure,
        )
        from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
            InteractionConditionTypeEnum,
        )
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        loaded = ScenarioLoader().load_from_file(str(_SCENARIOS / "survival_island_v4_coop.json"))
        bindings = loaded.reactive_object_state_bindings
        interactions = [
            interaction
            for interior in loaded.interiors.values()
            for obj in interior.objects
            for interaction in obj.interactions
        ]
        condition = next(
            c
            for interaction in interactions
            for c in interaction.preconditions
            if c.condition_type is InteractionConditionTypeEnum.OBJECT_STATE
            and classify_precondition_failure(c, bindings=bindings) is PreconditionFailureKind.TIME_RECOVERING
        )
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=MagicMock(),
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            reactive_object_state_bindings=bindings,
        )

        result = executor._precondition_failure_result(
            InteractionNotAllowedException("まだ戻っていない。", failed_condition=condition),
            open_now=(interactions[0],),
        )

        assert result.trace_payload == {"precondition_failure_kind": "time_recovering"}
        assert "いまできるのは" not in result.message
