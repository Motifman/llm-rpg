"""survival_island_v3_coop に配置した看板 (PR-H) の書き込み→読み取り E2E。

`tests/infrastructure/scenario/test_survival_island_v3_coop_sign_placement.py`
は JSON 構造の静的検証であり、「実際にプレイヤー A が書いた自由テキストを
プレイヤー B が examine で読めるか」はランタイムを起動しないと保証できない。

`application/world_graph/spot_interaction_application_service.py` の
`execute_interaction` を実際の v3_coop scenario 上で叩き、拠点 (campsite) の
「板切れの掲示」で不在の仲間へ書き置きが届く経路を確認する。

（LLM ツールの `interact` は `object_label` / `action_name` の解決を挟む
入口の都合上、本テストは application service を直接叩く — これは既存の
`test_sign_object_app_integration.py` と同じ方針で、v3_coop という実際の
scenario 上で成立することを確認する点が異なる。）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def _create_coop_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=SCENARIOS_DIR,
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name="テスト探索者"))
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id="survival_island_v3_coop", character_ids=[char.id]
        )
    )
    return mgr._sessions[summary.session_id]


def _id_int(runtime, kind: str, str_id: str) -> int:
    return runtime.id_mapper.get_int(kind, str_id)


def _teleport(runtime, player_id_int: int, spot_str_id: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    eid = EntityId.create(player_id_int)
    spot_int = _id_int(runtime, "spot", spot_str_id)
    try:
        graph.unplace_entity(eid)
    except Exception:
        pass
    graph.place_entity(eid, SpotId.create(spot_int))
    runtime._spot_graph_repo.save(graph)


def _player_id(runtime, string_id: str) -> PlayerId:
    for sp in runtime.scenario.player_spawns:
        if sp.string_id == string_id:
            return PlayerId(int(sp.player_id))
    raise AssertionError(f"{string_id} が scenario に存在しない")


class TestCampNoticeBoardCarriesMessageAcrossAbsence:
    """ada が書いた伝言を、居合わせなかった noah が後から読める。"""

    def test_noah_reads_message_ada_wrote_while_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ada が campsite の板切れに書き残し、その場に居なかった noah が
        後から campsite に来て読むと『本文』— エイダ が返る。"""
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        board_id = SpotObjectId.create(_id_int(runtime, "object", "camp_notice_board"))

        # ada は campsite で書き残し、その後 noah が (別の場所から) 訪れる想定。
        _teleport(runtime, int(ada), "campsite")
        write_result = runtime._interaction_service.execute_interaction(
            ada,
            board_id,
            "write_notice",
            interaction_parameters={"text": "山頂ルートは川沿い。合流して。"},
            current_tick=WorldTick(runtime.current_tick()),
        )
        assert write_result.messages == ("板切れの掲示 に書き込んだ。",)

        _teleport(runtime, int(noah), "campsite")
        read_result = runtime._interaction_service.execute_interaction(
            noah,
            board_id,
            "read_notice",
        )

        assert read_result.messages == (
            "『山頂ルートは川沿い。合流して。』 — エイダ",
        )

    def test_unwritten_board_shows_nothing_written(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """誰も書いていない板切れを読むと「何も書かれていない。」になる
        (未記入を silent failure にせず明示するのが #714 の仕様)。"""
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        noah = _player_id(runtime, "noah")
        board_id = SpotObjectId.create(_id_int(runtime, "object", "camp_notice_board"))
        _teleport(runtime, int(noah), "campsite")

        read_result = runtime._interaction_service.execute_interaction(
            noah,
            board_id,
            "read_notice",
        )

        assert read_result.messages == ("何も書かれていない。",)


class TestTrailCairnAtFoothillsForksTowardMountain:
    """山麓の石積みの目印も同じ書き込み→読み取り経路が通る。"""

    def test_write_then_read_round_trip_at_foothills(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        rio = _player_id(runtime, "rio")
        kai = _player_id(runtime, "kai")
        cairn_id = SpotObjectId.create(_id_int(runtime, "object", "trail_cairn"))

        _teleport(runtime, int(rio), "foothills")
        runtime._interaction_service.execute_interaction(
            rio,
            cairn_id,
            "carve_message",
            interaction_parameters={"text": "洞窟の先は崖崩れ、崖沿いへ回れ"},
            current_tick=WorldTick(runtime.current_tick()),
        )

        _teleport(runtime, int(kai), "foothills")
        read_result = runtime._interaction_service.execute_interaction(
            kai,
            cairn_id,
            "read_carving",
        )

        assert read_result.messages == (
            "『洞窟の先は崖崩れ、崖沿いへ回れ』 — リオ",
        )
