import { Application, Container, Graphics, Text } from "pixi.js";
import type { Layers } from "@/stores/simulation";
import type { Point } from "@/types/domain";
import { robotColors, type SceneFrame } from "../shared/scene";

export class WarehouseRenderer {
  app = new Application();
  world = new Container();
  geometry = new Container();
  robotLayer = new Container();
  width = 800;
  height = 500;
  zoom = 1;
  pan: Point = [0, 0];
  scale = 24;
  offset: Point = [0, 0];
  frame: SceneFrame | null = null;
  layers: Layers = {
    grid: true,
    paths: true,
    ids: true,
    reservations: false,
    conflicts: true,
    stations: true,
    heatmap: false,
  };
  previous = new Map<string, Point>();
  targets = new Map<string, Point>();
  sprites = new Map<string, Container>();
  lastUpdate = 0;
  duration = 200;
  ready = false;
  destroyed = false;
  async init(host: HTMLElement) {
    await this.app.init({
      background: "#fafafa",
      antialias: true,
      resolution: Math.min(window.devicePixelRatio, 2),
      autoDensity: true,
      preference: "webgl",
    });
    if (this.destroyed) {
      this.app.destroy(true, { children: true });
      return;
    }
    host.appendChild(this.app.canvas);
    this.app.stage.addChild(this.world);
    this.world.addChild(this.geometry, this.robotLayer);
    this.ready = true;
    this.app.ticker.add(() => this.animate());
    this.resize(host.clientWidth, host.clientHeight);
  }
  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
    if (this.ready) {
      this.app.renderer.resize(width, height);
      this.layout();
    }
  }
  layout() {
    if (!this.frame) return;
    const w = this.frame.warehouse;
    this.scale =
      Math.max(
        6,
        Math.min((this.width - 54) / w.width, (this.height - 64) / w.height),
      ) * this.zoom;
    this.offset = [
      (this.width - w.width * this.scale) / 2 + this.pan[0],
      (this.height - w.height * this.scale) / 2 + this.pan[1],
    ];
    this.world.position.set(...this.offset);
    this.world.scale.set(this.scale);
  }
  setCamera(zoom: number, pan: Point) {
    this.zoom = zoom;
    this.pan = pan;
    this.layout();
  }
  pick(x: number, y: number): Point | null {
    const p: Point = [
      Math.floor((x - this.offset[0]) / this.scale),
      Math.floor((y - this.offset[1]) / this.scale),
    ];
    return this.frame &&
      p[0] >= 0 &&
      p[1] >= 0 &&
      p[0] < this.frame.warehouse.width &&
      p[1] < this.frame.warehouse.height
      ? p
      : null;
  }
  label(
    text: string,
    x: number,
    y: number,
    size = 0.3,
    color = "#71717a",
    parent: Container = this.geometry,
  ) {
    const label = new Text({
      text,
      style: {
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize:
          Math.max(size, (parent === this.geometry ? 7.5 : 8) / this.scale) *
          64,
        fill: color,
        fontWeight: "500",
      },
    });
    label.scale.set(1 / 64);
    label.anchor.set(0.5);
    label.position.set(x, y);
    parent.addChild(label);
    return label;
  }
  update(frame: SceneFrame, layers: Layers) {
    if (!this.ready) return;
    const oldFrame = this.frame;
    this.frame = frame;
    this.layers = layers;
    this.layout();
    this.geometry.removeChildren().forEach((c) => c.destroy());
    this.robotLayer
      .removeChildren()
      .forEach((c) => c.destroy({ children: true }));
    this.sprites.clear();
    const { warehouse: w, simulation: s } = frame;
    const graphic = new Graphics();
    this.geometry.addChild(graphic);
    graphic
      .rect(0, 0, w.width, w.height)
      .fill("#ffffff")
      .stroke({ color: "#d4d4d8", width: 0.025 });
    if (layers.heatmap && s) {
      const max = Math.max(1, ...Object.values(s.heatmap));
      for (const [key, count] of Object.entries(s.heatmap)) {
        const [x, y] = key.split(",").map(Number);
        graphic
          .rect(x, y, 1, 1)
          .fill({ color: "#27bfd0", alpha: 0.1 + (0.65 * count) / max });
      }
    }
    if (layers.grid) {
      for (let x = 0; x <= w.width; x++)
        graphic.moveTo(x, 0).lineTo(x, w.height);
      for (let y = 0; y <= w.height; y++)
        graphic.moveTo(0, y).lineTo(w.width, y);
      graphic.stroke({ color: "#e4e4e7", width: 0.025 });
    }
    for (const cell of w.cells) {
      const { x, y, type } = cell;
      if (type === "FLOOR") continue;
      if (type === "SHELF") {
        graphic
          .roundRect(x + 0.08, y + 0.09, 0.84, 0.82, 0.05)
          .fill("#d4d4d8")
          .stroke({ color: "#a1a1aa", width: 0.02 });
        graphic
          .moveTo(x + 0.14, y + 0.5)
          .lineTo(x + 0.86, y + 0.5)
          .stroke({ color: "#a1a1aa", width: 0.05 });
      } else if (type === "WALL" || type === "OBSTACLE") {
        graphic
          .rect(x + 0.03, y + 0.03, 0.94, 0.94)
          .fill(type === "WALL" ? "#71717a" : "#b26745");
      } else if (layers.stations) {
        const color =
          type === "PICKUP"
            ? "#3b82f6"
            : type === "DROPOFF"
              ? "#4a9862"
              : "#c69224";
        graphic
          .roundRect(x + 0.1, y + 0.1, 0.8, 0.8, 0.1)
          .fill({ color, alpha: 0.18 })
          .stroke({ color, width: 0.04 });
        this.label(
          type === "PICKUP" ? "N" : type === "DROPOFF" ? "V" : "ϟ",
          x + 0.5,
          y + 0.5,
          0.4,
          color,
        );
      }
    }
    for (const [x, y] of s?.obstacles ?? []) {
      graphic.roundRect(x + 0.06, y + 0.06, 0.88, 0.88, 0.08).fill("#a55c3e");
      this.label("×", x + 0.5, y + 0.5, 0.6, "#ffcc9e");
    }
    if (layers.reservations && s)
      for (const r of s.reservations) {
        graphic.rect(r.x + 0.12, r.y + 0.12, 0.76, 0.76).fill({
          color:
            robotColors[
              frame.robots.findIndex((x) => x.id === r.robot_id) %
                robotColors.length
            ],
          alpha: 0.12,
        });
      }
    if (layers.paths)
      for (const [i, r] of frame.robots.entries()) {
        const path = r.path.slice(r.path_index);
        if (path.length > 1) {
          graphic.moveTo(path[0][0] + 0.5, path[0][1] + 0.5);
          for (const p of path.slice(1)) graphic.lineTo(p[0] + 0.5, p[1] + 0.5);
          graphic.stroke({
            color: robotColors[i % robotColors.length],
            width: 0.07,
            alpha:
              frame.selectedRobot && frame.selectedRobot !== r.id ? 0.25 : 0.65,
          });
        }
        if (r.goal)
          graphic.circle(r.goal[0] + 0.5, r.goal[1] + 0.5, 0.24).stroke({
            color: robotColors[i % robotColors.length],
            width: 0.05,
          });
      }
    if (layers.conflicts && s)
      for (const conflict of s.conflicts) {
        const p = conflict.vertex ?? conflict.a_edge?.[1];
        if (p)
          graphic
            .rect(p[0], p[1], 1, 1)
            .fill({ color: "#e75f68", alpha: 0.45 });
      }
    if (frame.hover)
      graphic
        .rect(frame.hover[0], frame.hover[1], 1, 1)
        .fill({ color: "#6366f1", alpha: 0.12 })
        .stroke({ color: "#6366f1", width: 0.04 });
    for (let x = 0; x < w.width; x += w.width > 30 ? 2 : 1)
      this.label(String(x), x + 0.5, -0.5, 0.29);
    for (let y = 0; y < w.height; y += w.height > 25 ? 2 : 1)
      this.label(String(y), -0.55, y + 0.5, 0.29);
    const changed =
      oldFrame?.simulation?.tick !== s?.tick ||
      oldFrame?.simulation?.id !== s?.id;
    if (changed) {
      this.previous = new Map(
        frame.robots.map((r) => [
          r.id,
          oldFrame?.robots.find((x) => x.id === r.id)?.position ?? r.position,
        ]),
      );
      this.lastUpdate = performance.now();
      this.duration = window.matchMedia("(prefers-reduced-motion: reduce)")
        .matches
        ? 0
        : Math.min(250, 350 / (s?.speed ?? 1));
    }
    for (const [i, r] of frame.robots.entries()) {
      const container = new Container();
      const color = robotColors[i % robotColors.length];
      const body = new Graphics();
      if (frame.selectedRobot === r.id)
        body
          .roundRect(-0.47, -0.47, 0.94, 0.94, 0.18)
          .stroke({ color: "#18181b", width: 0.045 });
      body
        .roundRect(-0.35, -0.35, 0.7, 0.7, 0.14)
        .fill(color)
        .stroke({ color: "#ffffff", alpha: 0.6, width: 0.02 });
      body
        .moveTo(0.22, -0.12)
        .lineTo(0.35, 0)
        .lineTo(0.22, 0.12)
        .fill("#ffffff");
      container.addChild(body);
      body.rotation = (r.orientation * Math.PI) / 180;
      if (layers.ids && (this.scale >= 24 || frame.selectedRobot === r.id))
        this.label(r.id, 0, 0.64, 0.3, "#3f3f46", container);
      this.robotLayer.addChild(container);
      this.sprites.set(r.id, container);
      this.targets.set(r.id, r.position);
    }
    this.animate();
  }
  animate() {
    const progress = this.duration
      ? Math.min(1, (performance.now() - this.lastUpdate) / this.duration)
      : 1;
    for (const [id, sprite] of this.sprites) {
      const target = this.targets.get(id)!;
      const previous = this.previous.get(id) ?? target;
      const contiguous =
        Math.abs(target[0] - previous[0]) + Math.abs(target[1] - previous[1]) <=
        1;
      const t = contiguous ? progress : 1;
      sprite.position.set(
        previous[0] + (target[0] - previous[0]) * t + 0.5,
        previous[1] + (target[1] - previous[1]) * t + 0.5,
      );
    }
  }
  destroy() {
    this.destroyed = true;
    if (this.ready) this.app.destroy(true, { children: true });
  }
}
