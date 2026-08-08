"""世界 snapshot の codec が、書いただけで登録されないまま残るのを防ぐ。

codec を書いても `_default_world_subsystem_codecs()` に足し忘れると、その
subsystem は **capture も restore もされない**。しかも症状は「長走 run を
再開したら、その state だけ初期値に戻っていた」で、再開してしばらく経って
から気付くことになる。`initial_items` (#830) / `initial_state` (#840) と
同じ「書いたのに使われない」形である。

これまでは codec ごとに
``test_default_world_subsystem_codecs_include_<name>`` を手で足す運用だった。
運用は正しく回っていたが、**足し忘れたことを検出する手段が「足し忘れた本人が
テストを書くこと」に依存している**。ここを構造的な検査に置き換える。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from ai_rpg_world.application.being import world_subsystems
from ai_rpg_world.application.being.experiment_snapshot_session import (
    _default_world_subsystem_codecs,
)

_SUBSYSTEM_DIR = Path(inspect.getfile(world_subsystems)).parent

#: 既定の codec 一覧に載せない codec と、その理由。
#:
#: 新しくここへ足すときは「載せなくても再開が壊れない」理由を書くこと。
#: 「あとで載せる」は理由にならない (それがまさに検出したい状態である)。
_ALLOWED_UNREGISTERED: dict[str, str] = {
    # 旧3形式の読み込み契約を単体で保つ decoder。既定の保存・復元入口は
    # migrate_legacy_recent_event_subsystems で新1形式へ変換してから
    # UnifiedRecentEventStoreSubsystemCodec だけを呼ぶため、登録すると旧形式を
    # 再び保存してしまう。
    "ShortTermMemorySubsystemCodec": "旧 sliding_window payload の decoder",
    "ObservationBufferSubsystemCodec": "旧 observation_buffer payload の decoder",
    "ActionResultStoreSubsystemCodec": "旧 action_result_store payload の decoder",
}


def _codec_class_names_on_disk() -> set[str]:
    """world_subsystems/ で定義されている codec クラス名を集める。

    import せず AST で読む。import すると、登録漏れの codec が副作用で
    登録されてしまう可能性を排除できないため。
    """
    names: set[str] = set()
    for path in _SUBSYSTEM_DIR.glob("*_codec.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("SubsystemCodec"):
                names.add(node.name)
    return names


class TestEveryCodecIsRegistered:
    """定義した codec は既定の一覧に載っている。"""

    def test_no_codec_is_left_out(self) -> None:
        """world_subsystems/ の全 codec が `_default_world_subsystem_codecs` に載る。

        載っていない codec は capture も restore もされない。再開したときに
        その state だけ初期値へ戻る形の静かな失敗になる。
        """
        registered = {type(codec).__name__ for codec in _default_world_subsystem_codecs()}
        on_disk = _codec_class_names_on_disk()

        missing = sorted(on_disk - registered - set(_ALLOWED_UNREGISTERED))

        assert not missing, (
            "codec を書いたのに _default_world_subsystem_codecs() に登録されて"
            "いません。再開時にその state だけ初期値へ戻ります。\n\n  "
            + "\n  ".join(missing)
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        """許可リストに、既に存在しない codec が残っていない。"""
        on_disk = _codec_class_names_on_disk()
        stale = sorted(set(_ALLOWED_UNREGISTERED) - on_disk)
        assert not stale, f"許可リストに存在しない codec が残っています: {stale}"

    def test_the_scan_finds_something(self) -> None:
        """走査そのものが空振りしていない。

        glob のパターンや命名規約が変わると、この検査は「0 件だから合格」と
        いう無害な顔で死ぬ。最低限の件数を要求して、死んだことに気付ける
        ようにする。
        """
        assert len(_codec_class_names_on_disk()) >= 20


class TestRegisteredKeysAreExpected:
    """登録した codec の key が、期待キー一覧にも載っている。

    登録は 2 か所ある (`_default_world_subsystem_codecs` と
    `EXPECTED_WORLD_SUBSYSTEM_KEYS`)。後者を忘れると
    `WorldStateSnapshotCoverageError` が出て**関係の無いテストが大量に落ちる**。
    失敗は loud なので静かな失敗ではないが、原因が読み取りにくい。
    ここで先に落として、どちらの登録が足りないかを名指しする。
    """

    def test_every_registered_codec_key_is_expected(self) -> None:
        """codec の subsystem_key が EXPECTED_WORLD_SUBSYSTEM_KEYS に載る。"""
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            EXPECTED_WORLD_SUBSYSTEM_KEYS,
        )

        registered = [codec.subsystem_key for codec in _default_world_subsystem_codecs()]
        missing = sorted(set(registered) - set(EXPECTED_WORLD_SUBSYSTEM_KEYS))

        assert not missing, (
            "codec は登録されていますが EXPECTED_WORLD_SUBSYSTEM_KEYS に"
            "載っていません。snapshot の網羅検査が落ちます。\n\n  "
            + "\n  ".join(missing)
        )

    def test_no_expected_key_lacks_a_codec(self) -> None:
        """期待キーに、対応する codec が無いものが残っていない。

        codec を消してキーだけ残すと、その subsystem は永久に欠測のまま
        「期待している」と主張し続けることになる。
        """
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            EXPECTED_WORLD_SUBSYSTEM_KEYS,
        )

        registered = {codec.subsystem_key for codec in _default_world_subsystem_codecs()}
        orphaned = sorted(set(EXPECTED_WORLD_SUBSYSTEM_KEYS) - registered)

        assert not orphaned, f"codec の無い期待キーが残っています: {orphaned}"


class TestRegisteredKeysAreUnique:
    """subsystem key が重複していない。

    重複すると、後勝ちで片方の capture が丸ごと消える。
    """

    def test_keys_do_not_collide(self) -> None:
        keys = [codec.subsystem_key for codec in _default_world_subsystem_codecs()]
        assert len(keys) == len(set(keys)), f"subsystem key が重複しています: {keys}"
