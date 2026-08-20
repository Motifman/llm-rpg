"""拒否が「駄目だ」で終わらず、行き先まで言うことを保証する。

## なぜこの試験が要るか

`disabled_tools` に `memo_add` と書くと、起動時にこう止まる。

    disabled_tools に実在しないツール名があります: memo_add
    指定できるのは: attack, buy_item, ...

止めてくれるのは正しい。しかし**書いた人は「この世界では memo を落とせない」と
読む**。実際は落とせて、**場所がシナリオではなく実験設定**なだけである
(`MEMO_TOOLS_ENABLED`)。**行き先の無い拒否は、拒否された側に推測を強いる。**

実際にこれで止まり、「落とせない」と報告した (私が)。エラーを読んで止まり、
その先を調べなかった。文面が行き先を書いていれば、そこで終わっていた。

最良の形は既にこの世界にある。`INVALID_DESTINATION_LABEL` は
「有効な destination_label: "市場の広場"」と**正解を列挙している**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

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
    raw: Dict[str, Any] = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["disabled_tools"] = disabled
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ToolExposureConfigurationError) as caught:
        create_world_runtime(str(path))
    return str(caught.value)


class TestARefusalPointsSomewhere:
    """落とせる場所があるなら、その場所を言う。"""

    def test_it_names_the_experiment_flag(self, tmp_path: Path) -> None:
        """memo を書いた人に、実験設定で落とすことと、その名前を伝える。"""
        message = _refusal(tmp_path, ["memo_add"])

        assert "MEMO_TOOLS_ENABLED" in message
        assert "実験設定" in message

    def test_it_still_lists_what_the_scenario_can_disable(
        self, tmp_path: Path,
    ) -> None:
        """従来どおり、シナリオで落とせる名前の一覧も出す (**正の対照**)。

        行き先を足したぶんで元の案内が消えると、**別の推測を強いる**ことに
        なる。
        """
        message = _refusal(tmp_path, ["memo_add"])

        assert "指定できるのは" in message
        assert "market_list_item" in message

    def test_a_plain_typo_gets_no_false_signpost(self, tmp_path: Path) -> None:
        """ただの綴り間違いには、行き先を書かない (**正の対照**)。

        存在しない名前に「実験設定で落とせます」と言うと、**無い道を
        指す**ことになる。今度は行き先そのものが嘘になる。
        """
        message = _refusal(tmp_path, ["market_lst_item"])

        assert "実験設定" not in message

    def test_a_mixed_list_signposts_only_the_ones_that_have_a_home(
        self, tmp_path: Path,
    ) -> None:
        """行き先のある名前と無い名前が混ざっても、あるものだけを案内する。"""
        message = _refusal(tmp_path, ["memo_add", "market_lst_item"])

        assert "memo_add は実験設定" in message
        assert "market_lst_item は実験設定" not in message
