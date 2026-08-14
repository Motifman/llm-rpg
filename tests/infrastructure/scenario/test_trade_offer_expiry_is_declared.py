"""提案が流れるまでの手番数を、シナリオから決められる。

期限は**世界の広さで決まる値**で、コードに固定してよい値ではなかった。
market_town_v2_trade の実 run では、焼き手の生産往復が 12 手番 (t44 に麦を
刈って t56 に焼いた) だったのに対し、既定の期限は 10 手番。予約注文
(gold を差し出してパンを求める) は**構造的に必ず流れる**状態で、エージェント
がどう振る舞っても成立しなかった。

`meeting.tick_limit` や `meeting.cooldown_ticks` と同じ「世界の広さで決まる
調整値」なので、同じ流儀でシナリオから渡せるようにする。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_TOWN = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"


def _raw() -> Dict[str, Any]:
    return json.loads(_TOWN.read_text(encoding="utf-8"))


def _load(raw: Dict[str, Any], tmp_path: Path):
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return ScenarioLoader().load_from_file(path)


class TestTheExpiryComesFromTheScenario:
    """宣言した手番数が読み取られる。"""

    def test_it_defaults_when_the_block_is_absent(self, tmp_path: Path) -> None:
        """`player_trade` を書いていない世界では、期限は engine の既定になる。"""
        result = _load(_raw(), tmp_path)

        assert result.player_trade_offer_expires_in_ticks is None

    def test_it_defaults_when_only_enabled_is_written(self, tmp_path: Path) -> None:
        """`enabled` だけ書いた世界でも、期限は engine の既定のままになる。

        None と「書いた値」を区別して持つ。0 を許さない値なので既定を数値で
        持っても実害は無いが、engine 側の既定を 1 箇所に保つため None にする。
        """
        raw = _raw()
        raw["player_trade"] = {"enabled": True}

        result = _load(raw, tmp_path)

        assert result.player_trade_offer_expires_in_ticks is None

    def test_a_declared_value_is_read(self, tmp_path: Path) -> None:
        """宣言した手番数がそのまま読み取られる。"""
        raw = _raw()
        raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": 24}

        result = _load(raw, tmp_path)

        assert result.player_trade_offer_expires_in_ticks == 24


class TestAnUnusableExpiryIsRefusedAtLoadTime:
    """成立しえない期限は、読み込みの時点で落とす。

    実 run が終わるまで「なぜか取引が成立しない」で悩まないため。
    """

    @pytest.mark.parametrize("value", [0, -1])
    def test_a_non_positive_expiry_is_refused(self, tmp_path: Path, value: int) -> None:
        """0 以下の手番数は読み込めない (作った瞬間に流れる提案を作らない)。"""
        raw = _raw()
        raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": value}

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "offer_expires_in_ticks" in str(exc.value)

    def test_a_boolean_is_refused(self, tmp_path: Path) -> None:
        """真偽値は整数として通さない。

        Python では `bool` が `int` の派生なので、素直に書くと `True` が
        1 手番として通る。**作った次の手番に流れる世界**が、書いた人の意図
        しない形で生まれる。
        """
        raw = _raw()
        raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": True}

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "offer_expires_in_ticks" in str(exc.value)

    @pytest.mark.parametrize("value", ["24", 24.0, [24]])
    def test_a_non_integer_is_refused(self, tmp_path: Path, value: Any) -> None:
        """整数でない値は読み込めない。"""
        raw = _raw()
        raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": value}

        with pytest.raises(ScenarioLoadError):
            _load(raw, tmp_path)


class TestTheDeclarationReachesTheOffer:
    """宣言が、実際に作られる提案の期限まで届いている。

    読めているのに配線されていないと、シナリオに書いたのに効かない静かな
    失敗になる。**宣言と、宣言が効いていない世界の両方**を見る。
    """

    def test_a_declared_expiry_changes_when_the_offer_runs_out(
        self, tmp_path: Path
    ) -> None:
        """宣言した手番数のあとに提案が流れる。"""
        raw = _raw()
        raw["players"].append({
            "id": "tom", "name": "トム",
            "spawn_spot": raw["players"][0]["spawn_spot"],
            "initial_items": [], "initial_gold": 50,
            "persona_prompt": "あなたはトム。",
        })
        raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": 24}
        path = tmp_path / "market_town_v1.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(str(path))

        offer = _make_offer(runtime)

        assert offer.expires_at_tick == runtime.current_tick() + 24

    def test_the_engine_default_applies_without_a_declaration(
        self, tmp_path: Path
    ) -> None:
        """宣言しなければ engine の既定 (10 手番) のままになる。

        正の対照。宣言を読む経路を壊したときに、上のテストだけだと「既定へ
        倒れた」ことに気付けない。
        """
        raw = _raw()
        raw["players"].append({
            "id": "tom", "name": "トム",
            "spawn_spot": raw["players"][0]["spawn_spot"],
            "initial_items": [], "initial_gold": 50,
            "persona_prompt": "あなたはトム。",
        })
        raw["player_trade"] = {"enabled": True}
        path = tmp_path / "market_town_v1.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(str(path))

        offer = _make_offer(runtime)

        assert offer.expires_at_tick == runtime.current_tick() + 10


def _make_offer(runtime: Any):
    """レナからトムへ提案を 1 件、実サービス経由で作る。"""
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId

    return runtime._player_trade_service.offer(
        PlayerId(1),
        target=PlayerId(2),
        gives_items=(),
        gives_gold=5,
        asks_item_labels=({"item_label": "薬草", "quantity": 1},),
        asks_gold=0,
        current_tick=runtime.current_tick(),
    )
