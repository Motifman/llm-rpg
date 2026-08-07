"""プロンプト本文と、同時に生成した tool 引数候補の表記契約を検査する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.world_graph.tool_argument_text import (
    quote_tool_argument,
)


@dataclass(frozen=True)
class PromptArgumentContractViolation:
    """引数候補が引用符つきで本文に現れなかった 1 件。"""

    value: str
    source: str
    target_label: str
    target_kind: str


class PromptArgumentContractError(RuntimeError):
    """起動時の全 player 検査で、引数表記の破れが見つかった。"""


def find_prompt_argument_contract_violations(
    current_state_text: str,
    runtime_context: ToolRuntimeContextDto,
) -> Tuple[PromptArgumentContractViolation, ...]:
    """宣言された文字列引数が、引用符つきで本文に現れることを確かめる。

    暗所で伏せた物体は snapshot を作る段階で objects から落ちるため、targets
    に登録されない。ここで ``dark_hidden_object_names`` を引く必要はない。
    将来それらを targets に載せる変更をしたなら、名前を指定できない候補を
    作ったことになるため、この検査が起動時に止めるのが正しい。

    逆向きの検査はしない。説明文の引用符まで「引数」と誤認するためである。
    """
    violations: list[PromptArgumentContractViolation] = []
    seen: set[tuple[str, str, str]] = set()
    for target_label, target in runtime_context.targets.items():
        candidates = (("display_name", target.display_name),) + tuple(
            ("action_name", action_name)
            for action_name in target.available_interactions
        )
        for source, value in candidates:
            value = str(value).strip()
            if not value or quote_tool_argument(value) in current_state_text:
                continue
            identity = (value, source, target_label)
            if identity in seen:
                continue
            seen.add(identity)
            violations.append(
                PromptArgumentContractViolation(
                    value=value,
                    source=source,
                    target_label=target_label,
                    target_kind=target.kind,
                )
            )
    return tuple(violations)
