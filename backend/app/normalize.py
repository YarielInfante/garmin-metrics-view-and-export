"""Garmin payload -> table-row normalization.

Every mapping here was derived from real FR970 fixtures (see
docs/garmin-field-notes.md), not from documentation. Garmin OMITS fields
rather than nulling them, so all sport-specific lookups use .get().

Unit notes handled here:
- pool length arrives in cm with a unit factor  -> meters
- details time-series values are already in natural units (m/s, cm, ms)
- directDoubleCadence is the real steps/min cadence (directRunCadence is strides/min)
- weight arrives in grams in user_profile but kg in lactate_threshold
- lactate threshold speed arrives divided by 10   -> m/s
"""

import json
from datetime import datetime, timezone

SPORT_BY_TYPE_KEY = {
    "running": "run", "trail_running": "run", "treadmill_running": "run",
    "track_running": "run", "indoor_running": "run",
    "cycling": "ride", "road_biking": "ride", "gravel_cycling": "ride",
    "indoor_cycling": "ride", "virtual_ride": "ride", "mountain_biking": "ride",
    "lap_swimming": "swim", "open_water_swimming": "swim",
    "strength_training": "strength",
    "walking": "walk", "hiking": "walk",
    "mobility": "mobility", "yoga": "mobility", "pilates": "mobility",
}


