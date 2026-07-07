import { useState } from "react";
import { AuthStatus, useApi } from "./api";
import { StatusBar } from "./components/StatusBar";
import { CyclingView } from "./views/CyclingView";
import { ExportView } from "./views/ExportView";
import { LoadView } from "./views/LoadView";
import { RunningView } from "./views/RunningView";
import { SetupView } from "./views/SetupView";
import { SwimmingView } from "./views/SwimmingView";
import { WellnessView } from "./views/WellnessView";

const VIEWS = [
  { key: "load", label: "Load & 80/20", el: <LoadView /> },
  { key: "run", label: "Running", el: <RunningView /> },
  { key: "bike", label: "Cycling", el: <CyclingView /> },
  { key: "swim", label: "Swimming", el: <SwimmingView /> },
  { key: "wellness", label: "Recovery", el: <WellnessView /> },
  { key: "export", label: "Export", el: <ExportView /> },
] as const;

export default function App() {
  const [view, setView] = useState<string>("load");
  // gate the whole app on Garmin auth: poll so it flips to the dashboard right
  // after login and back to Setup if tokens are ever revoked.
  const { data: auth, error: authError } = useApi<AuthStatus>("/api/auth/status", 2500);

  if (!auth) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        {authError ? (
          <span className="label text-sm text-hard">can’t reach the backend — retrying…</span>
        ) : (
          <span className="label text-sm text-carbon-500">loading…</span>
        )}
      </div>
    );
  }
  if (!auth.authenticated) {
    return <SetupView />;
  }

  return (
    <div className="min-h-screen">
      <StatusBar displayName={auth.display_name} />
      <nav className="border-b border-carbon-700">
        <div className="mx-auto flex max-w-7xl gap-1 px-6">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              className={`label border-b-2 px-4 py-3 text-sm transition-colors ${
                view === v.key
                  ? "border-signal text-bone-50"
                  : "border-transparent text-bone-300 hover:text-bone-100"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </nav>
      <main className="mx-auto max-w-7xl px-6 py-8">
        {VIEWS.find((v) => v.key === view)?.el}
      </main>
      <footer className="border-t border-carbon-700 py-4 text-center">
        <span className="data text-[10px] text-carbon-500">
          all data local · syncs itself every 3h · nothing leaves this machine
        </span>
      </footer>
    </div>
  );
}
