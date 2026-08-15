"""会議中のプロンプトが、その場で選べるものだけを見せることを保証する。

## 何が起きていたか

実 run 009 で、会議中のプロンプトが探索中と**まったく同じ**だった。

    接続先: 集会室の扉 → "集会室"（通行可）      ← 会議中は移動できない
    オブジェクト: "配線箱" …                     ← 会議中は触れない
    同じ場所にいるプレイヤー: (give_item で渡せる) ← 会議中は渡せない

「選べるのに必ず失敗する手」を並べない (#860) に真正面から反していた。
実際アオイは会議の最中に棚卸しを進めようとし、思考にも「話し合い中だけど、
私の担当の棚卸しをまず進めたい」と出ていた。

## 判断は 1 か所に置く

各ビルダの中で ``is_meeting`` を見る形は採らない。**今日 2 回踏んだ
「判断が散る」形そのもの**だから (死の観測 / ツールの出し分け)。
``prompt_section_layout`` の表に集める。

## 空間の知識は失わない

Among Us では会議中も地図を見られる。**消えるのは操作であって、空間の
知識ではない。** 見取り図はシステムプロンプトにあるので (#949)、接続先を
落としても推論の材料は残る。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.prompt_section_layout import (
    INTENTIONALLY_UNUSED,
    SECTIONS_BY_PHASE,
    PromptSection,
    sections_for,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _AOI, _HAGI = PlayerId(1), PlayerId(2), PlayerId(4), PlayerId(5)
_YURA, _SAKI = PlayerId(6), PlayerId(8)
#: インポスター。**行動ラベルが出うる唯一の視点。**
_KUZE = PlayerId(3)


@pytest.fixture()
def in_a_meeting():
    runtime = create_world_runtime(_DRILL)
    runtime.call_emergency_meeting(_MORI)
    return runtime


@pytest.fixture()
def free_roam():
    return create_world_runtime(_DRILL)


def _player_rows(text: str, heading: str) -> list[str]:
    """所持品や物体ではなく、指定した人物節の行だけを返す。"""
    lines = text.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith(heading)
    ) + 1
    rows: list[str] = []
    for line in lines[start:]:
        if not line.startswith('  - "'):
            break
        rows.append(line)
    return rows


class TestTheMeetingHidesWhatCannotBeChosen:
    """会議中は、その場で選べない対象が出ない。"""

    @pytest.mark.parametrize(
        "marker", ["接続先:", "オブジェクト:", "give_item"]
    )
    def test_the_unusable_sections_are_gone(self, in_a_meeting, marker) -> None:
        """移動先・オブジェクト・受け渡しの案内が消える。"""
        assert marker not in in_a_meeting.build_observation(_MORI)

    def test_they_are_still_there_during_free_roam(self, free_roam, ) -> None:
        """自由時間では今までどおり出る。

        **消しすぎていないか**を必ず一緒に見る。全部消えてもテストは通る。
        """
        text = free_roam.build_observation(_MORI)

        for marker in ("接続先:", "オブジェクト:", "give_item"):
            assert marker in text

    def test_nothing_shown_is_missing_from_the_toolset(self, in_a_meeting) -> None:
        """本文に出ている案内が、実際に出しているツールと矛盾しない。

        本文とツール一覧が食い違うと、**選べると読めるのに呼べない**。
        #948 で実行は塞いだが、読めてしまう状態は残したくない。
        """
        text = in_a_meeting.build_observation(_MORI)
        offered = {
            d.name
            for d in in_a_meeting.get_tool_definitions(player_id=_MORI)
        }
        names = ("interact", "travel_to", "give_item")
        assert any(name not in offered for name in names), (
            "この節が何も確かめていない"
        )

        for name in names:
            if name not in offered:
                assert name not in text, name


class TestWhatTheMeetingKeeps:
    """会議に要るものは残る。"""

    def test_who_is_here_is_listed(self, in_a_meeting) -> None:
        """この場に居る人が並ぶ。

        **誰に投票できるかを読む唯一の手がかり。** 消すと投票できない。
        """
        text = in_a_meeting.build_observation(_MORI)

        assert "この場に居る人:" in text
        for name in ("セナ", "クゼ", "アオイ", "ハギ"):
            assert name in text

    def test_the_fallen_are_marked(self) -> None:
        """倒れている人がそうと分かる。

        誰が減ったかが分からないと、議論の出発点が無い。
        """
        runtime = create_world_runtime(_DRILL)
        status = runtime._player_status_repo.find_by_id(_SENA)
        status.apply_damage(status.hp.value)
        events = list(status.get_events())
        status.clear_events()
        runtime._player_status_repo.save(status)
        runtime._speech_event_publisher.publish_all(events)
        runtime.call_emergency_meeting(_MORI)

        row = next(
            l for l in runtime.build_observation(_MORI).splitlines() if "セナ" in l
        )

        assert "倒れて" in row or "死亡" in row

    def test_no_action_labels_hang_off_the_names(self, in_a_meeting) -> None:
        """名前に行動が付かない。

        **インポスターの視点で見る。** クルーの行はもともと空 (#921 で
        自分にできない行為を外した) なので、クルーで見ると**行動を消さない
        実装でも通ってしまう**。実際それで変異を取り逃がした。

        自由時間ならこの視点で `[背後から襲う …]` が付く。会議中に付けると
        選べない手を並べることになる。
        """
        rows = _player_rows(
            in_a_meeting.build_observation(_KUZE), "この場に居る人:"
        )

        assert rows
        assert all("[" not in r for r in rows)

    def test_the_impostor_does_see_them_during_free_roam(self, free_roam) -> None:
        """自由時間ならインポスターの行に行動が付く。

        上のテストが「そもそも出ない視点」を見ていないことの担保。
        """
        rows = _player_rows(
            free_roam.build_observation(_KUZE),
            "同じ場所にいるプレイヤー:",
        )

        assert any("[" in r for r in rows)


class TestTheAnnouncementAtTheStart:
    """会議が始まったことと、できることが変わったことを伝える。"""

    def test_everyone_is_told_what_they_can_do_now(self) -> None:
        """開始の観測に、できることが変わった旨が入る。

        状態行は「いまも会議中」を伝えるが、**切り替わりは 1 度きりで、
        そのときに一番強く読まれる**。
        """
        runtime = create_world_runtime(_DRILL)
        before = len(runtime._obs_buffer.get_observations(_SENA))

        runtime.call_emergency_meeting(_MORI)

        prose = " ".join(
            e.output.prose
            for e in runtime._obs_buffer.get_observations(_SENA)[before:]
        )
        assert "話すことと投票だけ" in prose

    def test_it_does_not_name_any_tool(self) -> None:
        """文にツール名を書かない。

        会議で出るツールは世界によって違う。名前を書くと、落とした世界で
        嘘になる (#920)。
        """
        runtime = create_world_runtime(_DRILL)
        before = len(runtime._obs_buffer.get_observations(_SENA))
        runtime.call_emergency_meeting(_MORI)

        prose = " ".join(
            e.output.prose
            for e in runtime._obs_buffer.get_observations(_SENA)[before:]
        )
        for name in ("vote", "speak", "report_body"):
            assert name not in prose


class TestEveryPhaseAndSectionIsAccountedFor:
    """フェーズと節の割り当てに漏れが無い。"""

    def test_every_phase_has_a_layout(self) -> None:
        """全 GamePhase が表に載っている。

        **真偽値で引くと、フェーズが 3 つ目になったときに黙って自由時間へ
        縮退する** (codex の指摘)。新しいフェーズで使えない対象が並び続ける
        ことに誰も気づけない。
        """
        for phase in GamePhase:
            assert phase in SECTIONS_BY_PHASE, phase

    def test_an_unknown_phase_raises(self) -> None:
        """知らないフェーズは例外になる。"""
        with pytest.raises(KeyError):
            sections_for("MEETING")  # type: ignore[arg-type]

    def test_every_section_is_used_somewhere(self) -> None:
        """どの節も、どこかのフェーズに割り当てられている。

        表から漏れた節は**黙って消える**。意図して外すなら
        `INTENTIONALLY_UNUSED` に理由つきで書く。
        """
        assigned = {s for sections in SECTIONS_BY_PHASE.values() for s in sections}

        for section in PromptSection:
            assert section in assigned or section in INTENTIONALLY_UNUSED, section

    def test_free_roam_keeps_its_original_order(self) -> None:
        """自由時間の並びが従来どおり。

        **プレフィックスキャッシュを守るため** (codex の指摘)。順序が変わると
        過去 run とのプロンプト比較も崩れる。

        経済統合 Phase 3 で MARKET_BOARD を MERCHANTS の直後に足した。どちらも
        「いくらで買えるか」を読む節で、所持金と突き合わせる判断も同じ。
        会議中は市場ツールが出ないので、こちらも会議の並びからは落とす。

        経済統合 Phase 2 で TRADE_OFFERS を GOLD の直後に足した。会議中は
        落とす (取引ツールも会議中は出ないので、節だけ残すと「見えるのに手が
        無い」状態になる)。

        経済統合 Phase 1 で MERCHANTS と GOLD を MONSTERS と INVENTORY の間へ
        足した。**従来の 10 節の相対順は 1 つも動かしていない**。新しい 2 節は
        商人を宣言した世界でしか行を出さないので、宣言の無い既存シナリオの
        本文は 1 文字も変わらない (実際の run での確認は
        tests/demos/test_declared_economy_reaches_the_prompt.py が持つ)。
        """
        assert sections_for(GamePhase.FREE_ROAM) == (
            PromptSection.CONNECTIONS,
            PromptSection.OBJECTS,
            PromptSection.SUB_LOCATIONS,
            PromptSection.ENTITIES_WITH_ACTIONS,
            PromptSection.MONSTERS,
            PromptSection.MERCHANTS,
            PromptSection.MARKET_BOARD,
            PromptSection.GOLD,
            PromptSection.TRADE_OFFERS,
            PromptSection.INVENTORY,
            PromptSection.GROUND_ITEMS,
            PromptSection.NEEDS,
            PromptSection.ACTIVE_EFFECTS,
            PromptSection.AGENT_STATUS,
        )


class TestEngineWordsAreGone:
    """engine の語彙がプロンプトに出ない (#892)。"""

    def test_the_meeting_deadline_uses_the_worlds_clock(self, in_a_meeting) -> None:
        """締切が世界の時計の単位で出る。

        地図で直したのと同じ形が、状態行に残っていた。
        """
        line = next(
            l for l in in_a_meeting.build_observation(_MORI).splitlines()
            if "話し合い" in l
        )

        assert "分" in line
        assert "tick" not in line

    def test_the_deadline_says_what_happens_if_nobody_votes(self, in_a_meeting) -> None:
        """投票しないまま終わるとどうなるかを書く。

        run 009 は 6 tick を使い切って 24 回喋り、**投票は 1 票だけ**だった。
        残り回数は出ていたが、**それが何を意味するかが書かれていなかった。**
        """
        line = next(
            l for l in in_a_meeting.build_observation(_MORI).splitlines()
            if "話し合い" in l
        )

        assert "誰も追放されない" in line

    @pytest.mark.parametrize(
        ("player_id", "expected_entries"),
        (
            (
                _MORI,
                (
                    '風向風速計を較正する (観測室の風向風速計 → "calibrate_wind_instruments")',
                    '外気導入路の風量を測る (連絡通路の外気導入路 → "measure_air_intake_flow")',
                ),
            ),
            (
                _SENA,
                (
                    '照明設備の配線を点検する (温室の照明設備 → "inspect_grow_light_wiring")',
                    '本土連絡無線を試験する (通信室の本土連絡無線機 → "test_mainland_radio")',
                ),
            ),
            (
                _AOI,
                (
                    '給食用衛生品を検数する (医務室の給食用衛生品棚 → "count_catering_hygiene_supplies")',
                    '冷蔵庫の密閉を点検する (物資庫の冷蔵庫 → "inspect_cold_storage")',
                ),
            ),
            (
                _HAGI,
                (
                    '燃料ポンプを圧送試験する (燃料庫の燃料ポンプ → "test_fuel_pump")',
                    '発電機を点検する (機関室の発電機 → "check_generator")',
                ),
            ),
            (
                _YURA,
                (
                    '栽培棚の株を選別する (温室の栽培棚 → "select_cultivation_stock")',
                    '加温系の燃料残量を照合する (燃料庫の加温系燃料計 → "reconcile_heating_fuel")',
                ),
            ),
            (
                _SAKI,
                (
                    '観測記録を照合する (観測室の観測記録簿 → "reconcile_observation_records")',
                    '棚卸し帳を照合する (物資庫の棚卸し帳 → "count_supplies")',
                ),
            ),
        ),
    )
    def test_own_state_pairs_every_duty_task_with_its_entry_action(
        self, free_roam, player_id, expected_entries
    ) -> None:
        """一職掌の二作業を、呼び名・場所・物体・入口名つきで状態行へ出す。

        `duty=weather, role=crew` は engine のキーで、読み手はその語で何も
        探せない。途中段や偽装名ではなく、進捗に依存しない入口名を二件とも
        示すことで、最初の一件だけへ縮める後戻りを防ぐ。
        """
        line = next(
            l for l in free_roam.build_observation(player_id).splitlines()
            if l.startswith("自分の状態")
        )

        assert line.count(" → ") == 2
        assert all(expected in line for expected in expected_entries)
        assert "立場: クルー" in line
        assert "duty=" not in line and "role=" not in line
        assert not any(suffix in line for suffix in ("_2\"", "_3\"", "_pretend\""))

    def test_undeclared_state_is_still_shown(self) -> None:
        """呼び名の宣言が無い state は今までどおり出る。

        一度は落とす実装にしたが、それだと `cursed=true` のような自由 state
        を持つ世界で節が丸ごと消えた。**毒や呪いは本人が自己認識するための
        情報**で、消してよいものではない。
        """
        from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (  # noqa: E501
            _render_own_state,
        )

        assert _render_own_state({"cursed": True}, {}) == ["cursed=true"]

    def test_the_atmosphere_line_has_no_enum(self, free_roam) -> None:
        """明るさが enum のまま出ない。"""
        line = next(
            l for l in free_roam.build_observation(_MORI).splitlines()
            if l.startswith("雰囲気")
        )

        assert "明るい" in line
        for raw in ("BRIGHT", "DARK", "DIM"):
            assert raw not in line


class TestEveryEnumValueHasAName:
    """表示辞書が、対応する enum の全件を持っている。

    ## なぜ要るか

    明るさの呼び名を共有定数に出したとき、**表と enum の対応を縛らなかった**。

    - ``LightingEnum`` は 4 件なのに表は 3 件で、``PITCH_BLACK`` だけ生値が
      出た。しかも夜 + 嵐の屋外で実際に到達する。**この仕組みが消しに来た
      生値が、一番暗いときにだけ残っていた**
    - ``気温: WARM`` は 2 行下にあったのに手つかずだった
    - 天候の呼び名が関数の中で組み立てられ、別モジュールにも同じ表があった

    どれも「表を作ったが、抜けを検出する仕組みが無い」1 つの形 (claude の
    指摘)。``PromptSection`` / ``GamePhase`` に付けたのと同じ網羅をここにも
    付ける。

    **特定の値を列挙して「無いこと」を見る形では駄目。** 元のテストは
    ``("BRIGHT", "DARK", "DIM")`` の 3 つしか見ておらず、PITCH_BLACK を
    素通りさせていた。enum 側から引く。
    """

    def test_no_value_is_missing_from_its_table(self) -> None:
        """どの enum 値にも呼び名がある。"""
        from ai_rpg_world.application.llm.services.world_vocabulary import (
            DISPLAY_TABLES,
        )

        for enum_cls, table in DISPLAY_TABLES:
            missing = [e.value for e in enum_cls if e.value not in table]
            assert missing == [], (enum_cls.__name__, missing)

    def test_no_table_has_a_stale_key(self) -> None:
        """表に、enum から消えたキーが残っていない。

        残っていても害は無いが、**消えた概念の呼び名が残っている**のは
        読み手を惑わせる。
        """
        from ai_rpg_world.application.llm.services.world_vocabulary import (
            DISPLAY_TABLES,
        )

        for enum_cls, table in DISPLAY_TABLES:
            known = {e.value for e in enum_cls}
            assert set(table) <= known, (enum_cls.__name__, set(table) - known)

    def test_an_unknown_value_does_not_leak(self) -> None:
        """表に無い値は、生値ではなく空を返す。

        生値を返すと「載せ忘れた」ことが誰にも見えないまま漏れ続ける。
        **行が薄くなるほうが、enum が出るよりまし。**
        """
        from ai_rpg_world.application.llm.services.world_vocabulary import (
            lighting_display,
        )

        assert lighting_display("SOMETHING_NEW") == ""

    def test_the_atmosphere_line_has_no_raw_enum_at_all(self) -> None:
        """雰囲気の行に、どの enum の生値も出ない。

        **生値の集合そのものから作る。** 特定の 3 つを列挙する形だと、
        気温も、次に増える軸も素通りする。
        """
        from ai_rpg_world.application.llm.services.world_vocabulary import (
            DISPLAY_TABLES,
        )

        runtime = create_world_runtime(_DRILL)
        line = next(
            l for l in runtime.build_observation(_MORI).splitlines()
            if l.startswith("雰囲気")
        )

        for enum_cls, _table in DISPLAY_TABLES:
            for member in enum_cls:
                assert member.value not in line, (member.value, line)


class TestTheDeadlineSaysHowManyTurnsAreLeft:
    """締切が、残り時間と残り手番の両方を伝える。"""

    def test_both_the_clock_and_the_turns_are_shown(self, in_a_meeting) -> None:
        """「あと 30 分 (あと 6 回ぶん)」の形で出る。

        run 009 の失敗は「時間」ではなく**手番の読み違い**だった。24 回喋って
        9 回 `wait` が出たのは「待てば次がある」と読んだから。30 分と言われても、
        自分があと何回動けるかは分からない (claude の指摘)。
        """
        line = next(
            l for l in in_a_meeting.build_observation(_MORI).splitlines()
            if "話し合い" in l
        )

        assert "分" in line
        assert "回ぶん" in line
        assert "tick" not in line
