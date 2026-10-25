# 設計判断 / 設計思想集

設計判断の本文は [design_decisions/](design_decisions/) に、1件1ファイルで保存する。
実装前に関係する判断と [エージェント設計原則](agent_design_principles.md) を読む。

## 判断を追加・更新する

- 新しい判断は `docs/design_decisions/D<issue番号>.md` に作る。同じIssueで2件目以降なら `D<issue番号>-2.md`、`D<issue番号>-3.md` とする。
- 同じIssueで並行して書く場合は、枝番号を担当ごとにあらかじめ割り当てる。
- 見出しは `## D1448. 判断の題名` の形にし、ファイル名とIDを一致させる。既存の1〜238の番号と本文は維持する。
- 「何を」「なぜ」「どうしないと壊れるか」を書き、関連するIssue・PRを添える。取り消した判断も削除せず、理由を追記する。
- 参照は個別ファイルへのリンクを使う。文章でIDを書く場合は `design_decisions D1448` とし、GitHubのIssueへ飛ぶ `#1448` と混同しない。
- **新規追加では、この索引へ追記しない。** 個別ファイルの追加だけで完了する。全件は [フォルダー](design_decisions/) から探せる。
- 下の一覧は移行済みの判断への互換入口。既存のこのファイルへのリンクや見出しへのリンクも引き続き使える。

## 1. Prefix cache を守るため、system prompt と tool list は tick 間で不変にする

[本文](design_decisions/1.md)

## 2. 致命的に詰む状態を作らない (例: 疲労 100 でも use_item は通す)

[本文](design_decisions/2.md)

## 3. 揮発ラベル (S1 / I2 / P3) を捨て、名前 + ordinal で対象指定する

[本文](design_decisions/3.md)

## 4. travel / wait は「ツール内で tick を進めない」モデルにする

[本文](design_decisions/4.md)

## 5. silent failure を「構造」で塞ぐ (例外ハンドリングだけに頼らない)

[本文](design_decisions/5.md)

## 6. 後方互換を過度に守らない

[本文](design_decisions/6.md)

## 7. heartbeat は「最低発火頻度の floor」ではなく「最大沈黙時間の ceiling」

[本文](design_decisions/7.md)

## 8. 状態依存の表示は「プレイヤー状態セクション」に出す

[本文](design_decisions/8.md)

## 10. 実験 env の不正値は silent fallback せず fail-fast

[本文](design_decisions/10.md)

## 11. 設定は単一 DTO で集約、構築は「全部揃ってから 1 回 build」

[本文](design_decisions/11.md)

## 12. Future work は xfail-strict pytest で可視化する

[本文](design_decisions/12.md)

## 13. memory caller の Being 未解決時挙動は「役割」で分岐する

[本文](design_decisions/13.md)

## 14. promotion_frontier は Phase 3 Step 3c の scope 外 (= player_id keyed のまま)

[本文](design_decisions/14.md)

## 15. BeingSnapshot v2 は memory payload を「オペーク JSON」として持つ

[本文](design_decisions/15.md)

## 21. world snapshot は scenario 一致を hard-error で要求する (= cross-scenario load は不可)

[本文](design_decisions/21.md)

## 23. monster / quest codec は Phase 9-5 では未実装 (= 実需要待ち)

[本文](design_decisions/23.md)

## 22. world snapshot は subsystem ごとに codec を持ち、登録外は forward-compat で skip

[本文](design_decisions/22.md)

## 20. snapshot の schema 進化は (a) 厳格モード — 未サポート version は load 失敗

[本文](design_decisions/20.md)

## 19. snapshot ファイルは scenario 名メタデータを持ち、別シナリオ転送は warning だけで許容する

[本文](design_decisions/19.md)

## 17. experiment runner の snapshot は escape_game runtime の限定 store だけを拾う

[本文](design_decisions/17.md)

## 18. snapshot save は SIGINT を flag 化して run 終了経路に合流させる

[本文](design_decisions/18.md)

## 16. run 途中再開 CLI は 4 SQLite DB + in-memory memo の構成で動く

[本文](design_decisions/16.md)

## 9. 速度より「LLM の判断ミス」を優先して直す

[本文](design_decisions/9.md)

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

[本文](design_decisions/24.md)

## 25. application 層の circular import は test 側で warm-up import で回避 (= 既知債務)

[本文](design_decisions/25.md)

## 26. 勝敗は runtime でなくシナリオ専管 → game_end_conditions を書かなければ「永続世界」になる

[本文](design_decisions/26.md)

## 27. 新しい per-Being store は snapshot に乗せる前提で実装する (4 step checklist)

[本文](design_decisions/27.md)

## 28. 実験に意味を持つ設定は profile/config だけから入れる

[本文](design_decisions/28.md)

## 29. 再開境界で未通知観測を勝手に flush しない

[本文](design_decisions/29.md)

## 30. ローカルLLMはレプリカ単位で常駐管理し、実験を同じレプリカへ固定する

[本文](design_decisions/30.md)

## 31. テレポートの秘匿性は visibility ではなく「誰が居たか」で決まる

[本文](design_decisions/31.md)

## 32. 環境変化 (CHANGE_ATMOSPHERE) は部分更新にする

[本文](design_decisions/32.md)

## 33. 能動想起ツールは測定条件が整うまで profile 側で OFF にする

[本文](design_decisions/33.md)

## 34. memo A/B は「蒸留ありの手帳」と「手帳なし」を比較する

[本文](design_decisions/34.md)

## 35. `is_outdoor` 未宣言の屋内扱いは validator で見える化する

