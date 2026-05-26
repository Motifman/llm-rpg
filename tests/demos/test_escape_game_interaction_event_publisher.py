"""Issue #227 PR 6: SpotInteractionApplicationService に event_publisher を配線した動作確認 E2E。

Agent C #2 で発見された CRITICAL bug の修正。旧コードでは
``SpotInteractionApplicationService`` を ``event_publisher=None`` で構築
していたため、interaction が graph に積んだ ``ConnectionStateChangedEvent``
/ ``SpotObjectInteractedEvent`` / ``SpotPublicEffectObservedEvent`` 等が
``execute_interaction`` 内で extract & clear された後に publish されず
silent drop していた。

本 PR で ``_PipelineEventPublisher`` を作り、speech と interaction の両方
で共有することにより、ObservationPipeline 経由で各 recipient の buffer
に届けるようにする。

(注) 同時に PR 2 の handler-per-event-type アプローチを刷新している。
本テストは interaction 経路だけを対象とする。speech 経路は
``test_escape_game_speech_via_domain_event.py`` でカバー済み。
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from demos.escape_game.escape_game_runtime import create_escape_game_runtime


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"


class TestEscapeGameInteractionEventPublisher:
    """interaction 経由で fire する graph event が ObservationPipeline に届く。"""

    def test_interaction_emits_event_to_other_player_at_same_spot(self) -> None:
        """relay_puzzle: カイトが制御室の操作盤を power_on すると、同スポットに
        いるオブザーバー (player_id=2 リン) の observation buffer にも
        SpotPublicEffectObservedEvent / SpotObjectInteractedEvent 経由の
        観測が届くはず。

        旧 event_publisher=None では一切届かなかった (silent drop)。
        本 PR で接続後、何らかの観測 entry が buffer に積まれていることを
        確認する。
        """
        runtime = create_escape_game_runtime(_RELAY_PUZZLE)

        # relay_puzzle_demo: カイト (1) は制御室 (spot 1) spawn、リン (2) は
        # 廊下 (spot 2) spawn。同スポットに移して観測対象にする。
        graph = runtime._spot_graph_repo.find_graph()
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        # カイトの現スポット (= 制御室) を取得し、リンも同じ spot に移す
        kaito_spot = graph.get_entity_spot(EntityId.create(1))
        graph.unplace_entity(EntityId.create(2))
        graph.place_entity(EntityId.create(2), kaito_spot)
        runtime._spot_graph_repo.save(graph)

        # interaction を実行 (操作盤の電源を入れる)
        result = runtime.do_interact(
            PlayerId(1),
            "control_panel",
            "power_on",
        )
        assert result.messages

        # リンの観測バッファに spot_object_interacted / spot_public_effect の
        # いずれかが届いているはず。
        # chore (#240 後続): 旧 assert は `len > 0` だけで偽陽性リスク (scenario_event
        # 警告などが紛れていても通る) があったため、type を明示的に絞る。
        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        interaction_related = [
            e
            for e in rin_entries
            if e.output.structured.get("type")
            in {"spot_object_interacted", "spot_public_effect"}
        ]
        assert len(interaction_related) > 0, (
            "BUG: 同スポットのリンに interaction の observation が届いていない. "
            "SpotInteractionApplicationService.event_publisher が未配線の可能性。"
            f"buffer entries={rin_entries}"
        )

    def test_interaction_does_not_leak_to_player_at_different_spot(self) -> None:
        """別スポットのプレイヤーには interaction 観測が届かない (gating 確認)。"""
        runtime = create_escape_game_runtime(_RELAY_PUZZLE)

        # 既定 spawn: カイト=制御室, リン=廊下 — 別スポット
        result = runtime.do_interact(
            PlayerId(1),
            "control_panel",
            "power_on",
        )
        assert result.messages

        # 別スポットのリンに spot_object_interacted 観測は届かない
        rin_entries = runtime._obs_buffer.get_observations(PlayerId(2))
        interacted = [
            e
            for e in rin_entries
            if e.output.structured.get("type") == "spot_object_interacted"
        ]
        assert interacted == [], (
            f"BUG: 別スポットのリンに interaction 観測が漏れている: {interacted}"
        )
