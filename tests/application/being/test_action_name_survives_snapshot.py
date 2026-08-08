"""行動の構造化引数が snapshot の往復で消えないことを保証する。

``identifier_arguments`` は「実際にどの値を tool へ渡したか」という事実で、
``action_summary`` の表示名からは復元できない。保存・復元のどちらかを落とすと
**再開した run だけ静かに欠落する**。

CLAUDE.md #27 が per-Being store の追加で警告しているのと同じ形で、DTO に項目を
足したときも codec への追従が要る。
"""

from pathlib import Path

from ai_rpg_world.application.being.world_subsystems.short_term_memory_codec import (
    UnifiedRecentEventStoreSubsystemCodec,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)


def _latest_arguments(runtime) -> tuple[dict[str, str], tuple[str, ...]]:
    entries = runtime._action_result_store.get_recent(_MORI, 1)
    assert entries, "行動結果が記録されていない"
    return dict(entries[0].identifier_arguments), entries[0].free_text_argument_names


def test_action_arguments_survive_a_snapshot_round_trip() -> None:
    """保存して復元しても、呼んだ識別引数と自由文引数名が残る。"""
    codec = UnifiedRecentEventStoreSubsystemCodec()

    source = create_world_runtime(_SCENARIO)
    source.do_interact(_MORI, "duty_board", "read_board")
    assert _latest_arguments(source)[0]["action_name"] == "read_board"

    payload = codec.capture(source)

    restored = create_world_runtime(_SCENARIO)
    codec.restore(restored, payload)

    assert _latest_arguments(restored)[0]["action_name"] == "read_board"


def test_payload_carries_the_action_arguments() -> None:
    """保存形式の **行動エントリ** に構造化引数が載る。

    往復だけを見ると、保存側と復元側を **両方** 落としたときに素通りする。
    payload を直接見て、書き出されていることを別に縛る。

    payload 全体を文字列にして探すのでは足りない。同じ ``read_board`` が
    観測の structured payload にも載るため、行動側を落としても文字列は残る
    (最初にそう書いて空振りさせた)。**行動エントリの中だけ**を見る。
    """
    codec = UnifiedRecentEventStoreSubsystemCodec()
    runtime = create_world_runtime(_SCENARIO)
    runtime.do_interact(_MORI, "duty_board", "read_board")

    payload = codec.capture(runtime)

    arguments = _action_entry_arguments(payload)
    assert arguments, "payload に行動エントリが見つからない"
    assert any(item.get("action_name") == "read_board" for item in arguments)


def _action_entry_arguments(value) -> list[dict]:
    """payload から行動エントリの identifier_arguments だけを集める。

    観測の structured payload にも同名のキーが載るので、行動側だけを表す
    ``action_summary`` を持つ dict に限定する。
    """
    found: list[dict] = []
    if isinstance(value, dict):
        if "action_summary" in value:
            found.append(dict(value.get("identifier_arguments") or {}))
        for item in value.values():
            found.extend(_action_entry_arguments(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_action_entry_arguments(item))
    return found


def test_old_payload_without_action_arguments_restores_as_empty() -> None:
    """構造化引数を持たない旧 payload は空へ倒れ、復元自体は成功する。

    嘘の名前を作らないことが要点。復元できない情報は空のままにする。
    """
    codec = UnifiedRecentEventStoreSubsystemCodec()
    source = create_world_runtime(_SCENARIO)
    source.do_interact(_MORI, "duty_board", "read_board")
    payload = codec.capture(source)

    stripped = _strip_action_arguments(payload)

    restored = create_world_runtime(_SCENARIO)
    codec.restore(restored, stripped)

    assert _latest_arguments(restored) == ({}, ())


def _strip_action_arguments(value):
    """payload から新しい構造化引数キーを取り除いた複製を返す。"""
    if isinstance(value, dict):
        return {
            key: _strip_action_arguments(item)
            for key, item in value.items()
            if key not in {"identifier_arguments", "free_text_argument_names"}
        }
    if isinstance(value, list):
        return [_strip_action_arguments(item) for item in value]
    return value
