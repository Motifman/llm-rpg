from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration, GroupDeclaration
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import (
    PassageDeclaration,
    SpotDeclaration,
    SpotSectionDeclaration,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import ReferencesUnreadable, YamlNode


class DeclaredNames:
    def __init__(
        self,
        nouns: DeclaredNouns,
        unreadable: frozenset[tuple[str, str]],
        origins: ScenarioOrigins,
    ) -> None:
        self.nouns = nouns
        self._unreadable = unreadable
        self._origins = origins

    def _at(self, node: YamlNode) -> DesignLocation:
        return self._origins.locate(node.written_at())

    def flag(self, node: YamlNode) -> FlagDeclaration:
        return self.nouns.flag(self._name("flag", node), self._at(node))

    def spot(self, node: YamlNode) -> SpotDeclaration:
        return self.nouns.spot(self._name("spot", node), self._at(node))

    def passage(self, node: YamlNode) -> PassageDeclaration:
        return self.nouns.passage(self._name("passage", node), self._at(node))

    def object(self, node: YamlNode) -> ObjectDeclaration:
        return self.nouns.object(self._name("object", node), self._at(node))

    def object_state_key(self, node: YamlNode) -> ObjectStateKeyDeclaration:
        object_name, key = self._dotted(node)
        self._require_readable("object", object_name)
        return self.nouns.object_state_key(object_name, key, self._at(node))

    def item_spec(self, node: YamlNode) -> ItemSpecDeclaration:
        return self.nouns.item_spec(self._name("item_spec", node), self._at(node))

    def item_state_key(self, node: YamlNode) -> ItemStateKeyDeclaration:
        item_name, key = self._dotted(node)
        self._require_readable("item_spec", item_name)
        item_spec = self.nouns.item_spec(item_name, self._at(node))
        for state_key in item_spec.state_keys:
            if state_key.key.value == key:
                return state_key
        raise node.unreadable(f"item_spec {item_name!r} has no state key {key!r}")

    def group(self, node: YamlNode) -> GroupDeclaration:
        return self.nouns.group(self._name("group", node), self._at(node))

    def character(self, node: YamlNode) -> CharacterDeclaration:
        return self.nouns.character(self._name("character", node), self._at(node))

    def world_stage(self, node: YamlNode) -> WorldStageDeclaration:
        return self.nouns.world_stage(self._name("world_stage", node), self._at(node))

    def group_decision(self, node: YamlNode) -> GroupDecisionDeclaration:
        return self.nouns.group_decision(self._name("group_decision", node), self._at(node))

    def section(self, node: YamlNode) -> SpotSectionDeclaration:
        return self.nouns.section(self._name("section", node), self._at(node))

    def outcome(self, node: YamlNode) -> OutcomeDeclaration:
        return self.nouns.outcome(self._name("outcome", node), self._at(node))

    def _name(self, kind: str, node: YamlNode) -> str:
        name = node.text()
        self._require_readable(kind, name)
        return name

    def _require_readable(self, kind: str, name: str) -> None:
        if (kind, name) in self._unreadable:
            raise ReferencesUnreadable()

    def _dotted(self, node: YamlNode) -> tuple[str, str]:
        owner, dot, key = node.text().partition(".")
        if not dot or not owner or not key:
            raise node.unreadable(f"a state key is written as <name>.<key>, got {node.value!r}")
        return owner, key
