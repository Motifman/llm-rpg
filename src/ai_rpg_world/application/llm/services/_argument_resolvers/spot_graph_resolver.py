"""スポットグラフ系ツールの引数解決（ラベル → 内部 ID）。"""

import logging
import re
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target,
    require_target_type,
)

logger = logging.getLogger(__name__)


# Issue #269 第17回 R2 で観測された LLM の destination_label 崩れパターン:
# - "S2: 禁書扉 → 館長書斎" — prompt 行をそのまま貼る
# - "S2 (館長書斎)" — 括弧つきラベル
# - "解読室" — スポット名直書き (display_name 経路で吸収)
# - "S1" — 既存ラベル経路
# 共通解として、入力文字列から以下の候補を抽出して順に解決を試す:
# 1. 入力そのまま
# 2. 先頭の S\d+ / SL\d+ / P\d+ / OBJ\d+ / I\d+ / M\d+ ラベル
# 3. 括弧内 (..) または （..） の中身
# 4. " → " で区切られた右端 (末尾の括弧つき注釈を除いた行先名)
# 5. ":" / "：" 区切りで右側 (label プレフィックス除去後の本体)
_LEADING_LABEL_RE = re.compile(r"^(S\d+|SL\d+|OBJ\d+|P\d+|I\d+|M\d+)\b")
_PAREN_RE = re.compile(r"[(（]([^()（）]+)[)）]")
_TRAILING_PAREN_RE = re.compile(r"\s*[(（][^()（）]*[)）]\s*$")


def _normalize_label_candidates(label: str) -> List[str]:
    """LLM が destination_label / target_label に入れがちな崩れ表現から
    解決可能な候補形を生成する。同じ候補は除去しつつ出現順を保つ。

    例:
    - "S2: 禁書扉 → 館長書斎" → ["S2: ...", "S2", "禁書扉", "館長書斎"]
    - "S2 (館長書斎)" → ["S2 (館長書斎)", "S2", "館長書斎"]
    - "解読室" → ["解読室"]
    """
    s = label.strip()
    if not s:
        return []
    out: List[str] = [s]

    # PR Y_after_pr_all_200tick 後続: prompt 表記が ``"拠点"`` のように
    # ``""`` で囲んだ値を「渡すべき値」と明示する規約になったため、
    # LLM が quote ごと渡してきても resolver が中身を取り出せるようにする。
    # 対称な ``"..."`` または ``'...'`` のみを剥がす (片側だけは触らない)。
    if len(s) >= 2 and (
        (s[0] == '"' and s[-1] == '"')
        or (s[0] == "'" and s[-1] == "'")
    ):
        inner = s[1:-1].strip()
        if inner:
            out.append(inner)

    m = _LEADING_LABEL_RE.match(s)
    if m:
        out.append(m.group(1))

    m2 = _PAREN_RE.search(s)
    if m2:
        out.append(m2.group(1).strip())

    if "→" in s:
        right = s.split("→")[-1].strip()
        right = _TRAILING_PAREN_RE.sub("", right).strip()
        if right:
            out.append(right)

    if ":" in s or "：" in s:
        parts = re.split(r"[:：]", s, maxsplit=1)
        if len(parts) == 2:
            after = parts[1].strip()
            after = _TRAILING_PAREN_RE.sub("", after).strip()
            if after and after != s:
                out.append(after)
                if "→" in after:
                    left = after.split("→")[0].strip()
                    if left:
                        out.append(left)

    # dedup keep order, drop empty
    seen: set[str] = set()
    deduped: List[str] = []
    for c in out:
        c = c.strip()
        if not c or c in seen:
            continue
        seen.add(c)
        deduped.append(c)
    return deduped


