import { describe, expect, it } from "vitest";

import {
  getNumberObjectProperty,
  getObjectProperty,
  getStringObjectProperty,
  isRenderableObject,
  type TiledObject,
} from "./tiledMap";

describe("tiledMap helpers", () => {
  const object: TiledObject = {
    id: 1,
    name: "treasure",
    type: "object",
    x: 64,
    y: 96,
    properties: [
      { name: "asset_key", type: "string", value: "object_chest_closed" },
      { name: "spawn_weight", type: "int", value: 3 },
      { name: "interactive", type: "bool", value: true },
    ],
  };

  it("reads generic object properties", () => {
    expect(getObjectProperty(object, "asset_key")).toBe("object_chest_closed");
    expect(getObjectProperty(object, "interactive")).toBe(true);
    expect(getObjectProperty(object, "missing")).toBeNull();
  });

  it("reads typed object properties", () => {
    expect(getStringObjectProperty(object, "asset_key")).toBe("object_chest_closed");
    expect(getStringObjectProperty(object, "spawn_weight")).toBeNull();
    expect(getNumberObjectProperty(object, "spawn_weight")).toBe(3);
    expect(getNumberObjectProperty(object, "asset_key")).toBeNull();
  });

  it("detects renderable objects by asset key", () => {
    expect(isRenderableObject(object)).toBe(true);
    expect(
      isRenderableObject({
        id: 2,
        name: "plain-area",
        type: "area",
        x: 0,
        y: 0,
      }),
    ).toBe(false);
  });
});
