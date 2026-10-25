"""本番に残す発行の口は、イベント型と受け手だけで登録する。"""

import inspect

import pytest

from ai_rpg_world.application.world_runtime.pipeline_event_publisher import PipelineEventPublisher
from ai_rpg_world.domain.common.event_publisher import EventPublisher


@pytest.mark.parametrize("publisher_type", [EventPublisher, PipelineEventPublisher])
def test_registration_accepts_only_event_type_and_handler(publisher_type) -> None:
    """発行の口と本番の実装は、イベント型と受け手だけを登録の引数にする。"""
    assert list(inspect.signature(publisher_type.register_handler).parameters) == [
        "self", "event_type", "handler",
    ]
