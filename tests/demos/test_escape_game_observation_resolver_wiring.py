"""Issue #227 PR 1: escape_game runtime の observation resolver 配線テスト。

第13/14回実験で観測された「PlayerSpokeEvent が遠距離まで届く」根本原因の
1 つは、escape_game の resolver が ``SpotGraphRecipientStrategy`` 1 つしか
登録していなかったため、`PlayerSpokeEvent` (strategy_key=\"speech\") が
配信先解決の対象外になっていたことだった。

本テストは ``create_escape_game_runtime`` で組み立てた runtime の
``_obs_pipeline`` が、speech / item_use / 既存 spot_graph 系イベントを
それぞれ正しい strategy にルーティングできることを E2E で検証する。

PR 2 で speech 配信経路 (``_append_agent_speech``) も統一されるが、本 PR
1 ではまず resolver が正しく配線されていることだけを担保する。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

from tests.demos._escape_game_helpers import (
    FORBIDDEN_LIBRARY_PATH as _FORBIDDEN_LIBRARY,
    name_to_spot_id as _name_to_spot_id,
)


class TestEscapeGameObservationResolverWiring:
    """create_escape_game_runtime が組み立てた resolver が全 strategy を持つ。"""

    def test_player_spoke_event_resolves_to_same_spot_listener(
        self,
    ) -> None:
        """同スポットのリスナーが PlayerSpokeEvent の resolve に含まれる。

        SpotGraphSpeechRecipientStrategy が正しく登録されていれば成功する。
        旧バグ (strategy 未登録) では resolve が空になっていた。
        """
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        spot_id_value = _name_to_spot_id(runtime, "閲覧室")

        # forbidden_library のリン (player_id=2) は閲覧室 spawn。speaker と
        # 同スポットに配置するため、player_id=1 (カイト) を一時的に閲覧室へ移す。
        # SpotGraphSpeechRecipientStrategy はグラフ上の entity_spot map と
        # player_status_repository.find_all() (= player_id 一覧) のみを見るため、
        # status の current_spot_id を再同期する必要はない。
        graph = runtime._spot_graph_repo.find_graph()
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph.unplace_entity(EntityId.create(1))
        graph.place_entity(EntityId.create(1), SpotId.create(spot_id_value))
        runtime._spot_graph_repo.save(graph)

        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="hello",
            channel=SpeechChannel.SAY,
            spot_id=SpotId.create(spot_id_value),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )

        resolver = runtime._obs_pipeline._resolver  # type: ignore[attr-defined]
        pids = sorted(p.value for p in resolver.resolve(event))
        # 同スポットのリン (player_id=2) が含まれる
        assert 2 in pids, (
            f"BUG: 同スポットの相手が speech resolve に含まれていない (pids={pids}). "
            "SpotGraphSpeechRecipientStrategy が未登録の可能性。"
        )

    def test_player_spoke_event_does_not_resolve_to_far_listener(
        self,
    ) -> None:
        """master_study (8) から閲覧室 (2) まで 5 hop。NORMAL speech は届かない。

        resolver が hop-based 距離 gating を正しく動かしているかを確認。
        """
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        master_study_id = _name_to_spot_id(runtime, "館長書斎")

        # カイト (player_id=1) を館長書斎に移す (graph 側のみで十分)
        graph = runtime._spot_graph_repo.find_graph()
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph.unplace_entity(EntityId.create(1))
        graph.place_entity(EntityId.create(1), SpotId.create(master_study_id))
        runtime._spot_graph_repo.save(graph)

        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="リン、聞こえるか！",
            channel=SpeechChannel.SAY,
            spot_id=SpotId.create(master_study_id),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )

        resolver = runtime._obs_pipeline._resolver  # type: ignore[attr-defined]
        pids = {p.value for p in resolver.resolve(event)}
        # 5 hop 先のリン (player_id=2) は届かない (max_hops=1)
        assert 2 not in pids, (
            f"BUG: 5 hop 先のリンが SAY の resolve に含まれている (pids={pids}). "
            "SoundPropagationService の hop 制限が効いていない。"
        )

    def test_resolver_registers_multiple_strategies(self) -> None:
        """旧バグでは strategies=[spot_graph_strategy] のみだった。
        修正後は create_observation_recipient_resolver の全 strategy が登録
        されているはず。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        resolver = runtime._obs_pipeline._resolver  # type: ignore[attr-defined]
        # 内部の _strategies 属性は実装詳細だが、回帰テストとして count を見る。
        strategies = resolver._strategies  # type: ignore[attr-defined]
        # speech / spot_graph / item_use / conversation / default 等を含むはず
        # (具体 strategy 数は将来追加で増える可能性があるので 5 以上を要求)
        assert len(strategies) >= 5, (
            f"BUG: resolver の strategy 数が少なすぎる ({len(strategies)})。"
            f"create_observation_recipient_resolver 経由で構築されていない可能性。"
        )
        # 各 strategy の class 名を確認 (regression marker)
        class_names = {type(s).__name__ for s in strategies}
        required = {
            "SpotGraphRecipientStrategy",
            "SpotGraphSpeechRecipientStrategy",
        }
        missing = required - class_names
        assert not missing, (
            f"BUG: 必須 strategy が未登録 ({missing})。"
            f"登録済みは: {sorted(class_names)}"
        )
