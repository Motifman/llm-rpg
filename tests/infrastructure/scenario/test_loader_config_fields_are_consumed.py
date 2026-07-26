"""loader が読み取った設定が、本番経路で誰にも使われないまま残るのを防ぐ。

## 何度も踏んでいる穴

- `initial_items` (PR #830): loader は parse し、`grant_initial_items_to_inventory`
  も存在したのに、**本番経路から一度も呼ばれていなかった**
- `initial_state` (PR #840): loader は型検証までしていたのに、
  `PlayerStatusAggregate` は常に空の state で作られていた

どちらも「シナリオに書いたのに効かない」形の静かな失敗で、しかも失敗文は
シナリオ作者が書いた文言が返るので**原因が文言の裏に隠れる**。実 run で
「なぜか一度も成功しない」としてしか現れない。

テストが通り続けていたのは、唯一の利用者が本番の配線を迂回して自前で
fixture を組んでいたため。だから「そのフィールドを使うテストがあるか」では
検出できない。**本番コード (src/) がそのフィールドを読むか**を見る。

## 名前一致だけでは足りない

同名フィールドが複数の設定クラスにあると区別できない。実際 `initial_state`
は `PlayerSpawnConfig` と `ScenarioWeatherConfig` の両方にあり、素朴に
「`.initial_state` が src/ に出現するか」を見るだけだと、**後者だけが
読まれている状態を「読まれている」と誤認**する。#840 を見逃した実際の理由が
これで、当時の走査は 0 件と報告していた。

そこで判定を 2 段にしてある。

1. 一意な名前 → 「src/ で参照が 0」なら落とす
2. 同名が複数クラスにある名前 → 受け手の変数名まで見て、そのクラス由来と
   思われる受け手が 1 つも無ければ落とす

2 の受け手推定は完全ではないので、判定できない場合は落とさず見逃す
(偽陽性でテストを不安定にするより、取りこぼしを許容する)。

## 検証

#830 の修正前のコミットで実行すると、`initial_items` と `initial_state` の
両方を検出する。当時これがあれば、どちらも出荷前に止められた。

## このテストが見ないこと

**参照が生きた経路にあるかは見ない。** 到達しない分岐の中に
`spawn.initial_items` が残っていれば「読まれている」と数える。宣言が
実際に効くことは、シナリオを 1 本書いて歩かせる e2e が担う
(`tests/demos/test_darkened_station_scenario.py` など)。
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "ai_rpg_world"
_LOADER = _SRC / "infrastructure" / "scenario" / "scenario_loader.py"

#: 本番経路が読まなくてよいフィールドと、その理由。
#:
#: 新しくここへ足すときは、**「読まれなくても壊れない」理由**を書くこと。
#: 「あとで使う」は理由にならない (それがまさに #830 / #840 の状態だった)。
_ALLOWED_UNCONSUMED: dict[tuple[str, str], str] = {
    ("ScenarioMetadata", "theme"): "人間向けの分類。実行時の挙動には効かせない",
    ("ScenarioMetadata", "difficulty"): "人間向けの分類。実行時の挙動には効かせない",
    ("ScenarioMetadata", "estimated_ticks"): "人間向けの目安。tick 上限は実験設定側で決める",
    ("ScenarioMetadata", "author"): "人間向けの出典表記",
    ("AreaDef", "position_source"): (
        "宣言座標か重心算出かの由来を示す派生値。シナリオ作者が書くもので"
        "はないので、読まれなくても宣言が無視されることはない"
    ),
    ("ItemSpecDefinition", "string_id"): (
        "loader 内部で文字列 id を int id へ写像するためのキー。写像後は"
        "int id だけで扱うので、runtime が読まないのが正しい"
    ),
    ("ScenarioLootTableDefinition", "string_id"): (
        "同上。loader 内部の id 写像専用"
    ),
    ("AreaDef", "description"): (
        "作者向けの覚書。設計 doc (spot_graph_distant_view_design.md) の"
        "表示文の優先順は distant_descriptions → visible_name の 2 段で、"
        "description は最初から含まれていない。metadata.description と同じ"
        "「人間向けで prompt に出さない」枠"
    ),
}

#: そのクラスの値が入っていそうな受け手変数名。同名フィールドを持つクラスを
#: 見分けるためだけに使う。ここに挙げた名前で受けていれば「読まれている」。
_RECEIVER_HINTS: dict[str, tuple[str, ...]] = {
    "PlayerSpawnConfig": ("spawn", "player_spawn", "s"),
    "ScenarioWeatherConfig": ("weather_config", "weather"),
    "ScenarioDayNightConfig": ("day_night_config", "day_night"),
    "AreaDef": ("area",),
    "DistantCueDef": ("cue",),
    "ItemSpecDefinition": ("item_def", "spec", "definition"),
    "InitialItemSpec": ("initial", "initial_item"),
    "ScenarioLootTableDefinition": ("loot_table", "table"),
    "ScenarioMonsterTemplate": ("template", "monster_template", "st"),
}


def _loader_config_classes() -> dict[str, list[str]]:
    """scenario_loader.py が定義する dataclass とそのフィールド名。"""
    tree = ast.parse(_LOADER.read_text(encoding="utf-8"))
    classes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "dataclass")
            for d in node.decorator_list
        )
        if not is_dataclass:
            continue
        fields = [
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
        if fields:
            classes[node.name] = fields
    return classes


def _field_accesses() -> dict[str, set[str]]:
    """loader 以外の src/ から `受け手.フィールド` を集める。

    `getattr(x, "field")` の動的アクセスも数える。遠景 cue 系はこの形でしか
    読まれておらず、属性構文だけを見ると「誰も読んでいない」と誤判定する。
    """
    accesses: dict[str, set[str]] = defaultdict(set)
    for path in _SRC.rglob("*.py"):
        if path == _LOADER:
            continue
        text = path.read_text(encoding="utf-8")
        for receiver, field in re.findall(
            r"\b([A-Za-z_][A-Za-z_0-9]*)\.([a-z_][a-z_0-9]*)\b", text
        ):
            accesses[field].add(receiver)
        for receiver, field in re.findall(
            r"getattr\(\s*([A-Za-z_][A-Za-z_0-9]*)\s*,\s*[\"']([a-z_][a-z_0-9]*)[\"']",
            text,
        ):
            accesses[field].add(receiver)
    return accesses


class TestLoaderConfigFieldsAreConsumed:
    """loader が作る設定フィールドが、本番コードから読まれている。"""

    def test_no_field_is_silently_unconsumed(self) -> None:
        """どの設定フィールドも src/ (loader 以外) から読まれている。

        読まれないフィールドは「シナリオに書いたのに効かない」宣言になる。
        意図的に読まないものは ``_ALLOWED_UNCONSUMED`` に理由つきで登録する。
        """
        classes = _loader_config_classes()
        accesses = _field_accesses()

        owners: dict[str, list[str]] = defaultdict(list)
        for cls, fields in classes.items():
            for field in fields:
                owners[field].append(cls)

        unconsumed: list[str] = []
        for cls, fields in sorted(classes.items()):
            for field in fields:
                if (cls, field) in _ALLOWED_UNCONSUMED:
                    continue
                receivers = accesses.get(field, set())
                if not receivers:
                    unconsumed.append(f"{cls}.{field} (src/ に参照なし)")
                    continue
                if len(owners[field]) == 1:
                    continue
                # 同名フィールドを持つクラスが複数ある。このクラス由来と
                # 思われる受け手が 1 つでもあれば「読まれている」とみなす。
                hints = _RECEIVER_HINTS.get(cls)
                if hints is None:
                    continue  # 見分けがつかないので見逃す (偽陽性を出さない)
                if not any(hint in receivers for hint in hints):
                    unconsumed.append(
                        f"{cls}.{field} (同名: {', '.join(owners[field])} / "
                        f"受け手: {', '.join(sorted(receivers)) or 'なし'})"
                    )

        assert not unconsumed, (
            "loader が読み取っているのに本番経路が使っていないフィールドがあります。\n"
            "シナリオに書いても効かない宣言になり、失敗文の裏に原因が隠れます "
            "(#830 / #840 と同じ形)。\n\n  "
            + "\n  ".join(unconsumed)
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        """許可リストに、既に存在しないフィールドが残っていない。

        古い項目が残ると、後から同名のフィールドを足したときに黙って
        見逃される。
        """
        classes = _loader_config_classes()
        stale = [
            f"{cls}.{field}"
            for (cls, field) in _ALLOWED_UNCONSUMED
            if field not in classes.get(cls, ())
        ]
        assert not stale, f"許可リストに存在しないフィールドが残っています: {stale}"

    def test_receiver_hints_point_at_real_classes(self) -> None:
        """受け手ヒントが、実在する設定クラスを指している。

        クラス名を変えたときにヒントだけ取り残されると、同名フィールドの
        判定が黙って無効化される。
        """
        classes = _loader_config_classes()
        unknown = [cls for cls in _RECEIVER_HINTS if cls not in classes]
        assert not unknown, f"存在しないクラスへのヒントが残っています: {unknown}"
