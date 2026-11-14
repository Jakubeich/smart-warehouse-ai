import { lazy, Suspense } from "react";
import { usePreferences } from "@/stores/simulation";
import { Button } from "@/components/shared";
import { WarehouseCanvas } from "./2d/WarehouseCanvas";
import { RenderBoundary } from "./shared/RenderBoundary";
import type { WarehouseViewProps } from "./shared/scene";

const Warehouse3D = lazy(() => import("./3d/Warehouse3D"));

export function ViewUnavailable() {
  return (
    <div className="view-unavailable" role="alert">
      <strong>3D pohled se nepodařilo zobrazit</strong>
      <p>Simulace zůstává zachovaná. Pokračujte ve 2D pohledu.</p>
      <Button
        variant="outline"
        onClick={() => usePreferences.getState().setViewMode("2d")}
      >
        Zpět do 2D
      </Button>
    </div>
  );
}

export function WarehouseViewport(props: WarehouseViewProps) {
  const mode = usePreferences((state) => state.viewMode);
  if (mode !== "3d") return <WarehouseCanvas {...props} />;
  return (
    <RenderBoundary
      fallback={
        <div className="map-surface">
          <ViewUnavailable />
        </div>
      }
    >
      <Suspense
        fallback={
          <div className="map-surface view-loading" role="status">
            Načítání 3D pohledu…
          </div>
        }
      >
        <Warehouse3D {...props} />
      </Suspense>
    </RenderBoundary>
  );
}
