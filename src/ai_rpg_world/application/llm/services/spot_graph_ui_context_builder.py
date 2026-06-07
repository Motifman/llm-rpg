"""スポットグラフ用の UiContextBuilder（ラベル付与 + ToolRuntimeTarget 登録）。

SpotGraphPlayerSnapshotDto の構造化データからエフェメラルラベルを採番し、
LLM が読めるテキスト行と、ツール実行用の ToolRuntimeContextDto を同時に構築する。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

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

from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
    HEALTH_BUCKET_JP,
)


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
_ITEM_TYPE_DISPLAY = {
    "consumable": " (食料)",
    "equipment": " (装備)",
    "material": " (素材)",
    "tool": " (道具)",
    "key_item": " (重要)",
    "quest": " (任務品)",
    "cosmetic": " (装飾)",
    "other": "",
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


class SpotGraphUiContextBuilder(ILlmUiContextBuilder):
    """スポットグラフのスナップショットにラベルを付与する UiContextBuilder。"""

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

        self._build_connection_section(snap, allocator, collector, extra_lines)
        self._build_object_section(snap, allocator, collector, extra_lines)
        self._build_sub_location_section(snap, allocator, collector, extra_lines)
        self._build_entity_section(snap, allocator, collector, extra_lines)
        self._build_monster_section(snap, allocator, collector, extra_lines)
        self._build_inventory_section(snap, allocator, collector, extra_lines)
        self._build_ground_items_section(snap, allocator, collector, extra_lines)
        self._build_needs_section(snap, extra_lines)
        self._build_active_effects_section(snap, extra_lines)
        self._build_agent_status_section(snap, extra_lines)

        augmented_text = current_state_text
        if extra_lines:
            augmented_text = current_state_text.rstrip() + "\n" + "\n".join(extra_lines)

        return LlmUiContextDto(
            current_state_text=augmented_text,
            tool_runtime_context=ToolRuntimeContextDto(
                targets=collector.get_targets(),
                current_spot_id=snap.current_spot_id,
                current_sub_location_id=_current_sub_location_id_from_snapshot(snap),
            ),
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
                f"  - {entry.connection_name} → {disambiguated_name}（{status}）"
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
            interaction_parts: list[str] = []
            action_names: list[str] = []
            for inter in entry.interactions:
                interaction_parts.append(
                    f"{inter.display_label}(action_name=\"{inter.action_name}\")"
                )
                action_names.append(inter.action_name)
            act_str = " / ".join(interaction_parts) if interaction_parts else "—"
            desc_part = f" — {entry.description}" if entry.description else ""
            lines.append(f"  - {disambiguated_name}{desc_part} [{act_str}]")
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
            lines.append(f"  - {disambiguated_name}{here}")
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
                if fatigue_suffix:
                    suffix = fatigue_suffix
            lines.append(f"  - {disambiguated_name}{suffix}")
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
            lines.append(f"  - {disambiguated_name}（{desc}）")
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
        if not snap.need_lines:
            return
        lines.append("身体の状態:")
        for line in snap.need_lines:
            lines.append(f"  {line}")
        # PR β (実験 #29 後続): own player の疲労 tier に応じた行動ヒント。
        # describe() は数値 + 5 段階のテキストだけなので、ここで「重い行動が
        # block されている / 動きが鈍くなる」のような操作可能性に直結する
        # 情報を 1 行足す。system prompt は変えず state section にだけ載せる
        # 設計 (docs/design_decisions.md #1 / #8)。
        fatigue_level = snap.player_state.get("fatigue_level") if snap.player_state else None
        hint = _FATIGUE_OWN_HINT.get(fatigue_level or "ok")
        if hint:
            lines.append(f"  → {hint}")

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
            lines.append(f"  - {disambiguated_name}{qty}{type_mark}{spoiled_mark}")
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
            lines.append(f"  - {disambiguated_name}{spoiled_mark}")
            collector.add(
                label,
                InventoryToolRuntimeTargetDto(
                    label=label,
                    kind="ground_item",
                    display_name=disambiguated_name,
                    real_item_instance_id=entry.item_instance_id,
                ),
            )
