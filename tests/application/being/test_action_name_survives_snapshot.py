"""行動の正規名が snapshot の往復で消えないことを保証する。

``action_name`` は「実際に呼んだ interaction は何か」という事実で、
``action_summary`` の display_label からは復元できない。保存・復元のどちらかを
落とすと **再開した run だけ静かに欠落する**。

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


def _latest_action_name(runtime) -> str | None:
    entries = runtime._action_result_store.get_recent(_MORI, 1)
    assert entries, "行動結果が記録されていない"
    return entries[0].action_name


def test_action_name_survives_a_snapshot_round_trip() -> None:
    """保存して復元しても、呼んだ正規名が残る。"""
    codec = UnifiedRecentEventStoreSubsystemCodec()

    source = create_world_runtime(_SCENARIO)
    source.do_interact(_MORI, "duty_board", "read_board")
    assert _latest_action_name(source) == "read_board"

    payload = codec.capture(source)

    restored = create_world_runtime(_SCENARIO)
    codec.restore(restored, payload)

    assert _latest_action_name(restored) == "read_board"


def test_payload_carries_the_action_name() -> None:
    """保存形式の **行動エントリ** に正規名が載る。

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

    action_names = _action_entry_action_names(payload)
    assert action_names, "payload に行動エントリが見つからない"
    assert "read_board" in action_names


def _action_entry_action_names(value) -> list:
    """payload から「行動エントリらしき dict」の action_name だけを集める。

    観測の structured payload にも同名のキーが載るので、行動側だけを表す
    ``action_summary`` を持つ dict に限定する。
    """
    found: list = []
    if isinstance(value, dict):
        if "action_summary" in value:
            found.append(value.get("action_name"))
        for item in value.values():
            found.extend(_action_entry_action_names(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_action_entry_action_names(item))
    return found


def test_old_payload_without_action_name_restores_as_empty() -> None:
    """正規名を持たない旧 payload は None へ倒れ、復元自体は成功する。

    嘘の名前を作らないことが要点。復元できない情報は空のままにする。
    """
    codec = UnifiedRecentEventStoreSubsystemCodec()
    source = create_world_runtime(_SCENARIO)
    source.do_interact(_MORI, "duty_board", "read_board")
    payload = codec.capture(source)

    stripped = _strip_action_name(payload)

    restored = create_world_runtime(_SCENARIO)
    codec.restore(restored, stripped)

    assert _latest_action_name(restored) is None


def _strip_action_name(value):
    """payload から ``action_name`` キーだけを取り除いた複製を返す。"""
    if isinstance(value, dict):
        return {
            key: _strip_action_name(item)
            for key, item in value.items()
            if key != "action_name"
        }
    if isinstance(value, list):
        return [_strip_action_name(item) for item in value]
    return value
