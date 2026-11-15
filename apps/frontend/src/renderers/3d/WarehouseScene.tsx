import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type ComponentRef,
} from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei/core/OrbitControls";
import {
  Color,
  Group,
  InstancedMesh,
  Matrix4,
  PerspectiveCamera,
  Vector3,
} from "three";
import type { Layers } from "@/stores/simulation";
import type { Point, Robot, Simulation, Warehouse } from "@/types/domain";
import {
  motionDuration,
  motionPath,
  positionOnPath,
  robotColors,
  worldPosition,
  worldYaw,
  type RobotPose,
  type WarehouseViewProps,
} from "../shared/scene";
import {
  cellModels,
  placeholderParts,
  type BoxPart,
  type ModelKind,
} from "./assets";
import { ModelVisual, StaticModelBatch } from "./ModelVisual";
import { useModelSources } from "./modelSources";

export type CameraCommand = { mode: "orbit" | "top"; revision: number };
function CameraRig({
  warehouse,
  command,
  editing,
}: {
  warehouse: Warehouse;
  command: CameraCommand;
  editing?: boolean;
}) {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const { camera, size, invalidate } = useThree();
  const width = warehouse.width * warehouse.cell_size,
    depth = warehouse.height * warehouse.cell_size;
  useLayoutEffect(() => {
    const c = camera as PerspectiveCamera;
    const fov = (c.fov * Math.PI) / 180;
    const tanV = Math.tan(fov / 2),
      tanH = (tanV * size.width) / size.height;
    const target = new Vector3(
      width / 2,
      0.35 * warehouse.cell_size,
      depth / 2,
    );
    const direction =
      command.mode === "top"
        ? new Vector3(0, 1, 0.0001)
        : new Vector3(0.7, 1, 0.85).normalize();
    const right = new Vector3()
      .crossVectors(new Vector3(0, 1, 0), direction)
      .normalize();
    const up = new Vector3().crossVectors(direction, right);
    let distance = 1;
    // Fit the actual projected warehouse bounds, including tall models and control gutters.
    for (const x of [0, width])
      for (const y of [0, 2 * warehouse.cell_size])
        for (const z of [0, depth]) {
          const offset = new Vector3(x, y, z).sub(target);
          distance = Math.max(
            distance,
            offset.dot(direction) +
              Math.max(
                Math.abs(offset.dot(right)) / tanH,
                Math.abs(offset.dot(up)) / tanV,
              ),
          );
        }
    distance *= 1.05;
    c.position.copy(target).addScaledVector(direction, distance);
    c.near = 0.1;
    c.far = Math.max(1000, distance * 5);
    c.lookAt(target);
    c.updateProjectionMatrix();
    controls.current?.target.copy(target);
    controls.current?.update();
    invalidate();
  }, [
    camera,
    width,
    depth,
    warehouse.cell_size,
    size.width,
    size.height,
    command,
    invalidate,
  ]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      enableRotate={!editing}
      minDistance={2 * warehouse.cell_size}
      maxDistance={Math.max(width, depth) * 8}
      maxPolarAngle={Math.PI / 2 - 0.05}
    />
  );
}

/** Every proxy box (including shelf uprights and pallets) shares one draw call. */
function BoxInstances({ boxes }: { boxes: BoxPart[] }) {
  const mesh = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    const m = mesh.current!;
    if (!m) return;
    const matrix = new Matrix4();
    const color = new Color();
    boxes.forEach((part, i) => {
      matrix.makeScale(...part.size).setPosition(...part.position);
      m.setMatrixAt(i, matrix);
      m.setColorAt(i, color.set(part.color));
    });
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
  }, [boxes]);
  if (!boxes.length) return null;
  return (
    <instancedMesh
      ref={mesh}
      args={[undefined, undefined, boxes.length]}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial roughness={0.8} metalness={0.05} />
    </instancedMesh>
  );
}

