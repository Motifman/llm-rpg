"""Issue #227 PR 2: speech 配信が PlayerSpokeEvent 経路で距離 gating されることの E2E テスト。

旧コード (``_append_agent_speech``) は ``runtime.get_player_ids()`` で取得
した全プレイヤーへ直接 ObservationContextBuffer に append しており、
SoundPropagationService の hop 制限が完全にスキップされていた。
本 PR で speech は ``PlayerSpeechApplicationService.speak()`` 経由で
``PlayerSpokeEvent`` を fire し、ObservationPipeline → SpotGraphSpeech
RecipientStrategy で hop-based に gating される。

E2E テストとして以下を検証する:
1. 1 hop 以内の listener には observation が届く
2. 2+ hop 先の listener には observation が届かない
3. 話者自身の buffer には observation が積まれない (自己三人称ループ抑止)
"""

from __future__ import annotations

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

from tests.demos._world_runtime_helpers import (
    FORBIDDEN_LIBRARY_PATH as _FORBIDDEN_LIBRARY,
    name_to_spot_id as _name_to_spot_id,
    teleport as _teleport,
)


class TestWorldRuntimeSpeechViaDomainEvent:
    """do_say が PlayerSpokeEvent 経由で距離 gating する。"""

    def test_say_delivers_to_listener_at_same_spot(self) -> None:
        """同 spot の相手は speech_say を受け取る (旧 _append_agent_speech と同じ
        behavior、ただし配信経路は pipeline 経由になっている)。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        reading_room_id = _name_to_spot_id(runtime, "閲覧室")
        # カイト (1) を閲覧室へ。リン (2) は元から閲覧室 spawn
        _teleport(runtime, 1, reading_room_id)

        runtime.do_say(PlayerId(1), "リン、近くにいるか")

        # リン (player 2) の buffer に観測が積まれている
        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        assert any(
            e.output.structured.get("type") == "player_spoke"
            and "リン、近くにいるか" in e.output.structured.get("content", "")
            for e in rin_entries
        ), (
            f"BUG: 同スポットのリンに speech observation が届いていない. "
            f"buffer entries={rin_entries}"
        )

    def test_say_does_not_reach_listener_two_hops_away(self) -> None:
        """SAY は max_hops=1。書架 A (4) → 閲覧室 (2) は 2 hop なので届かない。

        旧 _append_agent_speech では距離無視で届いていたバグの回帰防止。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        shelf_a_id = _name_to_spot_id(runtime, "書架 A")
        _teleport(runtime, 1, shelf_a_id)
        # リン (2) は閲覧室 spawn のまま

        runtime.do_say(PlayerId(1), "ヴェル・ノクト")

        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        leaked = [
            e
            for e in rin_entries
            if e.output.structured.get("type") == "player_spoke"
            and "ヴェル・ノクト" in e.output.structured.get("content", "")
        ]
        assert leaked == [], (
            f"BUG: 2 hop 先のリンに speech が漏れている. "
            f"leaked={leaked} (max_hops=1 のはず)"
        )

    def test_say_does_not_reach_listener_five_hops_away(self) -> None:
        """館長書斎 (8) → 閲覧室 (2) は 5 hop。第13/14回実験で観測された
        遠距離 broadcast バグが復活していないことを確認。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        master_study_id = _name_to_spot_id(runtime, "館長書斎")
        _teleport(runtime, 1, master_study_id)

        runtime.do_say(PlayerId(1), "館長書斎にたどり着いたぞ")

        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        leaked = [
            e
            for e in rin_entries
            if "館長書斎にたどり着いたぞ" in e.output.structured.get("content", "")
        ]
        assert leaked == [], (
            f"BUG: 5 hop 先まで speech が漏れている (旧 _append_agent_speech バグの再侵入). "
            f"leaked={leaked}"
        )

    def test_speaker_buffer_does_not_receive_self_observation(self) -> None:
        """formatter が is_self=True で None を返すため、話者本人には
        三人称 observation が積まれない (Issue #188 第5回の自己三人称ループ抑止)。
        話者は action_result_store 経由で一人称 summary を受け取る前提。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        reading_room_id = _name_to_spot_id(runtime, "閲覧室")
        _teleport(runtime, 1, reading_room_id)

        runtime.do_say(PlayerId(1), "私はカイトだ")

        kaito_entries = runtime._obs_buffer.get_observations(PlayerId(1))
        self_entries = [
            e
            for e in kaito_entries
            if e.output.structured.get("type") == "player_spoke"
        ]
        assert self_entries == [], (
            f"BUG: 話者自身の buffer に三人称 speech observation が積まれている. "
            f"self_entries={self_entries}"
        )

    def test_whisper_delivers_only_to_target_player(self) -> None:
        """whisper は target_player_id 指定で同スポットの宛先のみに届く。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        reading_room_id = _name_to_spot_id(runtime, "閲覧室")
        _teleport(runtime, 1, reading_room_id)

        runtime.do_whisper(PlayerId(1), "秘密の話", PlayerId(2))

        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        assert any(
            "秘密の話" in e.output.structured.get("content", "")
            for e in rin_entries
        ), "whisper が宛先リンに届いていない"