[本文](design_decisions/35.md)

## 36. object.state の prompt 表示は scenario 側で宣言し、未宣言値は隠さない

[本文](design_decisions/36.md)

## 37. いまできない object action は候補から消さず、選べる行動とは別行に出す

[本文](design_decisions/37.md)

## 38. action_name は意味ラベルで補い、多義語は動詞 + 目的語へ寄せる

[本文](design_decisions/38.md)

## 39. 実験モデルは版固定 ID を使い、接続先の能力は実呼び出しで確かめる

[本文](design_decisions/39.md)

## 40. `CALL_MEETING.trigger` は宣言値を実行まで運び、未知値へ縮退しない

[本文](design_decisions/40.md)

## 41. 差し替え口の単体試験だけでなく、本物の接続を通す

[本文](design_decisions/41.md)

## 42. モンスター固有の攻撃能力はテンプレート宣言を単一の出所にする

[本文](design_decisions/42.md)

## 43. 個人結果・終了・生存圧を別々の宣言にし、旧一体型経路を残さない

[本文](design_decisions/43.md)

## 44. ツール露出は世界・フェーズ・本人状態を公開入口で合成する

[本文](design_decisions/44.md)

## 45. scenario event の世界文脈条件は既存の語義と状態の出所を再利用する

[本文](design_decisions/45.md)

## 46. 物体の存在・操作の公開・視認性を同じ空集合へ潰さない

[本文](design_decisions/46.md)

## 47. 提示後の状況変化と一覧外の選択を同じ失敗へ潰さない

[本文](design_decisions/47.md)

## 48. 襲撃の可否と目撃可能性を分け、派生 action は待ち時間を共有する

[本文](design_decisions/48.md)

## 49. tool にそのまま渡せる文字列だけを引用符で囲む

[本文](design_decisions/49.md)

## 50. 直近の出来事の時刻は記録時の世界内絶対時刻で固定する

[本文](design_decisions/50.md)

## 51. 観測と行動結果は記録時から一つの時系列へ置く

[本文](design_decisions/51.md)

## 52. prompt dataset の Being 配線を episodic 記憶から独立させる

[本文](design_decisions/52.md)

## 53. semantic top-K は選抜順位と表示順を分ける

[本文](design_decisions/53.md)

## 54. 直近の出来事は自分のターンを単位に、まとめて畳む

[本文](design_decisions/54.md)

## 55. L4 へ観測と自分の行動を一つの時系列で渡す

[本文](design_decisions/55.md)

## 56. 行動履歴の tool 引数は引数名で分類して構造化保存する

[本文](design_decisions/56.md)

## 57. 行動履歴は意味の表示と再利用できる呼び出しを併記する

[本文](design_decisions/57.md)

## 58. 個別 outcome を world snapshot の独立 subsystem として保存する

[本文](design_decisions/58.md)

## 59. world flag は状態の反復ではなく変化を因果つきで記録する

[本文](design_decisions/59.md)

## 60. 生死状態は一つの層へ潰さず、問いごとの query で読む

[本文](design_decisions/60.md)

## 61. 終局結果の世界固有文はシナリオが宣言する

[本文](design_decisions/61.md)

## 62. 確率条件の乱数位置は世界状態として保存する

[本文](design_decisions/62.md)

## 63. 述語評価は真偽値の互換入口より内側で理由を保持する

[本文](design_decisions/63.md)

## 64. 判定に文字列を使わない。値を持っているなら値を渡す

[本文](design_decisions/64.md)

## 65. enum で分岐するなら表にする。2 分岐は静かに嘘をつく

[本文](design_decisions/65.md)

## 66. 内部 ID をプロンプトへ出さない。露出は総当たりで見張る

[本文](design_decisions/66.md)

## 67. 想定外例外の発生位置は引数で受け、呼び方を AST で縛る

[本文](design_decisions/67.md)

## 68. 宣言したのに効かない形は、読み込み時か corpus 監査で落とす

[本文](design_decisions/68.md)

## 69. 呼び名の所有者は「値の集合を誰が決めるか」で分ける

[本文](design_decisions/69.md)

## 70. シナリオ述語の trace は実際の根評価を一度だけ記録する

[本文](design_decisions/70.md)

## 71. 共通述語は意味が同じ葉から移し、用途固有の出口は残す

[本文](design_decisions/71.md)

## 72. tick比較は同じ時間軸と境界を持つ用途だけ共通化する

[本文](design_decisions/72.md)

## 76. SQLiteのシナリオ宣言は全フィールドを同じschemaで往復させる

[本文](design_decisions/76.md)

## 77. 通知と効果経路を追加したSQLite宣言は新しいschemaを発行する

[本文](design_decisions/77.md)

## 73. 場所条件は対象範囲を用途側で選び、共通核では型を分ける

[本文](design_decisions/73.md)

## 74. 同期操作の準備は通常操作の可否と異なる参加者を要求する

[本文](design_decisions/74.md)

## 75. 数量を持たない所持条件は解決済み品目集合への所属として共通化する

[本文](design_decisions/75.md)

## 79. state完全一致は対象の選択と分離して共通化する

[本文](design_decisions/79.md)

## 78. 罠定義と屋外属性をSQLite再開後も保持する

[本文](design_decisions/78.md)

## 136. 複数陣営では固定人数でなく現在の生存人数を比較する

[本文](design_decisions/136.md)

## 137. 役職の相互開示はシナリオが宣言し、役職語彙は表示層へ渡さない

[本文](design_decisions/137.md)

## 80. 数量付き所持条件は解決済み品目別個数の比較として共通化する

