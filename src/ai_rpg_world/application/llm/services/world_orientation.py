"""シナリオの世界に入るときの案内 (Orientation) を、今のシステムプロンプトの文から詰める (#1630)。"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.application.llm.services.persona_prompt_fragment_builder import PERSONA_HEADING
from ai_rpg_world.being.contract import Description, Orientation

_PARAGRAPH_BREAK = "\n\n"


def world_orientation(
    *,
    persona_block: str,
    world_title: str,
    intro: str,
    briefing_sections: Sequence[str] = (),
    action_limit_text: str | None = None,
) -> Orientation:
    """見出しの行で始まる段落は 1 つの説明文にし、見出しの無い段落は直前の説明文に続ける。

    概要と見取り図は、見出しの行で始まる段落ごとに分ける。シナリオが概要に書いた見出し
    (【このゲームについて】など) も、今のプロンプトでは見出しとして読まれている。
    人柄は、役職ごとの人物像を後ろに足したものも含めて 1 つにする。

    行動の制限は見出しを持たず、今のプロンプトでは最後の段落の末尾に付いているので、
    最後の説明文の文に続ける (環境の決まりに分けるのは #1630 の 4 本目)。
    """
    premise = f"【世界の前提】\n- 舞台のタイトル: {world_title}\n- 概要: {intro}"
    paragraphs = _PARAGRAPH_BREAK.join((premise, *briefing_sections)).split(_PARAGRAPH_BREAK)
    descriptions = [Description(heading=PERSONA_HEADING[1:-1], text=_persona_text(persona_block))]
    for paragraph in paragraphs:
        heading, _, text = paragraph.partition("\n")
        if heading.startswith("【") and heading.endswith("】") and text.strip():
            descriptions.append(Description(heading=heading[1:-1], text=text))
        else:
            descriptions[-1] = _continued(descriptions[-1], _PARAGRAPH_BREAK + paragraph)
    if action_limit_text is not None:
        descriptions[-1] = _continued(descriptions[-1], f"\n- 行動の制限: {action_limit_text}")
    return Orientation(descriptions)


def _persona_text(persona_block: str) -> str:
    """構造化された人物像は見出しの行から始まるので、見出しを外して文だけにする。"""
    stripped = persona_block.lstrip()
    if stripped.startswith(PERSONA_HEADING):
        return stripped[len(PERSONA_HEADING) :].removeprefix("\n")
    return persona_block


def _continued(description: Description, text: str) -> Description:
    return Description(heading=description.heading, text=description.text + text)
