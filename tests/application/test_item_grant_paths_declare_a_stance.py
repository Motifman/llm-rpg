"""品を所持品へ入れる経路は、満杯のときどうするかを宣言してから足す。

`PlayerInventoryAggregate.acquire_item` は所持品が満杯だと**黙って品を捨てる**
(溢れイベントを出して return する)。そのイベントを publish する経路はどこにも
無いので、結果メッセージにも観測にも trace にも残らない。実 run
(`var/runs/m7_v3coop_001`) では、ノアが「乾いた流木を一本拾い上げた」で 36 回
成功しながら手放したのは 6 回で、20 枠に収まっていない。本人は「流木はもう
十八本ある」と信じたまま拾い続けていた。

**穴が空いていること自体より、足した人が気づけないことが問題**である。
`pickup_item` / `give_item` / `buy_item` / 市場 / 同席取引は、それぞれ別の PR で
個別に塞がれてきた。次に品を渡す経路を足す人は、この歴史を知らない。

そこで、品を入れる経路を持つモジュールを表に載せ、**満杯のときどうするかを
必ず宣言させる**。新しい経路を足すと表に無い名前が出てこのテストが落ちるので、
足した人はそこで選択を迫られる。表そのものが、いま何が塞がっていて何が
空いているかの一覧にもなる。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

_SRC = Path(__file__).resolve().parents[2] / "src" / "ai_rpg_world"

#: 品を所持品へ入れる呼び出し。名前で拾う。
_GRANT_CALLS = {
    "acquire_item",
    "grant_item_specs_to_inventory",
    "grant_initial_items_to_inventory",
}

#: 満杯のときの構え。新しい経路はこのどれかを選ぶ。
_REFUSE = "満杯なら事前に断る (何も動かさない)"
_DROP = "満杯なら足元に落として観測を届ける"
_NOT_REACHABLE = "現行経路から到達しない (旧実装)"
_NO_GUARD_YET = "未対処 — 満杯だと黙って消える"
_INFRASTRUCTURE = "付与の実装そのもの (構えは呼び出し側が決める)"

#: 検出は「呼んでいる」モジュールだけを拾う。`acquire_item` を**定義している**
#: 集約 (`player_inventory_aggregate.py`) は呼び出し側ではないので出てこない。

#: モジュール (src/ai_rpg_world からの相対パス) → 満杯のときの構え。
#:
#: `_NO_GUARD_YET` はいま 1 件も無い。**枠は残す** — 次に穴を見つけた人が
#: 記録する場所が要る。表を空にして消すと、見つけた人が書く場所を失う。
_STANCE: Dict[str, str] = {
    # ── 塞がっている ──────────────────────────────────────────────
    "application/world_graph/spot_graph_item_transfer_service.py": _REFUSE,
    "application/world_graph/spot_graph_merchant_trade_service.py": _REFUSE,
    "application/trade/services/market_service.py": _REFUSE,
    "application/trade/services/player_trade_service.py": _REFUSE,
    # ── 効果として与える経路: 足元へ落とす ────────────────────────
    "application/world_graph/spot_interaction_application_service.py": _DROP,
    "application/world_graph/spot_exploration_application_service.py": _DROP,
    "application/world_graph/spot_graph_scenario_event_stage_service.py": _DROP,
    "application/world_graph/player_interaction_application_service.py": _DROP,
    "application/world/handlers/item_taken_from_chest_handler.py": _NOT_REACHABLE,
    "application/world/handlers/monster_death_reward_handler.py": _NOT_REACHABLE,
    "application/world/services/place_object_service.py": _NOT_REACHABLE,
    "application/quest/services/quest_progress_reaction_service.py": _NOT_REACHABLE,
    "domain/world/service/harvest_domain_service.py": _NOT_REACHABLE,
    # 起動時の初期所持品は、枠を超えたら**読み込みの時点で落とす**。作者の
    # 誤りであって世界の出来事ではないので、地面に落とす形にはしない。
    "application/world_runtime/world_runtime.py": _REFUSE,
    # ── 現行経路から到達しない (旧実装) ──────────────────────────
    "application/shop/services/shop_command_service.py": _NOT_REACHABLE,
    "application/trade/services/trade_command_service.py": _NOT_REACHABLE,
    "application/conversation/services/conversation_command_service.py": _NOT_REACHABLE,
    # ── 付与の実装そのもの ────────────────────────────────────────
    "application/world_graph/spot_inventory_helpers.py": _INFRASTRUCTURE,
}


def _modules_that_grant_items() -> Set[str]:
    """品を所持品へ入れる呼び出しを持つモジュールを集める。

    import せず AST で読む。import すると副作用で経路が増減しうるため。
    """
    found: Set[str] = set()
    for path in _SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 構文エラーは別のテストの仕事
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            if name in _GRANT_CALLS:
                found.add(str(path.relative_to(_SRC)))
                break
    return found


class TestEveryGrantPathDeclaresWhatItDoesWhenFull:
    """品を入れる経路は、満杯のときの構えを宣言している。"""

    def test_no_grant_path_is_missing_from_the_table(self) -> None:
        """表に載っていない付与経路が無い。

        新しく品を渡す経路を足すと、ここで落ちる。落ちた人は「満杯のとき
        どうするか」を選んで表に書くことになる。**選ばせることが目的**で、
        表に載せること自体は目的ではない。
        """
        missing = sorted(_modules_that_grant_items() - set(_STANCE))

        assert not missing, (
            "品を所持品へ入れる経路が増えていますが、満杯のときの構えが"
            "宣言されていません。acquire_item は満杯だと黙って品を捨てるので、"
            "確かめずに渡すと『成功したのに増えていない』が誰にも見えない形で"
            f"起きます: {missing}"
        )

    def test_the_table_has_no_stale_entries(self) -> None:
        """表に、もう付与していないモジュールが残っていない。

        歯止めが「昔あった経路の一覧」に劣化するのを防ぐ。
        """
        stale = sorted(set(_STANCE) - _modules_that_grant_items())

        assert not stale, (
            f"付与しなくなったモジュールが表に残っています。消してください: {stale}"
        )

    def test_every_stance_is_one_of_the_known_ones(self) -> None:
        """宣言された構えが、決めてある選択肢のどれかになっている。"""
        known = {_REFUSE, _DROP, _NOT_REACHABLE, _NO_GUARD_YET, _INFRASTRUCTURE}
        unknown = {m: s for m, s in _STANCE.items() if s not in known}

        assert not unknown, f"知らない構えが書かれています: {unknown}"


class TestTheToolFacingPathsStillDeclareThatTheyRefuse:
    """ツールが直接品を受け取る経路の**宣言**が、事前拒否のままになっている。

    エージェントが自分の手番で「受け取る」と決めた行動は、失敗するなら
    **その場で理由が返る**べきである。黙って消えると、決定と結果が食い違った
    まま記憶へ流れる。

    **これは宣言の検査であって、挙動の検査ではない。** 宣言が `_REFUSE` の
    ままガードだけ外れても、ここは緑になる (実際に変異で確かめた)。挙動の側は
    経路ごとに別のテストが見ている:

    - `pickup_item` / `give_item`: `tests/demos/` の受け渡し系
    - `buy_item`: 商人との売買 (経済統合 Phase 1)
    - 市場の約定: `tests/application/trade/services/test_market_service.py`
    - 同席取引: `tests/demos/test_a_trade_never_makes_goods_vanish.py`

    ここが守るのは「4 経路のどれかを未対処へ**格下げ**したら気づく」ことで、
    ガードの実在ではない。
    """

    #: エージェントの 1 手が直接品を受け取る経路。
    _TOOL_FACING = (
        "application/world_graph/spot_graph_item_transfer_service.py",
        "application/world_graph/spot_graph_merchant_trade_service.py",
        "application/trade/services/market_service.py",
        "application/trade/services/player_trade_service.py",
    )

    def test_none_of_them_is_downgraded_to_unguarded(self) -> None:
        """ツールが受け取る 4 経路の宣言が、どれも事前拒否のままになっている。"""
        downgraded = [m for m in self._TOOL_FACING if _STANCE.get(m) != _REFUSE]

        assert not downgraded, (
            f"ツールが受け取る経路の構えが事前拒否から変わっています: {downgraded}"
        )
