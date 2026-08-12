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
- `schedules_turn` の audit は重要 (#412): HP 変化 / モンスター出現 / 発話 / アイテム overflow / 救助到達 / アイテムの受け渡し (drop / pickup / give) / etc. を漏れなく `schedules_turn=True` に揃える必要がある
- アイテム移動 3 種は初回 audit から漏れていた。v4 第 3 回 run で「`say_inline` を伴う受け渡しは発話観測が同席者を起こすので回るが、黙って渡すと相手が idle_timeout まで気づかない」と判明して追加した。audit 表の正本は `tests/application/observation/test_schedules_turn_audit.py` の docstring

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
| 26. 勝敗は runtime でなくシナリオ専管 → game_end_conditions を書かなければ「永続世界」 | 2026-06-25 | U5 経路統一 |
| 27. 新しい per-Being store は snapshot に乗せる前提で実装する (4 step checklist) | 2026-06-27 | PR #593 / #594 (PR-F + PR-G) |
| 30. ローカルLLMはレプリカ単位で常駐管理し、実験を同じレプリカへ固定する | 2026-07-25 | v108 夜間実験基盤 |
| 39. 実験モデルは版固定 ID を使い、接続先の能力は実呼び出しで確かめる | 2026-08-01 | PR #898 |

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

## 27. 新しい per-Being store は snapshot に乗せる前提で実装する (4 step checklist)

**何を**: 新しく per-Being scope の state を持つ store (= `BeingId` をキーに
保持する store) を追加するときは、その時点で `BeingMemorySnapshotService`
への配線まで含めて 1 PR にまとめる。「あとで足す」と後回しにすると、長走
実験の終了 → 再開で連続性が静かに壊れる silent failure になる。

実際 PR #580 (想起スロット) / #588 (afterglow) / #526 段階 2 (慣化) は
追加時に snapshot への追従が忘れられたまま main に入り、半年弱気付けな
かった。PR-F (#593) / PR-G (#594) で構造的 fail-fast と既存 3 store の
追従を入れたあと、次は「追加し忘れの再発を docs で 1 段目止める」のが本項。

**手順 (= 新 store 追加 PR でやること)**:

1. `BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS` に新 key を追加
   - 1 store = 1 key が原則。値の形が dict だが list 規約に合わせるため
     split が必要なら 2 key にしてよい (例: slot は entries と cooldown)
2. `BeingMemorySnapshotService.__init__` に新 store の引数を追加 (keyword-only)
   - Protocol 越しに渡せるなら `runtime_checkable` Protocol を使い、
     `isinstance()` で wiring 漏れを early detection する
3. `capture()` の payload dict に新 key の生成ロジックを追加
   - VO ↔ dict の codec は `_memory_payload_codecs.py` に集める
   - 1 を足して 3 を忘れると初回 capture で `SnapshotCoverageError` が
     起動時に投げられる (= PR-F の fail-fast)
4. `restore()` のデコード + 書き戻しを追加
   - store interface に `replace_all_by_being(...)` を必ず生やす。中身が
     空なら being の state を pop して「capture 時に空だった状態と完全に
     同じ姿で復元される」よう揃える
   - 実装の参照先: `InMemoryEpisodicRecallSlotStore.replace_all_by_being`
     (slot + cooldown) / `InMemoryAfterglowStore.replace_all_by_being`
     (entries のみ) / `InMemoryEpisodicRecallHabituationStore.replace_all_by_being`
     (mapping)。戻り値は `None`。
   - 1 を足して 4 を忘れると restore で `BeingMemoryPayloadFormatError` に
     化け、これも起動時に止まる

**追加で守ること**:

- `ExperimentSnapshotSession` の `fallback_used` ログ対象に新 store の属性名
  を追加する (= wiring 漏れで空 store が静かに使われる状態に気付ける)
- store interface に capture 用の read API (`list_all_by_being` 等) が
  無ければ追加する
- snapshot CLI (`scripts/being_snapshot_cli.py`) が新 store にアクセスできない
  in-memory sidecar なら、`cmd_save` で warning を残してユーザに「CLI 経由
  では dump されない」事実を伝える

**どうしないと壊れるか**:

- 1-4 のうちどれかを忘れると、`capture()` または `restore()` のどちらかが
  fail-fast で止まる。**全部を忘れた場合は構造で検出できない** ので、本項の
  チェックリストが最後の砦になる
- 「あとで snapshot 対応する」と後回しにすると、間に走った長走実験の trace
  に「想起階層の連続性が壊れた事実」が混入する。データに混入したノイズは
  後から取り除けない

**どこで出てきたか**: PR #594 (PR-G) で 3 store ぶんの追従漏れを一度に
解消した際、それ以前の 3 store を追加した一連の経路 (#580 / #583 が想起
スロット、#588 が afterglow、Issue #526 段階 2 が慣化 store) すべてが本
手順を踏んでいなかったことが判明したため、再発防止として本項を追加。

## 28. 実験に意味を持つ設定は profile/config だけから入れる

**何を**: LLM 実験の挙動を変える設定は、`data/experiment_profiles/*.json`
または `--experiment-config` の `runtime_config` だけから
`ResolvedLlmRuntimeConfig` に解決する。環境変数から同じ値を入れる互換経路は
作らない。例外は API キー、サーバのホスト/ポート、ローカル DB パスのような
秘密情報または実行基盤の設定に限る。

**なぜこの形か**:

- 1 つの値に複数の入力経路があると、run_start trace に残った値と実 runtime の
  値がずれる。過去の rolling_summary / prompt section / provider routing 系の
  静かな失敗はこの形で起きた。
- 実 LLM run はコストが高い。外側 shell に残った古い環境変数が混ざるだけで、
  比較不能な run ができてしまう。
- profile/config は成果物として `experiment.config.source.json` と
  `experiment.config.resolved.json` に保存できる。環境変数の履歴を後から完全に
  復元するより、入力を 1 本にする方が事故が少ない。

**実装上の決まり**:

- `run_scenario_experiment.py` は profile/config を process env に注入しない。
  `runtime_config` の mapping を直接 `ResolvedLlmRuntimeConfig.from_mapping(...)`
  に渡す。
- `create_world_runtime(..., config=cfg)` / `GameRuntimeManager(runtime_config=cfg)`
  / `create_llm_client_from_config(cfg)` のように、解決済み config を引数で渡す。
- 低レベル resolver は `env=None` でも `os.environ` を読まない。テストや移行用に
  mapping を渡す場合だけ、その mapping を読む。
- 新しい実験設定を足すときは、`ResolvedLlmRuntimeConfig`、profile、manifest、
  配線契約テストを同じ PR に含める。

**どうしないと壊れるか**:

- 「後方互換」として `LLM_*` や `BELIEF_*` を環境変数から読む経路を戻すと、
  profile に書いた条件と実 runtime の条件が分岐する。
- `LiteLLMClient` 内部で provider / model / reasoning / timeout を環境変数から
  読むと、manifest に残らないコスト条件が混ざる。
- 並列度や idle timeout も観測結果に影響しうるため、実験 run では config に
  固定して trace に残す。

**どこで出てきたか**: `v3coop_stagnation_001` / `002` 相当の「全部盛り」
実験条件を profile 化する作業中、ユーザから「API キー以外の env 入力経路は
廃止したい。一つの値に複数経路があることで過去にも苦しんだ」と指摘された。
そのため、後方互換よりも経路の単一化を優先する判断として固定した。

## 29. 再開境界で未通知観測を勝手に flush しない

**何を**: snapshot capture の直前に、日次集約などの未通知バッファを
強制 flush しない。未通知バッファ自体を world snapshot の subsystem として
保存・復元し、既存の tick 境界条件で後から配信する。

**なぜこの形か**:

- capture 前 flush は、連続 run なら日付境界で出る観測を snapshot 時刻に前倒し
  してしまう。これは resume run と連続 run の観測時刻をずらす。
- 観測駆動の LLM では、観測時刻のズレ自体が次の行動を変える。状態を保存する
  ために観測の発生時刻を変えるのは、再開品質として筋が悪い。
- 未通知バッファは「世界状態そのもの」ではなくても、未来に配信される予定の
  観測であり、実験の解釈に影響する。

**実装上の決まり**:

- `WorldRuntime._pending_spoiled` / `_pending_spoiled_day` のような
  未通知バッファは、専用 `WorldSubsystemCodec` で保存・復元する。
- codec は flush を呼ばない。復元後、既存の `advance_tick` / 日付境界処理に
  任せる。
- 追加時は「capture → restore 後に既存 flush 経路で観測が失われない」ことを
  テストで固定する。

**どうしないと壊れるか**:

- snapshot save が日付境界前に走ると、resume 後に「今日は X が腐った」という
  未通知観測が消える。食料管理の観察 run では、LLM が腐敗に気づく機会が
  静かに失われる。
- 逆に capture 前 flush にすると、観測は消えないが時刻が変わり、連続 run と
  resume run の比較可能性が落ちる。

**どこで出てきたか**: `belief_goal_full` の 200 tick 観察前に
snapshot/resume を主経路にできるかレビューした際、`_pending_spoiled` が
snapshot 対象外であることが見つかった。食料・腐敗が今回の重要観察対象なので、
flush ではなく codec による保存を採用した。

## 30. ローカルLLMはレプリカ単位で常駐管理し、実験を同じレプリカへ固定する

**何を**: v108のGemma 4 31BはH100 1枚につき1つの独立レプリカとして
GPU 0〜3、8100〜8103番へ固定する。プロセス寿命はユーザーsystemdで管理し、
異常終了時の再起動、HTTP死活確認、安全停止時の要求排出を共通の管理入口へ
集約する。実験を接続するときは、1 runの全要求を同じレプリカへ固定する。

**なぜこの形か**:

- 31Bの量子化モデルはH100 1枚に収まるため、4枚をテンソル並列で束ねるより、
  独立レプリカ4個の方が複数実験の総処理量と故障分離に向く。
- vLLMのプレフィックスキャッシュとKVキャッシュはレプリカ間で共有されない。
  要求ごとの単純なラウンドロビンでは、同じ実験の共通プロンプトが4台へ散る。
- 夜間実験では端末やCodexの会話寿命と推論サーバーの寿命を分離する必要がある。
  systemdへ寄せることで、開始、準備完了、異常再起動、正常停止の意味を一つにする。
- 停止前に`/metrics`の実行中・待機中要求を確認すれば、処理途中の要求を
  「終了したように見せる」静かな失敗を避けられる。

**どうしないと壊れるか**:

- `nohup`や端末上の親スクリプトだけで常駐させると、ログアウト、親プロセス終了、
  部分的な異常終了時の状態が曖昧になる。
- HTTP死活確認1回の失敗ですぐ再起動すると、起動時コンパイルや一時的な高負荷を
  障害と誤認する。連続失敗にだけ反応する。
- メトリクス欠落を要求0へ縮退すると、壊れたサーバーを排出完了と誤認して停止する。
- 推論サーバーの安全停止だけでは新しい実験の投入競合を防げない。後続の実験
  起動器では「新規割り当て停止」を要求排出より先に行う。

**どこで出てきたか**: v108のH100 4枚を使い、OpenRouterに依存せず複数の
長走実験を夜間に自走させる運用を検討した際、単純なロードバランサーでは
キャッシュ局所性と実験ごとの性能解釈が崩れることを確認したため。

## 31. テレポートの秘匿性は visibility ではなく「誰が居たか」で決まる

`TELEPORT_ENTITY` 効果 (隠し通路・ベント・魔法陣) を実装するにあたり、移動が
第三者に見えるかどうかを何で決めるかを選んだ。

**採用**: 出発スポットと到着スポットの presence だけで決まる。`teleport_entity`
は `move_entity` と同じ `EntityLeftSpotEvent` / `EntityEnteredSpotEvent` を
発火し、既存の観測経路がそれぞれのスポットの居合わせた者へ配る。誰も居なければ
誰にも観測されない = 秘密の移動が成立する。

**棄却**: `InteractionEffect.visibility` (ACTOR_DIRECT / PUBLIC_OBSERVABLE /
HIDDEN) で制御する案。物理的にその場に居る者が「消えた人」を見落とす表現は
不自然で、`HIDDEN` を許すと「目の前から人が消えたのに誰も気づかない」世界に
なる。他の効果 (ダメージ・状態異常) は身体の内側で起きるので visibility が
意味を持つが、移動は外形的な事実である。

ただし visibility を書いても黙って無視されると「HIDDEN にしたから見られない」
と誤解したまま秘密の移動を期待されるので、`TELEPORT_ENTITY` に visibility を
書いたシナリオは **読み込み時に `ScenarioLoadError` で落とす**。効かない設定を
黙って受け取らない。

同じ理由で、行き先 (`parameters.target_spot`) を欠いた `TELEPORT_ENTITY` も
読み込み時に落とす。domain 側は `spot_id <= 0` なら spec を作らない実装なので、
放置すると「書いたのに何も起きない」静かな失敗になる。`target_spot` を effect の
直下 (parameters の外) に書いた場合も同様に無言で消えるため、両方を弾く。

### 現在地と同じスポットへのテレポートは no-op

出発していないのに `EntityLeftSpotEvent` を流すと、同席者に幽霊のような出入りが
観測される。例外にはしない (ランダム転送などで正当に起こりうるため)。

### 複数 tick 移動との衝突は未解決 (既知の制約)

`PlayerSpotNavigationState` は本集約とは別に「どの接続を辿っている途中か」を
保持する。移動中の entity をテレポートさせると、次の `advance_spot_travel_one_tick`
が「接続の始点に居ない」として `EntityNotAtSpotException` を投げる。

現在この経路は踏めない。`teleport_entity` の呼び出し元は interact だけで、
行為者自身しか飛ばせず、移動中のプレイヤーはターンが回らないためである。ただし
この不変条件は別の層 (ターン割り当て) が担保しており、`teleport_entity` 自身は
何も知らない。**他者を飛ばす効果や trap 由来のテレポートを足すときは、呼び出し
側で移動状態を先に解消すること。** 症状は
`tests/domain/world_graph/aggregate/test_spot_graph_teleport_entity.py` の
`TestTeleportVersusConnectionMovement` が固定している。

## 32. 環境変化 (CHANGE_ATMOSPHERE) は部分更新にする

`CHANGE_ATMOSPHERE` 効果 (停電・気温変化・危険度上昇) の適用にあたり、
`SpotAtmosphere` をまるごと置き換えるか、指定項目だけ差し替えるかを選んだ。

**採用**: 部分更新。`update_spot_atmosphere` は渡された項目だけを差し替え、
指定しなかった項目 (`sound_ambient` / `smell` / `sound_intensity` など) は元の
値を保つ。停電で明るさだけ変えたいときに環境音や匂いまで既定値へ巻き戻ると、
その spot の描写が静かに壊れるため。`SpotNode` も `SpotAtmosphere` も frozen
なので `dataclasses.replace` を二段重ねる。

**棄却**: spec の内容でまるごと差し替える案。シナリオ作者が「明るさだけ変えた
つもり」で全部を消す事故が避けられない。

### 未設定 spot の既定は BRIGHT

`atmosphere` を持たない spot に `hazard_level` だけを指定した場合、明るさは
既定の `BRIGHT` が入る。「未設定 = 明るい」を安全側の既定とする — 暗いと視認
(`monster_visibility_service`) や戦闘の判定が変わるので、書かれていない spot を
勝手に暗くしない。

なお `hazard_description` を `None` に戻す (クリアする) 用途には非対応。
部分更新は「渡した項目だけ差し替える」ため、`None` は「指定なし」と区別できない。
クリアが必要になったら別途 sentinel を設計する。

### イベントは発火しない

環境変化の観測は interaction 側の `AppliedEffectSummary(kind=ATMOSPHERE_UPDATE)`
が `SpotPublicEffectObservedEvent` として同 spot の第三者へ届ける。集約側でも
イベントを出すと同じ変化が二重に観測される (#812 で直した interact の二重発火と
同型)。

### 読み込み時に弾くもの

`#31` (テレポート) と同じ方針で、書いたのに何も起きない経路を loader で塞ぐ。

- `parameters.target_spot` が無い: domain 側は `spot_id <= 0` なら spec を作らない
- `lighting` / `temperature` が enum 名として未知: 綴り間違いが実行時まで気づけない
- 変更項目が 1 つも無い: 何も変えない宣言は書き忘れとみなす

いずれも `ScenarioLoadError`。効かない設定を黙って受け取らない。

### interaction と scenario_events の両方から適用する

停電や気温低下は「誰かが操作した結果」だけでなく「時刻や条件で世界の側が変わる」
形でも起きる。`SpotGraphScenarioEventStageService` でも `atmosphere_update_specs`
を消費し、ON_TICK で照明を落とす表現を書けるようにした。

一方 `TELEPORT_ENTITY` は scenario_events では意味を持てない (行為者が居ないので
誰を飛ばすか決まらない)。黙って捨てると気づけないので、この経路で宣言された
場合は警告ログを残す。

## 33. 能動想起ツールは測定条件が整うまで profile 側で OFF にする

`SEMANTIC_SEARCH_ENABLED` と `EPISODIC_EXPLORE_RELATED_ENABLED` は、もともと
「`memory_search_semantic` / `memory_explore_related` を LLM に露出する」
設定として profile に書かれていた。しかし実験 runtime 側の露出制御が未配線で、
過去 run ではどちらのツールも一度も LLM に提示されていなかった。つまり true と
宣言していたが、実験条件としては実質 OFF だった。

#851 で露出制御が実際に効くようになったため、profile の true をそのまま残すと
次の run から突然 2 つの能動想起ツールが増える。これは正しい実装挙動ではあるが、
直近 run との比較条件を変え、さらに memo ツール表示制御の A/B 実験と干渉する。
どちらもターンを消費する能動想起であり、memo を減らして行動枠を返す効果を測る
局面では逆方向の圧力になる。

そのため `belief_goal_full` と `ablation_base` では、当面
`SEMANTIC_SEARCH_ENABLED=false` / `EPISODIC_EXPLORE_RELATED_ENABLED=false`
に明示する。これは「宣言したのに効いていなかった」状態から「意図して切っている」
状態へ移すための変更である。`EPISODIC_RECALL_ENABLED` は run 003 で実際に使われた
既存条件なので true のまま維持する。能動検索・関連探索は、後でまとまりとして
評価するときに profile で再度有効化する。

## 34. memo A/B は「蒸留ありの手帳」と「手帳なし」を比較する

v4 第3回 run では `memo_add` / `memo_done` / `memo_list` が全行動の約15%を
占めた。memo section の文字量は小さい一方、1ターン1ツール制約では memo を書いた
ターンに移動・探索・会話ができない。記憶システムが強くなった状態で、この手帳枠が
まだ必要かを測るため、`belief_goal_full` を基準にした A/B profile を分ける。

採用する腕は2本にする。A は `belief_goal_memo_ab_keep_memo` で、
`MEMO_TOOLS_ENABLED=true` のまま memo tool を露出し、`MEMO_DISTILL_ENABLED=true`
により `memo_done` を semantic 記憶の `BeliefEvidence` へ蒸留する。これは
docs/memory_system/short_term_memory_design.md が想定していた「memo = 目標・計画層」
を実際に動かす腕である。B は `belief_goal_memo_ab_hide_memo` で、
`MEMO_TOOLS_ENABLED=false` により memo tool と未完了 memo section、memo 完了 hint を
隠す。記憶本体 (episodic / semantic / passive recall / rolling summary) は止めない。

`ablation_base` は stagnation reasoning を落とした比較土台であり、memo A/B とは目的が
違う。したがって memo A/B の2 profile は `belief_goal_full` 系として置き、互いの差分は
`MEMO_TOOLS_ENABLED` の1キーだけにする。#33 で OFF にした
`SEMANTIC_SEARCH_ENABLED=false` / `EPISODIC_EXPLORE_RELATED_ENABLED=false` は両腕で維持し、
能動想起ツールの増加を memo 実験に混ぜない。

memo A/B の scenario は `survival_island_v4_coop.json` に固定する。v4 第3回 run との
比較可能性を保つためであり、v3 には position / area / distant cue が無く #35 の
「拠点から山影が見える」変更が効かないためである。run 時の `SCENARIO=` 上書きには
頼らず、profile を読めば実験条件が分かる状態にする。

## 35. `is_outdoor` 未宣言の屋内扱いは validator で見える化する

`SpotNode.is_outdoor` は既定 false のまま維持する。洞窟・廃屋・小屋など、空や
遠景が見えない spot を壊さないためである。一方で、未宣言が黙って屋内扱いになると、
遠景 (`distant_view`) や天候表示が抑止され、症状は「なぜか目標が見えない」として
しか表れない。

v4 第3回 run では、最長滞在拠点だった `hidden_cove` が `is_outdoor` 未宣言で屋内扱い
になり、拠点から山影が一度も見えていなかった。description 上は海に開けた入江であり、
屋内意図は読み取れないため、v3/v4 では `is_outdoor: true` を明示する。ただし v3 は
position / area / distant cue が未整備なので、この宣言だけでは遠景は出ない。v3 側の
宣言は、将来 v3 に遠景材料を足したときに同じ屋内抑止を再発させないための前準備である。

v4 ではこの変更により、次の本命 run で拠点から「切り立った山影」が見える。run 003
との比較では、この目標 cue の露出条件が変わったことを明記する。

既定値は変えず、`validate_spot_map` が屋内扱い spot と `is_outdoor` 未宣言 spot を
info / metrics に出す。シナリオ作者が map 検査時に「本当に屋内扱いでよいか」を確認
できるようにし、既存シナリオの意味を反転させない。

## 36. object.state の prompt 表示は scenario 側で宣言し、未宣言値は隠さない

`SpotObject.state` は interaction の前提条件や effect の真実源であり、`opened=false`
や `lit=false` のような値がそのまま prompt に出ると、エージェントには意味の薄い
内部表現として見える。一方で、状態表示をコード側で key ごとに決めると、シナリオ固有の
文脈 (「宝箱はまだ開いていない」「狼煙台に火はついていない」など) を失う。

そのため `StateDisplayRule(key, value, text)` を scenario の object に宣言し、
`visible_state()` が一致する key/value を日本語 tag に変換する。`available=false`
だけを `unavailable_hint` で特別扱いしていた既存設計を一般化した形であり、
`available` も明示 `state_display` があればそちらを優先する。

重要なのは、宣言の無い key/value を隠さないこと。key に rule があっても現在値に
対応する rule が無い場合は、従来どおり raw state を出す。ここで隠すと、
シナリオ作者の宣言漏れが prompt からもテストからも見えなくなり、再び静かな失敗になる。
v4 だけは hard audit で raw state を禁止し、他シナリオは quality テストで棚卸しする。

値比較では `False == 0` / `True == 1` を同一扱いしない。bool state と数値 state は
別概念なので、型を含む同一性キーで rule を照合する。

累積カウンタは完全一致だけでは上限の次の値で raw state に戻るため、整数下限の
`at_least` ルールも許可する。完全一致を最優先し、該当しない場合だけ、現在値以下の
`at_least` のうち最大閾値を使う。閾値に届かない値や整数以外には規則を広げず、従来
どおり raw state を出す。これにより「3 本以上なら次の判断は同じ」という表示はまとめ
つつ、宣言漏れを隠す #36 の安全策は維持する。bool は整数下限の対象にしない。

## 37. いまできない object action は候補から消さず、選べる行動とは別行に出す

object 行の `[...]` は LLM にとって「ここから action_name を選ぶ」欄として働く。
その中に `search(棚を調べた後)` のような現在必ず失敗する action を並べると、
選べる行動に見える。一方で、候補から消すと説明文だけが操作を誘う状態になり、
存在しない action_name を発明する実測がある。

そのため、`SpotGraphInteractionEntry` ではヒントを 2 種に分ける。

- `condition_hints`: 時刻・天候・明るさのような宣言由来の制約。選べる行動欄の
  `action(夜不可)` に残す
- `blocking_hints`: OBJECT_STATE や OBJECT_STOCK_AT_LEAST のように、現在値を読んだ
  結果いま満たしていない理由。`[...]` から外し、`いまできない:` 行へ出す

`ToolRuntimeTargetDto.available_interactions` は表示とは独立して、従来どおり全
action_name を持つ。これは resolver の入力候補であり、prompt の整形都合で削っては
いけない。表示は「選べるもの」と「いまできないもの」を分けるが、解決可能な候補集合は
変えない。

同席者への `give_item` 手がかりも、各 player 行に同じ文を繰り返さず見出しへ集約する。
ただし死亡・ダウン中の相手には渡せないため、見出し文は「倒れていない相手には」と
条件を含める。行ごとの死亡・ダウン表示と所持品表示は維持する。

## 38. action_name は意味ラベルで補い、多義語は動詞 + 目的語へ寄せる

interaction には `display_label` が既に宣言されており、観測側では「持ち物を奪う」の
ような意味表示に使われていた。しかし選択前の prompt では `action_name` だけが出ており、
エージェントは裸の識別子から意味を推測していた。`take` を「診る・手当てする」と解釈し、
失敗文を読んでも治療行為だという前提が剥がれなかったのは、この非対称が原因である。

そのため、選択前の表示でも `display_label` を必須の意味情報として扱う。空や
`action_name` と同一の `display_label` は、意味を持つ文字列が無いのと同じなので
監査で落とす。欠落・空白は `ScenarioLoader` で読み込み時に止め、KeyError や後段の
別エラーに流さない。

ただし表示だけでは足りない。LLM が実際に tool 引数へ渡すのは `action_name` であり、
介入実験でもラベルを添えた側が `take` と書き続けた。そのため action 名自体も
「動詞 + 目的語」に寄せる。`loot_from_downed` のように前提条件の一部を名前へ埋め込むと、
立っている相手に撃つことが名前の時点で矛盾になる。

改名前の段階では、多義語 denylist を quality 棚卸しとして置く。既存シナリオにはまだ
違反が残るため通常 CI では落とさず、改名 PR で違反を消してから hard audit に昇格する。
改名後は `take` / `search` / `light` などの裸動詞を通常監査で落とす。新しい
interaction を足すときは、`search_wreck_hold` や `loot_from_downed` のように
動詞と対象を名前に含める。

## 39. 実験モデルは版固定 ID を使い、接続先の能力は実呼び出しで確かめる

**何を**: OpenRouter 経由の実験では、特定の版を指すモデル ID を profile に固定する。
DeepSeek V4 Flash の 2026-07-31 更新版は、新しい `belief_goal_v4` profile から
`deepseek/deepseek-v4-flash-0731` を使う。接続先は、同モデルを fp8 で提供し、
`tool_choice=required` の実呼び出しに成功する Cloudflare に固定する。既存 profile は
過去の実験意図を表す記録なので書き換えず、新しい実験条件には新しい profile を足す。

**なぜ**:

- DeepSeek 直結 API の `deepseek-v4-flash` は常に最新版を指す。一方、OpenRouter は
  4月版を `deepseek/deepseek-v4-flash`、7月31日版を
  `deepseek/deepseek-v4-flash-0731` と別 ID にしている。この版固定により、実験の
  途中で同じ ID の中身が黙って変わり、過去 run と比較できなくなる事故を避けられる。
- 7月31日版の DeepSeek 公式 endpoint は `supported_parameters` に
  `tool_choice` を掲げながら、`required` と特定関数指定を 404 で拒否した。
  `supported_parameters` は接続先の宣言であって、値ごとの動作保証ではない。
  実験で必須の値は、本番と同じ provider 固定・reasoning 無効・tool schema で
  実際に呼び出して確かめる必要がある。
- `tool_choice=auto` に下げると tool call の無い応答を許し、エージェントが1回の
  起動を黙って失う静かな失敗になる。Cloudflare は総当たりした接続先のうち、
  fp8 と `required` を両立した唯一の選択肢だった。DeepInfra も `required` は通るが
  fp4 のため、モデル品質を上げる目的に合わない。
- Cloudflare の cache read 単価は DeepSeek 公式の10倍だが、run 004 の実測量では
  200 tick あたり約 0.10 USD の増加に収まる。速度、prompt 単価、completion 単価、
  キャッシュ動作は同等だったため許容した。

**どうしないと壊れるか**:

- 日付の無い可変 ID を固定版だとみなすと、モデル更新時点を後から特定できず、
  同じ profile 名の run 同士が比較不能になる。
- 既存 profile を新しいモデルへ上書きすると、過去 run がどの条件と意図で設計されたかを
  profile 自体から読めなくなる。`experiment.config.resolved.json` が実測条件を残していても、
  profile が担う実験計画の履歴は代替できない。
- `supported_parameters` だけを見て対応済みと判断すると、実行時の 404 を
  profile 読み込みや単体テストで検出できない。外部 endpoint の能力差には、通常の
  試験から除外した `tests/quality/` の実呼び出しプローブを置く。
- DeepSeek 公式が `required` に対応した後も Cloudflare 固定を惰性で残さない。
  プローブは「まだ拒否される」間だけ成功し、対応した瞬間に失敗して再検討を促す。
- 新しいモデル条件を既存 profile 群へ一括反映しない。新しい profile と継承元の差を
  テストで限定し、意図していない設定差や継承元の書き換えを許さない。

**どこで出てきたか**: DeepSeek V4 Flash 0731 への更新調査と接続先の総当たりを
行い、公開メタデータと実際の `tool_choice=required` 対応が一致しないことを確認した
PR #898。

## 40. `CALL_MEETING.trigger` は宣言値を実行まで運び、未知値へ縮退しない

`CALL_MEETING` の `parameters.trigger` は、会議状態と観測に残る招集理由である。
domain の効果結果までは値を保持していたが、application の callback が行為者しか
受け取らず、`WorldRuntime` が常に `emergency_button` を記録していた。この形では
シナリオに別の値を書いても成功扱いのまま宣言が消える。

そのため callback の契約を `(player_id, trigger)` とし、効果結果から
`begin_meeting` まで同じ値を運ぶ。効果側で既定値を補わず、省略・未知値は loader と
domain の両方で拒否する。許可値は domain の `CALL_MEETING_EFFECT_TRIGGERS` を
単一の出所とし、現在は `emergency_button` だけを認める。

`body_report` は死体との同席や重複報告を検査する別の招集入口であり、
`CALL_MEETING` の許可値には含めない。まだ存在しない2種類目の effect trigger のために
回数・クールダウンの規則表は先回りして作らず、実際の宣言を追加するときに、その値と
規則と試験を同時に追加する。

## 41. 差し替え口の単体試験だけでなく、本物の接続を通す

モンスター攻撃の状態異常は、`SpotAttackOrchestrator` に provider を差せる設計と
確率適用の単体試験を持っていた。しかし実runtimeの provider は
`monster.template_id` という存在しない属性を読み、例外を空の候補へ縮退させていた。
実際の属性は `monster.template.template_id` であり、2026-06-21の一括改名以降、
狼・野犬・毒蛇・大型カニの状態異常は一度も発火していなかった。

差し替え口 (seam) を用意して単体試験することは、効果適用ロジックの検証には有効で
ある。しかしスタブを直接差す試験だけでは、production の組み立てが正しい provider を
接続しているかは保証できない。差し替え可能な設計ほど、少なくとも1本は本物のloaderと
runtime組み立てを通り、公開入口の最終的な振る舞いを観測する試験が必要である。

モンスター攻撃では `execute_monster_attack` からプレイヤーの `active_effects` までを
観測し、4テンプレートの効果種別・確率境界・持続tick・強度を固定する。既知
テンプレートの効果が欠ければ公開入口の試験が失敗するため、配線不良を成功扱いの
まま通さない。

この修正以降は、狼・野犬が50%で12 tickの出血、毒蛇が60%で10 tickの毒、
大型カニが35%で8 tickの出血を実際に付与する。生存難易度が上がるため、修正前の
runと比較するときは実験条件の差として明記する。

## 42. モンスター固有の攻撃能力はテンプレート宣言を単一の出所にする

攻撃時状態異常の種別・確率・継続tick・強度は、モンスターの識別子をruntimeの
固定辞書へ照合して決めず、`MonsterTemplate.attack_status_effects` に宣言する。
識別子の逆引きproviderは、テンプレート定義と実行規則を別々に発展させ、実在しない
属性参照を空の効果へ縮退させた直接原因だったため、互換経路を残さず削除する。

`ScenarioLoader` は文字列の `effect_type` を `StatusEffectType` へ変換し、確率の
値域、正の継続tick、数値の強度を起動時に検証する。実行時に未知種別を無視したり、
確率や継続tickを丸めたりしない。ロード済みテンプレートはすでに有効なので、
`SpotAttackOrchestrator` は宣言を直接確率判定するだけにする。新しいモンスターは
コードの対応表を変えず、JSON宣言だけで新しい状態異常能力を持てる。

静的定義をSQLiteへ保存する経路でも同じ一覧を正規化した子表へ保存し、順序を含めて
復元する。シナリオから直接起動する経路だけを直してSQLite経路を空にすると、起動方法で
能力が分岐するためである。状態異常を持たないテンプレートは空タプルで表し、旧provider
や別形式への分岐は置かない。

この全面移行では、同じ4種を含む島シナリオ5本すべてへ宣言を追加する。過去シナリオの
hashは変わるが、二重経路を残して数週間後に別々の仕様へ発展させないことを優先する。
過去runの実測条件は各runの `experiment.config.resolved.json` とscenario hashで確認する。

## 43. 個人結果・終了・生存圧を別々の宣言にし、旧一体型経路を残さない

島シナリオの救助判定は、救助時刻・狼煙・山頂在席・取り残し期限・飢餓ダメージを
`outcome_resolution` という一つの専用設定にまとめ、runtime の固定サービスが解釈して
いた。この形では救助以外の個人結果を持つ新しいシナリオを追加するたびに、シナリオと
コードを一緒に変える必要がある。

個人結果は `player_outcome_rules`、混合集団結果の終了は
`game_end_conditions.end`、生存圧は `needs` に分ける。個人結果規則の発火条件には
既存の `ScenarioEventCondition` と `ScenarioConditionEvaluator` を再利用し、
`trigger` と `player_conditions` を分離する。前者は救助船のような機会が来たか、後者は
その機会の対象者を表す。対象者が0人でも `once` の機会は消費済みにし、後から同じ船を
利用できないようにする。発火済み状態は既存の scenario event 進捗ストアに保存し、
snapshot 再開でも再発火させない。

RESCUED / STRANDED / DEAD が混在する世界終了を `win` や `lose` に置くと宣言が嘘に
なるため、中立の `end` 配列で `ALL_PLAYER_OUTCOMES_RESOLVED` を宣言する。対象者0人を
全員確定とみなさず、終了条件を持たない永続世界は自動終了させない。

旧 `outcome_resolution` は互換経路として残さない。4本の島シナリオを一度に新形式へ
移し、旧設定型・旧サービス・runtime 分岐を削除し、旧キーは読み込み時に明示的に拒否
する。過去シナリオの hash は変わるが、過去 run の実測条件は各 run の
`experiment.config.resolved.json` と scenario hash で確認する。二つの経路を並存させて
別々に発展させるより、シナリオ作者が使う入口を一つに保つことを優先する。

`END_ON_ALL_DOWN` は世界内の勝敗や個人結果を決める規則ではなく、全員が行動不能な
実験を回し続けないための外的停止として扱う。特定の個人結果モードへ埋め込まず、
`check_game_end` の共通入口でシナリオ宣言より先に評価する。終了理由には設定名を含め、
世界内の `game_end_conditions` が成立した終了と後から区別できるようにする。

## 44. ツール露出は世界・フェーズ・本人状態を公開入口で合成する

run 011 では、投票済みのエージェントへ次のターンでも `vote` が提示され、
`ALREADY_VOTED` が 2 回発生した。`GamePhaseStore` は投票済みを把握していたが、
`get_tool_definitions()` と実際の LLM payload 生成が `player_id` を受け取らず、
本人固有の利用可否を判断できなかった。

投票後は票を変更できないため、本人にとって `vote` は「選べるが必ず失敗する手」になる。
この判定を prompt builder や実行器へ個別に足さず、`ToolExposure.split_for_phase` を
静的な世界宣言・会議フェーズ・本人の投票状態を合成する単一の入口とする。
`get_tool_definitions(player_id=...)` から最終的な LLM payload まで同じ本人 ID を運び、
投票済み本人からだけ `vote` を外す。未投票者の `vote` と全員の `speak` は残す。

`get_tool_definitions` は、本人向けの `player_id` と起動時の全員検査向けの
`for_every_player=True` のどちらか一方を必須とする。対象を省略した呼び出しを
全員向けとして扱うと、本人状態の運び忘れが従来動作へ黙って縮退し、今回と同じ
欠陥を再導入できるためである。`ToolExposure.split_for_phase` の
`voting_completed` も既定値を持たせず、呼び出し側が本人状態を明示する。

投票の進捗は `MeetingVoteCastEvent` で全参加者に知らせるが、イベント自体に投票先を
持たせない。締切前に公開するのは投票者名と残り人数だけであり、構造化観測や trace の
別経路から投票先が漏れるのを防ぐ。投票者本人はツール結果で把握しているため配信対象から
外し、同じ事実による重複観測と余分な自己起床を作らない。

## 45. scenario event の世界文脈条件は既存の語義と状態の出所を再利用する

妨害の進行停止と複数人での解除をシナリオから宣言できるよう、
`ScenarioEventCondition` に `GAME_PHASE_IS` と `PLAYERS_AT_SPOT` を加える。
別の条件評価器は作らず、scenario event・reactive binding・個人結果規則が共有する
`ScenarioConditionEvaluator` に集約する。条件名と評価分岐の網羅性は
`KNOWN_CONDITION_TYPES` の双方向監査で固定し、未知名を永久に偽の条件として通さない。

`GAME_PHASE_IS.game_phase` は `GamePhase.value` の既知値だけを読み込み時に許可する。
評価時は `WorldRuntime` と同じ唯一の `GamePhaseStore` を provider 経由で読み、未配線を
`False` に縮退させず構成エラーとして止める。別 store を作ると、会議へ遷移しても条件が
自由時間を見続けるためである。

人数条件には新しい `PLAYER_COUNT_AT_SPOT` を作らない。interaction 条件に既にある
`PLAYERS_AT_SPOT` を scenario event でも同じ意味で使い、`target_spot` の
`graph.presence_at(...).present_entity_ids` が必要人数以上なら成立する。必要人数の既定値は
既存と同じ2人とする。`PlayerStatusRepository` と突き合わせると「その場に居る」の出所が
二つになり、同じ語が利用箇所ごとに異なる意味を持つため採らない。

この語義では down 状態の人物も在席数に含む。これは妨害操作に適した人物を意味するから
ではなく、既存の `PLAYERS_AT_SPOT` と意味を分岐させないためである。将来「動ける人数」が
必要になった場合は、既存語の意味を静かに変更せず、`is_down` を除外する別の条件として
意図を名前に表す。

どちらの条件も engine 内部の述語であり、tick や秘密の状態をプロンプトへ直接表示しない。
新しい永続状態も持たないため snapshot の追加配線は不要である。

## 46. 物体の存在・操作の公開・視認性を同じ空集合へ潰さない

物体が現在地に存在すること、その行為者へ公開できる操作があること、暗さの中で
物体を視認できることは別の事実である。公開操作が0件という理由だけで物体を
resolver候補から外すと、目の前に存在する物体へ「この場所に無い」と返してしまう。
一方、世界に操作が1件も宣言されていない情景用物体は、従来どおりinteract候補に
しない。

行為者の `PLAYER_STATE_IS` により全操作を伏せた物体は、操作名を空のまま対象として
解決する。未定義の操作名を送られた場合も、秘密の操作名や件数を列挙せず、条件に
宣言された本人向け `failure_message` だけを返す。これにより「担当ではない」という
次の判断材料を届けつつ、偽装版の存在は漏らさない。

暗さで見えない物体はresolver候補へ入れない。現在状態を作る同じ視認判定から、
暗さで伏せた名前を内部contextへ運び、LLMがその名前を指定した場合だけ
「暗くて見えない」と返す。候補一覧へ名前を出したり、暗所でも操作を実行可能に
したりはしない。これにより、不存在と視界不良を同じ失敗文へ潰さず、灯りを探す
行動へつなげる。

## 47. 提示後の状況変化と一覧外の選択を同じ失敗へ潰さない

LLM の判断はプレイヤーごとに並列で作り、世界への適用は順番に行う。同じ tick の
先行者が会議を始めると、後続者が自由時間の一覧から正しく選んだ `interact` でも、
適用時には会議中なので実行できない。このとき「一覧に出ているものから選ぶこと」と
返すのは、本人が実際に見た一覧と矛盾する。

「いま使えるか」は従来どおり `get_tool_definitions` を唯一の出所として実行時に判定する。
「選んだ時点で一覧に載っていたか」は `_LlmPhaseAResult.tools_payload` に保持された、実際に
LLM へ送った内容だけを出所とする。prompt 時の条件を後から引き直す経路は作らない。

現在は使えず、送信済み一覧には載っていた場合を `TOOL_BECAME_UNAVAILABLE` とし、状況が
変わったため実行できないことを伝える。最初から一覧に無かった場合は従来の
`TOOL_NOT_OFFERED_NOW` と案内を維持する。両者は本人の選択の正しさも、trace で分析すべき
原因も異なるため、同じ error code にまとめない。どちらも次 tick に起こし、変化後の一覧
から選び直せるようにする。

## 48. 襲撃の可否と目撃可能性を分け、派生 action は待ち時間を共有する

暗所だけで襲撃できる規則では、光源を持つ本人が部屋を `DARK` から `DIM` へ変える
だけで襲撃を受けなくなる。同室全体が明るくなること自体は光の性質として正しいが、
灯りが本人を無敵にするのは社会的推理の駆け引きにならない。一方、襲撃の
`witness_policy` が常に `ACTOR_ONLY` だと、明るい場所に第三者が居ても加害者を
目撃できず、「居合わせた者にしか見えない」という公開説明とも食い違う。

襲撃できるかと、誰の仕業か特定できるかを別の問いとして扱う。暗所用の
`strike_down` は従来どおり匿名かつ第三者へ対人観測を出さない。暗所以外で使う
`strike_down_in_light` は `SAME_SPOT` とし、居合わせた者へ加害者名と対象名を
届ける。暗所へ匿名の目撃文は足さない。倒れた身体の発見だけを情報源として残し、
襲撃だったと即座に確定させないためである。灯りは免疫ではなく、その場で起きた
ことに加害者の名前を与える道具になる。

明暗の action を別々に宣言しても、再使用間隔は一つである。同じ意味の action を
交互に使って待ち時間を迂回できないよう、`InteractionDef.cooldown_group` を共有キー
として宣言し、省略時だけ従来の `action_name` へ戻す。対人操作と物体操作の両方が
このキーを読み、物体操作では従来どおり object id も組み合わせる。待ち時間ストアを
分けず、既存 snapshot の文字列キー形式も変えない。

`cooldown_group` は空文字や `object:` 接頭辞を読み込み時に拒否する。後者は物体操作の
内部キーに予約済みで、許すと対人と物体の待ち時間が静かに衝突するためである。
既存 snapshot では、group が旧 action 名と異なる宣言だけキーが変わり、その行為の
過去の待ち時間が一度失われる。`station_drill` は既存 action 名の `strike_down` を group
に使うため、暗所襲撃の保存済み待ち時間は維持される。

エージェントへ灯りの意味を伝える経路は、prompt に出ない item description に頼らない。
全員が読める当番表の `read_board` 結果へ共有規則を置く。item description も作者向け
宣言として実態に合わせるが、エージェントへの伝達を担ったとはみなさない。

## 49. tool にそのまま渡せる文字列だけを引用符で囲む

run 016 / 017 で、LLM が action の意味ラベルや、条件ヒントまで含む
表示行を `action_name` に送り、計 8 件失敗した。物体名・人名・移動先名は
引用符つきだったが、action だけが `当番表を読む (read_board)` のように
「渡す値」と「渡さない説明」を同じ括弧に入れていた。

プロンプトの規約を「引用符で囲まれた文字列だけが、tool 引数へそのまま
渡せる値」とする。action は `当番表を読む → "read_board"`、必須パラメータは
`"text" が要る`、接続は `"集会室の扉" → "連絡通路"` と表す。意味ラベルや
条件ヒントは引用符で囲まない。

整形処理ごとのテストだけでは、新しい表示経路の書き忘れを止められない。
`build_llm_context` が同時に作る `current_state_text` と `tool_runtime_context` を照合し、
全 target の `display_name` と `available_interactions` が引用符つきで本文にあることを
確かめる。起動時は全 player を検査して落とし、run 中は実験データを失わないよう
`prompt_argument_contract_violation` trace に残して続行する。

起動時検査の snapshot 構築では、monster や倒れた人の初回観測通知を一時的に
止める。検査は読み取り専用であり、Encounter Memory の「一度きり」を先に消費
してはならない。observer は検査終了時に必ず復元し、最初の prompt 構築で通常どおり
観測と `schedules_turn` を発火させる。

除外リストは持たない。暗所で伏せた物体は snapshot 構築時に落ち、targets に登録
されないため検査入力に現れない。将来それを targets に載せるなら、本文から
指定できない候補を作ることになるため、この検査が止めるのが正しい。
この変更は tick ごとに変わる `current_state_text` の書式だけを変え、プレフィックス
キャッシュに載る静的セクションは変えない。

## 50. 直近の出来事の時刻は記録時の世界内絶対時刻で固定する

「直近の出来事」は一度追加した行が変わらない安定した接頭辞として設計されている。
しかし描画時刻から「たった今 / 数分前 / さっき」を毎回計算すると、同じ entry の
本文が時間経過だけで書き換わる。この不変条件を回復するため、観測と行動結果へ
記録時の `game_time_label` を焼き込み、描画側は保存済みのラベルだけを使う。

相対ラベルを記録時に凍結する案は採らない。実 run
`v4coop_0731_007` の 6,983 行を測ると、凍結ラベルと描画時点の本来のラベルが
食い違う行は 4,143 行 (59.3%)、行動行では 3,669 / 4,980 行 (73.7%) だった。
「たった今」のまま古くなる文面は安定していても嘘になる。世界内絶対時刻なら、
記録後に変わらず、エージェントが暮らす世界の時間としても正しい。

調査で絶対時刻が欠けていたのは、通常の観測ではなく4つの配線だった。行動結果、
heartbeat、行動失敗、ループ警告の各境界で時刻または provider を必須にし、5つ目の
渡し忘れを既定の `None` へ縮退させない。旧 prompt の欠落479行は heartbeat 207行、
行動失敗261行、ループ警告11行で、通常の trace 観測416件には欠落がなかった。

この判断が保証するのは「追加済みの行本文が後から変わらないこと」と「時刻表現が
真実であること」だけである。行動結果ストアは最新20件のスライディングウィンドウで、
追加のたびに先頭行が落ちるため、この変更単独でプレフィックスキャッシュの命中率が
上がるとは主張しない。

## 51. 観測と行動結果は記録時から一つの時系列へ置く

観測と行動結果は届く入口が違うため別々のストアに保存され、描画時にだけ時刻順へ
合流していた。この分割は記憶の意味によるものではなく、観測は15件でL4へ畳む一方、
行動は20件の窓から古いものを落とすという別々の政策を生んだ。中期記憶へ自分の行動が
一件も渡らない原因にもなっていた。

記録時の表現を `UnifiedRecentEventEntry` に統一する。共通の外枠は
`occurred_at`、`game_time_label`、`kind` だけとし、観測と行動結果の固有項目は既存DTOを
payloadとして保持する。18項目ある行動DTOを平坦化して観測へ多数の `None` を持たせない。
既存の消費側には種類別の読み取り口を渡し、この段階では描画件数、観測15件でのL4生成、
行動・観測それぞれの保持上限を変えない。「格納場所の統一」と「窓の政策変更」を別PRに
して、本文の変化がどちらに由来するかを切り分けられるようにする。

`DefaultPromptBuilder` には統一ストアを必須依存として明示的に渡す。旧2リストから描画する
退避経路は残さない。任意配線やprivate属性の検査で旧経路へ縮退できると、後続で窓の政策を
変えたときに「変えたつもりが効いていない」状態が静かに生まれるためである。

world snapshot は `recent_event_store` 一つだけを保存する。旧
`sliding_window`、`observation_buffer`、`action_result_store` の3 payloadは復元入口で
新形式へ変換してから、通常の厳格なsubsystem網羅検査へ渡す。一部だけ存在する旧形式や、
旧形式と新形式の同居は部分復元を招くため拒否する。保存は新形式だけとし、旧形式を
再生産しない。

## 52. prompt dataset の Being 配線を episodic 記憶から独立させる

prompt dataset の各行は、世界内 player ではなく継続する主体を表す `being_id` を必須と
する。しかし従来は、この ID を解決する補助 Being 配線が episodic 記憶の有効化に
偶然依存していた。そのため記憶を省いた lean profile では、記録を有効にすると設定検証で
拒否され、run 016 / 017 の prompt を後から再生できなかった。

記録機能と記憶機能は別の関心事として扱う。`PROMPT_DATASET_CAPTURE_ENABLED` が有効なら、
episodic 記憶が無効でも `create_world_runtime` の起動中に補助 Being を配線し、全参加者を
provision する。設定上の相互依存は削除し、最初の LLM 呼び出しより前に実際の `being_id`
を解決できない構成は起動時に止める。capture が無効で episodic 記憶も無効なら、従来どおり
この配線は遅延したままとし、公開 tool の集合や世界の振る舞いは変えない。

## 53. semantic top-K は選抜順位と表示順を分ける

`【関連する学び】` の候補は recency、importance、relevance の score で top-K を
選ぶ。recency は描画時刻で変わるため、同じ集合でも候補の順位だけが入れ替わり、
プロンプト本文が変わっていた。見出しは関連度順を約束しておらず、表示順位を
エージェントへ伝える意味もない。

選抜は従来どおり score 順で行い、表示だけを `entry_id` 順へ固定する。同じ集合なら
時間が進んでも同じ文字列になり、集合が変われば本文も変わる。score 順を失うのではなく、
選抜と描画へ別々の責務を持たせる判断である。

`stable_to_volatile` では、実測で 36〜62% 変化する semantic top-K を L4 より上へ
置かない。安定した L4 と直近出来事の先頭を先に置き、予測の後ろで
`【関連する学び】`、`【関連する記憶】`、その本文に内包される想起見出しをまとめる。
直近の出来事が想起を引き起こすという読み順にも合う。`legacy` は A/B 比較用の旧順序
そのものに価値があるため変更しない。この変更は原則との不整合と順位の揺れを直すが、
キャッシュ改善量は実測前に主張しない。

## 54. 直近の出来事は自分のターンを単位に、まとめて畳む

観測と行動結果を一つのストアへ統一しても、観測15件と行動20件という旧来の別々な
表示政策を残すと、流入の多い観測のほうが先に消え、自分の行動だけが長く残る。
出来事の種類を一方だけ数えて窓を決めず、前回の自分のターン完了から今回の完了までを
一つの bucket とし、直近 N bucket を同じ時系列で保持する。

境界は episodic 再解釈の内側ではなく、直列・並列の両方が通る LLM wave の決算地点に
置く。reason-first の複数回の評価と行動は一つの判断なので1ターン、自己再スケジュールで
別 wave に進めば別ターンとする。短期記憶の全実装が `complete_turn` を必須実装するため、
lean profile や新しい実装で通知が黙って消える任意配線は作らない。

窓は毎ターン最古を落とすスライド方式にしない。既定では cap 20ターンまで追記し、到達時に
古い10ターンをまとめてL4へ畳み、残る10ターンから再び積む。これにより先頭が変わるのは
10ターンに一度となり、畳んだ直後も窓が空にならない。cap と畳む数は profile で変更できるが、
`0 < 畳む数 < cap` を起動時に強制する。

この段階のL4入力は従来どおり観測だけとし、行動を含める変更は別に測る。ターン bucket の
見出しも prompt へ出さず、表示は従来の一つの時系列を保つ。この判断が保証するのは窓の
単位と先頭の安定性であり、プレフィックスキャッシュの改善量は実 run の前に主張しない。

## 55. L4 へ観測と自分の行動を一つの時系列で渡す

観測だけを L4 入力にすると、自分の行動はターン窓から外れた時点で短期記憶から消え、
中期記憶には周囲の出来事から推測した行動しか残らない。観測を受けて行動した因果を保つ
ため、畳んだターン群の `UnifiedRecentEventEntry` を種類で分けず、`occurred_at` 順の
一つの時系列として L4 生成へ渡す。

入力行は【直近の出来事】と同じ描画規則を使う。これにより、エージェントが読んだ出来事と
要約器が読んだ出来事を同じ表記で比較でき、行動には `[行動]` の区別も残る。見出しには
畳んだターン数と出来事数を併記し、観測だけ・行動だけのターンも同じ入口で扱う。

この段階では L4 の system prompt と出力形式を変えない。何を優先して残すかは入力を実際に
通した結果を見てから別に決める。LLM 失敗時の template fallback も通常入力と同じ統一時系列
を使い、失敗したときだけ行動が消える差を作らない。L5 は引き続き退避された L4 一件だけを
入力とする。

## 56. 行動履歴の tool 引数は引数名で分類して構造化保存する

行動の自然文表示は意味を読み返すためのもので、tool に渡した値を復元する材料ではない。
表示名と正規名が異なる interaction では、自然文を写したエージェントが
`action_name` の解決に失敗した。特定の tool だけを補修すると同じ問題が別の引数で
再発するため、JSON Schema の property 名を単位に扱いを分類する。

完全一致が必要な名前・列挙値・構造化値は `identifier_arguments` に文字列として保存し、
配列内部の名前も引用符を含む正規 JSON のまま保つ。自由文は履歴を重複して肥大化させず、
呼び出し形を示せるよう `free_text_argument_names` に引数名だけを残す。
`inner_thought` と `expected_result` は直後の専用行に既に出るため省略する。分類は tool 名で
分岐せず、同名の引数には同じ規則を適用する。

露出可能な tool catalog の全 property は起動時に分類漏れを検査する。検査は実行器の
配線確認とは分離し、分類忘れと別の構成不備を同じ失敗へ潰さない。成功した core action と
generic な失敗経路の両方が同じ射影関数を通り、snapshot は構造化した値を保存する。旧 payload
には存在しないため空へ倒し、復元できない引数を捏造しない。この段階では記録だけを変え、
プロンプトへの表示は別 PR で扱う。

## 57. 行動履歴は意味の表示と再利用できる呼び出しを併記する

行動の自然文は物語として読み返せる表示名を優先する。一方、表示名は tool の正規引数とは
限らず、引用符で囲むと「そのまま引数へ写せる値」という prompt の規約に反する。
自然文を内部名だけの機械的な表記へ戻さず、全行動の直後に `呼び出し:` の続き行を置いて
二つの目的を分ける。

完全一致が必要な文字列は JSON の引用符で囲み、配列内の文字列も引用符を保つ。自由文は
値を再掲せず、`content=本文` のように引用符なしの日本語プレースホルダで書く。
`inner_thought` と `expected_result` は既存の専用行を使い、呼び出しには重複させない。
成功した行動は引数が無くても `listen()` のように必ず表示し、行動ごとに省略規則を
推測させない。失敗した行動は例外とし、通らなかった値を引用符つきの手本として
残さない。失敗行には `[失敗]`、`error_code`、復帰文が並ぶため、省略理由はその場で
読める。

続き行は既存の行動エントリと一緒に一度だけ描画し、別 section や描画時刻への依存を
増やさない。後続 entry の追記で既存行は変わらず、ターン窓の先頭安定性を保つ。
自然文側では対象名の引用符だけを残し、tool へ渡せない interaction の表示名からは
引用符を外す。

tool の静的な説明や失敗後の復帰文に、シナリオに存在するとは限らない
`action_name` の具体例は書かない。run 018 では静的に例示した名前をモデルが写し、
実際には宣言されていない操作を繰り返した。使える名前の真実の出所は毎回の
「現在の状況」の対象行だけとし、静的文面はそこの引用値をそのまま写す規則だけを伝える。

## 58. 個別 outcome を world snapshot の独立 subsystem として保存する

`PlayerOutcomeRegistry` の `DEAD` / `EJECTED` / `RESCUED` / `STRANDED` は、
勝敗上の確定状態である。身体の可動状態を表す `is_down` や、graph の配置からは
正しく復元できない。`is_down=True` は死亡確定前の蘇生可能な状態でもあり、
未配置は追放だけでなく初期未配置でもあり得るためである。

個別 outcome は `player_vitals` へ混ぜず、`player_outcome` world subsystem として
独立保存する。復元は `set_outcome` を再実行せず、player 集合を検証した後に
callback 無しで registry 全体を置換する。再開時に過去の死亡・追放を新しい観測や
trace として再通知しないためである。

この subsystem より前の world snapshot には outcome を推定する情報が無い。
分からない値を `UNRESOLVED` として補うと、死者や追放者が勝敗・投票母数へ戻った
壊れた世界で実験を続けてしまう。そのため完全な再開形式の top-level
`schema_version` を 3 に上げ、旧版の strict restore は理由を示して開始前に拒否する。
通常の非 strict 読み込みは調査・互換用途として旧版を引き続き受理するが、実験再開
には使わない。

## 59. world flag は状態の反復ではなく変化を因果つきで記録する

作業完了などの `SET_FLAG` は観測を生まない場合があり、最終状態や登場人物の発言だけ
では、どの行動で何が進んだかを実験後に確かめられない。flag を変更する各サービスで
個別に trace を書くと、新しい変更経路を足したときに観測だけを忘れる。そのため
`MutableWorldFlagState` を単一の絞り点とし、変更前後の集合差分を flag ごとの
`world_flag_changed` として通知する。

変更経路と行為者は状態だけから復元できないため、`add` / `remove` /
`replace_from_interaction` は `WorldFlagMutationContext` を必須とする。行為者が存在しない
経路でも `None` を明記させ、呼び出し元の渡し忘れを既定値で隠さない。同じ値への再設定は
記録せず、複数 flag が変われば安定した順序で一件ずつ記録する。現在の状態の集計はこの
変化列から分析側で作り、毎 tick 同じ値を重ねて因果を薄めない。

snapshot 復元も同じ状態置換 API を通すが、過去の成立を新しい出来事として再通知しては
ならない。復元側は `snapshot_restore` という変更元を明示し、状態オブジェクトではなく
trace への配線で除外する。これにより差分検出の真実の源を一つに保ちつつ、復元と実行中の
変化を混同しない。

## 60. 生死状態は一つの層へ潰さず、問いごとの query で読む

プレイヤーの生死に関する判断は、手番、世界観測、投票資格、通報できる身体で意味が
異なる。`is_down` と `PlayerOutcomeEnum` を各入口で別々に読むと、新しい状態を足した
とき一部だけが古い規則を使い続ける。一方、すべてを「活動中か」という一つの真偽値へ
潰すと、現在でも意図して異なる答えを返している状態を壊す。

そのため `PlayerLifeQuery` に問いを分け、各公開入口は同じ instance を共有する。
`can_take_turn` は確定済み outcome 全般と `status.can_act()` を見る。
`can_receive_world_observation` と `has_reportable_body` は現在の `is_down` を見る。
`can_vote` は `is_eliminated` と身体の有無を見る。特に `RESCUED` / `STRANDED` は手番を
持たないが投票資格を持つため、`can_take_turn` を投票判定へ流用しない。移動中の手番抑止は
生死の問いではないので、従来どおり手番入口に残す。

追放者は `is_down=False` なので、世界観測の門だけを見れば受信可能である。実際に観測が
届かず身体も通報されないのは、graph から配置が消えて宛先や対象として見つからないためで
ある。この偶然の守りを query の規則として捏造しない。将来、去った主体へ別の位置を与える
ときは、知覚や身体の規則を明示的に変える必要がある。

この整理では活動中、蘇生可能な昏倒、死亡確定、追放、救助、取り残しの六状態について、
query 自体の答えと実際の公開入口を同時に固定する。query の単体試験だけでは、正しく作った
判定が本番配線から呼ばれない欠陥を検出できないためである。この段階では層の概念や幽霊の
手番を導入せず、既存の振る舞いを変えない。

## 61. 終局結果の世界固有文はシナリオが宣言する

`DEAD` / `EJECTED` / `RESCUED` / `STRANDED` は世界を跨いで使う結果であり、汎用ランタイム
の語彙である。一方、「島に取り残された」「宇宙船へ帰還した」のような場所・世界観を含む
通知文はシナリオの表現である。結果の意味と、その世界でどう語るかを同じ層へ置かない。

シナリオ固有の文型は `metadata.player_outcome_messages` に結果名ごとに宣言し、未宣言時は
場所を決めつけない汎用文を使う。文型は `{player_name}` だけを許可し、未知の結果、未知の
置換項目、書式指定、変換指定、人物名を含まない文型は読込時に拒否する。実行時に不正な
文型を握りつぶしたり、別世界の既定文へ縮退させたりしない。

文の整形は application の小さなサービスへ置き、`WorldRuntime` は読込済みの表示方針を
渡して結果文を受け取るだけにする。通知範囲、構造化観測、起床指定は表示文とは別の判断
なので、文型の差し替えに連動させない。新しい舞台で既存 outcome を使うとき、世界固有の
名詞を汎用ランタイムへ条件分岐として追加しない。

## 62. 確率条件の乱数位置は世界状態として保存する

`PROBABILITY` 条件は scenario event、reactive binding、player outcome rule が
一つの乱数源を共有し、条件木の短絡順に値を消費する。seed だけを設定へ残しても、
snapshot 再開時に乱数列の先頭へ戻るため、連続実行とは異なる出来事が発火する。
したがって完全な world snapshot は seed ではなく `random.Random.getstate()` が
表す現在位置を独立 subsystem として保存する。

乱数源は特定の評価器の非公開属性ではなく `WorldRuntime` が所有し、評価器には同じ
実体を注入する。復元時も新しい乱数源へ差し替えず、既に各 stage が参照している実体に
`setstate()` する。これにより条件評価器を共通基盤へ置き換えても、保存形式と所有境界を
維持できる。

内部状態は pickle ではなく、版、整数列、ガウス分布用キャッシュを明示した JSON として
保存する。復元値は別の実体で完全に検証してから本番の乱数源へ適用し、壊れた入力で
稼働中の位置を半端に変えない。この状態を欠く旧 world snapshot は確率的な因果を再現
できないため、完全な再開形式を top-level `schema_version=6` とし、旧版の strict restore
は開始前に理由つきで拒否する。
