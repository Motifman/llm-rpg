# 設計判断 / 設計思想集

本ドキュメントは、実装の **「なぜこの形になっているか」** を集約した参考資料。
新機能を追加するとき、まずここを読んで既存の哲学と衝突しないかを確認する。
日々の実験 (#356 〜 #413 等) を通じて生まれた判断を、コードコメントに散らさず
ここに集める。

新しい判断を追加する場合:
- 「**何を**」「**なぜ**」「**どうしないと壊れるか**」の 3 点セットで書く
- 個別の PR / Issue 番号を添えて trace 可能にする
- 後から「やめた」場合は削除でなく取り消し線で残し、理由を併記する

---

## 1. Prefix cache を守るため、system prompt と tool list は tick 間で不変にする

**何を**: 1 ターン目と 2 ターン目で system prompt の文字列と tool list (= 並び順 + 各 tool の JSON Schema) を **完全一致** させる。

**なぜ**:
- LLM API (OpenAI / Anthropic / litellm 経由の vLLM 等) は、prefix が一致する prompt の入力 token を **キャッシュして実質無料化** する仕組みを持つ。長い system prompt + tool definitions は普通 4-8K token あり、これがキャッシュに乗るか乗らないかで wall time / cost が桁違いになる
- LLM のターンは数百回繰り返されるので、prefix を壊した瞬間に **全 turn が cold cache** になり 1 run のレイテンシが数倍になる

**どうしないと壊れるか**:
- 「疲労 85+ のとき system prompt 末尾に『朦朧としている』を追加する」のような **動的注入** はやらない
- ツールを動的に表示/非表示にする (`if status.fatigue >= 100: tools.pop("travel_to")` 等) もやらない
- 状態依存の情報は **prompt 後半のプレイヤー状態セクション** (= 毎 turn 変わる前提のところ) に乗せる

**どこでこの判断が出てきたか**:
- 実験 #28 / #29 で `cached_tokens=0` (prefix cache hit 0%) を観測 → wall time スパイクの 1 要因
- PR β (疲労ライフサイクル) でユーザ feedback: 「システムプロンプトはなるべく変えないようにしたい」

---

## 2. 致命的に詰む状態を作らない (例: 疲労 100 でも use_item は通す)

**何を**: ゲーム内で「**取れる手段が完全にゼロ**」になる状態を構造的に避ける。
例えば疲労 100 で動けない時でも、`use_item` / `wait` / `speech` のような **回復ループに乗るためのツール** は必ず通せるようにする。

**なぜ**:
- LLM agent はランダム探索ではなく「最良の手」を 1 つ選ぶ。詰みは無限ループ (同じ tool 呼び続ける) や silent crash になりやすい
- TRPG / survival シナリオでは「**仲間に助けてもらう**」「**食料で持ち直す**」が物語の核。完全詰みは物語を殺す
- 「動けないが、座ったまま回復行動はできる」というモデルは、現実の人間にも適合する直感的な設計

**どうしないと壊れるか**:
- 疲労 100 で use_item を block すると、食料を持っていても食えずに餓死。inventory に解決手段があるのに使えない構造は LLM が困惑する
- HP 0 (DEAD) も同様: dead player に対するアクションは全部 silent にする (#363 で対処)、ただし他 player から見れば「倒れている」観測は届く

**どこでこの判断が出てきたか**:
- PR β (疲労ライフサイクル) の設計議論で「100 のとき use_item を block するか」→ ユーザ判断「絶対通す」

---

## 3. 揮発ラベル (S1 / I2 / P3) を捨て、名前 + ordinal で対象指定する

**何を**: prompt 上に `S1: 扉 → 玄関` のような tick 内で振り直される連番ラベルを出さない。代わりに `- 扉 → 玄関` の名前直書き形式で、同名衝突時のみ `#1` / `#2` で disambiguate する。

**なぜ**:
- ラベルは **揮発的**: 同じ `I2` が次 turn で別アイテムを指す
- memo / episodic memory に「`I2` を渡した」と書かれると **再構築不能** (記憶汚染)
- 名前直書きなら過去 turn のメモがそのまま意味を持つ ("玄関に移動した" は tick を跨いで読める)

**どうしないと壊れるか**:
- 第13/14 回実験のリン「閲覧室 ↔ 入口広間」bouncing がこの構造的原因 (#229 で部分対処 → PR #421 / #425 で完全対処)
- 新規 tool を作るときも `*_label` 引数を増やさず「対象の名前」を渡す設計に揃える

**どこでこの判断が出てきたか**:
- 実験 #29 OFF 分析の feedback「ラベルをやめる」 → PR #421 / #425

---

## 4. travel / wait は「ツール内で tick を進めない」モデルにする

**何を**:
- `travel_to` ツールは travel state を立てて即返り、その後の world tick で 1 leg ずつ進む。移動中の player は `_can_player_act` filter で turn を skip し、到着時に再起床する
- `spot_graph_wait` ツールも同様に「今ターンは行動を控える」という意思決定だけを記録し、`advance_tick` は呼ばない (#471)

**なぜ**:
- 旧 `do_move` は内部で `advance_tick × 200` のネストループを回し、1 driver tick = 656 秒 / 134 LLM call というスパイクを生んでいた (#404)
- 旧 `do_wait` も nested `advance_tick` を 1 回呼んでおり、`_run_post_tick_hooks` → `run_scheduled_turns` → 他プレイヤー LLM ターン → `spot_graph_wait` → `do_wait` … の再帰カスケードを起こしていた。L run で 1 driver iteration 内に world tick が +104 ジャンプし、`MAX_WORLD_TICKS=140` を黙ってバイパス (#471)
- driver loop の `while current_tick < max_world_ticks` ガードは **iteration 先頭でしか効かない**ため、ネストカスケード中は上限を守れない

**どうしないと壊れるか**:
- ツール / handler / observation hook の中で `advance_tick` / `simulation.tick` を呼ぶ設計を持ち込まない。世界時計の更新は **外側の experiment loop / driver thread だけが触る** という不変条件
- wait は「skip ターン」記録だけにする。「tick を 1 進めるショートカット」として使う設計にすると #471 と同じ再帰カスケードが復活する
- 移動中の player の turn を空回りさせない (heartbeat / observation 経路で wake up しないよう `is_traveling` フィルタを通す)

**どこでこの判断が出てきたか**:
- 実験 #28 partial run の 656 秒スパイク → #404 / #405 (travel non-blocking) / #407 (per-agent idle timer)
- 実験 #468 L run の 1878 秒スパイク / +104 tick ジャンプ → #471 (do_wait nested advance 除去)

---

## 5. silent failure を「構造」で塞ぐ (例外ハンドリングだけに頼らない)

**何を**: 致命的な状態破綻 (orphan item / 状態不整合 / 順序逆転) は、例外 catch ではなく **コードの順序や事前ガード** で塞ぐ。

**なぜ**:
- 例外で catch すると失敗が prose に出ず、LLM も気づかない (= silent)
- 順序由来の破綻は再現条件が見えにくく、trace を grep しないと原因が辿れない

**例**:
- `give_item` で receiver が満杯の場合: 事前に `is_inventory_full()` チェック → 失敗時は ItemTransferException を投げる。送り手から先に抜いてから receiver に渡そうとして失敗するパスを作らない (#400)
- `use_item` で quantity=0 になった時: `inventory.save` → `item_repository.delete` の順に固定。逆順だと delete 成功 / inv save 失敗で orphan instance が残る (#400)
- `ItemUsedEvent` を `publish_all` で必ず流す: aggregate に積んで捨てない (#400)

**どうしないと壊れるか**:
- 似たような silent failure は実走で必ず再発する。「catch して握りつぶす」は使わない
- `try/except: pass` を書きそうになったら、本当に握りつぶしていい理由 (= 親 action と独立 / fail-safe で続行が望ましい) を comment に書く

**どこでこの判断が出てきたか**:
- 実験 #28 のアイテム系 silent failure 群 → #400

---

## 6. 後方互換を過度に守らない

**何を**: 「旧 API も残しておく」「旧フラグも動くようにしておく」のような移行層を、明確な必要性がない限り作らない。

**なぜ**:
- 後方互換層はそれ自体が **継続的に維持** されるべき表面積になり、テストの組み合わせ爆発を生む
- LLM の運用 (= 自分たちで動かしているだけ) では、外部 client 互換性のような重い制約がない
- 旧経路を切り捨てる方が、コードが単純になり読み手にも実装者にも親切

**どうしないと壊れるか**:
- 大きな refactor が「片落ち」状態 (新旧両方が動く中途半端な状態) で凍結すると、後で誰も触れなくなる
- PR #409 (MAX_TICKS → MAX_WORLD_TICKS) は完全 rename にした。env レベルでは旧 `EXPERIMENT_MAX_TICKS` を 1 段だけ backstop で読むが、それ以上の互換層は作らない

**どこでこの判断が出てきたか**:
- CLAUDE.md の repo ルールにも明記 ("後方互換を過度に守らない")
- PR #404 系列の `MAX_TICKS` rename

---

## 7. heartbeat は「最低発火頻度の floor」ではなく「最大沈黙時間の ceiling」

**何を**: 全 agent を `N tick おきに必ず起こす` という旧 heartbeat ではなく、`N tick 何も起きなかったら 1 回だけ起こす` という per-agent idle timer 方式にする。

**なぜ**:
- 旧 heartbeat (5 tick おき全員起床) は、event 駆動で active な agent にまで heartbeat を届けて空回り turn を量産していた
- 1 driver tick で 4 player × ceil(20/5) = 約 20 回の不要な LLM 呼び出しが乗っていた

**どうしないと壊れるか**:
- event 駆動の起床経路 (`schedules_turn=True` 観測) が網羅されていないと、idle_timeout (デフォルト 6 tick) まで重要な変化に気づかない
- `schedules_turn` の audit は重要 (#412): HP 変化 / モンスター出現 / 発話 / アイテム overflow / 救助到達 / etc. を漏れなく `schedules_turn=True` に揃える必要がある

**どこでこの判断が出てきたか**:
- 実験 #28 wall time スパイクの分析 → #407 (per-agent idle timer) + #412 (schedules_turn audit)

---

## 8. 状態依存の表示は「プレイヤー状態セクション」に出す

**何を**: 「疲労が限界」「HP 危険域」「中毒中」など、状態に応じた情報を LLM に伝える必要がある場合、**system prompt は触らず**、毎 turn 再生成されるプレイヤー状態セクション (= snapshot を文字列に展開する箇所) で表現する。

**なぜ**:
- 設計判断 #1 (prefix cache) と直結
- プレイヤー状態セクションは元々 turn ごとに変動する前提なので、追加情報を載せても prefix cache を壊さない

**どうしないと壊れるか**:
- 状態依存ヒントを system prompt に注入すると prefix cache が完全に死ぬ
- 状態セクションが長くなりすぎると LLM が読み切らなくなる懸念はあるので、要約 / 優先度設定を併用する

**どこでこの判断が出てきたか**:
- PR β (疲労ライフサイクル) の設計議論

---

## 10. 実験 env の不正値は silent fallback せず fail-fast

**何を**: `PROMPT_SECTION_ORDER` / `SHORT_TERM_MEMORY_KIND` / `SHORT_TERM_MEMORY_SCHEDULER_MODE` / `SEMANTIC_PASSIVE_TOP_K` / 各種 bool 系 env 等の **解決層**で、未知の値が来たら warning + default に縮退 (silent fallback) ではなく **`ValueError` を投げて即停止**する。

**なぜ**:
- 短縮形や typo (例: `SHORT_TERM_MEMORY_KIND=rolling` ← 正しくは `rolling_summary`) が silent fallback されると、**実験が間違った設定で走る**
- 長 tick の実験では「数時間走らせて trace を見るまで気づけない」状態になる (PR #433 で実際に発生: Parasail A/B 実験 Run B が rolling のつもりで sliding_window だった)
- 不正値は **shell の export ミス / 別の env を混同 / Makefile 引数の typo** など。実験者が意図して入れる事はほぼ無い → 黙って受理する価値より、即時 fail させて打ち直す方が安全

**どう実装するか**:
- enum 系 (`section_order`, `memory_kind`, `scheduler_mode`): 未知文字列で `ValueError(env_name + bad_value + valid_list)`
- 数値系 (`semantic_passive_top_k`): 非整数 / 負数で `ValueError`
- bool 系 (`_parse_bool_env`): TRUTHY と FALSY 両方の明示集合を持ち、どちらにも該当しない値で `ValueError`
- **未設定 / 空文字** は意図的な「default 採用」と解釈し、引き続き default を返す (この決定は維持)

**どうしないと壊れるか**:
- 同じ実験を何度もやり直すコストが膨らむ + 結果の信用も落ちる
- typo の発見が trace を grep するまで遅れる → 設計判断のフィードバックループが鈍る

**どこでこの判断が出てきたか**:
- PR #433 で「Parasail A/B 実験 Run B は sliding_window だった」事実が `run_start` payload から判明 → PR #434 で対策

---

## 11. 設定は単一 DTO で集約、構築は「全部揃ってから 1 回 build」

**何を**: env / scenario JSON / 引数由来の設定は `ResolvedLlmRuntimeConfig` のような **1 つの frozen DTO** に集約してから wiring に渡す。サービスは **「依存が揃ってから ctor で全部注入」** で構築し、setter で後注入する経路は作らない。

**なぜ**:
- 「env を 2 箇所で別解釈する」silent failure が大量発生した (PR #439 / PR #446: section_order や memory_kind が trace に書かれた値と実体でズレる)
- 「setter で後注入する Future work が忘れられる」silent failure も発生した (PR #444: `set_summary_services` setter は作ったが呼び出し側 wiring が未実装で 1 ヶ月放置 → 実機実験で L4/L5 が全件 template fallback)
- 「`Optional[X] = None` + 後注入」は呼び忘れを型エラーに昇格できない設計上の弱点

**どう実装するか**:
- env を読むのは `ResolvedLlmRuntimeConfig.from_env()` の 1 箇所だけ。entrypoint で 1 度だけ呼び、cfg を引数で渡し回す
- cfg は frozen dataclass。構築後の改変を封じる
- `to_trace_dict()` で trace 用 dict を出すとき API key は `***` にマスク
- 不正値は `ValueError` で fail-fast (= 設計判断 10 と併用)
- サービス構築は `_build_*(cfg, *args)` 形式で、依存物 (llm_client / persona_resolver) を ctor で全部受け取る
- setter は禁止ではないが、Optional dependency に対して使ったら **同時に「呼ばないと動かない場面」を構造的に作らない**こと

**どうしないと壊れるか**:
- 2 箇所目の env 解釈が必ずいつか追加される → silent failure 再発
- setter の呼び忘れが型チェックや CI で捕まらない → 実機実験で初めて発覚
- 「動いてるように見える別モード」が増える

**どこでこの判断が出てきたか**:
- PR #439 / #441 / #444 / #446 の 4 連続 silent failure
- architect レビュー (PR #444 後) → リファクタリング 6 PR (#446 / #447 / #448 / #449 / #450 / #451) で構造的対処

---

## 12. Future work は xfail-strict pytest で可視化する

**何を**: 「次の PR で対応する」という TODO を、**コメントではなく `@pytest.mark.xfail(strict=True, reason="PR #N: ...")`** で表現する。

**なぜ**:
- PR #439 で `set_summary_services` setter を作ったが「後で wiring が呼ぶ」が忘れられ PR #444 まで放置された
- リポジトリ内に散在する `# TODO` / `# 後で` / `# 仮` コメントは grep しないと発見できず、レビュー時にも見落とされる
- pytest なら CI で必ず実行され、強い可視性がある

**どう実装するか**:
- 「将来の PR で動くべきテスト」を `xfail(strict=True)` で書く。strict=True なので、対応した瞬間に "expected fail but passed" で CI が落ち、修正完了を強制 unmark させる
- reason に PR 番号 / target PR を必ず明記
- 例 (架空):
  ```python
  @pytest.mark.xfail(strict=True, reason="PR #439: setter is wired but no caller yet (target: PR #444)")
  def test_rolling_summary_llm_path_is_actually_wired_in_production():
      ...
  ```

**どうしないと壊れるか**:
- `# 後で` コメントが恒久放置される
- レビュー時に「ここ後で誰かが直すから OK」と通された scope split が忘れられる

**どこでこの判断が出てきたか**:
- PR #439 → PR #444 の 1 ヶ月放置事案
- architect レビュー (PR #444 後)

---

## 13. memory caller の Being 未解決時挙動は「役割」で分岐する

**何を**: Being / Resolver / WorldId のいずれかが未注入 / 未 provision で memory store の being_id 経路を引けないとき、caller の挙動は **役割によって 3 種類** を使い分ける。

| caller の役割 | 未解決時の挙動 | 理由 |
|---|---|---|
| LLM-visible tool (例: `SemanticMemorySearchToolExecutor`) | **fail-fast** (`INVALID_STATE` で `success=False`) | 「該当 0 件」と「内部状態未準備」を LLM が区別できないと、誤った判断につながる |
| turn の副作用 (例: `EpisodicSemanticClusterPromotionService`) | **silent no-op** | promotion 失敗で turn を止めない。次回 turn で再試行できる |
| prompt 強化 (例: `SemanticPassiveRecallService`) | **graceful empty list** | side feature なので turn を止めない。 wiring 漏れは別途 wiring level の test で塞ぐ責務 |

**なぜ**:
- すべて fail-fast にすると prompt 系の side feature で turn が落ちる
- すべて silent にすると LLM が「該当なし」と誤認して間違った行動を取る
- すべて graceful にすると wiring 漏れが本番で見えなくなる
- 「caller がどう失敗してほしいか」は本質的に **caller 側の関心** なので Repository 側でなく caller で判定する

**どうしないと壊れるか**:
- 一律 silent: LLM-visible tool で「該当なし」と「内部 bug」が判別不能になり、誤判断が trace から追えない
- 一律 fail-fast: passive recall や promotion の小さな失敗で turn 全体が止まる

**残るリスク**: graceful empty (passive recall) は wiring 漏れを隠す可能性がある。これは wiring-level test (= Resolver+WorldId が必ず注入される) で補完する責務とし、本 caller では「prompt が痩せるだけ」の縮退に留める。

**どこでこの判断が出てきたか**:
- PR #491 / #492 (Phase 3 Step 3b-2 / 3b-3 = semantic legacy 撤去)
- code-reviewer (MEDIUM-1) でも「Optional 設計は wiring 漏れを隠しうる」と指摘あり、トレードオフ込みで採用

---

## 14. promotion_frontier は Phase 3 Step 3c の scope 外 (= player_id keyed のまま)

**何を**: ``EpisodicPromotionFrontier`` は ``memory_link`` / ``recall_buffer`` /
``reinterpretation_journal`` の 3 連携 store とは別レイヤーで、現状は
player_id keyed のまま残す。``EpisodicMemoryLinkApplicationService`` から frontier
に追記するとき、Resolver で BeingId → player_id を逆引きする
``_player_id_for(being_id)`` helper を経由する。

**なぜ**:
- frontier は「次回 promotion で対象にすべき episode_id の集合」を保持する
  小さな in-memory ストア。run 跨ぎ identity を保つ必要が無く、Being 化の
  優先度が低い
- Step 3c は 3 store の being_id keyed 移行に集中するスコープで、frontier
  まで含めると変更範囲が膨らみすぎる
- 「caller 入口で being_id を 1 度だけ解決する」 resolve-once パターンを
  維持するには、frontier への追記時のみ player_id が必要 → 逆引き helper で
  橋渡しする方が、frontier 自体を Being 化するより安く済む

**どうしないと壊れるか**:
- frontier ごと一気に Being 化しようとすると、関連 service (
  ``EpisodicSemanticClusterPromotionService.drain`` / ``add`` /
  ``EpisodicMemoryLinkApplicationService.note_promotion_frontier_episodes``) を
  すべて同時に書き換える羽目になり、PR が肥大化してレビュー困難になる
- 逆引き helper を撤去し忘れると「Resolver の余分な lookup が turn ごとに
  走る」 dead code が残る

**どこでこの判断が出てきたか**:
- PR #495 (Phase 3 Step 3c-3) のレビュー指摘 MEDIUM-2
- 後続 Phase で frontier を being_id 化したら ``_player_id_for`` helper は
  撤去する

---

## 15. BeingSnapshot v2 は memory payload を「オペーク JSON」として持つ

**何を**: BeingSnapshot に memory payload を載せるとき、各 memory context
(memo / semantic / memory_link / recall_buffer / reinterpretation_journal /
episodic_episode) の VO や aggregate を直接フィールド化せず、`memory_payload_json:
str | None` という **オペーク な JSON 文字列** として保持する。JSON の内訳
schema は application 層の `BeingMemorySnapshotService` (Phase 4-2) が版管理
する。

**なぜ**:
- `domain/being/` から各 memory context の VO へ依存すると、本来独立すべき
  bounded context 間に逆方向の import が走る (= snapshot のために being が
  全 memory 文脈を知る必要が出る)
- memory store の内部 schema は将来も増減 / 改変が見込まれる (現状でも 5
  store ある)。VO field として固定すると BeingSnapshot version が memory
  schema の変更ごとに上がってしまい、Being 集約 root と memory の責務が
  混ざる
- オペーク JSON なら「Being 集約 root の不変条件」と「memory schema の版
  管理」を別軸で進化させられる (= 関心の分離)

**どうしないと壊れるか**:
- snapshot を VO 直入れにすると、新しい memory context が増えるたびに
  domain/being 配下の import 行と snapshot_version がドミノ式に動く
- 逆向き import が増えると将来の context 分離 (例: memory パッケージ独立化)
  が困難になる
- v1 (memory なし) と v2 (memory あり) を別 schema で扱うことで、Phase 2 で
  保存済みの v1 snapshot を後方互換で読み続けられる (= 既存 SQLite 行を
  捨てずに済む)

**どこでこの判断が出てきたか**:
- Phase 4 Step 4-1 着手時 (= 本 PR)
- 既存 `BeingSnapshot` docstring の「(b) 後で payload field を増やす」方針
  を具体化する形

---

## 21. world snapshot は scenario 一致を hard-error で要求する (= cross-scenario load は不可)

**何を**: ``WorldStateSnapshot`` の ``source_scenario`` が現 scenario と
異なる場合、``restore`` で ``WorldStateScenarioMismatchError`` を投げて
**fail-fast** する。memory snapshot の cross-scenario transfer (warning のみ)
とは **正反対の方針**。

**なぜ**:
- world state は scenario と密結合 (= ``spot_id`` / ``item_spec`` /
  ``scenario_events`` がすべて scenario 定義に依存)。別 scenario に load
  しても spot_id が存在しない等の壊れ方をする
- memory はキャラクターの「経験」なので scenario 跨ぎが意味を持つ (= 同じ
  キャラを別世界に転送)。world state は逆に「世界そのもの」なので、
  別世界の状態を持ち込むのは矛盾
- 両者が **別ファイル** (``being_*.json`` と ``world.json``) に分かれて
  いることで、cross-scenario use case は「Being snapshot のみコピー、
  world.json は転送先のものを別途用意」という運用で実現できる

**どうしないと壊れるか**:
- world snapshot を warning のみで通すと、別 scenario の world state を
  load した後 advance_tick で「存在しない spot_id を踏む」等の見えにくい
  エラーを引き起こす
- memory を hard-error にすると user の「同じキャラを別世界に転送する」
  use case (= 設計判断 #19 で許容済) が壊れる

**どこでこの判断が出てきたか**:
- Phase 9-1 着手時 (= 本 PR)、user との議論で「world は scenario 一致
  fail-fast」を確認

---

## 23. monster / quest codec は Phase 9-5 では未実装 (= 実需要待ち)

**何を**: ``world_subsystems/`` に ``MonsterAggregateSubsystemCodec`` /
``QuestProgressSubsystemCodec`` は存在しない。``MonsterAggregate`` は HP /
位置 / aggro / pursuit_state 等 15+ field の deep nested aggregate で、quest
も同様の構造を持つ。書けば書ける (Phase 9-3b の戦略 C パターン適用可能) が、
**現在 resume が必要とされている scenario (decay_demo / survival_island_v2)
が monster combat / quest を core mechanic にしていない** ため、未実装で
defer する。

**なぜ**:
- 必要のない codec を書くと「scenario JSON は変えてないのに codec の static
  metadata 部分が肥大化」する負債が生まれる
- monster / quest を使う scenario が登場した時に、その scenario の実需要に
  合わせて codec を書く方が schema が現実に即する
- Phase 9 の本来のゴール (= make experiment で resume が機能する) は 21
  subsystem で達成済

**どうしないと壊れるか**:
- 「将来必要かも」で全 aggregate に codec を書くと test と本体の維持コスト
  が累積する (= YAGNI 違反)
- 一方で「monster / quest を使う scenario で snapshot を取る」と、Phase 9-1
  設計判断 #22 により未登録 subsystem は forward-compat で skip され、resume
  時に monster/quest だけ scenario 初期状態に戻る (= 既知の制限として明示)

**どこでこの判断が出てきたか**:
- Phase 9-5 着手時 (= 本 PR)
- code-reviewer subagent の指摘 (= 「実需要待ちは妥当だが docs に明記すべき」)
- monster / quest を使う scenario が登場したら ``world_subsystems/`` に
  codec 追加 + ``_default_world_subsystem_codecs()`` に 1 行追加するだけ

---

## 22. world snapshot は subsystem ごとに codec を持ち、登録外は forward-compat で skip

**何を**: ``WorldStateSnapshotService`` は ``WorldSubsystemCodec`` を複数
登録できる構造にし、各 codec は独立して ``capture`` / ``restore`` を担当。
JSON 内 ``subsystems`` dict の各 key (= ``player_status`` / ``spot_interior``
等) が codec の ``subsystem_key`` と紐づく。

**登録外 subsystem は ``info`` ログを残して skip する** (= 例外を投げない)。

**なぜ**:
- world state は多くの独立した subsystem (player / spot / weather /
  monster / ...) の集合体で、scenario によって使う subsystem が異なる
- Phase 9-2 以降で 1 subsystem ずつ追加していく長期計画。新 subsystem が
  入る前の旧 snapshot を新 code で load できるよう、後方互換を保つ
- 逆に「新 snapshot を旧 code で load」(= 旧 code には codec 未登録) で
  fail-fast すると、forward 互換が壊れて運用が硬直する
- 各 subsystem の ``schema_version`` は codec 自身が管理 (= 中央集権でなく
  分散)。``WorldStateSnapshot`` 自体の ``schema_version`` は「subsystems
  dict の構造形式」の version だけを表す

**どうしないと壊れるか**:
- 「新 snapshot を旧 code で読む」が hard-error だと、Phase 9-2 が
  リリースされるまで Phase 9-3 以降の snapshot が使えなくなる
- 「subsystem を 1 つの hard-coded list で管理」する案だと、新 subsystem
  追加のたびに既存 code を変える必要がある (= 結合度が上がる)

**どこでこの判断が出てきたか**:
- Phase 9-1 着手時 (= 本 PR)
- 既存 ``BeingSnapshotCodec.SUPPORTED_VERSIONS`` の単純な version 集合と
  違い、world は **2 階層** (snapshot 自体の version + subsystem ごとの
  内部 version) になるので、別アプローチが必要だった

---

## 20. snapshot の schema 進化は (a) 厳格モード — 未サポート version は load 失敗

**何を**: ``BeingSnapshot.snapshot_version`` および ``memory_payload_json``
の ``schema_version`` が現行 supported 集合に含まれない場合、**load 経路で
fail-fast で例外を投げる**。``BeingSnapshotCodec.SUPPORTED_VERSIONS`` /
``SUPPORTED_PAYLOAD_SCHEMA_VERSIONS`` をシングルソース。

``RestoreBeingSnapshotFromFileUseCase.execute`` は ``repo.save_snapshot``
の前に明示的に version をチェックする (= 部分状態を repo に残さない)。

**なぜ**:
- run 途中再開の想定 use case は「同じ code バージョン同士で save / load」。
  schema が変わるほど離れた run を救う必要性は低い
- migration ルートを書くと「v1→v2 で意味の変質」が silent に起きうる
  (= 旧 file の値が新 schema で別の意味になる)。データを救うより data
  integrity を優先する
- 「(c) best-effort」(= 未知 field 無視 + 欠落 default 補完) は柔軟だが、
  「snapshot は完全な再現を保証する」設計判断 (= all-or-nothing #15) に反する

**どうしないと壊れるか**:
- v1 のまま新 code で load → ``snapshot_version=1`` を ``Codec.SUPPORTED_VERSIONS
  = {1, 2}`` のままにしておけば読める。互換性のために旧 version も
  ``SUPPORTED`` に **明示的に残す**。これは方針 (a) 厳格 と矛盾しない
  (= unsupported なら fail-fast、supported なら通る)
- 「migration が必要になったら」: ``SUPPORTED_VERSIONS`` を変えずに新 codec
  クラス (``BeingSnapshotCodecV3`` 等) を追加する案を検討。本 PR scope 外

**どこでこの判断が出てきたか**:
- Phase 8 着手時 (= 本 PR)、user が「一旦 (a) で行こう」と明示

---

## 19. snapshot ファイルは scenario 名メタデータを持ち、別シナリオ転送は warning だけで許容する

**何を**: snapshot JSON の root に ``_metadata`` ブロックを追加し、
``source_scenario`` (= 取得時のシナリオ名) と ``captured_at`` (= UTC ISO 8601)
を埋め込む。restore 時に現 scenario と ``source_scenario`` が異なる場合は
warning + trace event (``snapshot_load`` の payload に
``cross_scenario_transfers``) で記録するが、**エラーにはしない**。

**なぜ**:
- 「同じキャラクターを別シナリオに転送して前の memory を引き継ぐ」use case
  が将来ありうる (= forest_world でやり遂げた agent を desert_world に
  送り込んで挙動を見る、等)
- ただし「うっかり別シナリオに load して気付かない」事態は避けたい。
  warning + trace event で **意図せぬ転送は気付ける** が、意図した転送は
  そのまま走らせる、というバランス
- BeingSnapshot VO 本体は触らない (= 「VO は primitive-only」の設計判断
  #15 と整合)。メタデータは file gateway 層で独立に管理する

**どうしないと壊れるか**:
- 旧 snapshot ファイル (``_metadata`` キー無し) を後方互換で読めなくなる
  → ``data.get("_metadata")`` で ``None`` fallback。古い file も読める
- mismatch を hard error にすると cross-transfer use case が実装できない
- mismatch を silent に通すと、誤 load を発見できない

**どこでこの判断が出てきたか**:
- Phase 7 着手時 (= 本 PR)、user が「同じキャラを別世界に転送したい」と
  明示的に意図を示したこと

---

## 17. experiment runner の snapshot は escape_game runtime の限定 store だけを拾う

**何を**: ``scripts/run_scenario_experiment.py`` の Phase 6 統合では、
``_wiring_stub_from_escape_runtime`` が ``EscapeGameRuntime`` の private
attribute から **拾える分だけ** store を集めて
``ExperimentSnapshotSession`` に渡す。escape_game runtime には semantic /
memory_link / recall_buffer / reinterpretation_journal の 4 store がそもそも
存在しないため、これらは ``None`` で渡され、session 側で空 in-memory store
に fallback される。

**なぜ**:
- escape_game runtime は ``EpisodicStack`` (memo + episode のみ) を使う
  構成で、semantic / memory_link 等の高度 memory pipeline は
  ``create_llm_agent_wiring`` 経路でしか組まれない
- ここで「足りない store を後付けで配線する」と既存実験の挙動を変えてしまう
  (= 既存 trace との比較ができなくなる)
- 「snapshot に乗らない情報は空 array でも整合性が取れる」のが Phase 4-2b
  の JSON schema 設計の素敵な性質。fallback で問題が起きない

**どうしないと壊れるか**:
- 強制配線を入れると prompt 構築 / observation pipeline に副作用が混じる
- 「拾えない store → silent に snapshot off」だと、後で気付かれず復元に
  失敗する。info ログで fallback 使用を明示する (= silent failure を構造で
  防ぐ #5 と整合)

**どこでこの判断が出てきたか**:
- Phase 6 着手時 (= 本 PR)
- 将来 escape_game runtime に semantic stores を入れたら、wiring stub の
  attribute lookup を増やすだけで済む

---

## 18. snapshot save は SIGINT を flag 化して run 終了経路に合流させる

**何を**: ``run_scenario_experiment.py`` で ``--snapshot-save-dir`` を指定した
ときだけ SIGINT (Ctrl+C) を ``_interrupted = True`` フラグ立てに変える。
``KeyboardInterrupt`` を直接 raise させず、main loop が次の iteration で
正常に break する。break 後の通常終了経路 (= snapshot save + runtime.shutdown)
を必ず通すため。

**なぜ**:
- ``runtime.advance_tick()`` の中に LLM 呼び出し / async scheduler / 観測
  pipeline が絡んでいる。``KeyboardInterrupt`` が突然 raise されると
  partial state (= 観測が途中で止まる、scheduler が drain されない) で
  snapshot を取るリスクがある
- flag 化すれば「現 iteration の advance_tick() が綺麗に終わってから break」
  になる。snapshot は **整合性の取れた状態** から取れる
- ``--snapshot-save-dir`` 未指定なら SIGINT ハンドラを触らない (= 既存挙動
  完全互換)。snapshot を使わない実験では Ctrl+C は引き続き
  ``KeyboardInterrupt`` を即時 raise する

**どうしないと壊れるか**:
- グローバルに SIGINT を flag 化すると、snapshot を使わない既存実験の
  Ctrl+C の即時性が失われる (= ユーザーが Ctrl+C を 2 回押す習慣に行き着く)
- 直接 ``except KeyboardInterrupt`` で受けると、advance_tick の途中で止まる
  ので scheduler の drain が呼ばれず ``"recorder is already closed"``
  RuntimeError が後追いで出る (= 第21回実験の既知 silent failure と同型)

**どこでこの判断が出てきたか**:
- Phase 6 着手時 (= 本 PR)、user が「実験後にエラーが出られると困る」と
  明示的に要求した点をきっかけに

---

## 16. run 途中再開 CLI は 4 SQLite DB + in-memory memo の構成で動く

**何を**: ``scripts/being_snapshot_cli.py`` の ``_build_stack`` は 4 つの SQLite
ファイル (``being`` / ``memory_graph`` / ``episode`` / ``reinterpretation``) を
明示引数で取り、memo store だけは ``InMemoryMemoStore`` で新規に作る。

**なぜ**:
- 5 memory store のうち memo にだけ SQLite 実装がなく、in-memory にしか
  住んでいない (= Phase 3 までの整理で必要にならなかった)
- 「memo は持たないと困るが永続化先がない」を解決するのが snapshot JSON。
  CLI 起動ごとに memo store は新規になるが、 ``capture`` で payload に
  乗り、``restore`` で書き戻されるので **JSON ファイル自体が memo の
  永続化媒体** として機能する
- semantic + memory_link は同一 SQLite ファイルに共住 (=
  ``apply_memory_graph_migrations`` が両 schema を一括適用) なので CLI も
  同じ接続を共有

**どうしないと壊れるか**:
- memo の SQLite 実装を急いで作ると、Phase 5 のマイルストーン (= JSON 経由
  の途中再開) が遅れる。「memo は in-memory + JSON 経由保存」という整理で
  最短 path を取る
- 4 DB の役割を CLI 引数で明示することで、将来 DB 配置が変わっても CLI を
  作り直す必要がない (= 既存 game DB と同じ path を指定すれば動く)

**どこでこの判断が出てきたか**:
- Phase 5 着手時 (= 本 PR)
- 将来 memo SQLite を入れるときは ``--memo-db`` 引数を追加する

---

## 9. 速度より「LLM の判断ミス」を優先して直す

**何を**: 並列化 / 非同期化 / cache 最適化のような **wall time 改善** より、LLM が誤判断する原因を 1 つずつ潰す方を優先する。

**なぜ**:
- 並列化済 (#346 Step 1) で wall time はそれなりに改善した
- LLM の判断ミス (ITEM_NOT_CONSUMABLE / 揮発ラベル誤用 / 救助に向かわない etc.) は実走の物語そのものを壊す
- 「速いが頭が悪い」より「やや遅いが賢い」方が物語の検証に役立つ

**どうしないと壊れるか**:
- 「速いから OK」と判断ミスを放置すると、長期的に LLM 出力の信用が落ちる
- 「もっと速いモデルを使えば解決」と Inference 側に解決を委ねると、シナリオ設計のフィードバックが鈍る

**どこでこの判断が出てきたか**:
- 実験 #29 OFF 分析の feedback シリーズ (ラベル / アイテム type tag / scenario realism / batch tools / fatigue lifecycle)

---

## index (時系列)

| Decision | 採用 | 関連 PR / Issue |
|---|---|---|
| 1. Prefix cache 不変 | 2026-06-07 | (新規) PR β |
| 2. 詰み回避 (use_item は通す) | 2026-06-07 | (新規) PR β |
| 3. 揮発ラベルを捨てる | 2026-06-07 | #229 / #421 / #425 |
| 4. travel / wait は tool 内で tick を進めない | 2026-06-07 / 2026-06-14 | #404 / #405 / #471 |
| 5. silent failure を構造で塞ぐ | 2026-06-07 | #396 / #400 |
| 6. 後方互換を過度に守らない | (継続) | CLAUDE.md / #409 |
| 7. heartbeat → idle timer | 2026-06-07 | #346 / #407 / #412 |
| 8. 状態情報は state section へ | 2026-06-07 | (新規) PR β |
| 9. LLM 判断ミス > wall time | 2026-06-07 | 実験 #29 feedback 群 |
| 10. 実験 env は fail-fast | 2026-06-07 | PR #433 / #434 |
| 11. 設定 DTO 集約 + ctor 注入 | 2026-06-09 | PR #446-#451 (リファクタ 6 PR) |
| 12. Future work は xfail-strict で可視化 | 2026-06-09 | PR #451 (慣習化) |
| 13. memory caller の未解決時挙動は役割で分岐 | 2026-06-14 | PR #491 / #492 |
| 14. promotion_frontier は Phase 3 Step 3c scope 外 | 2026-06-14 | PR #495 |
| 15. BeingSnapshot v2 は memory payload をオペーク JSON で持つ | 2026-06-14 | Phase 4 Step 4-1 |
| 16. run 途中再開 CLI は 4 DB + in-memory memo で動く | 2026-06-14 | Phase 5 |
| 17. experiment runner の snapshot は escape_game runtime 限定 store のみ拾う | 2026-06-14 | Phase 6 |
| 18. snapshot save 経路の SIGINT は flag 化 (KeyboardInterrupt を抑制) | 2026-06-14 | Phase 6 |
| 19. snapshot メタデータで cross-scenario transfer を可視化 (warning のみ) | 2026-06-14 | Phase 7 |
| 20. snapshot schema 進化は (a) 厳格 — 未サポート version は load 失敗 | 2026-06-14 | Phase 8 |
| 21. world snapshot は scenario 一致を hard-error で要求 (= cross-scenario 不可) | 2026-06-14 | Phase 9-1 |
| 22. world snapshot は subsystem 分散 / 登録外 subsystem は forward-compat で skip | 2026-06-14 | Phase 9-1 |
| 23. monster / quest codec は Phase 9-5 では未実装 (= 実需要待ち) | 2026-06-14 | Phase 9-5 |
| 24. ObservationAppender ↔ encounter は observer slot で疎結合 | 2026-06-17 | PR3 (Encounter Memory wiring) |
| 25. application 層の circular import は test 側で warm-up import で回避 (= 既知債務) | 2026-06-17 | PR3 / observation.contracts ↔ llm.services |

---

## 24. ObservationAppender ↔ encounter は observer slot で疎結合

**何を**: ``ObservationAppender`` は ``observers: list[Callable]`` を受け取り、append
の度に各 observer を呼ぶ。``EncounterObservationCollector`` は collector の
``on_observation`` を bound method として slot に渡される。``ObservationAppender``
側は ``encounter`` への import を持たない。

**なぜ**:
- ``observation`` 層と ``encounter`` 層を疎結合に保つ。``application/`` は単一
  layer として扱われているが、責務が違うサブシステムを直接 import しないことで
  「観察を受け取る側 (appender) は観察者 (encounter / metrics / debug) を知らない」
  形を保てる
- observer 追加時の負担が低い: 別目的の Callable (例えば trace metrics) を後
  から差し込みやすい
- import grpah が浅くなり、循環 import の起こりやすさが下がる (= #25 とも整合)

**どうしないと壊れるか**:
- ``ObservationAppender`` の constructor で concrete collector を isinstance
  チェックする pattern を持ち込むと、observation → encounter の hard import が
  生まれて応用範囲を狭める
- 後で「append のたびに ○○ もしたい」が来るたびに ``ObservationAppender`` 改修
  が必要になる

**どこで出てきたか**: PR3 (Encounter Memory wiring) の subagent code-reviewer
レビューでカップリングを指摘され、Callable slot 化で対応した

---

## 25. application 層の circular import は test 側で warm-up import で回避 (= 既知債務)

**何を**: ``application/observation/contracts/__init__.py`` が
``llm.contracts.dtos`` を import し、その先で ``llm/__init__`` 経由で
``llm.services.agent_orchestrator`` → ``episodic_chunk_coordinator`` →
``observation.contracts.interfaces`` への参照が走り、partial initialization 中
の ``observation.contracts.interfaces`` を import しようとして
``ImportError`` (circular) が起きる。

回避策として、test ファイルでは ``llm.services.*`` を先に import して `llm` 側
を warm up してから ``observation.contracts.dtos`` を import する。新規 module
側は ``TYPE_CHECKING`` のみで ``ObservationOutput`` を参照する。

**なぜ債務として残すか**:
- 本質的な解は ``observation.contracts`` 側の package-level import を遅延化
  する (= ``__init__.py`` で interfaces を eager import しない) 構造的な改修。
  これは観測 / llm 双方の import 経路を整理する大きな refactor で、PR3 の
  スコープを越える
- 既存テストもこの順序に依存しており、暗黙の前提として運用されている
- 既知債務として明示化することで、次に再発見した時に同じ調査をやり直さない

**どうしないと壊れるか**:
- 新規 module で何も考えずに ``ObservationOutput`` を eager import すると、
  別の import 経路で ``observation.contracts`` を先に初期化する側が circular に
  巻き込まれる
- test の import 順序を「アルファベット順に整理する」ような自動 formatter で
  並べ替えると壊れる (= test 側に明示コメントを残す責務がある)

**どこで出てきたか**: PR3 (Encounter Memory) の collector / test 追加時に再現。
subagent reviewer が「pre-existing だが新規 file が増えるたびに workaround が
拡散する」と指摘したのを受けて、債務として明示化

## 26. 勝敗は runtime でなくシナリオ専管 → game_end_conditions を書かなければ「永続世界」になる

**何を**: ゲームの勝敗 (win/lose) と終了条件は runtime にハードコードせず、
シナリオの ``game_end_conditions`` ブロック (``win`` / ``lose`` の条件配列) だけが
source of truth。``check_game_end`` は ``scenario.win_conditions`` /
``lose_conditions`` を評価するだけで、**両方が空 (= JSON に ``game_end_conditions``
を書かない) なら決して ``is_ended=True`` を返さない**。その世界は外的停止
(driver の ``MAX_WORLD_TICKS``) でしか止まらない「永続世界」になる。

参照シナリオ: ``data/scenarios/persistent_world_demo.json`` (勝敗条件を一切宣言
しない最小デモ)。回帰固定: ``tests/integration/test_persistent_world.py``。

**なぜこの形か**:
- escape / survival のような「クリア/失敗で終わる世界」と、勝敗のない「ただ
  生きる世界」を **同じ turn engine** で両立させたい (経路統一の目的)。勝敗を
  runtime の前提にすると永続世界が書けなくなる。
- 勝敗をシナリオ宣言に寄せることで、runtime は「終了条件を評価して報告するだけ」
  の world 非依存な部品になる (`docs/agent_design_principles.md` の疎結合)。
- ``ResolvedLlmRuntimeConfig`` (runtime 設定) には勝敗概念のフィールドを **持たせ
  ない**。config 側に win/lose を足すと、宣言しない永続世界にも勝敗が漏れる。
  これも ``test_persistent_world.py`` で固定する。

**どうしないと壊れるか**:
- escape 固有の集団 WIN/LOSE や outcome 判定を runtime のデフォルト挙動として
  再注入すると、``game_end_conditions`` を書かないシナリオが勝手に終了したり、
  永続世界の prompt に「脱出できない」等の勝敗前提テキストが漏れる
  (後者は別途 escape prompt の world 中立化で扱う)。

**どこで出てきたか**: 経路統一アーク U5。「勝敗なく永続的な世界を実現したい」と
いう要望に対し、capability は既にあった (空条件 → 終了しない) が、それを行使する
シナリオもテストも無かったため、参照シナリオ + 回帰テスト + 本項で固定した。
