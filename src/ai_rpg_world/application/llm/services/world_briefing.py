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

from ai_rpg_world.application.llm.services.world_vocabulary import (
    lighting_display,
)
from ai_rpg_world.application.world_graph.tool_argument_text import (
    quote_tool_argument,
)


_DutyEntry = Tuple[str, str, str, str]
_TaskEntry = Tuple[str, str, str, str, str]


def _spot_name(spot: Any) -> str:
    return str(getattr(spot, "name", "") or getattr(spot, "spot_id", "") or "")


def _lighting_of(spot: Any) -> str:
    atmosphere = getattr(spot, "atmosphere", None)
    lighting = getattr(atmosphere, "lighting", None) if atmosphere else None
    return lighting_display(lighting) if lighting is not None else ""


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

    task_entries = _task_places(spots, interiors, duty_state_key)
    owner_by_duty = {
        duty: str(getattr(player, "name", "") or "") for player, duty in duties
    }
    lines: List[str] = ["【点検の割り当て】"]
    for duty, label, place, _object_name, _action_name in task_entries:
        where = f" ({place})" if place else ""
        if duty:
            owner = owner_by_duty.get(duty)
            if owner is None:
                # 担当キーだけ存在して割り当てる人物が居ない作業は、誰でも
                # 引き取れる作業ではない。engine のキーを露出せず省く。
                continue
            lines.append(f"  担当: {owner} — {label}{where}")
        else:
            lines.append(f"  共通 — {label}{where}")
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


def _task_places(
    spots: Sequence[Any], interiors: Any, duty_state_key: str
) -> List[_TaskEntry]:
    """点検を完了フラグから見つけ、担当の有無と入口の呼び名を返す。

    `task_` フラグを立てる interaction を点検の最終段とみなし、その
    action_name から同じ系列の入口を逆算する。物体内の「最初の操作」を採る
    と、点検と無関係な操作が先に宣言されたときに誤った入口を表示するため。

    担当条件が無い点検も落とさず「共通」として知らせることで、必要数だけ
    増えて利用者が存在を知らない状態を作らない。
    """
    found: List[_TaskEntry] = []
    by_spot_id = dict(interiors or {})
    for spot in spots:
        interior = by_spot_id.get(getattr(spot, "spot_id", None))
        for obj in getattr(interior, "objects", ()) or ():
            interactions = tuple(getattr(obj, "interactions", ()) or ())
            by_action_name = {
                str(getattr(interaction, "action_name", "") or ""): interaction
                for interaction in interactions
            }
            seen_entry_names: set[str] = set()
            for completion in interactions:
                if not any(
                    str(getattr(effect.effect_type, "value", effect.effect_type))
                    == "SET_FLAG"
                    and str(
                        (getattr(effect, "parameters", None) or {}).get(
                            "flag_name", ""
                        )
                    ).startswith("task_")
                    for effect in getattr(completion, "effects", ()) or ()
                ):
                    continue
                completion_name = str(
                    getattr(completion, "action_name", "") or ""
                )
                entry_name = completion_name
                for suffix in ("_3", "_2"):
                    if entry_name.endswith(suffix):
                        entry_name = entry_name[: -len(suffix)]
                        break
                entry = by_action_name.get(entry_name, completion)
                entry_name = str(getattr(entry, "action_name", "") or "")
                if not entry_name or entry_name in seen_entry_names:
                    continue
                seen_entry_names.add(entry_name)

                duty = ""
                for condition in getattr(entry, "preconditions", ()) or ():
                    required = getattr(condition, "required_state", None) or {}
                    if required.get(duty_state_key):
                        duty = str(required[duty_state_key])
                        break
                label = str(getattr(entry, "display_label", "") or entry_name)
                found.append(
                    (
                        duty,
                        label,
                        str(getattr(spot, "name", "") or ""),
                        str(getattr(obj, "name", "") or ""),
                        entry_name,
                    )
                )
    return found


