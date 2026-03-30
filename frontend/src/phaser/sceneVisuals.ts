import type { SceneWeather } from "../types";

export type ActorPalette = {
  bodyColor: number;
  accentColor: number;
  outlineColor: number;
};

export type WeatherOverlayStyle = {
  fillColor: number;
  alpha: number;
  streakColor: number | null;
  streakAlpha: number;
  streakSpacing: number;
};

export function getVisualAnimationState({
  movedThisFrame,
  tweenActive,
}: {
  movedThisFrame: boolean;
  tweenActive: boolean;
}): "walking" | "idle" {
  if (movedThisFrame || tweenActive) {
    return "walking";
  }
  return "idle";
}

export function getFacingAngleDegrees(facing: string): number {
  const rotationByFacing: Record<string, number> = {
    up: 0,
    down: 180,
    left: 270,
    right: 90,
  };
  return rotationByFacing[facing] ?? 180;
}

export function getActorPalette(actor: {
  is_manual_controlled?: boolean;
  actor_kind?: string;
}): ActorPalette {
  if (actor.is_manual_controlled === true) {
    return {
      bodyColor: 0xf2a65a,
      accentColor: 0xfff0b5,
      outlineColor: 0x4d2d16,
    };
  }
  if (actor.actor_kind === "world_object") {
    return {
      bodyColor: 0xc882ff,
      accentColor: 0xf3dbff,
      outlineColor: 0x332044,
    };
  }
  return {
    bodyColor: 0x6ac3ff,
    accentColor: 0xe4f5ff,
    outlineColor: 0x15384a,
  };
}

export function getWeatherOverlayStyle(
  weather: SceneWeather | null,
): WeatherOverlayStyle | null {
  const weatherType = weather?.weather_type ?? "CLEAR";
  const intensity = Math.max(0, Math.min(1, weather?.weather_intensity ?? 0));

  if (weatherType === "RAIN") {
    return {
      fillColor: 0x5a7694,
      alpha: 0.08 + intensity * 0.08,
      streakColor: 0xd7edff,
      streakAlpha: 0.18 + intensity * 0.08,
      streakSpacing: 26,
    };
  }
  if (weatherType === "HEAVY_RAIN" || weatherType === "STORM") {
    return {
      fillColor: 0x344a61,
      alpha: 0.14 + intensity * 0.12,
      streakColor: 0xe7f4ff,
      streakAlpha: 0.28 + intensity * 0.12,
      streakSpacing: 20,
    };
  }
  if (weatherType === "FOG") {
    return {
      fillColor: 0xd9e2df,
      alpha: 0.12 + intensity * 0.1,
      streakColor: null,
      streakAlpha: 0,
      streakSpacing: 0,
    };
  }
  return null;
}