[本文](design_decisions/80.md)

## 81. 整数state下限は対象解決と分離して共通化する

[本文](design_decisions/81.md)

## 82. 遠隔道具の明示対象は世界全体から解決し、解決不能を成功扱いしない

[本文](design_decisions/82.md)

## 83. scenarioの列挙値は実行時の不成立へ縮退させず読込時に拒否する

[本文](design_decisions/83.md)

## 84. 天候条件は正の一致だけを共通化し、否定と失敗文は用途側に残す

[本文](design_decisions/84.md)

## 86. 共通述語基盤は決定的な葉と用途表を完成境界とする

[本文](design_decisions/86.md)

## 85. 同時性はフェーズの意味に合わせ、比較 run に必要な量を trace へ残す

[本文](design_decisions/85.md)

## 87. 長走比較では短期記憶だけを要約し、補助 JSON 呼び出しは熟考しない

[本文](design_decisions/87.md)

## 88. REMOVE_ITEMは予約されていない具体instanceを全量確保してから消費する

[本文](design_decisions/88.md)

## 89. 時間制限つき妨害は発動・警報・協力解除・締切を別の宣言で持つ

[本文](design_decisions/89.md)

## 90. 在室数は用途別の範囲を明示し、動的表示はアプリケーション層で解く

[本文](design_decisions/90.md)

## 91. OpenRouter の会話固定 ID は run・世界・player から作り、本文へ混ぜない

[本文](design_decisions/91.md)

## 92. 再発動する時限事象は状態を解除し、経過時刻の窓で各周期を識別する

[本文](design_decisions/92.md)

## 93. persona の役職知識は世界の事実に限り、立ち回りを代行しない

[本文](design_decisions/93.md)

## 94. 人物固有文と役職共通知識を分離し、固定順で system prompt へ連結する

[本文](design_decisions/94.md)

## 95. tools payload は状態不変の常在ブロックを先頭へ固定する

[本文](design_decisions/95.md)

## 96. 熟考と required が両立しない provider は tool_choice を実験条件として切り替える

[本文](design_decisions/96.md)

## 97. 待ち時間の共有単位は役職ではなく interaction が宣言する

[本文](design_decisions/97.md)

## 98. 操作名の救済案内は候補表示と同じ露出集合から作る

[本文](design_decisions/98.md)

## 99. 進行中の異常はシナリオが宣言し、追記式の出来事より後ろへ表示する

[本文](design_decisions/99.md)

## 100. 会議による異常解除は明示効果で宣言し、遷移成功後だけ適用する

[本文](design_decisions/100.md)

## 101. 緊急招集を塞ぐ異常は全項目が明示し、遺体報告とは入口を分ける

[本文](design_decisions/101.md)

## 102. 道具の妨害間隔は品目内の共有名と世界共有を直交させる

[本文](design_decisions/102.md)

## 103. 配信先固定は既定を保ったまま実験設定で送信自体を外せるようにする

[本文](design_decisions/103.md)

## 104. 売買ツールは商人の宣言でゲートし、負の宣言と対にする

[本文](design_decisions/104.md)

## 105. 場所の失敗と品の失敗を同じ error_code へ畳まない

[本文](design_decisions/105.md)

## 106. 金銭が動くツールは部分成功を作らない

[本文](design_decisions/106.md)

## 107. 曖昧な対象は engine が代わりに選ばない

[本文](design_decisions/107.md)

## 108. 宣言だけ先に入れる PR は、配線で自動失効する猶予リストで通す

[本文](design_decisions/108.md)

## 109. 基盤障害は時間を失った事実だけを世界内の記憶へ残す

[本文](design_decisions/109.md)

## 138. 出来事の同一性を、prompt の見た目に依存させない

[本文](design_decisions/138.md)

## 110. 招集の判断材料には集合後の経過だけを末尾で渡す

[本文](design_decisions/110.md)

## 111. CI は固定した依存で振る舞いを試し、リポジトリ検査を別 job にする

[本文](design_decisions/111.md)

## 112. 商人は世界の外との出入り口で、世界の中に物を溜めない

[本文](design_decisions/112.md)

## 113. 板は自動で約定させない。交差は潰さず機会として残す

[本文](design_decisions/113.md)

## 114. 市場の値は「注文の向き」ではなく「見る人が打てる手」で名づける

[本文](design_decisions/114.md)

## 115. 板に預けたものが返せないときは、消さずに引き取り待ちで残す

[本文](design_decisions/115.md)

## 116. 板の注文は「同じ品目・同じ向きで 1 件まで」を状態の側で守る

[本文](design_decisions/116.md)

## 117. 外部の変化には適応し、自分の誤りには従わない

[本文](design_decisions/117.md)

## 118. 同じ量が動くなら、どのツールから動いても同じ形で記録する

[本文](design_decisions/118.md)

## 119. 食料腐敗の進行ルールは Item 集約に置く

[本文](design_decisions/119.md)

## 120. 腐敗食の消費数値は Item ドメインで計算する

[本文](design_decisions/120.md)

## 121. 世界の厳しさは宣言で決める。既定は据え置く

[本文](design_decisions/121.md)

## 122. 疲労の行為コストと限界時ブロックはドメイン政策に置く

[本文](design_decisions/122.md)

## 123. 欲求 tick の増加と限界ダメージは PlayerStatus が持つ

[本文](design_decisions/123.md)

## 139. 読めなかった値を、既定値として黙って返さない

[本文](design_decisions/139.md)

## 140. 期限を宣言したら、期限が来る経路まで繋ぐ

