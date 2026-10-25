"""現在状態問い合わせは、読み手のない移動先取得指定を公開しない。"""

from dataclasses import fields

from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery


def test_current_state_query_only_accepts_player_id() -> None:
    """現在状態問い合わせの入力項目は player_id だけで、旧移動先取得指定は存在しない。"""
    assert {field.name for field in fields(GetPlayerCurrentStateQuery)} == {"player_id"}
