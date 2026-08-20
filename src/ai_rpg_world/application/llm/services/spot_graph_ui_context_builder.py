"""スポットグラフ用の UiContextBuilder（ラベル付与 + ToolRuntimeTarget 登録）。

SpotGraphPlayerSnapshotDto の構造化データからエフェメラルラベルを採番し、
LLM が読めるテキスト行と、ツール実行用の ToolRuntimeContextDto を同時に構築する。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.encounter.contracts.interfaces import (
    IEncounterMemory,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    LlmUiContextDto,
    MerchantOfferDto,
    MerchantToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.world_graph.tool_argument_text import (
    quote_tool_argument,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
from ai_rpg_world.application.llm.services.prompt_section_layout import (
    PromptSection,
    sections_for,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.application.llm.services._runtime_target_collector import RuntimeTargetCollector
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    format_action_display_with_hints,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    _render_value,
)
from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
    HEALTH_BUCKET_JP,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.entity.spot_object import VISIBLE_STATE_TAGS_KEY

_logger = logging.getLogger(__name__)


PREFIX_CONNECTION = "S"
PREFIX_OBJECT = "OBJ"
PREFIX_SUB_LOCATION = "SL"
PREFIX_ENTITY = "P"
PREFIX_INVENTORY = "I"
PREFIX_MONSTER = "M"
# 地面アイテム (drop された / 初期配置) のラベル prefix。
# pickup tool が "G1" のような形で対象を指せるようにする。
PREFIX_GROUND_ITEM = "G"
PREFIX_MERCHANT = "MER"


def _current_sub_location_id_from_snapshot(
    snap: SpotGraphPlayerSnapshotDto,
) -> Optional[int]:
    """sub_locations のうち is_current の最初の sub_location_id を返す。

    ドメイン上は is_current は高々 1 件の想定。複数 True の場合は **先頭を採用**（仕様固定。バリデーションは別途検討）。
    """
    for entry in snap.sub_locations:
        if entry.is_current:
            return entry.sub_location_id
    return None


_ORDINAL_SUFFIX_RE = re.compile(r"\s+#\d+$")


def build_ordinal_disambiguator(names: List[str]) -> Dict[int, str]:
    """同名衝突する name に ``#1`` / ``#2`` ... を付与して返す (PR 6, #404 後続)。

    ラベル (S1 / I2 / P3 等) を prompt から外して **名前直接指定** に倒した
    あとに、「灰色のオオカミ」が同 spot に 2 匹いるような場面で LLM が
    どちらを指せばいいか分からなくなる。そのため、同名が複数あるときだけ
    末尾に ``#N`` を付ける (出現順)。1 つしかない名前は素のまま。

    レビュー反映 (#421 LOW): 関数は public な ``build_ordinal_disambiguator``
    として公開する。テスト / 他モジュールから直接利用できる。

    レビュー反映 (#421 MEDIUM): 入力 name が既に ``... #N`` で終わる場合は
    suffix を剥がしてから counts を取り、最終出力で改めて付け直す。
    シナリオ JSON で ``"小屋 #1"`` のような名前が人為的に書かれた場合の
    防御 (実害は低いが、``"小屋 #1 #1"`` のような二重 ordinal を生まない)。

    Args:
        names: 各エントリの display_name。並び順は section の表示順と同じ。

    Returns:
        index → disambiguated_name。``names[i]`` に対応する一意名。

    例:
        ["流木", "オオカミ", "オオカミ", "トラ"]
          → {0: "流木", 1: "オオカミ #1", 2: "オオカミ #2", 3: "トラ"}
    """
    # 既に末尾に "#N" が付いている場合は base name 単位で集計する。
    stripped = [_ORDINAL_SUFFIX_RE.sub("", n) for n in names]
    counts: Dict[str, int] = {}
    for base in stripped:
        counts[base] = counts.get(base, 0) + 1
    out: Dict[int, str] = {}
    seen: Dict[str, int] = {}
    for i, base in enumerate(stripped):
        if counts[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            out[i] = f"{base} #{seen[base]}"
        else:
            out[i] = base
    return out


# 後方互換: 旧名 (PR 6 で導入時は private) を alias として残す。新規呼び出しは
# public 名 ``build_ordinal_disambiguator`` を使うこと。
_build_ordinal_disambiguator = build_ordinal_disambiguator


# 実験 #29 後続: ItemType.value → LLM プロンプト向け日本語タグ。
# 「食料/道具」程度の粒度で区別できれば use_item の誤判断 (ITEM_NOT_CONSUMABLE)
# は減る想定。未知 type は空文字を返して何も表示しない (= silent fallback)。
#
# Issue #785-B: 旧タグの「使用不可」は「何にも使えない」と誤読され、
# 実際には interact の材料である流木・火打ち石まで使われなくなった。
# そのため、全否定語ではなく「食べ物ではない」「どこで使うか」を
# prompt に出す。
_ITEM_TYPE_DISPLAY = {
    "consumable": " (食料)",
    "equipment": " (装備・身につける用途。食べ物ではない)",
    "material": " (素材・そのままは食べられない。焚き火などの材料)",
    "tool": " (道具・そのままは食べられない。近くのものに使う)",
    "key_item": " (重要品・そのままは食べられない。対応する場所やものに使う)",
    "quest": " (任務品・そのままは食べられない。対応する場所やものに使う)",
    "cosmetic": " (装飾品・食べ物ではない)",
    "other": " (食べ物ではない。用途は周囲のオブジェクトや行動で確認)",
}


ITEM_CATEGORY_DISPLAY = {
    "FOOD": " (食料)",
    "MATERIAL": " (素材・そのままは食べられない。焚き火などの材料)",
    "TOOL": " (道具・そのままは食べられない。近くのものに使う)",
    "KEY_ITEM": " (重要品・そのままは食べられない。対応する場所やものに使う)",
    "LORE": " (手がかり・使う物ではない)",
    "DOCUMENT": " (記録・読んで手がかりを得る)",
}

_CONSUMABLE_ITEM_CATEGORY_DISPLAY = {
    "FOOD": " (食料)",
    "KEY_ITEM": " (重要品・そのまま使える)",
}


# PR β (実験 #29 後続): fatigue tier → 仲間表示用の suffix。
# 「ok」「tired」は静かに省略 (ノイズになる)、「fatigued」以上だけ表示。
_FATIGUE_DISPLAY = {
    "fatigued": " (疲れている)",
    "severe": " (ぐったりしている)",
    "exhausted": " (限界。動けず座り込んでいる)",
}


def _format_fatigue_suffix(fatigue_level: str) -> str:
    """疲労 tier → prompt 用の日本語 suffix。fatigued 未満は空文字。"""
    return _FATIGUE_DISPLAY.get(fatigue_level, "")


# P-U3/P-U4 (停滞感の表出): stagnation_band (none/light/strong) → prompt 用
# 文言。バンドごとの文言を 1 箇所に集約する (将来のペルソナ色付けのため)。
# none (前進中) は fatigue の ok/tired と同じく静かに省略する — 前進中に
# 偽の圧を出さないための意図的な非対称。
_STAGNATION_OWN_HINT = {
    "light": "何かが前に進んでいない気がする。",
    "strong": "同じことばかり繰り返している焦りが拭えない。",
}

_STAGNATION_OTHER_DISPLAY = {
    "light": " (何か手詰まりの様子)",
    "strong": " (苛立って落ち着かない様子)",
}


def _format_stagnation_suffix(stagnation_band: str) -> str:
    """停滞感バンド → 他者表示用の日本語 suffix。light 未満は空文字。"""
    return _STAGNATION_OTHER_DISPLAY.get(stagnation_band, "")


# own player 向けの行動ヒント。describe() の数値表記に加えて、操作可能性に
# 直結する情報 (重い tool が block されている / 動きが鈍る) を 1 行足す。
_FATIGUE_OWN_HINT = {
    "fatigued": "動きが鈍くなっている。重い行動は控えめに。",
    "severe": "判断が鈍ってきた。発話も呂律が回らない。早めに休むこと。",
    "exhausted": "疲労が限界。移動も、物への働きかけも、争いもできない。休むか食べるかしないと戻らない。",
}


def _format_item_type_tag(item_type: str) -> str:
    """item_type 文字列値を日本語タグに整形する。

    未知 / 空 / "other" のときは空文字 (タグ非表示)。
    """
    if not item_type:
        return ""
    return _ITEM_TYPE_DISPLAY.get(item_type, "")


def _format_item_category_tag(category: str) -> str:
    """scenario item_specs[].category 由来の prompt 用タグ。

    category は ItemType と別軸の作者分類。未知 / 空なら item_type 由来表示へ
    フォールバックできるよう空文字を返す。
    """
    if not category:
        return ""
    key = str(category).strip().upper()
    if not key:
        return ""
    return ITEM_CATEGORY_DISPLAY.get(key, "")


def _format_consumable_item_category_tag(category: str) -> str:
    """消費可能 item 用の category 表示。

    category は物語上の分類で、消費可能性とは別軸。消費できる item に
    非消費品向けの「食べられない」「interact して使う」を出さない。
    """
    if not category:
        return ""
    key = str(category).strip().upper()
    if not key:
        return ""
    return _CONSUMABLE_ITEM_CATEGORY_DISPLAY.get(key, "")


def _format_item_usage_hint(usage_hint: str) -> str:
    """ItemSpec の作者文による用途ヒントを所持品行向けに整形する。

    ここでは HAS_ITEM 条件から具体 spot / object を機械導出しない。渡された
    作者文だけを表示し、空なら何も出さない。
    """
    text = str(usage_hint or "").strip()
    if not text:
        return ""
    return f" (用途: {text})"


def _format_inventory_item_mark(
    *,
    usage_hint: str,
    category: str,
    item_type: str,
) -> str:
    """所持品の用途・種別表示を usage_hint > category > item_type の順に決める。"""
    usage_mark = _format_item_usage_hint(usage_hint)
    if usage_mark:
        return usage_mark
    if item_type == "consumable":
        consumable_category_mark = _format_consumable_item_category_tag(category)
        if consumable_category_mark:
            return consumable_category_mark
        return _format_item_type_tag(item_type)
    category_mark = _format_item_category_tag(category)
    if category_mark:
        return category_mark
    return _format_item_type_tag(item_type)


def _format_inventory_item_contract_mark(
    *,
    category: str,
    item_type: str,
) -> str:
    """作者説明があっても、別の案内文が参照する分類表示を残す。

    ``(食料)`` は ITEM_NOT_CONSUMABLE の対処文と consume_item の説明が
    選択目印として参照する。LORE / DOCUMENT も interact の対象ではない
    ことを伝える安全上の契約なので、作者の散文で置き換えない。
    """
    if item_type == "consumable":
        return _format_consumable_item_category_tag(
            category
        ) or _format_item_type_tag(item_type)
    if str(category or "").strip().upper() in ("LORE", "DOCUMENT"):
        return _format_item_category_tag(category)
    return ""


def _format_object_state(state: Dict[str, Any]) -> str:
    """SpotGraphObjectEntry.visible_state を prompt 表示用の tag に整形。

    PR-X (Y_after_pr639_640 後続): 空 dict → 空文字。1 個以上のエントリ
    があれば `` (key=value, key2=value2)`` の形式で prepend する。
    ただし ``SpotObject.visible_state()`` が内部キー ``__tags__`` で返す
    可用性ヒントは、LLM に key を見せず裸のタグとして表示する。

    値の変換は ``spot_graph_current_state_formatter._render_value`` に
    委譲する (bool→lowercase、None→"null"、その他 primitive→str)。
    formatter 側の旧 "スポット内オブジェクトの状態:" block と同じ
    convention を保つことで、LLM が「どちらの format が正しいか」で
    迷うのを避ける (旧 block は本 PR で削除、この inline 形式に一本化)。

    key の順序: 挿入順 (dict の insertion order)。同一 tick 内では domain
    側の visible_state() 出力順に依存するため、実質的に安定している。

    例:
      {}                             → ""
      {"__tags__": ("今は採れない・時間を置けば戻る",)} → " (今は採れない・時間を置けば戻る)"
      {"opened": True, "count": 0}   → " (opened=true, count=0)"
      {"latch": None}                → " (latch=null)"
    """
    if not state:
        return ""
    parts: List[str] = []
    for key, value in state.items():
        if key == VISIBLE_STATE_TAGS_KEY:
            if isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if str(v))
            elif value:
                parts.append(str(value))
            continue
        parts.append(f"{key}={_render_value(value)}")
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


def _format_action_with_hints(interaction: Any, *, hints_attribute: str) -> str:
    """display_label・action_name・表示専用ヒントを一続きに整形する。

    ToolRuntimeTargetDto.available_interactions には action_name だけを渡すため、
    ここで作る文字列は prompt 表示専用。
    """
    action_name = str(getattr(interaction, "action_name", ""))
    display_label = str(getattr(interaction, "display_label", "") or "").strip()
    hints = tuple(getattr(interaction, hints_attribute, ()) or ())
    return format_action_display_with_hints(
        action_name,
        hints,
        display_label=display_label,
    )


def _format_action_name_with_condition_hints(interaction: Any) -> str:
    """選べる action を意味ラベル・識別子・条件ヒントの順に整形する。"""
    return _format_action_with_hints(
        interaction,
        hints_attribute="condition_hints",
    )


#: 板に相手が居ないときの表示。**「できない」と書かない。**
#:
#: 以前は「売れない (買い注文なし)」「買えない (出品なし)」と書いていた。実 run で
#: 焼き手が「掲示板にはパンの買い注文がないから、手持ちのパンを売っても買い手が
#: つかない」と**売る可能性を検討したうえで棄却**している。しかし出品は買い注文の
#: 有無と関係なく、**買い手を待つ行為**である。66 手番にわたり全員へ「売れない」と
#: 表示し続け、板の前でパンを 2 つ以上持っていた手番が 16 回あった。**出品は
#: 起こりえた。起きなかったのは表示のせい。**
#:
#: 買い側も同じ形なので同時に直す (`market_bid` は 2 つの run で 0 回)。
_NO_BIDS = "買い注文なし (出品して待てる)"
_NO_LISTINGS = "出品なし (買い注文を出して待てる)"


#: 職能や世界の状態で、その人には操作が 1 つも残らなかったときの注記。
#: **engine は理由を推測しない。** 落ちた理由は職能とは限らず、世界の状態の
#: こともある。推測すると別の嘘になる。
#:
#: シナリオが「その属性は変えられない」と宣言していれば、この文の代わりに
#: ``<値の呼び名>だけが扱える`` が入る (`unreachable_attribute_notes`)。
#: **推測ではなく作者が書いた語**なので、上の規律とは両立する。宣言が
#: 無ければここへ落ちる。
_NOTHING_FOR_THIS_ACTOR = "いまのあなたに扱える操作はない"


def _format_blocked_action_name_with_hints(interaction: Any) -> str:
    """いまできない action を意味ラベル・識別子・理由の順に整形する。"""
    return _format_action_with_hints(
        interaction,
        hints_attribute="blocking_hints",
    )


#: これより暗いと物が見えない。``spot_perception_service`` の判定と揃える。
_UNSEEABLE_LIGHTING = frozenset({"DARK", "PITCH_BLACK"})


def _is_too_dark_to_see(snap: Any) -> bool:
    """明るさのせいで物が見えない状態か。

    **「何も無い」と「見えない」を区別するためだけに使う。** 見え方そのものの
    判定は snapshot を組む側が済ませており、ここではその結果を読むだけ。
    """
    atmosphere = getattr(snap, "atmosphere", None)
    lighting = getattr(atmosphere, "lighting", None) if atmosphere else None
    key = getattr(lighting, "value", lighting)
    return str(key) in _UNSEEABLE_LIGHTING


class SpotGraphUiContextBuilder(ILlmUiContextBuilder):
    """スポットグラフのスナップショットにラベルを付与する UiContextBuilder。

    PR4 (Encounter Memory): ``encounter_memory`` / ``current_tick_provider`` /
    ``spot_str_id_resolver`` を optional に受け取る。3 つ揃っていれば「現在地」
    と「同じ場所にいるプレイヤー」line に familiarity 注記 (= ``(初めて訪れた)``
    / ``(初めて会った)``) を付ける。1 つでも欠ければ既存挙動と完全に同じ
    (= 後方互換)。
    """

    def __init__(
        self,
        *,
        encounter_memory: Optional[IEncounterMemory] = None,
        current_tick_provider: Optional[Callable[[], int]] = None,
        spot_str_id_resolver: Optional[Callable[[int], str]] = None,
    ) -> None:
        if encounter_memory is not None and not isinstance(
            encounter_memory, IEncounterMemory
        ):
            raise TypeError(
                "encounter_memory must be IEncounterMemory or None"
            )
        if current_tick_provider is not None and not callable(
            current_tick_provider
        ):
            raise TypeError("current_tick_provider must be callable or None")
        if spot_str_id_resolver is not None and not callable(
            spot_str_id_resolver
        ):
            raise TypeError("spot_str_id_resolver must be callable or None")
        self._encounter_memory = encounter_memory
        self._current_tick_provider = current_tick_provider
        self._spot_str_id_resolver = spot_str_id_resolver

    @staticmethod
    def _phase_of(current_state: Optional[PlayerCurrentStateDto]) -> GamePhase:
        """いまのフェーズ。分からなければ自由時間。

        snapshot に載っていない経路 (テスト用の直接構築など) の挙動を
        変えないため。**会議中なのに自由時間と誤ると使えない対象が並ぶ**
        ので、載せるのは runtime の責務。
        """
        phase = getattr(current_state, "game_phase", None)
        return phase if isinstance(phase, GamePhase) else GamePhase.FREE_ROAM

    def build(
        self,
        current_state_text: str,
        current_state: Optional[PlayerCurrentStateDto],
    ) -> LlmUiContextDto:
        if current_state is None or current_state.spot_graph_snapshot is None:
            return LlmUiContextDto(
                current_state_text=current_state_text,
                tool_runtime_context=ToolRuntimeContextDto.empty(),
            )

        snap = current_state.spot_graph_snapshot
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        extra_lines: List[str] = []

        if getattr(snap, "viewer_is_departed", False):
            extra_lines.extend(
                (
                    "【いまの存在状態】",
                    "あなたは死亡した後も世界に留まっている。生きている者には"
                    "姿が見えず、声も届かない。死亡した者同士は互いを見聞きできる。"
                    "移動と許された点検作業は続けられ、変えた物の状態は生者とも共有される。",
                )
            )

        viewer_player_id: Optional[PlayerId] = None
        if current_state.player_id is not None:
            try:
                viewer_player_id = PlayerId(int(current_state.player_id))
            except Exception:
                viewer_player_id = None

        # どの節をどの順で出すかは prompt_section_layout が持つ。
        # **ここで is_meeting を見ない。** ビルダごとに分岐を書くと、節を
        # 1 つ足した人が忘れる (死の観測・ツールの出し分けで踏んだ形)。
        builders = {
            PromptSection.CONNECTIONS: lambda: self._build_connection_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.OBJECTS: lambda: self._build_object_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.SUB_LOCATIONS: lambda: self._build_sub_location_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.ENTITIES_WITH_ACTIONS: lambda: self._build_entity_section(
                snap, allocator, collector, extra_lines, viewer_player_id
            ),
            PromptSection.ENTITIES_PLAIN: lambda: self._build_entity_section(
                snap, allocator, collector, extra_lines, viewer_player_id,
                with_actions=False,
            ),
            PromptSection.MONSTERS: lambda: self._build_monster_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.MERCHANTS: lambda: self._build_merchant_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.MARKET_BOARD: lambda: self._build_market_section(
                snap, extra_lines
            ),
            PromptSection.GOLD: lambda: self._build_gold_section(snap, extra_lines),
            PromptSection.TRADE_OFFERS: lambda: self._build_trade_offer_section(
                snap, extra_lines
            ),
            PromptSection.INVENTORY: lambda: self._build_inventory_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.GROUND_ITEMS: lambda: self._build_ground_items_section(
                snap, allocator, collector, extra_lines
            ),
            PromptSection.NEEDS: lambda: (
                None
                if getattr(snap, "viewer_is_departed", False)
                else self._build_needs_section(snap, extra_lines)
            ),
            PromptSection.ACTIVE_EFFECTS: lambda: self._build_active_effects_section(
                snap, extra_lines
            ),
            PromptSection.AGENT_STATUS: lambda: self._build_agent_status_section(
                snap, extra_lines
            ),
        }
        for section in sections_for(self._phase_of(current_state)):
            builders[section]()

        # PR4: 「現在地」行に spot familiarity 注記を埋め込む。
        annotated_current_state_text = self._annotate_current_spot_familiarity(
            current_state_text, snap, viewer_player_id
        )

        augmented_text = annotated_current_state_text
        if extra_lines:
            augmented_text = (
                annotated_current_state_text.rstrip()
                + "\n"
                + "\n".join(extra_lines)
            )

        return LlmUiContextDto(
            current_state_text=augmented_text,
            tool_runtime_context=ToolRuntimeContextDto(
                targets=collector.get_targets(),
                dark_hidden_object_names=snap.dark_hidden_object_names,
                current_spot_id=snap.current_spot_id,
                current_sub_location_id=_current_sub_location_id_from_snapshot(snap),
            ),
        )

    # ────────────────────────────────────────────────────────
    # Familiarity helpers (PR4)
    # ────────────────────────────────────────────────────────

    def _annotate_current_spot_familiarity(
        self,
        current_state_text: str,
        snap: SpotGraphPlayerSnapshotDto,
        viewer_player_id: Optional[PlayerId],
    ) -> str:
        """「現在地: 〇〇」 line に ``(初めて訪れた)`` 等の familiarity 注記を
        追加する。encounter 注入が無い場合や lookup 失敗時は原文をそのまま返す。
        """
        if not self._encounter_enabled() or viewer_player_id is None:
            return current_state_text
        if snap.current_spot_id is None:
            return current_state_text
        annotation = self._spot_familiarity_annotation(
            viewer_player_id, snap.current_spot_id
        )
        if annotation is None:
            return current_state_text
        # 「現在地: <name>」line を find & 1 行だけ差し替える。description は触らない。
        # str.replace で部分一致させると、spot 名が description や他 line の
        # 部分文字列として現れたときに誤置換する。完全一致の行を探すため
        # split-join 経由で 1 行単位に絞る。
        spot_name = snap.current_spot_name or ""
        target_line = f"現在地: {spot_name}"
        replacement = f"{target_line} {annotation}"
        lines = current_state_text.split("\n")
        for i, line in enumerate(lines):
            if line == target_line:
                lines[i] = replacement
                return "\n".join(lines)
        return current_state_text

    def _spot_familiarity_annotation(
        self,
        viewer_player_id: PlayerId,
        spot_int_id: int,
    ) -> Optional[str]:
        try:
            spot_str_id = self._spot_str_id_resolver(spot_int_id)  # type: ignore[misc]
        except Exception:
            _logger.exception(
                "spot_str_id_resolver failed (spot_id=%s)", spot_int_id
            )
            return None
        try:
            record = self._encounter_memory.lookup(  # type: ignore[union-attr]
                viewer_player_id, EncounterKey.spot(spot_str_id)
            )
        except Exception:
            _logger.exception(
                "encounter_memory.lookup failed (spot=%s)", spot_str_id
            )
            return None
        if record is None:
            return None
        if record.is_first:
            return "(初めて訪れた)"
        return None

    def _player_familiarity_annotation(
        self,
        viewer_player_id: Optional[PlayerId],
        target_display_name: str,
    ) -> Optional[str]:
        if not self._encounter_enabled() or viewer_player_id is None:
            return None
        if not target_display_name:
            return None
        try:
            record = self._encounter_memory.lookup(  # type: ignore[union-attr]
                viewer_player_id, EncounterKey.player(target_display_name)
            )
        except Exception:
            _logger.exception(
                "encounter_memory.lookup failed (player=%s)",
                target_display_name,
            )
            return None
        if record is None:
            # まだ encounter が立っていない (= observation 未到達) なら注記しない
            return None
        if record.is_first:
            return "(初めて会った)"
        return None

    def _encounter_enabled(self) -> bool:
        return (
            self._encounter_memory is not None
            and self._current_tick_provider is not None
            and self._spot_str_id_resolver is not None
        )

    def _build_connection_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        # PR 6 (#404 後続): 旧 "S1: 扉 → 館長書斎" → "扉 → 館長書斎" に簡略化。
        # 同名スポット (= 異なる接続だが行き先 spot が同名) は ``#N`` で
        # 区別する。LLM は destination_label に行き先 spot 名そのものを渡せば
        # resolver が解決する。
        #
        # note: ``label`` 変数は prompt には出さないが、collector の dict key
        # として引き続き必要 (resolver の旧経路と互換)。allocator.next を呼ぶ
        # 副作用 (連番採番) も他 section と整合させるため維持している。
        if not snap.connections:
            return
        lines.append("接続先:")
        dest_names = [e.destination_spot_name for e in snap.connections]
        disamb = _build_ordinal_disambiguator(dest_names)
        for i, entry in enumerate(snap.connections):
            label = allocator.next(PREFIX_CONNECTION)
            disambiguated_name = disamb[i]
            if entry.is_passable:
                status = "通行可"
            elif entry.passage_condition_text:
                status = f"通行不可 — {entry.passage_condition_text}"
            else:
                status = "通行不可"
            lines.append(
                f"  - {quote_tool_argument(entry.connection_name)} → "
                f"{quote_tool_argument(disambiguated_name)}（{status}）"
            )
            collector.add(
                label,
                DestinationToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_destination",
                    display_name=disambiguated_name,
                    spot_id=entry.destination_spot_id,
                    destination_type="spot",
                ),
            )
            # shadow entry: edge 名 (connection_name) でも引けるよう同 spot を
            # 別 label で登録する。LLM が誤って edge 名を渡しても resolver が
            # destination spot に飛ばす silent rescue。``list_destination_labels``
            # は ``__edge_`` prefix で除外するのでユーザ向け候補列挙には出ない。
            shadow_label = f"__edge_{label}"
            collector.add(
                shadow_label,
                DestinationToolRuntimeTargetDto(
                    label=shadow_label,
                    kind="spot_graph_destination",
                    display_name=entry.connection_name,
                    spot_id=entry.destination_spot_id,
                    destination_type="spot",
                ),
            )

    def _build_object_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        # PR 6 (#404 後続): "OBJ1: 焚き火跡 ..." → "焚き火跡 ..."。
        # 同 spot に同名 object が複数ある場合 (例: 茂み x2) は ``#N`` で区別。
        if not snap.objects:
            # **無いことを明示する。** 節ごと消すと、LLM は「節が無い = 何も
            # 無い」と推論するしかない。同席者とモンスターの節は #283 後続で
            # 既にこの形に直してあり、**オブジェクトだけ漏れていた**。
            #
            # さらに悪いことに、ここでは「何も無い」と「暗くて見えない」と
            # いう**別の事実が同じ沈黙に潰れていた**。実 run 010 でハギは
            # 「照明が落ちてるから、もっと調べないと見つからないのか」と
            # 推測し、explore と listen に手番を溶かした。
            lines.append(
                "オブジェクト: (暗くて何も見えない。灯りが要る)"
                if _is_too_dark_to_see(snap)
                else "オブジェクト: (ここには何も無い)"
            )
            return
        lines.append("オブジェクト:")
        if _is_too_dark_to_see(snap):
            # **一覧が空でなくても、暗さは隠している。** 暗所でも見えるよう
            # 宣言された物 (非常用ランタンケース・通気口) が 1 つでもあると
            # 一覧は空にならないが、他の物は依然として暗さで消えている。
            # ここを空のときだけの分岐にしていたため、「見えている物が全部だ」と
            # 読める状態になっていた。実 run 010 の explore / listen への
            # 手番浪費と同じ形を作り直すところだった。
            lines.append("  (暗い。灯りがなければ、見えるのはこれだけ)")
        obj_names = [e.name for e in snap.objects]
        disamb = _build_ordinal_disambiguator(obj_names)
        for i, entry in enumerate(snap.objects):
            label = allocator.next(PREFIX_OBJECT)
            disambiguated_name = disamb[i]
            # action は意味を示す display_label と tool に渡す action_name を
            # 対にして表示する。前提条件ヒントも同じ括弧内へ中黒で連ねる。
            action_names: list[str] = [inter.action_name for inter in entry.interactions]
            action_labels: list[str] = [
                _format_action_name_with_condition_hints(inter)
                for inter in entry.interactions
                if not tuple(getattr(inter, "blocking_hints", ()) or ())
            ]
            blocked_action_labels: list[str] = [
                _format_blocked_action_name_with_hints(inter)
                for inter in entry.interactions
                if tuple(getattr(inter, "blocking_hints", ()) or ())
            ]
            # 職能や世界の状態で操作がすべて落ちた物体は、**角括弧ごと
            # 消える**。ところが system prompt は「表示された操作の中から
            # 選べ」と指示しているので、**表示が 1 つも無いのに選べと
            # 言われた**エージェントは動詞を発明する (実 run の
            # INTERACTION_ACTION_NOT_FOUND の全件がこの形だった)。
            # 時間で戻らないことは既に注記されているのに、職能だけ
            # 注記が無かった。**非対称を消す。**
            if action_labels:
                act_str = f" [{', '.join(action_labels)}]"
            elif getattr(entry, "has_role_hidden_interactions", False):
                # **注記が出る行は増やさない。** 出る位置は従来と同じで、
                # 中身が「永久に届かない」と分かっているときだけ具体に
                # なる。ここを別の分岐にすると、いままで注記の無かった行に
                # 注記が生えて、run の差分の出どころが分からなくなる。
                notes = tuple(
                    getattr(entry, "unreachable_attribute_notes", ()) or ()
                ) or (_NOTHING_FOR_THIS_ACTOR,)
                act_str = f" [{'、'.join(notes)}]"
            else:
                act_str = ""
            desc_part = f" — {entry.description}" if entry.description else ""
            # PR-X (Y_after_pr639_640 後続): visible state を prompt に露出。
            # {'available': False} のような state は原因準拠の再利用待ち
            # ヒントとして LLM に見え、PRECONDITION_FAILED ループを避けられる。
            state_part = _format_object_state(entry.state)
            # PR-FF (Y_after_pr639_640 後続): object 名を ``""`` で囲む
            # (PR #639/#640 で導入した quote 規約を全 section に拡張)。
            lines.append(
                f"  - \"{disambiguated_name}\"{state_part}{desc_part}{act_str}"
            )
            if blocked_action_labels:
                lines.append(f"      いまできない: {'、'.join(blocked_action_labels)}")
            # 世界に操作が無い物体は情景にだけ残す。一方、行為者の伏せた条件で
            # 操作名がすべて落ちた物体は対象として解決する。物体まで落とすと、
            # 目の前に在るのに「この場所に無い」という偽の失敗へ変わる。
            # available_interactions は引き続き公開 action_name だけなので、
            # 偽装版などの名前は漏れない。
            if action_names or entry.has_actor_hidden_interactions:
                collector.add(
                    label,
                    ToolRuntimeTargetDto(
                        label=label,
                        kind="spot_graph_object",
                        display_name=disambiguated_name,
                        world_object_id=entry.object_id,
                        available_interactions=tuple(action_names),
                    ),
                )

    def _build_sub_location_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        # PR 6 (#404 後続): "SL1: 祭壇前" → "祭壇前"。同名衝突は ``#N`` で区別。
        visible_subs = [s for s in snap.sub_locations if not s.is_hidden]
        if not visible_subs:
            return
        lines.append("サブロケーション:")
        sub_names = [e.name for e in visible_subs]
        disamb = _build_ordinal_disambiguator(sub_names)
        for i, entry in enumerate(visible_subs):
            label = allocator.next(PREFIX_SUB_LOCATION)
            disambiguated_name = disamb[i]
            here = "（現在ここ）" if entry.is_current else ""
            # PR-FF: sub_location 名を ``""`` で囲む (quote 規約の拡張)
            lines.append(f"  - \"{disambiguated_name}\"{here}")
            collector.add(
                label,
                ToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_sub_location",
                    display_name=disambiguated_name,
                    sub_location_id=entry.sub_location_id,
                ),
            )

    def _build_entity_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
        viewer_player_id: Optional[PlayerId] = None,
        *,
        with_actions: bool = True,
    ) -> None:
        """同じ場所にいる他プレイヤーを列挙する。

        ``with_actions=False`` は会議中の形。名前と生死だけを出し、行動と
        受け渡しの案内は落とす。**会議中はどちらも選べない。** 誰に投票
        できるかを読む手がかりとしては、名前と生死で足りる。

        Issue #283 後続の五感対称化: 旧実装は「居れば列挙、居なければ section
        ごと省略」だったため、LLM は「section 無し = 誰もいない」を暗黙推論
        するしかなく、結果として speech を「相手がここに居るか分からない」
        まま使う事故が起きていた (R1 カイトの SHOUT 誤用)。情報提示を
        対称にし、「他者がいない」事実も明示する。
        """
        if not snap.nearby_entities:
            lines.append("同じ場所にいるプレイヤー: (他のプレイヤーはこのスポットにいない)")
            return
        # PR 6 (#404 後続): "P1: リン" → "リン"。同名 player は scenario で
        # 避ける運用だが、防御的に ``#N`` 区別を入れておく。
        # 案内はツールが在る世界でだけ書く。無い世界で勧めると、選べない
        # 手段を勧めることになる。
        if with_actions and getattr(snap, "can_give_item", True):
            lines.append(
                "同じ場所にいるプレイヤー: "
                "(倒れていない相手には give_item で所持品を直接渡せる)"
            )
        elif with_actions:
            lines.append("同じ場所にいるプレイヤー:")
        else:
            lines.append("この場に居る人:")
        entity_names = [
            (e.display_name or f"プレイヤー({e.entity_id})")
            for e in snap.nearby_entities
        ]
        disamb = _build_ordinal_disambiguator(entity_names)
        for i, entry in enumerate(snap.nearby_entities):
            label = allocator.next(PREFIX_ENTITY)
            disambiguated_name = disamb[i]
            if getattr(entry, "is_own_fallen_body", False):
                # 自分の身体は世界に残っている事実として見せるが、tool の
                # target には登録しない。幽霊本人が自分を通報・略奪する候補を
                # 作らないため、通常行より先に完結させる。
                lines.append(f'  - "{disambiguated_name}" (あなたの亡骸)')
                continue
            # PR #347 後続: 倒れている相手は (倒れて動かない) を後置して、
            # speech / 受け渡しの対象として動かないことを LLM が認識できるよう
            # にする。OFF mode で過去の PlayerDownedEvent が観測 buffer から
            # 流れた後でも、snapshot から「あの人が床に転がっている」が読める。
            # 死亡 (終局・復活不可) は蘇生可能なダウンと明確に区別する。
            # is_dead を最優先し、婉曲でなく「死亡している」と直接的に出す
            # (LLM が小さな語を読み落として蘇生を試み続けないように)。
            is_dead = getattr(entry, "is_dead", False)
            if is_dead:
                suffix = " (死亡している)"
            elif entry.is_down:
                suffix = " (倒れて動かない)"
            else:
                suffix = ""
            # PR β (実験 #29 後続): 仲間の疲労状態を Observation でなく
            # state として常時表示する。死亡 / is_down 優先、それ以外で疲労を出す。
            if not is_dead and not entry.is_down:
                fatigue_suffix = _format_fatigue_suffix(entry.fatigue_level)
                # P-U4 (停滞感の表出・他者): fatigue と併存させる。ゲージ値は
                # 見せず、バンドに応じた様子の suffix だけを足す。
                stagnation_suffix = _format_stagnation_suffix(entry.stagnation_band)
                suffix = fatigue_suffix + stagnation_suffix
            # 行動不能 (死亡 / ダウン) の相手が持っているものを見せる。
            #
            # 実 run では、山頂で倒れた仲間が狼煙に要る流木を持ったままで、
            # それが見えないまま救助に失敗した。「誰が何を持ったまま倒れて
            # いるのか」が読めれば、起こしに行くか荷を引き受けるかを選べる。
            #
            # 何も持っていない場合も明示する。表示が無いだけだと「持っていない」
            # のか「見えていない」のか区別がつかず、確かめるために 1 ターン
            # 無駄にする。
            #
            # 起きて動いている相手には出さない。常時見えると窃盗が作業になり、
            # 奪う前に倒す必要が生まれる形の方が筋が良い (ユーザ確定)。
            carried_suffix = ""
            if is_dead or entry.is_down:
                carried = tuple(getattr(entry, "carried_item_names", ()) or ())
                carried_suffix = (
                    f" 〔{'、'.join(carried)}〕" if carried else " 〔手ぶら〕"
                )
            # PR4 (Encounter Memory): familiarity 注記 (= 「初めて会った」)。
            # display_name (= 表示名 / 安定名) で encounter を引く。is_down /
            # fatigue suffix と併存させたいので suffix の後に追加する。
            familiarity = self._player_familiarity_annotation(
                viewer_player_id, entry.display_name or ""
            )
            familiarity_suffix = f" {familiarity}" if familiarity else ""
            # PR-FF: 他プレイヤー名を ``""`` で囲む (quote 規約の拡張)。
            # whisper / give_item / tend_to_player の target_label 系で
            # 「``""`` 内が渡すべき値」規約を満たす。
            # 人を対象にできる action を、物体行の ``[gather, examine]`` と
            # 同じ書式で出す。ここを出さないと、対人行為を実装しても LLM から
            # は発見できない (宣言はあるのに一度も使われない)。
            #
            # 前提条件の成否は実行時に決まるので、ここでは候補としてだけ出す。
            # 物体行が「今は使えない action も並べる」のと同じ扱い。
            # **その相手にいま使える** action だけを出す。snapshot 単位の
            # 1 本のタプルだと全員の行に同じ一覧が並び、倒れている相手にしか
            # 使えない take が立っている相手の行にも出る (v4 第 3 回 run で
            # take 16 回全失敗の原因)。
            # 会議中は行動を付けない。選べない手を並べると、#860 で潰した
            # 「選べるのに必ず失敗する」形に戻る。
            player_actions = (
                tuple(getattr(entry, "action_entries", ()) or ())
                if with_actions
                else ()
            )
            available_action_labels = [
                _format_action_name_with_condition_hints(interaction)
                for interaction in player_actions
                if not tuple(getattr(interaction, "blocking_hints", ()) or ())
            ]
            blocked_action_labels = [
                _format_blocked_action_name_with_hints(interaction)
                for interaction in player_actions
                if tuple(getattr(interaction, "blocking_hints", ()) or ())
            ]
            action_suffix = (
                f" [{', '.join(available_action_labels)}]"
                if available_action_labels
                else ""
            )
            lines.append(
                f"  - \"{disambiguated_name}\""
                f"{suffix}{carried_suffix}{familiarity_suffix}"
                f"{action_suffix}"
            )
            if blocked_action_labels:
                lines.append(
                    f"      いまできない: {'、'.join(blocked_action_labels)}"
                )
            collector.add(
                label,
                PlayerToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_player",
                    display_name=disambiguated_name,
                    player_id=entry.entity_id,
                ),
            )

    def _build_monster_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        """同スポットに居るモンスター個体に M1, M2, ... を割り当てる。

        ラベルは揮発（既存パターン踏襲）。LLM がターンを跨いで個体を追跡したい
        場合は description / 名前から再特定する想定で、ここでは安定ハンドルを
        用意しない。戦闘ツールが導入された時に再評価する。

        死体は生存個体と同じ section に並べるが、表記とラベル説明文を分ける。
        現状では戦闘ツールがまだ無いため `available_interactions` は空。次の
        戦闘 PR で attack 等が実装された時点で埋める。

        Issue #283 後続: 空のときも明示する (五感の対称化)。
        """
        if not snap.monsters_at_spot:
            lines.append("同じ場所に居るモンスター: (このスポットにモンスターはいない)")
            return
        # PR 6 (#404 後続): "M1: 灰色のオオカミ" → "灰色のオオカミ"。
        # 同種が複数いる定番ケース (オオカミ 2 匹 等) は ``#N`` で区別する。
        # LLM が attack target_label に "灰色のオオカミ #2" を渡せば 2 番目に
        # 解決される。
        lines.append("同じ場所に居るモンスター:")
        monster_names = [e.display_name for e in snap.monsters_at_spot]
        disamb = _build_ordinal_disambiguator(monster_names)
        for i, entry in enumerate(snap.monsters_at_spot):
            label = allocator.next(PREFIX_MONSTER)
            disambiguated_name = disamb[i]
            if entry.is_dead:
                desc = "死骸"
            else:
                health_label = HEALTH_BUCKET_JP.get(
                    entry.health_bucket, entry.health_bucket
                )
                desc = f"{entry.behavior_label}・{health_label}"
            # PR-FF: モンスター名を ``""`` で囲む (attack target_label が
            # 「``""`` 内が渡すべき値」規約を満たす)。
            lines.append(f"  - \"{disambiguated_name}\"（{desc}）")
            appearance = str(getattr(entry, "appearance", "") or "").strip()
            if appearance:
                lines.append(f"    見た目: {appearance}")
            collector.add(
                label,
                MonsterToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_monster",
                    display_name=disambiguated_name,
                    monster_id=entry.monster_id,
                ),
            )

    @staticmethod
    def _build_needs_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        hp_line = getattr(snap, "hp_line", "") or ""
        if not snap.need_lines and not hp_line:
            return
        lines.append("身体の状態:")
        # HP は本人が真っ先に読むべき生存情報なので need より先に出す。
        if hp_line:
            lines.append(f"  {hp_line}")
        for line in snap.need_lines:
            lines.append(f"  {line}")
        # PR β (実験 #29 後続): own player の疲労 tier に応じた行動ヒント。
        # describe() は数値 + 5 段階のテキストだけなので、ここで「重い行動が
        # block されている / 動きが鈍くなる」のような操作可能性に直結する
        # 情報を 1 行足す。system prompt は変えず state section にだけ載せる
        # 設計 (docs/design_decisions.md #1 / #8)。
        # 旧実装は ``snap.player_state.get("fatigue_level")`` を読んでいたが
        # ``player_state`` は ``dict(player.state)`` (自由 state) しか乗らず、
        # ``fatigue_level`` は常に None で hint が一度も出ない silent failure に
        # なっていた (Y_after_pr607 観察)。専用 field ``own_fatigue_level`` から
        # 読むことで「exhausted で travel / attack / interact が block される」
        # 等の情報が agent の prompt に到達するようにする。
        fatigue_level = getattr(snap, "own_fatigue_level", "ok") or "ok"
        hint = _FATIGUE_OWN_HINT.get(fatigue_level)
        if hint:
            lines.append(f"  → {hint}")
        # P-U3 (停滞感の表出・自己): fatigue hint と同じ形式で 1 行足す。
        # none (前進中) では何も出さない (fatigue の ok/tired と同じ扱い)。
        stagnation_band = getattr(snap, "own_stagnation_band", "none") or "none"
        stagnation_hint = _STAGNATION_OWN_HINT.get(stagnation_band)
        if stagnation_hint:
            lines.append(f"  → {stagnation_hint}")

    @staticmethod
    def _build_active_effects_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        """PR #2 状態異常: 適用中の effect を「現在の状態異常:」section として surface。

        LLM が「出血している → bandage を探す」のような行動連鎖を取れるよう、
        身体の状態 (needs) とは分けたセクションで提示する。effects が空のとき
        は section ごと出さない (LLM の注意を空 list で散らさない)。
        """
        if not snap.active_effect_lines:
            return
        lines.append("現在の状態異常:")
        for line in snap.active_effect_lines:
            lines.append(f"  {line}")

    @staticmethod
    def _build_agent_status_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        """multi-tick busy 状態を「現在の行動状態:」section として surface。

        LLM が「自分は今移動中だから interact しても無意味」を理解できるように、
        busy の理由・残り tick・中断可能性を明示する。busy=False (= rest 状態)
        の場合は section を出さない (= 通常の "何でも行動できる" 状態)。
        """
        st = snap.agent_status
        if not st.busy:
            return
        lines.append("現在の行動状態:")
        reason = st.busy_reason or "進行中"
        lines.append(f"  {reason} (残り {st.remaining_ticks} tick)")
        if st.interruptible:
            lines.append(
                "  ※ 軽い行動 (発話 / memo / 観察) は並行して取れる。"
                "重い行動 (別の移動 / 物への働きかけ / 道具の使用 / 争い) を"
                "選ぶと現在の行動は中断され、その場で停止する。"
            )

    @staticmethod
    def _build_merchant_section(
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        """現在地に居る NPC 商人を「商人:」section として surface する。

        商人を宣言していない世界では 1 行も出さない。その世界には商人という
        概念が無く、不在を明示すると既存シナリオの prompt が変わって過去 run
        との比較可能性が切れるため。

        宣言した世界では、居ない spot でも不在を明示する。黙って節を消すと
        「ここには居ない」と「まだ見つけていない」が同じ沈黙に潰れ、商人を
        探して手番を溶かす (オブジェクト節で実際に起きた形)。
        """
        if not snap.economy_declared:
            return
        if not snap.merchants_at_spot:
            lines.append("商人: (この場所には居ない)")
            return
        lines.append("商人:")
        for merchant in snap.merchants_at_spot:
            lines.append(f"  - \"{merchant.name}\"")
            # 売買ツールが「品名 → どの商人か」を引けるよう、扱う品ごと
            # 対象として積む。ラベルはプロンプトに出さない (商人は名前で指す)。
            label = allocator.next(PREFIX_MERCHANT)
            collector.add(
                label,
                MerchantToolRuntimeTargetDto(
                    label=label,
                    kind="merchant",
                    display_name=merchant.name,
                    merchant_id=merchant.merchant_id,
                    sells=tuple(
                        MerchantOfferDto(
                            item_name=entry.item_name,
                            item_spec_id=entry.item_spec_id,
                            price=entry.price,
                        )
                        for entry in merchant.sells
                    ),
                    buys=tuple(
                        MerchantOfferDto(
                            item_name=entry.item_name,
                            item_spec_id=entry.item_spec_id,
                            price=entry.price,
                        )
                        for entry in merchant.buys
                    ),
                ),
            )
            for label, entries in (("売", merchant.sells), ("買", merchant.buys)):
                if not entries:
                    continue
                priced = " / ".join(
                    f"\"{entry.item_name}\" {entry.price}G" for entry in entries
                )
                lines.append(f"      {label}: {priced}")

    @staticmethod
    def _build_market_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        """市場の掲示板を「自分が何をできるか」の言葉で surface する。

        「売り 3 件 (最安 18G)」ではなく「18G で買える (出品 3件)」。読んだ人が
        「買い 1 件」を過去の約定か未来の意思表示か取り違えたのが発端で、
        **人間が迷う文面はエージェントも迷う**。行動の言葉に寄せると、板の
        状態を自分の行動へ翻訳する一段が要らなくなる。

        **買い側の列はまだ出さない。** 売る手段 (`market_sell`) が無いのに
        「15G で売れる」と書くと、存在しないツールを本文が宣伝することになり、
        無効化しないより悪い状態になる (`tend_to_player` / `give_item` で実際に
        起きた形)。買い板を入れる PR で列を 1 つ足す。

        買えない品目の行は出さない。「買えない」を毎行並べると、打てない手が
        毎ターン積み上がる。ただし**板の不在は明示する** — 黙って節を消すと
        「ここには無い」と「まだ見つけていない」が同じ沈黙に潰れ、板を探して
        手番を溶かす (商人の節と同じ判断)。
        """
        if not snap.market_declared:
            return
        if not snap.market_board_here:
            lines.append("市場の掲示板: (この場所には無い)")
            return
        lines.append("市場の掲示板:")
        if not snap.market_rows:
            lines.append("  (いま買えるものは出ていない)")
        for row in snap.market_rows:
            buy_side = (
                f"{row.buy_price_gold}G で買える "
                f"(出品 {row.listing_count}件 / 計 {row.buyable_quantity}つ)"
                if row.buy_price_gold is not None
                else _NO_LISTINGS
            )
            sell_side = (
                f"{row.sell_price_gold}G で売れる "
                f"(買い注文 {row.bid_count}件 / 計 {row.sellable_quantity}つ)"
                if row.sell_price_gold is not None
                else _NO_BIDS
            )
            lines.append(f"  \"{row.item_name}\" {buy_side}   {sell_side}")
        for order in snap.market_own_orders:
            # **売りと買いでラベルを分ける。** 同じ品目に両方出していると
            # 2 行並ぶので、同じラベルだと「自分で自分に売れる」と読める。
            if order.side == "buy":
                state = (
                    "引き取り待ち"
                    if order.is_awaiting_collection
                    else "まだ受けられていない"
                )
                label = "あなたの買い注文"
            else:
                state = (
                    "引き取り待ち"
                    if order.is_awaiting_collection
                    else "まだ売れていない"
                )
                label = "あなたの出品"
            lines.append(
                f"  {label}: \"{order.item_name}\" ×{order.quantity} "
                f"@{order.unit_price_gold}G ({state})"
            )

    @staticmethod
    def _build_trade_offer_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        """自分宛てに来ている取引の申し出を surface する。

        **申し出が無ければ節ごと出さない。** 「商人:」と違って不在を明示
        しないのは、申し出は世界に常在するものではなく、来ていないのが常態
        だから。毎ターン「申し出: (無い)」を出しても判断の材料にならない。
        """
        offers = tuple(getattr(snap, "incoming_trade_offers", ()) or ())
        if not offers:
            return
        lines.append("自分宛ての取引の申し出:")
        for offer in offers:
            lines.append(
                f"  - \"{offer.offerer_name}\" から: "
                f"{offer.gives_text} ⇄ {offer.asks_text} "
                f"(あと {offer.remaining_ticks} 手番で流れる)"
            )

    @staticmethod
    def _build_gold_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        """行動者本人の所持金を 1 行で surface する。

        0 でも行を出す。**行ごと消すと「無一文」と「経済の無い世界」が同じ
        沈黙に潰れる。** 商人を宣言していない世界でだけ、行そのものを出さない。
        """
        if not snap.economy_declared:
            return
        lines.append(f"所持金: {snap.own_gold}G")

    def _build_inventory_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        # PR 6 (#404 後続): "I1: 流木" → "流木"。
        # 同じ spec の腐敗 / 新鮮 は別 entry に分かれるが、運用上 name が衝突
        # することはほぼ無い。防御的に ``#N`` を入れておく。
        if not snap.inventory_items:
            return
        lines.append("所持アイテム:")
        inv_names = [e.name for e in snap.inventory_items]
        disamb = _build_ordinal_disambiguator(inv_names)
        for i, entry in enumerate(snap.inventory_items):
            label = allocator.next(PREFIX_INVENTORY)
            disambiguated_name = disamb[i]
            qty = f" x{entry.quantity}" if entry.quantity > 1 else ""
            # Phase D-3a: 腐敗食は (腐敗) を付ける。runtime 側で (spec, is_spoiled)
            # 単位で集約しているので、quantity と (腐敗) の関係は一意に決まる。
            spoiled_mark = " (腐敗)" if entry.is_spoiled else ""
            # usage_hint があれば作者文を最優先で表示する。無ければ scenario
            # item_specs[].category 由来の既定文、category が未知 / 空なら従来の
            # item_type 由来文へフォールバックする。
            item_mark = _format_inventory_item_mark(
                usage_hint=entry.usage_hint,
                category=entry.category,
                item_type=entry.item_type,
            )
            description = (entry.description or "").strip()
            if description:
                usage_hint = (entry.usage_hint or "").strip()
                usage_detail = f" ({usage_hint})" if usage_hint else ""
                # 分類を参照する案内文との契約は、作者説明があっても残す。
                # TOOL 等の一般的な定型文は、より具体的な作者説明に重ねない。
                contract_mark = _format_inventory_item_contract_mark(
                    category=entry.category,
                    item_type=entry.item_type,
                )
                item_detail = (
                    f" — {description}{usage_detail}{contract_mark}"
                )
            else:
                item_detail = item_mark
            action_names = [
                interaction.action_name for interaction in entry.interactions
            ]
            action_labels = [
                _format_action_name_with_condition_hints(interaction)
                for interaction in entry.interactions
                if not tuple(interaction.blocking_hints or ())
            ]
            blocked_action_labels = [
                _format_blocked_action_name_with_hints(interaction)
                for interaction in entry.interactions
                if tuple(interaction.blocking_hints or ())
            ]
            action_part = (
                f" [{', '.join(action_labels)}]" if action_labels else ""
            )
            # ``""`` 規約 (PR #639 後続): item 名のみ ``""`` で囲み、
            # x{量} / 種別タグ / 腐敗 タグは囲まない。LLM は「``""`` 内の
            # 値が item_label に渡すべき値」と読み取れる。
            lines.append(
                f"  - \"{disambiguated_name}\"{qty}{item_detail}{spoiled_mark}"
                f"{action_part}"
            )
            if blocked_action_labels:
                lines.append(
                    f"      いまできない: {'、'.join(blocked_action_labels)}"
                )
            # 後方互換: 既存 use_item は target.item_instance_id に item_spec_id を
            # 入れる慣習 (名前と内容が乖離しているが、リスクを取らないため触らない)。
            # 新しい drop_item / pickup_item は専用フィールド (real_item_instance_id /
            # inventory_slot_id) を見るので、ここで両方埋める。
            collector.add(
                label,
                InventoryToolRuntimeTargetDto(
                    label=label,
                    kind="inventory_item",
                    display_name=disambiguated_name,
                    item_instance_id=entry.item_spec_id,
                    real_item_instance_id=(
                        entry.item_instance_id if entry.item_instance_id >= 0 else None
                    ),
                    inventory_slot_id=(
                        entry.slot_id if entry.slot_id >= 0 else None
                    ),
                    is_spoiled=entry.is_spoiled,
                    available_interactions=tuple(action_names),
                ),
            )

    def _build_ground_items_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        """現在地に落ちているアイテムを名前直書きで列挙する。

        PR 6 (#404 後続): "G1: 流木" → "流木"。同名衝突は ``#N`` で区別。
        pickup tool は item の display_name を渡せば resolver が解決する。
        """
        if not snap.ground_items:
            return
        lines.append("地面に落ちているもの:")
        ground_names = [e.name for e in snap.ground_items]
        disamb = _build_ordinal_disambiguator(ground_names)
        for i, entry in enumerate(snap.ground_items):
            label = allocator.next(PREFIX_GROUND_ITEM)
            disambiguated_name = disamb[i]
            spoiled_mark = " (腐敗)" if entry.is_spoiled else ""
            # ``""`` 規約 (PR #639 後続): ground item 名のみ ``""`` で囲む。
            lines.append(f"  - \"{disambiguated_name}\"{spoiled_mark}")
            collector.add(
                label,
                InventoryToolRuntimeTargetDto(
                    label=label,
                    kind="ground_item",
                    display_name=disambiguated_name,
                    real_item_instance_id=entry.item_instance_id,
                ),
            )
