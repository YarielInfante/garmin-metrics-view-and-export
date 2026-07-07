import { useEffect, useState } from "react";

const BASE = "";

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || `${path}: ${res.status}`);
  return data as T;
}

export function useApi<T>(path: string | null, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) {
      setData(null);
      setError(null);
      return;
    }
    let live = true;
    const load = () =>
      getJson<T>(path)
        .then((d) => live && (setData(d), setError(null)))
        .catch((e) => live && setError(String(e)));
    load();
    const id = refreshMs ? setInterval(load, refreshMs) : undefined;
    return () => {
      live = false;
      if (id) clearInterval(id);
    };
  }, [path, refreshMs]);
  return { data, error };
}

// ---- types mirrored from the backend ----

export interface SyncStatus {
  running: boolean;
  phase: string | null;
  auth_required: boolean;
  auth_message: string | null;
  reauth_command: string;
  last_success_at: string | null;
  rate_limit_cooldown_until: string | null;
  last_run: {
    trigger: string;
    started_at: string;
    finished_at: string;
    status: string;
    error: string | null;
    stats: string;
  } | null;
  activity_count: number;
  newest_activity_at: string | null;
  newest_wellness_date: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  pending_mfa: boolean;
  display_name: string | null;
}

export interface AppConfig {
  targets: {
    cadence_band: [number, number];
    ftp_fallback_w: number;
    easy_zone_max: number;
    easy_target_pct: number;
    z2_cap_bpm_note: number;
    acwr_range: [number, number];
    pool_length_m: number;
  };
  sync: { interval_hours: number; staleness_hours: number };
  hr_zones: {
    sport: string;
    z1_floor: number; z2_floor: number; z3_floor: number;
    z4_floor: number; z5_floor: number;
    max_hr: number; lthr: number;
  }[];
}

export interface LoadDay {
  date: string;
  daily_load: number;
  acute_local: number;
  chronic_local: number;
  acwr_local: number | null;
  acute_garmin: number | null;
  chronic_garmin: number | null;
  acwr_garmin: number | null;
  acwr_status: string | null;
  readiness_score: number | null;
  readiness_level: string | null;
}

export interface IntensityWeek {
  week: string;
  z1: number; z2: number; z3: number; z4: number; z5: number;
  total_s: number;
  easy_pct: number | null;
  hard_pct: number | null;
}

export interface SummaryWeek {
  week: string;
  sport: string;
  sessions: number;
  duration_s: number;
  distance_m: number;
  training_load: number;
}

export interface RunRow {
  activity_id: number;
  name: string;
  start_time_local: string;
  distance_m: number;
  duration_s: number;
  avg_hr: number | null;
  avg_cadence_spm: number | null;
  avg_vertical_osc_cm: number | null;
  avg_gct_ms: number | null;
  avg_vertical_ratio_pct: number | null;
  avg_gct_balance_pct: number | null;
  avg_power_w: number | null;
  norm_power_w: number | null;
  aerobic_decoupling_pct: number | null;
  training_load: number | null;
  vo2max: number | null;
  pace_s_per_km: number | null;
}

export interface RunWeek {
  week: string;
  runs: number;
  distance_m: number;
  duration_s: number;
  pace_s_per_km: number | null;
  avg_hr: number | null;
  z1: number; z2: number; z3: number; z4: number; z5: number;
}

export interface WellnessDay {
  date: string;
  resting_hr: number | null;
  hrv_last_night_ms: number | null;
  hrv_weekly_avg_ms: number | null;
  hrv_status: string | null;
  sleep_s: number | null;
  sleep_deep_s: number | null;
  sleep_light_s: number | null;
  sleep_rem_s: number | null;
  sleep_awake_s: number | null;
  sleep_score: number | null;
  bb_charged: number | null;
  bb_drained: number | null;
  bb_high: number | null;
  bb_low: number | null;
  stress_avg: number | null;
  readiness_score: number | null;
  readiness_level: string | null;
  vo2max_running: number | null;
}

export interface ExportCoverage {
  earliest: string | null;
  latest: string | null;
  activities: number;
  days: number;
  payloads: number;
}

export interface RawExport {
  generated_at: string;
  range: { start: string; end: string };
  include_details: boolean;
  coverage: { activities: number; days: number };
  athlete_config: Record<string, unknown>;
  activities: unknown[];
  daily: Record<string, unknown>;
}

// ---- formatting helpers ----

export const fmtDur = (s: number | null | undefined) => {
  if (s == null) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}min`;
};

export const fmtPace = (sPerKm: number | null | undefined) => {
  if (sPerKm == null) return "—";
  const m = Math.floor(sPerKm / 60);
  const s = Math.round(sPerKm % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export const fmtDay = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export const fmtKm = (m: number | null | undefined) =>
  m == null ? "—" : `${(m / 1000).toFixed(1)}`;
