import {
  Suspense,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import { useGLTF } from "@react-three/drei/core/Gltf";
import {
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  type Material,
  type BufferGeometry,
} from "three";
import { RenderBoundary } from "../shared/RenderBoundary";
import { placeholderParts, type ModelKind } from "./assets";
import { ModelReadyContext, useModelSources } from "./modelSources";

function LoadedModel({
  src,
  kind,
  color,
}: {
  src: string;
  kind: ModelKind;
  color?: string;
}) {
  // No CDN dependency. Add local decoders deliberately if compressed assets are introduced.
  const { scene } = useGLTF(src, false, false);
  const onReady = useContext(ModelReadyContext);
  useEffect(() => onReady(kind), [onReady, kind]);
  const { instance, ownedMaterials } = useMemo(() => {
    const instance = scene.clone(true);
    const ownedMaterials = new Map<Material, MeshStandardMaterial>();
    instance.traverse((object) => {
      if (!(object instanceof Mesh)) return;
      object.castShadow = object.receiveShadow = true;
      const tint = (material: Material) => {
        if (
          !color ||
          material.name !== "SW_FleetAccent" ||
          !(material instanceof MeshStandardMaterial)
        )
          return material;
        if (!ownedMaterials.has(material)) {
          const copy = material.clone();
          copy.color.set(color);
          copy.emissive.set(color);
          ownedMaterials.set(material, copy);
        }
        return ownedMaterials.get(material)!;
      };
      object.material = Array.isArray(object.material)
        ? object.material.map(tint)
        : tint(object.material);
    });
    return { instance, ownedMaterials };
  }, [scene, color]);
  useEffect(
    () => () => ownedMaterials.forEach((material) => material.dispose()),
    [ownedMaterials],
  );
  // Geometries/materials from the loader cache belong to all instances.
  return <primitive object={instance} dispose={null} />;
}

type BatchPart = {
  geometry: BufferGeometry;
  material: Material | Material[];
  matrix: Matrix4;
};
function InstancedPart({
  part,
  positions,
  scale,
}: {
  part: BatchPart;
  positions: [number, number, number][];
  scale: number;
}) {
  const mesh = useRef<InstancedMesh>(null);
  useEffect(() => {
    const instance = mesh.current;
    return () => instance?.dispose();
  }, [part.geometry, part.material, positions.length]);
  useLayoutEffect(() => {
    const matrix = new Matrix4();
    positions.forEach((position, index) => {
      matrix
        .makeScale(scale, scale, scale)
        .setPosition(...position)
        .multiply(part.matrix);
      mesh.current!.setMatrixAt(index, matrix);
    });
    mesh.current!.instanceMatrix.needsUpdate = true;
    mesh.current!.computeBoundingSphere();
  }, [part, positions, scale]);
  return (
    <instancedMesh
      ref={mesh}
      args={[part.geometry, part.material, positions.length]}
      castShadow
      receiveShadow
      dispose={null}
    />
  );
}
function LoadedBatch({
  kind,
  src,
  positions,
  scale,
}: {
  kind: ModelKind;
  src: string;
  positions: [number, number, number][];
  scale: number;
}) {
  const { scene } = useGLTF(src, false, false);
  const onReady = useContext(ModelReadyContext);
  useEffect(() => onReady(kind), [kind, onReady]);
  const parts = useMemo(() => {
    scene.updateMatrixWorld(true);
    const parts: BatchPart[] = [];
    scene.traverse((object) => {
      if (object instanceof Mesh)
        parts.push({
          geometry: object.geometry,
          material: object.material,
          matrix: object.matrixWorld.clone(),
        });
    });
    return parts;
  }, [scene]);
  return parts.map((part, index) => (
    <InstancedPart
      key={index}
      part={part}
      positions={positions}
      scale={scale}
    />
  ));
}
export function StaticModelBatch({
  kind,
  positions,
  scale,
  onError,
  fallback,
}: {
  kind: ModelKind;
  positions: [number, number, number][];
  scale: number;
  onError: (kind: ModelKind) => void;
  fallback: ReactNode;
}) {
  const src = useModelSources()[kind];
  if (!src) return fallback;
  return (
    <RenderBoundary
      key={src}
      fallback={
        <ModelFailure kind={kind} onError={onError}>
          {fallback}
        </ModelFailure>
      }
    >
      <Suspense fallback={fallback}>
        <LoadedBatch
          kind={kind}
          src={src}
          positions={positions}
          scale={scale}
        />
      </Suspense>
    </RenderBoundary>
  );
}
function ModelFailure({
  kind,
  onError,
  children,
}: {
  kind: ModelKind;
  onError: (kind: ModelKind) => void;
  children: ReactNode;
}) {
  useEffect(() => onError(kind), [kind, onError]);
  return children;
}
export function Placeholder({
  kind,
  color,
}: {
  kind: ModelKind;
  color?: string;
}) {
  return (
    <group>
      {placeholderParts(kind, color).map((part, i) => (
        <mesh key={i} position={part.position} castShadow receiveShadow>
          <boxGeometry args={part.size} />
          <meshStandardMaterial
            color={part.color}
            roughness={0.7}
            metalness={0.12}
          />
        </mesh>
      ))}
    </group>
  );
}
export function ModelVisual({
  kind,
  color,
  onError,
  fallback,
}: {
  kind: ModelKind;
  color?: string;
  onError: (kind: ModelKind) => void;
  fallback?: ReactNode;
}) {
  const src = useModelSources()[kind];
  const placeholder = fallback ?? <Placeholder kind={kind} color={color} />;
  if (!src) return placeholder;
  return (
    <RenderBoundary
      key={src}
      fallback={
        <ModelFailure kind={kind} onError={onError}>
          {placeholder}
        </ModelFailure>
      }
    >
      <Suspense fallback={placeholder}>
        <LoadedModel src={src} kind={kind} color={color} />
      </Suspense>
    </RenderBoundary>
  );
}
