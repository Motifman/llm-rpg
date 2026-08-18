"""扱えない物体に「では誰なら扱えるか」を出す。

## なぜこの試験が要るか

実 run (v3.2 t24–t33) で、摘み手が焼き手から**窯の使い方を教わる取引**を受けて
待った。生業は変えられないので**永久に焼けない**。#1219 で世界は「永久に無理」を
判定できるようになったが、**その判定は誰にも見えていなかった**。

石窯の行はこう出ていた。

    - "石窯" — 熾火を抱えた石窯。… [いまのあなたに扱える操作はない]

「いま」と書いてあるので、待てば変わると読める。しかも**誰に頼めばいいか**を
言っていない。市場の要は「自分にできないことを他人に買う」なので、そこが
空白だと board へ向かう理由が 1 つ消える。

## 何を決めたか

注記は ``<値の呼び名>だけが扱える``。**呼び名は作者が書いたものだけ**を使い、
属性の種類 (生業 / 種族 / 身分) は engine が決め打ちしない。

3 案を実際に描画して決めた。作者が書いた ``failure_message`` をそのまま出す案は
**却下**した。あの文面は「呼んだ人ひとりへの応答」として書かれていて、一覧に
常時出る注記としては書かれていない (「パンを焼けるのは**あの人**だけだ」— あの人が
誰か分からず、焼き手は 2 人いるのに単数)。

型を ``<呼び名>の仕事`` にしかけたのも描画で差し戻した。生業なら通るが、種族を
同じ経路に通すと「エルフの仕事」になる。

## この試験が守る境界

**出る位置は増やさない。** 従来 ``[いまのあなたに扱える操作はない]`` が出ていた
行だけが具体になる。

**伏せた属性では出さない。** そして伏せた属性が混ざっていても、公開された
ぶんはそのまま出す。混在を理由に全部伏せると、**公開側の出力が伏せた属性の
有無で変わり、そこから伏せた属性の存在が読める**。
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_TOWN = _SCENARIOS / "market_town_v3_board.json"
_DRILL = _SCENARIOS / "station_drill.json"

#: 従来の注記。**この文が出る行だけ**が、具体的な注記に置き換わる。
_OLD_NOTE = "いまのあなたに扱える操作はない"
#: 呼び名が宣言されていないときの注記。**属性の種類を言わない。**
_NO_NAME = "いまのあなたには扱えない"

_PICKER = PlayerId(1)

#: 呼び名つきの生業の宣言。
_TRADE_NAMED = {
    "display_name": "生業",
    "visibility": "public",
    "mutable": False,
    "values": {"picker": "摘み手", "baker": "焼き手", "reaper": "刈り手"},
}
#: 呼び名の無い生業の宣言 (#1219 の配列形式)。
_TRADE_UNNAMED = {
    "display_name": "生業",
    "visibility": "public",
    "mutable": False,
    "values": ["picker", "baker", "reaper"],
}


def _oven(raw: Dict[str, Any]) -> Dict[str, Any]:
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            if obj["name"] == "石窯":
                return obj
    raise AssertionError("石窯がシナリオから消えています")


def _town(
    tmp_path: Path,
    stem: str,
    *,
    attributes: Optional[Dict[str, Any]] = None,
    oven_required: Optional[Dict[str, Any]] = None,
    extra_oven_actions: Optional[List[Dict[str, Any]]] = None,
    initial_state: Optional[Dict[str, Any]] = None,
) -> Any:
    """市場町を土台に、属性の宣言と石窯の条件だけを差し替えた世界を作る。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    # **宣言を明示的に外す。** 市場町は自分で属性を宣言しているので、
    # 「上書きしない = 宣言が無い」ではない。ここを黙って土台任せにすると、
    # 「宣言の無い世界」を見ているつもりの試験が、宣言済みの世界を見る。
    raw.pop("player_attributes", None)
    if attributes is not None:
        raw["player_attributes"] = attributes
    oven = _oven(raw)
    if oven_required is not None:
        oven["interactions"][0]["preconditions"][0]["required_state"] = oven_required
    for extra in extra_oven_actions or ():
        action = copy.deepcopy(oven["interactions"][0])
        action["action_name"] = extra["action_name"]
        action["display_label"] = extra.get("display_label", extra["action_name"])
        if extra.get("required_state") is None:
            action["preconditions"] = [
                cond
                for cond in action["preconditions"]
                if cond["condition_type"] != "PLAYER_STATE_IS"
            ]
        else:
            action["preconditions"][0]["required_state"] = extra["required_state"]
        oven["interactions"].append(action)
    for spawn in raw["players"]:
        spawn.setdefault("initial_state", {}).update(initial_state or {})
    path = tmp_path / f"{stem}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _oven_line(runtime: Any, player_id: PlayerId = _PICKER) -> str:
    """その人がかまど小屋で読む、石窯の行。"""
    runtime.do_move(player_id, "bake_house")
    for _ in range(2):
        runtime.advance_tick()
    text = runtime.build_llm_context(player_id).current_state_text
    return next(
        line for line in text.splitlines() if '"石窯"' in line
    )


