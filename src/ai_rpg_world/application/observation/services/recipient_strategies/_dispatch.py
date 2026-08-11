"""配信先解決を「イベント型 → 配信規則」の表で書くための共通部品。

## なぜ表にするか

観測の配信先は 2 段構えになっている。

1. ``ObservedEventRegistry`` が「このイベントはどの strategy が担当するか」を持つ
2. その strategy が「誰に届けるか」を決める

2 を ``isinstance`` の連鎖で書くと、1 に登録したのに分岐を書き忘れたときに
``supports()`` は True・``resolve()`` は空リスト・例外なし・テスト緑になり、
**そのイベントは誰にも観測されない**。エラーではないので実 run の分析でも
「たまたま誰も居なかった」と区別がつかない。

イベント型は 124 個あり、これから MMO 的な要素 (取引・売買・依頼など) を
組み込むほど増える。増やすたびに人間が突き合わせる形では続かないので、
表にして機械に突き合わせさせる。

## 使い方

1. モジュールに ``_RECIPIENT_RULES: Dict[type, RecipientRule]`` を置く
2. 誰にも配らない型があれば ``_DELIVERS_TO_NOBODY: Dict[type, str]`` に
   **理由つきで**書く (空タプルや暗黙の fall-through にしない)
3. ``__init__`` の最後で ``verify_rules_cover_registry(...)`` を呼ぶ
4. ``handled_event_types()`` を生やし、テストがレジストリと突き合わせる

## なぜ構築時に落とすのか

run 中に落とすのでは遅い理由が 2 つある。

1. LLM ツール経路は ``_execute_tool`` を広い ``except Exception`` で囲んで
   おり、通った例外は ``LLM_TOOL_EXECUTION_FAILED`` という汎用のツール失敗に
   化ける。配線漏れがエージェントの操作ミスと同じ見え方になり、run 分析から
   消える
2. ``_process_graph_events`` は ``clear_events()`` を先に呼んでから
   ``publish_all()`` するので、バッチ途中で例外が出ると残りのイベントが
   復元不能なまま失われる

壊れた状態で始めない、という snapshot 読み込みと同じ判断
(docs/design_decisions.md #15-#18)。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

__all__ = [
    "Add",
    "RecipientRule",
    "RecipientRuleWiringError",
    "verify_rules_cover_registry",
]

#: 配信規則が recipient を足すために呼ぶ関数。重複の扱いは呼ばれた側に任せる。
Add = Callable[[PlayerId], None]

#: 配信規則の形。第 1 引数は strategy 自身 (未束縛メソッドを表に置くため)。
RecipientRule = Callable[[Any, Any, Add], None]


class RecipientRuleWiringError(RuntimeError):
    """レジストリの割り当てと配信規則の表が食い違っている。

    **run が始まる前に落とすための例外。** 理由はモジュール docstring を参照。
    """


def verify_rules_cover_registry(
    *,
    registry: Any,
    strategy_key: str,
    rules: Mapping[type, Any],
    delivers_to_nobody: Mapping[type, str] | None = None,
) -> None:
    """担当と登録された全イベント型が、規則か「配らない」宣言に載っているか確かめる。

    どちらにも無い型は「登録したのに配信先が決まらない」= 観測が誰にも届かない
    状態なので、``RecipientRuleWiringError`` で落とす。

    ``delivers_to_nobody`` は「意図的に誰にも配らない」型と理由の対応。規則の
    表に空関数を置くのではなく別表にするのは、**書き忘れと「本当に配らない」を
    区別できるようにする**ため (空関数だとどちらも同じ見た目になる)。
    """
    nobody: Mapping[type, str] = delivers_to_nobody or {}
    registered: Iterable[type] = registry.get_event_types_for_strategy(strategy_key)

    missing = sorted(
        event_type.__name__
        for event_type in registered
        if event_type not in rules and event_type not in nobody
    )
    if missing:
        raise RecipientRuleWiringError(
            f"{strategy_key} 担当と登録されているのに配信先が決まらない"
            "イベント型があります。observation が誰にも届きません。"
            "_RECIPIENT_RULES に規則を足すか、意図的に配らないなら理由つきで "
            "_DELIVERS_TO_NOBODY へ登録してください: " + ", ".join(missing)
        )

    both = sorted(
        event_type.__name__ for event_type in rules if event_type in nobody
    )
    if both:
        raise RecipientRuleWiringError(
            f"{strategy_key} で、配信規則と「配らない」宣言の両方に載っている"
            "イベント型があります。どちらが意図か読めません: " + ", ".join(both)
        )


def blank_reasons(delivers_to_nobody: Mapping[type, str]) -> list[str]:
    """「配らない」理由が空文字列の型名を返す。

    理由を書く欄があっても空で登録できるなら「登録すれば無検査で通る」抜け道が
    残る。中身の妥当さはレビューが見るしかないが、空であることは機械で落とせる。
    """
    return sorted(
        event_type.__name__
        for event_type, reason in delivers_to_nobody.items()
        if not reason.strip()
    )


#: 型注釈のための別名。``Dict[type, RecipientRule]`` を各 strategy で書くより短い。
RuleTable = Dict[type, RecipientRule]
