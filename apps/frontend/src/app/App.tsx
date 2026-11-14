import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Bot,
  Box,
  CheckSquare2,
  FlaskConical,
  LayoutDashboard,
  Settings,
  Warehouse,
  Menu,
  BrainCircuit,
} from "lucide-react";
import { Toaster } from "sonner";
import { Button, Loading, ErrorPanel } from "@/components/shared";
import { useLive } from "@/hooks/useLive";
import { activeRunKey, useSimulation } from "@/stores/simulation";
import { stateSchema } from "@/types/domain";
import { api, ApiError } from "@/lib/api";
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const SimulationPage = lazy(() => import("@/pages/SimulationPage"));
const Warehouses = lazy(() => import("@/pages/Warehouses"));
const Experiments = lazy(() => import("@/pages/Experiments"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const Learning = lazy(() => import("@/pages/Learning"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const FleetTasks = lazy(() => import("@/pages/FleetTasks"));
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { t } from "@/lib/i18n";
const nav = [
  { path: "/", label: t("dashboard"), icon: LayoutDashboard },
  { path: "/simulation", label: t("simulation"), icon: Activity },
  { path: "/warehouses", label: t("warehouses"), icon: Warehouse },
  { path: "/robots", label: t("robots"), icon: Bot },
  { path: "/tasks", label: t("tasks"), icon: CheckSquare2 },
  { path: "/experiments", label: t("experiments"), icon: FlaskConical },
  { path: "/learning", label: "Strojové učení", icon: BrainCircuit },
  { path: "/analytics", label: t("analytics"), icon: BarChart3 },
  { path: "/settings", label: t("settings"), icon: Settings },
];
function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Hlavní navigace">
      {nav.slice(0, -1).map(({ path, label, icon: Icon }, i) => (
        <div key={path}>
          {i === 5 && <Separator className="my-5" />}
          <NavLink to={path} end={path === "/"} onClick={onNavigate}>
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        </div>
      ))}
    </nav>
  );
}
export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  useLive();
  useEffect(() => {
    const id = sessionStorage.getItem(activeRunKey);
    if (!id || useSimulation.getState().simulation) return;
    const request = new AbortController();
    const stillRestoring = () =>
      !request.signal.aborted &&
      sessionStorage.getItem(activeRunKey) === id &&
      !useSimulation.getState().simulation;

    void api(`/simulations/${id}`, { signal: request.signal })
      .then((data) => {
        if (stillRestoring())
          useSimulation.getState().setSimulation(stateSchema.parse(data));
      })
      .catch((e: unknown) => {
        if (!stillRestoring()) return;
        const store = useSimulation.getState();
        if (e instanceof ApiError && e.status === 404) {
          store.clear();
          return;
        }
        store.setError("Simulaci se nepodařilo obnovit. Zkuste obnovit stránku.");
      });
    return () => request.abort();
  }, []);
  const error = useSimulation((s) => s.error);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string }>("/health"),
    refetchInterval: 10000,
    retry: 1,
  });
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Přejít na obsah
      </a>
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <Box size={25} strokeWidth={1.5} />
          <span>Smart Warehouse</span>
        </NavLink>
        <Navigation />
        <div className="sidebar-footer">
          <NavLink to="/settings">
            <Settings size={18} />
            Nastavení
          </NavLink>
          <div className="connection-state">
            <i className={health.data ? "online-dot" : "offline-dot"} />
            {health.data ? "Připojeno" : "Server není dostupný"}
          </div>
        </div>
      </aside>
      <header className="mobile-header">
        <NavLink to="/" className="brand">
          <Box size={23} />
          <span>Smart Warehouse</span>
        </NavLink>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Otevřít navigaci">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent side="left">
            <SheetHeader>
              <SheetTitle>Smart Warehouse</SheetTitle>
            </SheetHeader>
            <div className="mobile-nav">
              <Navigation onNavigate={() => setMenuOpen(false)} />
              <NavLink to="/settings" onClick={() => setMenuOpen(false)}>
                <Settings size={18} />
                Nastavení
              </NavLink>
            </div>
          </SheetContent>
        </Sheet>
      </header>
      <main id="main-content" className="main-content">
        <ErrorPanel error={error} />
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/simulation" element={<SimulationPage />} />
            <Route path="/warehouses" element={<Warehouses />} />
            <Route path="/robots" element={<FleetTasks key="robots" kind="robots" />} />
            <Route path="/tasks" element={<FleetTasks key="tasks" kind="tasks" />} />
            <Route path="/experiments" element={<Experiments />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/learning" element={<Learning />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </Suspense>
      </main>
      <Toaster
        theme="light"
        position="bottom-right"
        richColors
        closeButton
        containerAriaLabel="Oznámení"
        toastOptions={{ closeButtonAriaLabel: "Zavřít oznámení" }}
      />
    </div>
  );
}
