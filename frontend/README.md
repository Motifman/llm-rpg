# Frontend Viewer

## Requirements

- Node.js `>= 20`
- npm `>= 10`

This frontend uses `Vite 5`, so older Node runtimes such as `v16` will fail at build time.

On this machine, make sure `/usr/local/bin/node` is selected before `/opt/local/bin/node`.

Example:

```bash
PATH=/usr/local/bin:$PATH npm install
PATH=/usr/local/bin:$PATH npm run test
PATH=/usr/local/bin:$PATH npm run build
PATH=/usr/local/bin:$PATH npm run dev
```

## Purpose

This app is the React + Phaser viewer for the backend scene APIs:

- `GET /api/world/overview`
- `GET /api/scenes/{spot_id}/snapshot`
- `WS /api/scenes/{scene_id}/stream`
- `POST /api/control/*`
- `POST /api/actors/{actor_id}/move`

## Current Scope

- Scene selection
- Fixed / follow camera switching
- Snapshot loading
- WebSocket polling stream updates
- Manual move controls
- Keyboard long-press step movement
- Follow-camera scene auto switching
- Tiled JSON-backed Phaser rendering with idle/walk actor motion and weather fades

## Verification

- `PATH=/usr/local/bin:$PATH npm run test`
- `PATH=/usr/local/bin:$PATH npm run build`
