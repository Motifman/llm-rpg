from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.verb import (
    AnnouncementTo,
    HappeningNotice,
    NoFailureWitness,
    NoNotice,
    PerceptionDeclaration,
    SightAt,
    Silent,
    SoundFrom,
)
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignWarning
from ai_rpg_world.game_world.domain.perception import NoTarget, NotNoticedLater, NotSeenInDim, NotSeenWithoutActor
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.kinded_node import split_kind
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import people_text, salience
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlFields, YamlNode

_WITNESS = "witness"
_TARGET = "target"
_SOUND = "sound"
_PERCEPTION_FIELDS = (_WITNESS, _TARGET, _SOUND, "seen_in_dark", "announcement", "on_failure", "salience")
_NOTICE_KINDS = ("sight_at", "sound_from", "announcement_to")


class PerceptionReader:
    def __init__(
        self,
        defaults: ScenarioDefaults,
        perception_defaults: YamlNode,
        names: DeclaredNames,
        conditions: ConditionReader,
        warnings: list[DesignWarning],
        origins: ScenarioOrigins,
    ) -> None:
        self._origins = origins
        self._defaults = defaults
        self._perception_defaults = perception_defaults
        self._names = names
        self._conditions = conditions
        self._warnings = warnings

    def perception(self, node: YamlNode, has_target: bool) -> PerceptionDeclaration:
        fields = self._defaults.fill("perception", node).fields(*_PERCEPTION_FIELDS)
        return node.build(
            lambda: PerceptionDeclaration(
                witness=self.sight_texts(self._written_or_default(fields, _WITNESS)),
                target=self._target(fields, has_target),
                sound=self._sound_or_silent(self._written_or_default(fields, _SOUND)),
                seen_in_dark=fields.required("seen_in_dark").boolean(),
                announcement=self._announcement(fields.required("announcement")),
                on_failure=self._on_failure(fields.required("on_failure")),
                salience=salience(fields.required("salience")),
            )
        )

    def sight_texts(self, node: YamlNode) -> SightTextsDeclaration:
        fields = self._defaults.fill("sight_texts", node).fields("clear", "dim", "unseen_actor", "noticed_later")
        dim = fields.required("dim")
        unseen_actor = fields.required("unseen_actor")
        noticed_later = fields.required("noticed_later")
        return SightTextsDeclaration(
            clear=people_text(fields.required("clear")),
            dim=NotSeenInDim() if dim.is_null() else people_text(dim),
            unseen_actor=NotSeenWithoutActor() if unseen_actor.is_null() else people_text(unseen_actor),
            noticed_later=NotNoticedLater() if noticed_later.is_null() else people_text(noticed_later),
        )

    def sound(self, node: YamlNode) -> SoundDeclaration:
        fields = self._defaults.fill("sound", node).fields("loudness", "clear", "muffled")
        return SoundDeclaration(
            loudness=fields.required("loudness").enum(Loudness),
            clear=people_text(fields.required("clear")),
            muffled=people_text(fields.required("muffled")),
        )

    def notice(self, node: YamlNode) -> HappeningNotice | NoNotice:
        if node.is_null():
            return NoNotice()
        kinded = split_kind(node, _NOTICE_KINDS, explains_failure=False)
        if kinded.kind == "sight_at":
            fields = self._defaults.fill("sight_at", kinded.body).fields("spot", "texts", "salience")
            return SightAt(
                spot=self._names.spot(fields.required("spot")),
                texts=self.sight_texts(fields.required("texts")),
                salience=salience(fields.required("salience")),
            )
        if kinded.kind == "sound_from":
            fields = self._defaults.fill("sound_from", kinded.body).fields("spot", "sound", "salience")
            return SoundFrom(
                spot=self._names.spot(fields.required("spot")),
                sound=self.sound(fields.required("sound")),
                salience=salience(fields.required("salience")),
            )
        return self.announcement_to(kinded.body)

    def announcement_to(self, node: YamlNode) -> AnnouncementTo:
        fields = self._defaults.fill("announcement_to", node).fields("audience", "text", "salience")
        return AnnouncementTo(
            audience=self._conditions.people(fields.required("audience")),
            text=people_text(fields.required("text")),
            salience=salience(fields.required("salience")),
        )

    def _written_or_default(self, fields: YamlFields, field: str) -> YamlNode:
        written = fields.optional(field)
        if written is not None:
            return written
        default = self._perception_defaults.fields(_WITNESS, _TARGET, _SOUND).optional(field)
        if default is None:
            return fields.required(field)
        self._warnings.append(
            DesignWarning(
                self._origins.locate(fields.node.child(field, None).written_at()),
                f"{field} is not written; the default text is used",
            )
        )
        return default

    def _target(self, fields: YamlFields, has_target: bool) -> SightTextsDeclaration | NoTarget:
        if not has_target:
            if fields.has(_TARGET):
                raise fields.required(_TARGET).unreadable("this action has no target to tell")
            return NoTarget()
        target = self._written_or_default(fields, _TARGET)
        return NoTarget() if target.is_null() else self.sight_texts(target)

    def _sound_or_silent(self, node: YamlNode) -> SoundDeclaration | Silent:
        return Silent() if node.is_null() else self.sound(node)

    def _announcement(self, node: YamlNode) -> AnnouncementTo | NoAnnouncement:
        return NoAnnouncement() if node.is_null() else self.announcement_to(node)

    def _on_failure(self, node: YamlNode) -> SightTextsDeclaration | NoFailureWitness:
        return NoFailureWitness() if node.is_null() else self.sight_texts(node)
