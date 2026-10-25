"""Jev の接続先が、いま本当にこの契約で答えるかを実呼び出しで確かめる。

`-m live_api` を明示したときだけ走る。通常の pytest と CI、`-m quality` からは外れる。

## なぜ実呼び出しが要るか

アダプタの単体試験は ``httpx.MockTransport`` で「送る形」と「受けた形の写し」
を見る。そこで固定した応答の形が**実際の API と合っているか**は、単体試験では
分からない (design_decisions #41)。

とくに確かめたいのは Noul の応答である。Noul は confidence を返さない前提で
``Optional`` にした。返すようになったら、呼び出し側は confidence を見られる
ようになるので、その変化に気づきたい。

## コスト

1 回で 3 問。実測で input 630 tokens / $0.00003 程度。
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentSource,
    NoulQuestion,
    ScoreQuestion,
)
from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
    JevTypedJudgmentAdapter,
)

_OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"


def _api_key() -> str:
    load_dotenv()
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value and value != "EMPTY":
            return value
    return ""


@pytest.mark.live_api
def test_jev_answers_three_typed_questions_about_one_japanese_state() -> None:
    """日本語の state に Noul / Choice / Score を 1 回で問うと、3 件とも答えが返る。"""
    api_key = _api_key()
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY / OPENAI_API_KEY が無いため実呼び出しを省略する")

    adapter = JevTypedJudgmentAdapter(
        api_key=api_key,
        endpoint=_OPENROUTER_DECISIONS,
        model="typesafe/jev-1.13",
        timeout_seconds=30.0,
    )

    answers = adapter.judge(
        {
            "actor": "アオイ",
            "inner_thought": "小麦を集めて夕食の材料にしたい。",
            "written_action_name": "gather",
            "target": "麦畑",
            "available_interactions": {
                "reap_wheat": "麦畑の麦を刈り取って小麦を得る",
                "water_field": "麦畑に水をやる",
            },
        },
        {
            "rescue": ChoiceQuestion(
                instructions=(
                    "書かれた行動名は、対象の操作一覧のどれを意図しているか。どれにも当たらなければ該当なしを選ぶ。"
                ),
                options={
                    "reap_wheat": "麦を刈り取る操作",
                    "water_field": "水をやる操作",
                    "__no_match__": "一覧のどの操作とも対応しない",
                },
            ),
            "wake": NoulQuestion(
                instructions="当人が今すぐ行動を変える価値があるか。",
                true_means="今すぐ行動を変える価値がある",
                false_means="今は何もしなくてよい",
            ),
            "urgency": ScoreQuestion(
                instructions="当人が置かれた状況の切迫度。",
                levels=["落ち着いている", "気にかかる", "急を要する"],
            ),
        },
    )

    assert set(answers) == {"rescue", "wake", "urgency"}
    assert all(a.source is JudgmentSource.JEV for a in answers.values())

    # 意味で寄せられることの確認。`gather` は一覧に無い発明された名前で、
    # 文字の重なりでは `reap_wheat` に寄せられない。
    assert answers["rescue"].value == "reap_wheat"
    assert answers["rescue"].confidence is not None

    assert 0.0 <= answers["wake"].value <= 1.0
    # Noul が confidence を返し始めたら、ここで気づく。
    assert answers["wake"].confidence is None

    assert 0.0 <= answers["urgency"].value <= 2.0


@pytest.mark.live_api
def test_an_invented_action_name_is_rescued_by_the_real_model() -> None:
    """実モデルに問うと、``gather`` が閾値 0.7 を超えて ``reap_wheat`` へ寄る。

    単体試験は答えを固定するので、**閾値が実際の出力と噛み合うか**は分からない。
    暫定値 0.7 で救えることを実呼び出しで確かめる。救えなくなったらここで気づく。
    """
    api_key = _api_key()
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY / OPENAI_API_KEY が無いため実呼び出しを省略する")

    from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
    from ai_rpg_world.application.llm.services._argument_resolvers.action_name_rescue import (  # noqa: E501
        ActionNameRescue,
    )
    from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
        ActionNameSource,
        pick_action_name,
    )

    target = ToolRuntimeTargetDto(
        label="OBJ1",
        kind="spot_graph_object",
        display_name="麦畑",
        world_object_id=10,
        available_interactions=("reap_wheat", "water_field", "inspect_field"),
        interaction_labels=(
            ("reap_wheat", "麦畑の麦を刈り取って小麦を得る"),
            ("water_field", "麦畑に水をやる"),
            ("inspect_field", "麦畑の育ち具合を見る"),
        ),
    )
    rescue = ActionNameRescue(
        port=JevTypedJudgmentAdapter(
            api_key=api_key,
            endpoint=_OPENROUTER_DECISIONS,
            model="typesafe/jev-1.13",
            timeout_seconds=30.0,
        ),
        min_confidence=0.7,
    )

    resolution = rescue.rescue(
        pick_action_name("gather", target),
        target=target,
        inner_thought="小麦を集めて夕食の材料にしたい。",
    )

    assert resolution.value == "reap_wheat"
    assert resolution.source is ActionNameSource.JUDGMENT
    assert resolution.judgment is not None
    assert resolution.judgment.accepted is True
