import { useCallback, useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Box, Scan, Rotate3D, ArrowDownToLine } from "lucide-react";
import { Button } from "@/components/shared";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { usePreferences } from "@/stores/simulation";
import { robotColors, type WarehouseViewProps } from "../shared/scene";
import { WarehouseScene, type CameraCommand } from "./WarehouseScene";
import { modelCatalog, type ModelKind } from "./assets";
import {
  ModelSourcesContext,
  ModelReadyContext,
  modelManifestSchema,
  type ModelSources,
} from "./modelSources";

function Unavailable() {
  return (
    <div className="view-unavailable" role="alert">
      <strong>3D pohled není dostupný</strong>
      <p>
        Prohlížeč nemůže vykreslit 3D scénu. Vaše simulace zůstává zachovaná.
      </p>
      <Button
        variant="outline"
        onClick={() => usePreferences.getState().setViewMode("2d")}
      >
        Zpět do 2D
      </Button>
    </div>
  );
}
export default function Warehouse3D(props: WarehouseViewProps) {
  const labels = useRef(new Map<string, HTMLButtonElement>());
  const layers = usePreferences((state) => state.layers);
  const [command, setCommand] = useState<CameraCommand>({
    mode: "orbit",
    revision: 0,
  });
  const [lost, setLost] = useState(false);
  const [sources, setSources] = useState<ModelSources>({});
  const [manifestError, setManifestError] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    void fetch("/models/manifest.json", {
      signal: abort.signal,
      cache: "no-cache",
    })
      .then((response) => {
        if (!response.ok) throw new Error("manifest");
        return response.json();
      })
      .then((json) => setSources(modelManifestSchema.parse(json).models))
      .catch(() => {
        if (!abort.signal.aborted) setManifestError(true);
      });
    return () => abort.abort();
  }, []);
  const onLost = useCallback(() => setLost(true), []);
  const [failed, setFailed] = useState<ModelKind[]>([]);
  const [ready, setReady] = useState<ModelKind[]>([]);
  const onReady = useCallback(
    (kind: ModelKind) =>
      setReady((old) => (old.includes(kind) ? old : [...old, kind])),
    [],
  );
  const onModelError = useCallback(
    (kind: ModelKind) =>
      setFailed((old) => (old.includes(kind) ? old : [...old, kind])),
    [],
  );
  const [reducedMotion, setReducedMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const basic = Object.values(sources).every((src) => !src);
  return (
    <div className="map-surface map-3d-surface">
      <div
        className="map-canvas"
        role="region"
        aria-label="Interaktivní 3D mapa skladu"
        data-testid="warehouse-3d"
        onContextMenu={(event) => event.preventDefault()}
      >
        {lost ? (
          <Unavailable />
        ) : (
          <Canvas
            shadows="percentage"
            frameloop="demand"
            dpr={[1, 1.5]}
            camera={{ fov: 40, near: 0.1, far: 1000 }}
          >
            <ModelSourcesContext value={sources}>
              <ModelReadyContext value={onReady}>
                <WarehouseScene
                  {...props}
                  labels={labels.current}
                  layers={layers}
                  command={command}
                  reducedMotion={reducedMotion}
                  onLost={onLost}
                  onModelError={onModelError}
                />
              </ModelReadyContext>
            </ModelSourcesContext>
          </Canvas>
        )}
      </div>
      {!lost && layers.ids && (
        <div className="robot-label-overlay">
          {props.frame.robots.map((robot, index) => (
            <button
              key={robot.id}
              ref={(element) => {
                if (element) labels.current.set(robot.id, element);
                else labels.current.delete(robot.id);
              }}
              className="robot-3d-label"
              style={{
                borderColor:
                  props.frame.selectedRobot === robot.id
                    ? robotColors[index % robotColors.length]
                    : undefined,
              }}
              aria-label={`Vybrat robota ${robot.id}`}
              onClick={() => !props.editing && props.onSelect?.(robot.id)}
            >
              <i
                style={{ background: robotColors[index % robotColors.length] }}
              />
              {robot.id}
            </button>
          ))}
        </div>
      )}
      <div className="model-note">
        <Dialog>
          <DialogTrigger asChild>
            <button className="model-note-button">
              <Box size={13} />
              {basic ? "Pracovní 3D modely" : "3D modely"}
            </button>
          </DialogTrigger>
          <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>Modely pro 3D pohled</DialogTitle>
              <DialogDescription>
                Sada modelů vytvořená v Blenderu pro tento sklad. Stav níže
                ukazuje, které modely už jsou ve scéně načtené.
              </DialogDescription>
            </DialogHeader>
            <div className="model-catalog">
              {Object.entries(modelCatalog).map(([kind, asset]) => (
                <div key={kind}>
                  <div>
                    <strong>{asset.label}</strong>
                    <small>{asset.size} · délka × šířka × výška</small>
                  </div>
                  <span>
                    {failed.includes(kind as ModelKind)
                      ? "Chyba souboru"
                      : sources[kind as ModelKind]
                        ? ready.includes(kind as ModelKind)
                          ? "GLB načteno"
                          : "GLB připraveno"
                        : "Základní tvar"}
                  </span>
                </div>
              ))}
            </div>
            <p className="subtle">
              Rozměry platí pro buňku 1 m. Střed modelu leží na podlaze, robot
              míří vpřed podél osy +X. Podlaha a trasy se vykreslují
              automaticky.
            </p>
            <p className="subtle">
              Změna vzhledu nemění pohyb, baterii ani plánování robotů.
            </p>
          </DialogContent>
        </Dialog>
        {failed.length > 0 && (
          <span role="status">
            {failed.map((key) => modelCatalog[key].label).join(", ")}: GLB se
            nepodařilo načíst, zobrazen základní tvar.
          </span>
        )}
        {manifestError && (
          <span role="status">
            Seznam modelů se nepodařilo načíst. Zobrazujeme základní tvary.
          </span>
        )}
      </div>
      {!lost && (
        <div className="map-camera camera-3d">
          <span>
            <Rotate3D size={12} />
            {props.editing
              ? "Kliknutím upravit · pravým tlačítkem posunout"
              : "Tažením otočit · pravým tlačítkem posunout · kolečkem přiblížit"}
          </span>
          <button
            aria-label="Pohled shora"
            title="Pohled shora"
            onClick={() =>
              setCommand((old) => ({ mode: "top", revision: old.revision + 1 }))
            }
          >
            <ArrowDownToLine size={15} />
          </button>
          <button
            aria-label="Obnovit 3D kameru"
            title="Obnovit 3D kameru"
            onClick={() =>
              setCommand((old) => ({
                mode: "orbit",
                revision: old.revision + 1,
              }))
            }
          >
            <Scan size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
