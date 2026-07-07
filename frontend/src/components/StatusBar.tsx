import { useState } from "react";
import { SyncStatus, useApi } from "../api";
import { SettingsModal } from "./SettingsModal";

function ago(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso + "Z").getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  return h < 48 ? `${h}h ${mins % 60}m ago` : `${Math.floor(h / 24)}d ago`;
}

export function StatusBar({ displayName }: { displayName?: string | null }) {
  const { data: status } = useApi<SyncStatus>("/api/sync/status", 10_000);
  const [kicking, setKicking] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const syncNow = async () => {
    setKicking(true);
    await fetch("/api/sync/now", { method: "POST" }).catch(() => {});
    setTimeout(() => setKicking(false), 2500);
  };

  const running = status?.running;
  const failed = status?.last_run && status.last_run.status !== "ok";

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-carbon-700 bg-carbon-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-2.5">
          <span className="label text-sm text-signal">Training / {displayName || "Athlete"}</span>
          <span className="data hidden text-[11px] text-carbon-500 sm:block">
            local only · {status?.activity_count ?? "—"} activities
          </span>
          <div className="data ml-auto flex items-center gap-3 text-[11px]">
            {running ? (
              <span className="flex items-center gap-1.5 text-signal">
                <span className="sync-dot inline-block h-1.5 w-1.5 rounded-full bg-signal" />
                syncing{status?.phase ? ` · ${status.phase}` : ""}
              </span>
            ) : (
              <span className={failed ? "text-hard" : "text-bone-300"}>
                {failed ? `last sync ${status?.last_run?.status}` : `synced ${ago(status?.last_success_at ?? null)}`}
              </span>
            )}
            <button
              onClick={syncNow}
              disabled={running || kicking}
              className="label border border-carbon-500 px-2.5 py-1 text-[11px] text-bone-100 transition-colors hover:border-signal hover:text-signal disabled:opacity-40"
            >
              Sync now
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              aria-label="Settings"
              className="label border border-carbon-500 px-2.5 py-1 text-[11px] text-bone-100 transition-colors hover:border-signal hover:text-signal"
            >
              Settings
            </button>
          </div>
        </div>
      </header>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {status?.rate_limit_cooldown_until && (
        <div className="border-b border-ride/60 bg-ride/10 px-6 py-2 text-center">
          <span className="data text-xs text-ride">
            Garmin is rate-limiting us — backing off until{" "}
            {new Date(status.rate_limit_cooldown_until + "Z").toLocaleTimeString()}. Data shown is
            from the local cache.
          </span>
        </div>
      )}
    </>
  );
}
