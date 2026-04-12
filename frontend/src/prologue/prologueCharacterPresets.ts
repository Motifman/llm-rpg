/**
 * 立ち絵のトーン補正プリセット（CSS `filter` 値）。
 * シーンの `character.tintPreset` で参照する。未指定は neutral。
 */
export const PROLOGUE_CHARACTER_TINT_PRESETS: Record<string, string> = {
  neutral: "none",
  /** 例: 夕景・暖色寄せ（必要に応じて調整） */
  eveningWarm: "brightness(0.96) saturate(1.08) sepia(0.12)",
  /** 例: 霧・寒色寄せ */
  fogCool: "brightness(1.02) saturate(0.92) hue-rotate(-6deg)",
};

export function resolveCharacterTintFilter(
  tintPreset: string | undefined,
  tintFilter: string | undefined,
): string | undefined {
  if (tintFilter != null && tintFilter.length > 0) {
    return tintFilter;
  }
  const key = tintPreset ?? "neutral";
  return PROLOGUE_CHARACTER_TINT_PRESETS[key] ?? PROLOGUE_CHARACTER_TINT_PRESETS.neutral;
}
