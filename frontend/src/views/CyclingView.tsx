import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtDay, fmtDur, fmtKm, useApi } from "../api";
import { Empty, Panel, Section, Stat, tooltipStyle } from "../components/ui";

interface Ride {
  activity_id: number;
  name: string;
  start_time_local: string;
  distance_m: number;
  duration_s: number;
  avg_speed_ms: number | null;
  max_speed_ms: number | null;
  avg_hr: number | null;
  elevation_gain_m: number | null;
  avg_power_w: number | null;
  norm_power_w: number | null;
  training_load: number | null;
}

interface CyclingData {
  rides: Ride[];
  ftp_history: { calendar_date: string; value: number }[];
  current_ftp_w: number | null;
  ftp_source: "garmin" | "config_fallback" | "none";
  weight_kg: number | null;
  w_per_kg: number | null;
  power_duration_curve: { duration_s: number; best_w: number }[];
  has_ride_power: boolean;
}

const kmh = (ms: number | null | undefined) => (ms == null ? null : ms * 3.6);

const fmtDurShort = (s: number) =>
  s >= 3600 ? `${s / 3600}h` : s >= 60 ? `${s / 60}m` : `${s}s`;

export function CyclingView() {
  const { data } = useApi<CyclingData>("/api/cycling/trends");
  const rides = (data?.rides ?? []).map((r) => ({
    ...r,
    avg_kmh: kmh(r.avg_speed_ms),
    max_kmh: kmh(r.max_speed_ms),
  }));
  const latest = rides.length ? rides[rides.length - 1] : null;

  return (
    <div>
      <Section
        index="01"
        title="Bike fitness"
        aside={
          data?.ftp_source === "garmin"
            ? "FTP from Garmin"
            : data?.ftp_source === "config_fallback"
              ? "FTP fallback from config"
              : undefined
        }
      >
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Panel delay={0}>
            <Stat
              label="FTP"
              value={data?.current_ftp_w != null ? String(Math.round(data.current_ftp_w)) : "—"}
              unit="W"
              sub={
                data?.ftp_source === "garmin"
                  ? "Garmin estimate"
                  : data?.ftp_source === "config_fallback"
                    ? "config fallback"
                    : "no rides or FTP yet"
              }
            />
          </Panel>
          <Panel delay={60}>
            <Stat label="W / kg" value={data?.w_per_kg != null ? data.w_per_kg.toFixed(2) : "—"} sub={data?.weight_kg ? `at ${data.weight_kg.toFixed(1)} kg` : undefined} />
          </Panel>
          <Panel delay={120}>
            <Stat label="Latest ride" value={fmtKm(latest?.distance_m)} unit="km" sub={latest ? fmtDur(latest.duration_s) : undefined} />
          </Panel>
          <Panel delay={180}>
            <Stat
              label="Avg speed"
              value={latest?.avg_kmh != null ? latest.avg_kmh.toFixed(1) : "—"}
              unit="km/h"
              sub={latest?.avg_hr ? `${Math.round(latest.avg_hr)} bpm avg` : undefined}
            />
          </Panel>
        </div>
      </Section>

      <Section index="02" title="Speed & distance progression" aside="per ride">
        <Panel delay={80}>
          {rides.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={rides} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="start_time_local" tickFormatter={fmtDay} axisLine={false} tickLine={false} minTickGap={40} />
                <YAxis yAxisId="km" tickFormatter={(m) => `${Math.round(Number(m) / 1000)}km`} axisLine={false} tickLine={false} />
                <YAxis yAxisId="speed" orientation="right" tickFormatter={(v) => `${v}`} domain={["auto", "auto"]} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={(d) => new Date(String(d)).toLocaleDateString()}
                  formatter={(v, name) =>
                    name === "distance" ? [`${(Number(v) / 1000).toFixed(1)} km`, name] : [`${Number(v).toFixed(1)} km/h`, name]
                  }
                />
                <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                <Bar yAxisId="km" dataKey="distance_m" name="distance" fill="#e8a33d" fillOpacity={0.55} maxBarSize={22} />
                <Line yAxisId="speed" dataKey="avg_kmh" name="avg speed" stroke="#e8e2d6" strokeWidth={1.8} dot={{ r: 3, fill: "#e8e2d6" }} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <Empty>No rides synced yet.</Empty>
          )}
        </Panel>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Panel title="Effort per ride" note="HR + training load (no power meter)" delay={140}>
            {rides.length ? (
              <ResponsiveContainer width="100%" height={180}>
                <ComposedChart data={rides} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                  <XAxis dataKey="start_time_local" tickFormatter={fmtDay} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="load" axisLine={false} tickLine={false} />
                  <YAxis yAxisId="hr" orientation="right" domain={[80, 190]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => new Date(String(d)).toLocaleDateString()} />
                  <Legend wrapperStyle={{ fontFamily: '"Spline Sans Mono", monospace', fontSize: 11 }} />
                  <Bar yAxisId="load" dataKey="training_load" name="load" fill="#e8a33d" fillOpacity={0.5} maxBarSize={18} />
                  <Scatter yAxisId="hr" dataKey="avg_hr" name="avg HR" fill="#e4572e" />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>—</Empty>
            )}
          </Panel>
          <Panel title="FTP over time" note="Garmin is source of truth" delay={200}>
            {data?.ftp_history?.length ? (
              <ResponsiveContainer width="100%" height={180}>
                <ComposedChart data={data.ftp_history} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                  <XAxis dataKey="calendar_date" tickFormatter={(d) => fmtDay(String(d))} axisLine={false} tickLine={false} />
                  <YAxis domain={[150, 300]} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v} W`, "FTP"]} />
                  <Line dataKey="value" name="FTP" stroke="#e8a33d" strokeWidth={2} dot={{ r: 4, fill: "#e8a33d" }} type="stepAfter" />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Empty>
                Garmin hasn't recorded an FTP yet
                {data?.current_ftp_w != null ? ` — using the ${Math.round(data.current_ftp_w)} W fallback` : ""}.
                New Garmin estimates append here automatically.
              </Empty>
            )}
          </Panel>
        </div>
      </Section>

      <Section index="03" title="Power" aside={data?.has_ride_power ? "power meter detected" : "no power meter on the bike"}>
        {data?.has_ride_power ? (
          <Panel title="Power duration curve" note="best average power across all rides" delay={100}>
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={data.power_duration_curve} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="#1d1a17" vertical={false} />
                <XAxis dataKey="duration_s" tickFormatter={fmtDurShort} scale="log" domain={["dataMin", "dataMax"]} type="number" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(s) => fmtDurShort(Number(s))} formatter={(v) => [`${v} W`, "best avg"]} />
                <Line dataKey="best_w" stroke="#e8a33d" strokeWidth={2} dot={{ r: 3, fill: "#e8a33d" }} />
              </ComposedChart>
            </ResponsiveContainer>
          </Panel>
        ) : (
          <Panel delay={100}>
            <Empty>
              Your rides carry no power data (no power meter paired). The power-duration curve,
              NP, IF and TSS pipelines are already built and will light up automatically on the
              first ride recorded with a power meter. Until then, effort is tracked via HR zones
              and training load above.
            </Empty>
          </Panel>
        )}
      </Section>
    </div>
  );
}
