"""倒れた相手から持ち物を奪う経路が、シナリオ宣言から実際の移動まで通る。

実 run のボトルネックが背景にある。山頂で仲間が倒れ、その荷物 (狼煙に要る
流木) を回収できずに救助が失敗した。PR #824 で「誰が何を持ったまま倒れて
いるか」が見えるようになったので、本テストは**回収そのもの**を固定する。

宣言はシナリオ直下の ``player_interactions`` に 1 回だけ書き、「起きている
相手からは奪えない」は前提条件で表現する
(docs/memory_system/interpersonal_interaction_design.md §3.2)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_VICTIM = PlayerId(2)
_BYSTANDER = PlayerId(3)

_TAKE_DEF = {
    "action_name": "loot_from_downed",
    "display_label": "持ち物を奪う",
    "preconditions": [
        {
            "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
            "failure_message": "相手は動いている。奪えない。",
        },
        {
            "condition_type": "TARGET_HAS_ITEM",
            "item_spec_id_parameter_key": "item_spec_id",
            "failure_message": "相手はそれを持っていない。",
        },
    ],
    "effects": [
        {
            "effect_type": "REMOVE_ITEM",
            "target": "TARGET_PLAYER",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
        {
            "effect_type": "GIVE_ITEM",
            "target": "ACTOR",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
    ],
}


def _scenario_dict(extra_players=()) -> dict:
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["player_interactions"] = [_TAKE_DEF]
    scenario["players"] = list(scenario["players"]) + list(extra_players)
    return scenario


def _runtime_from(scenario: dict, tmp_path: Path, *, gather: tuple):
    """``gather`` の player を全員 actor と同じスポットに揃えた runtime。"""
    path = tmp_path / "relay_with_take.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    for pid in gather:
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(EntityId.create(int(pid)), actor_spot)
    rt._spot_graph_repo.save(graph)
    return rt


@pytest.fixture()
def runtime_with_bystander(tmp_path: Path):
    """奪う二人に加えて、起きている第三者が同席している runtime。"""
    scenario = _scenario_dict(
        extra_players=[
            {
                "id": "player_c",
                "name": "ミナ",
                "spawn_spot": "corridor",
                "initial_items": [],
            }
        ]
    )
    return _runtime_from(scenario, tmp_path, gather=(_VICTIM, _BYSTANDER))


@pytest.fixture()
def runtime(tmp_path: Path):
    """take を宣言したシナリオで、両者を同じスポットに揃えた runtime。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["player_interactions"] = [_TAKE_DEF]
    path = tmp_path / "relay_with_take.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_VICTIM)))
    graph.place_entity(EntityId.create(int(_VICTIM)), actor_spot)
    rt._spot_graph_repo.save(graph)
    return rt


def _give_victim_an_item(rt) -> tuple[int, str]:
    """被害者に道具を 1 つ持たせ、(spec_id, 表示名) を返す。"""
    specs = list(rt._item_spec_repo.find_all())
    assert specs, "シナリオに item_spec が無い (構造が変わった)"
    spec = specs[0]
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )

    grant_item_specs_to_inventory(
        _VICTIM,
        (spec.item_spec_id,),
        rt._item_repo,
        rt._item_spec_repo,
        rt._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )
    return spec.item_spec_id.value, spec.name


def _knock_out(rt, player_id: PlayerId) -> None:
    status = rt._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    events = list(status.get_events())
    status.clear_events()
    rt._player_status_repo.save(status)
    rt._speech_event_publisher.publish_all(events)


def _owned_spec_ids(rt, player_id: PlayerId) -> set[int]:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        collect_owned_item_spec_ids_from_inventory,
    )

    inv = rt._player_inventory_repo.find_by_id(player_id)
    return {
        s.value
        for s in collect_owned_item_spec_ids_from_inventory(inv, rt._item_repo)
    }


