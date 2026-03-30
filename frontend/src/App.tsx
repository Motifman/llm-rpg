import { useState } from "react";

import { apiClient } from "./api/client";
import { useKeyboardStepMovement } from "./hooks/useKeyboardStepMovement";
import { useSceneRuntime } from "./hooks/useSceneRuntime";
import { GameCanvas } from "./phaser/GameCanvas";

const MOVE_LABELS = [
  { direction: "north", label: "N" },
  { direction: "west", label: "W" },
  { direction: "south", label: "S" },
  { direction: "east", label: "E" },
];

export function App() {
  const {
    connectionState,
    errorMessage,
    interactWithObject,
    manualActor,
    moveManualActor,
    overview,
    setCameraMode: syncCameraMode,
    selectedSpotId,
    setSelectedSpotId,
    snapshot,
  } = useSceneRuntime();
  const [speedMultiplier, setSpeedMultiplier] = useState(1);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [cameraMode, setCameraMode] = useState<"fixed" | "follow">("fixed");

  async function runCommand(action: () => Promise<void | unknown>) {
    try {
      setCommandError(null);
      await action();
    } catch (error) {
      setCommandError(
        error instanceof Error ? error.message : "Unknown command error",
      );
    }
  }

  useKeyboardStepMovement({
    enabled: manualActor != null,
    actorId: manualActor?.actor_id ?? null,
    onMove: async (actorId, direction) => {
      await runCommand(() => moveManualActor(actorId, direction));
    },
  });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="panel">
          <p className="eyebrow">Scenes</p>
          <h1>AI RPG World Viewer</h1>
          <div className="scene-list">
            {overview.map((scene) => (
              <button
                key={scene.spot_id}
                className={
                  scene.spot_id === selectedSpotId ? "scene-chip active" : "scene-chip"
                }
                onClick={() => setSelectedSpotId(scene.spot_id)}
                type="button"
              >
                <span>{scene.spot_name}</span>
                <small>
                  {scene.actor_count} actors / {scene.weather_type ?? "CLEAR"}
                </small>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <p className="eyebrow">Camera</p>
          <div className="control-row">
            <button
              onClick={() => {
                setCameraMode("fixed");
                syncCameraMode("fixed");
              }}
              type="button"
            >
              Fixed
            </button>
            <button
              onClick={() => {
                setCameraMode("follow");
                syncCameraMode("follow");
              }}
              type="button"
            >
              Follow
            </button>
          </div>
        </div>

        <div className="panel">
          <p className="eyebrow">Simulation</p>
          <div className="status-line">
            <span>Stream</span>
            <strong>{connectionState}</strong>
          </div>
          <div className="control-row">
            <button onClick={() => void runCommand(() => apiClient.pause())} type="button">
              Pause
            </button>
            <button onClick={() => void runCommand(() => apiClient.resume())} type="button">
              Resume
            </button>
          </div>
          <label className="speed-input">
            <span>Speed</span>
            <input
              max={5}
              min={0.25}
              onChange={(event) => setSpeedMultiplier(Number(event.target.value))}
              step={0.25}
              type="number"
              value={speedMultiplier}
            />
            <button
              onClick={() => void runCommand(() => apiClient.setSpeed(speedMultiplier))}
              type="button"
            >
              Apply
            </button>
          </label>
        </div>

        <div className="panel">
          <p className="eyebrow">Manual Actor</p>
          {manualActor ? (
            <>
              <div className="actor-card">
                <strong>{manualActor.display_name}</strong>
                <span>
                  Tile ({manualActor.tile_x}, {manualActor.tile_y})
                </span>
                <span>{manualActor.sprite_key}</span>
                <span>WASD / Arrow key hold supported</span>
              </div>
              <div className="move-grid">
                {MOVE_LABELS.map((item) => (
                  <button
                    key={item.direction}
                    onClick={() =>
                      void runCommand(() =>
                        moveManualActor(manualActor.actor_id, item.direction),
                      )
                    }
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">No manual actor found.</p>
          )}
        </div>
      </aside>

      <main className="viewer-column">
        <section className="viewer-panel">
          <div className="viewer-header">
            <div>
              <p className="eyebrow">Live Scene</p>
              <h2>{snapshot?.spot_name ?? "No scene selected"}</h2>
            </div>
          <div className="viewer-meta">
            <span>Version {snapshot?.scene_version ?? "-"}</span>
            <span>Tick {snapshot?.simulation.current_tick ?? "-"}</span>
            <span>{snapshot?.weather?.weather_type ?? "CLEAR"}</span>
            <span>{cameraMode.toUpperCase()}</span>
          </div>
          </div>
          <GameCanvas
            cameraMode={cameraMode}
            snapshot={snapshot}
            trackedActorId={cameraMode === "follow" ? manualActor?.actor_id ?? null : null}
          />
        </section>

        <section className="panel bottom-panel">
          <div className="split-columns">
            <div>
              <p className="eyebrow">Actors</p>
              <div className="list-block">
                {snapshot?.actors?.map((actor) => (
                  <div className="list-item" key={actor.actor_id}>
                    <strong>{actor.display_name}</strong>
                    <span>
                      ({actor.tile_x}, {actor.tile_y}) / {actor.facing}
                    </span>
                  </div>
                )) ?? <p className="muted">No actors yet.</p>}
              </div>
            </div>
            <div>
              <p className="eyebrow">Monsters</p>
              <div className="list-block">
                {snapshot?.monsters?.map((monster) => (
                  <div className="list-item" key={monster.monster_id}>
                    <strong>{monster.display_name}</strong>
                    <span>
                      ({monster.tile_x}, {monster.tile_y}) / {monster.facing}
                    </span>
                  </div>
                )) ?? <p className="muted">No monsters yet.</p>}
              </div>
            </div>
            <div>
              <p className="eyebrow">Objects</p>
              <div className="list-block">
                {snapshot?.objects?.map((object) => (
                  <div className="list-item" key={object.object_id}>
                    <strong>{object.display_name}</strong>
                    <span>
                      ({object.tile_x}, {object.tile_y}) / {object.object_kind}
                    </span>
                    <span>
                      {object.interaction_type ?? "no interaction"}
                      {" / "}
                      {object.is_blocking ? "blocking" : "passable"}
                    </span>
                    {"is_open" in object.interaction_data ? (
                      <span>
                        {(object.interaction_data.is_open as boolean) ? "opened" : "closed"}
                      </span>
                    ) : null}
                    {manualActor && object.interaction_type ? (
                      <button
                        onClick={() =>
                          void runCommand(() =>
                            interactWithObject(manualActor.actor_id, object.object_id),
                          )
                        }
                        type="button"
                      >
                        Interact
                      </button>
                    ) : null}
                  </div>
                )) ?? <p className="muted">No objects yet.</p>}
              </div>
            </div>
            <div>
              <p className="eyebrow">Logs</p>
              <div className="list-block">
                {snapshot?.ui_logs.slice(-8).map((entry, index) => (
                  <div className="list-item" key={`${entry.message}-${index}`}>
                    <strong>{entry.level}</strong>
                    <span>{entry.message}</span>
                  </div>
                )) ?? <p className="muted">No logs yet.</p>}
              </div>
            </div>
          </div>
          {errorMessage || commandError ? (
            <div className="error-banner">{errorMessage ?? commandError}</div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
