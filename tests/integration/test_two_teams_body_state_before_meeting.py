"""互いを知らない 2 つの班に、会う前の相手が倒れた・復帰した・倒れているのを見つけた観測から名前も存在も届かないことを保証する (#1531)。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "two_teams_unaware.json"


def _ids_by_name(runtime) -> dict[str, PlayerId]:
    return {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}


def _recent_events(runtime, player_id: PlayerId) -> str:
    user = runtime.build_full_prompt(player_id)["messages"][1]["content"]
    return user.split("【直近の出来事】", 1)[1].split("【", 1)[0]


def _down(runtime, player_id: PlayerId) -> None:
    """観測配信に状態更新を委ねず、整合したダウン状態を準備する。"""
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    events = list(status.get_events())
    status.clear_events()
    runtime._player_status_repo.save(status)
    current_tick = int(runtime.current_tick())
    spot_id = runtime._spot_graph_repo.find_graph().get_entity_spot(EntityId.create(int(player_id)))
    runtime._fallen_body_registry.record(player_id, spot_id, WorldTick(current_tick))
    runtime._death_grace_timer.register(player_id, downed_at_tick=current_tick)
    runtime._speech_event_publisher.publish_all(events)


def _revive(runtime, player_id: PlayerId) -> None:
    runtime._speech_event_publisher.publish(
        PlayerRevivedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=10,
            total_hp=10,
            caregiver_player_id=None,
        )
    )


def _walk(runtime, player_id: PlayerId, *spots: str) -> None:
    for spot in spots:
        runtime.do_move(player_id, spot)
        runtime.advance_until_player_idle(player_id)


class TestBeforeMeeting:
    """会う前の相手が倒れても復帰しても、遠くの班には名前も気配も届かないことを保証する。"""

    def test_remote_stranger_going_down_reaches_nobody_in_the_other_camp(self) -> None:
        """西のゲンジが倒れても、東のミナトのプロンプトには名前も「倒れた気配」も出ない。同じ野営地のサヤには名前付きで届く。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        _down(runtime, ids["ゲンジ"])

        minato = runtime.build_full_prompt(ids["ミナト"])["messages"][1]["content"]
        assert "ゲンジ" not in minato
        assert "倒れた気配" not in minato
        assert "ゲンジが倒れて動かなくなった。" in _recent_events(runtime, ids["サヤ"])

    def test_remote_stranger_reviving_reaches_nobody_in_the_other_camp(self) -> None:
        """西のゲンジが倒れて復帰しても、東のミナトのプロンプトには名前も「動けるようになった気配」も出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _down(runtime, ids["ゲンジ"])

        _revive(runtime, ids["ゲンジ"])

        minato = runtime.build_full_prompt(ids["ミナト"])["messages"][1]["content"]
        assert "ゲンジ" not in minato
        assert "動けるようになった気配" not in minato

    def test_finding_a_stranger_lying_there_is_someone(self) -> None:
        """ミナトが西の野営地で倒れているゲンジを見つけると、直近の出来事には「誰かが倒れているのを見つけた」と残り、名前は出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _down(runtime, ids["ゲンジ"])
        _walk(runtime, ids["ミナト"], "pass", "camp_west")

        runtime.build_full_prompt(ids["ミナト"])
        events = _recent_events(runtime, ids["ミナト"])

        assert "誰かが倒れているのを見つけた。" in events
        assert "ゲンジ" not in events


class TestFindingTheDead:
    """死んでいる相手を見つけた観測も、会っていなければ名前を伏せ、動かないことは残すことを保証する。"""

    def test_finding_a_dead_stranger_is_someone_who_does_not_move(self) -> None:
        """会っていないゲンジの死体を見つけたミナトには「誰かが倒れているのを見つけた。動かない。」と届き、名前は出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        observe = runtime._state_builder._fallen_body_observer

        observe(int(ids["ミナト"]), int(ids["ゲンジ"]), "ゲンジ", True)

        events = _recent_events(runtime, ids["ミナト"])
        assert "誰かが倒れているのを見つけた。動かない。" in events
        assert "ゲンジ" not in events

    def test_finding_a_dead_teammate_names_them(self) -> None:
        """紹介された仲間サヤの死体を見つけたゲンジには「サヤが倒れているのを見つけた。動かない。」と届く。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        observe = runtime._state_builder._fallen_body_observer

        observe(int(ids["ゲンジ"]), int(ids["サヤ"]), "サヤ", True)

        assert "サヤが倒れているのを見つけた。動かない。" in _recent_events(runtime, ids["ゲンジ"])


class TestAfterMeeting:
    """会ったあとの相手が倒れたら、遠くの気配も、倒れているのを見つけた観測も届くことを保証する。"""

    def test_finding_someone_met_lying_there_describes_them(self) -> None:
        """西の野営地でゲンジと会ってから峠に戻ったミナトが、倒れたゲンジのところへ戻ると、名前は知らないので見た目で「髭の濃い大柄な人が倒れているのを見つけた」と残る (#1581)。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _walk(runtime, ids["ミナト"], "pass", "camp_west", "pass")
        _down(runtime, ids["ゲンジ"])
        _walk(runtime, ids["ミナト"], "camp_west")

        runtime.build_full_prompt(ids["ミナト"])

        assert "髭の濃い大柄な人が倒れているのを見つけた。" in _recent_events(runtime, ids["ミナト"])

    def test_remote_acquaintance_going_down_is_felt(self) -> None:
        """西の野営地でゲンジと会ってから峠に戻ったミナトには、ゲンジが倒れると「遠くで誰かが倒れた気配」が届く。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _walk(runtime, ids["ミナト"], "pass", "camp_west", "pass")

        _down(runtime, ids["ゲンジ"])

        assert "遠くで誰かが倒れた気配がした。" in _recent_events(runtime, ids["ミナト"])
