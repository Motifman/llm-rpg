from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress import AllActionsAllowed, WorldStageDeclaration
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, WorldId, WorldStageId, WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldStage, WorldStageChangedEvent

_WORLD = WorldId("village")


def _stage(stage_id: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(stage_id),
        name=DisplayName(stage_id),
        description=DescriptionText(f"{stage_id}の段階"),
        allowed_actions=AllActionsAllowed(),
    )


class TestWorldStageOpen:
    """WorldStage.open が、最初の段階に入った状態の段階を作ることを保証する。"""

    def test_starts_in_initial_stage_at_given_tick(self) -> None:
        """昼の議論を最初の段階として tick 0 で作ると、current は昼の議論、entered_at は tick 0。"""
        stage = WorldStage.open(_WORLD, _stage("day_discussion"), WorldTick(0))

        assert stage.current() == WorldStageId("day_discussion")
        assert stage.entered_at() == WorldTick(0)
        assert stage.world_id == _WORLD

    def test_opening_records_no_event(self) -> None:
        """作っただけでは、イベントをためない。"""
        assert WorldStage.open(_WORLD, _stage("day_discussion"), WorldTick(0)).get_events() == []


class TestWorldStageEnter:
    """WorldStage.enter が段階を移り、移ったときだけ出る段階と入る段階を持つイベントをためることを保証する。"""

    def test_enter_moves_to_new_stage_at_given_tick(self) -> None:
        """tick 12 で夜へ enter すると、current は夜、entered_at は tick 12 になる。"""
        stage = WorldStage.open(_WORLD, _stage("day"), WorldTick(0))

        stage.enter(_stage("night"), WorldTick(12))

        assert stage.current() == WorldStageId("night")
        assert stage.entered_at() == WorldTick(12)

    def test_enter_records_event_with_left_and_entered_stage(self) -> None:
        """昼から夜への enter は、世界と、出る昼と入る夜と tick を持つ WorldStageChangedEvent をためる。"""
        stage = WorldStage.open(_WORLD, _stage("day"), WorldTick(0))

        stage.enter(_stage("night"), WorldTick(12))

        [event] = stage.get_events()
        assert isinstance(event, WorldStageChangedEvent)
        assert (event.world_id, event.before, event.after, event.at) == (
            _WORLD,
            WorldStageId("day"),
            WorldStageId("night"),
            WorldTick(12),
        )

    def test_entering_current_stage_changes_nothing(self) -> None:
        """今と同じ昼へ enter しても、entered_at は変わらず、イベントもためない。"""
        stage = WorldStage.open(_WORLD, _stage("day"), WorldTick(0))

        stage.enter(_stage("day"), WorldTick(5))

        assert stage.entered_at() == WorldTick(0)
        assert stage.get_events() == []


def _nouns(*stages: WorldStageDeclaration) -> DeclaredNouns:
    return DeclaredNouns(
        flags=(),
        spots=(),
        passages=(),
        objects=(),
        item_specs=(),
        groupings=(),
        groups=(),
        characters=(),
        world_stages=stages,
        group_decisions=(),
        sections=(),
        outcomes=(),
    )


class TestWorldStageDeclarationIn:
    """WorldStage.declaration_in が、名詞の宣言から今の段階の宣言を引いて返すことを保証する。"""

    def test_answers_declaration_of_current_stage(self) -> None:
        """昼から夜へ移った段階は、昼と夜を宣言した名詞から夜の宣言を返す。"""
        day, night = _stage("day"), _stage("night")
        stage = WorldStage.open(_WORLD, day, WorldTick(0))
        stage.enter(night, WorldTick(12))

        assert stage.declaration_in(_nouns(day, night)) == night