[本文](design_decisions/140.md)

## 124. プロンプトのテンプレートに、特定の世界の固有名詞を書かない

[本文](design_decisions/124.md)

## 125. 発話ぼかしの発火は is_severely_fatigued が決める

[本文](design_decisions/125.md)

## 141. できないことは、できない理由の粒度で見せる

[本文](design_decisions/141.md)

## 126. 言葉が自然に書ける形を、世界の側が受け取れるようにする

[本文](design_decisions/126.md)

## 127. 申告は真実ではなく期待として使い、実測と照合する

[本文](design_decisions/127.md)

## 128. 相手が居ないことを、自分が動けないことと書かない

[本文](design_decisions/128.md)

## 129. 失敗文は「何が駄目か」だけでなく「次にどこへ行けばよいか」を言う

[本文](design_decisions/129.md)

## 130. 遠さの段階は、それぞれ違うものを届ける

[本文](design_decisions/130.md)

## 131. 同じ身体に付く Being の一意性は、取り出した列に対する判定である

[本文](design_decisions/131.md)

## 142. 観戦用の所持品一覧は application 照会が公開走査を使う

[本文](design_decisions/142.md)

## 132. 記憶ツールの BeingId は手番入口で一度だけ決める

[本文](design_decisions/132.md)

## 133. プロンプト組み立ての BeingId は手番入口で一度だけ決める

[本文](design_decisions/133.md)

## 134. 受動想起と chunk は呼び出し側の BeingId を使う

[本文](design_decisions/134.md)

## 135. 応答として書かれた文を、常時出る注記に流用しない

[本文](design_decisions/135.md)

## 143. 値の呼び名は、全部に付けるか 1 つも付けないか

[本文](design_decisions/143.md)

## 144. memo 完了 hint は呼び出し側の BeingId を使う

[本文](design_decisions/144.md)

## 145. 信念固着と再解釈は呼び出し側の BeingId を使う

[本文](design_decisions/145.md)

## 146. 記憶リンクとクラスタ昇格は呼び出し側の BeingId を使う

[本文](design_decisions/146.md)

## 147. Unit of Workは永続化に絞り、CommandScopeがcommand完了を統括する

[本文](design_decisions/147.md)

## 148. 新CommandScopeはtransaction状態機械だけを本番配線の外で先に固める

[本文](design_decisions/148.md)

## 149. 同期イベントはCommandContextへ戻し、commit後handoffは元scopeの外で開始する

[本文](design_decisions/149.md)

## 150. 既存Unit of Workの自動rollbackをtransaction専用commitから分離する

[本文](design_decisions/150.md)

## 151. scope専用repositoryはtransaction開始後にproviderから一度だけ生成する

[本文](design_decisions/151.md)

## 152. application commandはscope factoryだけを保持してrepositoryを操作中に取得する

[本文](design_decisions/152.md)

## 153. CommandScopeのイベント処理はcommit前必須処理とcommit後配送の二相に限定する

[本文](design_decisions/153.md)

## 154. scope参加repositoryの集約イベントはCommandContextだけへ移す

[本文](design_decisions/154.md)

## 155. 再送必須イベントは業務状態と同じtransactionでoutboxへ保存する

[本文](design_decisions/155.md)

## 156. outbox workerは登録順に1件ずつ再配送する

[本文](design_decisions/156.md)

## 157. read model投影はconsumer inboxと同じtransactionで確定する

[本文](design_decisions/157.md)

## 158. outbox再配送はprocessの生存期間に属する有界loopで駆動する

[本文](design_decisions/158.md)

## 159. outbox一時失敗は順序を保ったまま間隔を広げ、上限で隔離する

[本文](design_decisions/159.md)

## 160. 更新commandの横展開は実利用される複数集約操作を一つずつ移す

[本文](design_decisions/160.md)

## 161. drop/pickupは所持品とSpotInteriorを同じtransactionで確定する

[本文](design_decisions/161.md)

## 162. repository外の世界内可変状態も同じcommandのrollbackへ参加させる

[本文](design_decisions/162.md)

## 163. interactionの外部状態と通知を同じ確定境界へ参加させる

[本文](design_decisions/163.md)

## 164. 通常の物体interactionはrepositoryと外部状態を一つのcommandで確定する

[本文](design_decisions/164.md)

## 165. 道具に宣言したinteractionも物体操作と同じcommandで確定する

[本文](design_decisions/165.md)

## 166. 対人interactionは二者の状態と観測を一つのcommandで確定する

[本文](design_decisions/166.md)

## 167. 会議開始は通常interactionから独立したcommandとして扱う

[本文](design_decisions/167.md)

## 168. 会議開始の状態と観測を一つのcommandで確定する

[本文](design_decisions/168.md)

## 169. 投票・追放・会議終了を一つのcommandで確定する

[本文](design_decisions/169.md)

## 170. SpotGraph移動は1 player・1操作ごとに確定する

[本文](design_decisions/170.md)

## 171. world tickは順序だけを所有し、確定はstageまたはcommandへ分ける

[本文](design_decisions/171.md)

## 172. needs decayはplayer status確定後にevidenceへ転記する

[本文](design_decisions/172.md)

## 173. scenario eventはevent定義1件ごとに世界状態と進捗を確定する

[本文](design_decisions/173.md)

## 174. 主観エピソードに経験の主体 BeingId を載せる

[本文](design_decisions/174.md)

## 175. 昇格フロンティアは BeingId で分ける

[本文](design_decisions/175.md)

## 176. エピソードがある経路では BeingId を VO から読む

[本文](design_decisions/176.md)

