import json

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterUpdateRequest,
)


def test_character_create_list_get_persists_to_disk(tmp_path) -> None:
    characters_path = tmp_path / "characters.json"
    manager = GameRuntimeManager(characters_path=characters_path)

    created = manager.create_character(
        CharacterCreateRequest(
            name="門前の少女",
            first_person="わたし",
            personality_tags=["静か", "記憶喪失"],
            speech_samples=["……ここ、知ってる気がする。"],
            fragmented_memory="白い廊下で誰かの名前を呼んだ。",
        )
    )

    assert characters_path.exists()
    assert manager.get_character(created.id) == created
    assert [c.id for c in manager.list_characters()] == [created.id]

    reloaded = GameRuntimeManager(characters_path=characters_path)
    assert reloaded.get_character(created.id) == created


def test_character_update_persists_to_disk(tmp_path) -> None:
    characters_path = tmp_path / "characters.json"
    manager = GameRuntimeManager(characters_path=characters_path)
    created = manager.create_character(CharacterCreateRequest(name="少女"))

    updated = manager.update_character(
        created.id,
        CharacterUpdateRequest(
            name="門前の少女",
            values="置いていかない",
        ),
    )

    assert updated is not None
    assert updated.name == "門前の少女"
    assert updated.values == "置いていかない"

    reloaded = GameRuntimeManager(characters_path=characters_path)
    assert reloaded.get_character(created.id) == updated


def test_character_saved_with_behavioral_rules_still_loads(tmp_path) -> None:
    """行動ルールの欄を消す前に保存したキャラクターも、欄を読み捨てて読み込める。"""
    characters_path = tmp_path / "characters.json"
    created = GameRuntimeManager(characters_path=characters_path).create_character(
        CharacterCreateRequest(name="門前の少女")
    )
    saved = json.loads(characters_path.read_text(encoding="utf-8"))
    saved["characters"][0]["behavioral_rules"] = ["むやみに大声を出さない"]
    characters_path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

    reloaded = GameRuntimeManager(characters_path=characters_path)

    assert reloaded.get_character(created.id) == created
