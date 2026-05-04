# スポットグラフ拡張 TODO

全て実装するとは限らないが、必要な要素の候補をまとめておく。

---

## 脱出ゲームに足りない要素

- [ ] **1. 時間制限 / カウントダウン** — 制限時間やデッドラインの概念
- [x] **2. トラップ（罠）** — PR #53: TrapDef, TrapEvaluationService, TrapTriggeredEvent
- [x] **3. エージェント間の協力要件** — PR #55: PREPARE_ACTION, PreparedActionRegistry, PLAYERS_AT_SPOT
- [x] **4. 情報の非対称性 / エージェント別可視性** — PR #56: SpotPerceptionService, detail_read_by, requires_read
- [x] **5. パズルの状態管理** — PR #54: PuzzleState, PuzzleEvaluationService, INTERACT parameters
- [x] **6. 環境変化のエスカレーション** — PR #57: イベントチェーン, tick_modulo, シナリオローダー対応

基盤: [x] **Effect/Condition 拡張** — PR #52: クロスドメインspec, 新enum, WorldGraphEffectService拡張

---

## 生活シミュレーションに足りない要素

- [ ] **7. スポットの時間スケジュール** — 時間帯による接続の開閉・スポット状態変化
- [x] **8. エージェントの欲求 / 動機システム** — PR #59: AgentNeed/AgentNeeds, PR #60: tick自然増加, PR #61: SATISFY_NEED効果
- [ ] **9. エージェント間関係（好感度・信頼・敵対）** — 対面の関係値
- [ ] **10. スポットの所有 / プライベート空間** — 動的な所有権・アクセス権
- [ ] **11. スポットのキャパシティ（定員）** — SpotPresenceの人数制限
- [ ] **12. 資源の再生・枯渇** — 再生可能リソースの仕組み

---

## スポットグラフの性質を活かした新要素

- [ ] **13. 情報伝播（噂・評判のグラフ拡散）** — 音声伝播の非同期情報伝播への拡張
- [ ] **14. チョークポイント戦略** — グラフの「橋」自動検出、戦略的地点の活用
- [x] **15. 動的な接続の生成・破壊** — PR #58: CREATE/DESTROY_CONNECTION, remove_connection()
- [ ] **16. グラフ距離ベースの影響圏** — ホップ数/travel_ticksベースの勢力圏・認知範囲
- [ ] **17. スポットの「評判」と動的プロパティ** — 行動履歴によるスポットの動的属性
- [ ] **18. 一方通行・非対称コストの活用** — 崖・滑り台等のゲームメカニクス化

---

## インフラ・基盤

- [x] **USE_ITEM ツール** — PR #62: スポットグラフでアイテム消費
- [x] **欲求値 SQLite 永続化** — PR #63: game_player_needs テーブル
- [x] **EventPublisher 導入** — PR #64: スポットグラフにイベント駆動副作用を有効化
- [ ] **ConsumableEffectHandler でアイテム消費→欲求回復** — SatisfyNeedEffect をItemEffectに追加
- [ ] **知覚フィルタのワイヤリング** — light_source_item_spec_ids / owned_item_spec_ids_provider の接続
