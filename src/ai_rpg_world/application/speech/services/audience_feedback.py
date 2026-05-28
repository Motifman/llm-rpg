"""speech 発火直後に LLM へ返す audience フィードバックの文面組み立て。

Issue #269 第17回観察:
- 「あなたの声は 1 名のプレイヤーに**届く範囲**です」→「届きました」が正しい
  (発話後の事実報告であり、可能性ではない)
- 「shout は 2 hop 範囲まで**届きます**」→「内容も伝わる」と speaker が
  誤解する。FAINT (= 内容不明) の listener が含まれる場合は明示する
- 0 audience 時は「届きます」を避け、聞こえる範囲には誰もいなかった旨を
  事実として書く

ここでは ``runtime_manager`` (escape_game 経路) と ``speech_executor``
(LLM tool 経路) の両方から呼ばれる共通文面を提供する。LLM 向け text なので
application 層に置くのが自然 (presentation には流さない)。
"""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceMember,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum


def zero_audience_text(channel: SpeechChannel) -> str:
    """audience 0 時の channel-aware フィードバック (parenthesized 内側)。

    「届きます」のような可能性を匂わせる表現を避け、聞こえる範囲には他の
    プレイヤーがいなかった事実 + 次手の選択肢を書く。
    """
    if channel == SpeechChannel.WHISPER:
        return (
            "囁きは同じスポット内の特定の 1 人にしか聞こえませんが、対象は同じスポット"
            "にいません。声は誰にも届きませんでした。channel=say や channel=shout に"
            "切り替えるか、対象の居るスポットへ移動してください。"
        )
    if channel == SpeechChannel.SAY:
        return (
            "say の聞こえる範囲 (同じスポット + 隣接 1 hop) には他のプレイヤーが"
            "いませんでした。声は誰にも届きませんでした。channel=shout なら 2 hop "
            "先まで届きます。それでも範囲外なら、別の場所へ移動して相手の居るスポット"
            "に近づいてください。"
        )
    # SHOUT
    return (
        "shout の聞こえる範囲 (2 hop) にも他のプレイヤーはいませんでした。"
        "声は誰にも届きませんでした。物理的に合流する以外に伝える手段がありません。"
        "別の場所へ移動してください。"
    )


def audience_summary_text(
    channel: SpeechChannel,
    members: Iterable[SpeechAudienceMember],
) -> str:
    """audience が 1 名以上のときの clarity 内訳付きフィードバック。

    - 全員 FAINT (内容が伝わっていない): 「届いたが内容は伝わっていない」を
      強調し、shout や接近を提案
    - それ以外: 「N 名に届きました（内訳）」形式で clarity 別の人数を見せる
    - 全員同じ clarity でもカテゴリは 1 つだけ表示 (情報量はちゃんと残る)
    """
    members_list = list(members)
    n = len(members_list)
    if n == 0:
        return zero_audience_text(channel)

    if channel == SpeechChannel.WHISPER:
        # WHISPER は同 spot 1 名のみ、常に CLEAR
        return "囁きが届きました。"

    c_clear = sum(1 for m in members_list if m.clarity == SoundClarityEnum.CLEAR)
    c_muffled = sum(1 for m in members_list if m.clarity == SoundClarityEnum.MUFFLED)
    c_faint = sum(1 for m in members_list if m.clarity == SoundClarityEnum.FAINT)

    # 全員 FAINT: 内容は実質伝わっていないので強めに警告する
    if c_faint == n:
        return (
            f"声は {n} 名の聴覚範囲には届きましたが、いずれも『かすかな声』としか"
            f"聞こえておらず、内容は伝わっていません。channel=shout に切り替えるか、"
            f"相手の居るスポットに近づいてください。"
        )

    parts = []
    if c_clear:
        parts.append(f"明瞭に聞こえた {c_clear} 名")
    if c_muffled:
        parts.append(f"くぐもって遠くから聞こえた {c_muffled} 名")
    if c_faint:
        parts.append(
            f"声があったとしか分からない (内容は伝わっていない) {c_faint} 名"
        )
    detail = " / ".join(parts)
    return f"あなたの声は {n} 名に届きました（{detail}）。"