const StaticModels = memo(function StaticModels({
  cells,
  obstacles,
  cellSize,
  stations,
  onError,
}: {
  cells: Warehouse["cells"];
  obstacles?: Point[];
  cellSize: number;
  stations: boolean;
  onError: (kind: ModelKind) => void;
}) {
  const sources = useModelSources();
  const { boxes, batches } = useMemo(() => {
    const boxes: BoxPart[] = [];
    const batches = new Map<
      ModelKind,
      { positions: [number, number, number][]; fallback: BoxPart[] }
    >();
    const entries = [
      ...cells,
      ...(obstacles ?? []).map(([x, y]) => ({
        x,
        y,
        type: "OBSTACLE",
      })),
    ];
    for (const cell of entries) {
      const kind = cellModels[cell.type];
      if (
        !kind ||
        (!stations && ["pickup", "dropoff", "charger"].includes(kind))
      )
        continue;
      const position = worldPosition([cell.x, cell.y], cellSize);
      const parts = placeholderParts(kind).map((part) => ({
        color: part.color,
        position: part.position.map(
          (v, i) => position[i] + v * cellSize,
        ) as BoxPart["position"],
        size: part.size.map((v) => v * cellSize) as BoxPart["size"],
      }));
      if (sources[kind]) {
        const batch = batches.get(kind) ?? { positions: [], fallback: [] };
        batch.positions.push(position);
        batch.fallback.push(...parts);
        batches.set(kind, batch);
      } else boxes.push(...parts);
    }
    return { boxes, batches };
  }, [cells, obstacles, cellSize, stations, sources]);
  return (
    <>
      <BoxInstances boxes={boxes} />
      {[...batches].map(([kind, batch]) => (
        <StaticModelBatch
          key={kind}
          kind={kind}
          positions={batch.positions}
          scale={cellSize}
          onError={onError}
          fallback={<BoxInstances boxes={batch.fallback} />}
        />
      ))}
    </>
  );
});

function RobotModel({
  robot,
  run,
  tick,
  speed,
  viewMotion,
  index,
  cellSize,
  selected,
  color,
  projections,
  reducedMotion,
  editing,
  onSelect,
  onError,
}: {
  robot: Robot;
  run: string;
  tick: number;
  speed: number;
  viewMotion?: Simulation["view_motion"];
  index: number;
  cellSize: number;
  selected: boolean;
  color: string;
  projections: Map<string, Vector3>;
  reducedMotion: boolean;
  editing?: boolean;
  onSelect?: (id: string) => void;
  onError: (kind: ModelKind) => void;
}) {
  const root = useRef<Group>(null);
  const body = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const previous = useRef<RobotPose | undefined>(undefined);
  const motion = useRef({
    path: [robot.position],
    elapsed: 1,
    duration: 0,
    fromYaw: 0,
    toYaw: 0,
  });
  const [x, y] = robot.position;
  const yaw = worldYaw(robot.orientation);
  useLayoutEffect(() => {
    const next: RobotPose = {
      run,
      tick,
      position: [x, y],
      episode: viewMotion?.episode,
    };
    const m = motion.current;
    m.path = motionPath(previous.current, next, viewMotion, index);
    m.fromYaw = body.current!.rotation.y;
    m.toYaw =
      m.fromYaw +
      Math.atan2(Math.sin(yaw - m.fromYaw), Math.cos(yaw - m.fromYaw));
    m.duration = reducedMotion ? 0 : motionDuration(m.path, speed);
    m.elapsed = 0;
    if (!m.duration) {
      root.current!.position.set(...worldPosition(next.position, cellSize));
      body.current!.rotation.y = yaw;
    }
    previous.current = next;
    invalidate();
  }, [
    x,
    y,
    yaw,
    run,
    tick,
    speed,
    cellSize,
    viewMotion,
    index,
    reducedMotion,
    invalidate,
  ]);
  const projected = useRef(new Vector3());
  useFrame((state, delta) => {
    const m = motion.current;
    if (m.elapsed < m.duration) {
      m.elapsed = Math.min(m.duration, m.elapsed + delta);
      const t = m.elapsed / m.duration;
      root.current!.position.set(
        ...worldPosition(positionOnPath(m.path, t), cellSize),
      );
      body.current!.rotation.y = m.fromYaw + (m.toYaw - m.fromYaw) * t;
      invalidate();
    }
    const point = projected.current.copy(root.current!.position);
    point.y += (robot.load > 0 ? 0.9 : 0.65) * cellSize;
    point.project(state.camera);
    point.x = ((point.x + 1) * state.size.width) / 2;
    point.y = ((1 - point.y) * state.size.height) / 2;
    projections.set(robot.id, point);
  }, -0.5);
  const select = (e: ThreeEvent<MouseEvent>) => {
    if (editing || e.delta > 4) return;
    e.stopPropagation();
    onSelect?.(robot.id);
  };
  return (
    <group
      ref={root}
      scale={cellSize}
      name={robot.id}
      userData={{ robotId: robot.id }}
    >
      <group ref={body} onClick={select}>
        <ModelVisual
          kind="robot"
          color={robot.mode === "OFFLINE" ? "#94a3b8" : color}
          onError={onError}
        />
        {robot.load > 0 && (
          <group position={[0, 0.35, 0]}>
            <ModelVisual kind="pallet" onError={onError} />
          </group>
        )}
      </group>
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]}>
          <ringGeometry args={[0.51, 0.57, 40]} />
          <meshBasicMaterial color="#4f46e5" />
        </mesh>
      )}
    </group>
  );
}

