"""所持金の変化を、ツールの外側で測って trace に残す。

`gold_after` / `gold_delta` / `gold_change_source` を出していたのは商人ツール
だけだった。板を通した売買は 7G 増えても所持金の記録が 1 行も出ず、trace から
台帳を組むと**板で稼いだ人を実際より低く見積もる**。

**同じ量が動くなら、どのツールから動いても同じ形で記録する。** ツールの側に
書いて回ると、書き忘れたツールが静かに漏れ、「どのツールが gold を動かすか」
という知識が分析器の側へ漏れる。ツールを 1 つ足すたびに分析器が壊れる形なので、
**呼び出しの前後で測る**ことにした。将来クエスト報酬や戦闘の戦利品で gold が
動いても、同じ経路を通る限り自動で残る。

## 呼んだ人だけでは足りなかった

最初の版は**呼び出した人の財布だけ**を測っていた。二者間の取引では相手側の
gold も動くので、実 run では受け取った側の行が 1 件も出ず、台帳は差額から
逆算するしかなかった。**逆算が要る時点で、知識が分析器へ戻っている。**

いまは**世界にいる全員を測る**。人数が少ないうちはこれで足りる。

**人数が増えたら「申告された人だけ測る」形へ移す判断が要る。** ただしそのとき
この理由が消えていると、後の人が「非効率だ」と思って申告ベースへ変え、
**申告漏れが静かな失敗として復活する**。移すなら、申告漏れを別の方法で検出
できるようにしてからにすること。

## 申告は真実ではなく、期待として使う

ツールは「この人たちの gold が動くはず」を申告できる (`gold_affected_player_ids`)。
**数字の真実は測った結果**で、申告は照合にだけ使う。食い違えば警告が出るので、
**申告漏れそのものが検出できる**。申告を真実にすると、漏れたときに静かに間違う。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Sequence

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

GoldReader = Callable[[PlayerId], Optional[int]]
"""その人の所持金を返す。読めない構成では None を返す。"""

RosterReader = Callable[[], Sequence[PlayerId]]
"""所持金を測る対象の一覧。読めない構成では空を返す。"""

ToolHandler = Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]


def wrap_with_gold_change(
    handler: ToolHandler,
    gold_reader: GoldReader,
    *,
    tool_name: str,
    roster_reader: Optional[RosterReader] = None,
) -> ToolHandler:
    """ツール実行の前後で所持金を測り、動いていたら trace に残す handler を返す。

    出どころの名前 (`gold_change_source`) は handler が名乗っていればそれを
    使う (`merchant_buy` のような意味のある名前をツール名で潰さない)。
    **数字は必ず測った側を使う** — 申告は書いた時点の想定で、実際は世界で
    起きたこと。台帳を組むのは後者でなければならない。
    """

    def _handler(
        player_id: PlayerId, arguments: Dict[str, Any], runtime_context: Any,
    ) -> LlmCommandResultDto:
        watched = _watched(roster_reader, player_id)
        before = _snapshot(gold_reader, watched)
        result = handler(player_id, arguments, runtime_context)
        after = _snapshot(gold_reader, watched)
        changes = _changes(before, after)
        if not changes:
            return result
        _warn_on_mismatch(tool_name, player_id, result, changes)
        return replace(
            result,
            trace_payload=_with_gold(
                result.trace_payload, changes, player_id, tool_name,
            ),
        )

    _handler.records_gold_change = True  # type: ignore[attr-defined]
    return _handler


def _watched(
    roster_reader: Optional[RosterReader], player_id: PlayerId,
) -> List[PlayerId]:
    """測る対象。名簿が読めなければ、少なくとも本人は測る。"""
    if roster_reader is None:
        return [player_id]
    try:
        roster = list(roster_reader())
    except Exception:  # noqa: BLE001
        logger.warning("所持金を測る対象の一覧を読めなかった", exc_info=True)
        return [player_id]
    if player_id not in roster:
        roster.append(player_id)
    return roster


def _snapshot(
    gold_reader: GoldReader, watched: Sequence[PlayerId],
) -> Dict[int, int]:
    """いまの所持金。読めなかった人は**入れない** (0 と書かない)。"""
    out: Dict[int, int] = {}
    for pid in watched:
        value = _read_gold(gold_reader, pid)
        if value is not None:
            out[int(pid.value)] = value
    return out


def _changes(
    before: Dict[int, int], after: Dict[int, int],
) -> Dict[int, Dict[str, int]]:
    """前後で動いた人だけを返す。

    **前後どちらかが読めなかった人は含めない。** 読めなかったことを 0 と
    書くと、動かなかったのと区別がつかなくなる。
    """
    return {
        pid: {"delta": after[pid] - before[pid], "after": after[pid]}
        for pid in before
        if pid in after and after[pid] != before[pid]
    }


def _with_gold(
    payload: Optional[Dict[str, Any]],
    changes: Dict[int, Dict[str, int]],
    player_id: PlayerId,
    tool_name: str,
) -> Dict[str, Any]:
    """所持金の変化を足した**新しい** payload を返す (元は変えない)。

    行動した人の分は従来どおり `gold_delta` / `gold_after` に置く。相手側を
    含む全員分は `gold_changes` に並べる。**1 か所を見れば台帳が組める**
    ようにするため、行動した人も `gold_changes` に含める。
    """
    merged = dict(payload or {})
    actor = int(player_id.value)
    if actor in changes:
        merged["gold_delta"] = changes[actor]["delta"]
        merged["gold_after"] = changes[actor]["after"]
        merged.setdefault("gold_change_source", tool_name)
    merged["gold_changes"] = [
        {"player_id": pid, "delta": change["delta"], "after": change["after"]}
        for pid, change in sorted(changes.items())
    ]
    return merged


def _warn_on_mismatch(
    tool_name: str,
    player_id: PlayerId,
    result: LlmCommandResultDto,
    changes: Dict[int, Dict[str, int]],
) -> None:
    """申告と実測の食い違いを警告する。

    **申告に無い人の gold が動いた**のは、どこかで意図しない移動が起きている
    ということなので、まさに検出したい事故になる。行動した人は常に動きうる
    ので、申告が無くても警告しない。
    """
    actor = int(player_id.value)
    declared = {int(pid) for pid in (result.gold_affected_player_ids or ())}
    declared.add(actor)
    moved = set(changes)
    unexpected = moved - declared
    if unexpected:
        logger.warning(
            "%s: 申告に無い人の所持金が動いた (player_ids=%s)",
            tool_name, sorted(unexpected),
        )
    missing = declared - moved - {actor}
    if missing:
        logger.warning(
            "%s: 動くと申告された人の所持金が動かなかった (player_ids=%s)",
            tool_name, sorted(missing),
        )


def _read_gold(gold_reader: GoldReader, player_id: PlayerId) -> Optional[int]:
    """所持金を読む。読めなければ None (ツール自体は止めない)。"""
    try:
        return gold_reader(player_id)
    except Exception:  # noqa: BLE001
        logger.warning(
            "所持金を読めなかったため gold の変化を trace に残せない: player_id=%s",
            player_id, exc_info=True,
        )
        return None


def build_gold_reader(player_status_repository: Any) -> GoldReader:
    """所持金リポジトリから読み取り役を作る。未注入なら常に None を返す。"""

    def _read(player_id: PlayerId) -> Optional[int]:
        if player_status_repository is None:
            return None
        status = player_status_repository.find_by_id(player_id)
        if status is None:
            return None
        return int(status.gold.value)

    return _read


def build_roster_reader(player_status_repository: Any) -> RosterReader:
    """所持金を測る対象の一覧を読む役を返す。"""

    def _roster() -> Sequence[PlayerId]:
        if player_status_repository is None:
            return ()
        return [status.player_id for status in player_status_repository.find_all()]

    return _roster
