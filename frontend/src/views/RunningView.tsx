import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppConfig, RunRow, RunWeek, fmtDay, fmtKm, fmtPace, useApi } from "../api";
import { Empty, Panel, Section, Stat, tooltipStyle } from "../components/ui";

const dayTick = (iso: string) => fmtDay(iso);

function MiniTrend({
  runs,
  dataKey,
  color,
  unit,
  domain,
}: {
  runs: RunRow[];
  dataKey: keyof RunRow;
  color: string;
  unit: string;
  domain?: [number | string, number | string];
}) {
  const has = runs.some((r) => r[dataKey] != null);
  if (!has)
    return <Empty>Not recorded on any synced run (needs a compatible sensor).</Empty>;
  return (
    <ResponsiveContainer width="100%" height={150}>
      <ComposedChart data={runs} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <XAxis dataKey="start_time_local" tickFormatter={dayTick} axisLine={false} tickLine={false} minTickGap={40} />
        <YAxis domain={domain ?? ["auto", "auto"]} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(d) => new Date(String(d)).toLocaleDateString()}
          formatter={(v) => [`${Number(v).toFixed(1)} ${unit}`, ""]}
        />
        <Line dataKey={dataKey as string} stroke={color} strokeWidth={1.8} dot={{ r: 2.5, fill: color }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function RunningView() {
  const { data: runs } = useApi<RunRow[]>("/api/running/trends");
  const { data: weeks } = useApi<RunWeek[]>("/api/running/weekly");
  const { data: config } = useApi<AppConfig>("/api/config");

  const [bandLow, bandHigh] = config?.targets.cadence_band ?? [165, 175];
  const latest = runs && runs.length ? runs[runs.length - 1] : null;

  return (
    <div>
      <Section index="01" title="Latest run" aside={latest ? new Date(latest.start_time_local).toLocaleString() : undefined}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <Panel delay={0}>
            <Stat label="Distance" value={fmtKm(latest?.distance_m)} unit="km" sub={latest?.name ?? undefined} />
          </Panel>
          <Panel delay={50}>
            <Stat label="Pace" value={fmtPace(latest?.pace_s_per_km)} unit="/km" sub={latest?.avg_hr ? `${Math.round(latest.avg_hr)} bpm avg` : undefined} />
          </Panel>
          <Panel delay={100}>
            <Stat
              label="Cadence"
              value={latest?.avg_cadence_spm != null ? String(Math.round(latest.avg_cadence_spm)) : "—"}
              unit="spm"
              tone={
                latest?.avg_cadence_spm == null
                  ? "text-bone-50"
                  : latest.avg_cadence_spm >= bandLow && latest.avg_cadence_spm <= bandHigh
                    ? "text-easy"
                    : "text-ride"
              }
              sub={`target ${bandLow}–${bandHigh}`}
            />
          </Panel>
          <Panel delay={150}>
            <Stat
              label="Decoupling"
              value={latest?.aerobic_decoupling_pct != null ? latest.aerobic_decoupling_pct.toFixed(1) : "—"}
              unit="%"
              tone={
                latest?.aerobic_decoupling_pct == null
                  ? "text-bone-50"
                  : latest.aerobic_decoupling_pct <= 5
                    ? "text-easy"
                    : "text-hard"
              }
              sub="pace:HR drift · ≤5% aerobic"
            />
          </Panel>
          <Panel delay={200}>
            <Stat label="Run power" value={latest?.norm_power_w != null ? String(Math.round(latest.norm_power_w)) : "—"} unit="W NP" sub={latest?.vo2max ? `VO₂max ${latest.vo2max}` : undefined} />
          </Panel>
        </div>
      </Section>

      <Section index="02" title="Cadence" aside={`band ${bandLow}–${bandHigh} spm`}>
        <Panel delay={80}>
          {runs && runs.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={runs} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="start_time_local" tickFormatter={dayTick} axisLine={false} tickLine={false} minTickGap={40} />
                <YAxis domain={[150, 190]} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={(d) => new Date(String(d)).toLocaleDateString()}
                  formatter={(v, name) => [name === "cadence" ? `${Math.round(Number(v))} spm` : String(v), name]}
                />
                <ReferenceArea y1={bandLow} y2={bandHigh} fill="#7fb069" fillOpacity={0.1} stroke="#7fb069" strokeOpacity={0.4} strokeDasharray="4 4" />
                <Line dataKey="avg_cadence_spm" name="cadence" stroke="#f0532f" strokeWidth={1.8} dot={{ r: 3, fill: "#f0532f" }} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>No runs synced yet.</Empty>
          )}
        </Panel>
      </Section>

      <Section index="03" title="Running dynamics">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Panel title="Vertical oscillation" note="cm · lower = calmer" delay={60}>
            <MiniTrend runs={runs ?? []} dataKey="avg_vertical_osc_cm" color="#3fbdd8" unit="cm" />
          </Panel>
          <Panel title="Ground contact time" note="ms · lower = snappier" delay={120}>
            <MiniTrend runs={runs ?? []} dataKey="avg_gct_ms" color="#e8a33d" unit="ms" />
          </Panel>
          <Panel title="Vertical ratio" note="% · osc ÷ stride" delay={180}>
            <MiniTrend runs={runs ?? []} dataKey="avg_vertical_ratio_pct" color="#7fb069" unit="%" />
          </Panel>
          <Panel title="GCT balance L/R" note="needs HRM strap" delay={240}>
            <MiniTrend runs={runs ?? []} dataKey="avg_gct_balance_pct" color="#e4572e" unit="%" />
          </Panel>
        </div>
      </Section>

      <Section index="04" title="Aerobic decoupling per run" aside="≤5% = aerobically stable">
        <Panel delay={100}>
          {runs && runs.some((r) => r.aerobic_decoupling_pct != null) ? (
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={runs} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <XAxis dataKey="start_time_local" tickFormatter={dayTick} axisLine={false} tickLine={false} minTickGap={40} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => new Date(String(d)).toLocaleDateString()} />
                <ReferenceLine y={5} stroke="#e4572e" strokeDasharray="5 5" />
                <ReferenceLine y={0} stroke="#57503f" />
                <Bar dataKey="aerobic_decoupling_pct" name="decoupling %" fill="#f0532f" fillOpacity={0.75} maxBarSize={18} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>
              Decoupling is computed from HR + grade-adjusted pace streams once run details sync
              (runs over 20 min only).
            </Empty>
          )}
        </Panel>
      </Section>

      <Section index="05" title="Weekly volume & pace/HR">
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="km per week" delay={80}>
            {weeks && weeks.length ? (
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={weeks} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="week" tickFormatter={dayTick} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={(m) => `${Math.round(Number(m) / 1000)}`} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${(Number(v) / 1000).toFixed(1)} km`, ""]} />
                  <Bar dataKey="distance_m" fill="#f0532f" fillOpacity={0.8} maxBarSize={28} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
          <Panel title="Weekly pace vs HR" note="line = pace · dots = avg HR" delay={140}>
            {weeks && weeks.length ? (
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={weeks} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="week" tickFormatter={dayTick} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="pace" tickFormatter={(v) => fmtPace(Number(v))} domain={["auto", "auto"]} reversed axisLine={false} tickLine={false} />
                  <YAxis yAxisId="hr" orientation="right" domain={[100, 190]} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v, name) => [name === "pace" ? `${fmtPace(Number(v))}/km` : `${Math.round(Number(v))} bpm`, name]}
                  />
                  <Line yAxisId="pace" dataKey="pace_s_per_km" name="pace" stroke="#e8e2d6" strokeWidth={1.8} dot={false} />
                  <Scatter yAxisId="hr" dataKey="avg_hr" name="HR" fill="#e4572e" />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
        </div>
      </Section>
    </div>
  );
}
