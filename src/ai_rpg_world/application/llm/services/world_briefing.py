"""世界の見取り図と点検の割り当てを、シナリオのデータから組み立てる。

## なぜ手書きをやめるか

station_drill の ``llm_public_intro`` には、シナリオが既に持っている事実が
手で写されていた。#938 で players / spots / game_end_conditions を変えた
とき、そちらが更新されず **4 箇所ずれた**。

    「参加者 4 人のうち 1 人がインポスター」  → 実際は 5 人 / 1 人
    「クルーの勝利: タスクをすべて終える」    → 実際は 4 個中 3 個
    「タスクは 3 つ」「3 つすべて終える」     → 実際は 4 つ / 3 つ必要
    機関室の発電機がタスク一覧に無い

実 run 009 のエージェントは**存在しない世界の前提で推論していた**。写しは
必ず腐る。データから組み立てれば、ずれようがない。

## なぜシステムプロンプトに置くか

見取り図も割り当ても **run 中変わらない**。だからプレフィックスキャッシュ
(設計判断 #1) に載り、実質ただで毎ターン見える。

Among Us では会議中も地図を見られる。**消えるのは操作であって、空間の
知識ではない。** システムプロンプトに置けば「会議のときは地図を出す」と
いうフェーズ分岐を engine に書かずに済む。

## 移動 tick を出す

アリバイの検証がこれで初めて可能になる。「集会室から物資庫は 2 tick かかる。
1 tick で着いたと言うなら通路を通ったはずだ」。run 009 でインポスターが
時刻を並べて弁明していたが、**検証する材料が誰にも無かった**。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

#: 明るさの生値をプロンプトに出さない (#892)。
_LIGHTING_TEXT = {
    "BRIGHT": "明るい",
    "DIM": "薄暗い",
    "DARK": "暗い",
}


def _spot_name(spot: Any) -> str:
    return str(getattr(spot, "name", "") or getattr(spot, "spot_id", "") or "")


def _lighting_of(spot: Any) -> str:
    atmosphere = getattr(spot, "atmosphere", None)
    lighting = getattr(atmosphere, "lighting", None) if atmosphere else None
    key = getattr(lighting, "value", lighting)
    return _LIGHTING_TEXT.get(str(key), "")


def build_world_map_text(
    spots: Sequence[Any],
    connections: Sequence[Any],
    *,
    minutes_per_tick: Optional[int] = None,
) -> str:
    """部屋の隣接と、そこへ移るのにかかる時間を 1 節にまとめる。空なら空文字。

    座標は出さない。**プレイヤーが使うのは「隣か / どれだけかかるか」だけ**で、
    x/y を出しても engine の内部表現が漏れるだけになる。

    ## 単位は世界の時計に揃える

    最初は ``機関室 1`` と数字だけを並べ、脚注で「tick 数」と説明していた。
    **数字より後ろに説明があるので、読む時点では意味が分からない。**
    個数にも識別子にも読める。しかも ``tick`` は engine の語彙で、世界の
    中に無い単位 (#892)。

    エージェントは毎ターン「現在時刻: 深夜 0:05」を見ている。同じ分単位で
    書けば、**アリバイの検算がそのままできる**。「0:10 に出たなら 0:15 に
    しか着けない」。

    ``minutes_per_tick`` が渡らない世界 (時計を宣言していない) では、
    数えられる単位で書く。engine の tick は出さない。
    """
    if not spots:
        return ""
    name_by_id = {str(getattr(s, "spot_id", "")): _spot_name(s) for s in spots}
    # 行き先は集合で持つ。**双方向の通路は両向きが別々に返ってくる**ので、
    # 素直に append すると同じ行き先が 2 度並ぶ。
    neighbours: Dict[str, Dict[str, int]] = {k: {} for k in name_by_id}

    def _note(src: str, dst: str, ticks: int) -> None:
        if src not in neighbours or dst not in neighbours:
            return
        # 同じ相手へ複数の経路があるなら短いほうを載せる。アリバイの検証に
        # 使うので、**最短でどれだけかかるか**が知りたい値。
        current = neighbours[src].get(dst)
        if current is None or ticks < current:
            neighbours[src][dst] = ticks

    for conn in connections:
        a = str(getattr(conn, "from_spot_id", "") or "")
        b = str(getattr(conn, "to_spot_id", "") or "")
        ticks = int(getattr(conn, "travel_ticks", 1) or 1)
        _note(a, b, ticks)
        if getattr(conn, "is_bidirectional", True):
            _note(b, a, ticks)

    lines: List[str] = ["【この場所の造り】"]
    for spot in spots:
        key = str(getattr(spot, "spot_id", ""))
        name = name_by_id.get(key) or key
        lighting = _lighting_of(spot)
        head = f"  {name}" + (f" ({lighting})" if lighting else "")
        exits = sorted(
            neighbours.get(key, {}).items(),
            key=lambda kv: (kv[1], name_by_id.get(kv[0], "")),
        )
        if not exits:
            lines.append(f"{head} — 行き来できる先は無い")
            continue
        rendered = " / ".join(
            f"{name_by_id.get(other, other)} まで {_travel_cost_text(ticks, minutes_per_tick)}"
            for other, ticks in exits
        )
        lines.append(f"{head} → {rendered}")
    return "\n".join(lines)


def _travel_cost_text(ticks: int, minutes_per_tick: Optional[int]) -> str:
    """移動にかかる時間を、その世界の言葉で書く。

    **単位を必ず数字に添える。** 脚注に逃がすと、読む時点で意味が分からない。
    """
    if minutes_per_tick and minutes_per_tick > 0:
        return f"{ticks * minutes_per_tick} 分"
    return f"{ticks} 手ぶん"


def build_duty_roster_text(
    players: Sequence[Any],
    spots: Sequence[Any],
    interiors: Any = None,
    *,
    duty_state_key: str = "duty",
    required_count: Optional[int] = None,
    winner_label: str = "",
) -> str:
    """誰がどの点検を担当し、その場所がどこかを 1 節にまとめる。

    担当を宣言していない世界では空文字を返す。**その世界に無い概念を
    プロンプトへ持ち込まない。**

    担当と場所の対応は、担当キーを要求する interaction がどの spot に
    あるかで決まる。シナリオに書き直させない (書き直させると必ずずれる)。
    """
    duties = [
        (p, str((getattr(p, "initial_state", None) or {}).get(duty_state_key) or ""))
        for p in players
    ]
    duties = [(p, d) for p, d in duties if d]
    if not duties:
        return ""

    place_of_duty = _duty_places(spots, interiors, duty_state_key)
    lines: List[str] = ["【点検の割り当て】"]
    for player, duty in duties:
        name = str(getattr(player, "name", "") or "")
        entry = place_of_duty.get(duty)
        if entry is None:
            # 担当だけ宣言されていて、対応する点検が世界に無い。engine の
            # キーを出すくらいなら書かない。**書くと読み手が触れないものを
            # 探しに行く。**
            continue
        label, place = entry
        where = f" ({place})" if place else ""
        lines.append(f"  {name} — {label}{where}")
    if len(lines) == 1:
        return ""
    # 勝ち筋の数字もデータから出す。**手で書くと、点検を 1 つ足したときに
    # 必ず置き去りになる** (#938 でそうなった)。
    if required_count is not None and winner_label:
        total = len(lines) - 1
        if required_count >= total:
            lines.append(f"  この {total} つをすべて終えれば{winner_label}の勝ち。")
        else:
            lines.append(
                f"  この {total} つのうち {required_count} つ終えれば{winner_label}の勝ち。"
            )
    return "\n".join(lines)


def _duty_places(
    spots: Sequence[Any], interiors: Any, duty_state_key: str
) -> Dict[str, Tuple[str, str]]:
    """担当キー → (その点検の呼び名, 場所の名前)。

    **担当キーをそのままプロンプトに出さない** (#892)。``weather`` は engine
    の識別子で、読み手に要るのは「気象を記録する」という呼び名のほう。

    呼び名は interaction の display_label から採る。1 段目 (`_2` `_3` が付か
    ないもの) を選ぶ。仕上げの段の「(仕上げ)」まで載せると、点検全体の名前
    としては狭くなる。
    """
    found: Dict[str, Tuple[str, str]] = {}
    # 部屋の中身は graph のノードではなく別の表に載っている。
    # ``SpotNode.interior`` は常に None なので、そちらを見ると**黙って空**になる。
    by_spot_id = dict(interiors or {})
    for spot in spots:
        interior = by_spot_id.get(getattr(spot, "spot_id", None))
        for obj in getattr(interior, "objects", ()) or ():
            for interaction in getattr(obj, "interactions", ()) or ():
                action_name = str(getattr(interaction, "action_name", "") or "")
                if action_name.endswith(("_2", "_3", "_pretend")):
                    continue
                for cond in getattr(interaction, "preconditions", ()) or ():
                    required = getattr(cond, "required_state", None) or {}
                    duty = required.get(duty_state_key)
                    if not duty:
                        continue
                    label = str(
                        getattr(interaction, "display_label", "") or action_name
                    )
                    found.setdefault(str(duty), (label, _spot_name(spot)))
    return found


def build_faction_summary_text(
    players: Sequence[Any],
    role_labels: Optional[Dict[str, str]] = None,
    *,
    role_key: str = "role",
) -> str:
    """陣営ごとの人数を 1 行にまとめる。役割の宣言が無ければ空文字。

    **人数は必ずデータから数える。** 手で書くと、人を 1 人足したときに
    必ず置き去りになる (#938 でそうなった)。

    **呼び名はシナリオが持つ。** ``crew`` / ``keeper`` は engine 側の識別子で、
    プロンプトに出す語ではない (#892)。呼び名の宣言が無い役割は数えるが
    名前を出さない。人数だけでも「何人いる世界か」は伝わる。
    """
    counts: Dict[str, int] = {}
    for player in players:
        role = str((getattr(player, "initial_state", None) or {}).get(role_key) or "")
        if role:
            counts[role] = counts.get(role, 0) + 1
    if len(counts) < 2:
        return ""
    total = sum(counts.values())
    labels = dict(role_labels or {})
    named = [
        f"{labels[role]} {n} 人" for role, n in sorted(counts.items()) if role in labels
    ]
    if not named:
        return f"参加者は {total} 人。自分がどの側かは【ペルソナ】に書かれている。"
    return (
        f"参加者は {total} 人。内訳は "
        + " / ".join(named)
        + "。自分がどの側かは【ペルソナ】に書かれている。"
    )


def build_world_briefing(
    *,
    spots: Sequence[Any],
    connections: Sequence[Any],
    players: Sequence[Any],
    show_world_map: bool,
    minutes_per_tick: Optional[int] = None,
    interiors: Any = None,
    role_labels: Optional[Dict[str, str]] = None,
    required_task_count: Optional[int] = None,
    task_winner_role: str = "",
) -> str:
    """システムプロンプトに載せる、run 中変わらない事実をまとめる。

    どれも空になりうる。**その世界に無い概念は 1 行も出さない。**
    """
    sections = [
        build_faction_summary_text(players, role_labels),
        build_world_map_text(spots, connections, minutes_per_tick=minutes_per_tick)
        if show_world_map
        else "",
        build_duty_roster_text(
            players,
            spots,
            interiors,
            required_count=required_task_count,
            winner_label=(role_labels or {}).get(task_winner_role, ""),
        ),
    ]
    return "\n\n".join(s for s in sections if s)
