"""拒否が「駄目だ」で終わらず、正解の一覧まで言うことを保証する。

## なぜこの試験が要るか

`disabled_tools` に実在しない名前を書くと、起動時にこう止まる。

    disabled_tools に実在しないツール名があります: market_lst_item
    指定できるのは: attack, buy_item, ...

名前を間違えた人が次に要るのは正解の一覧で、「不正な名前です」だけでは
同じ間違いを繰り返す。`INVALID_DESTINATION_LABEL` が「有効な destination_label:
"市場の広場"」と正解を列挙するのと同じ形にする。

古いメモの道具 (`memo_add` など) は #1631 で消した。以前は実験設定で落とせると
案内していたが、今はどこにも無いので、ほかの実在しない名前と同じに扱う。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import (
    ToolExposureConfigurationError,
    create_world_runtime,
)

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)


def _refusal(tmp_path: Path, disabled: list) -> str:
    raw: dict[str, Any] = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["disabled_tools"] = disabled
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ToolExposureConfigurationError) as caught:
        create_world_runtime(str(path))
    return str(caught.value)


class TestARefusalPointsSomewhere:
    """実在しない名前を拒むとき、拒んだ名前と、シナリオで落とせる名前の一覧を言う。"""

    def test_it_lists_what_the_scenario_can_disable(self, tmp_path: Path) -> None:
        """綴り間違いの名前を書くと、その名前と、シナリオで落とせる名前の一覧を出す。"""
        message = _refusal(tmp_path, ["market_lst_item"])

        assert "market_lst_item" in message
        assert "指定できるのは" in message
        assert "market_list_item" in message

    def test_an_old_memo_tool_is_refused_without_a_signpost(self, tmp_path: Path) -> None:
        """消した古いメモの道具の名前は、実在しない名前として拒み、実験設定へ案内しない。"""
        message = _refusal(tmp_path, ["memo_add"])

        assert "memo_add" in message
        assert "指定できるのは" in message
        assert "実験設定" not in message