def resolve_destination_target(
    label: str,
    runtime_context: ToolRuntimeContextDto,
) -> "DestinationToolRuntimeTargetDto":
    """destination_label を ``DestinationToolRuntimeTargetDto`` に解決する。

    Issue #276: world_runtime の ``_handle_travel_to`` と本家
    ``_resolve_travel_to`` で同じ解決ロジックを 2 ヶ所に書いていたのを
    こちらに集約した。world_runtime 経路は本関数で target を得てから
    ``runtime.do_move`` を直接呼ぶ。本家経路は本関数の結果から
    ``destination_spot_id`` を抽出して canonical 引数に変換する。

    解決順:
    1. ``_normalize_label_candidates(label)`` で崩れ表現 (連結文字列 / 括弧
       つき / 矢印つき) から候補形を抽出
    2. 各候補について ``runtime_context.targets`` 直接 lookup →
       display_name 一致の順で ``DestinationToolRuntimeTargetDto`` を探す
    3. どれにも該当しなければ ``INVALID_DESTINATION_LABEL``、kind 違いだけが
       見つかれば ``INVALID_DESTINATION_KIND``、spot_id が None なら
       ``INVALID_DESTINATION_KIND``
    """
    if not isinstance(label, str) or not label:
        raise ToolArgumentResolutionException(
            "接続先名が指定されていません。",
            "INVALID_DESTINATION_LABEL",
        )
    target: Optional[ToolRuntimeTargetDto] = None
    kind_mismatch = False
    for c in _normalize_label_candidates(label):
        if c in runtime_context.targets:
            hit = runtime_context.targets[c]
            if isinstance(hit, DestinationToolRuntimeTargetDto):
                target = hit
                break
            kind_mismatch = True
            continue
        found = _find_target_by_display_name(
            runtime_context,
            kind="spot_graph_destination",
            display_name=c,
        )
        if found is not None and isinstance(found, DestinationToolRuntimeTargetDto):
            target = found
            break
    if target is None:
        if kind_mismatch:
            raise ToolArgumentResolutionException(
                f"接続先名として使えない値です: {label}",
                "INVALID_DESTINATION_KIND",
            )
        raise ToolArgumentResolutionException(
            f"指定された接続先名は現在の候補にありません: {label}",
            "INVALID_DESTINATION_LABEL",
        )
    if target.spot_id is None:
        raise ToolArgumentResolutionException(
            f"移動先として解決できない名前です: {label}",
            "INVALID_DESTINATION_KIND",
        )
    return target  # type: ignore[return-value]


def _resolve_target_with_display_name_fallback(
    label: str,
    runtime_context: ToolRuntimeContextDto,
    *,
    kind: str,
    expected_types: tuple = (),
    label_name: str,
    invalid_label_code: str = "INVALID_TARGET_LABEL",
    invalid_kind_code: str = "INVALID_TARGET_KIND",
) -> ToolRuntimeTargetDto:
    """PR #441: label を「内部 label key (旧形式)」「LLM が渡す display_name」
    「崩れ表現 (連結 / 括弧つき) 」のいずれでも解決する共通 helper。

    PR #421 / #425 の「名前直書き」refactor 後、LLM は display_name を引数として
    渡すようになった。``resolve_destination_target`` / ``resolve_sub_location_target``
    は同等の fallback 経路を既に持っていたが、**object / use_item / drop_item /
    pickup_item / attack / give_item の 6 resolver は require_target 直叩きのまま
    で fallback 経路を持たず、display_name lookup が完全に効かない silent failure を
    抱えていた** (実験 #438 で 252 件 INVALID_TARGET_LABEL = 全 action の 92.3%
    失敗として顕在化、PR #440 で確認)。

    解決順:
    1. ``_normalize_label_candidates(label)`` で崩れ表現を分解
    2. 各候補について ``runtime_context.targets`` の直接 lookup
    3. miss なら ``_find_target_by_display_name(kind=kind)`` で display_name 一致を探す
    4. expected_types が指定されていれば、見つかった target の型一致もチェック

    Args:
        label: LLM が渡した文字列
        kind: display_name fallback で絞る ``ToolRuntimeTargetDto.kind`` 値
            (例: ``"spot_graph_object"`` / ``"inventory_item"`` / ``"ground_item"``
            / ``"spot_graph_monster"``)
        expected_types: 見つかった target の許容型 tuple。空 tuple なら型 check 無し
        label_name: エラーメッセージに含める日本語名 (例: ``"オブジェクト名"``)

    Raises:
        ToolArgumentResolutionException: 解決できないとき
    """
    if not isinstance(label, str) or not label.strip():
        raise ToolArgumentResolutionException(
            f"{label_name}が指定されていません。",
            invalid_label_code,
        )
    target: Optional[ToolRuntimeTargetDto] = None
    kind_mismatch = False
    for c in _normalize_label_candidates(label):
        if c in runtime_context.targets:
            hit = runtime_context.targets[c]
            if not expected_types or isinstance(hit, expected_types):
                target = hit
                break
            kind_mismatch = True
            continue
        found = _find_target_by_display_name(
            runtime_context,
            kind=kind,
            display_name=c,
        )
        if found is not None:
            if not expected_types or isinstance(found, expected_types):
                target = found
                break
            kind_mismatch = True
    if target is None:
        if kind_mismatch:
            raise ToolArgumentResolutionException(
                f"{label_name}として使えない値です: {label}",
                invalid_kind_code,
            )
        raise ToolArgumentResolutionException(
            f"指定された{label_name}は現在の候補にありません: {label}",
            invalid_label_code,
        )
    return target


