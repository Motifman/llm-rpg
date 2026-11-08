from __future__ import annotations

from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlNode

DEFAULTED_KINDS = frozenset(
    {
        "flag",
        "spot",
        "atmosphere",
        "section",
        "section_access",
        "object",
        "appearance",
        "state_key",
        "discoverable",
        "interaction",
        "passage",
        "passage_state",
        "item_spec",
        "grouping",
        "group",
        "character",
        "world_stage",
        "group_decision",
        "outcome",
        "happening",
        "reaction",
        "joint_action",
        "perception",
        "sight_texts",
        "sound",
        "sight_at",
        "sound_from",
        "announcement_to",
        "day_phase",
        "weather",
    }
)


class ScenarioDefaults:
    def __init__(self, node: YamlNode) -> None:
        self._by_kind: dict[str, YamlNode] = {}
        if node.is_null():
            return
        for kind, values in node.entries():
            if kind not in DEFAULTED_KINDS:
                raise values.unreadable(f"unknown kind {kind!r}; the kinds are {sorted(DEFAULTED_KINDS)}")
            if not isinstance(values.value, dict):
                raise values.unreadable(f"expected a mapping, got {values.value!r}")
            self._by_kind[kind] = values

    def fill(self, kind: str, node: YamlNode) -> YamlNode:
        defaults = self._by_kind.get(kind)
        if defaults is None or not isinstance(node.value, dict) or not isinstance(defaults.value, dict):
            return node
        filled = {key: value for key, value in defaults.value.items() if key not in node.value}
        sources = {str(key): defaults.child(str(key), value).written_at() for key, value in filled.items()}
        return YamlNode({**filled, **node.value}, node.path, node.source, {**(node.child_sources or {}), **sources})