## 177. 記憶リンクに経験の主体 BeingId を載せる

[本文](design_decisions/177.md)

## 178. monster spawnはslot 1件ごとに確定する

[本文](design_decisions/178.md)

## 179. monster behaviorはmonster 1体ごとに確定する

[本文](design_decisions/179.md)

## 180. reactive objectはbindingごと、passageはstage全体で確定する

[本文](design_decisions/180.md)

## 181. synchronized actionはgroupごとに確定する

[本文](design_decisions/181.md)

## 182. 天候と昼夜は遷移ごとに独立して確定する

[本文](design_decisions/182.md)

## 183. 食料劣化は全対象itemをstage単位で確定する

[本文](design_decisions/183.md)

## 184. 期限切れ取引提案はoffer一件単位で予約解除と一緒に確定する

[本文](design_decisions/184.md)

## 185. 期限切れ市場注文はorder一件単位で預り資産と一緒に確定する

[本文](design_decisions/185.md)

## 186. プレイヤー結果規則は発火rule単位で全対象と進捗を確定する

[本文](design_decisions/186.md)

## 187. 死亡猶予の期限到達はplayer単位で結果・timer・退場位置を確定する

[本文](design_decisions/187.md)

## 188. 探索は発見回数・室内・付与品・観測を一度に確定する

[本文](design_decisions/188.md)

## 189. 同席取引は提案・承諾・辞退をそれぞれ一度に確定する

[本文](design_decisions/189.md)

## 190. NPC商人との売買は支払・品物・観測を一度に確定する

[本文](design_decisions/190.md)

## 191. 市場注文の預託・値付け・返却は操作ごとに確定する

[本文](design_decisions/191.md)

## 192. 一回の市場操作が生む複数約定はまとめて確定する

[本文](design_decisions/192.md)

## 193. アイテム消費と消費効果は同じ確定区間で適用する

[本文](design_decisions/193.md)

## 194. 介抱による復活と復活イベントは同じ確定区間へ載せる

[本文](design_decisions/194.md)

## 195. 協力行動の二種類の準備記録は一緒に確定する

[本文](design_decisions/195.md)

## 196. ダウン・蘇生は身体と死亡猶予まで一度に確定する

[本文](design_decisions/196.md)

## 197. 旧確定経路は許可表を縮めながら撤去する

[本文](design_decisions/197.md)

## 198. player statusのtick stageはscope未配線を拒否する

[本文](design_decisions/198.md)

## 199. 食料劣化の公開入口はscopeと集約eventだけを使う

[本文](design_decisions/199.md)

## 200. 取引提案期限切れの公開入口はscope由来storeだけを使う

[本文](design_decisions/200.md)

## 201. 天候・昼夜の公開入口はscopeと確定後eventだけを使う

[本文](design_decisions/201.md)

## 202. reactive objectと同期行動の公開入口はscopeだけを使う

[本文](design_decisions/202.md)

## 203. monster behaviorの公開tickはscopeを必須とする

[本文](design_decisions/203.md)

## 204. 取引系の公開更新入口はscope未配線を拒否する

[本文](design_decisions/204.md)

## 205. interactionの公開更新入口はscope未配線を拒否する

[本文](design_decisions/205.md)

## 206. #1244完了後は任意の確定区間fallbackを認めない

[本文](design_decisions/206.md)

## 207. gold を減らす効果は、前提条件とのペアを読み込みで強制する

[本文](design_decisions/207.md)

## 208. 意味記憶エントリに経験の主体 BeingId を載せる

[本文](design_decisions/208.md)

## 209. 再解釈エントリに経験の主体 BeingId を載せる

[本文](design_decisions/209.md)

## 210. 履歴には、次に真似しても通る形だけを残す

[本文](design_decisions/210.md)

## 211. wall-time cap は呼び出し元を実際に解放しないと意味がない

[本文](design_decisions/211.md)

## 212. 交換比率が判定に効く世界でないと、値段の話は始まらない

[本文](design_decisions/212.md)

## 213. 世界の刻限はシナリオが持つ。`max_world_ticks` はループの上限でしかない

[本文](design_decisions/213.md)

## 214. 恒久的な LLM 障害は「サーバが名乗る理由」ではなく「治らなさ」で判定する

[本文](design_decisions/214.md)

## 215. 呼び出しの健全さは report の冒頭に出す

[本文](design_decisions/215.md)

## 216. LLM境界ではcommit済み後処理失敗を成功として伝える

[本文](design_decisions/216.md)

## 217. 他者の発言で起こすかは、判断の前に規則で守ってから判断に問う

[本文](design_decisions/217.md)

## 218. 二人で合わせる操作の入口は interact に統合する

[本文](design_decisions/218.md)

## 219. 起こすかは観測 1 件ごとでなく、tick の終わりに本人の未読をまとめて問う

[本文](design_decisions/219.md)

## 220. 起動判定は規則で素通しさせず、pending の全員を Jev に問う

[本文](design_decisions/220.md)

## 221. 起動判定の候補は pending の人ではなく、未読の観測がある人全員

[本文](design_decisions/221.md)

## 222. 起動判定は既定で外し、観察するときだけ入れる

[本文](design_decisions/222.md)

## 223. 行動名の意味による救済を semantic-resolver へ委譲する

[本文](design_decisions/223.md)

## 224. 効かない引数は残さず消し、並び順は契約として試験で固定する

[本文](design_decisions/224.md)

## 225. リポジトリの取得系はドメインの型を返し、実装ごとに変えない

[本文](design_decisions/225.md)