def resolve_object_target(
    label: str,
    runtime_context: ToolRuntimeContextDto,
) -> ToolRuntimeTargetDto:
    """interact 用の object_label を target に解決する。

    Issue #276 経路二重化解消: world_runtime の ``_handle_interact`` と本家
    ``_resolve_interact`` の object_label → world_object_id 解決を共通化。

    PR #441: PR #421 / #425 の「名前直書き」refactor に追従し、display_name
    fallback を追加 (実験 #438 で全 interact が INVALID_TARGET_LABEL で失敗
    した silent failure の root fix)。
    """
    target = _resolve_target_with_display_name_fallback(
        label,
        runtime_context,
        kind="spot_graph_object",
        label_name="オブジェクト名",
    )
    if target.world_object_id is None:
        raise ToolArgumentResolutionException(
            f"オブジェクトとして解決できない名前です: {label}",
            "INVALID_TARGET_KIND",
        )
    return target


def resolve_sub_location_target(
    label: Optional[str],
    runtime_context: ToolRuntimeContextDto,
) -> Optional[ToolRuntimeTargetDto]:
    """set_sub_location 用のラベル解決。label が空なら None を返す
    (sub_location クリア指示)。

    PR-EE/FF/X (Y_after_pr639_640 後続): prompt 表示で
    ``- "祭壇前"（現在ここ）`` のように quote されるようになったため、
    LLM が quote ごと渡してきても解決できる必要がある。他 4 resolver
    (object/player/attack/tend) と同じく ``_normalize_label_candidates``
    経由で崩れ表現を分解する。
    """
    if not label:
        return None
    target: Optional[ToolRuntimeTargetDto] = None
    for c in _normalize_label_candidates(label):
        if c in runtime_context.targets:
            hit = runtime_context.targets[c]
            target = hit
            break
        found = _find_target_by_display_name(
            runtime_context,
            kind="spot_graph_sub_location",
            display_name=c,
        )
        if found is not None:
            target = found
            break
    if target is None:
        raise ToolArgumentResolutionException(
            f"指定されたサブロケーション名は現在の候補にありません: {label}",
            "INVALID_TARGET_LABEL",
        )
    if target.sub_location_id is None:
        raise ToolArgumentResolutionException(
            f"サブロケーションとして解決できない名前です: {label}",
            "INVALID_TARGET_KIND",
        )
    return target


def resolve_player_target(
    label: str,
    runtime_context: ToolRuntimeContextDto,
) -> Optional[ToolRuntimeTargetDto]:
    """whisper target_label を spot_graph_player target に解決する。

    Issue #269 + #276: 「P1」のラベル / 「リン」の display_name / 「P1 (リン)」
    の連結形のいずれでも引ける。見つからなければ None (空文字も None)。

    world_runtime の ``_handle_speech`` whisper 経路で使う。本家側からは現状
    呼ばれていないが、後続で whisper resolver を統合する際の seed。
    """
    if not label:
        return None
    direct = runtime_context.targets.get(label)
    if direct is not None and direct.player_id is not None:
        return direct
    for c in _normalize_label_candidates(label):
        hit = runtime_context.targets.get(c)
        if hit is not None and hit.player_id is not None:
            return hit
        for t in runtime_context.targets.values():
            if getattr(t, "kind", None) != "spot_graph_player":
                continue
            if t.display_name == c and t.player_id is not None:
                return t
    return None


