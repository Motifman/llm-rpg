"""人が持つ属性の宣言が、条件評価まで届くことを保証する。

## なぜこの試験が要るか

実 run (v3.2 t24–t33) で、焼き手が摘み手に**窯の使い方を教える取引**を持ちかけ、
摘み手はそれを受けて待った。生業は変えられないので**永久に焼けない**。engine は
「足りない前提を先に満たすこと」と助言していた。**10 手番が消えた。**

物体には答えがある (#380: 待てば戻る / もう変わらない)。**人の側には無い。**

## この PR の範囲

**宣言とドメインの判定まで。表示は 1 ビットも変えない。**

`NEVER` を表示に反映するのは次の PR で、ここでは「宣言が判定に届いていること」と
「**届いても見え方が変わらないこと**」の両方を見る。後者が無いと、既存 run への
影響を切り分けられない。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    AttributeVisibility,
    ConditionSatisfiability,
    PlayerAttributeSpec,
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_TOWN = _SCENARIOS / "market_town_v3_board.json"
_DRILL = _SCENARIOS / "station_drill.json"

#: 市場町の生業。**実際にシナリオが使っている値**を書く。
_TRADE = {
    "display_name": "生業",
    "visibility": "public",
    "mutable": False,
    "values": ["picker", "baker", "reaper"],
}


def _specs(**overrides: Any) -> PlayerAttributeSpecs:
    spec = PlayerAttributeSpec(
        name="trade",
        display_name="生業",
        visibility=AttributeVisibility.PUBLIC,
        mutable=overrides.get("mutable", False),
    )
    return PlayerAttributeSpecs(by_name={"trade": spec})


class TestWhatCannotBeChangedIsSaidToBeImpossible:
    """変えられない属性は、満たしていなければ永久に満たせない。"""

    def test_an_immutable_mismatch_is_never(self) -> None:
        """変えられない属性が食い違っていれば `NEVER`。"""
        assert _specs().satisfiability(
            {"trade": "baker"}, {"trade": "picker"}
        ) is ConditionSatisfiability.NEVER

    def test_a_mutable_mismatch_is_only_not_yet(self) -> None:
        """変えられる属性なら `NOT_YET` (まだ満たしていないだけ)。"""
        assert _specs(mutable=True).satisfiability(
            {"trade": "baker"}, {"trade": "picker"}
        ) is ConditionSatisfiability.NOT_YET

    def test_a_match_is_satisfied_regardless(self) -> None:
        """満たしていれば、変えられるかに関係なく `SATISFIED`。"""
        for mutable in (True, False):
            assert _specs(mutable=mutable).satisfiability(
                {"trade": "baker"}, {"trade": "baker"}
            ) is ConditionSatisfiability.SATISFIED

    def test_an_undeclared_attribute_stays_not_yet(self) -> None:
        """宣言の無い属性は従来どおり (**変えられる前提**)。

        **新しい規則を既定にしない。** 既定を変えると、過去の run と
        比べられなくなる。
        """
        assert PlayerAttributeSpecs.empty().satisfiability(
            {"trade": "baker"}, {"trade": "picker"}
        ) is ConditionSatisfiability.NOT_YET

    def test_one_immutable_mismatch_makes_the_whole_thing_never(self) -> None:
        """複数の条件のうち 1 つでも変えられず食い違えば、全体が `NEVER`。

        残りが変えられても、**全体としては永久に満たせない**。
        """
        specs = PlayerAttributeSpecs(by_name={
            "trade": PlayerAttributeSpec(
                "trade", "生業", AttributeVisibility.PUBLIC, mutable=False
            ),
            "mood": PlayerAttributeSpec(
                "mood", "機嫌", AttributeVisibility.PUBLIC, mutable=True
            ),
        })

        assert specs.satisfiability(
            {"trade": "baker", "mood": "calm"},
            {"trade": "picker", "mood": "angry"},
        ) is ConditionSatisfiability.NEVER

    def test_an_unreadable_actor_is_not_declared_impossible(self) -> None:
        """行為者の状態が読めないときは `NOT_YET`。

        **分からないことを「永久に無理」と断定しない。** 断定すると、
        成立しうる行動を諦めさせる。`NEVER` に 2 種類 (本当に無理 /
        見えていない) を作らない。
        """
        assert _specs().satisfiability(
            {"trade": "baker"}, None
        ) is ConditionSatisfiability.NOT_YET


class TestTheDeclarationIsRead:
    """宣言が読め、壊れた宣言は起動時に落ちる。"""

    def _world(self, tmp_path: Path, attributes: Any) -> Any:
        raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
        # 市場町は自分で属性を宣言している。上書きしないことを「宣言が
        # 無い」と読み替えないよう、先に外す。
        raw.pop("player_attributes", None)
        if attributes is not None:
            raw["player_attributes"] = attributes
        path = tmp_path / "town.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return create_world_runtime(str(path))

    def test_the_declaration_is_kept(self, tmp_path: Path) -> None:
        """宣言した内容がそのまま保持される。"""
        runtime = self._world(tmp_path, {"trade": _TRADE})

        spec = runtime.scenario.player_attribute_specs.spec_of("trade")

        assert spec.visibility is AttributeVisibility.PUBLIC
        assert spec.mutable is False
        assert spec.values == ("picker", "baker", "reaper")

    def test_a_world_without_the_section_still_loads(self, tmp_path: Path) -> None:
        """宣言の無いシナリオも読める (**正の対照**)。"""
        runtime = self._world(tmp_path, None)

        assert runtime.scenario.player_attribute_specs.by_name == {}

    @pytest.mark.parametrize("broken", [
        {"trade": {"visibility": "maybe", "mutable": False}},
        {"trade": {"visibility": "public", "mutable": "no"}},
        {"trade": {"visibility": "public", "mutable": False, "values": "baker"}},
        {"trade": "public"},
    ])
    def test_a_broken_declaration_stops_the_world(
        self, tmp_path: Path, broken: Any,
    ) -> None:
        """宣言が壊れていたら起動時に落ちる。

        黙って既定へ倒すと、**書いたつもりで効いていない**世界ができる。
        """
        with pytest.raises(ScenarioLoadError):
            self._world(tmp_path, broken)

    def test_values_are_optional(self, tmp_path: Path) -> None:
        """`values` は書かなくてよい。

        数値や時刻の属性には列挙が無い。**必須にすると書けない属性ができる。**
        """
        runtime = self._world(
            tmp_path, {"mood": {"visibility": "secret", "mutable": True}}
        )

        assert runtime.scenario.player_attribute_specs.spec_of("mood").values == ()


class TestTheDeclarationReachesTheJudgement:
    """宣言が、実際の行為者の判定まで届く。"""

    def test_the_picker_can_never_bake(self, tmp_path: Path) -> None:
        """生業を不変と宣言した世界で、摘み手は永久に焼けないと判定される。

        **パースが通っただけでは足りない。** 宣言が判定に届いていない
        「読んだが使っていない」を通さないために、実際の行為者の状態で見る。
        """
        raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
        raw["player_attributes"] = {"trade": _TRADE}
        path = tmp_path / "town.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(str(path))

        picker = runtime._player_status_repo.find_by_id(PlayerId(1))
        verdict = runtime.scenario.player_attribute_specs.satisfiability(
            {"trade": "baker"}, picker.state
        )

        assert picker.state == {"trade": "picker"}
        assert verdict is ConditionSatisfiability.NEVER


class TestNothingTheAgentReadsHasChanged:
    """宣言を足しても、system prompt は 1 ビットも変わらない。

    表示への反映は「現在の状況」の行だけで起きる。system prompt まで
    動くと、プレフィックスキャッシュが壊れて run のコストが変わる。
    """

    @pytest.mark.parametrize("scenario_path", [_TOWN, _DRILL])
    def test_the_prompts_are_byte_identical(
        self, tmp_path: Path, scenario_path: Path,
    ) -> None:
        """宣言を足す前と後で、全プレイヤーのプロンプトがバイト一致する。"""
        raw: Dict[str, Any] = json.loads(scenario_path.read_text(encoding="utf-8"))
        before = create_world_runtime(str(scenario_path))

        raw["player_attributes"] = {"trade": _TRADE}
        declared_path = tmp_path / "declared.json"
        declared_path.write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )
        after = create_world_runtime(str(declared_path))

        assert _prompt_hashes(after) == _prompt_hashes(before)

    def test_the_oven_row_no_longer_says_only_that_nothing_is_possible(
        self, tmp_path: Path,
    ) -> None:
        """石窯の行が、待っても変わらないことを言うようになった。

        **この試験は PR #1219 の時点とは逆を見ている。** 当時は「宣言を
        足しても見え方が 1 ビットも変わらない」ことを見ていた。表示への
        反映を入れた PR で、その pin は役目を終えて置き換わった。

        ここでは配列形式 (呼び名なし) の宣言なので、属性の種類を言わない
        文になる。呼び名つきの宣言で「焼き手だけが扱える」と出ることは
        ``test_say_who_can_use_it.py`` が見る。
        """
        raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
        raw["player_attributes"] = {"trade": _TRADE}
        path = tmp_path / "town.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(str(path))

        runtime.do_move(PlayerId(1), "bake_house")
        for _ in range(2):
            runtime.advance_tick()
        line = next(
            line
            for line in runtime.build_llm_context(
                PlayerId(1)
            ).current_state_text.splitlines()
            if '"石窯"' in line
        )

        assert "いまのあなたには扱えない" in line
        assert "生業" not in line
        assert "焼き手" not in line


def _prompt_hashes(runtime: Any) -> Dict[int, str]:
    return {
        player_id: hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for player_id, prompt in (
            runtime._world_llm_system_prompts_by_player_id.items()
        )
    }
