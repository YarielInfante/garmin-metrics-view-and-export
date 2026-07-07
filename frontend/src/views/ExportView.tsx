import { useEffect, useMemo, useRef, useState } from "react";
import { ExportCoverage, RawExport, getJson, useApi } from "../api";
import { Empty, Panel, Section, Stat } from "../components/ui";

// local-date helpers (avoid toISOString()'s UTC shift near midnight in GMT-4)
const toISO = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseISO = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
};
const todayISO = () => toISO(new Date());
const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toISO(d);
};

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function DatePicker({
  value,
  placeholder,
  min,
  max,
  onPick,
}: {
  value: string;
  placeholder?: string;
  min?: string;
  max?: string;
  onPick: (iso: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => (value ? parseISO(value) : new Date()));
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (value) setView(parseISO(value));
  }, [value]);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const y = view.getFullYear();
  const m = view.getMonth();
  const firstDow = (new Date(y, m, 1).getDay() + 6) % 7; // Monday-first
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const today = todayISO();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`data flex w-36 items-center justify-between border px-2 py-1 text-xs transition-colors ${
          open ? "border-signal text-bone-50" : "border-carbon-500 text-bone-50 hover:border-bone-300"
        } bg-carbon-800`}
      >
        <span className={value ? "" : "text-carbon-500"}>{value || placeholder || "—"}</span>
        <span className="text-bone-300">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-60 border border-carbon-500 bg-carbon-900 p-3 shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <button onClick={() => setView(new Date(y, m - 1, 1))} className="px-2 text-lg leading-none text-bone-300 hover:text-signal">
              ‹
            </button>
            <span className="label text-[11px] text-bone-100">
              {MONTHS[m]} {y}
            </span>
            <button onClick={() => setView(new Date(y, m + 1, 1))} className="px-2 text-lg leading-none text-bone-300 hover:text-signal">
              ›
            </button>
          </div>
          <div className="grid grid-cols-7 gap-0.5">
            {WEEKDAYS.map((w) => (
              <div key={w} className="label pb-1 text-center text-[9px] text-carbon-500">
                {w}
              </div>
            ))}
            {cells.map((d, i) => {
              if (d === null) return <div key={i} />;
              const iso = toISO(new Date(y, m, d));
              const selected = iso === value;
              const off = (min && iso < min) || (max && iso > max);
              return (
                <button
                  key={i}
                  disabled={!!off}
                  onClick={() => {
                    onPick(iso);
                    setOpen(false);
                  }}
                  className={`data h-7 text-[11px] transition-colors ${
                    selected
                      ? "bg-signal font-bold text-carbon-950"
                      : off
                        ? "cursor-default text-carbon-700"
                        : iso === today
                          ? "text-signal hover:bg-carbon-700"
                          : "text-bone-100 hover:bg-carbon-700"
                  }`}
                >
                  {d}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

type Preset = { key: string; label: string; start: () => string | "" };
const PRESETS: Preset[] = [
  { key: "today", label: "Today", start: () => todayISO() },
  { key: "7d", label: "7 days", start: () => daysAgo(7) },
  { key: "4w", label: "4 weeks", start: () => daysAgo(28) },
  { key: "90d", label: "90 days", start: () => daysAgo(90) },
  { key: "all", label: "All", start: () => "" },
];

const fmtBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

export function ExportView() {
  const { data: coverage } = useApi<ExportCoverage>("/api/export/coverage");
  const [preset, setPreset] = useState("4w");
  const [start, setStart] = useState(daysAgo(28));
  const [end, setEnd] = useState(todayISO());
  const [includeDetails, setIncludeDetails] = useState(false);
  const [data, setData] = useState<RawExport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    const p = new URLSearchParams();
    if (start) p.set("start", start);
    if (end) p.set("end", end);
    if (includeDetails) p.set("include_details", "1");
    getJson<RawExport>(`/api/export/raw?${p.toString()}`)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [start, end, includeDetails]);

  const applyPreset = (pr: Preset) => {
    setPreset(pr.key);
    setStart(pr.start());
    setEnd(todayISO());
  };

  const json = useMemo(() => (data ? JSON.stringify(data, null, 2) : ""), [data]);
  const bytes = useMemo(() => new Blob([json]).size, [json]);

  const copy = async () => {
    await navigator.clipboard.writeText(json).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `garmin-export_${start || "all"}_${end}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <Section
        index="01"
        title="Export range"
        aside={coverage?.earliest ? `archive ${coverage.earliest} → ${coverage.latest}` : undefined}
      >
        <Panel delay={0} className="relative z-30">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <div className="label mb-1.5 text-[11px] text-bone-300">Quick range</div>
              <div className="flex gap-1">
                {PRESETS.map((pr) => (
                  <button
                    key={pr.key}
                    onClick={() => applyPreset(pr)}
                    className={`label border px-3 py-1.5 text-[11px] transition-colors ${
                      preset === pr.key
                        ? "border-signal text-signal"
                        : "border-carbon-500 text-bone-300 hover:border-bone-300 hover:text-bone-100"
                    }`}
                  >
                    {pr.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="label mb-1.5 text-[11px] text-bone-300">From</div>
              <DatePicker
                value={start}
                placeholder="earliest"
                max={end || todayISO()}
                onPick={(v) => {
                  setStart(v);
                  setPreset("custom");
                }}
              />
            </div>
            <div>
              <div className="label mb-1.5 text-[11px] text-bone-300">To</div>
              <DatePicker
                value={end}
                min={start || undefined}
                max={todayISO()}
                onPick={(v) => {
                  setEnd(v);
                  setPreset("custom");
                }}
              />
            </div>
            <label className="data flex cursor-pointer items-center gap-2 text-xs text-bone-300">
              <input
                type="checkbox"
                checked={includeDetails}
                onChange={(e) => setIncludeDetails(e.target.checked)}
                className="accent-signal"
              />
              include per-second detail (large)
            </label>
          </div>
        </Panel>
      </Section>

      <Section index="02" title="Bundle" aside={data ? `raw JSON · ${data.include_details ? "with details" : "summaries"}` : undefined}>
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <Panel delay={40}>
            <Stat label="Size" value={loading ? "…" : fmtBytes(bytes)} sub={bytes > 400_000 ? "large — download instead of paste" : "paste-ready"} tone={bytes > 400_000 ? "text-ride" : "text-bone-50"} />
          </Panel>
          <Panel delay={80}>
            <Stat label="Activities" value={data ? String(data.coverage.activities) : "—"} />
          </Panel>
          <Panel delay={120}>
            <Stat label="Wellness days" value={data ? String(data.coverage.days) : "—"} />
          </Panel>
          <Panel delay={160}>
            <Stat label="Config" value={data ? String(Object.values(data.athlete_config).filter(Boolean).length) : "—"} unit={data ? `/${Object.keys(data.athlete_config).length}` : undefined} sub="thresholds & zones" />
          </Panel>
        </div>

        <div className="mb-3 flex items-center gap-2">
          <button
            onClick={copy}
            disabled={!json}
            className="label border border-signal bg-signal/10 px-4 py-2 text-xs text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
          >
            {copied ? "Copied ✓" : "Copy for Claude"}
          </button>
          <button
            onClick={download}
            disabled={!json}
            className="label border border-carbon-500 px-4 py-2 text-xs text-bone-100 transition-colors hover:border-bone-300 disabled:opacity-40"
          >
            Download .json
          </button>
          <span className="data ml-auto text-[10px] text-carbon-500">
            stays on this machine until you copy or download
          </span>
        </div>

        <Panel delay={200}>
          {error ? (
            <Empty>Couldn't build the export: {error}</Empty>
          ) : loading && !data ? (
            <Empty>Assembling…</Empty>
          ) : data && (data.coverage.activities || data.coverage.days) ? (
            <pre className="data max-h-[28rem] overflow-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-bone-100">
              {json.length > 20000 ? json.slice(0, 20000) + "\n\n… preview truncated — Copy / Download for the full bundle" : json}
            </pre>
          ) : (
            <Empty>
              No data in this range yet. Activities and wellness populate as the background sync runs — check
              the archive dates above.
            </Empty>
          )}
        </Panel>
      </Section>
    </div>
  );
}
