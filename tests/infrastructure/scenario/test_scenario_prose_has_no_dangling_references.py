"""切り出して作ったシナリオに、元シナリオの名残が残っていないことを保証する。

## なぜ要るか

`station_drill` を `darkened_station` から削って作ったとき、**部屋を消した
のに文だけが残った**。当番表と目的文が「発電室のレバーで照明を落とせる」
「無線室の送信機を直せ」と言い続け、4 人のエージェントは run のほぼ全体を
存在しない部屋への行き方の相談に費やして終わった。

    p4: ここから発電室には直接行けないのか！別ルートを探す必要がありそうだ
    p2: 配膳用の裏口から物資庫を通るか、連絡通路の別の分岐を探すかだ

存在しない裏口まで推測し始めていた。**run を 1 本まるごと潰す**威力がある
のに、テストは 1 つも落ちなかった。宣言 (spots) と文 (prose) が別々に
書かれていて、突き合わせる場所がどこにも無かったため。

## なぜ派生関係を明示するのか

最初は「どこかのシナリオでは部屋名だが、このシナリオには無い名前」を
全シナリオから探す形で書いた。**誤検出だらけで使い物にならなかった**
(「浜辺」「広場」「川岸」のような普通名詞が姉妹シナリオでは部屋名なので、
情景描写のたびに引っかかる)。

危ないのは**切り出したとき**なので、派生関係そのものを宣言する。
`_DERIVED` に 1 行足すのが、切り出した人の責任になる。宣言しなければ
検査されないが、うるさすぎて無効化される検出器よりはましと判断した。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_FIXTURE_SCENARIO_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios"
)

#: 切り出して作ったシナリオ → 元のシナリオ。
#:
#: 既存シナリオから部屋やオブジェクトを削って別シナリオを作ったら、ここに
#: 足すこと。元にあって自分に無いものを文が指していないかを検査する。
_DERIVED: dict[str, str] = {
    "station_drill.json": "darkened_station.json",
}


def _strings(node) -> list[str]:
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    if isinstance(node, str):
        return [node]
    return []


def _load(name: str) -> dict:
    path = _SCENARIO_DIR / name
    if not path.exists():
        path = _FIXTURE_SCENARIO_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _spot_names(raw: dict) -> set[str]:
    return {
        s["name"]
        for s in raw.get("spots", [])
        if isinstance(s.get("name"), str) and len(s["name"]) >= 2
    }


def _object_names(raw: dict) -> set[str]:
    return {
        o["name"]
        for s in raw.get("spots", [])
        for o in s.get("interior", {}).get("objects", [])
        if isinstance(o.get("name"), str) and len(o["name"]) >= 2
    }


@pytest.mark.parametrize("child,parent", sorted(_DERIVED.items()))
def test_no_prose_points_at_removed_places(child: str, parent: str) -> None:
    """削った部屋の名前が文に残っていない。

    落ちたら、部屋を消したときに文の書き換えが漏れている。文を直すか
    部屋を戻すかのどちらか。**文だけ残すと、エージェントは存在しないものを
    延々と探す。**
    """
    child_raw, parent_raw = _load(child), _load(parent)
    removed = _spot_names(parent_raw) - _spot_names(child_raw)

    prose = "\n".join(_strings(child_raw))
    dangling = sorted(name for name in removed if name in prose)

    assert not dangling, f"{child} が、削ったはずの場所を指しています: {dangling}"


@pytest.mark.parametrize("child,parent", sorted(_DERIVED.items()))
def test_no_prose_points_at_removed_objects(child: str, parent: str) -> None:
    """削ったオブジェクトの名前も文に残っていない。

    部屋ごと消せばその中の対象も消える。「送信機を直せ」と目的文が言い
    続けたのがこれ。**目的文は毎ターン全員のプロンプトに載る**ので、
    部屋の説明より影響が大きい。
    """
    child_raw, parent_raw = _load(child), _load(parent)
    removed = _object_names(parent_raw) - _object_names(child_raw)

    prose = "\n".join(_strings(child_raw))
    dangling = sorted(name for name in removed if name in prose)

    assert not dangling, f"{child} が、削ったはずの対象を指しています: {dangling}"


@pytest.mark.parametrize("child,parent", sorted(_DERIVED.items()))
def test_no_item_survives_without_its_purpose(child: str, parent: str) -> None:
    """使い道ごと削ったアイテムの宣言が残っていない。

    送信機を消したのに「送信機の真空管」の宣言と、それを拾う操作が残って
    いた。**使い道の無い部品を拾うだけ**の行動になり、持ち物欄に出るぶん
    判断を汚す。実際 1 人がこれを拾って run を終えた。
    """
    child_raw = _load(child)
    declared = {s["id"] for s in child_raw.get("item_specs", [])}
    if not declared:
        pytest.skip("item_specs が無い")

    rest = {k: v for k, v in child_raw.items() if k != "item_specs"}
    text = "\n".join(_strings(rest))
    initial = set()
    for player in child_raw.get("players", []):
        for item in player.get("initial_items", []):
            initial.add(item if isinstance(item, str) else item.get("item_spec"))

    unused = sorted(i for i in declared if i not in initial and i not in text)

    assert not unused, f"{child} に使い道の無いアイテムが残っています: {unused}"
