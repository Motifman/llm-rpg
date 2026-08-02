"""秘匿した対人行為でも、対象本人にだけは届けられることを保証する。

`WitnessPolicy` と `EffectVisibility` の 2 軸では「第三者に届くか」しか
選べない。`ACTOR_ONLY` にすると対象本人にも届かなくなるので、「毒を盛られた
本人だけが異変に気づく」が書けなかった
(docs/memory_system/interpersonal_interaction_design.md §3.6)。

`notify_target` は 3 軸目で、interaction 単位。

| 軸 | 何を決めるか |
|---|---|
| `WitnessPolicy` | 第三者に行為が届くか |
| `EffectVisibility` | 第三者に効果が届くか |
| `notify_target` | **対象本人に行為が届くか** |
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerInteractedWithPlayerEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId

_ACTOR = 1
_TARGET = 2
_BYSTANDER = 3
_SPOT = 10


class _StubPresence:
    def __init__(self, entity_ids) -> None:
        self.present_entity_ids = tuple(entity_ids)


class _StubGraph:
    def __init__(self, entity_ids) -> None:
        self._presence = _StubPresence(entity_ids)

    def presence_at(self, spot_id):
        return self._presence

    def entity_spot_mapping(self):
        return {
            EntityId.create(int(eid)): SpotId.create(_SPOT)
            for eid in self._presence.present_entity_ids
        }


class _StubGraphRepository:
    def __init__(self, entity_ids) -> None:
        self._graph = _StubGraph(entity_ids)

    def find_graph(self):
        return self._graph


class _StubStatus:
    def __init__(self, is_down: bool, player_id: int = 0) -> None:
        self.is_down = is_down
        self.player_id = PlayerId(player_id) if player_id else None


class _StubStatusRepository:
    """倒れている player を宣言できるだけの stub。"""

    def __init__(self, downed_player_ids=()) -> None:
        self._downed = {int(pid) for pid in downed_player_ids}

    def find_by_id(self, player_id: PlayerId):
        return _StubStatus(int(player_id) in self._downed, int(player_id))

    def find_all(self):
        return [
            _StubStatus(pid in self._downed, pid)
            for pid in (_ACTOR, _TARGET, _BYSTANDER)
        ]


def _strategy(*, downed=()) -> SpotGraphRecipientStrategy:
    return SpotGraphRecipientStrategy(
        ObservedEventRegistry(),
        _StubGraphRepository((_ACTOR, _TARGET, _BYSTANDER)),
        _StubStatusRepository(downed),
    )


def _event(
    *,
    witness_policy: WitnessPolicy,
    notify_target: bool,
    target_was_down: bool = False,
) -> PlayerInteractedWithPlayerEvent:
    return PlayerInteractedWithPlayerEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=EntityId.create(_ACTOR),
        target_entity_id=EntityId.create(_TARGET),
        spot_id=SpotId.create(_SPOT),
        action_name="strike_down",
        result_message="",
        action_display_label="背後から襲う",
        witness_observation_message=None,
        witness_policy=witness_policy,
        target_was_down=target_was_down,
        notify_target=notify_target,
    )


def _recipients(strategy, event) -> List[int]:
    return sorted(int(pid) for pid in strategy.resolve(event))


class TestCovertActionNotifiesOnlyTheTarget:
    """ACTOR_ONLY + notify_target=true: 対象だけに届く。"""

    def test_target_receives_it(self) -> None:
        """秘匿した行為でも、やられた本人には届く。"""
        assert _recipients(
            _strategy(),
            _event(witness_policy=WitnessPolicy.ACTOR_ONLY, notify_target=True),
        ) == [_TARGET]

    def test_bystander_does_not(self) -> None:
        """同席している第三者には届かない (秘匿が成立する)。"""
        recipients = _recipients(
            _strategy(),
            _event(witness_policy=WitnessPolicy.ACTOR_ONLY, notify_target=True),
        )
        assert _BYSTANDER not in recipients

    def test_actor_does_not(self) -> None:
        """行為者本人には届かない (tool 結果で既に受け取っている)。"""
        recipients = _recipients(
            _strategy(),
            _event(witness_policy=WitnessPolicy.ACTOR_ONLY, notify_target=True),
        )
        assert _ACTOR not in recipients


class TestCovertActionWithoutNotifyStaysSilent:
    """ACTOR_ONLY + notify_target=false: 誰にも届かない (既存挙動)。"""

    def test_nobody_receives_it(self) -> None:
        """気づかれずに盗む行為は、対象にも届かない。"""
        assert _recipients(
            _strategy(),
            _event(witness_policy=WitnessPolicy.ACTOR_ONLY, notify_target=False),
        ) == []


class TestPublicActionIsUnaffected:
    """SAME_SPOT では notify_target の有無で配信先が変わらない。

    公然の行為では対象も第三者も既に受け取っている。ここで notify_target を
    見て分岐すると、同じ相手を 2 度足しかねない。
    """

    @pytest.mark.parametrize("notify_target", [True, False])
    def test_target_and_bystander_receive_it(self, notify_target) -> None:
        """対象と第三者の両方に届き、行為者だけが外れる。"""
        assert _recipients(
            _strategy(),
            _event(
                witness_policy=WitnessPolicy.SAME_SPOT, notify_target=notify_target
            ),
        ) == [_TARGET, _BYSTANDER]


class TestDownedTargetIsStillExcluded:
    """倒れている対象には notify_target でも届かない。

    倒れている player は recipient から構造的に除外される (Issue #621
    Phase 4: ターンが回らず観測を消化できない)。notify_target のために
    その規則を曲げると、消化されない観測が積まれるだけになる。

    致死打で「自分が殺されたこと」を本人に届けないのは意図した判断である。
    倒れている間にされたことは、目覚めたときに DownedIncidentLog 経由で
    まとめて読める (PR #831)。
    """

    def test_downed_target_receives_nothing(self) -> None:
        """倒れている対象は notify_target=true でも配信先に入らない。

        **判定は resolver の出口にある。** かつては strategy の末尾に
        あったが、speech 等の別経路に効かず実 run 008 で漏れた。strategy
        単体を見ていると、判定がどこにあっても通ってしまうので resolver
        越しに確かめる。
        """
        from unittest.mock import MagicMock

        from ai_rpg_world.application.observation.services.observation_recipient_resolver import (  # noqa: E501
            ObservationRecipientResolver,
        )

        repository = MagicMock()
        repository.find_by_id.side_effect = lambda pid: MagicMock(
            is_down=int(pid) == int(_TARGET)
        )
        resolver = ObservationRecipientResolver(
            strategies=[_strategy()], player_status_repository=repository
        )

        recipients = resolver.resolve(
            _event(
                witness_policy=WitnessPolicy.ACTOR_ONLY,
                notify_target=True,
                target_was_down=True,
            )
        )

        assert [r.value for r in recipients] == []