## 226. 値オブジェクトの定義はコードベースに 1 つだけ置く

[本文](design_decisions/226.md)

## 227. 対象の名前も、候補に当たらなければ意味で選び直す

[本文](design_decisions/227.md)

## 228. 在るのに種類が違う名前は「無い」と言わず、種類と使うツールを添えて返す

[本文](design_decisions/228.md)

## 229. 名前で対象を引く全ツールが、同じ 3 段の入口を通る

[本文](design_decisions/229.md)

## 230. 隣接していない既知の場所を行き先に書いたら、「見つからない」ではなく「隣接していない」と返す

[本文](design_decisions/230.md)

## 231. 存在しない tool 名への提案は、そのターンに送った tool から意味で選び、実行はしない

[本文](design_decisions/231.md)

## 232. ループ警告の文面は、繰り返しの理由の見立てで選ぶ。見立てで警告は消さない

[本文](design_decisions/232.md)

## 233. 完全一致で数えられない繰り返しは、直近の行動の窓を Jev に問って足す。件数はコードが持つ

[本文](design_decisions/233.md)

## 234. Jev の閾値は、誤ったときに行動が実行される問いにだけ残す

[本文](design_decisions/234.md)

## 235. 動的引数候補の実験は、モデルへ見せる前から同じ真実源を保存する

[本文](design_decisions/235.md)

## 236. 動的引数候補は世界説明を置き換えず、行動指示の直前で正規化して再提示する

[本文](design_decisions/236.md)

## 237. 信念を作る直前に、形と同じ意味の既存の信念を Jev に 1 回で問う。候補は文だけで絞る

[本文](design_decisions/237.md)

## 238. 目的の達成 hint は、判断が得られないとき規則へ縮退しない。清算できない目的は問わない

[本文](design_decisions/238.md)

## D1439. 予期の状態の変化と、その出来事を、同じ保存の単位で残す

[本文](design_decisions/D1439.md)

## D1463. 環境とエージェントの契約は、欄の段と経路ごとの必須欄を型で表し、本文に無い名前を写さない

[本文](design_decisions/D1463.md)

## D1440. 予期の清算は、ターンの終わりに 1 回だけ問い、保存してから配り、受け取る側に重複を見分けさせる

[本文](design_decisions/D1440.md)

## D1452. 信念と証拠は観測のターン数だけを持ち、状態の変わり方は観測の食い違いから学ぶ

[本文](design_decisions/D1452.md)

## D1441. 予期は環境の tool の引数として一律に書かせ、その手のターンの予期として積む

[本文](design_decisions/D1441.md)

## D1443. 予測の当否の材料は確定した予期だけから積み、受け取る側は受け取り済みの ID を材料と同じ store に持つ

[本文](design_decisions/D1443.md)

## D1484. 予期の根拠は形と同じ呼び出しで 1 件ずつ問い、確定した当否は根拠にだけ返す

[本文](design_decisions/D1484.md)

## D1414. ~~想起は状況の 6 つの欄から、残す欄を選んだマスクごとに引き、結果を混ぜずに持つ~~

[本文](design_decisions/D1414.md)

## D1414-2. 状況の項目は観測の契約に変換してから組み、profile で有効にしたときだけ【関連する学び】を切り替える

[本文](design_decisions/D1414-2.md)

## D1414-3. ~~次のターンの想起で残す欄は、ターンの終わりの清算の呼び出しで毎ターン問い、予期の判定とは分けて読む~~

[本文](design_decisions/D1414-3.md)

## D1414-4. ~~自分の体の状態は、清算の呼び出しで「平常 / 注意 / 危機」の帯に丸め、帯の文を生の本文に足す~~

[本文](design_decisions/D1414-4.md)

## D1414-5. ~~残す欄は、欄を選択肢にした 1 問の確率の上位を固定の件数だけ採り、欄の値を Jev に見せる~~

[本文](design_decisions/D1414-5.md)

## D1414-6. メモ・記憶・状況評価の道具の結果は、環境の観測として写さない

[本文](design_decisions/D1414-6.md)

## D1414-7. 文字の 2 字組は、改行・句読点・空白・記号の区切りをまたいで作らない

[本文](design_decisions/D1414-7.md)

## D1414-8. 想起は状況の全部の項目をつなげた 1 本の問い合わせで引き、上位 3 件を載せる

[本文](design_decisions/D1414-8.md)

## D1498. 信念の絞り込みは文字の 2 字組のままにし、形態素解析の手法は比べた記録だけ残して外す

[本文](design_decisions/D1498.md)

## D1454. 埋め込みの手法は絞り込みの差し替えとして足し、作る部品・ベクトルの索引・縮退を分けて差し替える

[本文](design_decisions/D1454.md)

## D1461. SNSの対象には作成時の不変識別子を保存し、表示参照と分ける

[本文](design_decisions/D1461.md)

## D1460. SNSの作者・親・通知先を、整数だけでなく作成時の対象へ束縛する

[本文](design_decisions/D1460.md)

## D1460-2. 初期のSNS読取は公開だけを、全祖先の権限を確かめて有限件ずつ返す

[本文](design_decisions/D1460-2.md)

## D1459. 公開SNSの投稿・親更新・通知を一つのCommandScopeで確定する

[本文](design_decisions/D1459.md)

## D1459-2. 公開SNSは二つの道具と通常観測に接続し、専用の起動ループを作らない

[本文](design_decisions/D1459-2.md)

## D1509. 外れた予期の材料には、清算に見せた時系列のうち書いてから確定するまでを付け、関係の無い出来事の除き方は信念をまとめる LLM に任せる

