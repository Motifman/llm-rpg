"""create_llm_agent_wiring 用の Config dataclass 群。

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
from typing import Any, Optional

from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)


@dataclass(frozen=True)
class SnsWiringConfig:
    """SNS / 仮想 SNS 画面関連の wiring 引数を 1 つに束ねる Config (HIGH-4 Step 8b)。

    SNS は元々「ゲーム内 SNS アプリ」として 10 個の関連サービスが配線されており、
    docstring に「同一インスタンスを渡せ」型の暗黙ルールが散らばっていた。本 Config
    は 1 箇所に集約し、必要に応じて ``__post_init__`` で配線制約を assert する。

    fields:
    - command 系 4 個: post / reply / user / notification
    - query 系 4 個: post_query / sns_page_query / reply_query / notification_query
    - session 系 2 個: mode_session (SNS / Trade 排他的なアプリスロット用)
      / page_session (仮想 SNS 画面状態)

    全 Optional。未注入なら該当機能は無効。
    """

    post_service: Optional[Any] = None
    reply_service: Optional[Any] = None
    user_command_service: Optional[Any] = None
    notification_command_service: Optional[Any] = None
    post_query_service: Optional[Any] = None
    sns_page_query_service: Optional[Any] = None
    reply_query_service: Optional[Any] = None
    notification_query_service: Optional[Any] = None
    mode_session: Optional[Any] = None
    page_session: Optional[Any] = None

    def __post_init__(self) -> None:
        # Issue #227 後続レビュー HIGH-5: 元 docstring の「同一インスタンス渡せ」型の
        # 配線制約を実行時 assert で表現する。誤配線時に silent drift にならないよう、
        # 検出可能なケースだけ最小限チェックする (深い isinstance 比較はしない)。
        #
        # ルール 1: page_session が設定されているなら mode_session も必要
        #   (page_session は SNS モード ON 時のみ意味を持つため)。
        if self.page_session is not None and self.mode_session is None:
            raise ValueError(
                "SnsWiringConfig: page_session を渡すなら mode_session も必須 "
                "(SNS モード ON でないと仮想 SNS 画面は動かない)"
            )


@dataclass(frozen=True)
class TradeWiringConfig:
    """取引 / 仮想取引画面関連の wiring 引数を 1 つに束ねる Config (HIGH-4 Step 8c)。

    fields:
    - command_service: 取引コマンド (trade_offer 等) の application service
    - page_session: 仮想取引画面のセッション
    - page_query_service: 仮想取引画面のスナップショット取得

    page_session は SNS と同様「アプリスロット」を共有するため、SNS と同じ
    sns_mode_session を持ち回るルールがある (詳細は __init__.py の docstring)。
    """

    command_service: Optional[Any] = None
    page_session: Optional[Any] = None
    page_query_service: Optional[Any] = None


@dataclass(frozen=True)
class GameRepositoriesConfig:
    """ゲーム系リポジトリの Optional 集合 (HIGH-4 Step 8c)。

    各リポジトリは個別のゲーム機能 (item / monster / quest / shop / trade /
    guild / hit_box / skill 系 / spot / spot_graph) を担当する。全 Optional で、
    未注入なら該当機能が disable される。

    本 Config は「リポジトリ群を持ち運ぶ」コンテナで、それぞれは独立した
    アグリゲートに紐付くため __post_init__ 制約は持たない。
    """

    item_repository: Optional[Any] = None
    item_spec_repository: Optional[Any] = None
    monster_repository: Optional[Any] = None
    monster_template_repository: Optional[Any] = None
    quest_repository: Optional[Any] = None
    shop_repository: Optional[Any] = None
    trade_repository: Optional[Any] = None
    guild_repository: Optional[Any] = None
    hit_box_repository: Optional[Any] = None
    skill_loadout_repository: Optional[Any] = None
    skill_deck_progress_repository: Optional[Any] = None
    skill_spec_repository: Optional[Any] = None
    sns_user_repository: Optional[Any] = None
    spot_repository: Optional[Any] = None
    spot_graph_repository: Optional[Any] = None


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

    episode_store: Optional[EpisodicEpisodeRepository] = None
    recall_buffer_store: Optional[EpisodicRecallBufferRepository] = None
    reinterpretation_journal_store: Optional[EpisodicReinterpretationJournalRepository] = None
    reinterpretation_completion: Optional[IEpisodicReinterpretationCompletionPort] = None
    chunk_episode_draft_builder: Optional[ChunkEpisodeDraftBuilder] = None
    chunk_coordinator: Optional[EpisodicChunkCoordinator] = None
    chunk_subjective_completion: Optional[IEpisodicChunkSubjectiveCompletionPort] = None