def _duty_places(
    spots: Sequence[Any], interiors: Any, duty_state_key: str
) -> Dict[str, _DutyEntry]:
    """担当キー → (呼び名, 場所名, 物体名, 入口 action_name)。

    **担当キーをそのままプロンプトに出さない** (#892)。``weather`` は engine
    の識別子で、読み手に要るのは「気象を記録する」という呼び名のほう。

    呼び名と操作名は interaction の 1 段目 (`_2` `_3` `_pretend` が付かない
    もの) から採る。**現在進行中の段へ追従しない。** 担当との対応は run 中
    不変の情報であり、現在段を出すと担当行が進捗ごとに変わる。どの段をいま
    呼べるかは、現在状態の物体行が別に教える。
    """
    found: Dict[str, _DutyEntry] = {}
    for duty, label, place, object_name, action_name in _task_places(
        spots, interiors, duty_state_key
    ):
        if duty:
            found.setdefault(duty, (label, place, object_name, action_name))
    # 単体の表示部品では完了効果まで組まない fixture もある。担当表示の
    # 問いには SET_FLAG は不要なので、担当条件を持つ入口を直接補う。
    by_spot_id = dict(interiors or {})
    for spot in spots:
        interior = by_spot_id.get(getattr(spot, "spot_id", None))
        for obj in getattr(interior, "objects", ()) or ():
            for interaction in getattr(obj, "interactions", ()) or ():
                action_name = str(getattr(interaction, "action_name", "") or "")
                if action_name.endswith(("_2", "_3", "_pretend")):
                    continue
                for condition in getattr(interaction, "preconditions", ()) or ():
                    required = getattr(condition, "required_state", None) or {}
                    duty = required.get(duty_state_key)
                    if not duty:
                        continue
                    found.setdefault(
                        str(duty),
                        (
                            str(
                                getattr(interaction, "display_label", "")
                                or action_name
                            ),
                            str(getattr(spot, "name", "") or ""),
                            str(getattr(obj, "name", "") or ""),
                            action_name,
                        ),
                    )
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


def build_meeting_rules_text(
    *,
    meeting_enabled: bool,
    tick_limit: Optional[int] = None,
    silence_limit_ticks: Optional[int] = None,
    cooldown_ticks: Optional[int] = None,
    minutes_per_tick: Optional[int] = None,
) -> str:
    """話し合いと投票の決まりを、engine の実装から書き起こす。

    ## なぜシナリオに書かせないか

    station_drill は決まりを ``llm_public_intro`` に手で写していた。そこには
    こうあった。

        投票は最多票の 1 人が追放される。同数なら誰も追放されない。
        棄権も 1 票として数える。

    素直に読めば「1 票入った人が追放される」。**実装はそうではない。**
    ``resolve_vote`` は最多票が棄権の数を **上回る** ことを求める
    (``top > skip_count``)。実 run 011 は 1 票対棄権 2 票で、誰も追放
    されなかった。

    ハギの独白が残っている。

        確証がないまま名指しはできない。棄権だ。

    **自分の棄権が犯人を守ることを知らないまま棄権した。** 文から導けない
    以上、これは推理力ではなく説明の問題。

    決まりは engine が持っているので engine が書く。シナリオが持つのは
    世界の言葉であって、集計の規則ではない (#949 と同じ切り分け)。

    ## 数字は世界の単位に直す

    打ち切りまでの長さを ``tick`` で出さない。世界の中に無い単位で、
    エージェントが毎ターン見ている時計とも揃わない (#892)。
    """
    if not meeting_enabled:
        return ""
    lines = [
        "【話し合いと投票の決まり】",
        "- 追放されるのは、最も多く名指しされた 1 人だけ。",
        "- 棄権も 1 票として数える。**棄権の数が名指しの最多と並ぶか上回ると、"
        "誰も追放されない。**",
        "- 棄権が誰も追放しない結果につながれば、襲う者には次に襲える機会が残る。",
        "- 名指しが割れて最多が複数居るときも、誰も追放されない。",
        "- 一度投じた票は変えられない。",
    ]
    if tick_limit:
        lines.append(
            "- 話し合いには"
            f"{_span_text(tick_limit, minutes_per_tick)}の持ち時間がある。"
            "使い切ると、投票していない人は棄権として扱われる。"
        )
    if silence_limit_ticks:
        lines.append(
            "- 誰も口を開かない時間が"
            f"{_span_text(silence_limit_ticks, minutes_per_tick)}続くと、"
            "その時点で打ち切られる。"
        )
    if cooldown_ticks:
        lines.append(
            "- 話し合いが終わった直後は招集できない。"
            f"次に集まれるまで{_span_text(cooldown_ticks, minutes_per_tick)}かかる。"
        )
    return "\n".join(lines)


