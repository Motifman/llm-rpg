"""脱出ゲーム LLM 用: ネタバレ抑制導入文・ペルソナ・時間・行動量の圧の説明。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.llm.services.persona_prompt_fragment_builder import (
    PersonaPromptFragmentBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.inner_thought import INNER_THOUGHT_FIELD_NAME
from ai_rpg_world.application.llm.services.tool_catalog.memo_argument import MEMO_FIELD_NAME
from ai_rpg_world.application.llm.services.world_orientation import world_orientation
from ai_rpg_world.application.llm.services.world_scene import CURRENT_SURROUNDINGS_HEADING
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_RECALL
from ai_rpg_world.being.application.conduct_text import conduct_text
from ai_rpg_world.being.application.working_memory_text import system_prompt_text
from ai_rpg_world.being.contract import Description, OfferedBeingTools, Orientation
from ai_rpg_world.being.domain.working_memory import WorkingMemory
from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.persona_prompt_policy import PersonaPromptPolicy
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioMetadata


@dataclass(frozen=True)
class CharacterPromptInput:
    """API キャラクターから渡す、LLM 用の最小フィールド（presentation に依存しない）。"""

    character_id: str
    name: str
    first_person: str = "私"
    personality_tags: tuple[str, ...] = ()
    appearance: str = ""
    speech_samples: tuple[str, ...] = ()
    fragmented_memory: str = ""
    values: str = ""
    strengths: str = ""
    weaknesses: str = ""
    interpersonal_tendency: str = ""


# シナリオ metadata.description はネタバレを含み得るため、LLM 初期文脈では使わず
# シナリオ JSON `metadata.llm_public_intro`（公開レイヤー）を渡す。未設定のときの既定はテーマ非固定。

_DEFAULT_SAFE_INTRO = (
    "この局面の具体的な勝利条件は、【現在の目的】を参照すること。"
    "周囲の状況を調べ、移動し、必要なら同席者と声をかけ合いながら進める。"
    "手がかりは状況文・記録・物に現れるが、真偽の判断は観測の積み重ねに委ねる。"
)

# 勝敗・終了条件のない永続世界 (#526 / U5) 向けの中立 default。勝利条件に言及しない。
_DEFAULT_NO_GOAL_INTRO = (
    "この世界に固定された勝敗や終わりはない。"
    "周囲の状況を調べ、移動し、必要なら同席者と声をかけ合いながら過ごす。"
    "手がかりは状況文・記録・物に現れるが、真偽の判断は観測の積み重ねに委ねる。"
)


WORLD_RULES_HEADING = "この世界の決まり"
_SAY_INLINE_RULE = (
    "- `say_inline` を持つツールでは、その行動をしながら一言を添えられる (任意、200 字以内)。"
    "同じ場所と隣の場所へ届く。"
    "報告・相談・呼びかけ・確認は、発話専用のターンを使わずここに書く方が、時間を無駄にしない。"
    "一言には、行動の結果ではなく、これから何をするかを言う。"
    "行動は断られることがあり、結果は次の観測で分かる。空なら発話しない。"
)


def safe_world_intro_text(metadata: ScenarioMetadata, *, has_goal: bool = True) -> str:
    """`description` ではなく、シナリオの `llm_public_intro`（公開導入）を返す。

    未設定（空）のときは汎用 default。``has_goal=False`` (勝敗条件のない永続世界) では
    勝利条件に言及しない中立 default を返す (層2: escape 前提が永続世界に漏れない)。
    """
    custom = (metadata.llm_public_intro or "").strip()
    if custom:
        return custom
    return _DEFAULT_SAFE_INTRO if has_goal else _DEFAULT_NO_GOAL_INTRO


def limited_action_and_time_pressure_text(*, has_goal: bool = True) -> str:
    """
    行動量に上限がある旨のみを述べる（具体的回数はシステム文に埋めない。
    回数はシナリオ・実行時で変わり得るため、必要なら将来ゲーム側の通知に委ねる）。

    ``has_goal=False`` (永続世界) では「使い方を誤ると脱出できない」という escape 固有の
    帰結を落とし、行動量に限りがある事実だけを中立に述べる (層2)。
    """
    if has_goal:
        return (
            "この局面で取りうる自発的な行動（移動・調べる・話す・メモする等）の総量には限りがあり、"
            "使い方を誤ると脱出できない可能性がある（現実世界の時計の分秒とは無関係）。"
            "今後、クライアントから残り行動量や制限の残りが知らされる場合は、それに従うこと。"
        )
    return (
        "この局面で取りうる自発的な行動（移動・調べる・話す・メモする等）の総量には限りがある"
        "（現実世界の時計の分秒とは無関係）。"
        "今後、クライアントから残り行動量や制限の残りが知らされる場合は、それに従うこと。"
    )


def build_persona_block_from_character(
    character: CharacterPromptInput | None,
    *,
    fallback_display_name: str,
    policy: PersonaPromptPolicy | None = None,
) -> str:
    """キャラクター入力からペルソナブロックを生成する。"""
    if character is None:
        return _fallback_persona_block(fallback_display_name)

    traits = list(character.personality_tags)
    samples = [s.strip() for s in character.speech_samples if isinstance(s, str) and s.strip()]
    if samples:
        quoted = " / ".join(f"「{s[:200]}」" for s in samples[:5])
        speech_style = f"次の口調の例に近づける: {quoted}"
    else:
        speech_style = "状況に応じた自然な口調。"

    frag = (character.fragmented_memory or "").strip()
    fragmented: tuple[str, ...] = (frag,) if frag else ()

    values_text = (character.values or "").strip()
    values: tuple[str, ...] = (values_text,) if values_text else ()

    fears_parts: list[str] = []
    w = (character.weaknesses or "").strip()
    if w:
        fears_parts.append(w)

    taboo_parts: list[str] = []
    inter = (character.interpersonal_tendency or "").strip()
    if inter:
        taboo_parts.append(f"対人傾向: {inter[:200]}")

    strengths = (character.strengths or "").strip()
    appearance = (character.appearance or "").strip()
    bg_parts: list[str] = []
    if strengths:
        bg_parts.append(f"長所: {strengths}")
    if appearance:
        bg_parts.append(f"外見: {appearance[:500]}")

    persona = AgentPersonaDto(
        character_id=character.character_id,
        display_name=character.name,
        first_person=(character.first_person or "私").strip() or "私",
        speech_style=speech_style,
        personality_traits=tuple(traits[:12]),
        values=values,
        fears=tuple(fears_parts[:6]) if fears_parts else (),
        taboos=tuple(taboo_parts[:6]) if taboo_parts else (),
        background_summary=" ".join(bg_parts).strip(),
        fragmented_memories=fragmented,
    )
    policy = policy or PersonaPromptPolicy()
    builder = PersonaPromptFragmentBuilder(policy)
    return builder.build(persona)


def _fallback_persona_block(display_name: str) -> str:
    persona = AgentPersonaDto(
        character_id="anonymous",
        display_name=display_name,
        first_person="私",
        speech_style="状況に応じた自然な口調。",
        personality_traits=("慎重", "観察的"),
        values=("まずは生き延びる",),
        fears=(),
        taboos=(),
        background_summary="この局面の探索者として行動する。",
        fragmented_memories=(),
    )
    return PersonaPromptFragmentBuilder(PersonaPromptPolicy()).build(persona)


def build_world_system_prompt(
    *,
    world_title: str,
    persona_block: str,
    safe_intro: str,
    has_goal: bool = True,
    limits_actions: bool = True,
    episode_index_shown: bool = False,
    episode_recall_offered: bool = False,
    say_inline_offered: bool = True,
    imposed_goal: str | None = None,
) -> str:
    """人柄と世界の前提と決まりを案内 (Orientation) に詰めて、``build_world_system_prompt_for`` で組む。

    limits_actions:
        ``False`` なら「行動の制限」の行を出さない。締め切りを置かない世界で、無い制限を
        信じさせないため。既定 ``True`` は従来どおり。
    """
    orientation = world_orientation(
        persona_block=persona_block,
        world_title=world_title,
        intro=safe_intro,
        rules=world_rules(
            has_goal=has_goal,
            action_limit_text=limited_action_and_time_pressure_text(has_goal=has_goal) if limits_actions else None,
            say_inline_offered=say_inline_offered,
        ),
    )
    being_tools = OfferedBeingTools(
        inner_thought=INNER_THOUGHT_FIELD_NAME,
        memo=MEMO_FIELD_NAME,
        episode_recall=TOOL_NAME_EPISODE_RECALL if episode_recall_offered else None,
        episode_index_shown=episode_index_shown,
    )
    return build_world_system_prompt_for(orientation, being_tools=being_tools, imposed_goal=imposed_goal)


def build_world_system_prompt_for(
    orientation: Orientation,
    *,
    being_tools: OfferedBeingTools,
    imposed_goal: str | None = None,
) -> str:
    """作業記憶のシステムプロンプトの区画と同じ組み方で、冒頭の一文、作法、案内、課された目的を並べる。

    作法は Being が、出している道具 (``being_tools``) から作る (#1630)。
    """
    return system_prompt_text(
        WorkingMemory(
            system=WorkingMemory.system_sections(orientation, conduct_text(being_tools), imposed_goal), message=()
        )
    )


def world_rules(
    *, has_goal: bool = True, action_limit_text: str | None = None, say_inline_offered: bool = True
) -> Description:
    """案内のうち、この世界での行動の決まり (#1630)。Being の作法ではなく、環境が決めること。

    has_goal:
        ``True`` (既定/勝敗条件のあるシナリオ) なら「勝利条件・最終目的」前提の文面。
        ``False`` (勝敗のない永続世界 = U5) なら勝敗を否定し、【現在の目的】があれば参照する中立文 (層2)。
    action_limit_text:
        行動量の制限の文。``None`` なら「行動の制限」の行を出さない。
    say_inline_offered:
        出すツールのどれかが ``say_inline`` を持つか (#1940)。``False`` なら一言の書き方を
        書かない。持たない世界で勧めると、エージェントは無い引数を使おうとする。
    """
    if has_goal:
        objective_rule = (
            "- **このシナリオの勝利条件 (最終目的) は、【現在の目的】に記される**。"
            "毎ターン参照し、自分の行動がその目的にどう繋がるかを意識すること。"
            "その他の活動 (探索・物資収集・調査) は全て最終目的のための手段である。"
        )
    else:
        objective_rule = (
            "- この世界に固定された勝敗や達成すべき最終目的はない。"
            "【現在の目的】があれば参照してよいが、"
            "無ければ自分の関心・状況・ペルソナに従って過ごす。"
        )
    lines = [
        f"- ラベル（接続先・オブジェクト・相手プレイヤー等）は、【{CURRENT_SURROUNDINGS_HEADING}】などに表示されたものだけを使う。",
        "- 行動は条件を満たさないと拒否されることがある。各オブジェクトに表示された操作の中から選ぶこと。",
        *((_SAY_INLINE_RULE,) if say_inline_offered else ()),
        objective_rule,
    ]
    if action_limit_text is not None:
        lines.append(f"- 行動の制限: {action_limit_text}")
    return Description(heading=WORLD_RULES_HEADING, text="\n".join(lines))