def _prompt_hashes(runtime: Any) -> Dict[int, str]:
    return {
        player_id: hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for player_id, prompt in (
            runtime._world_llm_system_prompts_by_player_id.items()
        )
    }


class TestTheRowSaysWhoCanUseIt:
    """扱えない物体の行が、誰なら扱えるかを言う。"""

    def test_the_value_display_name_is_used(self, tmp_path: Path) -> None:
        """値の呼び名が宣言されていれば「焼き手だけが扱える」と出る。"""
        runtime = _town(tmp_path, "named", attributes={"trade": _TRADE_NAMED})

        assert "[焼き手だけが扱える]" in _oven_line(runtime)

    def test_the_attribute_kind_is_never_invented(self, tmp_path: Path) -> None:
        """呼び名が無ければ、属性の種類を言わない文に落ちる。

        「あなたの生業では扱えない」と書くと、``race`` や ``standing`` を
        同じ経路に通したときに嘘になる。**世界が名前を持っていないものを、
        engine が代わりに名付けない。**
        """
        line = _oven_line(_town(tmp_path, "unnamed", attributes={"trade": _TRADE_UNNAMED}))

        assert f"[{_NO_NAME}]" in line
        assert "生業" not in line

    def test_the_authors_response_text_is_not_reused(self, tmp_path: Path) -> None:
        """作者が書いた ``failure_message`` を注記に流用しない。

        あの文面は**呼んだ人ひとりへの応答**として書かれている。市場町の
        文面は「パンを焼けるのは**あの人**だけだ」で、常時表示に置くと
        誰を指すのか分からず、焼き手が 2 人いる事実とも食い違う。
        """
        line = _oven_line(_town(tmp_path, "no-reuse", attributes={"trade": _TRADE_NAMED}))

        assert "あの人" not in line
        assert "火加減" not in line


class TestOnlyWhatIsPermanentIsSaid:
    """永久に届かないぶんだけを言う。"""

    def test_a_changeable_mismatch_keeps_the_old_note(self, tmp_path: Path) -> None:
        """変えられる属性が足りないだけなら、行は従来のままにする。

        「いまは無理だが、いずれ通る」ので、**注記が無いこと自体が正しい
        情報**である。ここに理由を出すと、伏せた条件の存在まで漏れる。
        """
        runtime = _town(
            tmp_path,
            "not-yet",
            attributes={
                "mood": {
                    "display_name": "機嫌",
                    "visibility": "public",
                    "mutable": True,
                    "values": {"calm": "落ち着いた人", "angry": "苛立った人"},
                }
            },
            oven_required={"mood": "calm"},
            initial_state={"mood": "angry"},
        )

        assert f"[{_OLD_NOTE}]" in _oven_line(runtime)

    def test_only_the_permanent_half_of_a_mixed_requirement_is_said(
        self, tmp_path: Path
    ) -> None:
        """変えられない要求と変えられる要求が混ざれば、前者だけを出す。"""
        line = _oven_line(_town(
            tmp_path,
            "mixed",
            attributes={
                "trade": _TRADE_NAMED,
                "mood": {
                    "display_name": "機嫌",
                    "visibility": "public",
                    "mutable": True,
                    "values": {"calm": "落ち着いた人", "angry": "苛立った人"},
                },
            },
            oven_required={"trade": "baker", "mood": "calm"},
            initial_state={"mood": "angry"},
        ))

        assert "[焼き手だけが扱える]" in line
        assert "落ち着いた人" not in line


