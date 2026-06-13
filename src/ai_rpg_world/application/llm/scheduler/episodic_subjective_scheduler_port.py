"""エピソード記憶の LLM 主観文付与を「いつ・どこで」実行するかを抽象化する Port。

# 何のため

PR #307 で escape_game に LLM 主観文付与 (`EpisodicChunkSubjectiveFieldsService`)
を配線したが、同期実行のためゲーム tick が LLM レイテンシ (1〜3 秒) ぶん
止まる。プレイヤー数が増えると 1 tick 内の chunk 数も増え、累積で体感に響く。

第22回実験議論で合意した **Pattern A: Fire-and-forget + eventual consistency**
の方針に従い、chunk_coordinator は「draft (テンプレで埋まった episode) を
即座に store に書き、scheduler に LLM 補完を投げて返ってくる」だけにする。
ワーカーが裏で LLM を呼び、完了したら同じ episode_id で store を上書きする。

# 一貫性

- ``episode_store.put(...)`` は episode_id 単位の上書きセマンティクス。
  draft → LLM 完了の上書きはアトミックに見える。
- 完了が即時 recall に間に合わなくても、PR #305 のテンプレ既定値が draft に
  入っているので prompt には常に何か文字が乗る。
- sliding window から外れる前 (実測 30-90 秒の SLA) に LLM が完了すれば、
  実用上「想起時にはリッチ化された文章が読める」状態になる。

# Port が他用途と独立な理由

「観測 prose のリッチ化」「想起後の再解釈」など他の非同期化候補は、
入出力の型もフォールバック戦略も異なるため、共通 Port にまとめると意味が
薄れる。底にあるスレッドプール / asyncio queue は実装で共有して構わないが、
Port は用途ごとに切るのが本プロジェクトの方針 (YAGNI)。
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ai_rpg_world.application.llm.contracts.chunk_encoding import ChunkEncodingInput
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


@runtime_checkable
class IEpisodicSubjectiveCompletionScheduler(Protocol):
    """LLM 主観文付与の実行をスケジュールする抽象。

    ``submit`` は非ブロッキングを想定する (= draft の処理が呼び出し元の
    制御フローから切り離されていること)。同期実装 (``InlineScheduler``) を
    渡すと従来の同期動作と等価になる。

    Methods:
        submit: 1 chunk 分の LLM 補完ジョブを投入する。drafted 段階の episode は
            既に ``episode_store`` に書かれている前提なので、Scheduler 側で改めて
            put する必要はない。Scheduler が完了時に LLM 結果で **同じ episode_id
            の episode を上書き** する責任を持つ。
        shutdown: 進行中ジョブをキャンセル or drain する。``timeout`` 秒待っても
            終わらないジョブは諦めて落ちる (= テンプレが残るだけで損失は限定的)。
    """

    def submit(
        self,
        draft: SubjectiveEpisode,
        *,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> None:
        ...

    def shutdown(self, timeout: Optional[float] = None) -> None:
        ...


__all__ = ["IEpisodicSubjectiveCompletionScheduler"]
