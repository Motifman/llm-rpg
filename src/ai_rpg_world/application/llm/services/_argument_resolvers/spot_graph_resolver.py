"""スポットグラフ系ツールの引数解決（ラベル → 内部 ID）。"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional

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
_NO_ACTION_PLACEHOLDER_RE = re.compile(
    r"^(?:[.…]+\s*)?[（(]\s*なし\s*[）)]$"
)


#: resolver が「解決に実際に使った正規の識別値」を報告する内部キー。
#: 履歴 (直近の出来事) に生の崩れた入力ではなくこちらを残すために使う。
#: tool schema には出さない (LLM から見えない)。
CANONICAL_IDENTIFIERS_KEY = "__canonical_identifiers"


def record_canonical_identifier(
    args: Dict[str, Any], name: str, value: Optional[str]
) -> None:
    """解決に使った正規値を、履歴へ運ぶために raw args へ書き添える。

    resolver は崩れた表記を救って成功させる。履歴に生値を残すと「その
    書き方で通った」と見えて崩れが定着するので、**次に真似しても通る形**
    をここで記録する。値が生値と同じなら何も足さない (無駄な差分を作らない)。
    """
    if not isinstance(value, str) or not value:
        return
    raw = args.get(name)
    if isinstance(raw, str) and raw == value:
        return
    bucket = args.get(CANONICAL_IDENTIFIERS_KEY)
    if not isinstance(bucket, dict):
        bucket = {}
        args[CANONICAL_IDENTIFIERS_KEY] = bucket
    bucket[name] = value


def _pick_action_name(action: str, target: "ToolRuntimeTargetDto") -> str:
    """表示の写し崩れを、対象が実際に持つ操作名へ寄せる。

    候補が対象の ``available_interactions`` に無ければ**生値をそのまま返す**。
    表示に無い名前の発明 (65 run で 111 件の主因) はここで救わず、従来どおり
    「その操作はありません + 利用可能な操作一覧」で失敗させる。
    """
    stripped = action.strip()
    available = getattr(target, "available_interactions", ()) or ()
    if not available:
        return stripped
    for candidate in normalize_action_name_candidates(stripped):
        if candidate in available:
            return candidate
    return stripped


def normalize_action_name_candidates(action: str) -> List[str]:
    """LLM が action_name に入れがちな崩れ表現から候補形を生成する。

    ラベル側 (`_normalize_label_candidates`) と同じ規約を操作名にも適用する。
    ツール定義は action_name について「``""`` で囲まれた値をそのまま渡す」と
    書き、target_label については「quote ごとどちらでも解釈する」と約束して
    いた。**約束が片側にしか実装されていなかった**ので、表示どおりに
    ``"offer_wheat"`` と渡した側が落ちていた (供物競争 run t73)。

    救うのは表示の写し崩れだけで、**表示に無い名前の発明は救わない**
    (候補を作っても対象の操作一覧に無ければ従来どおり失敗する)。
    """
    s = action.strip()
    if not s:
        return []
    out: List[str] = [s]

    # 対称な quote を剥がす: ``"offer_wheat"`` → ``offer_wheat``
    if len(s) >= 2 and (
        (s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")
    ):
        inner = s[1:-1].strip()
        if inner:
            out.append(inner)

    # 表示行の丸ごとコピー: ``麦を刈る → "reap_wheat"`` → ``reap_wheat``
    if "→" in s:
        tail = s.rsplit("→", 1)[1].strip()
        if tail:
            out.append(tail)
            if len(tail) >= 2 and (
                (tail[0] == '"' and tail[-1] == '"')
                or (tail[0] == "'" and tail[-1] == "'")
            ):
                inner = tail[1:-1].strip()
                if inner:
                    out.append(inner)

    seen: set = set()
    unique: List[str] = []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


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


def _candidate_display_names(
    runtime_context: ToolRuntimeContextDto,
    predicate: Callable[[ToolRuntimeTargetDto], bool],
) -> List[str]:
    """runtime target から LLM が次に指定できる表示名だけを順序保持で集める。

    失敗文は次の一手を修正するために LLM が読む。内部ラベル (S1 / OBJ1 等)
    ではなく prompt に露出している display_name だけを返し、同名は重複させない。
    """
    names: List[str] = []
    seen: set[str] = set()
    for target in runtime_context.targets.values():
        if not predicate(target):
            continue
        name = target.display_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _format_valid_candidates(candidate_label: str, candidates: List[str]) -> str:
    """有効候補一覧を失敗文に埋め込む短い日本語へ整形する。"""
    if not candidates:
        return f"有効な{candidate_label}: ありません"
    return f"有効な{candidate_label}: {' / '.join(candidates)}"


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
        candidates = _candidate_display_names(
            runtime_context,
            lambda target: isinstance(target, DestinationToolRuntimeTargetDto),
        )
        raise ToolArgumentResolutionException(
            (
                f"指定された接続先名は現在の候補にありません: {label} → "
                f"{_format_valid_candidates('接続先', candidates)}"
            ),
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
    # NOTE: 本ヘルパを ``resolve_target`` の上に載せ替えようとして失敗した経緯を
    # 残す。``kind`` と ``expected_types`` の **不一致が意図的に使われている**
    # 呼び出し元がある (pickup_item は ``kind="ground_item"`` +
    # ``expected_types=(InventoryToolRuntimeTargetDto,)`` で「所持アイテムとして
    # 解決させてから ground_item でないことを自前の文面で弾く」)。
    # ``resolve_target`` は直接 lookup も ``accept_kinds`` で絞るので、載せ替えると
    # この経路が汎用文面に落ち、「今いる場所に落ちているものではありません」という
    # 具体的な案内が消える。統合は呼び出し元の意味論を整理してから行う。
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
        candidates = _candidate_display_names(
            runtime_context,
            lambda target: target.kind == kind,
        )
        raise ToolArgumentResolutionException(
            (
                f"指定された{label_name}は現在の候補にありません: {label} → "
                f"{_format_valid_candidates(label_name, candidates)}"
            ),
            invalid_label_code,
        )
    return target


def resolve_target(
    label: str,
    runtime_context: ToolRuntimeContextDto,
    *,
    accept_kinds: tuple,
    label_name: str,
    invalid_label_code: str = "INVALID_TARGET_LABEL",
    invalid_kind_code: str = "INVALID_TARGET_KIND",
) -> ToolRuntimeTargetDto:
    """名前から対象を引く唯一の入口。複数の種別を同じ規約で受け付ける。

    対人インタラクションでは 1 つの引数に object と player の両方が入るため、
    種別ごとに分かれていた解決を 1 本にまとめる。

    それ以前の問題として、**同じ仕事なのに失敗の返し方が食い違っていた**。
    ``resolve_object_target`` は例外を投げるのに ``resolve_player_target`` は
    ``None`` を返しており、後者は呼び出し側が None を握り潰せば静かな失敗に
    なる。本関数は **常に例外で失敗を返す**。

    失敗は 2 種類に分ける。原因が違えば LLM が次に取る手も違うため。

    - ``INVALID_TARGET_LABEL``: その名前が候補に無い → 名前を直す
      (**受け付ける全種別の候補一覧を文面に含める**)
    - ``INVALID_TARGET_KIND``: 内部ラベル (``O1`` 等) で直接引けたが種別が違う
      → 別の対象を選ぶ

    表示名が別種別のものと一致した場合は ``INVALID_TARGET_KIND`` にせず
    ``INVALID_TARGET_LABEL`` にする。KIND の文面には候補一覧が付かないため、
    「その名前は別の種類だ」と正確に言う代わりに「では何が書けるのか」を
    失うことになり、LLM が次の一手を選べなくなるため。

    候補一覧は ``accept_kinds`` の**全種別**から集める。object だけ / player
    だけを挙げると「他に何を書けばよいか」が分からず同じ失敗を繰り返す。

    Args:
        accept_kinds: 受け付ける ``ToolRuntimeTargetDto.kind`` の tuple
        label_name: エラーメッセージに含める日本語名 (例: ``"対象の名前"``)

    Raises:
        ToolArgumentResolutionException: 解決できないとき
    """
    if not isinstance(label, str) or not label.strip():
        raise ToolArgumentResolutionException(
            f"{label_name}が指定されていません。",
            invalid_label_code,
        )

    kind_mismatch = False
    for candidate in _normalize_label_candidates(label):
        hit = runtime_context.targets.get(candidate)
        if hit is not None:
            if hit.kind in accept_kinds:
                return hit
            kind_mismatch = True
            continue
        # 表示名の探索は種別を順に見るので、素朴に最初の一致を返すと
        # 「物体『リン』とプレイヤー『リン』が同席している」ときに先に見た
        # 種別が常に勝つ。刺したつもりが物体を調べていた、のような成功として
        # 返る誤動作になるので、種別を跨いだ一致は全部集めてから判断する。
        # (`build_ordinal_disambiguator` はセクションごとに別々の名前リストへ
        #  適用されるため、種別横断の衝突には `#N` が付かない。)
        found_across_kinds = [
            f
            for f in (
                _find_target_by_display_name(
                    runtime_context, kind=kind, display_name=candidate
                )
                for kind in accept_kinds
            )
            if f is not None
        ]
        if len(found_across_kinds) > 1:
            raise ToolArgumentResolutionException(
                (
                    f"{label_name}「{candidate}」は複数の対象と一致します。"
                    "短縮ラベル ("
                    + "、".join(f.label for f in found_across_kinds)
                    + ") のいずれかで指定し直してください。"
                ),
                "AMBIGUOUS_TARGET_LABEL",
            )
        if found_across_kinds:
            return found_across_kinds[0]

    if kind_mismatch:
        raise ToolArgumentResolutionException(
            f"{label_name}として使えない値です: {label}",
            invalid_kind_code,
        )
    candidates = _candidate_display_names(
        runtime_context,
        lambda target: target.kind in accept_kinds,
    )
    raise ToolArgumentResolutionException(
        (
            f"指定された{label_name}は現在の候補にありません: {label} → "
            f"{_format_valid_candidates(label_name, candidates)}"
        ),
        invalid_label_code,
    )


def resolve_object_target(
    label: str,
    runtime_context: ToolRuntimeContextDto,
) -> ToolRuntimeTargetDto:
    """interact 用の target_label を target に解決する。

    Issue #276 経路二重化解消: world_runtime の ``_handle_interact`` と本家
    ``_resolve_interact`` の target_label → world_object_id 解決を共通化。

    PR #441: PR #421 / #425 の「名前直書き」refactor に追従し、display_name
    fallback を追加 (実験 #438 で全 interact が INVALID_TARGET_LABEL で失敗
    した silent failure の root fix)。
    """
    # NOTE: ここだけ ``expected_types`` を渡していないのは意図的で、書き忘れでは
    # ない。object は他の target と違い専用の DTO サブクラスを持たず、基底の
    # ``ToolRuntimeTargetDto`` のまま登録される。したがって isinstance では
    # 絞れないので、代わりに ``world_object_id`` フィールドの有無で「object と
    # して扱えるか」を判定している。統一時にここへ ``expected_types`` を足そうと
    # しても、渡すべきクラスが存在しない。
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
        candidates = _candidate_display_names(
            runtime_context,
            lambda target: target.kind == "spot_graph_sub_location",
        )
        raise ToolArgumentResolutionException(
            (
                f"指定されたサブロケーション名は現在の候補にありません: {label} → "
                f"{_format_valid_candidates('サブロケーション', candidates)}"
            ),
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
) -> ToolRuntimeTargetDto:
    """target_label を spot_graph_player target に解決する。

    「P1」のラベル / 「リン」の display_name / 「P1 (リン)」の連結形のいずれでも
    引ける (Issue #269 + #276)。

    かつては同等のループを手書きし、**見つからなければ `None` を返して**いた。
    兄弟の ``resolve_object_target`` は例外を投げるので、同じ「名前から対象を
    引く」仕事なのに失敗の返し方が食い違っており、呼び出し側が None を握り
    潰せば静かな失敗になる状態だった。``resolve_target`` に寄せて **例外で
    失敗を返す** ようにした。

    None が欲しい呼び出し元 (whisper のように独自の失敗文面を組み立てたい側)
    は、例外を捕まえて自分で変換する。「暗黙に None」ではなく「明示的に
    変換している」ことがコード上で見えるようにするため。

    Raises:
        ToolArgumentResolutionException: 解決できないとき
    """
    return resolve_target(
        label,
        runtime_context,
        accept_kinds=("spot_graph_player",),
        label_name="相手の名前",
    )


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
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_VOTE,
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
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    # 経済統合 Phase 3: 市場の掲示板。品名はここで検証だけして名前のまま通す
    # (世界の宣言との突き合わせは service)。数量・単価はここで整数にする。
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    # PR-α (Y_after_pr639_640 後続): 旧 GIVE_ITEMS は削除、GIVE_ITEM が
    # batch-always で吸収した。
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    # 会議と投票 (#869 / #874)。**分岐だけ書いて、この許可リストに足すのを
    # 忘れていた。** resolve_args は入口でここを見るので分岐に到達せず None を
    # 返し、presentation 経路では RESOLVER_DISPATCH_MISSING になる。どの run
    # でも誰も投票しなかったため、一度も発火せず 4 本走らせても気付けなかった。
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
})


def _inner_thought_value(args: Dict[str, Any]) -> str:
    raw = args.get("inner_thought", "")
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    return raw.strip()


def _give_quantity_or_raise(raw: Any) -> int:
    """渡す個数を読む。省略は 1。

    `bool` は `int` の派生なので素直に書くと `True` が 1 として通る。
    「パンを True 個渡す」を作らせない。
    """
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ToolArgumentResolutionException(
            "gives[].quantity は 1 以上の整数で指定してください "
            f"(受け取った値: {raw!r})。",
            "INVALID_ARGUMENT",
        )
    return raw


def _with_inner_thought(base: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """resolver が返す canonical args に、raw args の「保持すべき passthrough
    キー」を merge する。

    PR-θ1 (経路統合) 修正: 旧 _with_inner_thought は ``inner_thought`` だけを
    transparent に通していたが、``say_inline`` (行動しながらの一言) が resolver
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
    canonical = args.get(CANONICAL_IDENTIFIERS_KEY)
    if isinstance(canonical, dict) and canonical:
        out[CANONICAL_IDENTIFIERS_KEY] = dict(canonical)
    for passthrough_key in (
        "say_inline",
        "expected_result",
        "intention",
        "emotion_hint",
        # interact の自由入力 (看板の本文 / パズルの暗証番号)。
        #
        # **say_inline とまったく同じ取りこぼしが再発していた。** 実 run で
        # キーパーが text を渡して当番表に書こうとし、4 回とも「text
        # パラメータで指定してください」で拒否された。渡しているのに
        # 「渡していない」と言われるので、モデルは同じ手を繰り返す。
        "parameters",
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
        if tool_name == TOOL_NAME_SPOT_GRAPH_BUY_ITEM:
            return self._resolve_merchant_trade(args, runtime_context, selling=False)
        if tool_name == TOOL_NAME_SPOT_GRAPH_SELL_ITEM:
            return self._resolve_merchant_trade(args, runtime_context, selling=True)
        if tool_name == TOOL_NAME_SPOT_GRAPH_TRADE_OFFER:
            return self._resolve_trade_offer(args, runtime_context)
        if tool_name in (
            TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
            TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
        ):
            return self._resolve_trade_answer(args, runtime_context)
        if tool_name in (
            TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
            TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
            TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
            TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
            TOOL_NAME_SPOT_GRAPH_MARKET_BID,
            TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
        ):
            return self._resolve_market(tool_name, args)
        if tool_name == TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER:
            return self._resolve_tend_to_player(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_VOTE:
            return self._resolve_vote(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_REPORT_BODY:
            return self._resolve_report_body(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_USE_ITEM:
            return self._resolve_use_item(args, runtime_context)
        return None

    def _resolve_market(
        self, tool_name: str, args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """市場ツールの引数を整える。

        **品名は名前のまま通す。** 板に出ている品は自分の所持品とは限らず
        (誰かの出品を買う)、逆に出品するときは所持品にある。どちらの表示から
        来ても同じ名前で指せるようにするため、世界の宣言との突き合わせは
        service に任せる (`MARKET_UNKNOWN_ITEM` で返る)。

        数量・単価はここで整数にする。文字列のまま executor へ届くと、
        比較や掛け算が黙って文字列結合になる。
        """
        resolved = dict(args)
        label = args.get("item_label")
        if not isinstance(label, str) or not label.strip():
            raise ToolArgumentResolutionException(
                "品の名前が指定されていません。掲示板や所持品に出ている名前を"
                "そのまま指定してください。",
                "INVALID_ITEM_LABEL",
            )
        resolved["item_label"] = label.strip()
        for key in ("quantity", "unit_price", "new_unit_price"):
            if key not in args:
                continue
            value = args.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ToolArgumentResolutionException(
                    f"{key} は整数で指定してください。", "INVALID_NUMBER",
                )
            try:
                number = int(value)
            except (TypeError, ValueError) as exc:
                raise ToolArgumentResolutionException(
                    f"{key} は整数で指定してください。", "INVALID_NUMBER",
                ) from exc
            if number < 1:
                raise ToolArgumentResolutionException(
                    f"{key} は 1 以上で指定してください。", "INVALID_NUMBER",
                )
            resolved[key] = number
        # 向きは PR 2 では売り注文だけ。既定を置くのは、書かれていないときに
        # executor で None 判定を散らさないため。
        if tool_name in (
            TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
            TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
        ):
            side = args.get("side") or "sell"
            if side not in ("sell", "buy"):
                raise ToolArgumentResolutionException(
                    "side は sell か buy で指定してください。", "INVALID_SIDE",
                )
            resolved["side"] = side
        return resolved

    def _resolve_trade_offer(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """``trade_offer`` の相手と、差し出す品を解決する。

        **gives と asks で解決先が違う。**

        - gives は自分の所持品なので、所持アイテム表示の名前から引く
          (give_item と同じ)
        - asks は**相手の持ち物で、自分の prompt には出ていない**。表示から
          選ばせる流儀が使えないので、ここでは名前のまま通し、世界の宣言
          (item_spec) との突き合わせは executor が行う

        asks を「相手の所持品を prompt に出して選ばせる」形にしなかったのは、
        他人の持ち物が全部見えると情報の非対称性 (この世界の核) が壊れるため。
        持っていない品を求める提案は作れるが、それは相手が断ることで解決する。
        """
        target_label = args.get("target_player_label")
        if not isinstance(target_label, str) or not target_label.strip():
            raise ToolArgumentResolutionException(
                "持ちかける相手の名前が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = resolve_player_target(target_label, runtime_context)
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                f"この名前は取引の相手として扱えません: {target_label}",
                "INVALID_TARGET_KIND",
            )

        gives = self._resolve_offered_side(args.get("gives"), runtime_context)
        asks = self._read_requested_side(args.get("asks"))
        if not gives["items"] and not gives["gold"]:
            raise ToolArgumentResolutionException(
                "差し出すものが空です。品か gold のどちらかを書いてください。",
                "INVALID_ARGUMENT",
            )
        if not asks["item_labels"] and not asks["gold"]:
            raise ToolArgumentResolutionException(
                "求めるものが空です。品か gold のどちらかを書いてください。",
                "INVALID_ARGUMENT",
            )
        if gives["gold"] and asks["gold"]:
            raise ToolArgumentResolutionException(
                "gold は片側にだけ置けます (金だけの両替はできません)。",
                "INVALID_ARGUMENT",
            )

        return _with_inner_thought(
            {
                "target_player_id": target.player_id,
                "target_display_name": target.display_name,
                "gives_items": gives["items"],
                "gives_gold": gives["gold"],
                "asks_item_labels": asks["item_labels"],
                "asks_gold": asks["gold"],
            },
            args,
        )

    def _resolve_offered_side(
        self,
        raw: Any,
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """自分が差し出す側を、所持アイテム表示から解決する。"""
        side = self._read_side_shape(raw, "gives")
        items = []
        for entry in side["entries"]:
            label = entry["item_label"]
            target = _resolve_target_with_display_name_fallback(
                label,
                runtime_context,
                kind="inventory_item",
                expected_types=(InventoryToolRuntimeTargetDto,),
                label_name="差し出す品の名前",
                invalid_label_code="INVALID_TARGET_LABEL",
                invalid_kind_code="INVALID_TARGET_KIND",
            )
            if target.kind != "inventory_item" or target.item_instance_id is None:
                raise ToolArgumentResolutionException(
                    f"この名前は差し出す品として扱えません: {label}",
                    "INVALID_TARGET_KIND",
                )
            items.append(
                {
                    "item_spec_id": target.item_instance_id,
                    "item_display_name": target.display_name,
                    "quantity": entry["quantity"],
                }
            )
        return {"items": items, "gold": side["gold"]}

    def _read_requested_side(self, raw: Any) -> Dict[str, Any]:
        """相手に求める側は、名前のまま通す (突き合わせは executor)。"""
        side = self._read_side_shape(raw, "asks")
        return {
            "item_labels": [
                {"item_label": entry["item_label"], "quantity": entry["quantity"]}
                for entry in side["entries"]
            ],
            "gold": side["gold"],
        }

    @staticmethod
    def _read_side_shape(raw: Any, field: str) -> Dict[str, Any]:
        """片側の形 (items と gold) を検証して読む。"""
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ToolArgumentResolutionException(
                f"{field} はオブジェクトで指定してください。",
                "INVALID_ARGUMENT",
            )
        raw_items = raw.get("items", []) or []
        if not isinstance(raw_items, list):
            raise ToolArgumentResolutionException(
                f"{field}.items は配列で指定してください。",
                "INVALID_ARGUMENT",
            )
        entries = []
        for entry in raw_items:
            if not isinstance(entry, dict):
                raise ToolArgumentResolutionException(
                    f"{field}.items の要素はオブジェクトで指定してください。",
                    "INVALID_ARGUMENT",
                )
            label = entry.get("item_label")
            if not isinstance(label, str) or not label.strip():
                raise ToolArgumentResolutionException(
                    f"{field}.items の item_label が空です。",
                    "INVALID_TARGET_LABEL",
                )
            quantity = entry.get("quantity", 1)
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise ToolArgumentResolutionException(
                    f"{field}.items の quantity は整数で指定してください "
                    f"(指定値: {quantity!r})。",
                    "INVALID_ARGUMENT",
                )
            if quantity < 1 or quantity > 99:
                raise ToolArgumentResolutionException(
                    f"{field}.items の quantity は 1 以上 99 以下で指定してください "
                    f"(指定値: {quantity})。",
                    "INVALID_ARGUMENT",
                )
            entries.append({"item_label": label.strip(), "quantity": quantity})
        gold = raw.get("gold", 0) or 0
        if isinstance(gold, bool) or not isinstance(gold, int):
            raise ToolArgumentResolutionException(
                f"{field}.gold は整数で指定してください (指定値: {gold!r})。",
                "INVALID_ARGUMENT",
            )
        if gold < 0:
            raise ToolArgumentResolutionException(
                f"{field}.gold は 0 以上で指定してください (指定値: {gold})。",
                "INVALID_ARGUMENT",
            )
        return {"entries": entries, "gold": gold}

    def _resolve_trade_answer(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """``trade_accept`` / ``trade_decline`` の相手を解決する。

        省略できる (自分宛ての申し出が 1 件なら) ので、指定が無ければ
        そのまま通し、どの提案かの決定は executor が行う。
        """
        label = args.get("offerer_player_label")
        if label is None or (isinstance(label, str) and not label.strip()):
            return _with_inner_thought({"offerer_player_id": None}, args)
        if not isinstance(label, str):
            raise ToolArgumentResolutionException(
                "申し出た相手の名前は文字列で指定してください。",
                "INVALID_TARGET_LABEL",
            )
        target = resolve_player_target(label, runtime_context)
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                f"この名前は申し出た相手として扱えません: {label}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "offerer_player_id": target.player_id,
                "offerer_display_name": target.display_name,
            },
            args,
        )

    def _resolve_merchant_trade(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
        *,
        selling: bool,
    ) -> Dict[str, Any]:
        """``buy_item`` / ``sell_item`` の品名と数量を解決する。

        商人は引数で指さない。**その品を扱う商人が同席していれば、それが
        取引相手**という形にして、1 人しか居ない普通の場合に引数を増やさない。
        複数の商人が同じ品を扱うときだけ ``merchant_label`` で絞る。

        **曖昧なときに engine が最安 / 最高を勝手に選ばない。** どの商人と
        取引するかは価格差のある世界では意思決定そのもので、engine が選ぶと
        「安い方を選んだ」という判断がエージェントの経験から消える。
        """
        item_label = args.get("item_label")
        if not isinstance(item_label, str) or not item_label.strip():
            raise ToolArgumentResolutionException(
                "取引する品の名前が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        quantity = self._resolve_trade_quantity(args.get("quantity"))
        wanted = _normalize_label_candidates(item_label)

        merchant_label = args.get("merchant_label")
        # targets は {label: target} の dict。**キーを回すと文字列が来る。**
        merchants = [
            target
            for target in (runtime_context.targets or {}).values()
            if getattr(target, "kind", "") == "merchant"
        ]
        # **同席する商人が 0 人なのは「場所を間違えた」で、品名の誤りとは
        # 別の失敗にする。** 文面が同じでも error_code は状況ごとに正直で
        # ないと、trace で未発火理由を集計したときに「移動の問題」と
        # 「商人節の読み違い」が 1 つのコードに混ざる。
        if not merchants:
            raise ToolArgumentResolutionException(
                self._no_merchant_message(item_label, [], selling=selling),
                "MERCHANT_NOT_AT_SPOT",
            )
        if isinstance(merchant_label, str) and merchant_label.strip():
            narrowed = [
                target
                for target in merchants
                if target.display_name in _normalize_label_candidates(merchant_label)
            ]
            if not narrowed:
                raise ToolArgumentResolutionException(
                    f"その名前の商人はこの場所に居ません: {merchant_label}",
                    "MERCHANT_NOT_AT_SPOT",
                )
            merchants = narrowed

        matches = []
        for target in merchants:
            offers = target.buys if selling else target.sells
            for offer in offers:
                if offer.item_name in wanted:
                    matches.append((target, offer))
        if not matches:
            raise ToolArgumentResolutionException(
                self._no_merchant_message(item_label, merchants, selling=selling),
                "SELL_ITEM_NOT_BOUGHT_HERE" if selling else "BUY_ITEM_NOT_SOLD_HERE",
            )
        if len(matches) > 1:
            # 価格まで添える。候補を並べるだけだと、もう 1 手かけて
            # 「商人:」節を読み直すことになる。
            listed = "、".join(
                f"{target.display_name}が{offer.price}G"
                for target, offer in matches
            )
            verb = "買い取る" if selling else "売っている"
            raise ToolArgumentResolutionException(
                f"{item_label}を{verb}商人が複数居ます ({listed})。"
                "merchant_label で相手を指定してください。",
                "MERCHANT_AMBIGUOUS",
            )

        target, offer = matches[0]
        return _with_inner_thought(
            {
                "merchant_id": target.merchant_id,
                "merchant_display_name": target.display_name,
                "item_spec_id": offer.item_spec_id,
                "item_display_name": offer.item_name,
                "unit_price": offer.price,
                "quantity": quantity,
            },
            args,
        )

    @staticmethod
    def _resolve_trade_quantity(raw: Any) -> int:
        """売買の個数を検証する。

        上限を置くのは、``quantity: 100000`` が「所持金が足りない」として
        返ると、**数量の誤りが金の話にすり替わる**ため。数量の問題は数量の
        失敗として返す。
        """
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ToolArgumentResolutionException(
                f"個数は 1 以上 99 以下の整数で指定してください (指定値: {raw!r})。",
                "INVALID_ARGUMENT",
            )
        if raw < 1 or raw > 99:
            raise ToolArgumentResolutionException(
                f"個数は 1 以上 99 以下で指定してください (指定値: {raw})。",
                "INVALID_ARGUMENT",
            )
        return raw

    @staticmethod
    def _no_merchant_message(
        item_label: str, merchants: List[Any], *, selling: bool,
    ) -> str:
        """その品を扱う商人が居ないときの文面。扱う品を添えて次の手を残す。"""
        if not merchants:
            return "この場所に商人は居ません。商人の居る場所へ移動してください。"
        parts = []
        for target in merchants:
            offers = target.buys if selling else target.sells
            listed = "、".join(f"{o.item_name} {o.price}G" for o in offers) or "なし"
            parts.append(f"{target.display_name}: {listed}")
        verb = "買い取っている" if selling else "売っている"
        return (
            f"{item_label}を{verb}商人がこの場所に居ません。"
            + " / ".join(parts)
        )

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
                "is_spoiled": target.is_spoiled,
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

        - item_label (I1 等): use_item と同じく item_spec_id に解決する。
          slot は executor が実行時に引き直す。
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
        if item_target.item_instance_id is None:
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
        # resolve_player_target は解決できなければ例外を投げる (候補一覧つき)。
        # 以前はここで None を受けて同等の例外へ変換していたが、二重に候補を
        # 組み立てる必要は無くなった。
        player_target = resolve_player_target(target_player_label, runtime_context)
        if player_target.player_id is None:
            raise ToolArgumentResolutionException(
                f"この名前は渡す相手として扱えません: {target_player_label}",
                "INVALID_TARGET_KIND",
            )

        return _with_inner_thought(
            {
                "item_spec_id": item_target.item_instance_id,
                "is_spoiled": item_target.is_spoiled,
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
                quantity = _give_quantity_or_raise(entry.get("quantity"))
                resolved.append({
                    "index": i,
                    "quantity": quantity,
                    "item_spec_id": resolved_entry["item_spec_id"],
                    "is_spoiled": resolved_entry["is_spoiled"],
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
        """所持アイテムラベル (I1 等) を item_spec_id に解決する。

        ラベルは「同じ種類の集約表示」なので、resolver 時点で代表 slot を
        固定すると同名複数個の連続 drop / give で古い slot を掴む。
        use_item と同じく executor が実行時に slot を引き直す。
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
        if target.item_instance_id is None:
            raise ToolArgumentResolutionException(
                (
                    f"指定されたアイテム名は手放す対象として扱えません: {label}。"
                    "所持アイテム欄の \"\" 内の名前を指定してください。"
                ),
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "item_spec_id": target.item_instance_id,
                "is_spoiled": target.is_spoiled,
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

    def _resolve_vote(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """`spot_graph_vote` の target_player_label を player_id に解決する。

        **空ラベルは棄権**なので、解決せずそのまま通す。ここで「名前が無い」
        と弾くと棄権できなくなり、「情報が足りないので保留」という正当な
        判断を潰す (agent_design_principles の「取れる手段の質」)。
        """
        label = args.get("target_player_label")
        if not isinstance(label, str) or not label.strip():
            return {**args, "target_player_id": None}
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="spot_graph_player",
            expected_types=(PlayerToolRuntimeTargetDto,),
            label_name="投票する相手の名前",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        return {**args, "target_player_id": target.player_id}

    def _resolve_report_body(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """`spot_graph_report_body` の target_player_label を player_id に解決する。

        **投票と違って空ラベルを通さない。** 投票の空欄は棄権という意思表示
        だが、報告に対応するものは無い。誰を見つけたのかが会議の出発点なので、
        空のまま通すと招集の理由が定まらない。
        """
        label = args.get("target_player_label")
        if not isinstance(label, str) or not label.strip():
            raise ToolArgumentResolutionException(
                "倒れている相手の名前が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = _resolve_target_with_display_name_fallback(
            label,
            runtime_context,
            kind="spot_graph_player",
            expected_types=(PlayerToolRuntimeTargetDto,),
            label_name="倒れている相手の名前",
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        return {**args, "target_player_id": target.player_id}

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
        record_canonical_identifier(
            args, "destination_label", target.display_name
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
        """``target_label`` を物体・対象プレイヤー・所持道具に解決する。

        対人 interaction は専用ツールを増やさず ``interact`` に載せる
        (docs/memory_system/interpersonal_interaction_design.md §3.3)。対象名の
        指定作法が物体と人で揃うので、LLM は行為したいものの名前を書くだけで
        済む。解決した種別に応じて ``object_id`` か ``target_player_id`` の
        **どちらか一方だけ**を埋める。両方埋めると executor 側が物体への操作
        なのか対人操作なのか判別できなくなる。
        """
        target = resolve_target(
            args.get("target_label"),  # type: ignore[arg-type]
            runtime_context,
            accept_kinds=(
                "spot_graph_object",
                "spot_graph_player",
                "inventory_item",
            ),
            label_name="対象の名前",
        )
        action = args.get("action_name", "")
        if not isinstance(action, str) or not action.strip():
            raise ToolArgumentResolutionException(
                "action_name が指定されていません。",
                "INVALID_ARGUMENT",
            )
        if _NO_ACTION_PLACEHOLDER_RE.fullmatch(action.strip()):
            raise ToolArgumentResolutionException(
                "候補なしの表示は action_name として実行できません。",
                "INVALID_ARGUMENT",
            )
        # 表示の写し崩れ (quote つき / 表示行の丸ごとコピー) を救う。
        # 対象が持つ操作に一致する候補があればそれを採り、無ければ生値の
        # まま先へ送って従来どおり「その操作はありません」で失敗させる。
        action = _pick_action_name(action, target)
        record_canonical_identifier(args, "action_name", action)
        record_canonical_identifier(args, "target_label", target.display_name)
        if target.kind == "spot_graph_player":
            if target.player_id is None:
                raise ToolArgumentResolutionException(
                    f"対象プレイヤーとして扱えない名前です: {args.get('target_label')}",
                    "INVALID_TARGET_KIND",
                )
            return _with_inner_thought(
                {
                    "object_id": None,
                    "target_player_id": target.player_id,
                    "action_name": action.strip(),
                },
                args,
            )
        if target.kind == "inventory_item":
            if target.item_instance_id is None:
                raise ToolArgumentResolutionException(
                    f"所持道具として扱えない名前です: {args.get('target_label')}",
                    "INVALID_TARGET_KIND",
                )
            return _with_inner_thought(
                {
                    "object_id": None,
                    "target_player_id": None,
                    # inventory DTO の既存契約では item_instance_id に
                    # ItemSpecId が入る。実 instance は所持確認時に引き直す。
                    "item_spec_id": target.item_instance_id,
                    "action_name": action.strip(),
                },
                args,
            )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"オブジェクトとして解決できない名前です: {args.get('target_label')}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "object_id": target.world_object_id,
                "target_player_id": None,
                "item_spec_id": None,
                "action_name": action.strip(),
            },
            args,
        )
