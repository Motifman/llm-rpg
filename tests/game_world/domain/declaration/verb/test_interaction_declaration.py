from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, ItemArgument, TextArgument
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import DuplicateArgumentNameException
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from tests.game_world.support.verb_declarations_for_tests import as_declared_interaction, pull_lever


class TestInteractionDeclarationArguments:
    """InteractionDeclaration が、エージェントが渡す引数を名前の重ならない並びとして持つことを保証する。"""

    def test_same_argument_name_twice_raises(self) -> None:
        """arguments に同じ名前 "message" を種類を変えて 2 回書くと、DuplicateArgumentNameException を投げる。"""
        with pytest.raises(DuplicateArgumentNameException):
            pull_lever(
                arguments=(
                    ArgumentDeclaration(name=ArgumentName("message"), kind=TextArgument()),
                    ArgumentDeclaration(name=ArgumentName("message"), kind=ItemArgument()),
                )
            )

    def test_distinct_argument_names_are_kept_in_the_written_order(self) -> None:
        """arguments に別々の名前を書くと、断らずに書いた順のまま持ち、DeclaredInteraction としても同じ並びが読める。"""
        message = ArgumentDeclaration(name=ArgumentName("message"), kind=TextArgument())
        offering = ArgumentDeclaration(name=ArgumentName("offering"), kind=ItemArgument())

        declaration = as_declared_interaction(pull_lever(arguments=(message, offering)))

        assert declaration.arguments == (message, offering)

    def test_no_arguments_is_allowed(self) -> None:
        """arguments を空にすると、引数を取らない操作として断らずに作れる。"""
        assert pull_lever(arguments=()).arguments == ()