[本文](design_decisions/D1509.md)

## D1568. 予期の当否は、決め手が他の人の発言の中身しかないかも同じ呼び出しで問い、そうなら当たりを「まだ分からない」に下げる

[本文](design_decisions/D1568.md)

## D1513. 出来事の条件・操作の前提条件・効果に、種類ごとの許可キーの表を置き、表に無いキーは読み込み時に止める

[本文](design_decisions/D1513.md)

## D1514. 記憶だけを持ち越す回は、実験設定の `snapshot_load_mode: "replay"` で選び、前の回の世界の tick は記憶から外す

[本文](design_decisions/D1514.md)

## D1514-2. 回ごとの役と初期配置は、シナリオの `round_assignment` に枠として書き、シードと回の番号で並べ替える

[本文](design_decisions/D1514-2.md)

## D1514-3. 世界の側の乱数は、用途ごとに、シードと回の番号から作る

[本文](design_decisions/D1514-3.md)

## D1520. 会った相手の記録は Being が持ち、環境の encounter には「この観測はもう出した」の判定だけを残す

[本文](design_decisions/D1520.md)

## D1516. チームの勝敗は `teams[].win` で決め、個人の勝敗は所属チームの勝敗にそろえる。個人結果 (RESCUED など) とは別の軸で残す

[本文](design_decisions/D1516.md)

## D1546. 本人にも見せない属性は `player_attributes` で `hidden` と宣言する。`teams[].member_state` のキーを自動では伏せない

[本文](design_decisions/D1546.md)

## D1531. 名前を伏せても誰かがいると分かる観測は、主体を知らない受け手には届けない

[本文](design_decisions/D1531.md)

## D1557. でたらめに行動するスタブは、エージェントに見えている候補だけから選び、実シナリオの総当たりは CI に入れない

[本文](design_decisions/D1557.md)

## D1559. 移動の途中で区間が閉じたら、例外にせず、その手前で移動を取りやめる

[本文](design_decisions/D1559.md)

## D1558. 世界の tick の 1 体ぶんの例外は、CommandScope の単位で取りやめ、必ず trace と報告に出す

[本文](design_decisions/D1558.md)

## D1558-2. 確定済みの処理に続く後処理の失敗は、取りやめずに trace に残して続ける

[本文](design_decisions/D1558-2.md)

## D1569. 効果や出来事で持ち物から外れた品は、捨てたと言わず品名で伝える。出来事で消えたときの文は品の定義に書く

[本文](design_decisions/D1569.md)

## D1569-2. 前提条件で断られた操作の行も、成功の行と同じく操作の表示名で書く

[本文](design_decisions/D1569-2.md)

## D1569-3. 「行動の総量には限りがある」の行は、シナリオが外せるようにする。既定は従来どおり出す

[本文](design_decisions/D1569-3.md)

## D1581. 名前を知らない相手は見た目で出し、名乗りか、同じ場所で名前を呼ばれるのを聞いたときに名前に切り替える

[本文](design_decisions/D1581.md)

## D1582. 有効な reasoning effort も、OpenRouter の統一の形で `extra_body` に載せる

[本文](design_decisions/D1582.md)

## D1591. 操作が parameters から読むキーは、前提条件のものも効果のものも「が要る」で出す。キーが無いときは番号違いの文を使わず、キーを名指す

[本文](design_decisions/D1591.md)

## D1594. 同じ行動かを比べるとき、行動に添えた発言と、識別値の書き方の揺れを外す

[本文](design_decisions/D1594.md)

## D1596. 「(初めて訪れた)」は、着いてから最初の手番を実行するまでの間だけ付ける

[本文](design_decisions/D1596.md)

## D1595. 呼び出しが失敗した人は次の tick に回し、同じ人の 3 回連続で打ち切る。thinking は出力の上限トークン数で抑える

[本文](design_decisions/D1595.md)

## D1600. 試して学ぶ決まりは、外れ方を足りないものごとに分け、満ちた瞬間を音で知らせる。答えは書かない

[本文](design_decisions/D1600.md)

## D1602. 伝聞から来た信念は、支持の内訳から【関連する学び】に印を付ける。推測の言い方を残すことは指示で頼み、作る前の判定は変えない

[本文](design_decisions/D1602.md)

## D1601. 行動に添えた発言は、行動の結果を問わず dispatch で 1 回出す

[本文](design_decisions/D1601.md)

## D1607. 引数が渡されずに断られた操作は、同じ場所の他の人に失敗として見せない

[本文](design_decisions/D1607.md)

## D1613. 体の届く範囲の前提条件は、試して学ぶ決まりの前提条件より先に確かめる

[本文](design_decisions/D1613.md)

## D1618. 個人結果の規則は、世界の段の中と全員の手番のあとの 2 回判定する

[本文](design_decisions/D1618.md)

## D1616. システムプロンプトの記憶の指示は、組み上がった runtime が実際に出す欄とツールから書き分ける

[本文](design_decisions/D1616.md)

## D1623. 目次つきのエピソードは、ゲームから切り離した別の型で持ち、呼び名は重なったときに新しい側だけを伸ばす

[本文](design_decisions/D1623.md)

## D1626. エピソードは短期記憶を畳むときと環境を離れるときに、要約とは別の呼び出しで本人が書き起こす

[本文](design_decisions/D1626.md)

## D1623-2. エピソードの目次は空でも【思い出せる出来事】として毎ターン出し、呼び名で本文を呼び出す

[本文](design_decisions/D1623-2.md)

## D1623-3. 目次は本人が専用のツールで直し、目次を出す設定ではメモの出どころにエピソードを選ばせる

