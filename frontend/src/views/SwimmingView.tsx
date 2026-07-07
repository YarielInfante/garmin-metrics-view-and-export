import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtDay, fmtPace, useApi } from "../api";
import { Empty, Panel, Section, Stat, tooltipStyle } from "../components/ui";

interface SwimRow {
  activity_id: number;
  name: string;
  start_time_local: string;
  distance_m: number;
  duration_s: number;
  avg_hr: number | null;
  pool_length_m: number | null;
  active_lengths: number | null;
  avg_swolf: number | null;
  avg_strokes_per_length: number | null;
  avg_swim_cadence: number | null;
  fastest_100m_s: number | null;
  pace_per_100m_s: number | null;
}

interface SwimSession {
  activity: Record<string, unknown>;
  intervals: {
    interval_index: number;
    interval_type: string;
    duration_s: number;
    distance_m: number;
    pace_per_100m_s: number | null;
    num_lengths: number | null;
    avg_strokes_per_length: number | null;
    avg_swolf: number | null;
    avg_hr: number | null;
  }[];
  lengths: {
    interval_index: number;
    length_index: number;
    duration_s: number;
    pace_per_100m_s: number | null;
    strokes: number | null;
    swolf: number | null;
    avg_hr: number | null;
    stroke_type: string | null;
  }[];
}

const INTERVAL_SHADES = ["#3fbdd8", "#2d8fa6", "#57cfe8", "#1f6f82", "#6fd8ec"];

export function SwimmingView() {
  const { data: swims } = useApi<SwimRow[]>("/api/swimming/trends");
  const latest = swims && swims.length ? swims[swims.length - 1] : null;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const sessionId = selectedId ?? latest?.activity_id ?? null;
  const { data: session } = useApi<SwimSession>(
    sessionId ? `/api/swimming/sessions/${sessionId}` : null,
  );

  const lengths = sessionId && session ? session.lengths : [];

  return (
    <div>
      <Section index="01" title="Latest swim" aside={latest ? new Date(latest.start_time_local).toLocaleString() : undefined}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <Panel delay={0}>
            <Stat
              label="Distance"
              value={latest?.distance_m != null ? String(Math.round(latest.distance_m)) : "—"}
              unit="m"
              sub={latest?.pool_length_m ? `${latest.pool_length_m} m pool` : undefined}
            />
          </Panel>
          <Panel delay={50}>
            <Stat label="Pace" value={fmtPace(latest?.pace_per_100m_s)} unit="/100m" sub={latest?.fastest_100m_s ? `best 100m ${fmtPace(latest.fastest_100m_s)}` : undefined} />
          </Panel>
          <Panel delay={100}>
            <Stat label="SWOLF" value={latest?.avg_swolf != null ? String(Math.round(latest.avg_swolf)) : "—"} sub="lower = more efficient" />
          </Panel>
          <Panel delay={150}>
            <Stat
              label="Strokes / length"
              value={latest?.avg_strokes_per_length != null ? latest.avg_strokes_per_length.toFixed(1) : "—"}
              sub={latest?.avg_swim_cadence ? `${Math.round(latest.avg_swim_cadence)} str/min` : undefined}
            />
          </Panel>
          <Panel delay={200}>
            <Stat label="Lengths" value={latest?.active_lengths != null ? String(latest.active_lengths) : "—"} sub={latest?.avg_hr ? `${Math.round(latest.avg_hr)} bpm avg` : undefined} />
          </Panel>
        </div>
      </Section>

      <Section index="02" title="Trends across sessions" aside="per session">
        {swims && swims.length ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Panel title="Pace / 100m" note="lower = faster" delay={60}>
              <ResponsiveContainer width="100%" height={170}>
                <ComposedChart data={swims} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <XAxis dataKey="start_time_local" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                  <YAxis reversed domain={["auto", "auto"]} tickFormatter={(v) => fmtPace(Number(v))} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => new Date(String(d)).toLocaleDateString()} formatter={(v) => [`${fmtPace(Number(v))}/100m`, ""]} />
                  <Line dataKey="pace_per_100m_s" stroke="#3fbdd8" strokeWidth={1.8} dot={{ r: 3, fill: "#3fbdd8" }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </Panel>
            <Panel title="SWOLF" delay={120}>
              <ResponsiveContainer width="100%" height={170}>
                <ComposedChart data={swims} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <XAxis dataKey="start_time_local" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                  <YAxis domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => new Date(String(d)).toLocaleDateString()} />
                  <Line dataKey="avg_swolf" name="SWOLF" stroke="#e8a33d" strokeWidth={1.8} dot={{ r: 3, fill: "#e8a33d" }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </Panel>
            <Panel title="Strokes per length" delay={180}>
              <ResponsiveContainer width="100%" height={170}>
                <ComposedChart data={swims} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <XAxis dataKey="start_time_local" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                  <YAxis domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => new Date(String(d)).toLocaleDateString()} />
                  <Line dataKey="avg_strokes_per_length" name="strokes" stroke="#7fb069" strokeWidth={1.8} dot={{ r: 3, fill: "#7fb069" }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </Panel>
          </div>
        ) : (
          <Empty>No pool swims synced yet.</Empty>
        )}
      </Section>

      <Section
        index="03"
        title="Within-session durability"
        aside="per length — watch the back half"
      >
        <Panel delay={100}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="label text-[11px] text-bone-300">Session</span>
            <select
              className="data border border-carbon-500 bg-carbon-800 px-2 py-1 text-xs text-bone-50"
              value={sessionId ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}
            >
              {(swims ?? []).slice().reverse().map((s) => (
                <option key={s.activity_id} value={s.activity_id}>
                  {new Date(s.start_time_local).toLocaleDateString()} — {Math.round(s.distance_m)} m
                </option>
              ))}
            </select>
            {session && sessionId && (
              <span className="data ml-auto text-[10px] text-carbon-500">
                {(() => {
                  const n = session.intervals.filter((i) => i.interval_type === "ACTIVE").length;
                  return `${n} interval${n === 1 ? "" : "s"} · ${lengths.length} length${lengths.length === 1 ? "" : "s"} · shade = interval`;
                })()}
              </span>
            )}
          </div>
          {lengths.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={lengths} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="length_index" axisLine={false} tickLine={false} label={{ value: "length #", position: "insideBottomRight", offset: -2, style: { fill: "#57503f", fontSize: 10 } }} />
                <YAxis yAxisId="swolf" axisLine={false} tickLine={false} domain={["auto", "auto"]} />
                <YAxis yAxisId="pace" orientation="right" reversed tickFormatter={(v) => fmtPace(Number(v))} domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v, name) => [name === "pace" ? `${fmtPace(Number(v))}/100m` : String(v), name]}
                  labelFormatter={(i) => `length ${i}`}
                />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Bar yAxisId="swolf" dataKey="swolf" name="SWOLF">
                  {lengths.map((l, i) => (
                    <Cell key={i} fill={INTERVAL_SHADES[(l.interval_index - 1) % INTERVAL_SHADES.length]} />
                  ))}
                </Bar>
                <Line yAxisId="swolf" dataKey="strokes" name="strokes" stroke="#7fb069" strokeWidth={1.6} dot={{ r: 2.5, fill: "#7fb069" }} />
                <Line yAxisId="pace" dataKey="pace_per_100m_s" name="pace" stroke="#e8e2d6" strokeWidth={1.8} dot={{ r: 2.5, fill: "#e8e2d6" }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>
              Per-length data appears once this session's details are synced. If this is an
              open-water swim there are no lengths.
            </Empty>
          )}
        </Panel>
      </Section>
    </div>
  );
}
