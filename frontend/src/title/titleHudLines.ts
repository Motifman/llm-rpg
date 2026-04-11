/**
 * タイトル HUD 用の短文。シミュレーション試行・こちら側への接続・エラーなどを連想させるログ風の表記。
 */
export const TITLE_HUD_LINES: readonly string[] = [
  "MANSION_SIM: warm_start — attempt 4/∞",
  "OBSERVER_LINK: probing your_surface … no_ack",
  "ERROR 0xE4A1: inbound_handshake timed out",
  "SIM_TICK: frame desync — rolling back 12ms",
  "UPLINK: retrying bind to local_presence (backoff)",
  "SESSION_BRIDGE: connection_reset by far side",
  "PUPPET_THREAD: cannot mirror viewer_plane",
  "SIMULATION_DEPTH: exceeded safe envelope",
  "HOST_ENDPOINT: refused — trying ghost route",
  "RUNTIME_FAULT: null_reference in narrative_core",
  "YOUR_SIDE: socket open — parity check failed",
  "ECHO_TO_YOU: packet lost (checksum mismatch)",
  "LIVE_SIM: sandbox breach — containment hold",
  "CONNECT_ATTEMPT: stale token — reissue queued",
  "FATAL_OK: nonfatal stack unwind (logged)",
  "INBOUND_YOU: half_open — FIN never seen",
  "WORLD_MODEL: simulation step rejected",
  "ERROR_TRACE: cascading fail in link_layer",
  "PRESENCE_SYNC: we see you — channel unstable",
  "SIM_BOOTSTRAP: cold path — previous crash noted",
];

export const TITLE_HUD_TICK_MS = 2800;

export function pickTitleHudLine(avoid: string | null): string {
  const pool =
    avoid === null ? [...TITLE_HUD_LINES] : TITLE_HUD_LINES.filter((s) => s !== avoid);
  if (pool.length === 0) {
    return TITLE_HUD_LINES[0] ?? "";
  }
  return pool[Math.floor(Math.random() * pool.length)]!;
}
