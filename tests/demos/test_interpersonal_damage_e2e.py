"""人を傷つける行為が、倒れる・死ぬところまで正しく確定することを保証する。

設計 doc (docs/memory_system/interpersonal_interaction_design.md) の H-1 が
「キル経路の最大の罠」として挙げていた箇所である。

``APPLY_DAMAGE`` を対象に適用すると、対象の ``PlayerStatusAggregate`` が HP 0
で ``PlayerDownedEvent`` を内部に積む。これを回収して publish しないと
``PlayerDownedOutcomeHandler`` に届かず、**倒したのに DEAD outcome が確定
しない**。倒れた本人も蘇生猶予に入らず、実験の勝敗判定が静かに壊れる。

物体経由のダメージ (廃屋の梁が落ちる等) では Phase G #3 で同じ罠が既に
潰されている。対人経路でも同じ型 (publisher ガード内で drain → clear →
save → publish) を守る。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_VICTIM = PlayerId(2)

_STRIKE_DEF = {
    "action_name": "strike_down",
    "display_label": "殴り倒す",
    "preconditions": [{"condition_type": "ALWAYS"}],
    "effects": [
        {
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 9999, "message": "強かに打ち据えられた。"},
        }
    ],
}


@pytest.fixture()
def runtime(tmp_path: Path):
    """殴る行為を宣言し、二人を同じスポットに揃えた runtime。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["player_interactions"] = [_STRIKE_DEF]
    path = tmp_path / "relay_with_strike.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_VICTIM)))
    graph.place_entity(EntityId.create(int(_VICTIM)), spot)
    rt._spot_graph_repo.save(graph)
    return rt


class TestDamageReachesTheTarget:
    """ダメージが行為者ではなく対象に入る。"""

    def test_target_hp_drops(self, runtime) -> None:
        """対象の HP が減る。"""
        before = runtime._player_status_repo.find_by_id(_VICTIM).hp.value
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        after = runtime._player_status_repo.find_by_id(_VICTIM).hp.value
        assert after < before

    def test_actor_is_unharmed(self, runtime) -> None:
        """行為者の HP は減らない。

        バケットを分けずに damage_specs へ積むと **行為者に効く**。
        「相手を刺したつもりが自分が傷ついた」という、成功として返る誤動作。
        """
        before = runtime._player_status_repo.find_by_id(_ACTOR).hp.value
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        after = runtime._player_status_repo.find_by_id(_ACTOR).hp.value
        assert after == before

    def test_target_goes_down(self, runtime) -> None:
        """致死量なら対象が行動不能になる。"""
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        assert runtime._player_status_repo.find_by_id(_VICTIM).is_down is True


class TestDownedEventIsDelivered:
    """H-1: 対象が積んだ PlayerDownedEvent が publish される。"""

    def test_downed_event_reaches_the_publisher(self, runtime) -> None:
        """倒したとき PlayerDownedEvent が pipeline に流れる。

        流さないと PlayerDownedOutcomeHandler が走らず、倒したのに DEAD
        outcome が確定しない (設計 doc H-1)。
        """
        seen: list = []
        original = runtime._speech_event_publisher.publish_all

        def spy(events):
            seen.extend(events)
            return original(events)

        runtime._speech_event_publisher.publish_all = spy
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert any(isinstance(e, PlayerDownedEvent) for e in seen), (
            f"PlayerDownedEvent が publish されていない: {[type(e).__name__ for e in seen]}"
        )

    def test_death_grace_timer_starts(self, runtime) -> None:
        """倒された対象が蘇生猶予に入る。

        PlayerDownedOutcomeHandler まで届いたことの、外から見える証拠。
        猶予が始まらないと放置しても DEAD が確定しない。
        """
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        assert runtime._death_grace_timer.is_pending(_VICTIM), (
            "PlayerDownedEvent が handler に届いていない"
        )

    def test_stale_event_is_not_replayed(self, runtime) -> None:
        """一度 publish した PlayerDownedEvent が後から再放出されない。

        save より先に drain + clear しないと、集約が event を持ったまま
        永続化され、後続の find→get_events で陳腐化イベントが二重に流れる。
        """
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        status = runtime._player_status_repo.find_by_id(_VICTIM)
        assert not any(
            isinstance(e, PlayerDownedEvent) for e in status.get_events()
        ), "publish 済みの PlayerDownedEvent が集約に残っている"


class TestFellingBlowIsNotAnIncidentWhileDown:
    """倒した一撃を「倒れている間にされたこと」として記録しない。

    殴られ始めた時点では立っていたので、目覚めの「意識を失っている間の形跡」
    に混ぜるのは事実と違う。しかも倒された事実は PlayerDownedEvent 由来の
    観測で本人に即座に届くので、同じ一撃が二重に語られることになる。

    判定は「その行為の時点で倒れていたか」であって「いま倒れているか」では
    ない。後者で判定すると、致死の一撃は必ず前者に化ける。
    """

    def test_the_knockout_blow_is_not_logged_as_happening_while_down(
        self, runtime
    ) -> None:
        """立っている相手を倒した一撃は、被害記録に残らない。"""
        recorded: list = []
        log = runtime._downed_incident_log
        original = log.record
        log.record = lambda pid, desc: (recorded.append((int(pid), desc)), original(pid, desc))[1]

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert recorded == [], f"倒した一撃が被害記録に混ざっている: {recorded}"

    def test_striking_an_already_downed_target_is_logged(self, runtime) -> None:
        """既に倒れている相手への追撃は、被害記録に残る。

        こちらは本人が観測できないので、起きたときに伝える必要がある。
        """
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")
        recorded: list = []
        log = runtime._downed_incident_log
        original = log.record
        log.record = lambda pid, desc: (recorded.append((int(pid), desc)), original(pid, desc))[1]

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert recorded, "倒れている相手への追撃が記録されていない"


class TestSelfDamageIsNotSilentlyIgnored:
    """対人 action に書いた「行為者自身へのダメージ」も効く。"""

    def test_actor_targeted_damage_applies_to_the_actor(self, tmp_path) -> None:
        """target=ACTOR の APPLY_DAMAGE が行為者の HP を減らす。

        反動や代償のある行為 (殴れば自分の拳も痛む) を書けるようにする。
        受け取っておいて何も起きないのが最悪で、作者は書いたつもりのまま
        気付けない。
        """
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        scenario["player_interactions"] = [{
            "action_name": "reckless_strike",
            "display_label": "捨て身で殴る",
            "preconditions": [{"condition_type": "ALWAYS"}],
            "effects": [
                {"effect_type": "APPLY_DAMAGE", "target": "TARGET_PLAYER",
                 "parameters": {"damage": 5}},
                {"effect_type": "APPLY_DAMAGE", "target": "ACTOR",
                 "parameters": {"damage": 3, "message": "拳が裂けた。"}},
            ],
        }]
        path = tmp_path / "reckless.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
        rt = create_world_runtime(path)
        graph = rt._spot_graph_repo.find_graph()
        spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
        graph.unplace_entity(EntityId.create(int(_VICTIM)))
        graph.place_entity(EntityId.create(int(_VICTIM)), spot)
        rt._spot_graph_repo.save(graph)

        before = rt._player_status_repo.find_by_id(_ACTOR).hp.value
        rt.do_interact_with_player(_ACTOR, _VICTIM, "reckless_strike")

        assert rt._player_status_repo.find_by_id(_ACTOR).hp.value == before - 3
