export type TiledPropertyValue = string | number | boolean;

export type TiledProperty = {
  name: string;
  type: string;
  value: TiledPropertyValue;
};

export type TiledObject = {
  id: number;
  name: string;
  type: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  visible?: boolean;
  properties?: TiledProperty[];
};

export type TiledLayer = {
  id: number;
  name: string;
  type: "tilelayer" | "objectgroup";
  data?: number[];
  width?: number;
  height?: number;
  visible?: boolean;
  opacity?: number;
  objects?: TiledObject[];
};

export type TiledTileset = {
  firstgid: number;
  name: string;
  tilewidth: number;
  tileheight: number;
};

export type TiledDocument = {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  layers: TiledLayer[];
  tilesets?: TiledTileset[];
};

export function getObjectProperty(
  object: TiledObject,
  propertyName: string,
): TiledPropertyValue | null {
  const property = object.properties?.find((entry) => entry.name === propertyName);
  return property?.value ?? null;
}

export function getStringObjectProperty(
  object: TiledObject,
  propertyName: string,
): string | null {
  const value = getObjectProperty(object, propertyName);
  return typeof value === "string" ? value : null;
}

export function getNumberObjectProperty(
  object: TiledObject,
  propertyName: string,
): number | null {
  const value = getObjectProperty(object, propertyName);
  return typeof value === "number" ? value : null;
}

export function isRenderableObject(object: TiledObject): boolean {
  return getStringObjectProperty(object, "asset_key") != null;
}
