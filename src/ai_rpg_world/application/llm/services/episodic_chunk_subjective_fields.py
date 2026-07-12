"""チャンク由来のルール草案に対し LLM が interpreted / recall_text / prediction_error を付与する。"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence


def _as_utc(value: datetime) -> datetime:
    """naive datetime を UTC aware として扱う sort 正規化ヘルパ (Issue #311 後続)。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

from ai_rpg_world.application.llm.contracts.chunk_encoding import ChunkEncodingInput
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.heard_claim import (
    HeardClaim,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPredictionDraft,
    PendingResolutionVerdict,
)
from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    PendingPredictionValidationException,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.exceptions import LlmApiCallException

_SYSTEM_EPISODE_SUBJECTIVE_JSON = """あなたは RPG エージェントの主観記憶を埋める助手です。
入力はルールが組み立てたエピソード草案・人物像・ソース事実のみです。
出力は JSON オブジェクトのみ（前後に説明文やコードフェンスを付けない）。
キーは次の 4 つ: interpreted, recall_text, prediction_error, heading。

heading は、この出来事を後から「ぼんやり思い出す」ときの見出しとして使う
1 行サマリ。30 文字以内。原則として「〜した」「〜が起きた」のような体言止め
または過去形 1 文で、行動と印象的な要素を 1 つだけ含める。
（例: 「司書の手記を読んだ — 水の断片語」「廊下でカイトの声を聞いた」）
分からない / 出来事の特徴が無いときは空文字列 "" にする。

interpreted は「この出来事を当時どう意味づけたか」の日本語 1 文。
過去の出来事の意味付けなので、原則として過去形・完了形で書く
（例: 「〜と感じた」「〜だと気づいた」「〜が分かった」）。

recall_text は将来のプロンプトに差し込む、キャラクター本人の一人称による
TRPG リプレイ風の主観回想。250〜450 字程度で、当時の感情・見立て・手触りを含める。

**recall_text は必ず過去形で書くこと**。これは「思い出している」テキストであり、
未来の prompt で「過去にこういうことがあった」と参照される設計のため、
現在形・未来形・命令形・意志形（「〜しよう」「〜しなければ」「〜しよう」「〜したい」）は
使ってはいけない。
- OK: 「〜だった」「〜が見えた」「〜と思った」「〜していた」「〜してしまった」「〜だと気づいた」
- NG: 「〜しなきゃならない」「〜しよう」「〜する必要がある」「〜したい」「〜するつもりだ」

ただし当時の感情の余韻だけは「〜だった気がする」「今でも〜と思う」のような形を許す。
出来事の描写・行動・結果は厳格に過去形に統一する。

prediction_error は「行動前の予測 (expected) と実際の結果 (observed / outcome) の
食い違い」を日本語 1〜2 文で書く。expected が無い、または予測どおりだった場合は
空文字列 "" にする。これは願望が叶わなかったという話ではなく、世界の応答が自分の
見立てとどう違ったか・何を見落としていたかを簡潔に残すもの。過去形で書く。
（例: 「声をかければ話せると思っていたが、相手は黙って立ち去った。」）

入力に無い人物・場所・アイテム・結果・成否を新たに創作しない。
キューや observed の事実と矛盾しない表現にする。"""

# U6 (予測誤差統一設計 / salience): SALIENCE_STRUCTURED_FAILURE_ENABLED が
# OFF のときは既定 prompt を byte 不変に保つため、salience 節は文字列
# 追記(置換)で組み立てる。既存定数 _SYSTEM_EPISODE_SUBJECTIVE_JSON はテスト
# 資産 (past-tense regression test 等) が直接参照しているため変更しない。
_SALIENCE_KEY_LIST_OLD = "キーは次の 4 つ: interpreted, recall_text, prediction_error, heading。"
_SALIENCE_KEY_LIST_NEW = "キーは次の 5 つ: interpreted, recall_text, prediction_error, heading, salience。"
_SALIENCE_INSTRUCTION = """

salience は "low" または "high" のいずれか。high は「このキャラにとって
予測が大きく外れた / 初めての重大事」だけに使う判定で、日常的な出来事や
軽い驚きは low にする。判断に迷ったら low にする。"""

# U8 (予測誤差統一設計 部品2b: 誤差ゲート付き符号化 / 解像度): recall_text の
# 長さ指示を salience 連動にする。ERROR_GATED_ENCODING_ENABLED が OFF のとき、
# または salience_enabled 自体が OFF のときは元の一律の長さ指示のまま
# (byte 不変)。ON のときだけこの文字列で置換する。LLM は同一呼び出し内で
# salience を判定してから長さを選ぶ (追加 LLM 呼び出しは発生しない)。
_RECALL_LENGTH_INSTRUCTION_OLD = (
    "250〜450 字程度で、当時の感情・見立て・手触りを含める。"
)
_RECALL_LENGTH_INSTRUCTION_NEW = (
    "salience の判定結果に応じた長さで、当時の感情・見立て・手触りを含める。"
    "salience=high (予測が大きく外れた/初めての重大事) なら250〜450字程度で"
    "詳しく書き、salience=low (予測どおり/日常的) なら80〜150字程度の簡潔な"
    "定型に近い形にする。"
)


# U7 (予測誤差統一設計 / 無意識コンテキスト): UNCONSCIOUS_CONTEXT_ENABLED が
# OFF のときは system prompt を byte 不変に保つため、salience と同じ「文字列
# 追記」方式で組み立てる。新しい JSON キーは増やさない (interpreted /
# recall_text / prediction_error の判定基準を変えるだけの指示追記)。
_UNCONSCIOUS_CONTEXT_INSTRUCTION = """

ユーザメッセージに「## いまの自分（信念と自己像）」という節があれば、そこに
書かれた本人の信念・自己像に照らして interpreted / prediction_error /
salience を判定すること。信念に強く合致する出来事は想定内、信念に反する
出来事は想定外として重みづけてよい（これは人間らしい思い込みの表現であり、
むしろ望ましい）。ただし信念はあくまで解釈の材料であり、事実
（ルール草案の observed / cues / what / outcome）を信念に合わせて改変しては
ならない。当該節が無い場合はこの指示を無視してよい。"""


# U10a (予測誤差統一設計 部品6・pending prediction): salience と独立な
# もう 1 つの追加フィールド。key list の数字は salience_enabled の有無で
# ベースが変わるため、両方の組み合わせ (4→5 / 5→6) を別々の定数で持つ。
_PENDING_KEY_LIST_BASE_NEW = (
    "キーは次の 6 つ: interpreted, recall_text, prediction_error, heading, "
    "pending_prediction, pending_resolutions。"
)
_PENDING_KEY_LIST_WITH_SALIENCE_NEW = (
    "キーは次の 7 つ: interpreted, recall_text, prediction_error, heading, "
    "salience, pending_prediction, pending_resolutions。"
)
_PENDING_PREDICTION_INSTRUCTION = """

pending_prediction は、この chunk に将来の特定の時・場所・相手についての
約束や見込みが含まれるときだけ書くオブジェクト。**相手か場所か時刻の
いずれかが特定できないものは書かない**（乱発防止）。何も無ければ null にする。
オブジェクトのキーは次の 4 つ:
- text: 約束・見込みの内容を表す日本語 1 文
  （例: 「夕方に木の下でカイトとアイテムを交換する」）
- resolution_cues: 解決条件を表す文字列の配列（1 件以上）。各要素は
  "spot:<場所のspot_id>" または "player:<相手の名前>" のいずれかの形式
  （例: ["spot:12", "player:カイト"]）。入力の location.spot_id や who に
  実在するものだけを使い、新たに創作しない
- tick_offset_from / tick_offset_to: 解決が見込まれるまでの、今からの
  tick 数（0 以上の整数、tick_offset_to は tick_offset_from 以上）。
  正確な数値が分からない場合はおおよその見積もりでよいが、時刻の見当が
  全くつかない場合は pending_prediction 全体を null にする

pending_resolutions は、ユーザメッセージに【保留中の約束】節がある場合に、
その約束のうちこの chunk で決着がついたものだけを記す配列（無ければ空配列
[]）。当該節が無い場合はこの指示を無視して [] にする。各要素は次の 2 キーの
オブジェクト:
- pending_id: 【保留中の約束】節に添えられた id をそのまま写す
- verdict: "fulfilled"（果たされた）または "broken"（破られた）のいずれか。
  **どちらとも判断がつかない約束は配列に含めない**（曖昧なら黙って保留の
  ままにする）"""


# P9 (伝聞): HEARSAY_ENABLED が ON のときだけ append する節。key list の数字は
# 変えず「さらにキー heard_claims を加える」と明示する (pending との組み合わせで
# key list 定数が組合せ爆発するのを避ける追記方式)。flag OFF では一切出ない
# (byte 不変)。
_HEARD_CLAIMS_INSTRUCTION = """

さらに、JSON にキー heard_claims を加える。heard_claims は、この期間に他者が
「世界や人がどうであるか」(場所・物事・人物) について語った主張の配列。その場に
いない人についての話 (噂話) も含む。挨拶・依頼・感想は含めない。誰の発言か
具体的な名前で特定できるものだけを入れ、無ければ null。各要素は次の 2 キー:
- speaker: 主張を語った人物の**具体的な名前**。「不明」「誰か」「声」のような
  プレースホルダは禁止。名前が特定できない発言はこの配列に入れない
- claim: その人が語った「世界や人がどうであるか」の主張 1 文"""


# P9: 話者が特定できないときに LLM が入れがちなプレースホルダ。プロンプトでも
# 禁じるが、指示を無視して入れてきた場合の決定論的な最後の砦としてここで弾く
# (「話者が特定できる伝聞だけを積む」を構造で保証する)。casefold 済みで比較。
_HEARSAY_PLACEHOLDER_SPEAKERS = frozenset(
    {"不明", "誰か", "だれか", "声", "someone", "unknown", "?", "？", "n/a", "none"}
)


def _normalize_heard_claims(raw: Any) -> tuple[HeardClaim, ...]:
    """LLM 出力の ``heard_claims`` 配列を ``HeardClaim`` のタプルに正規化する (P9)。

    null / 非配列 → 空タプル。各要素は dict で speaker / claim が非空 str の
    ものだけ採る (speaker 欠落は捨てる = 話者を特定できない主張は伝聞にしない)。
    speaker が「不明」等のプレースホルダのものも捨てる (話者不明の主張を伝聞に
    しない = 誰から来た情報か分からない証拠を台帳に残さない)。
    """
    if not isinstance(raw, list):
        return ()
    out: list[HeardClaim] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        speaker = item.get("speaker")
        claim = item.get("claim")
        if not isinstance(speaker, str) or not speaker.strip():
            continue
        if speaker.strip().casefold() in _HEARSAY_PLACEHOLDER_SPEAKERS:
            continue
        if not isinstance(claim, str) or not claim.strip():
            continue
        try:
            out.append(HeardClaim(speaker=speaker, claim=claim))
        except Exception:
            continue
    return tuple(out)


def _build_system_prompt(
    *,
    salience_enabled: bool,
    unconscious_context_enabled: bool = False,
    error_gated_encoding_enabled: bool = False,
    pending_prediction_enabled: bool = False,
    hearsay_enabled: bool = False,
) -> str:
    """salience 節 / 無意識コンテキスト節 / 誤差ゲート付き解像度指示 /
    pending prediction 節を条件付きで足した system prompt を組み立てる。

    全 flag が OFF のときは ``_SYSTEM_EPISODE_SUBJECTIVE_JSON`` をそのまま返す
    (= 既定 prompt が byte 不変であることをここで保証する)。

    U8 の解像度指示 (recall_text 長さの salience 連動) は salience_enabled が
    True のときだけ意味を持つ (salience 自体が無ければ連動先が無い)。
    salience_enabled=False のときは error_gated_encoding_enabled の値に関わらず
    元の一律長さ指示のまま。
    """
    if not salience_enabled:
        base = _SYSTEM_EPISODE_SUBJECTIVE_JSON
    else:
        assert _SALIENCE_KEY_LIST_OLD in _SYSTEM_EPISODE_SUBJECTIVE_JSON
        with_new_keys = _SYSTEM_EPISODE_SUBJECTIVE_JSON.replace(
            _SALIENCE_KEY_LIST_OLD, _SALIENCE_KEY_LIST_NEW
        )
        if error_gated_encoding_enabled:
            assert _RECALL_LENGTH_INSTRUCTION_OLD in with_new_keys
            with_new_keys = with_new_keys.replace(
                _RECALL_LENGTH_INSTRUCTION_OLD, _RECALL_LENGTH_INSTRUCTION_NEW
            )
        base = with_new_keys + _SALIENCE_INSTRUCTION
    if pending_prediction_enabled:
        key_list_old = _SALIENCE_KEY_LIST_NEW if salience_enabled else _SALIENCE_KEY_LIST_OLD
        key_list_new = (
            _PENDING_KEY_LIST_WITH_SALIENCE_NEW
            if salience_enabled
            else _PENDING_KEY_LIST_BASE_NEW
        )
        assert key_list_old in base
        base = base.replace(key_list_old, key_list_new) + _PENDING_PREDICTION_INSTRUCTION
    if hearsay_enabled:
        base = base + _HEARD_CLAIMS_INSTRUCTION
    if unconscious_context_enabled:
        return base + _UNCONSCIOUS_CONTEXT_INSTRUCTION
    return base


_MAX_SUBJECTIVE_FIELD_CHARS = 700
# heading は afterglow index で並べる 1 行見出し。長すぎると視認性を損ね、
# prompt も嵩むため切り詰める。30 文字は「行動 + 印象的な 1 要素」を入れる
# 余裕としてユーザとの議論で合意した上限。
_MAX_HEADING_CHARS = 30


def _normalize_heading(raw: Any) -> str | None:
    """LLM 出力の heading を value object に渡せる形に揃える。

    - None / 非 str / 空白のみ → None
    - 長すぎる → ``_MAX_HEADING_CHARS`` 文字で切り詰め、末尾に「…」
    後続の SubjectiveEpisode コンストラクタはここで None / 非空 str だけを
    受け取る前提のため、空文字を許さない既存の Optional フィールド規約と
    整合する。
    """
    if raw is None or not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if len(stripped) <= _MAX_HEADING_CHARS:
        return stripped
    return stripped[: _MAX_HEADING_CHARS - 1].rstrip() + "…"


def _truncate(label: str, raw: str, *, max_chars: int) -> str:
    text = raw.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _format_draft_facts(ep: SubjectiveEpisode) -> str:
    cues_lines = "\n".join(c.to_canonical() for c in ep.cues)
    loc = ep.location
    loc_parts = [
        f"spot_id={loc.spot_id}",
        f"tile_area_ids={tuple(loc.tile_area_ids)}",
        f"sub_location_id={loc.sub_location_id}",
        f"xyz=({loc.x},{loc.y},{loc.z})",
    ]
    action_line = "(なし)"
    if ep.action is not None:
        aa = ep.action.canonical_arguments_text or ""
        action_line = f"tool_name={ep.action.tool_name}; args={aa}"
    lines = [
        f"what: {ep.what}",
        f"expected (行動前の予測):\n{ep.expected if ep.expected else '(なし)'}",
        f"observed (統一タイムライン):\n{ep.observed}",
        f"outcome: {ep.outcome}",
        f"who: {', '.join(ep.who) if ep.who else '(なし)'}",
        f"location: {'; '.join(loc_parts)}",
        f"action: {action_line}",
        f"cues (canonical):\n{cues_lines if cues_lines else '(なし)'}",
    ]
    return "\n".join(lines)


def _format_source_facts(encoding_input: ChunkEncodingInput) -> str:
    obs_lines: list[str] = []
    for o in sorted(encoding_input.observations, key=lambda e: _as_utc(e.occurred_at)):
        cat = o.output.observation_category
        gt = o.game_time_label or ""
        obs_lines.append(
            f"- occurred_at={o.occurred_at.isoformat()}; category={cat}; game_time={gt!s}"
        )
    for o in sorted(
        encoding_input.observation_overflow_from_window,
        key=lambda e: _as_utc(e.occurred_at),
    ):
        cat = o.output.observation_category
        obs_lines.append(
            f"- [window_overflow] occurred_at={o.occurred_at.isoformat()}; category={cat}"
        )
    act_lines: list[str] = []
    for a in sorted(encoding_input.action_results, key=lambda e: _as_utc(e.occurred_at)):
        tn = a.tool_name or ""
        act_lines.append(
            f"- occurred_at={a.occurred_at.isoformat()}; tool={tn!s}; "
            f"success={a.success:d}; action_summary={a.action_summary!s}; "
            f"result_summary={a.result_summary!s}; error_code={a.error_code!s}"
        )
    return "観測メタ（本文は含めない）:\n" + (
        "\n".join(obs_lines) if obs_lines else "(なし)"
    ) + "\n\n行動結果（ソース事実）:\n" + ("\n".join(act_lines) if act_lines else "(なし)")


def compute_template_interpreted(what: str) -> str:
    """``interpreted`` のテンプレ既定値。``what`` をそのまま (長すぎれば省略)。

    LLM 補完が走らない / 走ったが失敗したケースで使う。``ChunkEpisodeDraftBuilder``
    が draft 構築時に埋める用途にも使えるよう、`SubjectiveEpisode` ではなく
    生文字列で受ける形にしている。
    """
    return _truncate("interpreted_fallback", what, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def compute_template_recall(observed: str, what: str) -> str:
    """``recall_text`` のテンプレ既定値。

    ``observed`` (統一タイムラインの bullet 連結) の最初の非空行を 1 件抜き出し、
    なければ ``what`` で代替する。LLM 補完が無いとき / 失敗したときのフォールバック
    として、また draft 時点で「最低限なにか文がある」状態にするために使う。
    """
    for raw_line in observed.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if line:
            return _truncate("recall_fallback", line, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)
    return _truncate("recall_fallback", what, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def _template_interpreted(ep: SubjectiveEpisode) -> str:
    return compute_template_interpreted(ep.what)


def _template_recall(ep: SubjectiveEpisode) -> str:
    return compute_template_recall(ep.observed, ep.what)


def _normalize_llm_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return _truncate("llm_field", stripped, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def _merge_picks(
    *,
    llm_value: str | None,
    fallback: str,
) -> str:
    return llm_value if llm_value is not None else fallback


_VALID_SALIENCE_VALUES = ("low", "high")


def _normalize_salience(raw: Any) -> str:
    """LLM 出力の salience を "low"/"high" に正規化する。

    欠損・非 str・不正な値 (typo 等) は全て "low" に倒す (parse 失敗時は
    「一撃学習を起動しない」= 安全側に倒れる方針)。
    """
    if not isinstance(raw, str):
        return "low"
    normalized = raw.strip().lower()
    if normalized in _VALID_SALIENCE_VALUES:
        return normalized
    return "low"


# LLM が返す tick offset の妥当上限と最小窓幅。chunk 主観補完 LLM には
# 「今から何 tick 後か」だけを書かせているが、LLM は tick の尺度を知らず、
# 「夕方」を分 (1440) のような巨大値で返すことがある (L2 replay で観測)。
# 巨大な tick_offset_to は「窓が永遠に開いたまま = tick 失効が効かない」
# 退化を招き、逆に極端に狭い窓 (from==to) は「再浮上する前に窓が過ぎ去る」
# を招く。そこで抽出時に窓の起点・終点を近い将来の上限へクランプし、
# 最小幅を確保して両極を防ぐ。上限値は 140 tick 級の run で「果たされな
# かった約束が run 内に失効する」ことを担保する経験則で、M-run で調整可。
_PENDING_TICK_OFFSET_MAX = 30
_PENDING_TICK_WINDOW_MIN = 3


def _clamp_pending_tick_offsets(tick_offset_from: int, tick_offset_to: int) -> tuple[int, int]:
    """tick offset を妥当範囲へクランプする。

    - 上限 ``_PENDING_TICK_OFFSET_MAX`` を超える値は上限に丸める
    - クランプ後に窓が ``_PENDING_TICK_WINDOW_MIN`` 未満なら終点を広げる

    クランプは「有効な (from<=to かつ from>=0 の) 範囲を狭める / 最小幅を
    確保する」だけに留める。反転 (from>to) や負値はここで補正せず、そのまま
    後段の VO バリデーションに委ねて従来どおり None に落とす (壊れた出力を
    黙って「もっともらしい約束」に化けさせない)。
    """
    from_c = min(tick_offset_from, _PENDING_TICK_OFFSET_MAX)
    to_c = min(tick_offset_to, _PENDING_TICK_OFFSET_MAX)
    if from_c <= to_c and to_c - from_c < _PENDING_TICK_WINDOW_MIN:
        to_c = from_c + _PENDING_TICK_WINDOW_MIN
    return from_c, to_c


def _normalize_pending_prediction(raw: Any) -> PendingPredictionDraft | None:
    """LLM 出力の ``pending_prediction`` object を ``PendingPredictionDraft`` に

    正規化する。null / 非 object / 必須キー欠落 / 型不正 / VO のバリデーション
    違反 (resolution_cues の形式不正・tick 範囲逆転など) は全て None に倒す
    (= 「約束なし」と同じ扱い。乱発防止の指示を無視した壊れた出力を安全側で
    捨てる)。tick offset は ``_clamp_pending_tick_offsets`` で妥当範囲へ
    クランプしてから VO に渡す (LLM が tick 尺度を誤って巨大値を返す問題への
    防御。詳細は同関数の docstring)。
    """
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    raw_cues = raw.get("resolution_cues")
    if not isinstance(raw_cues, (list, tuple)):
        return None
    cues: list[str] = []
    for c in raw_cues:
        if not isinstance(c, str) or not c.strip():
            return None
        cues.append(c.strip())
    tick_offset_from = raw.get("tick_offset_from")
    tick_offset_to = raw.get("tick_offset_to")
    if isinstance(tick_offset_from, bool) or isinstance(tick_offset_to, bool):
        return None
    if not isinstance(tick_offset_from, int) or not isinstance(tick_offset_to, int):
        return None
    tick_offset_from, tick_offset_to = _clamp_pending_tick_offsets(
        tick_offset_from, tick_offset_to
    )
    try:
        return PendingPredictionDraft(
            text=text,
            resolution_cues=tuple(cues),
            tick_offset_from=tick_offset_from,
            tick_offset_to=tick_offset_to,
        )
    except PendingPredictionValidationException:
        return None


def _normalize_pending_resolutions(
    raw: Any, valid_pending_ids: frozenset[str]
) -> tuple[PendingResolutionVerdict, ...]:
    """LLM 出力の ``pending_resolutions`` 配列を ``PendingResolutionVerdict`` の

    tuple に正規化する。

    安全側の縮退 (壊れた要素は黙って捨てる):
    - null / 非配列 → 空タプル
    - 要素が非 object / pending_id 欠落・非 str / verdict が
      "fulfilled"/"broken" 以外 → その要素を捨てる
    - ``valid_pending_ids`` (= この chunk で prompt に載せた約束の id 群) に
      含まれない pending_id → 捨てる (存在しない約束を LLM が創作しても
      清算しない)
    - 同一 pending_id の重複 → 先勝ち (最初の判定を採用)
    """
    if not isinstance(raw, (list, tuple)):
        return ()
    verdicts: list[PendingResolutionVerdict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = item.get("pending_id")
        verdict = item.get("verdict")
        if not isinstance(pid, str) or not pid.strip():
            continue
        pid = pid.strip()
        if pid not in valid_pending_ids or pid in seen:
            continue
        try:
            v = PendingResolutionVerdict(pending_id=pid, verdict=verdict)
        except PendingPredictionValidationException:
            continue
        seen.add(pid)
        verdicts.append(v)
    return tuple(verdicts)


def _structured_prediction_error_fallback(
    draft: SubjectiveEpisode,
    encoding_input: ChunkEncodingInput,
) -> str | None:
    """LLM 不在・失敗時の保守的な prediction_error。

    予測 (expected) があり、かつ chunk に構造的な失敗 (success=False の action) が
    含まれるときだけ、最小限の乖離を残す。「成功したが予測と違う」のような意味的な
    食い違いは LLM 判断が要るので、ここでは扱わない (= None)。誤った驚きを
    捏造しないため、構造的に観測できる差分のみに限定する。
    """
    if not (isinstance(draft.expected, str) and draft.expected.strip()):
        return None
    if not any(not a.success for a in encoding_input.action_results):
        return None
    return "予測していたが、行動の一部が失敗した。"


class EpisodicChunkSubjectiveFieldsService:
    """
    ルール草案へ interpreted / recall_text / prediction_error を付与する。

    interpreted / recall_text は LLM 失敗・不正 JSON 時に what / observed 由来の
    テンプレへ落とす。prediction_error (= 予測と結果の質的乖離) は LLM が判断し、
    LLM 値が無いときは構造的失敗のみの保守 fallback (それも無ければ None)。
    """

    def __init__(
        self,
        completion: IEpisodicChunkSubjectiveCompletionPort,
        *,
        salience_enabled: bool = False,
        unconscious_context_provider: Optional[
            Callable[[int, Sequence[EpisodicCue]], str]
        ] = None,
        unconscious_context_enabled: bool = False,
        error_gated_encoding_enabled: bool = False,
        pending_prediction_enabled: bool = False,
        hearsay_enabled: bool = False,
    ) -> None:
        if not isinstance(completion, IEpisodicChunkSubjectiveCompletionPort):
            raise TypeError("completion must implement IEpisodicChunkSubjectiveCompletionPort")
        if not isinstance(salience_enabled, bool):
            raise TypeError("salience_enabled must be bool")
        if unconscious_context_provider is not None and not callable(
            unconscious_context_provider
        ):
            raise TypeError("unconscious_context_provider must be callable or None")
        if not isinstance(unconscious_context_enabled, bool):
            raise TypeError("unconscious_context_enabled must be bool")
        if not isinstance(error_gated_encoding_enabled, bool):
            raise TypeError("error_gated_encoding_enabled must be bool")
        if not isinstance(pending_prediction_enabled, bool):
            raise TypeError("pending_prediction_enabled must be bool")
        if not isinstance(hearsay_enabled, bool):
            raise TypeError("hearsay_enabled must be bool")
        self._completion = completion
        self._salience_enabled = salience_enabled
        # U7 (予測誤差統一設計 / 無意識コンテキスト): 「配線 (wire) と有効化
        # (enable) の分離」規約に従い、provider は常に受け取れるが
        # unconscious_context_enabled が False の間は一切呼び出さない
        # (= 未注入時と完全に同一の挙動)。
        self._unconscious_context_provider = unconscious_context_provider
        self._unconscious_context_enabled = unconscious_context_enabled
        # U8 (予測誤差統一設計 部品2b / default False = flag OFF): True のとき
        # だけ recall_text の長さ指示を salience 連動に差し替える。False
        # (既定) では U6 導入時の一律長さ指示のまま (byte 不変)。
        self._error_gated_encoding_enabled = error_gated_encoding_enabled
        # U10a (予測誤差統一設計 部品6・pending prediction / default False =
        # flag OFF): True のときだけ pending_prediction キーを system prompt に
        # 足し、応答を PendingPredictionDraft として episode に載せる。False
        # (既定) では pending_prediction_draft は常に None (= 導入前と byte 一致)。
        self._pending_prediction_enabled = pending_prediction_enabled
        # P9 (伝聞 / default False = flag OFF): True のときだけ heard_claims キーを
        # system prompt に足し、応答を HeardClaim として episode に載せる。False
        # (既定) では heard_claims は常に空タプル (= 導入前と byte 一致)。
        self._hearsay_enabled = hearsay_enabled
        self._logger = logging.getLogger(self.__class__.__name__)

    def merge_llm_subjective_fields(
        self,
        draft: SubjectiveEpisode,
        *,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> SubjectiveEpisode:
        """
        LLM で interpreted / recall_text / prediction_error を埋め合わせる。

        interpreted / recall_text は LLM 失敗・不正 JSON 時に what / observed 由来の
        テンプレへフォールバックする。prediction_error は LLM 値が無ければ構造的
        失敗のみの保守 fallback (それも無ければ None = 予測どおり / 予測なし)。
        """
        if not isinstance(draft, SubjectiveEpisode):
            raise TypeError("draft must be SubjectiveEpisode")
        if not isinstance(persona_text, str):
            raise TypeError("persona_text must be str")
        if not isinstance(encoding_input, ChunkEncodingInput):
            raise TypeError("encoding_input must be ChunkEncodingInput")

        fallback_i = _template_interpreted(draft)
        fallback_r = _template_recall(draft)
        _pending_sample = (
            ', "pending_prediction": {"text": "...", "resolution_cues": '
            '["spot:...", "player:..."], "tick_offset_from": 0, '
            '"tick_offset_to": 0}, "pending_resolutions": '
            '[{"pending_id": "...", "verdict": "fulfilled"}]'
            if self._pending_prediction_enabled
            else ""
        )
        _hearsay_sample = (
            ', "heard_claims": [{"speaker": "...", "claim": "..."}]'
            if self._hearsay_enabled
            else ""
        )
        _extra_sample = _pending_sample + _hearsay_sample
        response_format = (
            (
                '{"interpreted": "...", "recall_text": "...", "prediction_error": "...", '
                f'"heading": "...", "salience": "low"{_extra_sample}}}'
            )
            if self._salience_enabled
            else (
                '{"interpreted": "...", "recall_text": "...", "prediction_error": "...", '
                f'"heading": "..."{_extra_sample}}}'
            )
        )
        unconscious_context_text = self._resolve_unconscious_context_text(draft)
        user_sections = [
            "## 人物像（ペルソナ断片）",
            persona_text.strip() if persona_text.strip() else "(なし)",
        ]
        # U7 (予測誤差統一設計 / 無意識コンテキスト): flag ON かつ provider が
        # 非空テキストを返したときだけ section を足す。flag OFF はもちろん、
        # ON でも provider 未注入・例外・空文字なら user_sections は導入前と
        # 完全一致する (= 後方互換)。
        if self._unconscious_context_enabled and unconscious_context_text:
            user_sections += [
                "## いまの自分（信念と自己像）",
                unconscious_context_text,
            ]
        # U10b (予測誤差統一設計 部品6・pending prediction 清算): flag ON かつ
        # この chunk 時点で窓が開いた約束が渡っているときだけ【保留中の約束】節を
        # 足す。flag OFF / 約束なしのときは user_sections が U10a 時点と一致する。
        active_pendings = (
            encoding_input.active_pending_predictions
            if self._pending_prediction_enabled
            else ()
        )
        valid_pending_ids = frozenset(p.pending_id for p in active_pendings)
        if active_pendings:
            user_sections += [
                "## 保留中の約束（この chunk で決着したものだけ pending_resolutions に記す）",
                "\n".join(
                    f"- [{p.pending_id}] {p.text}" for p in active_pendings
                ),
            ]
        user_sections += [
            "## ルール草案（事実・索引はここに依存。改変禁止）",
            _format_draft_facts(draft),
            "## ソース事実（検証用メタ。新事実の根拠にしない）",
            _format_source_facts(encoding_input),
            "## 応答形式",
            response_format,
        ]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": _build_system_prompt(
                    salience_enabled=self._salience_enabled,
                    unconscious_context_enabled=self._unconscious_context_enabled,
                    error_gated_encoding_enabled=self._error_gated_encoding_enabled,
                    pending_prediction_enabled=self._pending_prediction_enabled,
                    hearsay_enabled=self._hearsay_enabled,
                ),
            },
            {"role": "user", "content": "\n\n".join(user_sections)},
        ]
        interp_llm: str | None = None
        recall_llm: str | None = None
        pred_err_llm: str | None = None
        heading_llm: str | None = None
        salience: str = "low"
        pending_prediction_draft: PendingPredictionDraft | None = None
        pending_resolution_verdicts: tuple[PendingResolutionVerdict, ...] = ()
        heard_claims: tuple[HeardClaim, ...] = ()
        try:
            raw_obj = self._completion.complete_episode_subjective_json(messages)
            if not isinstance(raw_obj, dict):
                self._logger.warning(
                    "Episode subjective completion returned non-object; using template fallback"
                )
            else:
                interp_llm = _normalize_llm_str(raw_obj.get("interpreted"))
                recall_llm = _normalize_llm_str(raw_obj.get("recall_text"))
                pred_err_llm = _normalize_llm_str(raw_obj.get("prediction_error"))
                # heading は afterglow index 用の 1 行見出し (#526 段階 3 後続)。
                # 失敗時 / 欠落時は None に倒し、SubjectiveEpisode に渡る前に
                # 30 文字へ切り詰める (後続テストで保証)。
                heading_llm = _normalize_heading(raw_obj.get("heading"))
                # U6: flag OFF のときは LLM が誤って salience を返しても無視
                # し、episode.salience は常に "low" のまま (= 導入前と同一
                # 挙動を保証する)。
                if self._salience_enabled:
                    salience = _normalize_salience(raw_obj.get("salience"))
                # U10a: flag OFF のときは LLM が誤って pending_prediction を
                # 返しても無視し、episode.pending_prediction_draft は常に
                # None のまま (= 導入前と同一挙動を保証する)。
                if self._pending_prediction_enabled:
                    pending_prediction_draft = _normalize_pending_prediction(
                        raw_obj.get("pending_prediction")
                    )
                    # U10b: 再浮上中の約束の清算判定。prompt に載せた約束の
                    # id (valid_pending_ids) に絞って正規化する。約束が 1 件も
                    # 渡っていない chunk では valid_pending_ids が空なので、
                    # LLM が何を返しても空タプルに畳まれる。
                    pending_resolution_verdicts = _normalize_pending_resolutions(
                        raw_obj.get("pending_resolutions"), valid_pending_ids
                    )
                # P9: flag OFF のときは LLM が誤って heard_claims を返しても無視
                # し、episode.heard_claims は常に空タプルのまま (= 導入前と同一)。
                if self._hearsay_enabled:
                    heard_claims = _normalize_heard_claims(
                        raw_obj.get("heard_claims")
                    )
        except LlmApiCallException as e:
            self._logger.warning(
                "Episode subjective LLM failed (%s); using template fallback",
                getattr(e, "error_code", "LLM_ERROR"),
            )
        except (TypeError, ValueError) as e:
            self._logger.warning("Episode subjective parse failed; using template fallback: %s", e)
        except Exception as e:
            self._logger.warning("Episode subjective LLM path failed; using template fallback: %s", e)

        interpreted = _merge_picks(llm_value=interp_llm, fallback=fallback_i)
        recall_text = _merge_picks(llm_value=recall_llm, fallback=fallback_r)
        # prediction_error は str/None 両方ありうる (予測どおり=None)。LLM 値が
        # 無ければ構造的差分のみの保守 fallback (失敗時 None)。
        prediction_error = (
            pred_err_llm
            if pred_err_llm is not None
            else _structured_prediction_error_fallback(draft, encoding_input)
        )
        merged = replace(
            draft,
            interpreted=interpreted,
            recall_text=recall_text,
            prediction_error=prediction_error,
            heading=heading_llm,
            salience=salience,
            pending_prediction_draft=pending_prediction_draft,
            pending_resolution_verdicts=pending_resolution_verdicts,
            heard_claims=heard_claims,
        )
        self._assert_rule_fields_unchanged(draft, merged)
        return merged

    def _resolve_unconscious_context_text(self, draft: SubjectiveEpisode) -> str:
        """U7: provider を呼んで「## いまの自分」section の本文を取得する。

        flag OFF・provider 未注入・provider の例外・非 str 戻り値・空文字は
        すべて空文字に縮退させる (= chunk 補完を止めない / 後方互換を保つ)。
        """
        if not self._unconscious_context_enabled or self._unconscious_context_provider is None:
            return ""
        try:
            raw_text = self._unconscious_context_provider(draft.player_id, draft.cues)
        except Exception as e:
            self._logger.warning(
                "unconscious_context_provider failed for player_id=%s; "
                "degrading to empty context: %s",
                draft.player_id,
                e,
            )
            return ""
        if not isinstance(raw_text, str):
            return ""
        return raw_text.strip()

    def _assert_rule_fields_unchanged(self, draft: SubjectiveEpisode, merged: SubjectiveEpisode) -> None:
        if merged.observed != draft.observed:
            raise ValueError("observed must remain unchanged after subjective merge")
        if merged.cues != draft.cues:
            raise ValueError("cues must remain unchanged after subjective merge")
        if merged.who != draft.who:
            raise ValueError("who must remain unchanged after subjective merge")
        if merged.what != draft.what:
            raise ValueError("what must remain unchanged after subjective merge")
        if merged.outcome != draft.outcome:
            raise ValueError("outcome must remain unchanged after subjective merge")


__all__ = ["EpisodicChunkSubjectiveFieldsService"]
