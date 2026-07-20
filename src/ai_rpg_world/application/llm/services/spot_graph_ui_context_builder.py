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
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
from ai_rpg_world.application.llm.services._runtime_target_collector import RuntimeTargetCollector
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
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
# PR-C (Y_after_issue621 後続): consumable 以外は ``use_item`` ツールで
# 使えないため、種別タグに **「使用不可」** を明示する。Y_after_issue621 では
# 流木 (material) に対して LLM が ``use_item`` を 7 回連続試行して全部失敗した。
# 既存の ``(素材)`` だけのタグでは「これは use_item できないアイテム」だと
# LLM が判断できなかった (= 飢餓で錯乱した時に「素材でも食えるかも」と試した)。
#
# 内部 error_code は ``ITEM_NOT_CONSUMABLE`` のまま (= 用語 grep 互換)、プレイヤー
# 露出文言だけ「使用不可」(= use_item できない、の直接表現) に統一する。
# 「消費不可」は player 視点で不自然なので避けた。
_ITEM_TYPE_DISPLAY = {
    "consumable": " (食料)",
    "equipment": " (装備・使用不可)",
    "material": " (素材・使用不可)",
    "tool": " (道具・使用不可)",
    "key_item": " (重要・使用不可)",
    "quest": " (任務品・使用不可)",
    "cosmetic": " (装飾・使用不可)",
    "other": " (使用不可)",
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
    "exhausted": "疲労が限界。travel / attack / interact は実行できない。wait や食事で回復が必要。",
}


def _format_item_type_tag(item_type: str) -> str:
    """item_type 文字列値を日本語タグに整形する。

    未知 / 空 / "other" のときは空文字 (タグ非表示)。
    """
    if not item_type:
        return ""
    return _ITEM_TYPE_DISPLAY.get(item_type, "")