def _find_target_by_display_name(
    runtime_context: ToolRuntimeContextDto,
    *,
    kind: str,
    display_name: str,
) -> Optional[ToolRuntimeTargetDto]:
    """`runtime_context.targets` を全スキャンし、同 kind かつ display_name 一致の最初の target を返す。

    LLM が会話履歴に残った `S1` などのスポット相対ラベルを次 turn でも再利用すると、
    自スポット移動後にラベルの指す先が反転して bouncing が起きる。これを避けるため、
    スポット名 (display_name) そのものを引数として受け付け、不変な意味で解決できるようにする。

    PR 6 (#404 後続) で名前+ordinal 設計に倒した後の挙動:
        - prompt 側で同名衝突時は ``灰色のオオカミ #1`` / ``灰色のオオカミ #2``
          のように disambiguate された display_name が target に格納される
        - LLM はこの disambiguated 名をそのまま引数として渡す想定
        - したがって本関数で複数マッチが起きるのは、シナリオ JSON で人為的に
          同一の display_name (disambiguated 後でも) を作ってしまった病的
          ケースのみ。warning は引き続き残しておく
    """
    matches: list[ToolRuntimeTargetDto] = []
    for target in runtime_context.targets.values():
        if target.kind == kind and target.display_name == display_name:
            matches.append(target)
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning(
            "Multiple runtime targets share the same display_name; "
            "using the first match. kind=%s display_name=%s labels=%s",
            kind,
            display_name,
            [t.label for t in matches],
        )
    return matches[0]
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

_SPOT_GRAPH_TOOLS = frozenset({
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    # PR-α (Y_after_pr639_640 後続): 旧 GIVE_ITEMS は削除、GIVE_ITEM が
    # batch-always で吸収した。
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
})


def _inner_thought_value(args: Dict[str, Any]) -> str:
    raw = args.get("inner_thought", "")
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    return raw.strip()