function Lines({ positions, color }: { positions: number[]; color: string }) {
  const points = useMemo(() => new Float32Array(positions), [positions]);
  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[points, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={color} />
    </lineSegments>
  );
}
function Tile({
  position,
  cellSize,
  color,
  opacity = 0.3,
  height = 0.035,
}: {
  position: Point;
  cellSize: number;
  color: string;
  opacity?: number;
  height?: number;
}) {
  const [x, , z] = worldPosition(position, cellSize);
  return (
    <mesh position={[x, height * cellSize, z]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[cellSize * 0.92, cellSize * 0.92]} />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={opacity}
        depthWrite={false}
      />
    </mesh>
  );
}
function ContextGuard({ onLost }: { onLost: () => void }) {
  const gl = useThree((state) => state.gl);
  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (event: Event) => {
      event.preventDefault();
      onLost();
    };
    canvas.addEventListener("webglcontextlost", lost);
    return () => canvas.removeEventListener("webglcontextlost", lost);
  }, [gl, onLost]);
  return null;
}

function LabelLayout({
  labels,
  projections,
  selected,
}: {
  labels: Map<string, HTMLButtonElement>;
  projections: Map<string, Vector3>;
  selected?: string | null;
}) {
  useFrame(({ size }) => {
    const occupied: { x: number; y: number }[] = [];
    const ordered = [...labels.entries()].sort(([a], [b]) =>
      a === selected ? -1 : b === selected ? 1 : a.localeCompare(b),
    );
    for (const [id, label] of ordered) {
      const point = projections.get(id);
      label.style.visibility = "hidden";
      if (
        !point ||
        point.z <= -1 ||
        point.z >= 1 ||
        point.x < 0 ||
        point.x > size.width ||
        point.y < 0 ||
        point.y > size.height
      )
        continue;
      const x = Math.max(28, Math.min(size.width - 28, point.x));
      for (let attempt = 0; attempt < 20; attempt++) {
        const offset = Math.ceil(attempt / 2) * 25 * (attempt % 2 ? -1 : 1);
        const y = point.y + offset;
        if (
          y < 40 ||
          y > size.height - 40 ||
          occupied.some((p) => Math.abs(p.x - x) < 55 && Math.abs(p.y - y) < 24)
        )
          continue;
        label.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
        label.style.visibility = "visible";
        occupied.push({ x, y });
        break;
      }
    }
  });
  return null;
}