def _parse_dt(value: str | None) -> datetime | None:
    """Garmin timestamps: '2026-07-04 11:34:54' (list) or '2026-07-04T11:34:54.0' (detail)."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace(" ", "T"))


def _epoch_ms(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def activity_row(entry: dict) -> dict:
    """Activities-list entry -> activities row (the cheap, list-only sync)."""
    type_key = (entry.get("activityType") or {}).get("typeKey", "unknown")
    pool_len = entry.get("poolLength")
    pool_factor = (entry.get("unitOfPoolLength") or {}).get("factor") or 100.0
    return {
        "activity_id": entry["activityId"],
        "name": entry.get("activityName"),
        "type_key": type_key,
        "sport": SPORT_BY_TYPE_KEY.get(type_key, "other"),
        "start_time_utc": _parse_dt(entry.get("startTimeGMT")),
        "start_time_local": _parse_dt(entry.get("startTimeLocal")),
        "duration_s": entry.get("duration"),
        "moving_duration_s": entry.get("movingDuration"),
        "elapsed_duration_s": entry.get("elapsedDuration"),
        "distance_m": entry.get("distance"),
        "avg_speed_ms": entry.get("averageSpeed"),
        "max_speed_ms": entry.get("maxSpeed"),
        "avg_hr": entry.get("averageHR"),
        "max_hr": entry.get("maxHR"),
        "calories": entry.get("calories"),
        "training_load": entry.get("activityTrainingLoad"),
        "aerobic_te": entry.get("aerobicTrainingEffect"),
        "anaerobic_te": entry.get("anaerobicTrainingEffect"),
        "te_label": entry.get("trainingEffectLabel"),
        "vo2max": entry.get("vO2MaxValue"),
        "steps": entry.get("steps"),
        **{f"hr_z{z}_s": entry.get(f"hrTimeInZone_{z}") for z in range(1, 6)},
        **{f"power_z{z}_s": entry.get(f"powerTimeInZone_{z}") for z in range(1, 6)},
        "avg_power_w": entry.get("avgPower"),
        "max_power_w": entry.get("maxPower"),
        "norm_power_w": entry.get("normPower"),
        "avg_cadence_spm": entry.get("averageRunningCadenceInStepsPerMinute")
        or entry.get("averageBikingCadenceInRevPerMinute"),
        "max_cadence_spm": entry.get("maxRunningCadenceInStepsPerMinute")
        or entry.get("maxBikingCadenceInRevPerMinute"),
        "avg_vertical_osc_cm": entry.get("avgVerticalOscillation"),
        "avg_gct_ms": entry.get("avgGroundContactTime"),
        "avg_vertical_ratio_pct": entry.get("avgVerticalRatio"),
        "avg_stride_len_cm": entry.get("avgStrideLength"),
        "avg_gct_balance_pct": entry.get("avgGroundContactBalance"),  # needs HRM strap
        "avg_gas_ms": entry.get("avgGradeAdjustedSpeed"),
        "elevation_gain_m": entry.get("elevationGain"),
        "elevation_loss_m": entry.get("elevationLoss"),
        "start_lat": entry.get("startLatitude"),
        "start_lon": entry.get("startLongitude"),
        "location_name": entry.get("locationName"),
        "pool_length_m": (pool_len / pool_factor) if pool_len else None,
        "active_lengths": entry.get("activeLengths"),
        "avg_swolf": entry.get("averageSwolf"),
        "avg_strokes_per_length": entry.get("avgStrokes"),
        "avg_swim_cadence": entry.get("averageSwimCadenceInStrokesPerMinute"),
        "total_strokes": entry.get("strokes"),
        "fastest_100m_s": entry.get("fastestSplit_100"),
        "fastest_1000m_s": entry.get("fastestSplit_1000"),
        "moderate_im": entry.get("moderateIntensityMinutes"),
        "vigorous_im": entry.get("vigorousIntensityMinutes"),
        "water_estimated_ml": entry.get("waterEstimated"),
        "bb_diff": entry.get("differenceBodyBattery"),
        "device_id": entry.get("deviceId"),
        "pr": entry.get("pr"),
        "raw": json.dumps(entry),
    }


# details metric key -> activity_samples column
_SAMPLE_COLS = {
    "directTimestamp": "ts_ms",           # epoch ms; converted below
    "sumDuration": "elapsed_s",
    "sumDistance": "distance_m",
    "directHeartRate": "hr",
    "directSpeed": "speed_ms",
    "directGradeAdjustedSpeed": "gas_ms",
    "directPower": "power_w",
    "directDoubleCadence": "cadence_spm",
    "directVerticalOscillation": "vertical_osc_cm",
    "directGroundContactTime": "gct_ms",
    "directVerticalRatio": "vertical_ratio",
    "directStrideLength": "stride_len_cm",
    "directElevation": "elevation_m",
    "directBodyBattery": "body_battery",
    "directAvailableStamina": "stamina_pct",
}


def sample_rows(activity_id: int, details: dict) -> list[dict]:
    descriptors = details.get("metricDescriptors") or []
    idx = {
        d["key"]: d["metricsIndex"]
        for d in descriptors
        if d.get("key") in _SAMPLE_COLS
    }
    rows = []
    seen_elapsed = set()
    for m in details.get("activityDetailMetrics") or []:
        metrics = m.get("metrics") or []
        row = {"activity_id": activity_id}
        for key, col in _SAMPLE_COLS.items():
            i = idx.get(key)
            row[col] = metrics[i] if i is not None and i < len(metrics) else None
        row["ts_utc"] = _epoch_ms(row.pop("ts_ms", None))
        if row.get("elapsed_s") is None or row["elapsed_s"] in seen_elapsed:
            continue  # need a unique elapsed_s as PK component
        seen_elapsed.add(row["elapsed_s"])
        rows.append(row)
    return rows


def lap_rows(activity_id: int, splits: dict) -> list[dict]:
    rows = []
    for i, lap in enumerate(splits.get("lapDTOs") or []):
        rows.append({
            "activity_id": activity_id,
            "lap_index": i,
            "start_time_utc": _parse_dt(lap.get("startTimeGMT")),
            "duration_s": lap.get("duration"),
            "distance_m": lap.get("distance"),
            "avg_speed_ms": lap.get("averageSpeed"),
            "avg_hr": lap.get("averageHR"),
            "max_hr": lap.get("maxHR"),
            "avg_power_w": lap.get("averagePower"),
            "norm_power_w": lap.get("normalizedPower"),
            "avg_cadence_spm": lap.get("averageRunCadence"),
            "avg_vertical_osc_cm": lap.get("verticalOscillation"),
            "avg_gct_ms": lap.get("groundContactTime"),
            "avg_vertical_ratio_pct": lap.get("verticalRatio"),
            "avg_stride_len_cm": lap.get("strideLength"),
            "elevation_gain_m": lap.get("elevationGain"),
            "raw": json.dumps(lap),
        })
    return rows


def _pace_100(duration, distance) -> float | None:
    return round(duration / distance * 100.0, 1) if distance and duration else None


def swim_interval_rows(activity_id: int, splits: dict) -> tuple[list[dict], list[dict]]:
    """Pool-swim splits payload -> (interval rows, length rows).

    For lap swims each lapDTO is one interval; rest intervals have
    distance 0 / no strokes. Per-length data nests in lengthDTOs.
    """
    intervals, lengths = [], []
    for lap in splits.get("lapDTOs") or []:
        distance = lap.get("distance")
        duration = lap.get("duration")
        active = bool(lap.get("numberOfActiveLengths")) and bool(distance)
        idx = lap.get("lapIndex")
        intervals.append({
            "activity_id": activity_id,
            "interval_index": idx,
            "interval_type": "ACTIVE" if active else "REST",
            "start_time_utc": _parse_dt(lap.get("startTimeGMT")),
            "duration_s": duration,
            "distance_m": distance,
            "pace_per_100m_s": _pace_100(duration, distance),
            "num_lengths": lap.get("numberOfActiveLengths"),
            "total_strokes": lap.get("totalNumberOfStrokes"),
            "avg_strokes_per_length": lap.get("averageStrokes"),
            "avg_swolf": lap.get("averageSWOLF"),
            "avg_swim_cadence": lap.get("averageSwimCadence"),
            "avg_hr": lap.get("averageHR"),
            "max_hr": lap.get("maxHR"),
            "stroke_type": lap.get("swimStroke"),
            "raw": json.dumps(lap),
        })
        if not active:
            continue
        for ln in lap.get("lengthDTOs") or []:
            lengths.append({
                "activity_id": activity_id,
                "interval_index": idx,
                "length_index": ln.get("lengthIndex"),
                "start_time_utc": _parse_dt(ln.get("startTimeGMT")),
                "duration_s": ln.get("duration"),
                "distance_m": ln.get("distance"),
                "pace_per_100m_s": _pace_100(ln.get("duration"), ln.get("distance")),
                "strokes": ln.get("totalNumberOfStrokes"),
                "swolf": ln.get("averageSWOLF"),
                "avg_hr": ln.get("averageHR"),
                "max_hr": ln.get("maxHR"),
                "stroke_type": ln.get("swimStroke"),
            })
    return intervals, lengths


def wellness_row(date_str: str, user_summary: dict | None, hrv: dict | None, sleep: dict | None) -> dict:
    row = {"date": date_str}
    us = user_summary or {}
    row.update({
        "resting_hr": us.get("restingHeartRate"),
        "steps": us.get("totalSteps"),
        "total_kcal": us.get("totalKilocalories"),
        "min_hr": us.get("minHeartRate"),
        "max_hr": us.get("maxHeartRate"),
        "stress_avg": us.get("averageStressLevel"),
        "stress_max": us.get("maxStressLevel"),
        "bb_charged": us.get("bodyBatteryChargedValue"),
        "bb_drained": us.get("bodyBatteryDrainedValue"),
        "bb_high": us.get("bodyBatteryHighestValue"),
        "bb_low": us.get("bodyBatteryLowestValue"),
        "moderate_im": us.get("moderateIntensityMinutes"),
        "vigorous_im": us.get("vigorousIntensityMinutes"),
    })
    summary = (hrv or {}).get("hrvSummary") or {}
    row.update({
        "hrv_last_night_ms": summary.get("lastNightAvg"),
        "hrv_weekly_avg_ms": summary.get("weeklyAvg"),
        "hrv_status": summary.get("status"),
    })
    dto = (sleep or {}).get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    row.update({
        "sleep_s": dto.get("sleepTimeSeconds"),
        "sleep_deep_s": dto.get("deepSleepSeconds"),
        "sleep_light_s": dto.get("lightSleepSeconds"),
        "sleep_rem_s": dto.get("remSleepSeconds"),
        "sleep_awake_s": dto.get("awakeSleepSeconds"),
        "sleep_score": (scores.get("overall") or {}).get("value"),
        "overnight_hrv_ms": (sleep or {}).get("avgOvernightHrv"),
        "bb_change_sleep": (sleep or {}).get("bodyBatteryChange"),
    })
    # a resting HR from the sleep payload beats a missing user-summary one
    if row["resting_hr"] is None:
        row["resting_hr"] = (sleep or {}).get("restingHeartRate")
    return row


def training_status_row(date_str: str, payload: dict | None, max_metrics) -> dict | None:
    """training-status payload is keyed by device id under latestTrainingStatusData."""
    row = {"date": date_str}
    found = False
    mrts = (payload or {}).get("mostRecentTrainingStatus") or {}
    by_device = mrts.get("latestTrainingStatusData") or {}
    for dev in by_device.values():
        acute = dev.get("acuteTrainingLoadDTO") or {}
        row.update({
            "acute_load": acute.get("dailyTrainingLoadAcute"),
            "chronic_load": acute.get("dailyTrainingLoadChronic"),
            "acwr": acute.get("dailyAcuteChronicWorkloadRatio"),
            "acwr_pct": acute.get("acwrPercent"),
            "acwr_status": acute.get("acwrStatus"),
            "feedback_phrase": dev.get("trainingStatusFeedbackPhrase"),
            "status_code": dev.get("trainingStatus"),
        })
        found = True
        break  # single-device setup; first entry is the FR970
    if isinstance(max_metrics, list) and max_metrics:
        mm = max_metrics[0] or {}
        generic = mm.get("generic") or {}
        cycling = mm.get("cycling") or {}
        row["vo2max_running"] = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
        row["vo2max_cycling"] = cycling.get("vo2MaxPreciseValue") or cycling.get("vo2MaxValue")
        found = found or row["vo2max_running"] is not None
    return row if found else None


def readiness_row(date_str: str, payload) -> dict | None:
    """Readiness returns a list of snapshots; prefer the after-wakeup one."""
    if not isinstance(payload, list) or not payload:
        return None
    entry = next(
        (e for e in payload if e.get("inputContext") == "AFTER_WAKEUP_RESET"),
        payload[0],
    )
    return {
        "date": date_str,
        "score": entry.get("score"),
        "level": entry.get("level"),
        "feedback_short": entry.get("feedbackShort"),
        "sleep_score": entry.get("sleepScore"),
        "hrv_factor_pct": entry.get("hrvFactorPercent"),
        "recovery_time_min": entry.get("recoveryTime"),
        "acute_load": entry.get("acuteLoad"),
        "input_context": entry.get("inputContext"),
    }


def _date_only(ts: str | None) -> str | None:
    return ts[:10] if ts else None


def biometric_rows(cycling_ftp: dict | None, lactate: dict | None, races: dict | None, profile: dict | None) -> list[dict]:
    rows = []

    def add(metric, date_str, value):
        if date_str and value is not None:
            rows.append({"metric": metric, "calendar_date": date_str, "value": float(value)})

    if cycling_ftp:
        add("cycling_ftp_w", _date_only(cycling_ftp.get("calendarDate")), cycling_ftp.get("functionalThresholdPower"))
    shr = (lactate or {}).get("speed_and_heart_rate") or {}
    add("lthr_bpm", _date_only(shr.get("calendarDate")), shr.get("heartRate"))
    if shr.get("speed") is not None:
        add("lt_speed_ms", _date_only(shr.get("calendarDate")), shr["speed"] * 10.0)  # Garmin stores /10
    power = (lactate or {}).get("power") or {}
    add("running_ftp_w", _date_only(power.get("calendarDate")), power.get("functionalThresholdPower"))
    add("weight_kg", _date_only(power.get("weightCreateTime") or power.get("calendarDate")), power.get("weight"))
    if not power.get("weight") and (profile or {}).get("userData", {}).get("weight"):
        add("weight_kg", datetime.now().date().isoformat(), profile["userData"]["weight"] / 1000.0)  # grams -> kg
    if races:
        d = races.get("calendarDate")
        add("race_5k_s", d, races.get("time5K"))
        add("race_10k_s", d, races.get("time10K"))
        add("race_half_s", d, races.get("timeHalfMarathon"))
        add("race_marathon_s", d, races.get("timeMarathon"))
    return rows


def hr_zone_rows(zones_payload) -> list[dict]:
    rows = []
    for cfg in zones_payload or []:
        rows.append({
            "sport": cfg.get("sport", "DEFAULT"),
            "training_method": cfg.get("trainingMethod"),
            **{f"z{i}_floor": cfg.get(f"zone{i}Floor") for i in range(1, 6)},
            "max_hr": cfg.get("maxHeartRateUsed"),
            "lthr": cfg.get("lactateThresholdHeartRateUsed"),
            "resting_hr": cfg.get("restingHeartRateUsed"),
        })
    return rows
