import { BoxGeometry } from "three";

/** A real, self-contained glTF 2 binary for exercising the loader, not a production asset. */
export function robotGlbFixture(): Buffer {
  const geometry = new BoxGeometry(0.78, 0.38, 0.58).toNonIndexed();
  const positions = Buffer.from(geometry.attributes.position.array.buffer);
  const normals = Buffer.from(geometry.attributes.normal.array.buffer);
  const binary = Buffer.concat([positions, normals]);
  const document = {
    asset: { version: "2.0", generator: "Warehouse E2E fixture" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, translation: [0, 0.19, 0] }],
    meshes: [
      { primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, material: 0 }] },
    ],
    materials: [
      {
        pbrMetallicRoughness: {
          baseColorFactor: [0.1, 0.4, 0.8, 1],
          metallicFactor: 0.1,
          roughnessFactor: 0.6,
        },
      },
    ],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: positions.length, target: 34962 },
      {
        buffer: 0,
        byteOffset: positions.length,
        byteLength: normals.length,
        target: 34962,
      },
    ],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 36,
        type: "VEC3",
        min: [-0.39, -0.19, -0.29],
        max: [0.39, 0.19, 0.29],
      },
      { bufferView: 1, componentType: 5126, count: 36, type: "VEC3" },
    ],
  };
  const json = Buffer.from(JSON.stringify(document));
  const padded = Buffer.concat([
    json,
    Buffer.alloc((4 - (json.length % 4)) % 4, 32),
  ]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + padded.length + binary.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  geometry.dispose();
  return Buffer.concat([header, padded, binHeader, binary]);
}