class TestWhatIsHiddenStaysHidden:
    """伏せた属性は注記にしない。"""

    def test_a_secret_attribute_keeps_the_old_note(self, tmp_path: Path) -> None:
        """伏せた属性が理由なら、行は従来のままにする。"""
        runtime = _town(
            tmp_path,
            "secret",
            attributes={
                "trade": {
                    "display_name": "生業",
                    "visibility": "secret",
                    "mutable": False,
                    "values": _TRADE_NAMED["values"],
                }
            },
        )

        assert f"[{_OLD_NOTE}]" in _oven_line(runtime)
        assert "焼き手" not in _oven_line(runtime)

    def test_the_public_half_survives_a_secret_neighbour(
        self, tmp_path: Path
    ) -> None:
        """公開された属性と伏せた属性が混ざっても、公開されたぶんは出す。

        混在を理由に全部伏せると、**公開側の出力が伏せた属性の有無で
        変わる**。そこから伏せた属性の存在が読めるので、伏せ方が伏せて
        いることを漏らす。
        """
        line = _oven_line(_town(
            tmp_path,
            "mixed-visibility",
            attributes={
                "trade": _TRADE_NAMED,
                "role": {
                    "display_name": "役割",
                    "visibility": "secret",
                    "mutable": False,
                    "values": {"werewolf": "人狼", "villager": "村人"},
                },
            },
            oven_required={"trade": "baker", "role": "werewolf"},
            initial_state={"role": "villager"},
        ))

        assert "[焼き手だけが扱える]" in line
        assert "人狼" not in line
        assert "役割" not in line

    def test_declaring_a_secret_attribute_changes_no_prompt(
        self, tmp_path: Path
    ) -> None:
        """伏せた属性を宣言しても、全プレイヤーのプロンプトがバイト一致する。

        注記の実装を入れたあと、**伏せる分岐だけを壊しても緑になる**形では
        意味がないので、行ではなくプロンプト全文で見る。
        """
        before = _town(tmp_path, "no-decl")
        after = _town(
            tmp_path,
            "secret-decl",
            attributes={
                "trade": {
                    "display_name": "生業",
                    "visibility": "secret",
                    "mutable": False,
                    "values": _TRADE_NAMED["values"],
                }
            },
        )

        assert _prompt_hashes(after) == _prompt_hashes(before)


class TestManyReasonsAreSaidOnceAndInOrder:
    """複数の理由は、宣言順に、重複なく並ぶ。"""

    def test_several_reasons_follow_the_declared_order(
        self, tmp_path: Path
    ) -> None:
        """3 つの要求が、シナリオに書かれた順で並ぶ。

        **3 つ以上で、宣言順と辞書順が食い違う組み合わせで見る。** 2 つだと
        dict や set の反復順と偶然一致して、順序を見ているつもりで何も
        見ていない試験になる (ここでは辞書順なら race → standing → trade)。
        """
        line = _oven_line(_town(
            tmp_path,
            "order",
            attributes={
                "trade": _TRADE_NAMED,
                "standing": {
                    "display_name": "身分",
                    "visibility": "public",
                    "mutable": False,
                    "values": {"guild_member": "ギルド員", "townsfolk": "町の者"},
                },
                "race": {
                    "display_name": "種族",
                    "visibility": "public",
                    "mutable": False,
                    "values": {"elf": "エルフ", "human": "人間"},
                },
            },
            oven_required={
                "trade": "baker",
                "standing": "guild_member",
                "race": "elf",
            },
            initial_state={"standing": "townsfolk", "race": "human"},
        ))

        assert (
            "[焼き手だけが扱える、ギルド員だけが扱える、エルフだけが扱える]"
            in line
        )

    def test_the_same_reason_is_not_repeated(self, tmp_path: Path) -> None:
        """同じ値を要求する操作が 2 つあっても、注記は 1 回だけ出る。

        注記は物体単位なので、**何回要求されたかは読み手にとって情報では
        ない。**
        """
        line = _oven_line(_town(
            tmp_path,
            "dedupe",
            attributes={"trade": _TRADE_NAMED},
            extra_oven_actions=[{
                "action_name": "bake_flatbread",
                "display_label": "平パンを焼く",
                "required_state": {"trade": "baker"},
            }],
        ))

        assert line.count("焼き手だけが扱える") == 1


