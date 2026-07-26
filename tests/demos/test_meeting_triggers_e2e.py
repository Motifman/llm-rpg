"""エージェント自身の判断で会議を開けることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 4。
ここまでは招集の口が無く、会議は runtime を直接叩かないと始まらなかった。

## 失敗は学習可能でなければならない

「押せない」理由が返らないと、LLM は同じ手を繰り返す。#860 で潰した
「使えない候補を試し続ける」形と同じなので、拒否のときは**何が足りないか**を
文で返す。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _spot_of(runtime, player_id: PlayerId):
    graph = runtime._spot_graph_repo.find_graph()
    return graph.get_entity_spot(EntityId.create(int(player_id)))


def _pass_ticks(runtime, count: int) -> None:
    for _ in range(count):
        runtime.advance_tick()


def _knock_down(runtime, player_id: PlayerId) -> None:
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)


class TestEmergencyButton:
    """緊急ボタンで会議が始まる。"""

    def test_pressing_starts_a_meeting(self, runtime) -> None:
        """押すと会議になる。"""
        result = runtime.call_emergency_meeting(_KUZE)

        assert result.success is True
        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_the_card_is_spent(self, runtime) -> None:
        """一度押すと持ち札が減る。"""
        runtime.call_emergency_meeting(_KUZE)

        assert runtime._game_phase_store.has_emergency_button(_KUZE) is False

    def test_second_press_by_the_same_player_is_refused(self, runtime) -> None:
        """同じ人は二度押せない。理由が文で返る。"""
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")
        _pass_ticks(runtime, runtime._game_phase_store.MEETING_COOLDOWN_TICKS + 1)

        result = runtime.call_emergency_meeting(_KUZE)

        assert result.success is False
        assert result.message

    def test_another_player_can_still_press(self, runtime) -> None:
        """別の人の持ち札は残っている。"""
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")
        _pass_ticks(runtime, runtime._game_phase_store.MEETING_COOLDOWN_TICKS + 1)

        assert runtime.call_emergency_meeting(_MORI).success is True


class TestCooldown:
    """会議直後は誰も招集できない。"""

    def test_pressing_during_cooldown_is_refused(self, runtime) -> None:
        """終了直後は、持ち札のある人でも押せない。"""
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")

        result = runtime.call_emergency_meeting(_MORI)

        assert result.success is False
        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_after_the_cooldown_it_works(self, runtime) -> None:
        """既定 tick 経てば押せる。"""
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")
        _pass_ticks(runtime, runtime._game_phase_store.MEETING_COOLDOWN_TICKS)

        assert runtime.call_emergency_meeting(_MORI).success is True


class TestBodyReport:
    """死体を見つけたら報告できる。"""

    def _put_body_next_to(self, runtime, reporter: PlayerId, body: PlayerId) -> None:
        graph = runtime._spot_graph_repo.find_graph()
        graph.unplace_entity(EntityId.create(int(body)))
        graph.place_entity(EntityId.create(int(body)), _spot_of(runtime, reporter))
        runtime._spot_graph_repo.save(graph)
        _knock_down(runtime, body)

    def test_reporting_starts_a_meeting(self, runtime) -> None:
        """同じ場所の倒れた相手を報告すると会議になる。"""
        self._put_body_next_to(runtime, _MORI, _SENA)

        result = runtime.report_body(_MORI, _SENA)

        assert result.success is True
        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_reporting_ignores_the_cooldown(self, runtime) -> None:
        """会議直後でも報告できる。

        死体は世界の事実であって、招集の濫用ではない (設計 doc §6.3)。
        """
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")
        self._put_body_next_to(runtime, _MORI, _SENA)

        assert runtime.report_body(_MORI, _SENA).success is True

    def test_the_same_body_cannot_be_reported_twice(self, runtime) -> None:
        """同じ死体で二度は開けない。"""
        self._put_body_next_to(runtime, _MORI, _SENA)
        runtime.report_body(_MORI, _SENA)
        runtime.end_meeting(reason="vote_concluded")

        result = runtime.report_body(_MORI, _SENA)

        assert result.success is False
        assert result.message

    def test_a_standing_player_is_not_a_body(self, runtime) -> None:
        """立っている相手は報告できない。理由が文で返る。"""
        graph = runtime._spot_graph_repo.find_graph()
        graph.unplace_entity(EntityId.create(int(_SENA)))
        graph.place_entity(EntityId.create(int(_SENA)), _spot_of(runtime, _MORI))
        runtime._spot_graph_repo.save(graph)

        result = runtime.report_body(_MORI, _SENA)

        assert result.success is False
        assert result.message

    def test_a_body_elsewhere_cannot_be_reported(self, runtime) -> None:
        """離れた場所の死体は報告できない (見えていないので)。

        このシナリオは全員が同じ部屋から始まるので、明示的に離す。
        """
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        graph = runtime._spot_graph_repo.find_graph()
        elsewhere = SpotId.create(runtime.id_mapper.get_int("spot", "storage"))
        graph.unplace_entity(EntityId.create(int(_SENA)))
        graph.place_entity(EntityId.create(int(_SENA)), elsewhere)
        runtime._spot_graph_repo.save(graph)
        _knock_down(runtime, _SENA)

        result = runtime.report_body(_MORI, _SENA)

        assert result.success is False


class TestEveryoneGathers:
    """招集で全員が同じ場所に集まる。

    集めないと、発話が hop 越しに届かない相手が出る。**議論に参加できない人が
    構造的に生まれる**ので、会議として成立しない (設計 doc H-3)。

    **このシナリオは全員が同じ部屋から始まる。** 動かさずに検証すると
    `hall == hall` を比べるだけになり、集合処理を丸ごと消しても通る
    (レビューで指摘された。同じ形の空振りを本ファイル内で二度やっている)。
    必ず離してから呼ぶ。
    """

    def _scatter(self, runtime) -> None:
        """招集者以外を別々の部屋へ散らす。"""
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        graph = runtime._spot_graph_repo.find_graph()
        for pid, spot_name in ((_MORI, "storage"), (_SENA, "corridor"), (_AOI, "radio_room")):
            graph.unplace_entity(EntityId.create(int(pid)))
            graph.place_entity(
                EntityId.create(int(pid)),
                SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
            )
        runtime._spot_graph_repo.save(graph)

    def test_all_living_players_end_up_together(self, runtime) -> None:
        """散っていた生存者が招集者の場所へ移動する。"""
        self._scatter(runtime)
        assert len({_spot_of(runtime, p) for p in (_MORI, _SENA, _AOI)}) == 3

        runtime.call_emergency_meeting(_KUZE)

        target = _spot_of(runtime, _KUZE)
        for pid in (_MORI, _SENA, _AOI):
            assert _spot_of(runtime, pid) == target

    def test_the_fallen_stay_where_they_are(self, runtime) -> None:
        """倒れている相手は動かさない。

        会議に参加できない (観測が届かない) 相手を運ぶと、死体の位置という
        手がかりが消える。誰がどこで倒れていたかは推理の材料になる。
        """
        self._scatter(runtime)
        _knock_down(runtime, _SENA)
        before = _spot_of(runtime, _SENA)
        assert before != _spot_of(runtime, _KUZE), "前提が崩れている: 既に同席している"

        runtime.call_emergency_meeting(_KUZE)

        assert _spot_of(runtime, _SENA) == before


class TestGatheringSettlesInFlightTravel:
    """移動中の相手を集めても、後の tick が壊れない。

    経路の途中でテレポートすると ``PlayerSpotNavigationState`` に古い出発地と
    残り leg が残る。次の travel stage が「entity は接続の起点に居ない」で
    例外を投げ、**world tick のループごと落ちる**。

    `SpotGraphAggregate.teleport_entity` の docstring が「呼び出し側で移動
    状態を先に解消すること」と警告しているのはこの件で、テレポートを持ち込んだ
    この PR が閉じる責任を負う。レビューで再現手順つきで指摘された。
    """

    def test_world_keeps_ticking_after_gathering_a_traveler(self, runtime) -> None:
        """移動中に招集されても、その後 tick が進む。"""
        runtime.do_move(_SENA, "generator_room")
        runtime.advance_tick()

        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")

        runtime.advance_tick()  # ここで落ちていた

    def test_the_traveler_is_no_longer_in_transit(self, runtime) -> None:
        """集められた本人の移動状態が畳まれている。"""
        runtime.do_move(_SENA, "generator_room")
        runtime.advance_tick()

        runtime.call_emergency_meeting(_KUZE)

        nav = runtime._player_status_repo.find_by_id(_SENA).spot_navigation_state
        assert not nav.is_traveling


class TestRefusalDoesNotChangeTheWorld:
    """拒否されたときは何も動かない。"""

    def test_refused_press_leaves_the_phase_alone(self, runtime) -> None:
        """押せなかったらフェーズは自由時間のまま。"""
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")

        runtime.call_emergency_meeting(_MORI)  # クールダウン中

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_refused_press_does_not_spend_the_card(self, runtime) -> None:
        """押せなかったら持ち札も減らない。

        減らすと、クールダウンに当たっただけで持ち札を失う。
        """
        runtime.call_emergency_meeting(_KUZE)
        runtime.end_meeting(reason="vote_concluded")

        runtime.call_emergency_meeting(_MORI)  # クールダウン中

        assert runtime._game_phase_store.has_emergency_button(_MORI) is True