def _with_inner_thought(base: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """resolver が返す canonical args に、raw args の「保持すべき passthrough
    キー」を merge する。

    PR-θ1 (経路統合) 修正: 旧 _with_inner_thought は ``inner_thought`` だけを
    transparent に通していたが、``say_inline`` (立ち去り際の一言) が resolver
    通過後の args から抜け落ちて執行 executor に届かず 100% silent failure して
    いた (t=18 の P1 travel_to say_inline が誰にも届かない = 前実験で observation
    ゼロ)。

    ``give_item`` 経路だけ動いていたのは ``_resolve_give_item`` が明示的に
    ``"say_inline": args.get(...)`` を追加していたため。全 resolver で
    重複記述するのは書き漏れリスクが大きいので、共通 helper で自動 passthrough
    に格上げする。base 側で明示指定されていれば上書きしない (give_item 経路と
    互換)。

    Note: subjective fields (expected_result / intention / emotion_hint) は
    現状 tool catalog schema に露出していないので raw args にも含まれない。
    露出 ON になっても executor 側で ``extract_subjective_action_fields(args)``
    が raw args から読む契約なので、resolver 通過後の args にも透過する必要が
    ある。今回同時に passthrough する。
    """
    out = dict(base)
    out["inner_thought"] = _inner_thought_value(args)
    for passthrough_key in (
        "say_inline",
        "expected_result",
        "intention",
        "emotion_hint",
    ):
        if passthrough_key in args and passthrough_key not in out:
            out[passthrough_key] = args[passthrough_key]
    return out


class SpotGraphArgumentResolver:
    """spot_graph_* ツールのラベル引数を canonical 引数に解決する。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name not in _SPOT_GRAPH_TOOLS:
            return None
        if tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO:
            return self._resolve_travel_to(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION:
            return self._resolve_set_sub_location(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_EXPLORE:
            return _with_inner_thought({}, args)
        if tool_name == TOOL_NAME_SPOT_GRAPH_WAIT:
            return _with_inner_thought(
                {"reason": str(args.get("reason", "")).strip()}, args
            )
        if tool_name == TOOL_NAME_SPOT_GRAPH_LISTEN:
            return _with_inner_thought({}, args)
        if tool_name == TOOL_NAME_SPOT_GRAPH_INTERACT:
            return self._resolve_interact(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_ATTACK:
            return self._resolve_attack(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_DROP_ITEM:
            return self._resolve_drop_item(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM:
            return self._resolve_pickup_item(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_GIVE_ITEM:
            return self._resolve_give_item(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER:
            return self._resolve_tend_to_player(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_USE_ITEM:
            return self._resolve_use_item(args, runtime_context)
        return None

    def _resolve_use_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """所持アイテムラベル (I1 等) を item_spec_id に解決する。

        実験 #25 で発覚 (#356 trace): tool catalog は ``item_label`` を要求し、
        executor は ``item_spec_id`` を読むのに、resolver 側に dispatch が無く
        全 106 件の use_item が ``INVALID_ARGUMENT`` で落ちていた。

        Note: ``ToolRuntimeTargetDto.item_instance_id`` は legacy 慣習で
        item_spec_id を入れている (DTO 定義のコメント参照)。本 resolver は
        その慣習に合わせて item_spec_id として exec 側に渡す。
        """
        label = args.get("item_label")
        # PR #441: display_name fallback で「真水 (食料)」等の prompt 表記も受理
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="inventory_item",
            expected_types=(InventoryToolRuntimeTargetDto,),
            label_name="使用するアイテム名",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if target.kind != "inventory_item":
            raise ToolArgumentResolutionException(
                f"この名前は所持アイテムではありません: {label}",
                "INVALID_TARGET_KIND",
            )
        if target.item_instance_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定されたアイテム名は使用対象として扱えません: {label}。"
                    "所持アイテム欄の \"\" 内の名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "item_spec_id": target.item_instance_id,
                "item_display_name": target.display_name,
            },
            args,
        )

    def _resolve_single_give_entry(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """1 件の give entry (item_label + target_player_label) を解決する
        内部 helper。``_resolve_give_item`` (batch-always) が gives 配列の
        各 entry に対して呼び出す。

        - item_label (I1 等): drop と同じく InventoryToolRuntimeTargetDto (kind="inventory_item")
        - target_player_label (P1 等 / 名前): resolve_player_target で player_id を取り出す
        """
        item_label = args.get("item_label")
        # PR #441: display_name fallback
        item_target = _resolve_target_with_display_name_fallback(
            item_label,
            runtime_context,
            kind="inventory_item",
            expected_types=(InventoryToolRuntimeTargetDto,),
            label_name="渡すアイテム名",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if item_target.kind != "inventory_item":
            raise ToolArgumentResolutionException(
                f"この名前は所持アイテムではありません: {item_label}",
                "INVALID_TARGET_KIND",
            )
        if item_target.inventory_slot_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定されたアイテム名は渡す対象として扱えません: {item_label}。"
                    "所持アイテム欄の \"\" 内の名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )

        target_player_label = args.get("target_player_label")
        if not isinstance(target_player_label, str) or not target_player_label.strip():
            raise ToolArgumentResolutionException(
                "渡す相手の名前が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        player_target = resolve_player_target(target_player_label, runtime_context)
        if player_target is None or player_target.player_id is None:
            raise ToolArgumentResolutionException(
                f"指定された相手の名前が現在の候補にありません: {target_player_label}",
                "INVALID_TARGET_LABEL",
            )

        return _with_inner_thought(
            {
                "slot_id": item_target.inventory_slot_id,
                "target_player_id": player_target.player_id,
                "target_display_name": player_target.display_name,
                "item_display_name": item_target.display_name,
            },
            args,
        )

    def _resolve_give_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """``give_item`` (batch-always) の gives 配列を各 entry ごとに解決する。

        PR-α (Y_after_pr639_640 後続): 旧 give_item (単発) と give_items (batch)
        を統合。``give_item`` は常に ``gives: [...]`` を受け取り、単発でも配列で
        表現される (len=1)。

        Partial success 方針: resolve 段階で 1 件失敗しても他は通す。失敗 entry
        は ``{"error_code": "...", "message": "..."}`` で埋めて executor 側に
        渡し、executor で「OK / NG」を集約 message に変換する。これにより
        LLM は「リン宛は失敗、トマ宛は OK」のような **部分的成功** を 1 turn で
        観測できる。

        ``inner_thought`` / ``say_inline`` 等の外側引数はそのまま保持する。
        """
        gives = args.get("gives")
        if not isinstance(gives, list) or not gives:
            raise ToolArgumentResolutionException(
                "gives は非空の配列で指定してください。1 件だけ渡す場合も"
                "配列で包む必要があります (例: gives=[{item_label: ..., "
                "target_player_label: ...}])。",
                "INVALID_ARGUMENT",
            )

        resolved: list[Dict[str, Any]] = []
        for i, entry in enumerate(gives):
            if not isinstance(entry, dict):
                resolved.append({
                    "index": i,
                    "error_code": "INVALID_ARGUMENT",
                    "message": f"gives[{i}] は object でなければなりません。",
                })
                continue
            try:
                resolved_entry = self._resolve_single_give_entry(
                    {
                        "item_label": entry.get("item_label"),
                        "target_player_label": entry.get("target_player_label"),
                        "inner_thought": "",
                    },
                    runtime_context,
                )
                resolved.append({
                    "index": i,
                    "slot_id": resolved_entry["slot_id"],
                    "target_player_id": resolved_entry["target_player_id"],
                    "target_display_name": resolved_entry["target_display_name"],
                    "item_display_name": resolved_entry["item_display_name"],
                    "item_label": entry.get("item_label"),
                    "target_player_label": entry.get("target_player_label"),
                })
            except ToolArgumentResolutionException as e:
                resolved.append({
                    "index": i,
                    "error_code": e.error_code,
                    "message": str(e),
                    "item_label": entry.get("item_label"),
                    "target_player_label": entry.get("target_player_label"),
                })

        return _with_inner_thought(
            {
                "gives_resolved": resolved,
                "say_inline": args.get("say_inline", ""),
            },
            args,
        )

    def _resolve_drop_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """所持アイテムラベル (I1 等) を slot_id / item_instance_id に解決する。

        勘違いポイント: ラベルは「同じ種類の集約表示」なので、解決後の
        内部 ID は代表 1 件を指す。LLM 視点で気になるのはアイテムの種類なので
        問題にならないが、コード側では一意の所持品を狙って drop することになる。
        """
        label = args.get("item_label")
        # PR #441: display_name fallback
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="inventory_item",
            expected_types=(InventoryToolRuntimeTargetDto,),
            label_name="落とすアイテム名",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        # その場に落ちているアイテム (kind="ground_item") は drop の対象にならない
        if target.kind != "inventory_item":
            raise ToolArgumentResolutionException(
                f"この名前は所持アイテムではありません: {label}",
                "INVALID_TARGET_KIND",
            )
        if target.inventory_slot_id is None or target.real_item_instance_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定されたアイテム名は手放す対象として扱えません: {label}。"
                    "所持アイテム欄の \"\" 内の名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "slot_id": target.inventory_slot_id,
                "item_instance_id": target.real_item_instance_id,
                "target_display_name": target.display_name,
                # Phase C: stealth フラグを bool として executor に渡す
                # (executor 側で WitnessPolicy に変換する)。LLM が省略したら
                # bool() で False に丸める (= デフォルト SAME_SPOT)。
                "stealth": bool(args.get("stealth", False)),
            },
            args,
        )

    def _resolve_pickup_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """その場に落ちているアイテムの名前を item_instance_id に解決する。"""
        label = args.get("ground_item_label")
        # PR #441: display_name fallback
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="ground_item",
            expected_types=(InventoryToolRuntimeTargetDto,),
            label_name="拾うものの名前",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if target.kind != "ground_item":
            raise ToolArgumentResolutionException(
                f"この名前は今いる場所に落ちているものではありません: {label}",
                "INVALID_TARGET_KIND",
            )
        if target.real_item_instance_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定された名前は拾う対象として扱えません: {label}。"
                    "地面に落ちているもの欄の \"\" 内の名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "item_instance_id": target.real_item_instance_id,
                "target_display_name": target.display_name,
                "stealth": bool(args.get("stealth", False)),
            },
            args,
        )

    def _resolve_tend_to_player(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """`spot_graph_tend_to_player` の target_player_label を player_id に解決する。

        Issue #621 Phase 3b: 同 spot に倒れた仲間を介抱して revive する。
        runtime_context.targets に PlayerToolRuntimeTargetDto として登録されて
        いる相手の display_name / 短縮ラベル (P1, P2, ...) で指定可能。
        monster (kind=spot_graph_monster) や inventory を渡すと
        INVALID_TARGET_KIND で弾く。
        """
        label = args.get("target_player_label")
        if not isinstance(label, str) or not label.strip():
            raise ToolArgumentResolutionException(
                "蘇生する相手の名前が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        try:
            target = _resolve_target_with_display_name_fallback(
                label,
                runtime_context,
                kind="spot_graph_player",
                expected_types=(PlayerToolRuntimeTargetDto,),
                label_name="蘇生対象の名前",
                invalid_label_code="INVALID_TARGET_LABEL",
                invalid_kind_code="INVALID_TARGET_KIND",
            )
        except ToolArgumentResolutionException as e:
            # Y_after_pr639_640_200tick 後続: 「候補にない」だけの message は
            # LLM を混乱させる (別 spot にいるプレイヤー / 倒れていない
            # プレイヤーの区別がつかない)。tend の同 spot + ダウン 制約を
            # message で明示する。error_code は既存を保持して LLM 側の
            # 学習パス (remediation mapping) を壊さない。
            if e.error_code == "INVALID_TARGET_LABEL":
                raise ToolArgumentResolutionException(
                    (
                        f"{label} は現在の場所で介抱できる候補にいません。"
                        "同じ場所で倒れているプレイヤーの名前を指定してください。"
                        "相手が別の場所にいる場合は先に移動し、相手が倒れていない"
                        "場合は話しかけるなど別の行動を選んでください。"
                    ),
                    "INVALID_TARGET_LABEL",
                )
            raise
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定された名前は介抱する相手として扱えません: {label}。"
                    "同じ場所で倒れているプレイヤーの名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "target_player_id": target.player_id,
                "target_display_name": target.display_name,
            },
            args,
        )

    def _resolve_attack(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """`spot_graph_attack` の target_label をモンスター ID に解決する。

        ラベルが MonsterToolRuntimeTargetDto に解決できない場合、または
        monster_id が None の場合は `INVALID_TARGET_LABEL` で弾く。
        """
        label = args.get("target_label")
        # PR #441: display_name fallback
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="spot_graph_monster",
            expected_types=(MonsterToolRuntimeTargetDto,),
            label_name="攻撃対象名",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if target.monster_id is None:
            raise ToolArgumentResolutionException(
                f"この名前は攻撃対象ではありません: {label}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "monster_id": target.monster_id,
                "target_display_name": target.display_name,
            },
            args,
        )

    def _resolve_travel_to(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        target = resolve_destination_target(
            args.get("destination_label"),  # type: ignore[arg-type]
            runtime_context,
        )
        return _with_inner_thought({"destination_spot_id": target.spot_id}, args)

    def _resolve_set_sub_location(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        target = resolve_sub_location_target(
            args.get("sub_location_label"), runtime_context
        )
        sub_location_id = target.sub_location_id if target is not None else None
        return _with_inner_thought({"sub_location_id": sub_location_id}, args)

    def _resolve_interact(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        target = resolve_object_target(
            args.get("object_label"),  # type: ignore[arg-type]
            runtime_context,
        )
        action = args.get("action_name", "")
        if not isinstance(action, str) or not action.strip():
            raise ToolArgumentResolutionException(
                "action_name が指定されていません。",
                "INVALID_ARGUMENT",
            )
        return _with_inner_thought(
            {"object_id": target.world_object_id, "action_name": action.strip()},
            args,
        )