export function WarehouseScene({
  frame,
  onCell,
  onHover,
  onSelect,
  editing,
  layers,
  command,
  reducedMotion,
  onLost,
  onModelError,
  labels,
}: WarehouseViewProps & {
  labels: Map<string, HTMLButtonElement>;
  layers: Layers;
  command: CameraCommand;
  reducedMotion: boolean;
  onLost: () => void;
  onModelError: (kind: ModelKind) => void;
}) {
  const projections = useRef(new Map<string, Vector3>());
  const w = frame.warehouse,
    s = frame.simulation,
    unit = w.cell_size;
  const width = w.width * unit,
    depth = w.height * unit;
  const hover = useRef<string | null>(null);
  const grid = useMemo(() => {
    const lines: number[] = [];
    for (let x = 0; x <= w.width; x++)
      lines.push(x * unit, 0.012, 0, x * unit, 0.012, depth);
    for (let y = 0; y <= w.height; y++)
      lines.push(0, 0.012, y * unit, width, 0.012, y * unit);
    return lines;
  }, [w.width, w.height, unit, width, depth]);
  const cellAt = (
    event: ThreeEvent<PointerEvent | MouseEvent>,
  ): Point | null => {
    const x = Math.floor(event.point.x / unit),
      y = Math.floor(event.point.z / unit);
    return x >= 0 && y >= 0 && x < w.width && y < w.height ? [x, y] : null;
  };
  const maxHeat = layers.heatmap
    ? Math.max(1, ...Object.values(s?.heatmap ?? {}))
    : 1;
  return (
    <>
      <color attach="background" args={["#f4f5f7"]} />
      <ambientLight intensity={1.3} />
      <hemisphereLight args={["#eef4ff", "#acb3bf", 1.4]} />
      <directionalLight
        position={[width * 0.2, Math.max(width, depth), -depth * 0.4]}
        intensity={2}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-Math.max(width, depth)}
        shadow-camera-right={Math.max(width, depth)}
        shadow-camera-top={Math.max(width, depth)}
        shadow-camera-bottom={-Math.max(width, depth)}
        shadow-camera-far={Math.max(width, depth) * 5}
        shadow-normalBias={0.03}
      />
      <CameraRig warehouse={w} command={command} editing={editing} />
      <ContextGuard onLost={onLost} />
      <mesh position={[width / 2, -0.09 * unit, depth / 2]} receiveShadow>
        <boxGeometry args={[width, 0.18 * unit, depth]} />
        <meshStandardMaterial color="#e9edf0" roughness={0.95} />
      </mesh>
      <mesh
        position={[width / 2, 0.005, depth / 2]}
        rotation={[-Math.PI / 2, 0, 0]}
        onClick={(event) => {
          const cell = cellAt(event);
          if (cell && event.delta <= 4) onCell?.(cell);
        }}
        onPointerMove={(event) => {
          if (!editing) return;
          const cell = cellAt(event),
            key = cell?.join(",") ?? null;
          if (key !== hover.current) {
            hover.current = key;
            onHover?.(cell);
          }
        }}
        onPointerLeave={() => {
          hover.current = null;
          onHover?.(null);
        }}
      >
        <planeGeometry args={[width, depth]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {layers.grid && <Lines positions={grid} color="#cbd2d9" />}
      <StaticModels
        cells={w.cells}
        obstacles={s?.obstacles}
        cellSize={unit}
        stations={layers.stations}
        onError={onModelError}
      />
      {layers.heatmap &&
        Object.entries(s?.heatmap ?? {}).map(([key, value]) => (
          <Tile
            key={key}
            position={key.split(",").map(Number) as Point}
            cellSize={unit}
            color="#f97316"
            opacity={0.1 + (0.6 * value) / maxHeat}
          />
        ))}
      {layers.reservations &&
        (s?.reservations ?? [])
          .filter((r) => r.tick <= (s?.tick ?? 0) + 3)
          .map((r) => (
            <Tile
              key={`${r.robot_id}-${r.x}-${r.y}-${r.tick}`}
              position={[r.x, r.y]}
              cellSize={unit}
              color="#8b5cf6"
              height={0.04}
            />
          ))}
      {layers.conflicts &&
        (s?.conflicts ?? []).flatMap((c, i) =>
          (c.vertex
            ? [c.vertex]
            : [...(c.a_edge ?? []), ...(c.b_edge ?? [])]
          ).map((p, j) => (
            <Tile
              key={`${i}-${j}`}
              position={p}
              cellSize={unit}
              color="#ef4444"
              opacity={0.65}
              height={0.05}
            />
          )),
        )}
      {editing && frame.hover && (
        <Tile
          position={frame.hover}
          cellSize={unit}
          color="#4f46e5"
          height={0.06}
        />
      )}
      <LabelLayout
        labels={labels}
        projections={projections.current}
        selected={frame.selectedRobot}
      />
      {frame.robots.map((robot, index) => {
        const color = robotColors[index % robotColors.length];
        const path = [
          robot.position,
          ...robot.path.slice(robot.path_index + 1),
        ];
        const positions = path.slice(1).flatMap((p, i) => {
          const a = worldPosition(path[i], unit),
            b = worldPosition(p, unit);
          return [a[0], 0.065 * unit, a[2], b[0], 0.065 * unit, b[2]];
        });
        return (
          <group key={`${s?.id ?? w.id}-${robot.id}`}>
            {layers.paths && positions.length > 0 && (
              <Lines positions={positions} color={color} />
            )}
            <RobotModel
              robot={robot}
              run={s?.id ?? w.id}
              tick={s?.tick ?? 0}
              speed={s?.speed ?? 1}
              viewMotion={s?.view_motion}
              index={index}
              cellSize={unit}
              selected={frame.selectedRobot === robot.id}
              color={color}
              projections={projections.current}
              reducedMotion={reducedMotion}
              editing={editing}
              onSelect={onSelect}
              onError={onModelError}
            />
          </group>
        );
      })}
    </>
  );
}
