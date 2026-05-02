export type SelectableCharacter = {
  id: string;
  worldId: string;
  name: string;
  subtitle: string;
  roleLabel: string;
  description: string;
  imageSrc?: string;
  thumbnailSrc?: string;
  statusLabel: string;
};

export const PARTY_SLOT_COUNT = 4;

export const CHARACTERS_BY_WORLD: Record<string, SelectableCharacter[]> = {
  abandoned_hospital: [
    {
      id: "gate_girl",
      worldId: "abandoned_hospital",
      name: "門前の少女",
      subtitle: "GATE GIRL // MEMORY ANCHOR",
      roleLabel: "案内者",
      description:
        "閉じられた夜の入口に立つ少女。記憶の欠落と選択の痛みを、静かな声で指し示す。",
      imageSrc: "/assets/prologue/gate_girl.png",
      thumbnailSrc: "/assets/prologue/gate_girl.png",
      statusLabel: "LINKABLE",
    },
    {
      id: "lost_nurse_placeholder",
      worldId: "abandoned_hospital",
      name: "未接続の看護師",
      subtitle: "NO SIGNAL // PLACEHOLDER",
      roleLabel: "未接続",
      description:
        "病棟の奥から断片的な応答だけが返っている。転送可能な輪郭は、まだ確定していない。",
      statusLabel: "NO_SIGNAL",
    },
    {
      id: "night_patient_placeholder",
      worldId: "abandoned_hospital",
      name: "記録外の患者",
      subtitle: "NO SIGNAL // PLACEHOLDER",
      roleLabel: "未接続",
      description:
        "古い記録に名前だけが残っている存在。同期には追加の記憶断片が必要になる。",
      statusLabel: "NO_SIGNAL",
    },
  ],
};

export function getCharactersForWorld(worldId: string): SelectableCharacter[] {
  return CHARACTERS_BY_WORLD[worldId] ?? [];
}
