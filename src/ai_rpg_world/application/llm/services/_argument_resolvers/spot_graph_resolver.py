"""スポットグラフ系ツールの引数解決（ラベル → 内部 ID）。"""

import logging
import re
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
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

    同名スポットが複数ある場合は最初にマッチしたものを採用しつつ warning を残す。
    シナリオ規約として同名禁止が望ましいが、ここでは防御的に最初の 1 件で先へ進める。
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
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
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
})


def _inner_thought_value(args: Dict[str, Any]) -> str:
    raw = args.get("inner_thought", "")
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    return raw.strip()


def _with_inner_thought(base: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    out["inner_thought"] = _inner_thought_value(args)
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
        return None

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
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "攻撃対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "攻撃対象ラベル",
            (MonsterToolRuntimeTargetDto,),
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if target.monster_id is None:
            raise ToolArgumentResolutionException(
                f"このラベルは攻撃対象ではありません: {label}",
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
        label = args.get("destination_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "接続先ラベルが指定されていません。",
                "INVALID_DESTINATION_LABEL",
            )
        # 解決戦略: 入力からいくつかの候補形 (ラベル単体 / スポット名 / 連結文字列の
        # 部品) を取り出し、(1) targets 辞書ヒット → (2) display_name 一致 の順で
        # 探す。Issue #269 第17回 R2 で「S2: 禁書扉 → 館長書斎」のような連結文字列
        # を LLM が destination_label に貼って失敗する例が観測されたため、候補抽出
        # で吸収する。
        target: Optional[ToolRuntimeTargetDto] = None
        kind_mismatch = False
        candidates = _normalize_label_candidates(label)
        for c in candidates:
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
                    f"接続先ラベルとして使えないラベルです: {label}",
                    "INVALID_DESTINATION_KIND",
                )
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_DESTINATION_LABEL",
            )
        if target.spot_id is None:
            raise ToolArgumentResolutionException(
                f"移動先として解決できないラベルです: {label}",
                "INVALID_DESTINATION_KIND",
            )
        return _with_inner_thought({"destination_spot_id": target.spot_id}, args)

    def _resolve_set_sub_location(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("sub_location_label")
        if not label:
            return _with_inner_thought({"sub_location_id": None}, args)
        # destination と同じく、SL1 等のラベルだけでなくサブロケーション名 (文字列) も
        # 受け付ける。理由は _resolve_travel_to と同じく label leak 対策。
        if label in runtime_context.targets:
            target = require_target(
                label,
                runtime_context,
                "サブロケーションラベル",
                invalid_label_code="INVALID_TARGET_LABEL",
            )
        else:
            found = _find_target_by_display_name(
                runtime_context,
                kind="spot_graph_sub_location",
                display_name=label,
            )
            if found is None:
                raise ToolArgumentResolutionException(
                    f"指定された対象ラベルは現在の候補にありません: {label}",
                    "INVALID_TARGET_LABEL",
                )
            target = found
        if target.sub_location_id is None:
            raise ToolArgumentResolutionException(
                f"サブロケーションとして解決できないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {"sub_location_id": target.sub_location_id}, args
        )

    def _resolve_interact(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("object_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "オブジェクトラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target(
            label,
            runtime_context,
            "オブジェクトラベル",
            invalid_label_code="INVALID_TARGET_LABEL",
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"オブジェクトとして解決できないラベルです: {label}",
                "INVALID_TARGET_KIND",
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
