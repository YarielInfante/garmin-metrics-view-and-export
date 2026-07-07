import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppConfig, IntensityWeek, LoadDay, SummaryWeek, fmtDay, fmtDur, useApi } from "../api";
import { Empty, Panel, Section, Stat, tooltipStyle } from "../components/ui";

const SPORT_COLOR: Record<string, string> = {
  run: "#f0532f",
  ride: "#e8a33d",
  swim: "#3fbdd8",
  strength: "#8a8274",
  walk: "#57503f",
  mobility: "#57503f",
  other: "#3a3630",
};

export function LoadView() {
  const { data: load } = useApi<{ days: LoadDay[]; acwr_range: [number, number] }>("/api/load/daily");
  const { data: intensity } = useApi<{ weeks: IntensityWeek[]; easy_target_pct: number; easy_zone_max: number }>(
    "/api/intensity/weekly",
  );
  const { data: summary } = useApi<SummaryWeek[]>("/api/summary/weekly");
  const { data: config } = useApi<AppConfig>("/api/config");

  const days = load?.days ?? [];
  const today = days.length ? days[days.length - 1] : null;
  const [acwrLow, acwrHigh] = load?.acwr_range ?? [0.8, 1.3];
  const acwr = today?.acwr_garmin ?? today?.acwr_local ?? null;

  const weeks = intensity?.weeks ?? [];
  const thisWeek = weeks.length ? weeks[weeks.length - 1] : null;

  // pivot multisport summary into week rows
  const summaryWeeks = Object.values(
    (summary ?? []).reduce<Record<string, Record<string, number | string>>>((acc, r) => {
      const w = String(r.week);
      acc[w] = acc[w] ?? { week: w };
      acc[w][r.sport] = r.duration_s;
      return acc;
    }, {}),
  );

  // prefer running zones, then a DEFAULT/global config, then whatever exists
  const zoneCfg =
    config?.hr_zones?.find((z) => z.sport === "RUNNING") ??
    config?.hr_zones?.find((z) => z.sport === "DEFAULT") ??
    config?.hr_zones?.[0];

  return (
    <div>
      <Section index="01" title="Today" aside={today?.date}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Panel delay={0}>
            <Stat
              label="ACWR"
              value={acwr != null ? acwr.toFixed(2) : "—"}
              tone={
                acwr == null
                  ? "text-bone-50"
                  : acwr >= acwrLow && acwr <= acwrHigh
                    ? "text-easy"
                    : "text-hard"
              }
              sub={today?.acwr_status ?? `healthy ${acwrLow}–${acwrHigh}`}
            />
          </Panel>
          <Panel delay={60}>
            <Stat label="Acute load · 7d" value={String(Math.round(today?.acute_garmin ?? today?.acute_local ?? 0))} sub="vs chronic baseline" />
          </Panel>
          <Panel delay={120}>
            <Stat
              label="Readiness"
              value={today?.readiness_score != null ? String(Math.round(today.readiness_score)) : "—"}
              unit="/100"
              tone={
                today?.readiness_score == null
                  ? "text-bone-50"
                  : today.readiness_score >= 60
                    ? "text-easy"
                    : today.readiness_score >= 35
                      ? "text-ride"
                      : "text-hard"
              }
              sub={today?.readiness_level ?? undefined}
            />
          </Panel>
          <Panel delay={180}>
            <Stat
              label="Easy this week"
              value={thisWeek?.easy_pct != null ? thisWeek.easy_pct.toFixed(0) : "—"}
              unit="%"
              tone={
                thisWeek?.easy_pct == null
                  ? "text-bone-50"
                  : thisWeek.easy_pct >= (intensity?.easy_target_pct ?? 80)
                    ? "text-easy"
                    : "text-hard"
              }
              sub={`target ≥ ${intensity?.easy_target_pct ?? 80}% in Z1–Z${intensity?.easy_zone_max ?? 2}`}
            />
          </Panel>
        </div>
      </Section>

      <Section index="02" title="Training load — acute vs chronic" aside="Garmin load units">
        <Panel delay={80}>
          {days.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDay} minTickGap={40} axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => String(d)} />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Bar dataKey="daily_load" name="daily" fill="#2a2620" stroke="#57503f" strokeWidth={0.5} />
                <Line dataKey={(d: LoadDay) => d.acute_garmin ?? d.acute_local} name="acute (7d)" stroke="#ff6b1a" dot={false} strokeWidth={2} />
                <Line dataKey={(d: LoadDay) => d.chronic_garmin ?? d.chronic_local} name="chronic (28d)" stroke="#7fb069" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>No activities synced yet.</Empty>
          )}
        </Panel>
        <div className="mt-4">
          <Panel title="ACWR ratio" note={`band ${acwrLow}–${acwrHigh} = healthy`} delay={140}>
            {days.length ? (
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="date" tickFormatter={fmtDay} minTickGap={40} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 2]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <ReferenceArea y1={acwrLow} y2={acwrHigh} fill="#7fb069" fillOpacity={0.09} stroke="#7fb069" strokeOpacity={0.35} strokeDasharray="4 4" />
                  <Line dataKey={(d: LoadDay) => d.acwr_garmin ?? d.acwr_local} name="ACWR" stroke="#e8e2d6" dot={false} strokeWidth={1.6} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>ACWR appears once activities and Garmin training status are synced.</Empty>
            )}
          </Panel>
        </div>
      </Section>

      <Section
        index="03"
        title="80/20 intensity distribution"
        aside={zoneCfg ? `Garmin zones · Z2 ends ${zoneCfg.z3_floor - 1} bpm` : undefined}
      >
        <Panel delay={100}>
          {weeks.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={weeks} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <XAxis dataKey="week" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(s) => `${Math.round(s / 3600)}h`} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtDur(Number(v))} />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Bar dataKey="z1" stackId="z" name="Z1" fill="#5d7a5a" />
                <Bar dataKey="z2" stackId="z" name="Z2" fill="#7fb069" />
                <Bar dataKey="z3" stackId="z" name="Z3" fill="#e8c547" />
                <Bar dataKey="z4" stackId="z" name="Z4" fill="#e8873d" />
                <Bar dataKey="z5" stackId="z" name="Z5" fill="#e4572e" />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>Zone data lands with the first synced activities.</Empty>
          )}
        </Panel>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Panel title="% easy (Z1–Z2) per week" note="dashed = target" delay={160}>
            {weeks.length ? (
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={weeks} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="week" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <ReferenceLine y={intensity?.easy_target_pct ?? 80} stroke="#7fb069" strokeDasharray="5 5" />
                  <Area dataKey="easy_pct" name="easy %" stroke="#7fb069" fill="#7fb069" fillOpacity={0.12} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
          <Panel title="Weekly multisport hours" delay={220}>
            {summaryWeeks.length ? (
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={summaryWeeks} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis dataKey="week" tickFormatter={(w) => fmtDay(String(w))} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={(s) => `${Math.round(Number(s) / 3600)}h`} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtDur(Number(v))} />
                  {Object.keys(SPORT_COLOR).map((sport) => (
                    <Bar key={sport} dataKey={sport} stackId="s" name={sport} fill={SPORT_COLOR[sport]} />
                  ))}
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
