"""前提条件を否定形で書けることを保証する。

## なぜ enum を増やすのをやめるか

否定が要るたびに専用の enum を足してきた結果、すでに 5 対ある。

    TIME_OF_DAY_IS / TIME_OF_DAY_IS_NOT
    WEATHER_IS / WEATHER_IS_NOT
    SPOT_LIGHTING_IS / SPOT_LIGHTING_IS_NOT
    AT_SPOT_IS / AT_SPOT_IS_NOT
    TARGET_HAS_ITEM / TARGET_HAS_NO_ITEM

**種類が 2 倍に増え続ける構造**で、条件を 1 つ足すたびに評価器の分岐も
#905 の可視クラスの分類表も 2 つ増える。6 対目 (「倒れていない相手だけ」)
を足す前に止める。

## 条件エンジンの統合ではない

負債マップ (docs/precondition_target_state_debt_map.md) は「4 系統の条件
エンジン統合は非推奨」としている。`negate` はそれとは別で、権威実装
(spot_interaction_service) が 1 箇所で否定を扱うだけ。discovery /
scenario_event の別系統には触らない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)


class TestNegateInvertsTheResult:
    """`negate` を付けると、条件の成否が反転する。

    実経路 (シナリオ → runtime → 対人 interaction) で確かめる。テスト専用の
    入口を作ると、本番が通らない形でも通ってしまう。
    """

    def _runtime_with_negated_strike(self, tmp_path):
        """「倒れていない相手にだけ襲える」を宣言したシナリオを組む。"""
        import json
        from pathlib import Path

        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        src = (
            Path(__file__).resolve().parents[3]
            / "data" / "scenarios" / "station_drill.json"
        )
        raw = json.loads(src.read_text(encoding="utf-8"))
        strike = next(
            i for i in raw["player_interactions"] if i["action_name"] == "strike_down"
        )
        strike["preconditions"].append({
            "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
            "negate": True,
            "failure_message": "相手はもう動かない。",
        })
        path = tmp_path / "negated.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return create_world_runtime(path)

    def _prepare(self, rt):
        """キーパーに刃物を持たせ、暗い通路で被害者と二人にする。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        def mv(p, s):
            g = rt._spot_graph_repo.find_graph()
            g.unplace_entity(EntityId.create(int(p)))
            g.place_entity(
                EntityId.create(int(p)),
                SpotId.create(rt.id_mapper.get_int("spot", s)),
            )
            rt._spot_graph_repo.save(g)

        keeper, victim = PlayerId(3), PlayerId(2)
        mv(keeper, "storage")
        rt.do_interact(keeper, "supply_shelf", "find_cutter")
        mv(keeper, "corridor")
        mv(victim, "corridor")
        return keeper, victim

    def test_a_standing_target_can_still_be_attacked(self, tmp_path) -> None:
        """立っている相手には従来どおり襲える。

        否定形を足したせいで本来の用途まで塞がっていないかを見る。
        """
        rt = self._runtime_with_negated_strike(tmp_path)
        keeper, victim = self._prepare(rt)

        rt.do_interact_with_player(keeper, victim, "strike_down")

        assert rt._player_status_repo.find_by_id(victim).hp.value < 100

    def test_a_downed_target_can_no_longer_be_attacked(self, tmp_path) -> None:
        """倒れた相手は襲えない。

        **これが目的。** 死体に「背後から襲う」が出る歪みを、シナリオの
        宣言で塞げるようにする。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        rt = self._runtime_with_negated_strike(tmp_path)
        keeper, victim = self._prepare(rt)
        status = rt._player_status_repo.find_by_id(victim)
        status.apply_damage(status.hp.value)
        rt._player_status_repo.save(status)

        with pytest.raises(InteractionNotAllowedException) as e:
            rt.do_interact_with_player(keeper, victim, "strike_down")

        assert "もう動かない" in str(e.value)

    def test_without_negate_a_downed_target_is_still_attackable(self, tmp_path) -> None:
        """宣言しなければ従来どおり (倒れた相手にも襲える)。

        既存シナリオの挙動を変えていないことを固定する。
        """
        import json
        from pathlib import Path

        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        src = (
            Path(__file__).resolve().parents[3]
            / "data" / "scenarios" / "station_drill.json"
        )
        path = tmp_path / "plain.json"
        path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        rt = create_world_runtime(path)
        keeper, victim = self._prepare(rt)
        status = rt._player_status_repo.find_by_id(victim)
        status.apply_damage(status.hp.value)
        rt._player_status_repo.save(status)

        rt.do_interact_with_player(keeper, victim, "strike_down")  # 例外にならない


class TestNegateIsAllowedOnlyWhereItWasThoughtThrough:
    """否定してよい条件は明示の許可制。

    条件の分岐には「満たしていない」と**「評価できない」**(provider 未配線
    など) が混ざっている。後者を機械的に反転すると、配線ミスが「条件を
    満たした」に化けて素通りする。**静かな失敗を新しく作ることになる。**

    だから許可した種別だけ反転させ、それ以外は読み込み時に落とす。増やす
    ときは、その種別の「評価できない」経路を確かめてから足す。
    """

    def test_an_unlisted_condition_is_rejected_at_load(self, tmp_path) -> None:
        """許可していない種別に negate を書くと読み込みで落ちる。"""
        import json
        from pathlib import Path

        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
            ScenarioLoader,
        )

        src = (
            Path(__file__).resolve().parents[3]
            / "data" / "scenarios" / "station_drill.json"
        )
        raw = json.loads(src.read_text(encoding="utf-8"))
        strike = next(
            i for i in raw["player_interactions"] if i["action_name"] == "strike_down"
        )
        strike["preconditions"].append({
            "condition_type": "HAS_ITEM",
            "required_item": "cutter",
            "negate": True,
        })
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(path)


class TestNoNewNegatedMemberIsAdded:
    """否定専用の enum をこれ以上増やさない。

    落ちたら、その否定は `negate: true` で書けないか考える。書けないなら
    `_LEGACY` に足す理由を書く。**足す前に止めるのがこのテストの仕事。**
    """

    #: `negate` を入れる前から在る否定専用の種別。
    #:
    #: 既存シナリオが使っているので消さない。新しく足さないためだけの一覧。
    _LEGACY = {
        "TIME_OF_DAY_IS_NOT",
        "WEATHER_IS_NOT",
        "SPOT_LIGHTING_IS_NOT",
        "AT_SPOT_IS_NOT",
        "TARGET_HAS_NO_ITEM",
    }

    def test_no_unexpected_negated_member(self) -> None:
        """否定専用の種別が、既知の 5 つから増えていない。"""
        negated = {
            c.value
            for c in InteractionConditionTypeEnum
            if c.value.endswith("_IS_NOT") or "_HAS_NO_" in c.value
        }

        assert negated == self._LEGACY, (
            f"否定専用の種別が増減しています: {sorted(negated ^ self._LEGACY)}。"
            "新しい否定は negate: true で書いてください"
        )

    def test_the_legacy_members_still_exist(self) -> None:
        """既存の 5 つは消えていない。

        消すと既存シナリオが読み込めなくなる。置き換えるなら移行が要る。
        """
        known = {c.value for c in InteractionConditionTypeEnum}

        assert self._LEGACY <= known


class TestScenariosCanWriteIt:
    """シナリオ JSON から書ける。"""

    def test_negate_is_parsed(self, tmp_path) -> None:
        """`"negate": true` が読み込まれる。

        domain が対応しても loader が読まなければシナリオには書けない
        (initial_state で二度作った形)。
        """
        import json
        from pathlib import Path

        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        src = (
            Path(__file__).resolve().parents[3]
            / "data" / "scenarios" / "station_drill.json"
        )
        raw = json.loads(src.read_text(encoding="utf-8"))
        strike = next(
            i for i in raw["player_interactions"] if i["action_name"] == "strike_down"
        )
        strike["preconditions"].append({
            "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
            "negate": True,
            "failure_message": "相手はもう動かない。",
        })
        path = tmp_path / "negated.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        result = ScenarioLoader().load_from_file(path)

        loaded = next(
            i for i in result.player_interactions if i.action_name == "strike_down"
        )
        negated = [c for c in loaded.preconditions if c.negate]
        assert len(negated) == 1
        assert negated[0].failure_message == "相手はもう動かない。"