[本文](design_decisions/D1623-3.md)

## D1628. メモは Being ごとのメモ帳を集約の根にし、分類ごとの件数の上限をメモ帳が守る

[本文](design_decisions/D1628.md)

## D1628-2. メモは環境の tool の省略できる引数 `memo` で書き、崩れた操作だけを外して本人に理由を返す

[本文](design_decisions/D1628-2.md)

## D1597. 成功した自分の行動のあとは次の tick に手番を回す。休むのは wait を選んだときと移動中だけ

[本文](design_decisions/D1597.md)

## D1617. 記憶の部品と Jev の LLM 呼び出しは、行動の `llm_call` と分けて `aux_llm_call` に部品名つきで残す

[本文](design_decisions/D1617.md)

## D1612. 行動に添える一言には、結果ではなくこれから何をするかを書くよう、書き方の案内で頼む

[本文](design_decisions/D1612.md)

## D1641. 人を対象にした操作の品名は、完全一致・部分一致・意味の判断の順で相手の持ち物に当て、当てられないときは「持っていない」と言い切らない

[本文](design_decisions/D1641.md)

## D1631. 短期記憶の既定は rolling_summary にする

[本文](design_decisions/D1631.md)

## D1631-2. OpenRouter の provider を固定したら、送る引数をすべて受け付ける provider にだけ送る

[本文](design_decisions/D1631-2.md)

## D1631-3. 推論の段階を書かない run は minimal で送る

[本文](design_decisions/D1631-3.md)

## D1631-4. 古いメモのうち LLM から見える部分を消し、保存先と過去の trace を読む側は残す

[本文](design_decisions/D1631-4.md)

## D1631-5. 消した部品の snapshot のキーは、拒まずに捨てて件数を trace に残す

[本文](design_decisions/D1631-5.md)

## D1824. 短期記憶は要約の要約 (L5) を作らず、3 世代を超えた要約は捨てる

[本文](design_decisions/D1824.md)

## D1824-2. 短期記憶の要約は【ここまでのいきさつ】として流れと気分だけを持ち、言われた予定と実際にしたことを分けて書かせる

[本文](design_decisions/D1824-2.md)

## D1824-5. 短期記憶の出来事には、それを見る 1 手の番号を付ける

[本文](design_decisions/D1824-5.md)

## D1824-6. Being の snapshot に後から足したキーは、無ければ空として読む

[本文](design_decisions/D1824-6.md)

## D1824-7. 行動の結果は環境が文にして観測の本文に入れ、構造の欄は契約に足さない

[本文](design_decisions/D1824-7.md)

## D1824-8. 観測は、環境の中で起きた順を持つ。順は同じ環境の中でだけ比べられる

[本文](design_decisions/D1824-8.md)

## D1824-9. 短期記憶は、出来事の種類ごとの型と、規則を持つ集約で持つ

[本文](design_decisions/D1824-9.md)

## D1824-10. 【直近の出来事】を Being の側でも作り、今の文と影で比べる

[本文](design_decisions/D1824-10.md)

## D1824-11. 古いターンは、いきさつが届いたときに外す

[本文](design_decisions/D1824-11.md)

## D1824-12. 短期記憶が頼んだいきさつは、裏で作り、その Being のターンの始めに入れる

[本文](design_decisions/D1824-12.md)

## D1652. CI の uv は、配布元からではなく PyPI から固定版を入れる

[本文](design_decisions/D1652.md)

## D1837. ゲームと Being のイベント基盤を一つにする

[本文](design_decisions/D1837.md)

## D1621. エピソードは、自分の目次を持つ集約にする。目次の並びは問い合わせで作る

[本文](design_decisions/D1621.md)

## D1862. 本番のプロンプトからタイル用の問い合わせと整形への参照を外す

[本文](design_decisions/D1862.md)

## D1862-3. ギルド依頼の発行場所はスポットで確認する

[本文](design_decisions/D1862-3.md)

## D1862-4. ショップの購入場所はスポットの一致で確かめる

[本文](design_decisions/D1862-4.md)

## D1862-2. タイルマップ専用のイベント受け手と一括登録を消す

[本文](design_decisions/D1862-2.md)

## D1862-6. 旧タイルの時間進行と専用のモンスター行動を削除する

[本文](design_decisions/D1862-6.md)

## D1862-5. 旧タイル用LLMの入口を消し、UI構築器を明示して渡す

[本文](design_decisions/D1862-5.md)

## D1862-7. タイル上の移動と経路探索を削除し、追跡の領域とスポット移動を残す

[本文](design_decisions/D1862-7.md)

## D1862-8. タイルの宝箱・設置物・品の操作の入口だけを削除する

[本文](design_decisions/D1862-8.md)

## D1862-9. タイル専用の採取・スキル実行を削除し、装備の値は残す

[本文](design_decisions/D1862-9.md)

## D1862-10. 旧タイル用の現在状態問い合わせを、本番の取得契約を残して削除する

[本文](design_decisions/D1862-10.md)

## D1862-11. タイル専用の観測を外し、本番の配信規則を保つ

[本文](design_decisions/D1862-11.md)

## D1862-14. 物理マップは本体に先立ち保存先だけを切り離す

[本文](design_decisions/D1862-14.md)

## D1862-13. タイルの当たり判定を削除し、モンスターのスキル装備の値を残す

[本文](design_decisions/D1862-13.md)

## D1862-12. NPC会話の木と会話終了のクエスト購読を一緒に削除する

[本文](design_decisions/D1862-12.md)