def _format_object_state(state: Dict[str, Any]) -> str:
    """SpotGraphObjectEntry.visible_state を prompt 表示用の tag に整形。

    PR-X (Y_after_pr639_640 後続): 空 dict → 空文字。1 個以上のエントリ
    があれば `` (key=value, key2=value2)`` の形式で prepend する。

    値の変換は ``spot_graph_current_state_formatter._render_value`` に
    委譲する (bool→lowercase、None→"null"、その他 primitive→str)。
    formatter 側の旧 "スポット内オブジェクトの状態:" block と同じ
    convention を保つことで、LLM が「どちらの format が正しいか」で
    迷うのを避ける (旧 block は本 PR で削除、この inline 形式に一本化)。

    key の順序: 挿入順 (dict の insertion order)。同一 tick 内では domain
    側の visible_state() 出力順に依存するため、実質的に安定している。

    例:
      {}                             → ""
      {"available": False}           → " (available=false)"
      {"opened": True, "count": 0}   → " (opened=true, count=0)"
      {"latch": None}                → " (latch=null)"
    """
    if not state:
        return ""
    parts: List[str] = [f"{k}={_render_value(v)}" for k, v in state.items()]
    return f" ({', '.join(parts)})"


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

        viewer_player_id: Optional[PlayerId] = None
        if current_state.player_id is not None:
            try:
                viewer_player_id = PlayerId(int(current_state.player_id))
            except Exception:
                viewer_player_id = None

        self._build_connection_section(snap, allocator, collector, extra_lines)
        self._build_object_section(snap, allocator, collector, extra_lines)
        self._build_sub_location_section(snap, allocator, collector, extra_lines)
        self._build_entity_section(
            snap, allocator, collector, extra_lines, viewer_player_id
        )
        self._build_monster_section(snap, allocator, collector, extra_lines)
        self._build_inventory_section(snap, allocator, collector, extra_lines)
        self._build_ground_items_section(snap, allocator, collector, extra_lines)
        self._build_needs_section(snap, extra_lines)
        self._build_active_effects_section(snap, extra_lines)
        self._build_agent_status_section(snap, extra_lines)

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
                f"  - {entry.connection_name} → \"{disambiguated_name}\"（{status}）"
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
            return
        lines.append("オブジェクト:")
        obj_names = [e.name for e in snap.objects]
        disamb = _build_ordinal_disambiguator(obj_names)
        for i, entry in enumerate(snap.objects):
            label = allocator.next(PREFIX_OBJECT)
            disambiguated_name = disamb[i]
            # PR-EE (Y_after_pr639_640 後続): action 表示は action_name の
            # カンマ区切りに簡略化。旧
            # ``[gather(action_name="gather") / examine(action_name="examine")]``
            # は冗長で認知負荷が高く、LLM の action 誤発明を招いていた。
            action_names: list[str] = [inter.action_name for inter in entry.interactions]
            act_str = f" [{', '.join(action_names)}]" if action_names else ""
            desc_part = f" — {entry.description}" if entry.description else ""
            # PR-X (Y_after_pr639_640 後続): visible state を prompt に露出。
            # {'available': False} のような state が「使用不可」タグとして
            # LLM に見え、PRECONDITION_FAILED ループを avoid できる。
            state_part = _format_object_state(entry.state)
            # PR-FF (Y_after_pr639_640 後続): object 名を ``""`` で囲む
            # (PR #639/#640 で導入した quote 規約を全 section に拡張)。
            lines.append(
                f"  - \"{disambiguated_name}\"{state_part}{desc_part}{act_str}"
            )
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
    ) -> None:
        """同じ場所にいる他プレイヤーを列挙する。

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
        lines.append("同じ場所にいるプレイヤー:")
        entity_names = [
            (e.display_name or f"プレイヤー({e.entity_id})")
            for e in snap.nearby_entities
        ]
        disamb = _build_ordinal_disambiguator(entity_names)
        for i, entry in enumerate(snap.nearby_entities):
            label = allocator.next(PREFIX_ENTITY)
            disambiguated_name = disamb[i]
            # PR #347 後続: 倒れている相手は (倒れて動かない) を後置して、
            # speech / 受け渡しの対象として動かないことを LLM が認識できるよう
            # にする。OFF mode で過去の PlayerDownedEvent が観測 buffer から
            # 流れた後でも、snapshot から「あの人が床に転がっている」が読める。
            suffix = " (倒れて動かない)" if entry.is_down else ""
            # PR β (実験 #29 後続): 仲間の疲労状態を Observation でなく
            # state として常時表示する。is_down 優先、それ以外で疲労を出す。
            if not entry.is_down:
                fatigue_suffix = _format_fatigue_suffix(entry.fatigue_level)
                # P-U4 (停滞感の表出・他者): fatigue と併存させる。ゲージ値は
                # 見せず、バンドに応じた様子の suffix だけを足す。
                stagnation_suffix = _format_stagnation_suffix(entry.stagnation_band)
                suffix = fatigue_suffix + stagnation_suffix
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
            lines.append(
                f"  - \"{disambiguated_name}\"{suffix}{familiarity_suffix}"
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
                "重い行動 (別の移動 / interact / use_item / attack) を選ぶと "
                "現在の行動は中断され、その場で停止する。"
            )

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
            # 実験 #29 後続: item_type を日本語タグで表示し、LLM が
            # 「食べられる / 道具 / 素材」の区別をリストだけで判断できるよう
            # にする。ITEM_NOT_CONSUMABLE (= 食料じゃないものを食べようとする
            # ミス) を減らす目的。
            type_mark = _format_item_type_tag(entry.item_type)
            # ``""`` 規約 (PR #639 後続): item 名のみ ``""`` で囲み、
            # x{量} / 種別タグ / 腐敗 タグは囲まない。LLM は「``""`` 内の
            # 値が item_label に渡すべき値」と読み取れる。
            lines.append(
                f"  - \"{disambiguated_name}\"{qty}{type_mark}{spoiled_mark}"
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