class TestTheNoteAppearsWhereItAlreadyDid:
    """注記が出る行を増やさない。"""

    def test_an_object_with_something_left_to_do_gets_no_note(
        self, tmp_path: Path
    ) -> None:
        """使える操作が 1 つでも残っていれば、注記は出ない (従来どおり)。

        **この PR はこの穴を解いていない。** 注記は物体単位なので、使える
        操作が残ると、落ちた操作の存在自体が見えないままになる。摘み手は
        石窯に「パンを焼く」があることを知る道が無い。
        """
        line = _oven_line(_town(
            tmp_path,
            "partial",
            attributes={"trade": _TRADE_NAMED},
            extra_oven_actions=[{
                "action_name": "peek_into_oven",
                "display_label": "窯を覗く",
                "required_state": None,
            }],
        ))

        assert "peek_into_oven" in line
        assert "焼き手だけが扱える" not in line
        assert _OLD_NOTE not in line

    def test_a_world_without_the_declaration_is_untouched(
        self, tmp_path: Path
    ) -> None:
        """属性を宣言していない世界の行は、従来の注記のまま (**正の対照**)。"""
        assert f"[{_OLD_NOTE}]" in _oven_line(_town(tmp_path, "plain"))

    def test_another_scenario_is_byte_identical(self, tmp_path: Path) -> None:
        """別のシナリオに宣言を足しても、プロンプトがバイト一致する。"""
        raw: dict = json.loads(_DRILL.read_text(encoding="utf-8"))
        before = create_world_runtime(str(_DRILL))
        raw["player_attributes"] = {"trade": _TRADE_NAMED}
        path = tmp_path / "drill.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        assert _prompt_hashes(create_world_runtime(str(path))) == _prompt_hashes(before)


class TestTheDeclarationOfValueNames:
    """値の呼び名の宣言が読め、壊れていれば起動時に落ちる。"""

    def test_the_object_form_is_read(self, tmp_path: Path) -> None:
        """オブジェクト形式は、取りうる値と呼び名の両方になる。"""
        runtime = _town(tmp_path, "obj-form", attributes={"trade": _TRADE_NAMED})
        spec = runtime.scenario.player_attribute_specs.spec_of("trade")

        assert spec.values == ("picker", "baker", "reaper")
        assert spec.display_name_of_value("baker") == "焼き手"

    def test_the_array_form_still_works(self, tmp_path: Path) -> None:
        """配列形式は従来どおり読め、呼び名は無い (#1219 の後方互換)。

        呼び名を必須にすると、**値に名前を付けようがない属性**が書けなくなる。
        """
        runtime = _town(tmp_path, "list-form", attributes={"trade": _TRADE_UNNAMED})
        spec = runtime.scenario.player_attribute_specs.spec_of("trade")

        assert spec.values == ("picker", "baker", "reaper")
        assert spec.display_name_of_value("baker") is None

    @pytest.mark.parametrize("broken", [
        {"baker": ""},
        {"": "焼き手"},
        {"baker": 1},
    ])
    def test_a_broken_value_name_stops_the_world(
        self, tmp_path: Path, broken: Any,
    ) -> None:
        """呼び名が空や文字列でなければ起動時に落ちる。

        黙って無視すると、**書いたつもりで注記に出ない**世界ができる。
        """
        with pytest.raises(ScenarioLoadError):
            _town(
                tmp_path,
                "broken",
                attributes={"trade": {**_TRADE_NAMED, "values": broken}},
            )