class TestTakeFromFallenPlayer:
    """倒れた相手からの回収が成立する / 起きている相手からは成立しない。"""

    def test_item_moves_from_the_fallen_player_to_the_actor(self, runtime) -> None:
        """倒れた相手の持ち物が、行為者の手元へ移る。"""
        spec_id, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)

        runtime.do_interact_with_player(
            _ACTOR, _VICTIM, "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        assert spec_id in _owned_spec_ids(runtime, _ACTOR)
        assert spec_id not in _owned_spec_ids(runtime, _VICTIM)

    def test_looting_uses_the_recorded_body_location(self, runtime) -> None:
        """倒れた主体を別室へ動かしても、倒れた場所に残る身体から回収できる。"""
        _, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)
        graph = runtime._spot_graph_repo.find_graph()
        body_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
        another_spot = next(
            node.spot_id for node in graph.iter_spot_nodes() if node.spot_id != body_spot
        )
        graph.unplace_entity(EntityId.create(int(_VICTIM)))
        graph.place_entity(EntityId.create(int(_VICTIM)), another_spot)
        runtime._spot_graph_repo.save(graph)

        result = runtime.do_interact_with_player(
            _ACTOR,
            _VICTIM,
            "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        assert result.action_name == "loot_from_downed"

    def test_body_row_uses_the_recorded_location_once(self, runtime) -> None:
        """主体が別室へ動いても倒れた場所に身体行が一つだけ残る。"""
        _knock_out(runtime, _VICTIM)
        graph = runtime._spot_graph_repo.find_graph()
        body_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
        another_spot = next(
            node.spot_id for node in graph.iter_spot_nodes() if node.spot_id != body_spot
        )
        graph.unplace_entity(EntityId.create(int(_VICTIM)))
        graph.place_entity(EntityId.create(int(_VICTIM)), another_spot)
        runtime._spot_graph_repo.save(graph)

        snapshot = runtime._state_builder.build_snapshot(int(_ACTOR))
        body_rows = [
            entry for entry in snapshot.nearby_entities
            if entry.entity_id == int(_VICTIM)
        ]

        assert len(body_rows) == 1
        assert body_rows[0].is_down is True

    def test_body_row_is_not_duplicated_at_the_downed_spot(self, runtime) -> None:
        """entity と身体記録が同地点にあっても、

        身体行は一つだけ出る。
        """
        _knock_out(runtime, _VICTIM)

        snapshot = runtime._state_builder.build_snapshot(int(_ACTOR))
        body_rows = [
            entry
            for entry in snapshot.nearby_entities
            if entry.entity_id == int(_VICTIM)
        ]

        assert len(body_rows) == 1
        assert body_rows[0].is_down is True

    def test_action_result_uses_declared_display_label(self, runtime) -> None:
        """対人行為の直近記録もaction_nameでなくシナリオの意味表示を使う。"""
        _, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)

        result = runtime.do_interact_with_player(
            _ACTOR,
            _VICTIM,
            "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        entry = runtime._action_result_store.get_recent(_ACTOR, 1)[0]
        assert result.action_display_label == "持ち物を奪う"
        assert entry.action_summary == "「リン」に対して持ち物を奪う"

    def test_standing_player_cannot_be_looted(self, runtime) -> None:
        """起きて動いている相手からは奪えない。

        常時スリが成立すると窃盗が作業になって質感が薄れる。奪う前に倒す
        必要が生まれる形にする (ユーザ確定)。
        """
        spec_id, item_name = _give_victim_an_item(runtime)

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(
                _ACTOR, _VICTIM, "loot_from_downed",
                interaction_parameters={"item": item_name},
            )
        assert spec_id not in _owned_spec_ids(runtime, _ACTOR)

    def test_taking_something_the_target_lacks_fails_as_a_precondition(
        self, runtime
    ) -> None:
        """相手が持っていない品目を指定しても、内部エラーではなく前提条件で落ちる。

        「相手はそれを持っていない」は普通に起きる状況で、LLM が次の手を
        選べる形で返す必要がある。
        """
        _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(
                _ACTOR, _VICTIM, "loot_from_downed",
                interaction_parameters={"item": "存在しない架空の道具"},
            )


class TestActorInventoryFull:
    """行為者の手が塞がっているときに、奪った物を消滅させない。"""

    def _fill_inventory(self, rt, player_id: PlayerId) -> None:
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        inv = rt._player_inventory_repo.find_by_id(player_id)
        spec = list(rt._item_spec_repo.find_all())[0]
        free = sum(
            1
            for i in range(inv.max_slots)
            if inv.get_item_instance_id_by_slot(SlotId(i)) is None
        )
        grant_item_specs_to_inventory(
            player_id,
            (spec.item_spec_id,) * free,
            rt._item_repo,
            rt._item_spec_repo,
            rt._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

    def test_full_actor_inventory_fails_before_taking_anything(self, runtime) -> None:
        """空きが無ければ、対象から取り上げる前に前提条件で落とす。

        ``acquire_item`` は満杯のとき黙って捨てる (overflow event を積むだけで
        例外にしない)。先に取り上げてから渡そうとすると、**対象からは消えて
        行為者には入らない** = アイテムが世界から消滅する。しかも成功として
        返るので誰も気づけない。
        """
        spec_id, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)
        self._fill_inventory(runtime, _ACTOR)

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(
                _ACTOR, _VICTIM, "loot_from_downed",
                interaction_parameters={"item": item_name},
            )
        # 対象の持ち物は減っていない
        assert spec_id in _owned_spec_ids(runtime, _VICTIM)


class TestTheftIsObserved:
    """奪う行為が、同席している第三者に届く。

    観測を伴わない対人行為は作らない。state だけ変わって誰にも何も見えないと、
    trace からも効果を確認できず、他のエージェントが反応する機会も無い
    (agent_design_principles.md「他者からの可視性」)。

    **被害者本人には届かない。** 倒れている player は observation の宛先から
    一律に外されている (Issue #621 Phase 4: ターンが回らず観測を消化できず、
    復活時に buffer を clear する仕様と整合させるため)。奪えるのは倒れている
    相手だけなので、被害者は構造的に受け取れない。気を失っている間の出来事を
    知覚しないのは筋が通っているが、「起きたら荷が減っている理由が分からない」
    ままではある。復活時に何が起きたかを渡す経路は別途必要で、本 PR では
    扱わない (設計 doc の notify_target と同じ回)。
    """

    def _theft_observations(self, rt, player_id: PlayerId) -> list:
        return [
            e
            for e in rt._obs_buffer.get_observations(player_id)
            if e.output.structured.get("type") == "player_interacted_with_player"
        ]

    def test_a_standing_bystander_observes_the_theft(
        self, runtime_with_bystander
    ) -> None:
        """同席して起きている第三者に、奪う行為が 1 件届く。"""
        rt = runtime_with_bystander
        _, item_name = _give_victim_an_item(rt)
        _knock_out(rt, _VICTIM)

        rt.do_interact_with_player(
            _ACTOR, _VICTIM, "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        observed = self._theft_observations(rt, _BYSTANDER)
        assert len(observed) == 1
        assert observed[0].output.schedules_turn is True, (
            "目撃しても turn が回らないと、反応する機会そのものが無い"
        )

    def test_the_actor_does_not_observe_their_own_theft(
        self, runtime_with_bystander
    ) -> None:
        """行為者本人には目撃観測を返さない (tool 結果で既に受け取っている)。"""
        rt = runtime_with_bystander
        _, item_name = _give_victim_an_item(rt)
        _knock_out(rt, _VICTIM)

        rt.do_interact_with_player(
            _ACTOR, _VICTIM, "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        assert self._theft_observations(rt, _ACTOR) == []

    def test_the_bystander_prose_names_both_sides(
        self, runtime_with_bystander
    ) -> None:
        """目撃 prose に、誰が誰に何をしたかが出る。"""
        rt = runtime_with_bystander
        _, item_name = _give_victim_an_item(rt)
        _knock_out(rt, _VICTIM)

        rt.do_interact_with_player(
            _ACTOR, _VICTIM, "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        prose = self._theft_observations(rt, _BYSTANDER)[0].output.prose
        assert "カイト" in prose and "リン" in prose
        assert "持ち物を奪う" in prose


class TestVictimLearnsOnWaking:
    """奪われた本人が、意識を取り戻したときに何をされたか読める。

    倒れている player は observation の宛先から一律に外れる (#621 Phase 4)。
    奪えるのは倒れている相手だけなので、被害者はその瞬間には観測できない。
    気を失っている間の出来事を知覚しないのは筋が通るが、起きたあとも永久に
    分からないままだと荷が減った理由を本人が説明できない。
    """

    def _post_hoc_prose(self, rt, player_id: PlayerId) -> str:
        return "\n".join(
            e.output.prose or ""
            for e in rt._obs_buffer.get_observations(player_id)
            if e.output.structured.get("kind") == "player_revived_post_hoc"
        )

    def _revive(self, rt, player_id: PlayerId) -> None:
        status = rt._player_status_repo.find_by_id(player_id)
        status.revive(hp_recovery_rate=0.4, caregiver_player_id=_ACTOR)
        events = list(status.get_events())
        status.clear_events()
        rt._player_status_repo.save(status)
        rt._speech_event_publisher.publish_all(events)

    def test_the_victim_reads_what_was_done_to_them(self, runtime) -> None:
        """目覚めの観測に、誰に何をされたかが出る。"""
        _, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)
        runtime.do_interact_with_player(
            _ACTOR, _VICTIM, "loot_from_downed",
            interaction_parameters={"item": item_name},
        )

        self._revive(runtime, _VICTIM)

        prose = self._post_hoc_prose(runtime, _VICTIM)
        assert "持ち物を奪う" in prose, prose
        assert "形跡" in prose

    def test_waking_without_incidents_says_nothing_extra(self, runtime) -> None:
        """何もされずに起きたときは、余計な文が付かない。"""
        _knock_out(runtime, _VICTIM)

        self._revive(runtime, _VICTIM)

        prose = self._post_hoc_prose(runtime, _VICTIM)
        assert prose, "目覚めの観測そのものは出る"
        assert "形跡" not in prose

    def test_reviving_removes_the_body_from_the_row(self, runtime) -> None:
        """蘇生すると身体記録が消え、同席者行は倒れた身体として描かれない。"""
        _knock_out(runtime, _VICTIM)

        self._revive(runtime, _VICTIM)

        assert runtime._fallen_body_registry.find(_VICTIM) is None
        snapshot = runtime._state_builder.build_snapshot(int(_ACTOR))
        victim = next(
            entry for entry in snapshot.nearby_entities
            if entry.entity_id == int(_VICTIM)
        )
        assert victim.is_down is False
