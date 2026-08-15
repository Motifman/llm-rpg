"""所持金の変化を、ツールの外側で測って trace に残す。

`gold_after` / `gold_delta` / `gold_change_source` を出していたのは商人ツール
だけだった。板を通した売買は 7G 増えても所持金の記録が 1 行も出ず、trace から
台帳を組むと**板で稼いだ人を実際より低く見積もる**。

**同じ量が動くなら、どのツールから動いても同じ形で記録する。** ツールの側に
書いて回ると、書き忘れたツールが静かに漏れ、「どのツールが gold を動かすか」
という知識が分析器の側へ漏れる。ツールを 1 つ足すたびに分析器が壊れる形なので、
**呼び出しの前後で測る**ことにした。将来クエスト報酬や戦闘の戦利品で gold が
動いても、同じ経路を通る限り自動で残る。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

GoldReader = Callable[[PlayerId], Optional[int]]
"""その人の所持金を返す。読めない構成では None を返す。"""

ToolHandler = Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]


def wrap_with_gold_change(
    handler: ToolHandler, gold_reader: GoldReader, *, tool_name: str,
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
        before = _read_gold(gold_reader, player_id)
        result = handler(player_id, arguments, runtime_context)
        after = _read_gold(gold_reader, player_id)
        if before is None or after is None or before == after:
            # 読めなかったことを 0 と書くと、**動かなかったのと区別が
            # つかなくなる**。動いていないなら足さない (trace を太らせない)。
            return result
        return replace(
            result,
            trace_payload=_with_gold(result.trace_payload, before, after, tool_name),
        )

    _handler.records_gold_change = True  # type: ignore[attr-defined]
    return _handler


def _with_gold(
    payload: Optional[Dict[str, Any]], before: int, after: int, tool_name: str,
) -> Dict[str, Any]:
    """所持金の 3 項目を足した**新しい** payload を返す (元は変えない)。"""
    merged = dict(payload or {})
    merged["gold_delta"] = after - before
    merged["gold_after"] = after
    merged.setdefault("gold_change_source", tool_name)
    return merged


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
