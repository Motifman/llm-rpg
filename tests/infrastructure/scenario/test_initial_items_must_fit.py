"""枠に入りきらない初期所持品は、読み込みの時点で落とす。

run が始まってから足元に落ちていると、シナリオ作家は**自分の宣言が効いて
いないことに気づけません** (#830 / #840 と同じ形)。枠を超える初期所持品は
**作者の誤りであって、世界の出来事ではない**。

効果として与えられる品 (採取・報酬) は「持ちきれず落ちた」で良いが、こちらは
まだ誰も居ない起動前の話で、落とす先も無い。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

#: 所持枠。集約が持っている値をそのまま使う (テストに数字を写さない)。
DEFAULT_MAX_SLOTS = PlayerInventoryAggregate.DEFAULT_MAX_SLOTS

_TOWN = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"


def _load_with_initial_items(tmp_path: Path, count: int) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"][0]["initial_items"] = ["herb"] * count
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return ScenarioLoader().load_from_file(path)


class TestInitialItemsMustFitInThePack:
    """初期所持品は、所持枠に収まっている必要がある。"""

    def test_too_many_is_refused(self, tmp_path: Path) -> None:
        """枠を超える初期所持品を書いたシナリオは読み込めない。"""
        with pytest.raises(ScenarioLoadError):
            _load_with_initial_items(tmp_path, DEFAULT_MAX_SLOTS + 1)

    def test_exactly_full_is_allowed(self, tmp_path: Path) -> None:
        """ちょうど枠ぴったりは通る (**境界の正の対照**)。

        1 つ厳しくすると、意図して満杯から始める世界が書けなくなる。
        """
        result = _load_with_initial_items(tmp_path, DEFAULT_MAX_SLOTS)

        assert result is not None

    def test_the_message_says_who_and_how_many(self, tmp_path: Path) -> None:
        """失敗文に、誰の宣言か・いくつ書いたか・枠がいくつかが出る。

        直せる形でないと、作者は「多すぎる」とだけ言われて数え直すことになる。
        """
        with pytest.raises(ScenarioLoadError) as exc:
            _load_with_initial_items(tmp_path, DEFAULT_MAX_SLOTS + 3)

        message = str(exc.value)
        assert "initial_items" in message
        assert str(DEFAULT_MAX_SLOTS + 3) in message
        assert str(DEFAULT_MAX_SLOTS) in message
