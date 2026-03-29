export type SceneMap = {
  map_asset_key: string;
  tiled_map_path: string;
  tile_width: number;
  tile_height: number;
  map_width_tiles: number;
  map_height_tiles: number;
  collision_layer_name: string;
  tileset_keys: string[];
};

export type SceneCamera = {
  mode: string;
  tracked_actor_id: number | null;
  viewport_width: number;
  viewport_height: number;
};

export type SimulationState = {
  is_paused: boolean;
  speed_multiplier: number;
  current_tick: number;
};

export type SceneActor = {
  actor_id: number;
  player_id: number | null;
  display_name: string;
  actor_kind: string;
  tile_x: number;
  tile_y: number;
  facing: string;
  sprite_key: string;
  is_manual_controlled: boolean;
  is_llm_controlled: boolean;
  state: string;
  busy_until_tick?: number | null;
};

export type SceneWeather = {
  weather_type: string;
  weather_intensity: number;
  weather_overlay_key: string | null;
};

export type SceneGateway = {
  gateway_id: number;
  tile_x: number;
  tile_y: number;
  target_spot_id: number;
  target_spot_name: string;
  landing_tile_x: number;
  landing_tile_y: number;
};

export type SceneArea = {
  area_id: number;
  name: string;
  shape_kind: string;
  points: Array<{ x: number; y: number }>;
};

export type SceneLogEntry = {
  level: string;
  message: string;
  related_actor_id: number | null;
};

export type GameSceneSnapshot = {
  scene_id: string;
  spot_id: number;
  spot_name: string;
  map: SceneMap;
  camera: SceneCamera;
  simulation: SimulationState;
  actors: SceneActor[];
  monsters: unknown[];
  weather: SceneWeather | null;
  gateways: SceneGateway[];
  areas: SceneArea[];
  ui_logs: SceneLogEntry[];
  scene_version: number;
  server_time_ms: number;
};

export type WorldSceneSummary = {
  spot_id: number;
  scene_id: string;
  spot_name: string;
  actor_count: number;
  monster_count: number;
  weather_type: string | null;
  scene_version: number;
};

export type SceneDeltaEvent = {
  event_id: string;
  event_type: string;
  scene_id: string;
  spot_id: number;
  scene_version: number;
  emitted_at_ms: number;
  payload: Record<string, unknown>;
};

export type SceneEventsMessage = {
  type: "scene_events";
  scene_id: string;
  events: SceneDeltaEvent[];
  latest_scene_version: number;
};

export type StreamErrorMessage = {
  type: "error";
  detail: string;
  errors?: Array<Record<string, unknown>>;
};

export type PongMessage = {
  type: "pong";
};

export type StreamMessage = SceneEventsMessage | StreamErrorMessage | PongMessage;

export type MoveResult = {
  success: boolean;
  player_id: number;
  player_name: string;
  from_spot_id: number;
  from_spot_name: string;
  to_spot_id: number;
  to_spot_name: string;
  from_coordinate: { x: number; y: number; z: number };
  to_coordinate: { x: number; y: number; z: number };
  moved_at: string;
  busy_until_tick: number;
  message: string;
  error_message: string | null;
};
