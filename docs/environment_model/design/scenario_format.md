# シナリオの形式 (YAML)

シナリオの作者 (人と LLM) が書く形式。読み込む側 (infrastructure) が、ここから名詞と動詞の宣言 ([world_design.md](world_design.md)) を作り、`WorldDesign.compose` に渡す。決めた経緯は #2052。

## 決まり

- 1 つのシナリオは 1 つの YAML ファイル。共通の部品は `includes:` で取り込む
- 名前で指すものは、欄の値ではなく、地図 (mapping) の鍵に書く (`spots: { lift_landing: { ... } }`)。鍵が `SpotId` などの宣言の名前になる。同じ鍵を 2 回書くと、YAML を読む時点で `DesignFlaw` にする
- 作者は、名詞の中に、その名詞に付く動詞を書いてよい (物の中に操作、区画の中に出入り)。読み込む側が名詞と動詞に分ける (#1990)
- 宣言の型は既定値を持たない。書かなかった欄は、読み込む側が共通の部品 (データ) の既定で埋める (#2029 の E2)。埋めたものは `DesignWarning` にしない。作者が書くべきなのに書かなかったもの (知覚の文など) だけを `DesignWarning` にする
- 誤りの場所 (`DesignLocation`) は、宣言の種類・名前・欄で表す。YAML の道筋 (`spots.lift_landing.objects.lift_panel.interactions.start_lift.precondition`) は、`DesignLocation("object", "lift_panel", "interactions.start_lift.precondition")` に写す
- 文の中の人は、`{actor}` `{target}` `{chosen_by_group}` `{each_person}` だけ。物や場所の名前は、作者が文に直接書く

## 一番上の欄

```yaml
includes: [common/ja_default.yaml]    # 共通の部品。断りの文の表、組み込みの行為の知覚の文、知覚の既定の文、行為の長さなど
introduction:                         # WorldIntroduction
  text: ...                           # 導入
  objective: ...                      # 目的
rules: { ... }                        # WorldRules。includes の既定を、書いた欄だけ上書きする
time: { day_night: ..., weather: ... }
flags: { ... }
groupings: { ... }                    # 分け方と、その中の集まり
spots: { ... }                        # 場所。中に区画・物・見つかる物を書く
passages: { ... }
item_specs: { ... }
characters: { ... }
world_stages: { ... }
group_decisions: { ... }
outcomes: { ... }
happenings: { ... }
reactions: { ... }
joint_actions: { ... }
person_interactions: { ... }          # 殴る、盗むなど、人への操作
ending: ...
```

## 条件と効果の書き方

木の 1 つの節は地図で、種類を表す鍵をちょうど 1 つ持つ。鍵が種類 (条件や効果の型の名前を snake_case にし、`Condition` / `Effect` を外したもの)、値がその欄。欄が 1 つだけの種類は、値に直接書いてよい。条件の節だけは、種類の鍵と並べて `failure_text` を書ける。種類の鍵が 0 個か 2 個以上の節は `DesignFlaw`。

```yaml
precondition:
  all_of:
    - flag_is_raised: generator_running        # 欄が 1 つなら直接
    - has_item: { who: actor, item_spec: lift_key, count: 1 }
  failure_text: 操作盤の鍵穴に合う鍵を持っていないか、機械が動いていない。
```

- `failure_text` は、その節の欄と並べて書く。条件を置いた場所の根には必ず書く (#2029 の B1)
- 主語は `actor` `target` `chosen_by_group` `each_person` と、名指しの人 (`{ named: haru }`)

## 例: 廃坑の山村の昇降機

今の形式では、籠に乗ることを人の属性 (`aboard`)、籠の在庫 (3)、乗った印の品物 (`lift_berth`) の 3 つで表している。新しい形式では、乗り場の中の籠を区画 (定員 3) にし、操作盤を籠の中からしか届かない物にする。

```yaml
spots:
  lift_landing:
    name: 昇降機の乗り場
    description: 坑道の最も深い所にある昇降機の乗り場。鉄の籠が地上へ続く縦穴に吊られている。
    atmosphere: { lighting: dark, outdoor: false, temperature: cold, ambient_sound: 縦穴を吹き上がる風の音 }

    sections:
      cage:
        name: 昇降機の籠
        capacity: 3
        reachable_objects: [lift_panel]          # 操作盤は籠の中からしか届かない
        access:                                   # SectionAccessDeclaration
          enter_label: 籠に乗り込む
          leave_label: 籠から降りる
          enter_text: 鉄の籠に乗り込んだ。籠が足もとで小さく揺れた。
          leave_text: 籠から降りた。
          entry_condition:
            not: { flag_is_raised: lift_departed }
            failure_text: 籠はもう上がってしまった。
          perceived_as:
            witness: { clear: "{actor}が昇降機の籠に乗り込んだ。" }

    objects:
      lift_panel:
        name: 籠の操作盤
        description: 籠の奥の壁にある操作盤。鍵穴と始動の把手が付いている。
        interactions:
          start_lift:
            display_label: 鍵を差して昇降機を動かす
            precondition:
              all_of:
                - not: { flag_is_raised: lift_departed }
                  failure_text: 籠はもう上がってしまった。昇降機は二度と動かない。
                - has_item: { who: actor, item_spec: lift_key, count: 1 }
                  failure_text: 鍵穴に合う鍵を持っていない。
                - flag_is_raised: generator_running
                  failure_text: 把手を引いても、籠はぴくりとも動かない。
              failure_text: 昇降機は動かない。
            effect:
              raise_flag: lift_departed
            success_text: 籠が大きく揺れ、ゆっくりと縦穴を上がりはじめた。
            perceived_as:
              witness: { clear: "{actor}が昇降機の操作盤に鍵を差し、把手を引いた。" }
              sound: { loudness: very_loud, clear: 鉄の籠が軋みながら上がっていく音がした。, muffled: 遠くで重い鉄の軋む音がした。 }

outcomes:
  rescued: { name: 救出, announcement: "{each_person}は昇降機で外へ出た。" }
  stranded: { name: 取り残された, announcement: "{each_person}は坑道に取り残された。" }

happenings:
  lift_leaves:                                    # 籠が上がったとき、籠の中の人は救出、ほかは取り残される
    condition: { flag_is_raised: lift_departed, failure_text: 籠はまだ上がっていない。 }
    once: true
    effect:
      sequence:
        - for_everyone:
            people: { where: { is_in_section: { who: each_person, section: cage } } }
            effect: { set_outcome: { who: each_person, outcome: rescued } }
        - for_everyone:
            people: { where: { not: { is_in_section: { who: each_person, section: cage } } } }
            effect: { set_outcome: { who: each_person, outcome: stranded } }
```

## 例: 獣を出来事に置き換える

今の廃坑の山村では、北の坑道で物音が積もると「坑道の獣」が現れる (モンスター)。モンスターは #1971 で設計するので、ここでは出来事に置き換える。

```yaml
happenings:
  beast_north_attacks:
    condition:
      all_of:
        - flag_is_raised: beast_north_awake
        - people_count_at_least:
            people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }
            count: 1
      failure_text: 北の坑道は静かだ。
    once: false
    effect:
      for_everyone:
        people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }
        effect: { damage: { who: each_person, amount: 8 } }
    notice:
      sound_from: { spot: north_tunnel, sound: { loudness: very_loud, clear: 暗がりから何かが唸り、飛びかかってきた。, muffled: 坑道の奥で獣のような唸り声がした。 } }
```

## 例: 登場人物

世界に渡す部分と、Being に渡す人柄 (`being:`) を分けて書く。読み込む側は `being:` を世界の宣言に入れず、Being の入口 (ステージ 8) に渡す。

```yaml
characters:
  haru:
    appearance: 測量具を背負った年かさの男
    spawn_spot: north_shaft_head
    initial_items: [lamp, fuel_can, lamp_oil, lamp_oil]
    initial_held: [lamp]
    initial_groups: [team_north]
    knows_at_start: [mio]
    being:
      name: ハル
      first_person: 私
      persona: あなたはハル、山の測量を請け負う調査隊の隊長で、落ち着いた男。……
      objective: ミオと二人そろって、坑道の奥の昇降機で外へ出る。
```

## 決めたこと (#2052)

1. 条件と効果の節は、種類を鍵にした地図で書く (`kind:` の欄は使わない)。短く書けて、人と LLM が読みやすいため
2. 1 つのシナリオは 1 ファイル。共通の部品だけを `includes:` で取り込む
3. 名前は地図の鍵に書く (`id:` の欄は使わない)
4. `includes:` は、地図を鍵ごとに重ね、シナリオに書いた鍵だけを置き換える
5. Being に渡す人柄は、登場人物の `being:` の中に書く
