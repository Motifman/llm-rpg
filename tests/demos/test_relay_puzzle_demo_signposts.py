"""Issue #171b: relay_puzzle_demo に in-world signpost (ゴール導線) が
組み込まれているかの回帰防止テスト。

LLM が WIN 条件 (ALL_AT_SPOT vault) を「メタ情報の直書き」ではなく、
シナリオ内のオブジェクト・narrative intro から自力で読み取れる状態を維持する。

検証する不変条件:
- ``metadata.llm_public_intro`` に「金庫室」がゴールとして書かれている
- 制御室に「作戦メモ」SIGN が置かれ examine で role-relay の手順が読める
- 廊下に「方角案内板」SIGN が置かれ examine で目的地が明示される
- 金庫室に「到達記録装置」SIGN が置かれ examine で goal 確認の文面が読める
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)


def _load():
    return ScenarioLoader().load_from_file(SCENARIO_PATH)


def _find_object_by_name(loaded, spot_label: str, object_name: str):
    """spot ラベル (例 "control_room") と日本語表示名から interior object を取得。"""
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId

    spot_id = SpotId(loaded.id_mapper.get_int("spot", spot_label))
    interior = loaded.interiors.get(spot_id)
    assert interior is not None, f"spot {spot_label} に interior が無い"
    for obj in interior.objects:
        if obj.name == object_name:
            return obj
    raise AssertionError(
        f"spot {spot_label} に object name={object_name!r} が見つからない"
    )


def _examine_message(obj) -> str:
    """examine インタラクションの SHOW_MESSAGE 文面を取り出す。"""
    for inter in obj.interactions:
        if inter.action_name != "examine":
            continue
        for eff in inter.effects:
            if eff.effect_type.value == "SHOW_MESSAGE":
                return eff.parameters.get("message", "")
    raise AssertionError(f"object {obj.name} に examine→SHOW_MESSAGE が無い")


class TestNarrativeIntro:
    """metadata.llm_public_intro による narrative goal の伝達。"""

    def test_intro_mentions_vault_as_goal(self) -> None:
        """イントロに『金庫室』がゴールとして書かれている。"""
        loaded = _load()
        intro = loaded.metadata.llm_public_intro
        assert "金庫室" in intro
        # 「ゴール」「目指す」「到達」「たどり着く」のいずれかが含まれる
        assert any(kw in intro for kw in ("目指", "到達", "たどり着"))

    def test_intro_hints_at_coordination(self) -> None:
        """イントロに「役割分担」「連携」など co-op を示唆する語が含まれる。"""
        loaded = _load()
        intro = loaded.metadata.llm_public_intro
        assert any(kw in intro for kw in ("役割分担", "連携", "協力"))


class TestControlRoomSignpost:
    """制御室の作戦メモが relay 戦略を示す。"""

    def test_operations_memo_exists(self) -> None:
        obj = _find_object_by_name(_load(), "control_room", "作戦メモ")
        assert obj is not None

    def test_memo_describes_relay_strategy(self) -> None:
        """メモの examine 文面に「電源を入れている間」「制御室に残る」が読み取れる。"""
        msg = _examine_message(_find_object_by_name(_load(), "control_room", "作戦メモ"))
        assert "電源" in msg
        assert any(kw in msg for kw in ("残", "役割"))


class TestCorridorSignpost:
    """廊下の方角案内板が目的地と扉のロック条件を示す。"""

    def test_signboard_exists(self) -> None:
        obj = _find_object_by_name(_load(), "corridor", "方角案内板")
        assert obj is not None

    def test_signboard_mentions_destination_and_lock(self) -> None:
        msg = _examine_message(
            _find_object_by_name(_load(), "corridor", "方角案内板")
        )
        assert "金庫室" in msg
        # 扉のロック条件にも触れている
        assert any(kw in msg for kw in ("ロック", "電源", "通行"))


class TestVaultSignpost:
    """金庫室の到達記録装置が「ここが目的地」と確認できる。"""

    def test_arrival_recorder_exists(self) -> None:
        obj = _find_object_by_name(_load(), "vault", "到達記録装置")
        assert obj is not None

    def test_recorder_confirms_goal(self) -> None:
        msg = _examine_message(
            _find_object_by_name(_load(), "vault", "到達記録装置")
        )
        # 「二人とも到達」=「ALL_AT_SPOT」の自然語表現
        assert "二人" in msg
        assert any(kw in msg for kw in ("到達", "目的地", "任務完了"))
