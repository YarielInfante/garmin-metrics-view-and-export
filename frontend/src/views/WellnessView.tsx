import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { WellnessDay, fmtDay, useApi } from "../api";
import { Empty, Panel, Section, Stat, tooltipStyle } from "../components/ui";

export function WellnessView() {
  const { data } = useApi<WellnessDay[]>("/api/wellness/daily");
  const days = data ?? [];
  const today = days.length ? days[days.length - 1] : null;

  const sleepHours = (d: WellnessDay) => (d.sleep_s != null ? d.sleep_s / 3600 : null);

  return (
    <div>
      <Section index="01" title="This morning" aside={today?.date}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Panel delay={0}>
            <Stat
              label="HRV last night"
              value={today?.hrv_last_night_ms != null ? String(Math.round(today.hrv_last_night_ms)) : "—"}
              unit="ms"
              tone={
                today?.hrv_last_night_ms == null || today?.hrv_weekly_avg_ms == null
                  ? "text-bone-50"
                  : today.hrv_last_night_ms >= today.hrv_weekly_avg_ms
                    ? "text-easy"
                    : "text-ride"
              }
              sub={today?.hrv_weekly_avg_ms ? `7d avg ${Math.round(today.hrv_weekly_avg_ms)} ms` : undefined}
            />
          </Panel>
          <Panel delay={60}>
            <Stat label="Resting HR" value={today?.resting_hr != null ? String(Math.round(today.resting_hr)) : "—"} unit="bpm" />
          </Panel>
          <Panel delay={120}>
            <Stat
              label="Sleep"
              value={sleepHours(today ?? ({} as WellnessDay)) != null ? sleepHours(today!)!.toFixed(1) : "—"}
              unit="h"
              sub={today?.sleep_score != null ? `score ${Math.round(today.sleep_score)}` : undefined}
            />
          </Panel>
          <Panel delay={180}>
            <Stat
              label="Body battery"
              value={today?.bb_high != null ? `${Math.round(today.bb_low ?? 0)}–${Math.round(today.bb_high)}` : "—"}
              sub={today?.bb_charged != null ? `+${Math.round(today.bb_charged)} / −${Math.round(today.bb_drained ?? 0)}` : undefined}
            />
          </Panel>
        </div>
      </Section>

      <Section index="02" title="HRV & resting HR" aside="overnight averages">
        <Panel delay={80}>
          {days.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDay} axisLine={false} tickLine={false} minTickGap={30} />
                <YAxis yAxisId="hrv" domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                <YAxis yAxisId="rhr" orientation="right" domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Area yAxisId="hrv" dataKey="hrv_last_night_ms" name="HRV (ms)" stroke="#7fb069" fill="#7fb069" fillOpacity={0.12} connectNulls />
                <Line yAxisId="hrv" dataKey="hrv_weekly_avg_ms" name="HRV 7d avg" stroke="#7fb069" strokeDasharray="5 4" dot={false} connectNulls />
                <Line yAxisId="rhr" dataKey="resting_hr" name="RHR (bpm)" stroke="#e4572e" strokeWidth={1.8} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>Wellness syncs daily once tokens are set up.</Empty>
          )}
        </Panel>
      </Section>

      <Section index="03" title="Sleep">
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Stages" note="hours per night" delay={100}>
            {days.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="date" tickFormatter={fmtDay} axisLine={false} tickLine={false} minTickGap={30} />
                  <YAxis tickFormatter={(s) => `${Math.round(Number(s) / 3600)}h`} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v) => [`${(Number(v) / 3600).toFixed(1)} h`, ""]}
                  />
                  <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                  <Bar dataKey="sleep_deep_s" stackId="s" name="deep" fill="#2d5f8a" />
                  <Bar dataKey="sleep_light_s" stackId="s" name="light" fill="#3fbdd8" />
                  <Bar dataKey="sleep_rem_s" stackId="s" name="REM" fill="#7fb069" />
                  <Bar dataKey="sleep_awake_s" stackId="s" name="awake" fill="#57503f" />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
          <Panel title="Sleep score & readiness" delay={160}>
            {days.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="date" tickFormatter={fmtDay} axisLine={false} tickLine={false} minTickGap={30} />
                  <YAxis domain={[0, 100]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                  <Line dataKey="sleep_score" name="sleep score" stroke="#3fbdd8" strokeWidth={1.8} dot={false} connectNulls />
                  <Line dataKey="readiness_score" name="readiness" stroke="#ff6b1a" strokeWidth={1.8} dot={false} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
        </div>
      </Section>

      <Section index="04" title="Body battery & stress">
        <Panel delay={120}>
          {days.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <XAxis dataKey="date" tickFormatter={fmtDay} axisLine={false} tickLine={false} minTickGap={30} />
                <YAxis domain={[0, 100]} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Area dataKey="bb_high" name="BB high" stroke="#3fbdd8" fill="#3fbdd8" fillOpacity={0.1} dot={false} connectNulls />
                <Line dataKey="bb_low" name="BB low" stroke="#3fbdd8" strokeDasharray="4 4" dot={false} connectNulls />
                <Line dataKey="stress_avg" name="avg stress" stroke="#e8a33d" strokeWidth={1.6} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>—</Empty>
          )}
        </Panel>
      </Section>
    </div>
  );
}
