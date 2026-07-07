import { useEffect, useState } from "react";
import { AppConfig, getJson, postJson } from "../api";

const FIELDS: { group: string; items: { key: string; label: string; step?: number }[] }[] = [
  {
    group: "Running",
    items: [
      { key: "cadence_band_low", label: "Cadence band — low (spm)" },
      { key: "cadence_band_high", label: "Cadence band — high (spm)" },
    ],
  },
  { group: "Cycling", items: [{ key: "ftp_fallback_w", label: "FTP fallback (W)" }] },
  { group: "Swimming", items: [{ key: "pool_length_m", label: "Pool length (m)" }] },
  {
    group: "Intensity (80/20)",
    items: [
      { key: "easy_zone_max", label: "Easy = HR zones 1…N", step: 1 },
      { key: "easy_target_pct", label: "Easy target (%)" },
      { key: "z2_cap_bpm_note", label: "Z2 cap note (bpm)" },
    ],
  },
  {
    group: "Training load",
    items: [
      { key: "acwr_low", label: "ACWR healthy band — low", step: 0.1 },
      { key: "acwr_high", label: "ACWR healthy band — high", step: 0.1 },
    ],
  },
];

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJson<AppConfig>("/api/config")
      .then((c) => {
        const t = (c as AppConfig & { editable_targets?: Record<string, number> }).editable_targets ?? {};
        setValues(Object.fromEntries(Object.entries(t).map(([k, v]) => [k, String(v)])));
      })
      .catch((e) => setError(String(e)));
  }, []);

  const save = async () => {
    if (!values) return;
    setBusy(true);
    setError(null);
    try {
      const nums: Record<string, number> = {};
      for (const [k, v] of Object.entries(values)) {
        if (v.trim() === "" || Number.isNaN(Number(v))) {
          setError(`"${k}" must be a number`);
          setBusy(false);
          return;
        }
        nums[k] = Number(v);
      }
      await postJson("/api/config/targets", { values: nums });
      // reload so every view picks up the new targets
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-carbon-950/80 px-6 py-12" onMouseDown={onClose}>
      <div className="panel w-full max-w-lg p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-baseline justify-between border-b border-carbon-700 pb-2">
          <h2 className="label text-sm text-bone-100">Training targets</h2>
          <button onClick={onClose} className="data text-xs text-bone-300 hover:text-bone-100">
            ✕
          </button>
        </div>
        {!values ? (
          <p className="data text-xs text-bone-300">Loading…</p>
        ) : (
          <div className="space-y-4">
            {FIELDS.map((g) => (
              <div key={g.group}>
                <div className="label mb-1.5 text-[11px] text-signal">{g.group}</div>
                <div className="grid grid-cols-2 gap-2">
                  {g.items.map((f) => (
                    <label key={f.key} className="block">
                      <span className="data mb-1 block text-[10px] text-bone-300">{f.label}</span>
                      <input
                        type="number"
                        step={f.step ?? "any"}
                        value={values[f.key] ?? ""}
                        onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                        className="data w-full border border-carbon-500 bg-carbon-800 px-2 py-1 text-xs text-bone-50 outline-none focus:border-signal"
                      />
                    </label>
                  ))}
                </div>
              </div>
            ))}
            {error && <p className="data text-xs text-hard">{error}</p>}
            <div className="flex items-center gap-2 border-t border-carbon-700 pt-3">
              <button
                onClick={save}
                disabled={busy}
                className="label border border-signal bg-signal/10 px-4 py-2 text-xs text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
              >
                {busy ? "Saving…" : "Save"}
              </button>
              <button onClick={onClose} className="label border border-carbon-500 px-4 py-2 text-xs text-bone-300 hover:border-bone-300">
                Cancel
              </button>
              <span className="data ml-auto text-[10px] text-carbon-500">HR zones come from Garmin</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
