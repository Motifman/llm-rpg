"""死亡した担当者が、生者へ混ざらずに作業を続ける挙動を保証する。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
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


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)
_HAGI = PlayerId(5)


class _StubClient:
    """LLM は呼ばず、実際のツール境界だけを通す。"""


def _wiring(runtime) -> _WorldLlmWiring:
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_StubClient(),
    )


def _user_prompt(runtime, player_id: PlayerId) -> str:
    prompt = runtime.build_full_prompt(player_id)
    return next(
        message["content"]
        for message in prompt["messages"]
        if message["role"] == "user"
    )


def _main_distribution_panel_label(runtime, player_id: PlayerId) -> tuple[str, object]:
    """実際の手番文脈から主配電盤の対象ラベルと文脈を返す。"""
    ui = runtime.build_llm_context(player_id)
    label = next(
        label
        for label, target in ui.tool_runtime_context.targets.items()
        if getattr(target, "display_name", "") == "主配電盤"
    )
    return label, ui.tool_runtime_context


def _interact_with_main_distribution_panel(
    runtime,
    player_id: PlayerId,
    action_name: str,
):
    """主配電盤への操作を、エージェントが読む実ツール境界まで通す。"""
    label, context = _main_distribution_panel_label(runtime, player_id)
    return _wiring(runtime)._execute_tool(
        player_id,
        "interact",
        {"target_label": label, "action_name": action_name},
        context,
        offered_tool_names_at_prompt=frozenset({"interact"}),
    )


def _spot(runtime, name: str) -> SpotId:
    return SpotId.create(runtime.id_mapper.get_int("spot", name))


def _place_living(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, _spot(runtime, spot_name))
    runtime._spot_graph_repo.save(graph)


def _make_dead(runtime, player_id: PlayerId, spot_name: str) -> None:
    _place_living(runtime, player_id, spot_name)
    runtime._fallen_body_registry.record(
        player_id, _spot(runtime, spot_name), WorldTick(runtime.current_tick())
    )
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(player_id, PlayerOutcomeEnum.DEAD)


def _make_downed(runtime, player_id: PlayerId, spot_name: str) -> None:
    _place_living(runtime, player_id, spot_name)
    runtime._fallen_body_registry.record(
        player_id, _spot(runtime, spot_name), WorldTick(runtime.current_tick())
    )
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def test_departed_position_is_visible_only_from_the_departed_side(runtime) -> None:
    """別位置へ動いた幽霊は生者の現在状況に混ざらず、本人には移動先が見える。"""
    _make_dead(runtime, _SENA, "greenhouse")
    _place_living(runtime, _AOI, "storage")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))

    living_text = runtime.build_observation(_AOI)
    departed_text = runtime.build_observation(_SENA)

    assert '"セナ"' not in living_text
    assert "現在地: 物資庫" in departed_text
    assert '"アオイ"' in departed_text
    assert EntityId.create(int(_SENA)) not in runtime._spot_graph_repo.find_graph().presence_at(
        _spot(runtime, "storage")
    ).present_entity_ids


def test_departed_position_does_not_count_as_physical_presence(runtime) -> None:
    """別位置の幽霊は PLAYERS_AT_SPOT の協力人数へ混ざらない。"""
    _make_dead(runtime, _SENA, "greenhouse")
    _place_living(runtime, _AOI, "storage")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    storage = runtime._spot_interior_repo.find_by_spot_id(_spot(runtime, "storage"))
    assert storage is not None
    lantern_case = next(
        obj for obj in storage.objects if obj.name == "非常用ランタンケース"
    )
    take_lantern = next(
        interaction
        for interaction in lantern_case.interactions
        if interaction.action_name == "take_lantern"
    )
    two_people_required = replace(
        take_lantern,
        allowed_actor_planes=(
            InteractionActorPlane.LIVING,
            InteractionActorPlane.DEPARTED,
        ),
        preconditions=take_lantern.preconditions
        + (
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.PLAYERS_AT_SPOT,
                required_player_count=2,
                failure_message="二人いなければ扱えない。",
            ),
        ),
    )
    runtime._spot_interior_repo.save(
        _spot(runtime, "storage"),
        storage.replace_object(
            replace(lantern_case, interactions=(two_people_required,))
        ),
    )

    with pytest.raises(Exception, match="二人いなければ"):
        runtime.do_interact(_SENA, "emergency_lantern_case", "take_lantern")


def test_departed_player_can_move_without_moving_the_body(runtime) -> None:
    """幽霊の移動完了は別位置だけを変え、身体を倒れた場所に残す。"""
    _make_dead(runtime, _SENA, "corridor")

    runtime.do_move(_SENA, "storage")
    for _ in range(10):
        runtime.advance_tick()
        if runtime.get_player_spot_name(_SENA) == "物資庫":
            break

    assert runtime.get_player_spot_name(_SENA) == "物資庫"
    assert runtime._fallen_body_registry.find(_SENA).spot_id == _spot(
        runtime, "corridor"
    )
    assert runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(_SENA))
    ) == _spot(runtime, "corridor")


def test_missing_departed_position_never_falls_back_to_moving_the_body(runtime) -> None:
    """DEAD の別位置が欠けた不整合時は、身体の物理位置を移動に使わず止まる。"""
    _place_living(runtime, _SENA, "corridor")
    status = runtime._player_status_repo.find_by_id(_SENA)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(_SENA, PlayerOutcomeEnum.DEAD)

    with pytest.raises(RuntimeError, match="去った主体の位置がありません"):
        runtime.do_move(_SENA, "storage")

    assert runtime.get_player_spot_id(_SENA) is None
    assert runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(_SENA))
    ) == _spot(runtime, "corridor")


def test_departed_player_can_complete_their_declared_task(runtime) -> None:
    """死亡した通信担当が三段階を終えると、共有世界の task_grow_light_wiring が立つ。"""
    _make_dead(runtime, _SENA, "greenhouse")

    for action_name in (
        "inspect_grow_light_wiring",
        "inspect_grow_light_wiring_2",
        "inspect_grow_light_wiring_3",
    ):
        runtime.do_interact(_SENA, "grow_lights", action_name)

    assert "task_grow_light_wiring" in runtime._world_flag_state.as_frozen_set()


def test_restore_power_explicitly_requires_a_living_actor() -> None:
    """主配電盤の復旧操作は既定値に頼らず、生者だけが使えると宣言する。"""
    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    restore_power = next(
        interaction
        for spot in raw["spots"]
        for obj in spot.get("interior", {}).get("objects", [])
        for interaction in obj.get("interactions", [])
        if interaction.get("action_name") == "restore_power"
    )

    assert restore_power["allowed_actor_planes"] == ["LIVING"]


def test_departed_wrong_action_guidance_does_not_reveal_living_only_action(
    runtime,
) -> None:
    """候補に出ない生者専用操作は、幽霊が名前を誤ったときの案内にも出ない。"""
    _make_dead(runtime, _SENA, "machine_room")

    result = _interact_with_main_distribution_panel(
        runtime, _SENA, "restore_lighting"
    )

    assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
    assert "restore_power" not in result.message


def test_living_wrong_action_guidance_keeps_the_visible_restore_action(
    runtime,
) -> None:
    """生者には候補表示と同じ restore_power を誤入力時の案内にも残す。"""
    _place_living(runtime, _HAGI, "machine_room")

    result = _interact_with_main_distribution_panel(
        runtime, _HAGI, "restore_lighting"
    )

    assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
    assert "restore_power" in result.message


def test_departed_restore_refusal_explains_that_a_living_body_is_required(
    runtime,
) -> None:
    """幽霊が復旧を呼ぶと、曖昧な不能でなく生きた体が要る理由を返す。"""
    _make_dead(runtime, _SENA, "machine_room")

    result = _interact_with_main_distribution_panel(
        runtime, _SENA, "restore_power"
    )

    assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
    assert "生きた体が要る" in result.message


def test_departed_restore_refusal_explains_which_tasks_can_continue(runtime) -> None:
    """幽霊の復旧拒否は、失われていない自分の担当と共通点検も伝える。"""
    _make_dead(runtime, _SENA, "machine_room")

    result = _interact_with_main_distribution_panel(
        runtime, _SENA, "restore_power"
    )

    assert "自分の担当と共通の点検" in result.message


def test_departed_restore_refusal_has_its_own_trace_classification(runtime) -> None:
    """存在層の拒否は一般の前提不足へ混ぜず、actor_plane として記録する。"""
    _make_dead(runtime, _SENA, "machine_room")

    result = _interact_with_main_distribution_panel(
        runtime, _SENA, "restore_power"
    )

    assert result.trace_payload == {"precondition_failure_kind": "actor_plane"}


def test_departed_state_reaches_the_actual_turn_prompt(runtime) -> None:
    """幽霊の存在状態は補助表示でなく、実際の手番の user prompt に届く。"""
    _make_dead(runtime, _SENA, "greenhouse")

    text = _user_prompt(runtime, _SENA)

    assert "【いまの存在状態】" in text
    assert "生きている者には姿が見えず、声も届かない" in text


def test_departed_prompt_omits_the_physical_body_section(runtime) -> None:
    """幽霊の手番では HP・空腹・疲労を含む身体の状態を表示しない。"""
    _make_dead(runtime, _SENA, "corridor")

    text = _user_prompt(runtime, _SENA)

    assert "身体の状態" not in text
    assert "HP: 0/100" not in text
    assert "空腹" not in text
    assert "疲労" not in text


def test_departed_action_does_not_accumulate_fatigue(runtime) -> None:
    """幽霊が実ツール境界から作業しても、死後の身体へ疲労を加算しない。"""
    _make_dead(runtime, _SENA, "greenhouse")
    _place_living(runtime, _AOI, "storage")
    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")
    _place_living(runtime, _AOI, "greenhouse")
    wiring = _wiring(runtime)
    context = runtime.build_llm_context(_SENA).tool_runtime_context
    target_label = next(
        label
        for label, target in context.targets.items()
        if getattr(target, "display_name", "") == "照明設備"
    )
    before = runtime._player_status_repo.find_by_id(_SENA).fatigue_value

    result = wiring._execute_tool(
        _SENA,
        "interact",
        {"target_label": target_label, "action_name": "inspect_grow_light_wiring"},
        context,
        offered_tool_names_at_prompt=frozenset({"interact"}),
    )

    assert result.success is True
    status = runtime._player_status_repo.find_by_id(_SENA)
    assert status.fatigue_value == before
    assert status.hp.value == 0
    assert status.is_down is True


def test_departed_player_sees_their_own_body_without_a_tool_target(runtime) -> None:
    """幽霊は同じ場所の自分の亡骸を知るが、通報・略奪の対象にはできない。"""
    _make_dead(runtime, _AOI, "storage")

    text = _user_prompt(runtime, _AOI)
    context = runtime.build_llm_context(_AOI).tool_runtime_context

    assert text.count('"アオイ" (あなたの亡骸)') == 1
    own_body_row = next(
        line for line in text.splitlines() if '"アオイ" (あなたの亡骸)' in line
    )
    assert "loot_from_downed" not in own_body_row
    assert "report_body" not in own_body_row
    assert all(
        getattr(target, "player_id", None) != int(_AOI)
        for target in context.targets.values()
    )


def test_departed_victim_is_told_they_can_move_without_learning_the_killer(runtime) -> None:
    """幽霊化した被害者には移動可能性と非対称な知覚を伝え、加害者名は伏せる。"""
    _place_living(runtime, _KUZE, "corridor")
    _place_living(runtime, _SENA, "corridor")
    darken_spot(runtime)
    before = len(runtime._obs_buffer.get_observations(_SENA))

    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

    entries = runtime._obs_buffer.get_observations(_SENA)[before:]
    downed = next(
        entry.output
        for entry in entries
        if entry.output.structured.get("type") == "player_downed"
    )
    assert "死亡した後も移動できる" in downed.prose
    assert "生きている者には姿が見えず、声も届かない" in downed.prose
    assert "クゼ" not in downed.prose
    assert "killer_player_id" not in downed.structured


def test_departed_player_is_offered_only_their_physical_capabilities(runtime) -> None:
    """幽霊には移動・作業・発話・待機・傾聴だけを出し、取得や対人操作を宣伝しない。"""
    darken_spot(runtime, "greenhouse")
    _make_dead(runtime, _SENA, "greenhouse")
    dark_ui = runtime.build_llm_context(_SENA)
    _place_living(runtime, _AOI, "storage")
    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")
    _place_living(runtime, _AOI, "greenhouse")
    _make_downed(runtime, _AOI, "greenhouse")

    tools = {definition.name for definition in runtime.get_tool_definitions(player_id=_SENA)}
    ui = runtime.build_llm_context(_SENA)
    text = ui.current_state_text

    assert {"travel_to", "interact", "speak", "wait", "listen"} <= tools
    assert {"pickup_item", "give_item", "report_body"}.isdisjoint(tools)
    assert not any(
        "inspect_grow_light_wiring" in target.available_interactions
        for target in dark_ui.tool_runtime_context.targets.values()
    )
    assert any(
        "inspect_grow_light_wiring" in target.available_interactions
        for target in ui.tool_runtime_context.targets.values()
    )
    assert "take_lantern" not in text
    assert "loot_from_downed" not in text
    assert "tend_to_player" not in text
    assert "生きている者には姿が見えず、声も届かない" in text


@pytest.mark.parametrize(
    ("departed", "in_meeting", "voted"),
    [
        pytest.param(False, False, False, id="living_free_roam"),
        pytest.param(False, True, False, id="living_meeting_before_vote"),
        pytest.param(False, True, True, id="living_meeting_after_vote"),
        pytest.param(True, False, False, id="departed_free_roam"),
        pytest.param(True, True, False, id="departed_meeting"),
    ],
)
@pytest.mark.parametrize(
    "include_todo_tools",
    [
        pytest.param(True, id="with_memory_tools"),
        pytest.param(False, id="without_memory_tools"),
    ],
)
def test_actual_payload_keeps_the_always_present_prefix_in_every_observed_state(
    runtime,
    departed: bool,
    in_meeting: bool,
    voted: bool,
    include_todo_tools: bool,
) -> None:
    """run 035 の五状態で、設定上の常在ツールは実 payload の先頭で同順になる。

    記憶ツールを無効にした比較構成では ``wait`` / ``speak`` に続く
    ``listen`` までを実 payload で縛る。死亡時に ``listen`` が落ちる退行は、
    長い記憶ツール定義が間に無い構成で初めて接頭辞の差として表れるためである。
    """
    if not include_todo_tools:
        runtime = create_world_runtime(_SCENARIO, include_todo_tools=False)
    player_id = _SENA if departed else _MORI
    if departed:
        _make_dead(runtime, player_id, "hall")
    if in_meeting:
        runtime.begin_meeting(
            initiator_player_id=_KUZE,
            trigger="emergency_button",
        )
    if voted:
        runtime.cast_vote(player_id, _KUZE)

    names = [
        tool["function"]["name"]
        for tool in _wiring(runtime)._build_tools_payload(player_id)
    ]

    expected_prefix = ["wait", "speak"]
    if include_todo_tools:
        expected_prefix += ["memo_add", "memo_list", "memo_done"]
    else:
        expected_prefix += ["listen"]
    assert names[: len(expected_prefix)] == expected_prefix


def test_departed_player_interaction_labels_follow_the_declared_plane(runtime) -> None:
    """幽霊の対人候補は、対象の条件が揃っても生者専用の宣言から出ない。"""
    _make_dead(runtime, _KUZE, "storage")
    _make_downed(runtime, _AOI, "storage")
    status = runtime._player_status_repo.find_by_id(_KUZE)

    labels = runtime._player_interaction_service.available_action_labels_for(
        target_is_incapacitated=True,
        actor_state=dict(status.state),
        actor_player_id=_KUZE,
    )

    assert all("loot_from_downed" not in label for label in labels)
    assert runtime.available_player_action_names(_KUZE) == ()


def test_departed_prompt_suppresses_player_actions_from_every_provider(runtime) -> None:
    """幽霊の同席者行は、provider が候補を返しても対人行為を表示しない。"""
    _make_dead(runtime, _SENA, "corridor")
    _place_living(runtime, _AOI, "corridor")
    from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
        SpotGraphInteractionEntry,
    )

    runtime._state_builder._player_action_entries_provider = lambda **_kwargs: (
        SpotGraphInteractionEntry(
            action_name="forbidden_action",
            display_label="forbidden_player_action",
        ),
    )

    text = runtime.build_observation(_SENA)

    assert "forbidden_action" not in text


def test_departed_player_interaction_is_rejected_before_other_preconditions(runtime) -> None:
    """幽霊の対人行為は、対象の所持など他の前提条件より先に存在層で拒否する。"""
    _make_dead(runtime, _KUZE, "storage")
    _place_living(runtime, _AOI, "storage")
    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")
    _make_downed(runtime, _AOI, "storage")

    with pytest.raises(InteractionNotAllowedException, match="生きた体が要る"):
        runtime.do_interact_with_player(
            _KUZE,
            _AOI,
            "loot_from_downed",
            interaction_parameters={"item": "手提げランタン"},
        )


def test_undeclared_interaction_is_rejected_for_departed_player(runtime) -> None:
    """生者専用のランタン取得は表示だけでなく実行入口でも拒否する。"""
    _make_dead(runtime, _SENA, "storage")

    with pytest.raises(Exception, match="生きた体が要る"):
        runtime.do_interact(_SENA, "emergency_lantern_case", "take_lantern")


def test_departed_player_cannot_use_the_sabotage_panel(runtime) -> None:
    """幽霊には手元の制御端末を表示せず、直接指定しても隔壁妨害を拒否する。"""
    _make_dead(runtime, _KUZE, "hall")
    terminal = ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )

    prompt = runtime.build_full_prompt(_KUZE)["messages"][1]["content"]
    assert "seal_bulkhead" not in prompt
    with pytest.raises(Exception, match="生きた体が要る"):
        runtime.do_interact_with_item(_KUZE, terminal, "seal_bulkhead")


def test_departed_speech_reaches_departed_but_not_the_living(runtime) -> None:
    """同じ場所の幽霊同士には声が届き、生者には話者の観測が漏れない。"""
    _make_dead(runtime, _SENA, "corridor")
    _make_dead(runtime, _HAGI, "machine_room")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    runtime._departed_position_store.move(_HAGI, _spot(runtime, "storage"))
    _place_living(runtime, _AOI, "storage")
    departed_before = len(runtime._obs_buffer.get_observations(_HAGI))
    living_before = len(runtime._obs_buffer.get_observations(_AOI))

    runtime.do_say(_SENA, "配線は続けられる")

    departed = runtime._obs_buffer.get_observations(_HAGI)[departed_before:]
    living = runtime._obs_buffer.get_observations(_AOI)[living_before:]
    assert any("配線は続けられる" in entry.output.prose for entry in departed)
    assert all("配線は続けられる" not in entry.output.prose for entry in living)


def test_world_actions_follow_the_same_perception_matrix(runtime) -> None:
    """同じ場所の生者の行為は幽霊へ届き、幽霊の行為は生者へ漏れない。"""
    _make_dead(runtime, _SENA, "greenhouse")
    _place_living(runtime, _KUZE, "greenhouse")
    living_before = len(runtime._obs_buffer.get_observations(_KUZE))

    runtime.do_interact(_SENA, "grow_lights", "inspect_grow_light_wiring")

    living = runtime._obs_buffer.get_observations(_KUZE)[living_before:]
    assert all("照明設備の配線を点検している" not in entry.output.prose for entry in living)

    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    _place_living(runtime, _AOI, "storage")
    departed_before = len(runtime._obs_buffer.get_observations(_SENA))

    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")

    departed = runtime._obs_buffer.get_observations(_SENA)[departed_before:]
    assert any("非常用ランタンケースを開けた" in entry.output.prose for entry in departed)
