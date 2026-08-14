"""interactionの外部可変状態がcommitとrollbackへ追従することを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.common.exceptions import (
    PoisonedRollbackParticipantException,
    RollbackParticipantRestoreException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    InteractionCooldownStore,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import (
    WorldFlagRegistry,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    SnapshotRollbackParticipant,
    build_interaction_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionAdapter,
)

PLAYER_ID = PlayerId(1)
FIRST_SPOT = SpotId.create(10)
SECOND_SPOT = SpotId.create(20)


class _Transaction:
    def __init__(self, timeline: list[str] | None = None) -> None:
        self._active = False
        self._timeline = timeline

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        self._active = True
        if self._timeline is not None:
            self._timeline.append("transaction.begin")

    def commit(self) -> None:
        self._active = False
        if self._timeline is not None:
            self._timeline.append("transaction.commit")

    def rollback(self) -> None:
        self._active = False
        if self._timeline is not None:
            self._timeline.append("transaction.rollback")


def _graph_repository() -> InMemorySpotGraphRepository:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id, name in ((FIRST_SPOT, "第一地点"), (SECOND_SPOT, "第二地点")):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=name,
                description="rollback試験用",
                category=SpotCategoryEnum.FIELD,
                parent_id=None,
            )
        )
    graph.place_entity(EntityId.create(int(PLAYER_ID)), FIRST_SPOT)
    graph.clear_events()
    return InMemorySpotGraphRepository(graph)


def _resources():
    world_flags = MutableWorldFlagState(WorldFlagRegistry.of("initial"))
    cooldowns = InteractionCooldownStore()
    cooldowns.record_success(
        PLAYER_ID,
        "inspect",
        3,
        scope=InteractionCooldownScope.ACTOR,
    )
    cooldowns.record_success(
        PLAYER_ID,
        "shared_inspect",
        4,
        scope=InteractionCooldownScope.WORLD,
    )
    departed = DepartedPositionStore()
    departed.place(PLAYER_ID, FIRST_SPOT)
    graph = _graph_repository()
    participants = build_interaction_rollback_participants(
        world_flags=world_flags,
        cooldowns=cooldowns,
        departed_positions=departed,
        spot_graph=graph,
    )
    return world_flags, cooldowns, departed, graph, participants


class TestInteractionRollbackParticipants:
    """4つの外部資源を同じcommand境界で確定または復元する挙動を保証する。"""

    def test_rollback_restores_all_resources_to_command_start(self) -> None:
        """command失敗ではflag・待ち時間・退場者位置・graphを全て開始前へ戻す。"""
        world_flags, cooldowns, departed, graph, participants = _resources()
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=participants,
        )

        adapter.begin()
        world_flags.add(
            "changed",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(PLAYER_ID),
            ),
        )
        cooldowns.record_success(
            PLAYER_ID,
            "inspect",
            9,
            scope=InteractionCooldownScope.ACTOR,
        )
        cooldowns.record_success(
            PLAYER_ID,
            "shared_inspect",
            10,
            scope=InteractionCooldownScope.WORLD,
        )
        departed.move(PLAYER_ID, SECOND_SPOT)
        graph.find_graph().teleport_entity(
            EntityId.create(int(PLAYER_ID)),
            SECOND_SPOT,
        )

        adapter.rollback()

        assert world_flags.as_frozen_set() == frozenset({"initial"})
        assert cooldowns.last_success_tick(PLAYER_ID, "inspect") == 3
        assert cooldowns.last_success_tick(
            PLAYER_ID,
            "shared_inspect",
            scope=InteractionCooldownScope.WORLD,
        ) == 4
        assert departed.find(PLAYER_ID) == FIRST_SPOT
        assert graph.find_graph().get_entity_spot(
            EntityId.create(int(PLAYER_ID))
        ) == FIRST_SPOT
        assert graph.find_graph().get_events() == []

    def test_commit_keeps_all_resource_changes(self) -> None:
        """command成功では4資源の変更を復元せずそのまま確定する。"""
        world_flags, cooldowns, departed, graph, participants = _resources()
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=participants,
        )

        adapter.begin()
        world_flags.add(
            "changed",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(PLAYER_ID),
            ),
        )
        cooldowns.record_success(
            PLAYER_ID,
            "inspect",
            9,
            scope=InteractionCooldownScope.ACTOR,
        )
        cooldowns.record_success(
            PLAYER_ID,
            "shared_inspect",
            10,
            scope=InteractionCooldownScope.WORLD,
        )
        departed.move(PLAYER_ID, SECOND_SPOT)
        graph.find_graph().teleport_entity(
            EntityId.create(int(PLAYER_ID)),
            SECOND_SPOT,
        )

        adapter.commit()

        assert world_flags.as_frozen_set() == frozenset({"initial", "changed"})
        assert cooldowns.last_success_tick(PLAYER_ID, "inspect") == 9
        assert cooldowns.last_success_tick(
            PLAYER_ID,
            "shared_inspect",
            scope=InteractionCooldownScope.WORLD,
        ) == 10
        assert departed.find(PLAYER_ID) == SECOND_SPOT
        assert graph.find_graph().get_entity_spot(
            EntityId.create(int(PLAYER_ID))
        ) == SECOND_SPOT

    def test_world_flag_callback_is_delivered_only_after_commit(self) -> None:
        """flag変更通知はtransaction内では保留され、commit後だけ元の順序で届く。"""
        timeline: list[str] = []
        world_flags, _, _, _, participants = _resources()
        world_flags.set_change_callback(
            lambda change: timeline.append(f"flag.{change.flag_name}")
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=participants,
        )

        adapter.begin()
        world_flags.add(
            "committed",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(PLAYER_ID),
            ),
        )
        assert timeline == ["transaction.begin"]

        adapter.commit()

        assert timeline == ["transaction.begin", "transaction.commit", "flag.committed"]

    def test_world_flag_callback_is_discarded_after_rollback(self) -> None:
        """rollbackしたflag変更は状態だけでなく外部通知にも残さない。"""
        timeline: list[str] = []
        world_flags, _, _, _, participants = _resources()
        world_flags.set_change_callback(
            lambda change: timeline.append(f"flag.{change.flag_name}")
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=participants,
        )

        adapter.begin()
        world_flags.add(
            "rolled_back",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(PLAYER_ID),
            ),
        )
        adapter.rollback()

        assert timeline == ["transaction.begin", "transaction.rollback"]
        assert world_flags.as_frozen_set() == frozenset({"initial"})

    def test_world_flag_callback_failure_poison_resource_before_next_command(self) -> None:
        """commit後通知に失敗したflag資源は競合窓を作らず後続利用を拒否する。"""
        callback_error = RuntimeError("trace callback failed")
        world_flags, _, _, _, participants = _resources()

        def fail_callback(change: object) -> None:
            raise callback_error

        world_flags.set_change_callback(fail_callback)
        first = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=participants,
        )
        first.begin()
        world_flags.add(
            "committed",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(PLAYER_ID),
            ),
        )

        with pytest.raises(TransactionCommittedCleanupException):
            first.commit()

        second = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=participants,
        )
        with pytest.raises(PoisonedRollbackParticipantException) as caught:
            second.begin()

        assert caught.value.poison_error is callback_error
        second.rollback()

    def test_restore_failure_poison_participant_for_following_commands(self) -> None:
        """復元不能になった参加資源は後続commandで再利用せず即時拒否する。"""
        resource = object()
        restore_error = RuntimeError("restore failed")
        participant = SnapshotRollbackParticipant(
            resource,
            take_snapshot=lambda: "before",
            restore_snapshot=lambda snapshot: (_ for _ in ()).throw(restore_error),
        )
        first = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=(participant,),
        )
        first.begin()

        with pytest.raises(RollbackParticipantRestoreException):
            first.rollback()

        second = RollbackParticipantTransactionAdapter(
            _Transaction(),
            participants=(participant,),
        )
        with pytest.raises(PoisonedRollbackParticipantException) as caught:
            second.begin()

        assert caught.value.poison_error is restore_error
        second.rollback()
