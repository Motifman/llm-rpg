"""確定区間必須のapplication serviceを単体試験するための補助。"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any


def passthrough_command_scope_factory(**repositories: Any) -> MagicMock:
    """指定repositoryをそのまま公開する副作用のない偽scope factoryを返す。"""
    context = MagicMock()
    context.repositories = SimpleNamespace(**repositories)
    context.__enter__.return_value = context
    factory = MagicMock()
    factory.create.return_value = context
    return factory


def bind_passthrough_spot_interaction_scope(service: Any) -> Any:
    """旧規則試験を、公開入口の確定区間契約を迂回せず実行可能にする。"""
    factory = passthrough_command_scope_factory(
        spot_graph=service._spot_graph_repository,
        spot_interiors=service._spot_interior_repository,
        player_inventories=service._player_inventory_repository,
        items=service._item_repository,
        item_specs=service._item_spec_repository,
        player_statuses=service._player_status_repository,
    )
    publisher = service._event_publisher
    if publisher is not None:
        factory.create.return_value.collect_all.side_effect = publisher.publish_all
    service.set_command_scope_factory(factory)
    return service


def install_passthrough_spot_interaction_constructor(
    monkeypatch: Any,
    service_type: type,
) -> None:
    """規則試験で生成したserviceへ副作用なしscopeを明示的に補う。"""
    original_init = service_type.__init__

    def _init_and_bind(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        bind_passthrough_spot_interaction_scope(self)

    monkeypatch.setattr(service_type, "__init__", _init_and_bind)


__all__ = [
    "bind_passthrough_spot_interaction_scope",
    "install_passthrough_spot_interaction_constructor",
    "passthrough_command_scope_factory",
]
