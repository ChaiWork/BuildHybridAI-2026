"""
SQLite Local Persistence Layer and Synthetic Demonstration Data Seeder for TARS Care AI.
Stores historical telemetry, user-entered measurements, psychological self-assessments,
store-and-forward Earth synchronization queues, and configurable hazard thresholds.
"""

from __future__ import annotations
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from models import (
    AstronautBaseline,
    RadiationConfigLimits,
    EnvironmentalConfigLimits,
    DataProvenance,
    MissionPhase,
    RiskLevel,
)
from mission_ops import (
    CREW_ORDER,
    DEFAULT_DEMO_PIN,
    crew_synthetic_profiles,
    default_crew_baselines,
    default_medical_kit_items,
    hash_privacy_pin,
)

def _resolve_default_db_path() -> str:
    explicit = os.environ.get("TARSCARE_DB_PATH", "").strip()
    if explicit:
        return explicit
    local_dir = os.path.dirname(__file__)
    # Vercel Functions mount deployment files read-only; use writable temp storage in serverless runs.
    if os.environ.get("VERCEL") or not os.access(local_dir, os.W_OK):
        return os.path.join(tempfile.gettempdir(), "tarscare_local.db")
    return os.path.join(local_dir, "tarscare_local.db")


DB_PATH = _resolve_default_db_path()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_id TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI',
            timestamp TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            mission_phase TEXT NOT NULL,
            gravity_g REAL NOT NULL,
            provenance TEXT NOT NULL,
            absorbed_dose_mgy REAL NOT NULL,
            absorbed_dose_rate_mgy_hr REAL NOT NULL,
            equivalent_dose_msv REAL NOT NULL,
            equivalent_dose_rate_msv_day REAL NOT NULL,
            cumulative_effective_dose_msv REAL NOT NULL,
            radiation_source TEXT NOT NULL,
            radiation_event_type TEXT NOT NULL,
            mood_score REAL NOT NULL,
            stress_level REAL NOT NULL,
            emotional_wellbeing REAL NOT NULL,
            fatigue_level REAL NOT NULL,
            workload_score REAL NOT NULL,
            social_interaction_score REAL NOT NULL,
            sleep_duration_hrs REAL NOT NULL,
            sleep_quality_pct REAL NOT NULL,
            sleep_schedule_window TEXT NOT NULL,
            sleep_irregularities INTEGER NOT NULL,
            feeling_isolated INTEGER NOT NULL,
            concentration_difficulty INTEGER NOT NULL,
            motivation_level REAL NOT NULL,
            heart_rate_bpm REAL NOT NULL,
            systolic_bp_mmhg REAL NOT NULL,
            diastolic_bp_mmhg REAL NOT NULL,
            spo2_pct REAL NOT NULL,
            respiratory_rate_bpm REAL NOT NULL DEFAULT 16.0,
            body_temp_c REAL NOT NULL,
            dizziness_severity INTEGER NOT NULL,
            faintness_presyncope INTEGER NOT NULL,
            chest_discomfort INTEGER NOT NULL DEFAULT 0,
            palpitations INTEGER NOT NULL DEFAULT 0,
            shortness_of_breath INTEGER NOT NULL DEFAULT 0,
            physical_activity_mins REAL NOT NULL,
            exercise_performance_pct REAL NOT NULL,
            muscle_strength_idx REAL NOT NULL,
            exercise_adherence_pct REAL NOT NULL,
            musculoskeletal_discomfort INTEGER NOT NULL,
            balance_score REAL NOT NULL,
            coordination_score REAL NOT NULL,
            spatial_disorientation INTEGER NOT NULL,
            visual_disturbance_sans INTEGER NOT NULL,
            cabin_temp_c REAL NOT NULL,
            cabin_pressure_kpa REAL NOT NULL,
            oxygen_pct REAL NOT NULL,
            co2_mmhg REAL NOT NULL,
            co2_ppm REAL NOT NULL,
            humidity_pct REAL NOT NULL,
            air_quality_index REAL NOT NULL,
            env_warning_event TEXT NOT NULL,
            respiratory_symptoms TEXT NOT NULL,
            infection_symptoms TEXT NOT NULL,
            reported_symptoms TEXT NOT NULL DEFAULT '[]',
            hygiene_adherence_pct REAL NOT NULL,
            notes TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS psych_questionnaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_id TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI',
            timestamp TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            emotional_condition_rating INTEGER NOT NULL,
            psychological_stress_rating INTEGER NOT NULL,
            motivation_rating INTEGER NOT NULL,
            fatigue_rating INTEGER NOT NULL,
            sleep_difficulty_rating INTEGER NOT NULL,
            isolation_feeling_rating INTEGER NOT NULL,
            concentration_workload_rating INTEGER NOT NULL,
            journal_reflection TEXT NOT NULL,
            provenance TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS store_forward_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_id TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI',
            report_uid TEXT NOT NULL,
            created_at TEXT NOT NULL,
            synced_at TEXT,
            mission_day INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            hazard_triggers TEXT NOT NULL,
            transmission_status TEXT NOT NULL,
            provenance TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sans_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_id TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI',
            timestamp TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            eye_tested TEXT NOT NULL,
            wavy_lines_detected INTEGER NOT NULL,
            scotoma_cells TEXT NOT NULL,
            near_acuity_shift INTEGER NOT NULL,
            notes TEXT NOT NULL,
            provenance TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_kit_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            bay_location TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit TEXT NOT NULL,
            min_threshold INTEGER NOT NULL,
            expiry_date TEXT NOT NULL,
            cmo_auth_required INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL,
            last_inspected TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS device_states (
            crew_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            connection_status TEXT NOT NULL,
            active_mode TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '',
            last_measurement_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (crew_id, device_id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS device_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            measurement_category TEXT NOT NULL,
            measurement_type TEXT NOT NULL,
            value REAL,
            value_text TEXT,
            unit TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            connection_method TEXT NOT NULL,
            data_source TEXT NOT NULL,
            connection_status TEXT NOT NULL,
            quality_status TEXT NOT NULL,
            quality_note TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 1,
            telemetry_field TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hardware_examinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            exam_type TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            data_source TEXT NOT NULL,
            findings_json TEXT NOT NULL,
            summary_note TEXT NOT NULL DEFAULT '',
            abnormal_flag INTEGER NOT NULL DEFAULT 0,
            abnormal_reason TEXT NOT NULL DEFAULT '',
            attachments_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS biosample_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            specimen_type TEXT NOT NULL,
            collection_protocol TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            storage_location TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            attachments_json TEXT NOT NULL DEFAULT '[]',
            assay_results_json TEXT NOT NULL DEFAULT '{}',
            assay_imported_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS donki_events (
            event_uid TEXT PRIMARY KEY,
            service_type TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            severity TEXT NOT NULL,
            regime_scope TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            linked_ids_json TEXT NOT NULL DEFAULT '[]',
            source_url TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL DEFAULT '{}',
            data_provenance TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS insight_weather_sols (
            sol_id TEXT PRIMARY KEY,
            first_utc TEXT NOT NULL DEFAULT '',
            last_utc TEXT NOT NULL DEFAULT '',
            season TEXT NOT NULL DEFAULT '',
            northern_season TEXT NOT NULL DEFAULT '',
            southern_season TEXT NOT NULL DEFAULT '',
            month_ordinal INTEGER,
            at_json TEXT NOT NULL DEFAULT '{}',
            hws_json TEXT NOT NULL DEFAULT '{}',
            pre_json TEXT NOT NULL DEFAULT '{}',
            wd_json TEXT NOT NULL DEFAULT '{}',
            validity_json TEXT NOT NULL DEFAULT '{}',
            missing_sensors_json TEXT NOT NULL DEFAULT '[]',
            data_provenance TEXT NOT NULL DEFAULT 'REAL_NASA_INSIGHT',
            fetched_at TEXT NOT NULL
        )
        """
    )

    conn.commit()

    # Schema migration guard for existing tarscare_local.db
    cur.execute("PRAGMA table_info(telemetry_records)")
    cols = {r["name"] for r in cur.fetchall()}
    migrations = [
        ("crew_id", "TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI'"),
        ("respiratory_rate_bpm", "REAL NOT NULL DEFAULT 16.0"),
        ("chest_discomfort", "INTEGER NOT NULL DEFAULT 0"),
        ("palpitations", "INTEGER NOT NULL DEFAULT 0"),
        ("shortness_of_breath", "INTEGER NOT NULL DEFAULT 0"),
        ("reported_symptoms", "TEXT NOT NULL DEFAULT '[]'"),
    ]
    for col_name, col_def in migrations:
        if col_name not in cols:
            cur.execute(
                f"ALTER TABLE telemetry_records ADD COLUMN {col_name} {col_def}"
            )
            conn.commit()

    for tbl in ("psych_questionnaires", "store_forward_reports"):
        cur.execute(f"PRAGMA table_info({tbl})")
        tcols = {r["name"] for r in cur.fetchall()}
        if "crew_id" not in tcols:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN crew_id TEXT NOT NULL DEFAULT 'ARES-IV-SUCHAI'")
            conn.commit()

    # Seed if empty, and backfill Sols 155-170 if upgrading from 14-Sol DB
    cur.execute("SELECT COUNT(*) as cnt FROM telemetry_records WHERE crew_id = 'ARES-IV-SUCHAI'")
    row = cur.fetchone()
    if row["cnt"] == 0:
        seed_synthetic_data(conn)
    _ensure_30_sol_synthetic_history(conn)
    _ensure_crew_ops_seed(conn)

    # Upgrade legacy demo astronaut name in existing local DB if present
    cur.execute("SELECT value_json FROM system_state WHERE key = 'baseline'")
    brow = cur.fetchone()
    if brow and "Elena Vance-Chen" in brow["value_json"]:
        bdata = json.loads(brow["value_json"])
        bdata["name"] = "SuChai"
        bdata["astronaut_id"] = "ARES-IV-SUCHAI"
        cur.execute(
            "INSERT OR REPLACE INTO system_state (key, value_json) VALUES ('baseline', ?)",
            (json.dumps(bdata),),
        )
        conn.commit()

    from support_modules import init_support_tables
    init_support_tables(conn)

    conn.close()


def _ensure_30_sol_synthetic_history(conn: sqlite3.Connection) -> None:
    """Guarantees 30 Sols (155-184) of synthetic history for SuChai without overwriting user records."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM telemetry_records WHERE mission_day = 155 AND crew_id = 'ARES-IV-SUCHAI'")
    if cur.fetchone()["cnt"] > 0:
        return
    early_sols = [
        # day, phase, grav, abs_mgy, eq_msv, cum_msv, rad_evt, mood, stress, fatigue, work, sleep_h, sleep_q, hr, sys_bp, dia_bp, spo2, resp_rate, temp, dizz, strength, bal, co2_mmhg, humid, aqi, notes
        (155, "MICROGRAVITY_TRANSIT", 0.0, 0.43, 1.04, 135.2, "GCR_BACKGROUND", 8.2, 2.4, 2.9, 5.2, 7.4, 87.0, 58.0, 111.0, 70.0, 98.5, 15.0, 36.6, 0, 98.1, 94.0, 2.2, 46.0, 18.0, "Transit Day 155: nominal deep-space cruise; baseline cardiovascular stability."),
        (156, "MICROGRAVITY_TRANSIT", 0.0, 0.43, 1.05, 136.2, "GCR_BACKGROUND", 8.3, 2.5, 3.0, 5.3, 7.5, 88.0, 58.0, 110.0, 69.0, 98.4, 15.0, 36.6, 0, 98.0, 93.8, 2.2, 46.0, 18.0, "Transit Day 156: routine ARED lower-body loading completed."),
        (157, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.06, 137.3, "GCR_BACKGROUND", 8.1, 2.6, 3.1, 5.4, 7.3, 86.0, 59.0, 111.0, 70.0, 98.5, 15.2, 36.6, 0, 97.9, 93.6, 2.3, 45.0, 19.0, "Transit Day 157: sleep hygiene schedule steady."),
        (158, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.06, 138.4, "GCR_BACKGROUND", 8.0, 2.7, 3.2, 5.6, 7.2, 85.0, 59.0, 111.0, 70.0, 98.4, 15.1, 36.6, 0, 97.8, 93.5, 2.3, 45.0, 19.0, "Transit Day 158: weekly cabin swab & water quality check nominal."),
        (159, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.07, 139.4, "GCR_BACKGROUND", 8.2, 2.5, 3.0, 5.1, 7.6, 88.0, 58.0, 110.0, 70.0, 98.5, 14.9, 36.6, 0, 97.8, 93.6, 2.2, 46.0, 18.0, "Transit Day 159: crew social conference & Earth video family exchange."),
        (160, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.06, 140.5, "GCR_BACKGROUND", 8.1, 2.6, 3.1, 5.4, 7.4, 86.0, 59.0, 111.0, 70.0, 98.4, 15.0, 36.6, 0, 97.7, 93.4, 2.3, 45.0, 19.0, "Transit Day 160: nominal optic nerve ultrasound & tonometry check."),
        (161, "MICROGRAVITY_TRANSIT", 0.0, 0.46, 1.09, 141.6, "GCR_BACKGROUND", 7.9, 2.9, 3.3, 5.7, 7.1, 84.0, 60.0, 112.0, 71.0, 98.3, 15.3, 36.6, 0, 97.6, 93.2, 2.4, 45.0, 20.0, "Transit Day 161: ECLSS filter maintenance shift."),
        (162, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.08, 142.7, "GCR_BACKGROUND", 8.0, 2.8, 3.2, 5.5, 7.3, 85.0, 59.0, 111.0, 70.0, 98.4, 15.1, 36.6, 0, 97.6, 93.2, 2.3, 46.0, 19.0, "Transit Day 162: nominal cardio ergometer session."),
        (163, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.07, 143.7, "GCR_BACKGROUND", 8.1, 2.6, 3.0, 5.3, 7.5, 87.0, 58.0, 110.0, 69.0, 98.5, 15.0, 36.6, 0, 97.5, 93.1, 2.2, 46.0, 18.0, "Transit Day 163: restful sleep window achieved."),
        (164, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.08, 144.8, "GCR_BACKGROUND", 8.0, 2.7, 3.1, 5.5, 7.4, 86.0, 59.0, 111.0, 70.0, 98.4, 15.1, 36.6, 0, 97.5, 93.0, 2.3, 45.0, 19.0, "Transit Day 164: orbital navigation course correction check."),
        (165, "MICROGRAVITY_TRANSIT", 0.0, 0.46, 1.09, 145.9, "GCR_BACKGROUND", 7.9, 2.8, 3.3, 5.6, 7.2, 85.0, 59.0, 111.0, 70.0, 98.4, 15.2, 36.6, 0, 97.4, 93.0, 2.4, 45.0, 19.0, "Transit Day 165: nominal flight physiology."),
        (166, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.08, 147.0, "GCR_BACKGROUND", 8.0, 2.7, 3.2, 5.4, 7.4, 86.0, 59.0, 110.0, 70.0, 98.4, 15.0, 36.6, 0, 97.4, 93.1, 2.3, 46.0, 19.0, "Transit Day 166: crew cognitive reaction task baseline on target."),
        (167, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.07, 148.1, "GCR_BACKGROUND", 8.1, 2.6, 3.1, 5.3, 7.5, 87.0, 58.0, 110.0, 70.0, 98.5, 15.0, 36.6, 0, 97.3, 93.1, 2.2, 46.0, 18.0, "Transit Day 167: off-duty recovery & music journaling."),
        (168, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.08, 149.1, "GCR_BACKGROUND", 8.0, 2.7, 3.1, 5.4, 7.4, 86.0, 59.0, 111.0, 70.0, 98.4, 15.1, 36.6, 0, 97.3, 93.0, 2.3, 45.0, 19.0, "Transit Day 168: landing suit sizing & stowage verification."),
        (169, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.07, 150.2, "GCR_BACKGROUND", 8.1, 2.6, 3.0, 5.4, 7.5, 87.0, 59.0, 111.0, 70.0, 98.5, 15.0, 36.6, 0, 97.2, 93.0, 2.3, 46.0, 19.0, "Transit Day 169: approach navigation simulation."),
        (170, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.08, 151.0, "GCR_BACKGROUND", 8.1, 2.6, 3.1, 5.5, 7.5, 87.0, 59.0, 111.0, 70.0, 98.4, 15.0, 36.6, 0, 97.2, 93.0, 2.3, 46.0, 19.0, "Transit Day 170: nominal pre-insertion readiness."),
    ]
    for row in early_sols:
        (
            day, phase, grav, abs_mgy, eq_msv, cum_msv, rad_evt,
            mood, stress, fatigue, work, sleep_h, sleep_q,
            hr, sys_bp, dia_bp, spo2, resp_rate, temp, dizz, strength, bal,
            co2_mmhg, humid, aqi, notes
        ) = row
        ts = f"2026-10-{day - 139:02d}T08:00:00Z"
        cur.execute(
            """
            INSERT INTO telemetry_records (
                timestamp, mission_day, mission_phase, gravity_g, provenance,
                absorbed_dose_mgy, absorbed_dose_rate_mgy_hr, equivalent_dose_msv,
                equivalent_dose_rate_msv_day, cumulative_effective_dose_msv,
                radiation_source, radiation_event_type,
                mood_score, stress_level, emotional_wellbeing, fatigue_level,
                workload_score, social_interaction_score,
                sleep_duration_hrs, sleep_quality_pct, sleep_schedule_window,
                sleep_irregularities, feeling_isolated, concentration_difficulty, motivation_level,
                heart_rate_bpm, systolic_bp_mmhg, diastolic_bp_mmhg, spo2_pct, respiratory_rate_bpm, body_temp_c,
                dizziness_severity, faintness_presyncope,
                physical_activity_mins, exercise_performance_pct, muscle_strength_idx,
                exercise_adherence_pct, musculoskeletal_discomfort,
                balance_score, coordination_score, spatial_disorientation, visual_disturbance_sans,
                cabin_temp_c, cabin_pressure_kpa, oxygen_pct, co2_mmhg, co2_ppm,
                humidity_pct, air_quality_index, env_warning_event,
                respiratory_symptoms, infection_symptoms, hygiene_adherence_pct, notes
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                ts, day, phase, grav, DataProvenance.SYNTHETIC_DEMO.value,
                abs_mgy, round(abs_mgy / 24.0, 4), eq_msv, eq_msv, cum_msv,
                "HABITAT_TEPC_PLUS_CREW_DOSIMETER (SYNTHETIC)", rad_evt,
                mood, stress, round((mood + (10 - stress)) / 2.0, 1), fatigue,
                work, 7.8, sleep_h, sleep_q, "22:30 - 05:30 UTC-MARS",
                1, 0, 0, 8.1,
                hr, sys_bp, dia_bp, spo2, resp_rate, temp,
                dizz, 0, 110.0, 95.0, strength, 95.0, 0,
                bal, round(bal + 2.5, 1), 0, 0,
                21.5, 70.3, 21.1, co2_mmhg, round(co2_mmhg * 1315.0, 0),
                humid, aqi, "NONE", json.dumps([]), json.dumps([]), 97.0, notes,
            ),
        )
    conn.commit()


def seed_synthetic_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # 1. Seed system_state (baseline, limits, comm state)
    baseline = AstronautBaseline()
    rad_limits = RadiationConfigLimits()
    env_limits = EnvironmentalConfigLimits()
    comm_state = {
        "earth_comm_status": "NOMINAL_DELAYED",
        "one_way_delay_minutes": 14.2,
        "distance_million_km": 255.4,
        "last_sync_timestamp": "2026-11-14T04:15:00Z",
        "offline_mode_forced": False,
        "dsn_note": "Simulated store-and-forward deep-space telemetry queue (does not implement NASA's actual Deep Space Network).",
    }

    for k, v in [
        ("baseline", baseline.model_dump()),
        ("rad_limits", rad_limits.model_dump()),
        ("env_limits", env_limits.model_dump()),
        ("comm_state", comm_state),
    ]:
        cur.execute(
            "INSERT OR REPLACE INTO system_state (key, value_json) VALUES (?, ?)",
            (k, json.dumps(v)),
        )

    # 2. Seed 14 Sols (Mission Days 171 to 184) of realistic synthetic astronaut telemetry
    # Showing transition from Microgravity Transit (Days 171-175) to Mars Surface 0.38g (Days 176-184)
    # including a minor SPE radiation warning on Day 179 and CO2/orthostatic adaptation on Day 183-184.
    synthetic_sols = [
        # (day, phase, grav, abs_mgy, eq_msv, cum_msv, rad_evt, mood, stress, fatigue, work, sleep_h, sleep_q, hr, sys_bp, dia_bp, spo2, temp, dizz, strength, bal, co2_mmhg, humid, aqi, resp, notes)
        (171, "MICROGRAVITY_TRANSIT", 0.0, 0.44, 1.08, 152.1, "GCR_BACKGROUND", 8.1, 2.6, 3.1, 5.5, 7.5, 87.0, 59.0, 111.0, 70.0, 98.4, 36.6, 0, 97.2, 93.0, 2.3, 46.0, 19.0, [], "Nominal deep-space transit cruise; routine ARED + cycle countermeasures."),
        (172, "MICROGRAVITY_TRANSIT", 0.0, 0.45, 1.10, 153.2, "GCR_BACKGROUND", 8.0, 2.8, 3.3, 5.8, 7.4, 86.0, 60.0, 112.0, 71.0, 98.3, 36.6, 0, 96.8, 92.5, 2.4, 45.0, 20.0, [], "Nominal cruise; optical coherence check stable."),
        (173, "MICROGRAVITY_TRANSIT", 0.0, 0.46, 1.12, 154.3, "GCR_BACKGROUND", 7.9, 3.0, 3.5, 6.0, 7.2, 84.0, 60.0, 110.0, 70.0, 98.5, 36.6, 0, 96.5, 92.0, 2.5, 45.0, 21.0, [], "Pre-Mars orbital insertion checklist preparation."),
        (174, "MICROGRAVITY_TRANSIT", 0.0, 0.47, 1.14, 155.5, "GCR_BACKGROUND", 7.6, 3.6, 4.0, 6.8, 6.9, 82.0, 62.0, 110.0, 69.0, 98.2, 36.7, 0, 96.0, 91.0, 2.6, 44.0, 22.0, [], "Increased workload ahead of Mars entry, descent, and landing (EDL)."),
        (175, "MICROGRAVITY_TRANSIT", 0.0, 0.48, 1.15, 156.6, "GCR_BACKGROUND", 7.5, 4.2, 4.4, 7.4, 6.6, 80.0, 64.0, 109.0, 69.0, 98.1, 36.7, 0, 95.5, 90.0, 2.7, 43.0, 23.0, [], "Final microgravity day; fluid loading protocol initiated prior to 0.38g entry."),
        (176, "MARS_SURFACE", 0.38, 0.29, 0.72, 157.3, "GCR_MARS_SHIELDED", 8.4, 3.8, 5.2, 7.5, 6.5, 78.0, 74.0, 101.0, 65.0, 97.9, 36.7, 2, 91.5, 79.0, 2.5, 42.0, 25.0, [], "Landing Sol 1 (0.38g): expected post-transit orthostatic heart rate elevation and mild vestibular ataxia."),
        (177, "MARS_SURFACE", 0.38, 0.30, 0.74, 158.1, "GCR_MARS_SHIELDED", 8.1, 3.5, 4.8, 6.8, 6.9, 81.0, 71.0, 103.0, 66.0, 98.0, 36.6, 1, 92.0, 81.0, 2.5, 42.0, 24.0, [], "Graduated 0.38g neurovestibular balance adaptation drills underway."),
        (178, "MARS_SURFACE", 0.38, 0.31, 0.76, 158.8, "GCR_MARS_SHIELDED", 7.9, 3.4, 4.3, 6.4, 7.1, 83.0, 67.0, 106.0, 68.0, 98.1, 36.6, 1, 92.8, 84.0, 2.6, 41.0, 26.0, [], "Habitat deployment nominal; cardiovascular baroreflex stabilizing."),
        (179, "MARS_SURFACE", 0.38, 1.15, 2.95, 161.8, "SPE_SOLAR_ENERGETIC_PROTON", 7.2, 4.9, 5.0, 6.2, 6.3, 76.0, 68.0, 107.0, 68.0, 97.9, 36.7, 0, 93.0, 85.0, 2.9, 40.0, 28.0, [], "Moderate Solar Particle Event (SPE) detected by orbital + habitat dosimeters; crew sheltered in water-wall core for 9 hours."),
        (180, "MARS_SURFACE", 0.38, 0.52, 1.28, 163.1, "SPE_DECAY_TAIL", 7.5, 4.0, 4.6, 6.3, 6.8, 80.0, 66.0, 108.0, 69.0, 98.0, 36.6, 0, 93.2, 86.0, 2.7, 41.0, 27.0, [], "SPE proton flux subsiding; post-storm dosimetry review completed."),
        (181, "MARS_SURFACE", 0.38, 0.33, 0.81, 163.9, "GCR_MARS_SHIELDED", 7.7, 3.6, 4.2, 6.5, 7.0, 82.0, 65.0, 108.0, 69.0, 98.1, 36.6, 0, 93.6, 87.0, 2.6, 42.0, 25.0, [], "First geological surface EVA completed; minor airlock regolith dust tracked."),
        (182, "MARS_SURFACE", 0.38, 0.34, 0.83, 164.7, "GCR_MARS_SHIELDED", 7.3, 4.3, 4.9, 7.2, 6.4, 79.0, 66.0, 107.0, 68.0, 97.8, 36.7, 0, 93.0, 86.0, 3.0, 38.0, 39.0, [], "Extended sample analysis shift; slight sleep truncation and rising cabin CO2."),
        (183, "MARS_SURFACE", 0.38, 0.58, 1.42, 166.1, "GCR_PLUS_SOLAR_FLARE", 6.8, 5.1, 5.8, 7.8, 5.9, 74.0, 71.0, 103.0, 66.0, 97.4, 36.8, 1, 91.8, 83.0, 3.3, 35.0, 52.0, ["Mild dry cough"], "Primary CDRA scrubber bed nearing saturation (CO2 3.3 mmHg); mild throat/airway dryness after airlock maintenance."),
        (184, "MARS_SURFACE", 0.38, 0.68, 1.68, 167.8, "SOLAR_PROTON_ENHANCEMENT", 6.4, 5.4, 6.2, 7.9, 5.7, 72.0, 73.0, 101.0, 65.0, 97.2, 36.8, 1, 91.2, 82.0, 3.4, 34.0, 56.0, ["Mild dry cough", "Headache (CO2 correlated)"], "Current Sol 184 telemetry: elevated solar proton flux (1.68 mSv/day), 3-sol sleep reduction (5.7 hrs), mild orthostatic HR rise (+15 bpm vs. baseline), and cabin CO2 at 3.4 mmHg."),
    ]

    for row in synthetic_sols:
        (
            day, phase, grav, abs_mgy, eq_msv, cum_msv, rad_evt,
            mood, stress, fatigue, work, sleep_h, sleep_q,
            hr, sys_bp, dia_bp, spo2, temp, dizz, strength, bal,
            co2_mmhg, humid, aqi, resp, notes
        ) = row
        ts = f"2026-11-{day - 170:02d}T08:00:00Z"
        cur.execute(
            """
            INSERT INTO telemetry_records (
                timestamp, mission_day, mission_phase, gravity_g, provenance,
                absorbed_dose_mgy, absorbed_dose_rate_mgy_hr, equivalent_dose_msv,
                equivalent_dose_rate_msv_day, cumulative_effective_dose_msv,
                radiation_source, radiation_event_type,
                mood_score, stress_level, emotional_wellbeing, fatigue_level,
                workload_score, social_interaction_score,
                sleep_duration_hrs, sleep_quality_pct, sleep_schedule_window,
                sleep_irregularities, feeling_isolated, concentration_difficulty, motivation_level,
                heart_rate_bpm, systolic_bp_mmhg, diastolic_bp_mmhg, spo2_pct, body_temp_c,
                dizziness_severity, faintness_presyncope,
                physical_activity_mins, exercise_performance_pct, muscle_strength_idx,
                exercise_adherence_pct, musculoskeletal_discomfort,
                balance_score, coordination_score, spatial_disorientation, visual_disturbance_sans,
                cabin_temp_c, cabin_pressure_kpa, oxygen_pct, co2_mmhg, co2_ppm,
                humidity_pct, air_quality_index, env_warning_event,
                respiratory_symptoms, infection_symptoms, hygiene_adherence_pct, notes
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                ts, day, phase, grav, DataProvenance.SYNTHETIC_DEMO.value,
                abs_mgy, round(abs_mgy / 24.0, 4), eq_msv, eq_msv, cum_msv,
                "HABITAT_TEPC_PLUS_CREW_DOSIMETER (SYNTHETIC)", rad_evt,
                mood, stress, round((mood + (10 - stress)) / 2.0, 1), fatigue,
                work, 7.6 if day < 182 else 6.8,
                sleep_h, sleep_q, "22:30 - 05:30 UTC-MARS",
                1 if sleep_h >= 6.5 else 3,
                1 if day >= 183 else 0,
                1 if co2_mmhg >= 3.2 else 0,
                7.9 if day < 182 else 6.9,
                hr, sys_bp, dia_bp, spo2, temp,
                dizz, 0,
                105.0 if day < 182 else 82.0,
                94.0 if day < 182 else 87.0,
                strength,
                93.0 if day < 182 else 81.0,
                1 if dizz > 0 else 0,
                bal, round(bal + 3.0, 1), 0, 0,
                21.6, 70.3, 21.1, co2_mmhg, round(co2_mmhg * 1315.0, 0),
                humid, aqi,
                "CDRA_CO2_ELEVATED" if co2_mmhg >= 3.0 else "NONE",
                json.dumps(resp), json.dumps([]), 96.0, notes
            ),
        )

    # 3. Seed psych questionnaire history
    cur.execute(
        """
        INSERT INTO psych_questionnaires (
            timestamp, mission_day, emotional_condition_rating, psychological_stress_rating,
            motivation_rating, fatigue_rating, sleep_difficulty_rating,
            isolation_feeling_rating, concentration_workload_rating,
            journal_reflection, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-11-14T07:30:00Z", 184, 7, 5, 8, 6, 4, 3, 7,
            "Surface EVA workload has been intense over the last 3 Sols. Woke up twice due to warm bunk airflow; planning blue-light alignment and CDRA scrubber bed switch today.",
            DataProvenance.SYNTHETIC_DEMO.value,
        ),
    )

    # 4. Seed store-and-forward reports
    seed_reports = [
        (
            "RPT-SOL-179-SPE",
            "2026-11-09T18:20:00Z",
            "2026-11-09T19:05:00Z",
            179,
            "Sol 179 Solar Particle Event (SPE) Shelter & Dosimetry Report",
            "Equivalent dose rate peaked at 2.95 mSv/day (1.15 mGy absorbed). Crew sheltered in polyethylene/water-wall core; cumulative dose 161.8 mSv.",
            RiskLevel.WARNING.value,
            json.dumps(["Space Radiation"]),
            "SYNCHRONIZED_ACK",
            DataProvenance.SYNTHETIC_DEMO.value,
            json.dumps({"mission_day": 179, "equivalent_dose_msv": 2.95, "absorbed_dose_mgy": 1.15}),
        ),
        (
            "RPT-SOL-184-MULTI",
            "2026-11-14T08:05:00Z",
            None,
            184,
            "Sol 184 Integrated Multi-Hazard Assessment (CO2 + Sleep + Solar Flux)",
            "Warning triggers across Radiation (1.68 mSv/day), Isolation (5.7h sleep), Gravity (+15 bpm HR vs baseline in 0.38g), and Environment (CO2 3.4 mmHg). Queued for DSN link.",
            RiskLevel.WARNING.value,
            json.dumps(["Space Radiation", "Isolation and Confinement", "Gravity Fields", "Hostile and Closed Environments"]),
            "QUEUED_LOCAL_BUFFER",
            DataProvenance.SYNTHETIC_DEMO.value,
            json.dumps({"mission_day": 184, "co2_mmhg": 3.4, "sleep_duration_hrs": 5.7, "heart_rate_bpm": 73.0}),
        ),
    ]
    for rpt in seed_reports:
        cur.execute(
            """
            INSERT INTO store_forward_reports (
                report_uid, created_at, synced_at, mission_day, title, summary,
                risk_level, hazard_triggers, transmission_status, provenance, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rpt,
        )

    conn.commit()
    _ensure_30_sol_synthetic_history(conn)


def _ensure_crew_ops_seed(conn: sqlite3.Connection) -> None:
    """Seed multi-crew baselines, crew telemetry snapshots, privacy PIN hashes, and onboard Medical Kit inventory."""
    cur = conn.cursor()

    def _get_ss(key: str) -> Any:
        cur.execute("SELECT value_json FROM system_state WHERE key = ?", (key,))
        row = cur.fetchone()
        return json.loads(row["value_json"]) if row else None

    def _set_ss(key: str, val: Any) -> None:
        cur.execute("INSERT OR REPLACE INTO system_state (key, value_json) VALUES (?, ?)", (key, json.dumps(val)))

    if not _get_ss("active_crew_id"):
        _set_ss("active_crew_id", "ARES-IV-SUCHAI")

    crew_baselines = _get_ss("crew_baselines") or default_crew_baselines()
    existing_su_baseline = _get_ss("baseline")
    if isinstance(existing_su_baseline, dict) and existing_su_baseline.get("name"):
        crew_baselines["ARES-IV-SUCHAI"] = existing_su_baseline
    _set_ss("crew_baselines", crew_baselines)

    if _get_ss("crew_baseline_histories") is None:
        su_hist = _get_ss("baseline_history") or []
        _set_ss("crew_baseline_histories", {"ARES-IV-SUCHAI": su_hist if isinstance(su_hist, list) else []})

    pins = _get_ss("crew_privacy_pins") or {}
    default_hash = hash_privacy_pin(DEFAULT_DEMO_PIN)
    changed_pins = False
    for cid in CREW_ORDER:
        if cid not in pins:
            pins[cid] = {"pin_hash": default_hash, "hint": "Default demo PIN: 2026"}
            changed_pins = True
    if changed_pins:
        _set_ss("crew_privacy_pins", pins)

    cur.execute("SELECT COUNT(*) as cnt FROM medical_kit_items")
    if cur.fetchone()["cnt"] == 0:
        for item in default_medical_kit_items():
            cur.execute(
                """
                INSERT INTO medical_kit_items (
                    item_code, name, bay_location, category, quantity, unit,
                    min_threshold, expiry_date, cmo_auth_required, notes, last_inspected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["item_code"],
                    item["name"],
                    item["bay_location"],
                    item["category"],
                    item["quantity"],
                    item["unit"],
                    item["min_threshold"],
                    item["expiry_date"],
                    int(bool(item["cmo_auth_required"])),
                    item["notes"],
                    item["last_inspected"],
                ),
            )

    for prof in crew_synthetic_profiles():
        cid = prof["crew_id"]
        cur.execute("SELECT COUNT(*) as cnt FROM telemetry_records WHERE crew_id = ?", (cid,))
        if cur.fetchone()["cnt"] == 0:
            for d in prof["days"]:
                (
                    day, eq_msv, abs_mgy, cum_msv, hr, sys_bp, dia_bp, spo2, resp_rate, temp,
                    sleep_h, mood, stress, fatigue, co2_mmhg, strength, bal, dizz, sans_vis, notes
                ) = d
                ts = f"2026-11-{day - 170:02d}T08:00:00Z"
                cur.execute(
                    """
                    INSERT INTO telemetry_records (
                        crew_id, timestamp, mission_day, mission_phase, gravity_g, provenance,
                        absorbed_dose_mgy, absorbed_dose_rate_mgy_hr, equivalent_dose_msv,
                        equivalent_dose_rate_msv_day, cumulative_effective_dose_msv,
                        radiation_source, radiation_event_type,
                        mood_score, stress_level, emotional_wellbeing, fatigue_level,
                        workload_score, social_interaction_score,
                        sleep_duration_hrs, sleep_quality_pct, sleep_schedule_window,
                        sleep_irregularities, feeling_isolated, concentration_difficulty, motivation_level,
                        heart_rate_bpm, systolic_bp_mmhg, diastolic_bp_mmhg, spo2_pct, respiratory_rate_bpm, body_temp_c,
                        dizziness_severity, faintness_presyncope,
                        physical_activity_mins, exercise_performance_pct, muscle_strength_idx,
                        exercise_adherence_pct, musculoskeletal_discomfort,
                        balance_score, coordination_score, spatial_disorientation, visual_disturbance_sans,
                        cabin_temp_c, cabin_pressure_kpa, oxygen_pct, co2_mmhg, co2_ppm,
                        humidity_pct, air_quality_index, env_warning_event,
                        respiratory_symptoms, infection_symptoms, hygiene_adherence_pct, notes
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    """,
                    (
                        cid, ts, day, MissionPhase.MARS_SURFACE.value, 0.38, DataProvenance.SYNTHETIC_DEMO.value,
                        abs_mgy, round(abs_mgy / 24.0, 4), eq_msv, eq_msv, cum_msv,
                        "CREW_ACTIVE_DOSIMETER_BAND (SYNTHETIC)", "SPE_SOLAR_ENERGETIC_PROTON" if day == 179 else "GCR_MARS_SHIELDED",
                        mood, stress, round((mood + (10 - stress)) / 2.0, 1), fatigue,
                        6.5, 7.6, sleep_h, 84.0 if sleep_h >= 7.0 else 72.0, "22:30 - 05:30 UTC-MARS",
                        1 if sleep_h >= 7.0 else 2, 0, 0, 8.0,
                        hr, sys_bp, dia_bp, spo2, resp_rate, temp,
                        dizz, 0, 95.0, 93.0 if dizz == 0 else 80.0, strength, 92.0 if dizz == 0 else 82.0,
                        1 if dizz >= 2 else 0, bal, round(bal + 2.0, 1), 0, int(bool(sans_vis)),
                        21.6, 70.3, 21.1, co2_mmhg, round(co2_mmhg * 1315.0, 0),
                        43.0, 26.0, "CDRA_CO2_ELEVATED" if co2_mmhg >= 3.0 else "NONE",
                        json.dumps([]), json.dumps([]), 96.0, notes,
                    ),
                )
            pday, emot, pstr, mot, fat, sdiff, iso_r, cw, refl = prof["psych"]
            cur.execute(
                """
                INSERT INTO psych_questionnaires (
                    crew_id, timestamp, mission_day, emotional_condition_rating, psychological_stress_rating,
                    motivation_rating, fatigue_rating, sleep_difficulty_rating,
                    isolation_feeling_rating, concentration_workload_rating, journal_reflection, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, "2026-11-14T07:45:00Z", pday, emot, pstr, mot, fat, sdiff, iso_r, cw, refl, DataProvenance.SYNTHETIC_DEMO.value),
            )
    conn.commit()


def _row_to_telemetry_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["feeling_isolated"] = bool(d["feeling_isolated"])
    d["concentration_difficulty"] = bool(d["concentration_difficulty"])
    d["faintness_presyncope"] = bool(d["faintness_presyncope"])
    d["chest_discomfort"] = bool(d.get("chest_discomfort", 0))
    d["palpitations"] = bool(d.get("palpitations", 0))
    d["shortness_of_breath"] = bool(d.get("shortness_of_breath", 0))
    d["spatial_disorientation"] = bool(d["spatial_disorientation"])
    d["visual_disturbance_sans"] = bool(d["visual_disturbance_sans"])
    d.setdefault("respiratory_rate_bpm", 16.0)
    d["respiratory_symptoms"] = json.loads(d["respiratory_symptoms"] or "[]")
    d["infection_symptoms"] = json.loads(d["infection_symptoms"] or "[]")
    d["reported_symptoms"] = json.loads(d.get("reported_symptoms") or "[]")
    return d


def get_active_crew_id() -> str:
    cid = fetch_system_state("active_crew_id")
    return str(cid) if isinstance(cid, str) and cid else "ARES-IV-SUCHAI"


def set_active_crew_id(crew_id: str) -> str:
    crew_baselines = fetch_system_state("crew_baselines") or default_crew_baselines()
    if crew_id not in crew_baselines:
        raise ValueError(f"Unknown crew_id: {crew_id}")
    update_system_state("active_crew_id", crew_id)
    update_system_state("baseline", crew_baselines[crew_id])
    histories = fetch_system_state("crew_baseline_histories") or {}
    update_system_state("baseline_history", histories.get(crew_id, []))
    return crew_id


def fetch_crew_baseline(crew_id: Optional[str] = None) -> Dict[str, Any]:
    cid = crew_id or get_active_crew_id()
    crew_baselines = fetch_system_state("crew_baselines") or default_crew_baselines()
    if cid in crew_baselines:
        return crew_baselines[cid]
    return fetch_system_state("baseline") or AstronautBaseline().model_dump()


def fetch_crew_baseline_history(crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cid = crew_id or get_active_crew_id()
    histories = fetch_system_state("crew_baseline_histories") or {}
    if isinstance(histories, dict) and cid in histories:
        return list(histories[cid])
    if cid == "ARES-IV-SUCHAI":
        h = fetch_system_state("baseline_history")
        return list(h) if isinstance(h, list) else []
    return []


def save_crew_baseline(
    crew_id: str,
    validated_baseline: Dict[str, Any],
    audit_entry: Optional[Dict[str, Any]] = None,
) -> None:
    crew_baselines = fetch_system_state("crew_baselines") or default_crew_baselines()
    crew_baselines[crew_id] = validated_baseline
    update_system_state("crew_baselines", crew_baselines)
    if crew_id == get_active_crew_id():
        update_system_state("baseline", validated_baseline)

    if audit_entry:
        histories = fetch_system_state("crew_baseline_histories") or {}
        if not isinstance(histories, dict):
            histories = {}
        lst = list(histories.get(crew_id) or [])
        lst.insert(0, audit_entry)
        lst = lst[:25]
        histories[crew_id] = lst
        update_system_state("crew_baseline_histories", histories)
        if crew_id == get_active_crew_id():
            update_system_state("baseline_history", lst)


def fetch_all_telemetry(crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM telemetry_records WHERE crew_id = ? ORDER BY mission_day ASC, id ASC",
        (target_crew,),
    )
    rows = [_row_to_telemetry_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_system_state(key: str) -> Any:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value_json FROM system_state WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return json.loads(row["value_json"]) if row else {}


def update_system_state(key: str, value: Any) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO system_state (key, value_json) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    conn.commit()
    conn.close()


def insert_telemetry_record(data: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur.execute(
        """
        INSERT INTO telemetry_records (
            crew_id, timestamp, mission_day, mission_phase, gravity_g, provenance,
            absorbed_dose_mgy, absorbed_dose_rate_mgy_hr, equivalent_dose_msv,
            equivalent_dose_rate_msv_day, cumulative_effective_dose_msv,
            radiation_source, radiation_event_type,
            mood_score, stress_level, emotional_wellbeing, fatigue_level,
            workload_score, social_interaction_score,
            sleep_duration_hrs, sleep_quality_pct, sleep_schedule_window,
            sleep_irregularities, feeling_isolated, concentration_difficulty, motivation_level,
            heart_rate_bpm, systolic_bp_mmhg, diastolic_bp_mmhg, spo2_pct, respiratory_rate_bpm, body_temp_c,
            dizziness_severity, faintness_presyncope, chest_discomfort, palpitations, shortness_of_breath,
            physical_activity_mins, exercise_performance_pct, muscle_strength_idx,
            exercise_adherence_pct, musculoskeletal_discomfort,
            balance_score, coordination_score, spatial_disorientation, visual_disturbance_sans,
            cabin_temp_c, cabin_pressure_kpa, oxygen_pct, co2_mmhg, co2_ppm,
            humidity_pct, air_quality_index, env_warning_event,
            respiratory_symptoms, infection_symptoms, reported_symptoms, hygiene_adherence_pct, notes
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            target_crew,
            now_iso,
            data["mission_day"],
            data["mission_phase"],
            data["gravity_g"],
            data["provenance"],
            data["absorbed_dose_mgy"],
            data["absorbed_dose_rate_mgy_hr"],
            data["equivalent_dose_msv"],
            data["equivalent_dose_rate_msv_day"],
            data["cumulative_effective_dose_msv"],
            data["radiation_source"],
            data["radiation_event_type"],
            data["mood_score"],
            data["stress_level"],
            data["emotional_wellbeing"],
            data["fatigue_level"],
            data["workload_score"],
            data["social_interaction_score"],
            data["sleep_duration_hrs"],
            data["sleep_quality_pct"],
            data["sleep_schedule_window"],
            data["sleep_irregularities"],
            int(bool(data["feeling_isolated"])),
            int(bool(data["concentration_difficulty"])),
            data["motivation_level"],
            data["heart_rate_bpm"],
            data["systolic_bp_mmhg"],
            data["diastolic_bp_mmhg"],
            data["spo2_pct"],
            data.get("respiratory_rate_bpm", 16.0),
            data["body_temp_c"],
            data["dizziness_severity"],
            int(bool(data["faintness_presyncope"])),
            int(bool(data.get("chest_discomfort", False))),
            int(bool(data.get("palpitations", False))),
            int(bool(data.get("shortness_of_breath", False))),
            data["physical_activity_mins"],
            data["exercise_performance_pct"],
            data["muscle_strength_idx"],
            data["exercise_adherence_pct"],
            data["musculoskeletal_discomfort"],
            data["balance_score"],
            data["coordination_score"],
            int(bool(data["spatial_disorientation"])),
            int(bool(data["visual_disturbance_sans"])),
            data["cabin_temp_c"],
            data["cabin_pressure_kpa"],
            data["oxygen_pct"],
            data["co2_mmhg"],
            data["co2_ppm"],
            data["humidity_pct"],
            data["air_quality_index"],
            data["env_warning_event"],
            json.dumps(data.get("respiratory_symptoms", [])),
            json.dumps(data.get("infection_symptoms", [])),
            json.dumps(data.get("reported_symptoms", [])),
            data["hygiene_adherence_pct"],
            data.get("notes", ""),
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT * FROM telemetry_records WHERE id = ?", (new_id,))
    row = _row_to_telemetry_dict(cur.fetchone())
    conn.close()
    return row


def fetch_store_forward_reports() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM store_forward_reports ORDER BY id DESC")
    items = []
    for r in cur.fetchall():
        d = dict(r)
        d["hazard_triggers"] = json.loads(d["hazard_triggers"] or "[]")
        d["payload_json"] = json.loads(d["payload_json"] or "{}")
        items.append(d)
    conn.close()
    return items


def create_store_forward_report(
    mission_day: int,
    title: str,
    summary: str,
    risk_level: str,
    hazard_triggers: List[str],
    payload: Dict[str, Any],
    provenance: str,
    comm_online: bool = False,
    crew_id: Optional[str] = None,
) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Prevent duplicate consecutive identical queued reports
    cur.execute(
        """
        SELECT report_uid, created_at, synced_at, transmission_status
        FROM store_forward_reports
        WHERE crew_id = ? AND mission_day = ? AND title = ? AND summary = ? AND risk_level = ?
        ORDER BY id DESC LIMIT 1
        """,
        (target_crew, mission_day, title, summary, risk_level),
    )
    existing = cur.fetchone()
    if existing and existing["transmission_status"] == "QUEUED_LOCAL_BUFFER" and not comm_online:
        conn.close()
        return {
            "crew_id": target_crew,
            "report_uid": existing["report_uid"],
            "created_at": existing["created_at"],
            "synced_at": existing["synced_at"],
            "mission_day": mission_day,
            "title": title,
            "summary": summary,
            "risk_level": risk_level,
            "hazard_triggers": hazard_triggers,
            "transmission_status": existing["transmission_status"],
            "provenance": provenance,
            "duplicate_prevented": True,
        }

    cur.execute("SELECT COALESCE(MAX(id), 0) as max_id FROM store_forward_reports")
    seq = int(cur.fetchone()["max_id"]) + 1
    uid = f"RPT-SOL-{mission_day}-{seq:03d}"
    status = "SYNCHRONIZED_ACK" if comm_online else "QUEUED_LOCAL_BUFFER"
    synced_at = now_iso if comm_online else None

    cur.execute(
        """
        INSERT INTO store_forward_reports (
            crew_id, report_uid, created_at, synced_at, mission_day, title, summary,
            risk_level, hazard_triggers, transmission_status, provenance, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            uid,
            now_iso,
            synced_at,
            mission_day,
            title,
            summary,
            risk_level,
            json.dumps(hazard_triggers),
            status,
            provenance,
            json.dumps(payload),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "crew_id": target_crew,
        "report_uid": uid,
        "created_at": now_iso,
        "synced_at": synced_at,
        "mission_day": mission_day,
        "title": title,
        "summary": summary,
        "risk_level": risk_level,
        "hazard_triggers": hazard_triggers,
        "transmission_status": status,
        "provenance": provenance,
        "duplicate_prevented": False,
    }


def synchronize_queued_reports() -> Dict[str, Any]:
    comm_state = fetch_system_state("comm_state") or {}
    is_offline = bool(comm_state.get("offline_mode_forced", False)) or (
        "BLACKOUT" in str(comm_state.get("earth_comm_status", "")).upper()
    )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM store_forward_reports WHERE transmission_status != 'SYNCHRONIZED_ACK'")
    pending_before = int(cur.fetchone()["cnt"])

    if is_offline:
        conn.close()
        return {
            "synchronized_count": 0,
            "remaining_queued": pending_before,
            "status": "BLOCKED_OFFLINE",
            "message": "Earth communication is in Offline/Blackout mode; queued reports remain safely preserved locally.",
            "synced_at": comm_state.get("last_sync_timestamp"),
            "comm_state": comm_state,
        }

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur.execute(
        """
        UPDATE store_forward_reports
        SET transmission_status = 'SYNCHRONIZED_ACK', synced_at = ?
        WHERE transmission_status != 'SYNCHRONIZED_ACK'
        """,
        (now_iso,),
    )
    updated_count = int(cur.rowcount or 0)
    conn.commit()
    cur.execute("SELECT COUNT(*) as cnt FROM store_forward_reports WHERE transmission_status != 'SYNCHRONIZED_ACK'")
    remaining = int(cur.fetchone()["cnt"])
    conn.close()

    comm_state["last_sync_timestamp"] = now_iso
    update_system_state("comm_state", comm_state)

    delay_min = float(comm_state.get("one_way_delay_minutes", 0.0) or 0.0)
    mode_note = (
        f"Acknowledged after simulated {delay_min:.1f}-min one-way deep-space transit."
        if delay_min > 0.1
        else "Acknowledged over direct Earth link."
    )
    return {
        "synchronized_count": updated_count,
        "remaining_queued": remaining,
        "status": "SYNCED",
        "message": f"Synchronized {updated_count} report(s). {mode_note}",
        "synced_at": now_iso,
        "comm_state": comm_state,
    }


def fetch_psych_questionnaires(crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM psych_questionnaires WHERE crew_id = ? ORDER BY id DESC",
        (target_crew,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def insert_psych_questionnaire(data: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur.execute(
        """
        INSERT INTO psych_questionnaires (
            crew_id, timestamp, mission_day, emotional_condition_rating, psychological_stress_rating,
            motivation_rating, fatigue_rating, sleep_difficulty_rating,
            isolation_feeling_rating, concentration_workload_rating,
            journal_reflection, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            now_iso,
            data["mission_day"],
            data["emotional_condition_rating"],
            data["psychological_stress_rating"],
            data["motivation_rating"],
            data["fatigue_rating"],
            data["sleep_difficulty_rating"],
            data["isolation_feeling_rating"],
            data["concentration_workload_rating"],
            data.get("journal_reflection", ""),
            data.get("provenance", DataProvenance.USER_ENTERED.value),
        ),
    )
    conn.commit()
    conn.close()
    return {**data, "crew_id": target_crew, "timestamp": now_iso}


def fetch_sans_assessments(crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM sans_assessments WHERE crew_id = ? ORDER BY id DESC",
        (target_crew,),
    )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["wavy_lines_detected"] = bool(d["wavy_lines_detected"])
        d["near_acuity_shift"] = bool(d["near_acuity_shift"])
        d["scotoma_cells"] = json.loads(d.get("scotoma_cells") or "[]")
        out.append(d)
    conn.close()
    return out


def insert_sans_assessment(data: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cells = list(data.get("scotoma_cells") or [])
    cur.execute(
        """
        INSERT INTO sans_assessments (
            crew_id, timestamp, mission_day, eye_tested, wavy_lines_detected,
            scotoma_cells, near_acuity_shift, notes, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            now_iso,
            data["mission_day"],
            data.get("eye_tested", "BOTH"),
            int(bool(data.get("wavy_lines_detected", False))),
            json.dumps(cells),
            int(bool(data.get("near_acuity_shift", False))),
            data.get("notes", ""),
            data.get("provenance", DataProvenance.USER_ENTERED.value),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "crew_id": target_crew,
        "timestamp": now_iso,
        "mission_day": data["mission_day"],
        "eye_tested": data.get("eye_tested", "BOTH"),
        "wavy_lines_detected": bool(data.get("wavy_lines_detected", False)),
        "scotoma_cells": cells,
        "near_acuity_shift": bool(data.get("near_acuity_shift", False)),
        "notes": data.get("notes", ""),
        "provenance": data.get("provenance", DataProvenance.USER_ENTERED.value),
    }


def fetch_medical_kit_items() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medical_kit_items ORDER BY id ASC")
    items = []
    for r in cur.fetchall():
        d = dict(r)
        d["cmo_auth_required"] = bool(d.get("cmo_auth_required", 0))
        items.append(d)
    conn.close()
    return items


def adjust_medical_kit_item(
    item_code: str,
    quantity_delta: Optional[int] = None,
    set_quantity: Optional[int] = None,
    notes: Optional[str] = None,
    mark_inspected: bool = False,
) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medical_kit_items WHERE item_code = ?", (item_code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Unknown medical kit item_code: {item_code}")
    qty = int(row["quantity"])
    if set_quantity is not None:
        qty = max(0, int(set_quantity))
    elif quantity_delta is not None:
        qty = max(0, qty + int(quantity_delta))
    new_notes = notes if notes is not None else row["notes"]
    new_insp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if mark_inspected else row["last_inspected"]
    cur.execute(
        """
        UPDATE medical_kit_items
        SET quantity = ?, notes = ?, last_inspected = ?
        WHERE item_code = ?
        """,
        (qty, new_notes, new_insp, item_code),
    )
    conn.commit()
    cur.execute("SELECT * FROM medical_kit_items WHERE item_code = ?", (item_code,))
    updated = dict(cur.fetchone())
    updated["cmo_auth_required"] = bool(updated.get("cmo_auth_required", 0))
    conn.close()
    return updated


def fetch_device_states(crew_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM device_states WHERE crew_id = ?", (target_crew,))
    out: Dict[str, Dict[str, Any]] = {}
    for r in cur.fetchall():
        d = dict(r)
        out[d["device_id"]] = d
    conn.close()
    return out


def upsert_device_state(
    crew_id: Optional[str],
    device_id: str,
    connection_status: str,
    active_mode: str,
    last_error: str = "",
    last_measurement_at: Optional[str] = None,
) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT last_measurement_at FROM device_states WHERE crew_id = ? AND device_id = ?",
        (target_crew, device_id),
    )
    existing = cur.fetchone()
    eff_last_meas = (
        last_measurement_at
        if last_measurement_at is not None
        else (existing["last_measurement_at"] if existing else "")
    )
    cur.execute(
        """
        INSERT OR REPLACE INTO device_states (
            crew_id, device_id, connection_status, active_mode,
            last_error, last_measurement_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            device_id,
            connection_status,
            active_mode,
            last_error,
            eff_last_meas,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute(
        "SELECT * FROM device_states WHERE crew_id = ? AND device_id = ?",
        (target_crew, device_id),
    )
    out = dict(cur.fetchone())
    conn.close()
    return out


def insert_device_measurements(
    crew_id: Optional[str], items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    cur = conn.cursor()
    inserted: List[Dict[str, Any]] = []
    for item in items:
        meta_json = json.dumps(item.get("metadata") or {})
        cur.execute(
            """
            INSERT INTO device_measurements (
                record_uid, crew_id, device_id, device_name,
                measurement_category, measurement_type, value, value_text, unit,
                recorded_at, connection_method, data_source, connection_status,
                quality_status, quality_note, confirmed, telemetry_field,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["record_uid"],
                target_crew,
                item["device_id"],
                item["device_name"],
                item["measurement_category"],
                item["measurement_type"],
                item.get("value"),
                item.get("value_text"),
                item["unit"],
                item["recorded_at"],
                item["connection_method"],
                item["data_source"],
                item["connection_status"],
                item["quality_status"],
                item.get("quality_note", ""),
                int(bool(item.get("confirmed", True))),
                item.get("telemetry_field"),
                meta_json,
                now_iso,
            ),
        )
        rec = dict(item)
        rec["crew_id"] = target_crew
        rec["confirmed"] = bool(item.get("confirmed", True))
        rec["created_at"] = now_iso
        inserted.append(rec)
    conn.commit()
    conn.close()
    return inserted


def fetch_device_measurements(
    crew_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 80,
) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    if device_id:
        cur.execute(
            "SELECT * FROM device_measurements WHERE crew_id = ? AND device_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, device_id, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM device_measurements WHERE crew_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, limit),
        )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["confirmed"] = bool(d.get("confirmed", 0))
        d["metadata"] = json.loads(d.pop("metadata_json", "{}") or "{}")
        out.append(d)
    conn.close()
    return out


def insert_hardware_examination(
    crew_id: Optional[str], exam: Dict[str, Any]
) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    exam_uid = exam.get("exam_uid") or f"EXM-{target_crew}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    findings = exam.get("findings") or {}
    attachments = exam.get("attachments") or []
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO hardware_examinations (
            exam_uid, crew_id, device_id, device_name, exam_type, mission_day,
            recorded_at, data_source, findings_json, summary_note,
            abnormal_flag, abnormal_reason, attachments_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_uid,
            target_crew,
            exam["device_id"],
            exam["device_name"],
            exam["exam_type"],
            int(exam["mission_day"]),
            exam.get("recorded_at") or now_iso,
            exam.get("data_source", "guided_examination"),
            json.dumps(findings),
            exam.get("summary_note", ""),
            int(bool(exam.get("abnormal_flag", False))),
            exam.get("abnormal_reason", ""),
            json.dumps(attachments),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "exam_uid": exam_uid,
        "crew_id": target_crew,
        "device_id": exam["device_id"],
        "device_name": exam["device_name"],
        "exam_type": exam["exam_type"],
        "mission_day": int(exam["mission_day"]),
        "recorded_at": exam.get("recorded_at") or now_iso,
        "data_source": exam.get("data_source", "guided_examination"),
        "findings": findings,
        "summary_note": exam.get("summary_note", ""),
        "abnormal_flag": bool(exam.get("abnormal_flag", False)),
        "abnormal_reason": exam.get("abnormal_reason", ""),
        "attachments": attachments,
        "created_at": now_iso,
    }


def fetch_hardware_examinations(
    crew_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    if device_id:
        cur.execute(
            "SELECT * FROM hardware_examinations WHERE crew_id = ? AND device_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, device_id, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM hardware_examinations WHERE crew_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, limit),
        )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["abnormal_flag"] = bool(d.get("abnormal_flag", 0))
        d["findings"] = json.loads(d.pop("findings_json", "{}") or "{}")
        d["attachments"] = json.loads(d.pop("attachments_json", "[]") or "[]")
        out.append(d)
    conn.close()
    return out


def insert_biosample_record(
    crew_id: Optional[str], record: Dict[str, Any]
) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sample_uid = record.get("sample_uid") or f"BIO-{target_crew}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    attachments = record.get("attachments") or []
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO biosample_records (
            sample_uid, crew_id, device_id, device_name, specimen_type,
            collection_protocol, mission_day, collected_at, storage_location,
            status, notes, attachments_json, assay_results_json,
            assay_imported_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample_uid,
            target_crew,
            record["device_id"],
            record["device_name"],
            record["specimen_type"],
            record["collection_protocol"],
            int(record["mission_day"]),
            record.get("collected_at") or now_iso,
            record["storage_location"],
            record.get("status", "COLLECTED_STORED"),
            record.get("notes", ""),
            json.dumps(attachments),
            json.dumps(record.get("assay_results") or {}),
            record.get("assay_imported_at", ""),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "sample_uid": sample_uid,
        "crew_id": target_crew,
        "device_id": record["device_id"],
        "device_name": record["device_name"],
        "specimen_type": record["specimen_type"],
        "collection_protocol": record["collection_protocol"],
        "mission_day": int(record["mission_day"]),
        "collected_at": record.get("collected_at") or now_iso,
        "storage_location": record["storage_location"],
        "status": record.get("status", "COLLECTED_STORED"),
        "notes": record.get("notes", ""),
        "attachments": attachments,
        "assay_results": record.get("assay_results") or {},
        "assay_imported_at": record.get("assay_imported_at", ""),
        "created_at": now_iso,
    }


def fetch_biosample_records(
    crew_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    target_crew = crew_id or get_active_crew_id()
    conn = get_conn()
    cur = conn.cursor()
    if device_id:
        cur.execute(
            "SELECT * FROM biosample_records WHERE crew_id = ? AND device_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, device_id, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM biosample_records WHERE crew_id = ? ORDER BY id DESC LIMIT ?",
            (target_crew, limit),
        )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["attachments"] = json.loads(d.pop("attachments_json", "[]") or "[]")
        d["assay_results"] = json.loads(d.pop("assay_results_json", "{}") or "{}")
        out.append(d)
    conn.close()
    return out


def attach_biosample_assay(
    crew_id: Optional[str], sample_uid: str, assay_payload: Dict[str, Any]
) -> Dict[str, Any]:
    target_crew = crew_id or get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM biosample_records WHERE crew_id = ? AND sample_uid = ?",
        (target_crew, sample_uid),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Unknown biosample sample_uid '{sample_uid}' for crew '{target_crew}'")
    cur.execute(
        """
        UPDATE biosample_records
        SET status = 'ASSAY_IMPORTED',
            assay_results_json = ?,
            assay_imported_at = ?
        WHERE crew_id = ? AND sample_uid = ?
        """,
        (json.dumps(assay_payload), now_iso, target_crew, sample_uid),
    )
    conn.commit()
    cur.execute(
        "SELECT * FROM biosample_records WHERE crew_id = ? AND sample_uid = ?",
        (target_crew, sample_uid),
    )
    updated = dict(cur.fetchone())
    updated["attachments"] = json.loads(updated.pop("attachments_json", "[]") or "[]")
    updated["assay_results"] = json.loads(updated.pop("assay_results_json", "{}") or "{}")
    conn.close()
    return updated


def upsert_donki_events(events: List[Dict[str, Any]]) -> int:
    """Persist normalized NASA DONKI space-weather events into local SQLite cache."""
    if not events:
        return 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    cur = conn.cursor()
    saved = 0
    for ev in events:
        event_uid = str(ev.get("event_uid") or "").strip()
        if not event_uid:
            continue
        cur.execute(
            """
            INSERT OR REPLACE INTO donki_events (
                event_uid, service_type, activity_id, start_time, severity,
                regime_scope, title, summary, linked_ids_json, source_url,
                metrics_json, payload_json, data_provenance, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_uid,
                str(ev.get("service_type") or ""),
                str(ev.get("activity_id") or event_uid),
                str(ev.get("start_time") or now_iso),
                str(ev.get("severity") or "INFO"),
                str(ev.get("regime_scope") or "HELIOSPHERIC_DEEP_SPACE"),
                str(ev.get("title") or "DONKI Event"),
                str(ev.get("summary") or ""),
                json.dumps(ev.get("linked_ids") or []),
                str(ev.get("source_url") or ""),
                json.dumps(ev.get("metrics") or {}),
                json.dumps(ev.get("raw_payload") or {}),
                str(ev.get("data_provenance") or "LIVE_NASA_DONKI"),
                str(ev.get("fetched_at") or now_iso),
            ),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def fetch_donki_events(
    service_type: Optional[str] = None,
    limit: int = 120,
) -> List[Dict[str, Any]]:
    """Return cached DONKI events ordered newest-first, without mutating network state."""
    conn = get_conn()
    cur = conn.cursor()
    if service_type and service_type.upper() != "ALL":
        cur.execute(
            """
            SELECT * FROM donki_events
            WHERE service_type = ?
            ORDER BY start_time DESC, event_uid DESC
            LIMIT ?
            """,
            (service_type, limit),
        )
    else:
        cur.execute(
            """
            SELECT * FROM donki_events
            ORDER BY start_time DESC, event_uid DESC
            LIMIT ?
            """,
            (limit,),
        )
    out: List[Dict[str, Any]] = []
    for r in cur.fetchall():
        d = dict(r)
        d["linked_ids"] = json.loads(d.pop("linked_ids_json", "[]") or "[]")
        d["metrics"] = json.loads(d.pop("metrics_json", "{}") or "{}")
        # Keep raw payload compact if needed by caller, parsed from payload_json
        d["raw_payload"] = json.loads(d.pop("payload_json", "{}") or "{}")
        out.append(d)
    conn.close()
    return out


def fetch_donki_service_counts() -> Dict[str, int]:
    """Return count of cached DONKI records per service_type."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT service_type, COUNT(*) AS cnt FROM donki_events GROUP BY service_type")
    counts = {str(r["service_type"]): int(r["cnt"]) for r in cur.fetchall()}
    conn.close()
    return counts


def fetch_donki_sync_meta() -> Dict[str, Any]:
    """Return non-secret DONKI synchronization status and per-service timestamps."""
    stored = fetch_system_state("donki_sync_meta") or {}
    return {
        "last_sync_at": stored.get("last_sync_at", ""),
        "last_sync_status": stored.get("last_sync_status", "NEVER_SYNCED"),
        "last_sync_message": stored.get(
            "last_sync_message",
            "No NASA DONKI sync executed yet. Connect Earth link (Connected or Delayed) and sync to cache official SWRC alerts offline.",
        ),
        "last_window": stored.get("last_window", {"start_date": "", "end_date": ""}),
        "service_statuses": stored.get("service_statuses", {}),
    }


def update_donki_sync_meta(meta: Dict[str, Any]) -> None:
    """Persist non-secret DONKI synchronization status into system_state."""
    update_system_state("donki_sync_meta", meta)


def fetch_donki_secret_config() -> Dict[str, Any]:
    """Return backend-only DONKI configuration (never return directly inside public /api/state)."""
    stored = fetch_system_state("donki_secret_config") or {}
    return {
        "api_key": str(stored.get("api_key") or "").strip(),
        "auto_advisory_in_eva": bool(stored.get("auto_advisory_in_eva", True)),
    }


def update_donki_secret_config(cfg: Dict[str, Any]) -> None:
    """Persist backend-only DONKI configuration into system_state."""
    update_system_state("donki_secret_config", cfg)


def upsert_insight_sols(sols: List[Dict[str, Any]]) -> int:
    """Persist normalized NASA InSight Elysium Planitia per-Sol weather summaries."""
    if not sols:
        return 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    cur = conn.cursor()
    saved = 0
    for row in sols:
        sol_id = str(row.get("sol_id") or "").strip()
        if not sol_id:
            continue
        cur.execute(
            """
            INSERT OR REPLACE INTO insight_weather_sols (
                sol_id, first_utc, last_utc, season, northern_season, southern_season,
                month_ordinal, at_json, hws_json, pre_json, wd_json,
                validity_json, missing_sensors_json, data_provenance, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sol_id,
                str(row.get("first_utc") or ""),
                str(row.get("last_utc") or ""),
                str(row.get("season") or ""),
                str(row.get("northern_season") or ""),
                str(row.get("southern_season") or ""),
                int(row["month_ordinal"]) if row.get("month_ordinal") is not None else None,
                json.dumps(row.get("at") or {}),
                json.dumps(row.get("hws") or {}),
                json.dumps(row.get("pre") or {}),
                json.dumps(row.get("wd") or {}),
                json.dumps(row.get("validity") or {}),
                json.dumps(row.get("missing_sensors") or []),
                str(row.get("data_provenance") or "REAL_NASA_INSIGHT"),
                str(row.get("fetched_at") or now_iso),
            ),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def fetch_insight_sols(limit: int = 30) -> List[Dict[str, Any]]:
    """Return cached InSight Sol weather rows ordered newest Sol first."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM insight_weather_sols
        ORDER BY CAST(sol_id AS INTEGER) DESC
        LIMIT ?
        """,
        (limit,),
    )
    out: List[Dict[str, Any]] = []
    for r in cur.fetchall():
        d = dict(r)
        d["at"] = json.loads(d.pop("at_json", "{}") or "{}")
        d["hws"] = json.loads(d.pop("hws_json", "{}") or "{}")
        d["pre"] = json.loads(d.pop("pre_json", "{}") or "{}")
        d["wd"] = json.loads(d.pop("wd_json", "{}") or "{}")
        d["validity"] = json.loads(d.pop("validity_json", "{}") or "{}")
        d["missing_sensors"] = json.loads(d.pop("missing_sensors_json", "[]") or "[]")
        out.append(d)
    conn.close()
    return out


def fetch_insight_sync_meta() -> Dict[str, Any]:
    """Return non-secret InSight synchronization status."""
    stored = fetch_system_state("insight_sync_meta") or {}
    return {
        "last_sync_at": stored.get("last_sync_at", ""),
        "last_sync_status": stored.get("last_sync_status", "NEVER_SYNCED"),
        "last_sync_message": stored.get(
            "last_sync_message",
            "No NASA InSight Mars Weather sync executed yet. Sync while Earth link is Connected or Delayed to cache Elysium Planitia telemetry offline.",
        ),
        "sol_keys": stored.get("sol_keys", []),
        "endpoint": stored.get(
            "endpoint",
            "https://api.nasa.gov/insight_weather/?feedtype=json&ver=1.0",
        ),
    }


def update_insight_sync_meta(meta: Dict[str, Any]) -> None:
    """Persist InSight synchronization status into system_state."""
    update_system_state("insight_sync_meta", meta)


