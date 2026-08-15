"""行動ログ (直近の出来事) の action_summary を表示用に整形する。

# 何のため

``_format_action_summary`` (full orchestrator) と ``runtime_manager`` は raw tool
args 全体を ``json.dumps`` して action_summary にしていた。結果として、発話本文・
メモ本文・心の声など、別の自然文位置に出る情報が JSON にも重複表示されていた。

本モジュールは tool 名ごとの表示関数で、行動を短い自然文にする。表に無い tool
名は従来の JSON 形式へフォールバックする。これは LLM が ``look_around`` などの
存在しない tool 名を返す実データがあるためで、表示の失敗で prompt 構築を落とさない。

# 注意 (canonical args ではない)

これは **表示用** の整形であり、``ActionResultEntry.action_summary`` に保存は
されるが、loop_guard の引数 fingerprint や tool 実行に使う canonical args とは
別物。fingerprint は ``build_argument_fingerprint`` が raw args から narrative を
strip して計算するので、本整形の有無に依存しない。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional

from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    ACTION_ARGUMENT_CLASSIFICATIONS,
    ActionArgumentDisplayKind,
)

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    TOOL_NAME_MEMORY_RECALL_EPISODES,
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

# action_summary の JSON fallback から落とす主観入力・冗長入力フィールド。
# - expected_result: chunk_encoding が [予測: ...] で別表記するので二重表示回避
# - inner_thought: ActionResultEntry.inner_thought から「心の声: ...」として出す
# - content: speak / memo_add では自然文または別 section に出るため JSON から落とす
# - reason / intention / emotion_hint: recent-events の生 JSON には不要
ACTION_SUMMARY_HIDDEN_FIELDS = frozenset(
    {
        "content",
        "reason",
        "inner_thought",
        "intention",
        "expected_result",
        "emotion_hint",
    }
)

ActionSummaryFormatter = Callable[[Mapping[str, Any]], str]

# resolver 後は公開 label が内部 ID に置き換わる。成功した core action の記録まで
# LLM が実際に送った引数の射影を運ぶためだけの内部キーで、tool schema には出さない。
ACTION_HISTORY_PROJECTION_KEY = "__action_history_projection"

def project_action_arguments_for_history(
    args: Optional[Mapping[str, Any]],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """raw tool 引数を、履歴に保存する識別引数と自由文引数名へ射影する。

    値を再利用できる引数だけを ``identifier_arguments`` に残す。配列・数値・
    boolean・null は JSON として正規化し、自由文は内容を重複保存せず名前だけを
    残す。分類表の順序で返すため、LLM が JSON property の順序を変えても履歴の
    並びは揺れない。
    """

    source = args or {}
    identifiers: dict[str, str] = {}
    free_text_names: list[str] = []
    for name, kind in ACTION_ARGUMENT_CLASSIFICATIONS.items():
        if name not in source:
            continue
        value = source[name]
        if kind == ActionArgumentDisplayKind.IDENTIFIER_STRING:
            identifiers[name] = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            )
        elif kind == ActionArgumentDisplayKind.IDENTIFIER_JSON:
            identifiers[name] = json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            )
        elif kind == ActionArgumentDisplayKind.FREE_TEXT:
            free_text_names.append(name)
    return identifiers, tuple(free_text_names)


def action_history_projection_kwargs(
    args: Mapping[str, Any],
) -> dict[str, object]:
    """runtime の記録入口へ渡す射影済み keyword arguments を返す。"""

    carried = args.get(ACTION_HISTORY_PROJECTION_KEY)
    if (
        isinstance(carried, tuple)
        and len(carried) == 2
        and isinstance(carried[0], dict)
        and isinstance(carried[1], tuple)
    ):
        identifiers, free_text_names = carried
    else:
        identifiers, free_text_names = project_action_arguments_for_history(args)
    return {
        "identifier_arguments": identifiers,
        "free_text_argument_names": free_text_names,
    }


def _text(args: Mapping[str, Any], key: str) -> str:
    raw = args.get(key)
    if raw is None:
        return ""
    return str(raw).strip()


def _quote(text: str) -> str:
    return f"「{text}」" if text else "対象"


def _format_speak(args: Mapping[str, Any]) -> str:
    content = _text(args, "content")
    channel = _text(args, "channel")
    if channel == "whisper":
        target = _text(args, "target_label")
        if target:
            return f"{_quote(target)}に囁いた: {_quote(content)}"
        return f"あなたは囁いた: {_quote(content)}"
    if channel == "shout":
        return f"あなたは叫んだ: {_quote(content)}"
    return f"あなたは言った: {_quote(content)}"


def _format_memo_add(args: Mapping[str, Any]) -> str:
    return "メモを書いた"


def _format_memo_done(args: Mapping[str, Any]) -> str:
    raw_ids = args.get("memo_ids")
    if isinstance(raw_ids, list):
        ids = [str(v).strip() for v in raw_ids if str(v).strip()]
    else:
        ids = []
    if not ids:
        return "メモを完了にした"
    joined = ", ".join(ids)
    return f"メモ {len(ids)} 件を完了にした ({joined})"


def _format_memo_list(args: Mapping[str, Any]) -> str:
    return "メモ一覧を確認した"


def _format_interact(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_label")
    action = _text(args, "action_name")
    if target and action:
        return f"{_quote(target)}に {action} した"
    if target:
        return f"{_quote(target)}に働きかけた"
    return "目の前の対象に働きかけた"


def _format_travel_to(args: Mapping[str, Any]) -> str:
    destination = _text(args, "destination_label") or _text(args, "destination_spot_id")
    return f"{destination}へ移動した" if destination else "移動した"


def _format_set_sub_location(args: Mapping[str, Any]) -> str:
    sub_location = _text(args, "sub_location_label") or _text(args, "sub_location_id")
    return f"{sub_location}へ位置を移した" if sub_location else "位置を移した"


def _format_use_item(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    return f"{_quote(item)}を使った"


def _format_drop_item(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    return f"{_quote(item)}を地面に置いた"


def _format_pickup_item(args: Mapping[str, Any]) -> str:
    item = _text(args, "ground_item_label")
    return f"{_quote(item)}を拾った"


def _format_give_item(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_player_label")
    item = _text(args, "item_label")
    if not item:
        gives = args.get("gives")
        if isinstance(gives, list) and gives:
            first = gives[0]
            if isinstance(first, Mapping):
                item = _text(first, "item_label")
                target = target or _text(first, "target_player_label")
    if target and item:
        return f"{_quote(target)}に{_quote(item)}を渡した"
    if target:
        return f"{_quote(target)}にアイテムを渡した"
    return "アイテムを渡した"


def _format_buy_item(args: Mapping[str, Any]) -> str:
    """買った品と個数を短い自然文にする。相手の商人名も残す。"""
    return _format_merchant_trade(args, verb="買った")


def _format_sell_item(args: Mapping[str, Any]) -> str:
    """売った品と個数を短い自然文にする。"""
    return _format_merchant_trade(args, verb="売った")


def _format_merchant_trade(args: Mapping[str, Any], *, verb: str) -> str:
    item = _text(args, "item_label")
    merchant = _text(args, "merchant_label")
    quantity = args.get("quantity")
    count = f"{quantity}つ" if isinstance(quantity, int) and not isinstance(quantity, bool) else ""
    if item and merchant:
        return f"{_quote(merchant)}に{_quote(item)}を{count}{verb}"
    if item:
        return f"{_quote(item)}を{count}{verb}"
    return f"商人と取引した"


def _format_trade_offer(args: Mapping[str, Any]) -> str:
    """誰に持ちかけたかを短い自然文にする。"""
    target = _text(args, "target_player_label")
    return f"{_quote(target)}に取引を持ちかけた" if target else "取引を持ちかけた"


def _format_trade_accept(args: Mapping[str, Any]) -> str:
    offerer = _text(args, "offerer_player_label")
    return f"{_quote(offerer)}の申し出を受けた" if offerer else "取引の申し出を受けた"


def _format_trade_decline(args: Mapping[str, Any]) -> str:
    offerer = _text(args, "offerer_player_label")
    return f"{_quote(offerer)}の申し出を断った" if offerer else "取引の申し出を断った"


def _format_market_list_item(args: Mapping[str, Any]) -> str:
    """何をいくらで板に出したかを短い自然文にする。"""
    item = _text(args, "item_label")
    price = args.get("unit_price")
    count = args.get("quantity")
    if item and price:
        return f"掲示板に{_quote(item)}を{count}つ、1つ{price}Gで出した"
    return "掲示板に品を出した"


def _format_market_buy(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    count = args.get("quantity")
    return f"掲示板から{_quote(item)}を{count}つ買った" if item else "掲示板から買った"


def _format_market_reprice(args: Mapping[str, Any]) -> str:
    """値をいくらに変えたかを残す。**値動きは後から追える形で書く。**"""
    item = _text(args, "item_label")
    price = args.get("new_unit_price")
    if item and price:
        return f"{_quote(item)}の値を1つ{price}Gに変えた"
    return "掲示板の値を変えた"


def _format_market_cancel(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    return f"{_quote(item)}の出品を取り下げた" if item else "掲示板の注文を取り下げた"


def _format_market_bid(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    price = args.get("unit_price")
    count = args.get("quantity")
    if item and price:
        return f"掲示板に{_quote(item)}を{count}つ、1つ{price}Gで買うと出した"
    return "掲示板に買い注文を出した"


def _format_market_sell(args: Mapping[str, Any]) -> str:
    item = _text(args, "item_label")
    count = args.get("quantity")
    return f"掲示板の買い注文へ{_quote(item)}を{count}つ売った" if item else "掲示板へ売った"


def _format_attack(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_label")
    return f"{_quote(target)}を攻撃した"


def _format_tend_to_player(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_player_label")
    return f"{_quote(target)}を介抱した"


def _format_listen(args: Mapping[str, Any]) -> str:
    return "耳を澄ました"


def _format_explore(args: Mapping[str, Any]) -> str:
    return "この場所を探索した"


def _format_wait(args: Mapping[str, Any]) -> str:
    return "その場で待機した"


def _format_prepare_action(args: Mapping[str, Any]) -> str:
    action_name = _text(args, "action_name")
    return f"{action_name} を準備した" if action_name else "協力行動を準備した"


def _format_vote(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_player_label")
    return f"{_quote(target)}へ投票した" if target else "投票した"


def _format_report_body(args: Mapping[str, Any]) -> str:
    target = _text(args, "target_player_label")
    return f"{_quote(target)}が倒れていると知らせた" if target else "倒れている人を知らせた"


ACTION_SUMMARY_FORMATTERS: dict[str, ActionSummaryFormatter] = {
    TOOL_NAME_MEMO_ADD: _format_memo_add,
    TOOL_NAME_MEMO_DONE: _format_memo_done,
    TOOL_NAME_MEMO_LIST: _format_memo_list,
    TOOL_NAME_SPEECH: _format_speak,
    TOOL_NAME_SPOT_GRAPH_ATTACK: _format_attack,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM: _format_buy_item,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM: _format_sell_item,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER: _format_trade_offer,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT: _format_trade_accept,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE: _format_trade_decline,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM: _format_market_list_item,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY: _format_market_buy,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE: _format_market_reprice,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL: _format_market_cancel,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID: _format_market_bid,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL: _format_market_sell,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM: _format_drop_item,
    TOOL_NAME_SPOT_GRAPH_EXPLORE: _format_explore,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM: _format_give_item,
    TOOL_NAME_SPOT_GRAPH_INTERACT: _format_interact,
    TOOL_NAME_SPOT_GRAPH_LISTEN: _format_listen,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM: _format_pickup_item,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION: _format_prepare_action,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY: _format_report_body,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: _format_set_sub_location,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER: _format_tend_to_player,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: _format_travel_to,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM: _format_use_item,
    TOOL_NAME_SPOT_GRAPH_VOTE: _format_vote,
    TOOL_NAME_SPOT_GRAPH_WAIT: _format_wait,
}

# 能動想起系は結果文が本体で、行動名と引数を短く自然文化しても情報量が増えない。
# JSON fallback を意図的に使うツールとして明示分類し、追加時の判断漏れをテストで
# 捕まえる。
INTENTIONAL_ACTION_SUMMARY_FALLBACK_TOOLS = frozenset(
    {
        TOOL_NAME_MEMORY_EXPLORE_RELATED,
        TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
        TOOL_NAME_MEMORY_RECALL_EPISODES,
        TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    }
)


def format_action_summary_for_display(
    tool_name: str, args: Optional[Mapping[str, Any]] = None
) -> str:
    """tool 名 + args から「直近の出来事」用の行動要約文を作る。"""
    formatter = ACTION_SUMMARY_FORMATTERS.get(tool_name)
    if formatter is not None:
        return formatter(args or {})
    return _format_action_summary_fallback(tool_name, args)


def _format_action_summary_fallback(
    tool_name: str, args: Optional[Mapping[str, Any]] = None
) -> str:
    """表に無い tool 名を従来の JSON 形式で安全に表示する。"""
    if not args:
        return f"{tool_name} を実行しました。"
    visible = {k: v for k, v in args.items() if k not in ACTION_SUMMARY_HIDDEN_FIELDS}
    if not visible:
        return f"{tool_name} を実行しました。"
    try:
        args_str = json.dumps(visible, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(visible)
    return f"{tool_name}({args_str}) を実行しました。"


__all__ = [
    "ACTION_SUMMARY_FORMATTERS",
    "ACTION_SUMMARY_HIDDEN_FIELDS",
    "INTENTIONAL_ACTION_SUMMARY_FALLBACK_TOOLS",
    "format_action_summary_for_display",
]
