"""create_llm_agent_wiring / create_spot_graph_wiring 用の Config dataclass 群。

Issue #227 後続レビュー HIGH-4 改善: 両 factory の 100+ 引数を機能ごとの dataclass に
グループ化し、シグネチャの認知負荷を下げる。各 Config は機能の塊として独立しており、
未使用なら丸ごと省略できる。

段階的導入:
- EpisodicWiringConfig: episodic memory 関連 7 field (Step 8a)
- 今後: SnsWiringConfig / TradeWiringConfig / RepositoriesConfig 等

caller は既存 kwargs と新 Config を同時に渡せる移行期 API は採用せず、Config の
新規導入と同時に caller を更新する (clean break 方式)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationCompletionPort,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)


@dataclass(frozen=True)
class EpisodicWiringConfig:
    """episodic memory 関連の wiring 引数を 1 つに束ねる Config (HIGH-4 Step 8a)。

    全フィールド Optional。default は「全て未注入 = in-memory ストアで自動配線」。

    fields:
    - episode_store: 共有 episode store の override。None なら
      resolve_default_episodic_episode_store が SUBJECTIVE_EPISODE_DB_PATH 環境変数を
      見て決める
    - recall_buffer_store / reinterpretation_journal_store: 受動想起 buffer と
      再解釈 journal。両方 None なら同じ default 解決ロジック
    - reinterpretation_completion: 再解釈の LLM 補完 port。None なら default
      (LiteLLM 接続時のみ自動有効)
    - chunk_episode_draft_builder: チャンク草案ビルダーの override (テスト用)
    - chunk_coordinator: チャンク coordinator 全体を差し替える override
      (両 factory での「inner builder を全部置き換えたい」用途)
    - chunk_subjective_completion: チャンクの subjective fields LLM 補完 port
      override
    """

    episode_store: Optional[IEpisodicEpisodeStore] = None
    recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None
    reinterpretation_journal_store: Optional[IEpisodicReinterpretationJournalStore] = None
    reinterpretation_completion: Optional[IEpisodicReinterpretationCompletionPort] = None
    chunk_episode_draft_builder: Optional[ChunkEpisodeDraftBuilder] = None
    chunk_coordinator: Optional[EpisodicChunkCoordinator] = None
    chunk_subjective_completion: Optional[IEpisodicChunkSubjectiveCompletionPort] = None
