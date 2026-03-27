"""SQLite dialogue tree repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.infrastructure.repository.sqlite_dialogue_tree_repository import (
    SqliteDialogueTreeRepository,
    SqliteDialogueTreeWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def test_dialogue_tree_reader_and_writer_roundtrip() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteDialogueTreeRepository.for_connection(conn)
    writer = SqliteDialogueTreeWriter.for_standalone_connection(conn)

    writer.replace_tree(
        tree_id=DialogueTreeId(1),
        entry_node_id=DialogueNodeId(0),
        nodes={
            0: DialogueNode(
                node_id=0,
                text="hello",
                choices=(),
                next_node_id=1,
                is_terminal=False,
            ),
            1: DialogueNode(
                node_id=1,
                text="bye",
                choices=(),
                next_node_id=None,
                is_terminal=True,
            ),
        },
    )

    assert repo.get_entry_node_id(DialogueTreeId(1)) == DialogueNodeId(0)
    node = repo.get_node(DialogueTreeId(1), DialogueNodeId(1))
    assert node is not None
    assert node.text == "bye"


def test_dialogue_tree_shared_writer_requires_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    writer = SqliteDialogueTreeWriter.for_shared_unit_of_work(conn)

    with pytest.raises(RuntimeError, match="writer"):
        writer.replace_tree(
            tree_id=DialogueTreeId(1),
            entry_node_id=DialogueNodeId(0),
            nodes={},
        )


def test_dialogue_tree_shared_writer_works_inside_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)

    with uow:
        writer = SqliteDialogueTreeWriter.for_shared_unit_of_work(uow.connection)
        repo = SqliteDialogueTreeRepository.for_connection(uow.connection)
        writer.replace_tree(
            tree_id=DialogueTreeId(1),
            entry_node_id=DialogueNodeId(0),
            nodes={
                0: DialogueNode(
                    node_id=0,
                    text="hello",
                    choices=(),
                    next_node_id=None,
                    is_terminal=True,
                )
            },
        )
        assert repo.get_node(DialogueTreeId(1), DialogueNodeId(0)) is not None