def _span_text(ticks: int, minutes_per_tick: Optional[int]) -> str:
    """長さを世界の単位で書く。**tick を出さない。**

    分に直せない世界では「手番 N 回ぶん」と書く。数だけを裸で置くと、
    個数にも識別子にも読める (#949 で地図が踏んだ形)。
    """
    if minutes_per_tick:
        return f" {ticks * minutes_per_tick} 分"
    return f" 手番 {ticks} 回ぶん"


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
    meeting_enabled: bool = False,
    meeting_tick_limit: Optional[int] = None,
    meeting_silence_limit_ticks: Optional[int] = None,
    meeting_cooldown_ticks: Optional[int] = None,
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
        build_meeting_rules_text(
            meeting_enabled=meeting_enabled,
            tick_limit=meeting_tick_limit,
            silence_limit_ticks=meeting_silence_limit_ticks,
            cooldown_ticks=meeting_cooldown_ticks,
            minutes_per_tick=minutes_per_tick,
        ),
    ]
    return "\n\n".join(s for s in sections if s)


def build_recorded_player_state_tick_keys(
    spots: Sequence[Any],
    interiors: Any = None,
    player_interactions: Any = None,
) -> frozenset:
    """``RECORD_PLAYER_STATE_TICK`` が本人の state に書く key を宣言から集める。

    ``tick`` は世界の中に無い語 (#892)。``自分の状態: prayed_at_tick=5`` と
    出ると、読み手はその数字で何も判断できない。

    物体 state と違い、本人の state に ``hidden_state_keys`` は無い。**どの key
    が内部の記録かは宣言からしか分からない**ので、ここで導出して表示側へ渡す。

    名前で当てにいかない (``tick`` を含む key を探す等)。それでは作家の命名を
    engine が推測する形に逆戻りする。物体側と同じ「書く宣言があるなら伏せる」に
    揃える。
    """
    keys: set = set()

    def _scan(effects: Any) -> None:
        for effect in effects or ():
            effect_type = getattr(effect, "effect_type", None)
            name = getattr(effect_type, "value", effect_type)
            if name != "RECORD_PLAYER_STATE_TICK":
                continue
            params = getattr(effect, "parameters", None) or {}
            state_key = params.get("state_key")
            if isinstance(state_key, str) and state_key:
                keys.add(state_key)

    def _scan_interactions(interactions: Any) -> None:
        for interaction in interactions or ():
            _scan(getattr(interaction, "effects", ()))

    _scan_interactions(player_interactions)
    for interior in _iter_interiors(interiors):
        for obj in getattr(interior, "objects", ()) or ():
            _scan_interactions(getattr(obj, "interactions", ()))
    return frozenset(keys)


def _iter_interiors(interiors: Any):
    """interiors がどの形で来ても内部を列挙する。"""
    if interiors is None:
        return ()
    if hasattr(interiors, "values"):
        return list(interiors.values())
    if isinstance(interiors, (list, tuple)):
        return list(interiors)
    return ()


def build_own_state_display_names(
    spots: Sequence[Any],
    interiors: Any = None,
    role_labels: Optional[Dict[str, str]] = None,
    *,
    duty_state_key: str = "duty",
    role_key: str = "role",
) -> Dict[str, Tuple[str, str]]:
    """自由 state のキー=値 → (見出し, 呼び名)。

    ``自分の状態: duty=weather, role=crew`` のように engine のキーが
    プロンプトへ漏れていた (#892)。読み手はその語で何も探せない。

    **新しい辞書を作らない。** 呼び名は既にシナリオが持っている。

    - 役割 → ``metadata.role_labels``
    - 担当 → その担当を要求する interaction の display_label と入口 action_name

    display_label 自体を action_name として受理する案は採らない。表示値と識別子の
    契約が曖昧になり、「引用符内だけをそのまま渡し、表示に無い名前は推測しない」
    という規則と矛盾する (#1011)。代わりに両者の対応を ``→`` で明示する。

    宣言の無いキーは載せない。載せると、また engine の語彙が出る。
    """
    names: Dict[str, Tuple[str, str]] = {}
    for role, label in (role_labels or {}).items():
        names[f"{role_key}={role}"] = ("立場", label)
    for duty, (task_label, place, object_name, action_name) in _duty_places(
        spots, interiors, duty_state_key
    ).items():
        if action_name:
            quoted_action = quote_tool_argument(action_name)
            if place and object_name:
                call_hint = f"{place}の{object_name} → {quoted_action}"
            elif place:
                call_hint = f"{place} → {quoted_action}"
            else:
                call_hint = quoted_action
            task_label = f"{task_label} ({call_hint})"
        names[f"{duty_state_key}={duty}"] = ("担当", task_label)
    return names
