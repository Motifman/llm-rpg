"""
ツール実行ターン向けの決定論的 EpisodicCue 生成。

LLM・プロンプト文字列・旧 cue_keys に依存しない。runtime / tool メタ /
canonical_arguments / LlmCommandResultDto / ActionResultEntry / 観測 structured のみを入力とする。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Iterable, Sequence

_logger = logging.getLogger(__name__)

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    ActionResultEntry,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
if TYPE_CHECKING:
    # Issue #283 後続: 観測 prose の自由文 cue 抽出に使う。Protocol なので
    # 型チェック時のみ参照。runtime には依存しない (caller が None でも安全)。
    from ai_rpg_world.application.llm.services.world_noun_matcher import (
        IWorldNounMatcher,
    )
    # PR8 (R5): encounter memory を recall cue 源にする。Protocol 型なので
    # 型チェック時のみ参照、runtime には依存しない。
    from ai_rpg_world.application.encounter.contracts.interfaces import (
        IEncounterMemory,
    )

_EMOTION_HINT_SET = frozenset(EMOTION_HINT_VALUES)
_SAFE_SEGMENT_RE = re.compile(r"[^a-z0-9_]+")

# 1 episode あたりの cue 上限（索引肥大・暴走防止）
MAX_EPISODIC_CUES = 32
# tile_area は冗長になりやすいため個別上限（action/outcome より後ろで列挙し、ここで打ち切る）
MAX_TILE_AREA_CUES = 24
# value は索引キーとして短く保つ（canonical は axis:value のため value 側のみが対象）
MAX_CUE_VALUE_CHARS = 96


def build_episodic_cues_for_tool_turn(
    *,
    tool_name: str,
    canonical_arguments: Mapping[str, Any] | None,
    runtime_context: ToolRuntimeContextDto | None,
    command_result: LlmCommandResultDto | None,
    observation_structured: Mapping[str, Any] | None = None,
) -> tuple[EpisodicCue, ...]:
    """
    同一入力から常に同じ cue 列を返す（挿入順も固定）。

    None のコンテキストや未知フィールドは黙って無視する。
    """
    collected: list[EpisodicCue] = []

    # action / outcome / canonical はシグナルが強いため先に並べ、tile_area 大量時でも欠落しないようにする。
    tn = _optional_str(tool_name)
    if tn is not None:
        seg = _sanitize_tool_segment(tn)
        if seg is not None:
            collected.append(EpisodicCue(axis="action", value=seg, source=EpisodicCueSource.TOOL))

    args = canonical_arguments
    if args is not None:
        collected.extend(_cues_from_canonical_arguments(args))

    res = command_result
    if res is not None:
        oc = _outcome_cue_from_success_and_error(success=res.success, error_code=res.error_code)
        if oc is not None:
            collected.append(oc)

    collected.extend(
        _collect_situation_episodic_cues(
            runtime_context=runtime_context,
            observation_structured=observation_structured,
        )
    )

    validated = _validate_and_dedupe(collected)
    return tuple(validated)


def merge_ordered_episodic_cues(
    ordered_parts: Sequence[tuple[EpisodicCue, ...]],
) -> tuple[EpisodicCue, ...]:
    """
    複数の cue 列を先頭から順に連結し、canonical 単位で重複除去する。

    チャンク境界など、観測由来の局面 cue と複数 tool ターンの cue を束ねるときに使う。
    先に渡した列の cue が、同一 canonical では後続より優先される（挿入順維持）。
    """
    collected: list[EpisodicCue] = []
    for part in ordered_parts:
        collected.extend(part)
    return tuple(_validate_and_dedupe(collected))


def build_situation_episodic_cues(
    *,
    runtime_context: ToolRuntimeContextDto | None,
    observation_structured: Mapping[str, Any] | None = None,
    latest_action: ActionResultEntry | None = None,
    observation_prose: str | None = None,
    noun_matcher: "IWorldNounMatcher | None" = None,
    additional_freetexts: Sequence[str] | None = None,
    encounter_memory: "IEncounterMemory | None" = None,
    encounter_player_id: PlayerId | None = None,
    encounter_current_tick: int | None = None,
    encounter_recent_window_ticks: int = 5,
) -> tuple[EpisodicCue, ...]:
    """
    受動想起用の「現在局面」に相当する cue 列を、保存時 `build_episodic_cues_for_tool_turn` と
    同じ軸・語彙・正規化で返す（挿入順も固定）。

    `ToolRuntimeContextDto` と直近観測 structured に加え、`latest_action` があれば
    直近ツール名・成否（§0.2）を action / outcome 軸で足し、チャンク保存側の cue と揃えて想起しやすくする。

    Issue #283 後続: ``observation_prose`` + ``noun_matcher`` が両方注入されていれば、
    観測の自由文本を ``WorldNounMatcher`` (Aho-Corasick) で走査し、含まれる固有名詞
    から ``OBSERVATION_FREETEXT`` source で cue を追加する。これにより SNS / speech
    の prose に「書架A」とだけ書かれているケースでも place_spot:3 cue が立つ。

    PR7 (R4): ``additional_freetexts`` が与えられたら、各文字列にも noun_matcher を
    適用する。caller は直近 N 件の観測 prose / 自分の発話 / 自分の内心などを
    まとめて渡す想定。これにより「最新観測 1 件にしか matcher が当たらない」
    狭さが解消される。None / 空 list / matcher 未注入の場合は何もしない。

    PR8 (R5): ``encounter_memory`` + ``encounter_player_id`` + ``encounter_current_tick``
    が全て与えられたら、直近 ``encounter_recent_window_ticks`` 以内に encounter
    した entity / spot / event を ``ENCOUNTER`` source の cue として追加する。
    構造化 spawn / arrival 観測しか無い場面でも entity / spot cue を立てて、
    過去 episode が recall されるようにするための経路。

    None の入力や未知フィールドは黙って無視する。
    """
    collected: list[EpisodicCue] = []
    if latest_action is not None:
        collected.extend(_cues_from_latest_action_entry(latest_action))
    collected.extend(
        _collect_situation_episodic_cues(
            runtime_context=runtime_context,
            observation_structured=observation_structured,
            observation_prose=observation_prose,
            noun_matcher=noun_matcher,
            additional_freetexts=additional_freetexts,
        )
    )
    if (
        encounter_memory is not None
        and encounter_player_id is not None
        and encounter_current_tick is not None
    ):
        collected.extend(
            _cues_from_recent_encounters(
                encounter_memory=encounter_memory,
                player_id=encounter_player_id,
                current_tick=encounter_current_tick,
                recent_window_ticks=encounter_recent_window_ticks,
            )
        )
    validated = _validate_and_dedupe(collected)
    return tuple(validated)


def _collect_situation_episodic_cues(
    *,
    runtime_context: ToolRuntimeContextDto | None,
    observation_structured: Mapping[str, Any] | None,
    observation_prose: str | None = None,
    noun_matcher: "IWorldNounMatcher | None" = None,
    additional_freetexts: Sequence[str] | None = None,
) -> list[EpisodicCue]:
    """runtime / 観測 structured / 観測 prose / 追加 freetexts から局面 cue を
    組み立てる (重複除去・件数上限は呼び出し側)。"""
    out: list[EpisodicCue] = []
    rt = runtime_context
    if rt is not None:
        out.extend(_cues_from_runtime_place(rt))

    obs = observation_structured
    if obs is not None:
        out.extend(_cues_from_observation_structured(obs))

    if observation_prose and noun_matcher is not None:
        out.extend(_cues_from_observation_prose(observation_prose, noun_matcher))

    if additional_freetexts and noun_matcher is not None:
        for raw in additional_freetexts:
            if not raw:
                continue
            out.extend(_cues_from_observation_prose(raw, noun_matcher))

    if rt is not None:
        out.extend(_cues_from_runtime_targets(rt.targets))
        out.extend(_cues_from_runtime_tile_areas(rt))

    return out


def _cues_from_observation_prose(
    prose: str,
    noun_matcher: "IWorldNounMatcher",
) -> list[EpisodicCue]:
    """観測 prose に含まれる固有名詞から cue を立てる (Issue #283 後続)。

    ``WorldNounMatcher.find_in_text`` が返す ``NounMatch`` の axis / value を
    そのまま ``EpisodicCue`` に変換する。matcher 側で既に "kind_id" 形式の
    value にしているので、構造化 cue と同じ index で recall に乗る。

    同一 prose に同じ entity の言及が複数あっても (axis, value) が同じなので、
    ``_validate_and_dedupe`` で 1 件に正規化される。
    """
    try:
        matches = noun_matcher.find_in_text(prose)
    except Exception:
        # matcher 実装の予期しない失敗で prompt build を止めない。ただし
        # 「matcher が壊れて 0 件にフォールバック中」を後から見つけられる
        # よう WARN 級で traceback ごと残す (silent failure 防止)。
        _logger.warning(
            "noun_matcher.find_in_text failed; recall fallback to empty cue list",
            exc_info=True,
        )
        return []
    out: list[EpisodicCue] = []
    for m in matches:
        out.append(
            EpisodicCue(
                axis=m.axis,
                value=m.value,
                source=EpisodicCueSource.OBSERVATION_FREETEXT,
            )
        )
    return out


def _cues_from_latest_action_entry(entry: ActionResultEntry) -> list[EpisodicCue]:
    """IActionResultStore の最新行動から action / outcome cue を付与（tool ターンと同一正規化）。"""
    out: list[EpisodicCue] = []
    tn = _optional_str(entry.tool_name)
    if tn is not None:
        seg = _sanitize_tool_segment(tn)
        if seg is not None:
            out.append(EpisodicCue(axis="action", value=seg, source=EpisodicCueSource.TOOL))
    oc = _outcome_cue_from_success_and_error(success=entry.success, error_code=entry.error_code)
    if oc is not None:
        out.append(oc)
    return out


def _optional_str(raw: object | None) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if s else None


def _sanitize_tool_segment(name: str) -> str | None:
    """tool 名を cue value として安全な単一段に落とす。"""
    lowered = name.strip().lower()
    if not lowered:
        return None
    cleaned = _SAFE_SEGMENT_RE.sub("_", lowered).strip("_")
    return _truncate_value(cleaned) if cleaned else None


def _sanitize_id_segment(prefix: str, raw_id: int) -> str:
    body = str(int(raw_id))
    seg = f"{prefix}_{body}" if prefix else body
    out = _truncate_value(seg)
    return out


def _truncate_value(value: str) -> str:
    if len(value) <= MAX_CUE_VALUE_CHARS:
        return value
    return value[:MAX_CUE_VALUE_CHARS]


def _normalize_error_code(code: str) -> str | None:
    s = code.strip().lower()
    if not s:
        return None
    cleaned = _SAFE_SEGMENT_RE.sub("_", s).strip("_")
    if not cleaned:
        return None
    return _truncate_value(cleaned)


def _outcome_cue_from_success_and_error(
    *, success: bool, error_code: str | None
) -> EpisodicCue | None:
    """成功 / 失敗から outcome cue を作る。

    #526 後続 Fix D: 成功時は cue を出さない。実 run の trace 解析で、
    ほぼ全 episode が ``outcome:success`` を持ち、毎ターン全 successful
    episode が hit して recall が肥大することが判明したため。outcome cue は
    失敗時 (= 希少 + 「何かおかしかった」シグナル) にのみ意味がある。

    失敗は error_code があれば ``failure_{normalized}``、無ければ ``failure``。
    成功は ``None`` (= cue なし)。read 側でも同じ判定を共有するため、本関数を
    通る全経路 (build / recall 両方) で対称に効く。
    """
    if success:
        # Fix D: 成功 outcome cue は index 選択性が極端に低いので出さない。
        return None
    ec = error_code
    if isinstance(ec, str) and ec.strip():
        norm = _normalize_error_code(ec)
        value = f"failure_{norm}" if norm else "failure"
    else:
        value = "failure"
    safe = _truncate_value(value)
    if not safe:
        return None
    return EpisodicCue(axis="outcome", value=safe, source=EpisodicCueSource.TOOL)


def _strict_int(raw: Any) -> int | None:
    """bool は int のサブクラスだがゲーム id として誤解釈しない。"""
    return raw if type(raw) is int else None


def _cues_from_runtime_place(rt: ToolRuntimeContextDto) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    sid = _strict_int(rt.current_spot_id)
    if sid is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(sid), source=src))
    sub = _strict_int(rt.current_sub_location_id)
    if sub is not None:
        out.append(EpisodicCue(axis="sub_loc", value=str(sub), source=src))
    return out


def _cues_from_runtime_tile_areas(rt: ToolRuntimeContextDto) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    areas = rt.current_area_ids
    if not isinstance(areas, tuple):
        return out
    sorted_ids = sorted({a for a in areas if type(a) is int})
    for aid in sorted_ids[:MAX_TILE_AREA_CUES]:
        out.append(EpisodicCue(axis="tile_area", value=str(aid), source=src))
    return out


def _kind_slug(kind: str) -> str:
    k = kind.strip().lower()
    if not k:
        return "target"
    cleaned = _SAFE_SEGMENT_RE.sub("_", k).strip("_")
    return cleaned if cleaned else "target"


def _cues_from_runtime_targets(targets: Mapping[str, ToolRuntimeTargetDto]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    for label in sorted(targets.keys()):
        t = targets[label]
        if not isinstance(t, ToolRuntimeTargetDto):
            continue
        pid = _strict_int(t.player_id)
        if pid is not None:
            slug = _kind_slug(t.kind)
            val = _sanitize_id_segment(slug, pid)
            out.append(EpisodicCue(axis="entity", value=val, source=src))
        woid = _strict_int(t.world_object_id)
        if woid is not None:
            val = _sanitize_id_segment("world_object", woid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
        iid = _strict_int(t.item_instance_id)
        if iid is not None:
            val = _sanitize_id_segment("item_instance", iid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
        cid = _strict_int(t.chest_world_object_id)
        if cid is not None:
            val = _sanitize_id_segment("chest_world_object", cid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
    return out


def _cues_from_recent_encounters(
    *,
    encounter_memory: "IEncounterMemory",
    player_id: PlayerId,
    current_tick: int,
    recent_window_ticks: int,
) -> list[EpisodicCue]:
    """PR8 (R5): 直近 ``recent_window_ticks`` 以内に encounter した entity /
    spot / event から recall cue を立てる。

    EncounterKey.kind → EpisodicCue.axis のマッピング:
      ``player`` → axis=``entity``, value=``spot_graph_player_{identifier}``
        (= ``_cues_from_runtime_targets`` の entity 形式と整合)
      ``spot``   → axis=``place_spot``, value=``{identifier}``
        (= ``_cues_from_runtime_place`` の spot 形式と整合)
      ``event``  → axis=``action``, value=``{identifier}``

    時間窓判定は ``last_seen_tick`` ベース。``current_tick - last_seen_tick``
    が ``recent_window_ticks`` 以下のものだけを cue 化する。

    encounter memory の例外は warning にして空 list を返す (recall を止めない
    silent-safe fallback)。``EncounterRecord.is_first`` 等の状態は cue では
    区別しない: 「直近で会った」「直近で再会した」のどちらも cue を立てる
    だけで、その先のスコアリングは PR6 (R3) の cue scoring に任せる。
    """
    try:
        records = encounter_memory.get_records_for(player_id)
    except Exception:
        _logger.warning(
            "encounter_memory.get_records_for failed; recall fallback to empty encounter cues",
            exc_info=True,
        )
        return []
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.ENCOUNTER
    for key, record in records.items():
        # 時間窓判定: tick の差 (= 経過 tick 数) が window 以下なら含める。
        # past tick が大きい (= 未来) ケースは記録ミス想定で skip。
        delta = current_tick - record.last_seen_tick
        if delta < 0 or delta > recent_window_ticks:
            continue
        identifier = key.identifier
        if not identifier:
            continue
        kind = key.kind
        if kind == "player":
            ident_int = _strict_int_str(identifier)
            if ident_int is None:
                continue
            value = _sanitize_id_segment("spot_graph_player", ident_int)
            out.append(EpisodicCue(axis="entity", value=value, source=src))
        elif kind == "spot":
            ident_int = _strict_int_str(identifier)
            if ident_int is None:
                continue
            # int → str を経由して runtime 由来 cue (= ``_cues_from_runtime_place``
            # の ``str(sid)``) と同じ canonical 表記に揃える。"007" のような
            # zero-padded identifier も "7" に正規化されて、runtime cue と
            # PR6 (R3) のスコアリング上で merge される。
            out.append(
                EpisodicCue(
                    axis="place_spot",
                    value=str(ident_int),
                    source=src,
                )
            )
        elif kind == "event":
            # ``_sanitize_tool_segment`` を流用: tool 名と同じ [a-z0-9_]
            # 正規化で event identifier も canonical 化する (action 軸の
            # cue 値形式と整合)。
            seg = _sanitize_tool_segment(identifier)
            if seg is None:
                continue
            out.append(EpisodicCue(axis="action", value=seg, source=src))
        # 未知 kind は (sanitize 経由でも未保証なので) skip
    return out


def _strict_int_str(raw: str) -> int | None:
    """``str(int)`` 形式の identifier を int に戻す。整数以外は None。

    NOTE: 兄弟の ``_strict_int`` (上記) とは用途が違う:
      - ``_strict_int``: ``Any`` を受け取り「型が真に int」かをチェック (bool 排除)
      - ``_strict_int_str``: ``str`` を受け取り int に parse する (canonical 化用途)
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _cues_from_canonical_arguments(args: Mapping[str, Any]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    hint = args.get("emotion_hint")
    if isinstance(hint, str):
        h = hint.strip().lower()
        if h in _EMOTION_HINT_SET:
            hv = _truncate_value(h)
            out.append(EpisodicCue(axis="emotion", value=hv, source=EpisodicCueSource.TOOL))
    woid = _strict_int(args.get("world_object_id"))
    if woid is not None:
        val = _sanitize_id_segment("world_object", woid)
        out.append(EpisodicCue(axis="object", value=val, source=EpisodicCueSource.TOOL))
    return out


def _coerce_non_bool_int(raw: Any) -> int | None:
    if type(raw) is int:
        return raw
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw)
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s or not s.isdigit():
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def _coerce_actor_entity(raw: Any) -> str | None:
    x = _coerce_non_bool_int(raw)
    if x is not None:
        return _sanitize_id_segment("actor", x)
    if isinstance(raw, str):
        slug = _sanitize_tool_segment(raw)
        if slug is None:
            return None
        return _truncate_value(f"actor_{slug}")
    return None


def _cues_from_observation_structured(structured: Mapping[str, Any]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.OBSERVATION_STRUCTURED
    spot = structured.get("spot_id_value")
    si = _coerce_non_bool_int(spot)
    if si is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(si), source=src))
    # #526 後続 Fix B: 移動観測 (entity_entered_spot / entity_left_spot /
    # to/from) が emit する ``from_spot_id_value`` / ``to_spot_id_value`` も
    # place_spot cue に変換する。両方とも「ここに居た / ここに来た」という
    # 意味で recall の手がかりに値する (dedupe は呼出側で行われる)。
    from_spot = _coerce_non_bool_int(structured.get("from_spot_id_value"))
    if from_spot is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(from_spot), source=src))
    to_spot = _coerce_non_bool_int(structured.get("to_spot_id_value"))
    if to_spot is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(to_spot), source=src))
    wov = structured.get("world_object_id_value")
    wi = _coerce_non_bool_int(wov)
    if wi is not None:
        val = _sanitize_id_segment("world_object", wi)
        out.append(EpisodicCue(axis="object", value=val, source=src))
    actor = structured.get("actor")
    av = _coerce_actor_entity(actor)
    if av is not None:
        out.append(EpisodicCue(axis="entity", value=av, source=src))
    return out


def _validate_and_dedupe(cues: Iterable[EpisodicCue]) -> list[EpisodicCue]:
    """canonical 単位で重複除去し、件数・値長を守る。"""
    seen: set[str] = set()
    ordered: list[EpisodicCue] = []
    for c in cues:
        if not isinstance(c, EpisodicCue):
            continue
        val = c.value
        if len(val) > MAX_CUE_VALUE_CHARS:
            continue
        key = c.to_canonical()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(c)
        if len(ordered) >= MAX_EPISODIC_CUES:
            break
    return ordered
