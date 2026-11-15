"""
Integrated Astronaut Support Modules for TARS Care:
1. Food & Life-Support Supplies Management (Inventory, Multi-Category Depletion Estimator, Per-Astronaut Nutrition, Alerts)
2. Distance from Earth & Mission Communication Monitoring (Delay Simulator, Offline-First Queue, Message Centre, Sync History)
3. Isolation Support — Private Personal Journal, Self-Reported Mood Tracker & Offline-First Personal AI Companion

100% local-first SQLite persistence + local Ollama LLM inference with deterministic offline fallback.
Preserves all NASA 5-Hazard safety rules: never diagnoses medical/psychiatric conditions, never prescribes medications,
never recommends unsafe/expired food, and suppresses physical exercise suggestions during medical exercise-hold states.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import database
from local_ai_rag import _probe_ollama, get_ai_config, get_local_ai_status
from models import DataProvenance, RiskLevel

FOOD_CATEGORIES = [
    "Freeze-dried meals",
    "Ready-to-eat meals",
    "Snacks",
    "Fruits and vegetables",
    "Protein sources",
    "Beverages",
    "Emergency food supplies",
    "Potable Water & Hydration",
]

MOOD_LEVELS = {
    "Very Positive": 5,
    "Positive": 4,
    "Neutral": 3,
    "Low": 2,
    "Very Low": 1,
}

FEELING_TAGS = [
    "Lonely",
    "Stressed",
    "Tired",
    "Anxious",
    "Motivated",
    "Calm",
    "Homesick",
]

GUIDED_REFLECTION_PROMPTS = [
    "How are you feeling today?",
    "What was the most challenging part of today?",
    "What made you feel positive today?",
    "Are you missing anyone or anything from Earth?",
    "Is there something you would like to talk about?",
    "What are you looking forward to tomorrow?",
    "What was one good moment today?",
    "What would make tomorrow easier?",
    "What achievement are you proud of?",
]

COMM_SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "EARTH_PROXIMITY_LEO": {
        "scenario_id": "EARTH_PROXIMITY_LEO",
        "label": "Earth Proximity (Low-Earth Orbit)",
        "mission_location": "Low-Earth Orbit Departure Staging · 410 km Altitude",
        "mission_destination": "Ares-Horizon IV Orbital Checkout",
        "distance_million_km": 0.0004,
        "one_way_delay_minutes": 0.01,
        "comm_condition": "NORMAL",
        "earth_comm_status": "NOMINAL_DIRECT",
        "offline_mode_forced": False,
        "signal_quality_pct": 99.0,
        "bandwidth_kbps": 12500.0,
        "relay_satellite": "TDRSS Tracking & Data Relay Satellite System → MCC-Houston",
        "next_comm_window_utc": "Continuous near-real-time S/Ka-band relay",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "Near-Earth orbit exhibits negligible light-time latency (< 0.02 s). Real-time voice and telemetry links are available whenever TDRSS relay satellites are in line-of-sight.",
    },
    "LUNAR_CISLUNAR": {
        "scenario_id": "LUNAR_CISLUNAR",
        "label": "Lunar-Distance Mission (Artemis / Gateway)",
        "mission_location": "Lunar Near-Rectilinear Halo Orbit (NRHO) · Cislunar Space",
        "mission_destination": "Lunar South Pole & Cislunar Staging",
        "distance_million_km": 0.384,
        "one_way_delay_minutes": 0.02,
        "comm_condition": "NORMAL",
        "earth_comm_status": "NOMINAL_DIRECT",
        "offline_mode_forced": False,
        "signal_quality_pct": 95.0,
        "bandwidth_kbps": 4200.0,
        "relay_satellite": "Lunar Relay Satellite → Deep Space Network (Goldstone)",
        "next_comm_window_utc": "Continuous cislunar link (1.28 s one-way light time)",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "At ~384,400 km, one-way light travel takes ~1.28 seconds (~2.56 seconds round-trip). Interactive voice conversation with Earth remains feasible except during far-side occultation.",
    },
    "MARS_TRANSIT_CRUISE": {
        "scenario_id": "MARS_TRANSIT_CRUISE",
        "label": "Mars Interplanetary Transit (0g Cruise)",
        "mission_location": "Heliocentric Interplanetary Transfer Orbit (0.00g)",
        "mission_destination": "Mars Jezero-Elysium Frontier",
        "distance_million_km": 145.8,
        "one_way_delay_minutes": 8.1,
        "comm_condition": "DELAYED",
        "earth_comm_status": "NOMINAL_DELAYED",
        "offline_mode_forced": False,
        "signal_quality_pct": 84.0,
        "bandwidth_kbps": 850.0,
        "relay_satellite": "Spacecraft High-Gain X-Band Antenna → DSN Canberra",
        "next_comm_window_utc": "2026-11-15T19:00:00Z (DSN 70m Scheduled Track)",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "Mid-cruise interplanetary distance introduces an 8.1-minute one-way propagation delay (16.2 minutes round-trip). Real-time conversation is impossible; store-and-forward packets and autonomous onboard assessment are required.",
    },
    "MARS_SURFACE_NOMINAL": {
        "scenario_id": "MARS_SURFACE_NOMINAL",
        "label": "Mars Surface Operations (Nominal Delayed)",
        "mission_location": "Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)",
        "mission_destination": "Mars Surface Operations (Ares-Horizon IV)",
        "distance_million_km": 255.4,
        "one_way_delay_minutes": 14.2,
        "comm_condition": "DELAYED",
        "earth_comm_status": "NOMINAL_DELAYED",
        "offline_mode_forced": False,
        "signal_quality_pct": 79.0,
        "bandwidth_kbps": 512.0,
        "relay_satellite": "Ares Mars Relay Orbiter → DSN Madrid Complex",
        "next_comm_window_utc": "2026-11-15T20:15:00Z (Orbiter Overflight Pass #412)",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "On the Martian surface, Earth-Mars distance varies between ~55M km and ~400M km (~4 to 24 minutes one-way delay). At 255.4M km, signals take 14.2 minutes one-way (28.4 minutes round-trip).",
    },
    "MARS_INTERMITTENT_RELAY": {
        "scenario_id": "MARS_INTERMITTENT_RELAY",
        "label": "Mars Surface (Intermittent Dust / Relay Degradation)",
        "mission_location": "Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)",
        "mission_destination": "Mars Surface Operations (Ares-Horizon IV)",
        "distance_million_km": 298.8,
        "one_way_delay_minutes": 16.6,
        "comm_condition": "INTERMITTENT",
        "earth_comm_status": "HIGH_LATENCY_DEGRADED",
        "offline_mode_forced": False,
        "signal_quality_pct": 38.0,
        "bandwidth_kbps": 96.0,
        "relay_satellite": "Low-Elevation Relay Orbiter Pass (Atmospheric Dust Attenuation)",
        "next_comm_window_utc": "2026-11-15T22:40:00Z (Short 11-min High-Elevation Window)",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "High-latency link (16.6 min one-way, 33.2 min round-trip) compounded by orbital relay geometry and regional atmospheric dust attenuation. Packet transfers may drop and require automated queue retry.",
    },
    "MARS_SOLAR_CONJUNCTION": {
        "scenario_id": "MARS_SOLAR_CONJUNCTION",
        "label": "Mars Solar Conjunction (Complete Blackout)",
        "mission_location": "Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)",
        "mission_destination": "Mars Surface Operations (Ares-Horizon IV)",
        "distance_million_km": 378.0,
        "one_way_delay_minutes": 21.0,
        "comm_condition": "BLACKOUT",
        "earth_comm_status": "CONJUNCTION_BLACKOUT",
        "offline_mode_forced": True,
        "signal_quality_pct": 0.0,
        "bandwidth_kbps": 0.0,
        "relay_satellite": "Solar Corona Occlusion — Direct & Relay Links Suspended",
        "next_comm_window_utc": "Post-Conjunction Reacquisition Window (Sol 196)",
        "telemetry_source_type": "SIMULATED_SCENARIO",
        "explanation": "During solar conjunction, the Sun blocks radio transmission between Earth and Mars (~21 min one-way light time, 42 min round-trip). TARS Care operates 100% offline; all health assessments, food logs, journals, and local AI companion conversations continue uninterrupted locally.",
    },
}


def init_support_tables(conn: sqlite3.Connection) -> None:
    """Create tables for Food & Supplies, Mission Communication Centre, and Personal Companion & Journal."""
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_uid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL NOT NULL,
            initial_quantity REAL NOT NULL,
            serving_size TEXT NOT NULL DEFAULT '1 portion',
            unit TEXT NOT NULL,
            calories_per_serving REAL NOT NULL,
            protein_g REAL NOT NULL,
            carbs_g REAL NOT NULL,
            fat_g REAL NOT NULL,
            water_ml_per_serving REAL NOT NULL DEFAULT 0.0,
            micronutrients_json TEXT NOT NULL DEFAULT '{}',
            nutrition_complete INTEGER NOT NULL DEFAULT 1,
            storage_requirements TEXT NOT NULL,
            bay_location TEXT NOT NULL DEFAULT 'Galley G1',
            expiry_sol INTEGER NOT NULL,
            expiry_date TEXT NOT NULL,
            shelf_life_days INTEGER NOT NULL DEFAULT 540,
            added_sol INTEGER NOT NULL DEFAULT 1,
            date_added TEXT NOT NULL,
            food_source TEXT NOT NULL,
            min_threshold REAL NOT NULL DEFAULT 10.0,
            critical_threshold REAL NOT NULL DEFAULT 4.0,
            daily_ration_per_astronaut REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'AVAILABLE',
            provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS food_consumption_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consumption_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            meal_type TEXT NOT NULL,
            food_item_uid TEXT NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity_consumed REAL NOT NULL,
            unit TEXT NOT NULL,
            calories REAL NOT NULL,
            protein_g REAL NOT NULL,
            carbs_g REAL NOT NULL,
            fat_g REAL NOT NULL,
            water_ml REAL NOT NULL DEFAULT 0.0,
            micronutrients_json TEXT NOT NULL DEFAULT '{}',
            is_estimated_nutrition INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            provenance TEXT NOT NULL DEFAULT 'USER_ENTERED',
            recorded_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crew_nutrition_targets (
            crew_id TEXT PRIMARY KEY,
            calories_target_kcal REAL NOT NULL,
            protein_target_g REAL NOT NULL,
            carbs_target_g REAL NOT NULL,
            fat_target_g REAL NOT NULL,
            water_target_ml REAL NOT NULL,
            vitamin_d_target_iu REAL NOT NULL DEFAULT 800.0,
            calcium_target_mg REAL NOT NULL DEFAULT 1200.0,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS resupply_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resupply_uid TEXT UNIQUE NOT NULL,
            mission_day INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            food_item_uid TEXT NOT NULL,
            food_name TEXT NOT NULL,
            quantity_delta REAL NOT NULL,
            quantity_after REAL NOT NULL,
            unit TEXT NOT NULL,
            source TEXT NOT NULL,
            authorised_by TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
            recorded_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS comm_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            recipient TEXT NOT NULL DEFAULT 'Earth Mission Control & Flight Surgeons (MCC-Houston)',
            message_type TEXT NOT NULL DEFAULT 'MISSION_CONTROL_MESSAGE',
            priority TEXT NOT NULL DEFAULT 'NORMAL',
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Queued',
            one_way_delay_minutes REAL NOT NULL DEFAULT 14.2,
            round_trip_delay_minutes REAL NOT NULL DEFAULT 28.4,
            distance_million_km REAL NOT NULL DEFAULT 255.4,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sent_at TEXT,
            acknowledged_at TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            failure_reason TEXT NOT NULL DEFAULT '',
            linked_report_uid TEXT NOT NULL DEFAULT '',
            provenance TEXT NOT NULL DEFAULT 'USER_ENTERED'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_uid TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            comm_condition TEXT NOT NULL,
            one_way_delay_minutes REAL NOT NULL,
            round_trip_delay_minutes REAL NOT NULL,
            distance_million_km REAL NOT NULL,
            messages_attempted INTEGER NOT NULL,
            messages_sent INTEGER NOT NULL,
            messages_failed INTEGER NOT NULL,
            reports_synced INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            mood TEXT NOT NULL DEFAULT '',
            feelings_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            guided_prompt TEXT NOT NULL DEFAULT '',
            is_private INTEGER NOT NULL DEFAULT 1,
            allow_ai_access INTEGER NOT NULL DEFAULT 0,
            provenance TEXT NOT NULL DEFAULT 'USER_ENTERED',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mood_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checkin_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            mission_day INTEGER NOT NULL,
            mood TEXT NOT NULL,
            mood_numeric INTEGER NOT NULL,
            feelings_json TEXT NOT NULL DEFAULT '[]',
            note TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'SELF_REPORTED',
            provenance TEXT NOT NULL DEFAULT 'USER_ENTERED',
            recorded_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_privacy_settings (
            crew_id TEXT PRIMARY KEY,
            allow_ai_journal_context INTEGER NOT NULL DEFAULT 0,
            allow_ai_mood_context INTEGER NOT NULL DEFAULT 1,
            allow_ai_mission_telemetry_context INTEGER NOT NULL DEFAULT 1,
            store_companion_history INTEGER NOT NULL DEFAULT 1,
            preferred_topics_json TEXT NOT NULL DEFAULT '["Astronomy & Planetary Science", "Music & Reading", "Habitat Gardening", "Earth Memories"]',
            escalation_contact_role TEXT NOT NULL DEFAULT 'Crew Medical Officer (Dr. Elena Vance) & Mission Commander',
            escalation_procedure_note TEXT NOT NULL DEFAULT 'Onboard Private CMO Peer Support & Store-and-Forward Flight Surgeon Behavioral Consult Protocol (PROC-BEHAV-SAFE-01)',
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS companion_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_uid TEXT UNIQUE NOT NULL,
            crew_id TEXT NOT NULL,
            title TEXT NOT NULL,
            conversation_mode TEXT NOT NULL DEFAULT 'COMPANION_CHAT',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS companion_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_uid TEXT UNIQUE NOT NULL,
            conversation_uid TEXT NOT NULL,
            crew_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            engine_used TEXT NOT NULL,
            safety_escalation_triggered INTEGER NOT NULL DEFAULT 0,
            support_tier TEXT NOT NULL DEFAULT 'ORDINARY_COMPANIONSHIP',
            suggested_coping_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    _seed_support_modules_if_empty(conn)


def _compute_food_item_status(
    quantity: float,
    min_threshold: float,
    critical_threshold: float,
    expiry_sol: int,
    current_sol: int = 184,
) -> str:
    if quantity <= 0.0:
        return "CRITICAL"
    if expiry_sol < current_sol:
        return "EXPIRED"
    if quantity <= critical_threshold:
        return "CRITICAL"
    if (expiry_sol - current_sol) <= 14:
        return "EXPIRING_SOON"
    if quantity <= min_threshold:
        return "RUNNING_LOW"
    return "AVAILABLE"


def _seed_support_modules_if_empty(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # 1. Seed mission food configuration in system_state if absent
    cur.execute("SELECT value_json FROM system_state WHERE key = 'food_mission_config'")
    if not cur.fetchone():
        food_cfg = {
            "crew_count": 4,
            "current_mission_sol": 184,
            "planned_mission_end_sol": 260,
            "next_resupply_sol": 240,
            "next_resupply_label": "Pre-Positioned Surface Cargo Module B (Sol 240)",
            "portions_per_astronaut_per_day": 3.0,
            "water_liters_per_astronaut_per_day": 2.6,
            "water_warning_threshold_liters": 180.0,
        }
        cur.execute(
            "INSERT OR REPLACE INTO system_state (key, value_json) VALUES ('food_mission_config', ?)",
            (json.dumps(food_cfg),),
        )

    # Ensure extended comm_state fields exist
    cur.execute("SELECT value_json FROM system_state WHERE key = 'comm_state'")
    crow = cur.fetchone()
    if crow:
        cstate = json.loads(crow["value_json"])
        changed = False
        defaults = {
            "scenario_id": "MARS_SURFACE_NOMINAL",
            "mission_location": "Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)",
            "mission_destination": "Mars Surface Operations (Ares-Horizon IV)",
            "comm_condition": "DELAYED",
            "round_trip_delay_minutes": round(float(cstate.get("one_way_delay_minutes", 14.2)) * 2.0, 2),
            "signal_quality_pct": 79.0,
            "bandwidth_kbps": 512.0,
            "relay_satellite": "Ares Mars Relay Orbiter → DSN Madrid Complex",
            "last_successful_comm": "2026-11-14T04:15:00Z",
            "next_comm_window_utc": "2026-11-15T20:15:00Z (Orbiter Overflight Pass #412)",
            "telemetry_source_type": "CONFIGURED_SIMULATION",
        }
        for k, v in defaults.items():
            if k not in cstate:
                cstate[k] = v
                changed = True
        if changed:
            cur.execute(
                "INSERT OR REPLACE INTO system_state (key, value_json) VALUES ('comm_state', ?)",
                (json.dumps(cstate),),
            )

    # 2. Seed crew_nutrition_targets
    cur.execute("SELECT COUNT(*) as cnt FROM crew_nutrition_targets")
    if cur.fetchone()["cnt"] == 0:
        targets = [
            ("ARES-IV-SUCHAI", 2850.0, 115.0, 360.0, 95.0, 2600.0, 800.0, 1200.0, "Mission Commander · Surface EVA & ARED resistive profile", "2026-11-14T08:00:00Z"),
            ("ARES-IV-VANCE", 2550.0, 102.0, 320.0, 85.0, 2400.0, 800.0, 1200.0, "Crew Medical Officer · Habitat biomedical operations profile", "2026-11-14T08:00:00Z"),
            ("ARES-IV-CHEN", 3100.0, 130.0, 395.0, 102.0, 2900.0, 1000.0, 1300.0, "Flight Engineer · Heavy airlock & EVA maintenance profile", "2026-11-14T08:00:00Z"),
            ("ARES-IV-OKAFOR", 2650.0, 106.0, 335.0, 88.0, 2500.0, 800.0, 1200.0, "Planetary Astrobiologist · Surface geology & lab profile", "2026-11-14T08:00:00Z"),
        ]
        for t in targets:
            cur.execute(
                """
                INSERT INTO crew_nutrition_targets (
                    crew_id, calories_target_kcal, protein_target_g, carbs_target_g,
                    fat_target_g, water_target_ml, vitamin_d_target_iu, calcium_target_mg,
                    notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                t,
            )

    # 3. Seed realistic Mars habitat food inventory (clearly labelled SYNTHETIC_DEMO)
    cur.execute("SELECT COUNT(*) as cnt FROM food_items")
    if cur.fetchone()["cnt"] == 0:
        seed_items = [
            (
                "FOOD-FD-001",
                "Freeze-Dried Chicken Teriyaki & Brown Rice",
                "Freeze-dried meals",
                420.0,
                600.0,
                "1 rehydratable pouch (240g prepared)",
                "portions",
                520.0,
                34.0,
                62.0,
                14.0,
                180.0,
                json.dumps({"vitamin_d_iu": 240, "calcium_mg": 180, "iron_mg": 4.2, "potassium_mg": 540, "sodium_mg": 460}),
                1,
                "Ambient Dry Galley Rack (18–24°C, <50% RH)",
                "Galley G1 · Bay A",
                420,
                "2027-07-08",
                730,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                80.0,
                30.0,
                1.5,
                "High-protein primary entrée; rehydrate with 180 mL hot potable water.",
            ),
            (
                "FOOD-FD-002",
                "Freeze-Dried Lentil Curry & Quinoa",
                "Freeze-dried meals",
                360.0,
                520.0,
                "1 rehydratable pouch (250g prepared)",
                "portions",
                490.0,
                24.0,
                71.0,
                12.0,
                200.0,
                json.dumps({"vitamin_d_iu": 180, "calcium_mg": 210, "iron_mg": 6.5, "potassium_mg": 620, "sodium_mg": 390}),
                1,
                "Ambient Dry Galley Rack (18–24°C, <50% RH)",
                "Galley G1 · Bay B",
                410,
                "2027-06-28",
                730,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                70.0,
                25.0,
                1.0,
                "Plant-forward main meal rich in dietary fiber, iron, and potassium.",
            ),
            (
                "FOOD-RTE-003",
                "Thermostabilized Wild Salmon & Sweet Potato",
                "Ready-to-eat meals",
                195.0,
                320.0,
                "1 retort pouch (210g)",
                "portions",
                540.0,
                36.0,
                44.0,
                24.0,
                85.0,
                json.dumps({"vitamin_d_iu": 520, "calcium_mg": 260, "iron_mg": 3.1, "potassium_mg": 590, "sodium_mg": 420}),
                1,
                "Ambient Galley Locker (15–23°C)",
                "Galley G2 · Bay A",
                340,
                "2027-04-18",
                540,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                60.0,
                20.0,
                0.8,
                "Omega-3 and Vitamin D fortified ready-to-eat pouch supporting CSA TBone skeletal & vascular health.",
            ),
            (
                "FOOD-SNK-004",
                "High-Calorie Almond & Cranberry EVA Energy Bars",
                "Snacks",
                148.0,
                280.0,
                "1 fortified bar (85g)",
                "bars",
                360.0,
                12.0,
                46.0,
                15.0,
                0.0,
                json.dumps({"vitamin_d_iu": 160, "calcium_mg": 240, "iron_mg": 3.4, "potassium_mg": 310, "sodium_mg": 190}),
                1,
                "Ambient / EVA Prep Locker A2",
                "Galley G2 · Bay C",
                365,
                "2027-05-13",
                540,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                50.0,
                20.0,
                1.0,
                "Compact ration bar for pre-EVA energy and afternoon caloric bridging.",
            ),
            (
                "FOOD-FV-005",
                "Veggie Chamber Fresh Mizuna Greens & Cherry Tomatoes",
                "Fruits and vegetables",
                14.0,
                40.0,
                "1 fresh harvest bowl (95g)",
                "bowls",
                65.0,
                2.8,
                12.0,
                0.8,
                75.0,
                json.dumps({"vitamin_c_mg": 48, "calcium_mg": 65, "potassium_mg": 290}),
                0,
                "Cold Stowage MELFI-C (4°C · Consume within 12 Sols of harvest)",
                "Hydroponic Bay V1",
                191,
                "2026-11-21",
                14,
                177,
                "2026-11-07T10:00:00Z",
                "Veggie Habitat Chamber Harvest (Simulated Demo)",
                20.0,
                6.0,
                0.5,
                "Fresh habitat-grown produce; micronutrient values partially estimated from Veggie batch weight.",
            ),
            (
                "FOOD-PRO-006",
                "Whey & Pea Leucine Bone-Support Protein Packets",
                "Protein sources",
                110.0,
                220.0,
                "1 single-serve packet (42g)",
                "packets",
                180.0,
                32.0,
                6.0,
                3.0,
                250.0,
                json.dumps({"vitamin_d_iu": 400, "calcium_mg": 450, "iron_mg": 2.5, "potassium_mg": 220, "sodium_mg": 180}),
                1,
                "Ambient Dry Locker G3",
                "Galley G3 · Bay A",
                194,
                "2026-11-24",
                365,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                40.0,
                15.0,
                0.8,
                "Post-ARED exercise recovery protein with Vitamin D3 & Calcium; Lot #A1 approaching expiry window.",
            ),
            (
                "FOOD-BEV-007",
                "Isotonic Electrolyte & Vitamin C Hydration Mix",
                "Beverages",
                210.0,
                360.0,
                "1 drink pouch (350 mL prepared)",
                "pouches",
                90.0,
                0.0,
                22.0,
                0.0,
                350.0,
                json.dumps({"vitamin_c_mg": 90, "calcium_mg": 80, "potassium_mg": 380, "sodium_mg": 520}),
                1,
                "Ambient Galley & Airlock Hydration Rack",
                "Galley G1 · Bay D",
                450,
                "2027-08-07",
                730,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Cargo (Simulated Demo)",
                60.0,
                24.0,
                1.2,
                "Supports plasma volume retention in 0.38g Mars gravity and post-EVA rehydration.",
            ),
            (
                "FOOD-EMG-008",
                "High-Density Emergency Storm-Shelter Ration Blocks",
                "Emergency food supplies",
                96.0,
                96.0,
                "1 compressed ration block (1000 kcal)",
                "blocks",
                1000.0,
                28.0,
                125.0,
                42.0,
                0.0,
                json.dumps({"vitamin_d_iu": 400, "calcium_mg": 400, "iron_mg": 8.0, "potassium_mg": 700, "sodium_mg": 650}),
                1,
                "Radiation Storm Shelter Core · Sealed Foil Locker S2",
                "Storm Shelter S2",
                900,
                "2028-10-30",
                1825,
                1,
                "2026-05-15T08:00:00Z",
                "Pre-Positioned Ares-IV Contingency Reserve (Simulated Demo)",
                48.0,
                24.0,
                0.25,
                "5-year shelf-life contingency rations reserved for Solar Particle Event shelter lock-ins or galley failure.",
            ),
            (
                "FOOD-WAT-009",
                "ECLSS Recycled & Mineralized Potable Water Reserve",
                "Potable Water & Hydration",
                840.0,
                1000.0,
                "1 Liter (1000 mL)",
                "L",
                0.0,
                0.0,
                0.0,
                0.0,
                1000.0,
                json.dumps({"calcium_mg": 35, "magnesium_mg": 12, "potassium_mg": 10, "sodium_mg": 15}),
                1,
                "Water-Wall Shielding Bladder Tank W1 & Galley Dispenser",
                "ECLSS Tank W1",
                999,
                "2029-12-31",
                1825,
                1,
                "2026-05-15T08:00:00Z",
                "ECLSS Water Processor Assembly + ISRU Buffer (Simulated Demo)",
                240.0,
                120.0,
                2.6,
                "Closed-loop potable water reserve (~88% recovery efficiency); doubles as radiation shielding mass.",
            ),
        ]
        for row in seed_items:
            (
                uid, name, cat, qty, init_qty, srv, unit, kcal, pro, carb, fat, wat,
                micro, comp, stor, bay, exp_sol, exp_date, shelf, add_sol, add_date,
                src, min_t, crit_t, ration, notes
            ) = row
            st = _compute_food_item_status(qty, min_t, crit_t, exp_sol, 184)
            cur.execute(
                """
                INSERT INTO food_items (
                    item_uid, name, category, quantity, initial_quantity, serving_size, unit,
                    calories_per_serving, protein_g, carbs_g, fat_g, water_ml_per_serving,
                    micronutrients_json, nutrition_complete, storage_requirements, bay_location,
                    expiry_sol, expiry_date, shelf_life_days, added_sol, date_added,
                    food_source, min_threshold, critical_threshold, daily_ration_per_astronaut,
                    status, provenance, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid, name, cat, qty, init_qty, srv, unit, kcal, pro, carb, fat, wat,
                    micro, comp, stor, bay, exp_sol, exp_date, shelf, add_sol, add_date,
                    src, min_t, crit_t, ration, st, DataProvenance.SYNTHETIC_DEMO.value,
                    notes, "2026-11-14T08:00:00Z",
                ),
            )

    # 4. Seed food consumption records for Sols 182–184
    cur.execute("SELECT COUNT(*) as cnt FROM food_consumption_records")
    if cur.fetchone()["cnt"] == 0:
        seed_cons = [
            ("CONS-182-01", "ARES-IV-SUCHAI", 182, "Breakfast", "FOOD-FD-002", "Freeze-Dried Lentil Curry & Quinoa", "Freeze-dried meals", 1.0, "portions", 490.0, 24.0, 71.0, 12.0, 450.0, json.dumps({"vitamin_d_iu": 180, "calcium_mg": 210}), 0, "Morning meal before sample shift", "SYNTHETIC_DEMO", "2026-11-12T07:15:00Z"),
            ("CONS-182-02", "ARES-IV-SUCHAI", 182, "Lunch", "FOOD-FD-001", "Freeze-Dried Chicken Teriyaki & Brown Rice", "Freeze-dried meals", 1.5, "portions", 780.0, 51.0, 93.0, 21.0, 600.0, json.dumps({"vitamin_d_iu": 360, "calcium_mg": 270}), 0, "Mid-sol galley meal", "SYNTHETIC_DEMO", "2026-11-12T13:00:00Z"),
            ("CONS-182-03", "ARES-IV-SUCHAI", 182, "Dinner", "FOOD-RTE-003", "Thermostabilized Wild Salmon & Sweet Potato", "Ready-to-eat meals", 1.5, "portions", 810.0, 54.0, 66.0, 36.0, 750.0, json.dumps({"vitamin_d_iu": 780, "calcium_mg": 390}), 0, "Post-ARED recovery dinner", "SYNTHETIC_DEMO", "2026-11-12T19:30:00Z"),
            ("CONS-182-04", "ARES-IV-SUCHAI", 182, "Snack / EVA Ration", "FOOD-SNK-004", "High-Calorie Almond & Cranberry EVA Energy Bars", "Snacks", 2.0, "bars", 720.0, 24.0, 92.0, 30.0, 700.0, json.dumps({"vitamin_d_iu": 320, "calcium_mg": 480}), 0, "Afternoon EVA prep bars + water", "SYNTHETIC_DEMO", "2026-11-12T16:00:00Z"),
            ("CONS-183-01", "ARES-IV-SUCHAI", 183, "Breakfast", "FOOD-FD-001", "Freeze-Dried Chicken Teriyaki & Brown Rice", "Freeze-dried meals", 1.0, "portions", 520.0, 34.0, 62.0, 14.0, 500.0, json.dumps({"vitamin_d_iu": 240, "calcium_mg": 180}), 0, "Morning ration", "SYNTHETIC_DEMO", "2026-11-13T07:20:00Z"),
            ("CONS-183-02", "ARES-IV-SUCHAI", 183, "Lunch", "FOOD-RTE-003", "Thermostabilized Wild Salmon & Sweet Potato", "Ready-to-eat meals", 1.5, "portions", 810.0, 54.0, 66.0, 36.0, 650.0, json.dumps({"vitamin_d_iu": 780, "calcium_mg": 390}), 0, "Mid-sol meal after airlock work", "SYNTHETIC_DEMO", "2026-11-13T13:15:00Z"),
            ("CONS-183-03", "ARES-IV-SUCHAI", 183, "Dinner", "FOOD-FD-002", "Freeze-Dried Lentil Curry & Quinoa", "Freeze-dried meals", 1.5, "portions", 735.0, 36.0, 106.5, 18.0, 650.0, json.dumps({"vitamin_d_iu": 270, "calcium_mg": 315}), 0, "Evening meal", "SYNTHETIC_DEMO", "2026-11-13T19:45:00Z"),
            ("CONS-183-04", "ARES-IV-SUCHAI", 183, "Hydration", "FOOD-BEV-007", "Isotonic Electrolyte & Vitamin C Hydration Mix", "Beverages", 2.0, "pouches", 180.0, 0.0, 44.0, 0.0, 700.0, json.dumps({"vitamin_c_mg": 180, "calcium_mg": 160}), 0, "Electrolyte rehydration", "SYNTHETIC_DEMO", "2026-11-13T17:00:00Z"),
            ("CONS-184-01", "ARES-IV-SUCHAI", 184, "Breakfast", "FOOD-FD-001", "Freeze-Dried Chicken Teriyaki & Brown Rice", "Freeze-dried meals", 1.0, "portions", 520.0, 34.0, 62.0, 14.0, 500.0, json.dumps({"vitamin_d_iu": 240, "calcium_mg": 180}), 0, "Sol 184 breakfast ration", "SYNTHETIC_DEMO", "2026-11-14T07:10:00Z"),
            ("CONS-184-02", "ARES-IV-SUCHAI", 184, "Lunch", "FOOD-RTE-003", "Thermostabilized Wild Salmon & Sweet Potato", "Ready-to-eat meals", 1.0, "portions", 540.0, 36.0, 44.0, 24.0, 600.0, json.dumps({"vitamin_d_iu": 520, "calcium_mg": 260}), 0, "Sol 184 lunch pouch", "SYNTHETIC_DEMO", "2026-11-14T12:40:00Z"),
            ("CONS-184-03", "ARES-IV-SUCHAI", 184, "Snack / EVA Ration", "FOOD-FV-005", "Veggie Chamber Fresh Mizuna Greens & Cherry Tomatoes", "Fruits and vegetables", 1.0, "bowls", 65.0, 2.8, 12.0, 0.8, 350.0, json.dumps({"vitamin_c_mg": 48, "calcium_mg": 65}), 1, "Fresh Veggie greens with lunch (estimated label)", "SYNTHETIC_DEMO", "2026-11-14T12:55:00Z"),
            ("CONS-184-04", "ARES-IV-SUCHAI", 184, "Hydration", "FOOD-BEV-007", "Isotonic Electrolyte & Vitamin C Hydration Mix", "Beverages", 2.0, "pouches", 180.0, 0.0, 44.0, 0.0, 700.0, json.dumps({"vitamin_c_mg": 180, "calcium_mg": 160}), 0, "Mid-sol electrolyte drink pouches", "SYNTHETIC_DEMO", "2026-11-14T15:10:00Z"),
        ]
        for c in seed_cons:
            cur.execute(
                """
                INSERT INTO food_consumption_records (
                    consumption_uid, crew_id, mission_day, meal_type, food_item_uid,
                    food_name, category, quantity_consumed, unit, calories, protein_g,
                    carbs_g, fat_g, water_ml, micronutrients_json, is_estimated_nutrition,
                    notes, provenance, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                c,
            )

    # 5. Seed resupply_records
    cur.execute("SELECT COUNT(*) as cnt FROM resupply_records")
    if cur.fetchone()["cnt"] == 0:
        seed_resupply = [
            ("RSP-SOL-165-01", 165, "RESUPPLY_DELIVERY", "FOOD-FD-001", "Freeze-Dried Chicken Teriyaki & Brown Rice", 120.0, 480.0, "portions", "Ares-IV Cargo Pallet B1 Transfer", "SuChai (Mission Commander)", "Transferred 120 portions from Cargo Module B1 into Galley G1.", "SYNTHETIC_DEMO", "2026-10-26T10:00:00Z"),
            ("RSP-SOL-177-02", 177, "VEGGIE_HARVEST", "FOOD-FV-005", "Veggie Chamber Fresh Mizuna Greens & Cherry Tomatoes", 24.0, 24.0, "bowls", "Veggie Hydroponic Growth Chamber V1", "Dr. Amina Okafor (Astrobiologist)", "Harvested Sol 177 Mizuna & dwarf cherry tomato crop.", "SYNTHETIC_DEMO", "2026-11-07T10:00:00Z"),
            ("RSP-SOL-180-03", 180, "RESUPPLY_DELIVERY", "FOOD-WAT-009", "ECLSS Recycled & Mineralized Potable Water Reserve", 65.0, 860.0, "L", "ISRU Sabatier / Subsurface Ice Melt Batch #4", "Marcus Chen (Flight Engineer)", "Verified conductivity, pH, and silver-biocide mineralization before bladder transfer.", "SYNTHETIC_DEMO", "2026-11-10T15:30:00Z"),
        ]
        for r in seed_resupply:
            cur.execute(
                """
                INSERT INTO resupply_records (
                    resupply_uid, mission_day, event_type, food_item_uid, food_name,
                    quantity_delta, quantity_after, unit, source, authorised_by,
                    notes, provenance, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )

    # 6. Seed comm_messages and sync_history
    cur.execute("SELECT COUNT(*) as cnt FROM comm_messages")
    if cur.fetchone()["cnt"] == 0:
        seed_msgs = [
            (
                "MSG-SOL-179-001",
                "ARES-IV-SUCHAI",
                "SuChai (Mission Commander)",
                "Earth Mission Control & Flight Surgeons (MCC-Houston)",
                "HEALTH_REPORT",
                "IMPORTANT",
                "Sol 179 SPE Storm Shelter Dosimetry & Crew Verification",
                "All 4 crew sheltered inside polyethylene water-wall core during SEP event. Peak rate 2.95 mSv/day (1.15 mGy absorbed). All crew vitals nominal.",
                "Sent",
                13.8,
                27.6,
                248.2,
                "2026-11-09T18:20:00Z",
                "2026-11-09T19:05:00Z",
                "2026-11-09T18:22:00Z",
                "2026-11-09T19:05:00Z",
                0,
                "",
                "RPT-SOL-179-SPE",
                "SYNTHETIC_DEMO",
            ),
            (
                "MSG-SOL-184-002",
                "ARES-IV-SUCHAI",
                "SuChai (Mission Commander)",
                "Earth Mission Control & Flight Surgeons (MCC-Houston)",
                "HEALTH_REPORT",
                "IMPORTANT",
                "Sol 184 Multi-Hazard Health & ECLSS CO2 Status Packet",
                "Queued Sol 184 integrated telemetry: Cabin CO2 at 3.4 mmHg prior to CDRA bed switchover; sleep 5.7h; resting HR 73 bpm (+15 vs baseline in 0.38g).",
                "Queued",
                14.2,
                28.4,
                255.4,
                "2026-11-14T08:05:00Z",
                "2026-11-14T08:05:00Z",
                None,
                None,
                0,
                "",
                "RPT-SOL-184-MULTI",
                "SYNTHETIC_DEMO",
            ),
            (
                "MSG-SOL-184-003",
                "ARES-IV-SUCHAI",
                "SuChai (Mission Commander)",
                "Earth Logistics & Nutritional Support Desk",
                "SUPPLY_REPORT",
                "NORMAL",
                "Sol 184 Galley Inventory & Veggie Fresh Crop Update",
                "Galley audit complete. Main freeze-dried & thermostabilized meal reserves remain on track for Sol 240 cargo module transfer. Fresh Mizuna greens running low (14 bowls remaining).",
                "Draft",
                14.2,
                28.4,
                255.4,
                "2026-11-14T09:15:00Z",
                "2026-11-14T09:15:00Z",
                None,
                None,
                0,
                "",
                "",
                "SYNTHETIC_DEMO",
            ),
        ]
        for m in seed_msgs:
            cur.execute(
                """
                INSERT INTO comm_messages (
                    message_uid, crew_id, sender_name, recipient, message_type, priority,
                    subject, body, status, one_way_delay_minutes, round_trip_delay_minutes,
                    distance_million_km, created_at, updated_at, sent_at, acknowledged_at,
                    retry_count, failure_reason, linked_report_uid, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                m,
            )

    cur.execute("SELECT COUNT(*) as cnt FROM sync_history")
    if cur.fetchone()["cnt"] == 0:
        cur.execute(
            """
            INSERT INTO sync_history (
                sync_uid, timestamp, mission_day, comm_condition, one_way_delay_minutes,
                round_trip_delay_minutes, distance_million_km, messages_attempted,
                messages_sent, messages_failed, reports_synced, status, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SYNC-SOL-179-01",
                "2026-11-09T19:05:00Z",
                179,
                "DELAYED",
                13.8,
                27.6,
                248.2,
                1,
                1,
                0,
                1,
                "SUCCESS",
                "Synchronized 1 health report and 1 mission control message across 13.8-min one-way (27.6-min round-trip) DSN link.",
            ),
        )

    # 7. Seed user_privacy_settings for all crew members
    cur.execute("SELECT COUNT(*) as cnt FROM user_privacy_settings")
    if cur.fetchone()["cnt"] == 0:
        for cid in ("ARES-IV-SUCHAI", "ARES-IV-VANCE", "ARES-IV-CHEN", "ARES-IV-OKAFOR"):
            cur.execute(
                """
                INSERT INTO user_privacy_settings (
                    crew_id, allow_ai_journal_context, allow_ai_mood_context,
                    allow_ai_mission_telemetry_context, store_companion_history,
                    preferred_topics_json, escalation_contact_role,
                    escalation_procedure_note, updated_at
                ) VALUES (?, 0, 1, 1, 1, ?, ?, ?, ?)
                """,
                (
                    cid,
                    json.dumps(["Astronomy & Planetary Science", "Music & Reading", "Habitat Gardening", "Earth Memories"]),
                    "Crew Medical Officer (Dr. Elena Vance) & Mission Commander",
                    "Onboard Private CMO Peer Support & Store-and-Forward Flight Surgeon Behavioral Consult Protocol (PROC-BEHAV-SAFE-01)",
                    "2026-11-14T08:00:00Z",
                ),
            )

    # 8. Seed initial private journal entries and self-reported mood check-ins for SuChai
    cur.execute("SELECT COUNT(*) as cnt FROM journal_entries")
    if cur.fetchone()["cnt"] == 0:
        seed_journals = [
            (
                "JRN-SOL-178-01",
                "ARES-IV-SUCHAI",
                178,
                "Watching Earth Rise Like a Pale Blue Star Above Elysium",
                "Stepped near the viewport after finishing habitat deployment checks. Earth is just a tiny point of light now, more than 250 million kilometres away. I miss Sunday mornings with family back on Earth, but sharing tea with Elena, Marcus, and Amina after dinner made the habitat feel warm and grounded.",
                "Positive",
                json.dumps(["Calm", "Homesick", "Motivated"]),
                json.dumps(["Earth Memories", "Crew Moment", "Daily Reflection"]),
                "Are you missing anyone or anything from Earth?",
                1,
                0,
                "SYNTHETIC_DEMO",
                "2026-11-08T21:10:00Z",
                "2026-11-08T21:10:00Z",
            ),
            (
                "JRN-SOL-181-02",
                "ARES-IV-SUCHAI",
                181,
                "First Geological EVA Walk on Martian Regolith",
                "Completed our first full surface geological traverse today. Walking in 0.38g takes a deliberate rhythm, yet collecting basalts alongside Amina felt like a lifelong milestone. Grateful for the crew's teamwork.",
                "Very Positive",
                json.dumps(["Motivated", "Calm"]),
                json.dumps(["EVA Milestone", "Personal Achievement"]),
                "What made you feel positive today?",
                1,
                0,
                "SYNTHETIC_DEMO",
                "2026-11-11T20:45:00Z",
                "2026-11-11T20:45:00Z",
            ),
            (
                "JRN-SOL-184-03",
                "ARES-IV-SUCHAI",
                184,
                "Long Maintenance Shift & Waiting on Delayed Messages from Home",
                "Three back-to-back sols of airlock and CDRA scrubber maintenance have left me tired. The 28-minute round-trip communication delay makes family exchanges feel distant today. Planning to wind down early with acoustic music and 30 minutes of quiet reading before sleep.",
                "Neutral",
                json.dumps(["Tired", "Homesick", "Stressed"]),
                json.dumps(["Sleep & Recovery", "Family & Earth", "Daily Reflection"]),
                "What was the most challenging part of today?",
                1,
                0,
                "SYNTHETIC_DEMO",
                "2026-11-14T20:30:00Z",
                "2026-11-14T20:30:00Z",
            ),
        ]
        for j in seed_journals:
            cur.execute(
                """
                INSERT INTO journal_entries (
                    entry_uid, crew_id, mission_day, title, content, mood,
                    feelings_json, tags_json, guided_prompt, is_private,
                    allow_ai_access, provenance, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                j,
            )

    cur.execute("SELECT COUNT(*) as cnt FROM mood_checkins")
    if cur.fetchone()["cnt"] == 0:
        seed_moods = [
            ("MOOD-178", "ARES-IV-SUCHAI", 178, "Positive", 4, json.dumps(["Calm", "Homesick"]), "Habitat deployment settled; good crew dinner.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-08T21:00:00Z"),
            ("MOOD-179", "ARES-IV-SUCHAI", 179, "Neutral", 3, json.dumps(["Stressed", "Calm"]), "Confined in storm shelter during solar proton event.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-09T20:00:00Z"),
            ("MOOD-180", "ARES-IV-SUCHAI", 180, "Positive", 4, json.dumps(["Motivated", "Calm"]), "Post-SPE dosimetry clear; back to normal quarters.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-10T20:30:00Z"),
            ("MOOD-181", "ARES-IV-SUCHAI", 181, "Very Positive", 5, json.dumps(["Motivated"]), "First geological surface EVA completed.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-11T20:40:00Z"),
            ("MOOD-182", "ARES-IV-SUCHAI", 182, "Positive", 4, json.dumps(["Tired", "Motivated"]), "Long sample analysis shift.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-12T21:00:00Z"),
            ("MOOD-183", "ARES-IV-SUCHAI", 183, "Neutral", 3, json.dumps(["Tired", "Stressed"]), "Warm bunk airflow and CO2 scrubber maintenance.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-13T21:15:00Z"),
            ("MOOD-184", "ARES-IV-SUCHAI", 184, "Neutral", 3, json.dumps(["Tired", "Homesick"]), "Feeling the 14.2-min one-way distance from Earth after a busy Sol.", "SELF_REPORTED", "SYNTHETIC_DEMO", "2026-11-14T20:25:00Z"),
        ]
        for m in seed_moods:
            cur.execute(
                """
                INSERT INTO mood_checkins (
                    checkin_uid, crew_id, mission_day, mood, mood_numeric,
                    feelings_json, note, source, provenance, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                m,
            )

    # Seed initial welcome conversation for Personal Companion
    cur.execute("SELECT COUNT(*) as cnt FROM companion_conversations")
    if cur.fetchone()["cnt"] == 0:
        conv_uid = "CONV-SOL-184-WELCOME"
        cur.execute(
            """
            INSERT INTO companion_conversations (
                conversation_uid, crew_id, title, conversation_mode, created_at, updated_at
            ) VALUES (?, 'ARES-IV-SUCHAI', 'Sol 184 Evening Decompression & Check-In', 'COMPANION_CHAT', '2026-11-14T20:00:00Z', '2026-11-14T20:01:00Z')
            """,
            (conv_uid,),
        )
        cur.execute(
            """
            INSERT INTO companion_messages (
                message_uid, conversation_uid, crew_id, role, content, engine_used,
                safety_escalation_triggered, support_tier, suggested_coping_json, created_at
            ) VALUES (?, ?, 'ARES-IV-SUCHAI', 'assistant', ?, 'OFFLINE_DETERMINISTIC_COMPANION', 0, 'ORDINARY_COMPANIONSHIP', ?, '2026-11-14T20:00:00Z')
            """,
            (
                "CMSG-WELCOME-01",
                conv_uid,
                "Hello SuChai. I'm your TARSCARE Companion — always here onboard, even 255.4 million km from Earth. Whether you'd like to talk through today's airlock shift, reflect on something you miss from home, chat about astronomy or music, or just take a quiet breather, I'm listening whenever you're ready.",
                json.dumps([
                    "Guided 4-4-6 paced breathing (3 minutes)",
                    "Write a private reflection in My Journal",
                    "Prepare a store-and-forward note for family on Earth",
                ]),
            ),
        )

    conn.commit()


# =============================================================================
# PART 1: FOOD & LIFE-SUPPORT SUPPLIES MANAGEMENT FUNCTIONS
# =============================================================================

def get_food_mission_config() -> Dict[str, Any]:
    stored = database.fetch_system_state("food_mission_config") or {}
    history = database.fetch_all_telemetry()
    current_sol = int(history[-1]["mission_day"]) if history else int(stored.get("current_mission_sol", 184))
    return {
        "crew_count": int(stored.get("crew_count", 4)),
        "current_mission_sol": current_sol,
        "planned_mission_end_sol": int(stored.get("planned_mission_end_sol", 260)),
        "next_resupply_sol": int(stored.get("next_resupply_sol", 240)),
        "next_resupply_label": str(stored.get("next_resupply_label", "Pre-Positioned Surface Cargo Module B (Sol 240)")),
        "portions_per_astronaut_per_day": float(stored.get("portions_per_astronaut_per_day", 3.0)),
        "water_liters_per_astronaut_per_day": float(stored.get("water_liters_per_astronaut_per_day", 2.6)),
        "water_warning_threshold_liters": float(stored.get("water_warning_threshold_liters", 180.0)),
    }


def update_food_mission_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_food_mission_config()
    for k in (
        "crew_count",
        "planned_mission_end_sol",
        "next_resupply_sol",
        "next_resupply_label",
        "portions_per_astronaut_per_day",
        "water_liters_per_astronaut_per_day",
        "water_warning_threshold_liters",
    ):
        if k in updates and updates[k] is not None:
            cfg[k] = updates[k]
    database.update_system_state("food_mission_config", cfg)
    return cfg


def fetch_food_items(current_sol: Optional[int] = None) -> List[Dict[str, Any]]:
    sol = current_sol if current_sol is not None else get_food_mission_config()["current_mission_sol"]
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM food_items ORDER BY id ASC")
    items: List[Dict[str, Any]] = []
    for r in cur.fetchall():
        d = dict(r)
        d["micronutrients"] = json.loads(d.pop("micronutrients_json", "{}") or "{}")
        d["nutrition_complete"] = bool(d.get("nutrition_complete", 1))
        d["sols_until_expiry"] = int(d["expiry_sol"]) - int(sol)
        d["status"] = _compute_food_item_status(
            float(d["quantity"]),
            float(d["min_threshold"]),
            float(d["critical_threshold"]),
            int(d["expiry_sol"]),
            int(sol),
        )
        items.append(d)
    conn.close()
    return items


def add_food_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_food_mission_config()
    sol = int(payload.get("added_sol") or cfg["current_mission_sol"])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = payload.get("item_uid") or f"FOOD-USR-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    qty = max(0.0, float(payload.get("quantity", 10.0)))
    min_t = float(payload.get("min_threshold", 10.0))
    crit_t = float(payload.get("critical_threshold", 4.0))
    shelf_days = int(payload.get("shelf_life_days", 365))
    exp_sol = int(payload.get("expiry_sol") or (sol + shelf_days))
    exp_date = payload.get("expiry_date") or (datetime.now(timezone.utc) + timedelta(days=max(1, exp_sol - sol))).strftime("%Y-%m-%d")
    st = _compute_food_item_status(qty, min_t, crit_t, exp_sol, cfg["current_mission_sol"])
    micro = payload.get("micronutrients") or {}
    prov = payload.get("provenance") or DataProvenance.USER_ENTERED.value

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO food_items (
            item_uid, name, category, quantity, initial_quantity, serving_size, unit,
            calories_per_serving, protein_g, carbs_g, fat_g, water_ml_per_serving,
            micronutrients_json, nutrition_complete, storage_requirements, bay_location,
            expiry_sol, expiry_date, shelf_life_days, added_sol, date_added,
            food_source, min_threshold, critical_threshold, daily_ration_per_astronaut,
            status, provenance, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uid,
            str(payload["name"]).strip(),
            str(payload.get("category") or "Freeze-dried meals"),
            qty,
            float(payload.get("initial_quantity") or qty),
            str(payload.get("serving_size") or "1 portion"),
            str(payload.get("unit") or "portions"),
            float(payload.get("calories_per_serving", 400.0)),
            float(payload.get("protein_g", 20.0)),
            float(payload.get("carbs_g", 50.0)),
            float(payload.get("fat_g", 12.0)),
            float(payload.get("water_ml_per_serving", 0.0)),
            json.dumps(micro),
            int(bool(payload.get("nutrition_complete", True))),
            str(payload.get("storage_requirements") or "Ambient Galley Rack (18–24°C)"),
            str(payload.get("bay_location") or "Galley G1"),
            exp_sol,
            exp_date,
            shelf_days,
            sol,
            now_iso,
            str(payload.get("food_source") or "User-Entered Mission Inventory"),
            min_t,
            crit_t,
            float(payload.get("daily_ration_per_astronaut", 0.5)),
            st,
            prov,
            str(payload.get("notes") or ""),
            now_iso,
        ),
    )
    cur.execute(
        """
        INSERT INTO resupply_records (
            resupply_uid, mission_day, event_type, food_item_uid, food_name,
            quantity_delta, quantity_after, unit, source, authorised_by,
            notes, provenance, recorded_at
        ) VALUES (?, ?, 'ITEM_ADDED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"RSP-ADD-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            cfg["current_mission_sol"],
            uid,
            str(payload["name"]).strip(),
            qty,
            qty,
            str(payload.get("unit") or "portions"),
            str(payload.get("food_source") or "User-Entered Mission Inventory"),
            str(payload.get("authorised_by") or "Crew Member"),
            str(payload.get("notes") or "Added new food inventory item"),
            prov,
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    items = fetch_food_items(cfg["current_mission_sol"])
    return next((i for i in items if i["item_uid"] == uid), items[-1])


def update_food_item(item_uid: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_food_mission_config()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM food_items WHERE item_uid = ?", (item_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Food item '{item_uid}' not found.")
    current = dict(row)
    old_qty = float(current["quantity"])

    if "quantity" in updates and updates["quantity"] is not None:
        current["quantity"] = max(0.0, float(updates["quantity"]))
    elif "quantity_delta" in updates and updates["quantity_delta"] is not None:
        current["quantity"] = max(0.0, old_qty + float(updates["quantity_delta"]))

    for field in (
        "name",
        "category",
        "serving_size",
        "unit",
        "calories_per_serving",
        "protein_g",
        "carbs_g",
        "fat_g",
        "water_ml_per_serving",
        "storage_requirements",
        "bay_location",
        "expiry_sol",
        "expiry_date",
        "min_threshold",
        "critical_threshold",
        "daily_ration_per_astronaut",
        "notes",
    ):
        if field in updates and updates[field] is not None:
            current[field] = updates[field]

    if "nutrition_complete" in updates and updates["nutrition_complete"] is not None:
        current["nutrition_complete"] = int(bool(updates["nutrition_complete"]))
    if "micronutrients" in updates and isinstance(updates["micronutrients"], dict):
        current["micronutrients_json"] = json.dumps(updates["micronutrients"])

    new_status = _compute_food_item_status(
        float(current["quantity"]),
        float(current["min_threshold"]),
        float(current["critical_threshold"]),
        int(current["expiry_sol"]),
        cfg["current_mission_sol"],
    )

    cur.execute(
        """
        UPDATE food_items
        SET name = ?, category = ?, quantity = ?, serving_size = ?, unit = ?,
            calories_per_serving = ?, protein_g = ?, carbs_g = ?, fat_g = ?,
            water_ml_per_serving = ?, micronutrients_json = ?, nutrition_complete = ?,
            storage_requirements = ?, bay_location = ?, expiry_sol = ?, expiry_date = ?,
            min_threshold = ?, critical_threshold = ?, daily_ration_per_astronaut = ?,
            status = ?, notes = ?, updated_at = ?
        WHERE item_uid = ?
        """,
        (
            current["name"],
            current["category"],
            current["quantity"],
            current["serving_size"],
            current["unit"],
            current["calories_per_serving"],
            current["protein_g"],
            current["carbs_g"],
            current["fat_g"],
            current["water_ml_per_serving"],
            current["micronutrients_json"],
            current["nutrition_complete"],
            current["storage_requirements"],
            current["bay_location"],
            current["expiry_sol"],
            current["expiry_date"],
            current["min_threshold"],
            current["critical_threshold"],
            current["daily_ration_per_astronaut"],
            new_status,
            current["notes"],
            now_iso,
            item_uid,
        ),
    )
    delta = round(float(current["quantity"]) - old_qty, 2)
    if abs(delta) > 1e-6:
        cur.execute(
            """
            INSERT INTO resupply_records (
                resupply_uid, mission_day, event_type, food_item_uid, food_name,
                quantity_delta, quantity_after, unit, source, authorised_by,
                notes, provenance, recorded_at
            ) VALUES (?, ?, 'QUANTITY_UPDATE', ?, ?, ?, ?, ?, 'Manual Galley Audit', 'Crew Member', ?, 'USER_ENTERED', ?)
            """,
            (
                f"RSP-UPD-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                cfg["current_mission_sol"],
                item_uid,
                current["name"],
                delta,
                current["quantity"],
                current["unit"],
                str(updates.get("notes") or f"Updated quantity ({delta:+.1f} {current['unit']})"),
                now_iso,
            ),
        )
    conn.commit()
    conn.close()
    items = fetch_food_items(cfg["current_mission_sol"])
    return next(i for i in items if i["item_uid"] == item_uid)


def remove_food_item(item_uid: str, reason: str = "Removed expired or unavailable item") -> Dict[str, Any]:
    cfg = get_food_mission_config()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM food_items WHERE item_uid = ?", (item_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Food item '{item_uid}' not found.")
    d = dict(row)
    cur.execute("DELETE FROM food_items WHERE item_uid = ?", (item_uid,))
    cur.execute(
        """
        INSERT INTO resupply_records (
            resupply_uid, mission_day, event_type, food_item_uid, food_name,
            quantity_delta, quantity_after, unit, source, authorised_by,
            notes, provenance, recorded_at
        ) VALUES (?, ?, 'EXPIRED_REMOVAL', ?, ?, ?, 0.0, ?, 'Galley Disposal / Quarantine', 'Crew Member', ?, 'USER_ENTERED', ?)
        """,
        (
            f"RSP-REM-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            cfg["current_mission_sol"],
            item_uid,
            d["name"],
            -float(d["quantity"]),
            d["unit"],
            reason,
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return {"removed_item_uid": item_uid, "name": d["name"], "reason": reason}


def record_food_consumption(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Record meal/beverage consumption, deduct inventory quantity safely, and persist nutritional intake.
    Never allows consuming expired food items.
    """
    target_crew = crew_id or database.get_active_crew_id()
    cfg = get_food_mission_config()
    sol = int(payload.get("mission_day") or cfg["current_mission_sol"])
    item_uid = str(payload["food_item_uid"])
    qty_consumed = float(payload.get("quantity_consumed", 1.0))
    if qty_consumed <= 0:
        raise ValueError("Quantity consumed must be greater than zero.")

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM food_items WHERE item_uid = ?", (item_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Food item '{item_uid}' not found in inventory.")

    item = dict(row)
    if int(item["expiry_sol"]) < sol:
        conn.close()
        raise ValueError(
            f"Food safety block: '{item['name']}' expired on Sol {item['expiry_sol']} (current Sol {sol}). "
            "Do not consume expired rations; remove item to quarantine/disposal and select an in-date food item."
        )
    avail = float(item["quantity"])
    if qty_consumed > avail:
        conn.close()
        raise ValueError(
            f"Insufficient stock for '{item['name']}': requested {qty_consumed} {item['unit']}, only {avail} {item['unit']} available."
        )

    new_qty = round(max(0.0, avail - qty_consumed), 2)
    new_status = _compute_food_item_status(
        new_qty,
        float(item["min_threshold"]),
        float(item["critical_threshold"]),
        int(item["expiry_sol"]),
        sol,
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur.execute(
        "UPDATE food_items SET quantity = ?, status = ?, updated_at = ? WHERE item_uid = ?",
        (new_qty, new_status, now_iso, item_uid),
    )

    micro_base = json.loads(item.get("micronutrients_json") or "{}")
    scaled_micro = {k: round(float(v) * qty_consumed, 1) for k, v in micro_base.items() if isinstance(v, (int, float))}
    water_ml = round(float(item.get("water_ml_per_serving", 0.0)) * qty_consumed + float(payload.get("extra_water_ml", 0.0)), 1)
    cons_uid = f"CONS-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

    cur.execute(
        """
        INSERT INTO food_consumption_records (
            consumption_uid, crew_id, mission_day, meal_type, food_item_uid,
            food_name, category, quantity_consumed, unit, calories, protein_g,
            carbs_g, fat_g, water_ml, micronutrients_json, is_estimated_nutrition,
            notes, provenance, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cons_uid,
            target_crew,
            sol,
            str(payload.get("meal_type") or "Lunch"),
            item_uid,
            item["name"],
            item["category"],
            qty_consumed,
            item["unit"],
            round(float(item["calories_per_serving"]) * qty_consumed, 1),
            round(float(item["protein_g"]) * qty_consumed, 1),
            round(float(item["carbs_g"]) * qty_consumed, 1),
            round(float(item["fat_g"]) * qty_consumed, 1),
            water_ml,
            json.dumps(scaled_micro),
            0 if bool(item.get("nutrition_complete", 1)) else 1,
            str(payload.get("notes") or ""),
            DataProvenance.USER_ENTERED.value,
            now_iso,
        ),
    )

    # Also deduct rehydration / drinking water from potable water tank if applicable and item isn't already water
    if water_ml > 0 and item_uid != "FOOD-WAT-009":
        cur.execute("SELECT quantity, min_threshold, critical_threshold, expiry_sol FROM food_items WHERE item_uid = 'FOOD-WAT-009'")
        wrow = cur.fetchone()
        if wrow:
            w_qty = max(0.0, round(float(wrow["quantity"]) - (water_ml / 1000.0), 3))
            w_st = _compute_food_item_status(w_qty, float(wrow["min_threshold"]), float(wrow["critical_threshold"]), int(wrow["expiry_sol"]), sol)
            cur.execute("UPDATE food_items SET quantity = ?, status = ?, updated_at = ? WHERE item_uid = 'FOOD-WAT-009'", (w_qty, w_st, now_iso))

    conn.commit()
    conn.close()
    return {
        "consumption_uid": cons_uid,
        "crew_id": target_crew,
        "mission_day": sol,
        "food_item_uid": item_uid,
        "food_name": item["name"],
        "quantity_consumed": qty_consumed,
        "remaining_quantity": new_qty,
        "unit": item["unit"],
    }


def record_food_resupply(payload: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_food_mission_config()
    sol = int(payload.get("mission_day") or cfg["current_mission_sol"])
    item_uid = str(payload["food_item_uid"])
    added_qty = float(payload.get("quantity_added", 0.0))
    if added_qty <= 0:
        raise ValueError("Resupply quantity_added must be positive.")

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM food_items WHERE item_uid = ?", (item_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Food item '{item_uid}' not found.")
    item = dict(row)
    new_qty = round(float(item["quantity"]) + added_qty, 2)
    new_init = max(float(item["initial_quantity"]), new_qty)
    new_status = _compute_food_item_status(
        new_qty,
        float(item["min_threshold"]),
        float(item["critical_threshold"]),
        int(item["expiry_sol"]),
        sol,
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur.execute(
        "UPDATE food_items SET quantity = ?, initial_quantity = ?, status = ?, updated_at = ? WHERE item_uid = ?",
        (new_qty, new_init, new_status, now_iso, item_uid),
    )
    rsp_uid = f"RSP-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    cur.execute(
        """
        INSERT INTO resupply_records (
            resupply_uid, mission_day, event_type, food_item_uid, food_name,
            quantity_delta, quantity_after, unit, source, authorised_by,
            notes, provenance, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USER_ENTERED', ?)
        """,
        (
            rsp_uid,
            sol,
            str(payload.get("event_type") or "RESUPPLY_DELIVERY"),
            item_uid,
            item["name"],
            added_qty,
            new_qty,
            item["unit"],
            str(payload.get("source") or "Cargo Module Transfer / Veggie Harvest"),
            str(payload.get("authorised_by") or "Mission Commander"),
            str(payload.get("notes") or f"Resupply of +{added_qty} {item['unit']}"),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "resupply_uid": rsp_uid,
        "food_item_uid": item_uid,
        "food_name": item["name"],
        "quantity_added": added_qty,
        "quantity_after": new_qty,
        "unit": item["unit"],
    }


def calculate_supply_projection(
    total_portions: float,
    astronaut_count: int,
    portions_per_astronaut_per_day: float,
    current_sol: int = 184,
    planned_mission_end_sol: int = 260,
    next_resupply_sol: Optional[int] = 240,
) -> Dict[str, Any]:
    """
    Deterministic remaining-supply projection formula.
    Example: 120 meal portions / (2 astronauts * 3 portions/day) = 20.0 days remaining.
    """
    crew = max(1, int(astronaut_count))
    rate_per_person = max(0.1, float(portions_per_astronaut_per_day))
    daily_crew_rate = round(crew * rate_per_person, 2)
    est_days = round(max(0.0, float(total_portions)) / daily_crew_rate, 1)
    depletion_sol = round(current_sol + est_days, 1)
    depletion_date = (datetime.now(timezone.utc) + timedelta(days=est_days)).strftime("%Y-%m-%d")
    mission_remaining_sols = max(0, planned_mission_end_sol - current_sol)
    covers_until_resupply = True if next_resupply_sol is None else (depletion_sol >= next_resupply_sol)
    covers_full_mission = depletion_sol >= planned_mission_end_sol
    return {
        "is_projection": True,
        "projection_disclaimer": "Projection only — estimated from configured crew count and daily ration rate, not a guaranteed supply duration.",
        "total_portions": round(float(total_portions), 2),
        "astronaut_count": crew,
        "portions_per_astronaut_per_day": rate_per_person,
        "daily_crew_consumption_rate": daily_crew_rate,
        "estimated_remaining_days": est_days,
        "projected_depletion_sol": depletion_sol,
        "projected_depletion_date": depletion_date,
        "planned_mission_end_sol": planned_mission_end_sol,
        "mission_remaining_sols": mission_remaining_sols,
        "next_resupply_sol": next_resupply_sol,
        "covers_until_resupply": covers_until_resupply,
        "covers_full_mission": covers_full_mission,
    }


def fetch_crew_nutrition_target(crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM crew_nutrition_targets WHERE crew_id = ?", (target_crew,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "crew_id": target_crew,
        "calories_target_kcal": 2850.0,
        "protein_target_g": 115.0,
        "carbs_target_g": 360.0,
        "fat_target_g": 95.0,
        "water_target_ml": 2600.0,
        "vitamin_d_target_iu": 800.0,
        "calcium_target_mg": 1200.0,
        "notes": "Default deep-space exploration target",
        "updated_at": "2026-11-14T08:00:00Z",
    }


def update_crew_nutrition_target(crew_id: Optional[str], updates: Dict[str, Any]) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    current = fetch_crew_nutrition_target(target_crew)
    for k in (
        "calories_target_kcal",
        "protein_target_g",
        "carbs_target_g",
        "fat_target_g",
        "water_target_ml",
        "vitamin_d_target_iu",
        "calcium_target_mg",
        "notes",
    ):
        if k in updates and updates[k] is not None:
            current[k] = updates[k]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO crew_nutrition_targets (
            crew_id, calories_target_kcal, protein_target_g, carbs_target_g,
            fat_target_g, water_target_ml, vitamin_d_target_iu, calcium_target_mg,
            notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            float(current["calories_target_kcal"]),
            float(current["protein_target_g"]),
            float(current["carbs_target_g"]),
            float(current["fat_target_g"]),
            float(current["water_target_ml"]),
            float(current["vitamin_d_target_iu"]),
            float(current["calcium_target_mg"]),
            str(current.get("notes") or ""),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return fetch_crew_nutrition_target(target_crew)


def build_food_and_supplies_state(crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    cfg = get_food_mission_config()
    sol = cfg["current_mission_sol"]
    crew_count = max(1, int(cfg["crew_count"]))
    items = fetch_food_items(sol)

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM food_consumption_records WHERE crew_id = ? ORDER BY mission_day DESC, id DESC LIMIT 60",
        (target_crew,),
    )
    consumption_rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["micronutrients"] = json.loads(d.pop("micronutrients_json", "{}") or "{}")
        d["is_estimated_nutrition"] = bool(d.get("is_estimated_nutrition", 0))
        consumption_rows.append(d)

    cur.execute("SELECT * FROM resupply_records ORDER BY id DESC LIMIT 40")
    resupply_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Category-by-category remaining supply projections (never collapse heterogeneous categories into one misleading number)
    category_projections: List[Dict[str, Any]] = []
    for cat in FOOD_CATEGORIES:
        cat_items = [i for i in items if i["category"] == cat and i["status"] != "EXPIRED"]
        if not cat_items:
            continue
        total_qty = round(sum(float(i["quantity"]) for i in cat_items), 2)
        unit = cat_items[0]["unit"]
        ration_per_person = sum(float(i.get("daily_ration_per_astronaut", 0.5)) for i in cat_items)
        configured_daily_crew_rate = round(max(0.2, ration_per_person * crew_count), 2)

        recent_cat_cons = [
            float(c["quantity_consumed"])
            for c in consumption_rows
            if c["category"] == cat and int(c["mission_day"]) >= (sol - 2)
        ]
        recorded_daily_person = sum(recent_cat_cons) / 3.0 if recent_cat_cons else ration_per_person
        effective_daily_crew_rate = round(max(0.2, ((ration_per_person * 0.6) + (recorded_daily_person * 0.4)) * crew_count), 2)
        est_days = round(total_qty / effective_daily_crew_rate, 1)
        depletion_sol = round(sol + est_days, 1)
        depletion_date = (datetime.now(timezone.utc) + timedelta(days=est_days)).strftime("%Y-%m-%d")

        if recorded_daily_person > ration_per_person * 1.15:
            trend = "ELEVATED_CONSUMPTION"
        elif recorded_daily_person < ration_per_person * 0.85:
            trend = "CONSERVING"
        else:
            trend = "NOMINAL_STEADY"

        cat_status = "NORMAL"
        if est_days <= 14 or any(i["status"] == "CRITICAL" for i in cat_items):
            cat_status = "CRITICAL"
        elif est_days < (cfg["next_resupply_sol"] - sol) or any(i["status"] in ("RUNNING_LOW", "EXPIRING_SOON") for i in cat_items):
            cat_status = "WARNING"

        category_projections.append({
            "category": cat,
            "item_count": len(cat_items),
            "available_quantity": total_qty,
            "unit": unit,
            "configured_daily_crew_rate": configured_daily_crew_rate,
            "effective_daily_crew_rate": effective_daily_crew_rate,
            "estimated_remaining_days": est_days,
            "projected_depletion_sol": depletion_sol,
            "projected_depletion_date": depletion_date,
            "consumption_trend": trend,
            "status": cat_status,
            "is_projection": True,
        })

    # Primary Meal Portions Projection (Freeze-dried meals + Ready-to-eat meals)
    primary_meal_items = [
        i for i in items
        if i["category"] in ("Freeze-dried meals", "Ready-to-eat meals") and i["status"] != "EXPIRED"
    ]
    primary_portions = sum(float(i["quantity"]) for i in primary_meal_items)
    primary_projection = calculate_supply_projection(
        total_portions=primary_portions,
        astronaut_count=crew_count,
        portions_per_astronaut_per_day=cfg["portions_per_astronaut_per_day"],
        current_sol=sol,
        planned_mission_end_sol=cfg["planned_mission_end_sol"],
        next_resupply_sol=cfg["next_resupply_sol"],
    )

    # Total non-expired caloric reserve projection
    total_kcal_available = round(
        sum(float(i["quantity"]) * float(i["calories_per_serving"]) for i in items if i["status"] != "EXPIRED"),
        0,
    )
    target = fetch_crew_nutrition_target(target_crew)
    daily_fleet_kcal = round(float(target["calories_target_kcal"]) * crew_count, 0)
    caloric_days = round(total_kcal_available / max(1000.0, daily_fleet_kcal), 1)

    # Potable water reserve
    water_items = [i for i in items if i["category"] == "Potable Water & Hydration"]
    water_liters = round(sum(float(i["quantity"]) for i in water_items), 1)
    daily_fleet_water_l = round(cfg["water_liters_per_astronaut_per_day"] * crew_count, 2)
    water_days = round(water_liters / max(1.0, daily_fleet_water_l), 1)

    # Daily nutrition aggregation for active astronaut on current Sol (and 7-Sol history)
    today_records = [c for c in consumption_rows if int(c["mission_day"]) == sol]
    today_kcal = round(sum(float(c["calories"]) for c in today_records), 1)
    today_pro = round(sum(float(c["protein_g"]) for c in today_records), 1)
    today_carbs = round(sum(float(c["carbs_g"]) for c in today_records), 1)
    today_fat = round(sum(float(c["fat_g"]) for c in today_records), 1)
    today_water_ml = round(sum(float(c["water_ml"]) for c in today_records), 1)
    has_estimated = any(bool(c.get("is_estimated_nutrition")) for c in today_records)

    today_micro: Dict[str, float] = {}
    for c in today_records:
        for mk, mv in (c.get("micronutrients") or {}).items():
            if isinstance(mv, (int, float)):
                today_micro[mk] = round(today_micro.get(mk, 0.0) + float(mv), 1)

    # Non-diagnostic nutritional target comparison explanations
    explanations: List[str] = []
    kcal_pct = round((today_kcal / max(1.0, float(target["calories_target_kcal"]))) * 100.0, 0)
    pro_pct = round((today_pro / max(1.0, float(target["protein_target_g"]))) * 100.0, 0)
    water_pct = round((today_water_ml / max(1.0, float(target["water_target_ml"]))) * 100.0, 0)

    if kcal_pct < 75:
        explanations.append(
            f"Recorded Sol {sol} energy intake ({today_kcal:.0f} kcal) is currently at {kcal_pct:.0f}% of your configured mission target ({target['calories_target_kcal']:.0f} kcal). Logging your evening meal or an energy ration helps sustain muscle and cognitive readiness in {cfg['current_mission_sol']} operations."
        )
    elif kcal_pct > 115:
        explanations.append(
            f"Recorded Sol {sol} energy intake ({today_kcal:.0f} kcal) is above your configured target ({target['calories_target_kcal']:.0f} kcal), which may be appropriate on high-workload EVA sols."
        )
    else:
        explanations.append(
            f"Recorded Sol {sol} caloric intake ({today_kcal:.0f} kcal) is well aligned ({kcal_pct:.0f}%) with your personal mission target."
        )

    if pro_pct < 75:
        explanations.append(
            f"Protein intake ({today_pro:.1f}g / {target['protein_target_g']:.0f}g target) is below your daily goal; adequate protein and Vitamin D/Calcium support weight-bearing bone and muscle retention under partial gravity (CSA TBone)."
        )
    if water_pct < 75:
        explanations.append(
            f"Recorded hydration ({today_water_ml:.0f} mL / {target['water_target_ml']:.0f} mL target) is below your daily hydration goal; adequate fluid-electrolyte intake supports orthostatic blood pressure stability."
        )
    if has_estimated:
        explanations.append(
            "Note: One or more items logged today (such as fresh habitat-grown produce) have incomplete food-label data and include clearly flagged estimated micronutrient values."
        )

    # Build Food & Supply Alerts
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    food_alerts: List[Dict[str, Any]] = []
    for item in items:
        if item["status"] == "EXPIRED":
            food_alerts.append({
                "alert_uid": f"FALERT-EXP-{item['item_uid']}",
                "alert_type": "EXPIRED_UNSAFE",
                "severity": "CRITICAL",
                "affected_item_uid": item["item_uid"],
                "affected_item_name": item["name"],
                "current_quantity": item["quantity"],
                "unit": item["unit"],
                "recommended_action": f"DO NOT CONSUME: '{item['name']}' passed expiry on Sol {item['expiry_sol']}. Remove item to quarantine/disposal immediately and substitute in-date rations.",
                "timestamp": now_iso,
            })
        elif item["status"] == "CRITICAL":
            food_alerts.append({
                "alert_uid": f"FALERT-CRIT-{item['item_uid']}",
                "alert_type": "CRITICAL_STOCK",
                "severity": "CRITICAL",
                "affected_item_uid": item["item_uid"],
                "affected_item_name": item["name"],
                "current_quantity": item["quantity"],
                "unit": item["unit"],
                "recommended_action": f"Critical stock level ({item['quantity']} {item['unit']} remaining). Rebalance daily menu to high-stock categories and include in next Mission Control supply report.",
                "timestamp": now_iso,
            })
        elif item["status"] == "EXPIRING_SOON":
            food_alerts.append({
                "alert_uid": f"FALERT-SOON-{item['item_uid']}",
                "alert_type": "EXPIRING_SOON",
                "severity": "WARNING",
                "affected_item_uid": item["item_uid"],
                "affected_item_name": item["name"],
                "current_quantity": item["quantity"],
                "unit": item["unit"],
                "recommended_action": f"Approaching expiry in {item['sols_until_expiry']} Sols (Sol {item['expiry_sol']} / {item['expiry_date']}). Prioritise FIFO consumption while still within safe shelf-life.",
                "timestamp": now_iso,
            })
        elif item["status"] == "RUNNING_LOW":
            food_alerts.append({
                "alert_uid": f"FALERT-LOW-{item['item_uid']}",
                "alert_type": "LOW_STOCK",
                "severity": "WARNING",
                "affected_item_uid": item["item_uid"],
                "affected_item_name": item["name"],
                "current_quantity": item["quantity"],
                "unit": item["unit"],
                "recommended_action": f"Stock running low ({item['quantity']} {item['unit']} <= {item['min_threshold']} {item['unit']} threshold). Schedule Veggie harvest or cargo transfer.",
                "timestamp": now_iso,
            })

    if not primary_projection["covers_full_mission"]:
        food_alerts.append({
            "alert_uid": "FALERT-DEPLETION-MISSION",
            "alert_type": "DEPLETION_BEFORE_MISSION_END",
            "severity": "WARNING" if primary_projection["covers_until_resupply"] else "CRITICAL",
            "affected_item_uid": "PRIMARY_MEAL_PORTIONS",
            "affected_item_name": "Primary Meal Portions (Freeze-Dried & Ready-to-Eat)",
            "current_quantity": primary_portions,
            "unit": "portions",
            "recommended_action": (
                f"Projected primary meal depletion (Sol {primary_projection['projected_depletion_sol']}) is earlier than planned mission end (Sol {cfg['planned_mission_end_sol']}). "
                f"{'Verify Sol ' + str(cfg['next_resupply_sol']) + ' cargo transfer manifest.' if primary_projection['covers_until_resupply'] else 'Adjust daily ration allocation and notify Mission Control immediately.'}"
            ),
            "timestamp": now_iso,
        })

    if water_liters < cfg["water_warning_threshold_liters"]:
        food_alerts.append({
            "alert_uid": "FALERT-WATER-LOW",
            "alert_type": "WATER_BELOW_THRESHOLD",
            "severity": "CRITICAL" if water_liters < 100.0 else "WARNING",
            "affected_item_uid": "FOOD-WAT-009",
            "affected_item_name": "ECLSS Recycled & Mineralized Potable Water Reserve",
            "current_quantity": water_liters,
            "unit": "L",
            "recommended_action": f"Potable water reserve ({water_liters} L) is below the configured {cfg['water_warning_threshold_liters']} L threshold. Inspect ECLSS Water Processor Assembly recovery loop and initiate ISRU transfer.",
            "timestamp": now_iso,
        })

    if kcal_pct < 75:
        food_alerts.append({
            "alert_uid": f"FALERT-NUTR-INCOMPLETE-{sol}",
            "alert_type": "INCOMPLETE_NUTRITION_LOG",
            "severity": "WARNING",
            "affected_item_uid": target_crew,
            "affected_item_name": f"Sol {sol} Daily Nutritional Intake Log",
            "current_quantity": today_kcal,
            "unit": "kcal",
            "recommended_action": f"Sol {sol} nutritional log is incomplete ({today_kcal:.0f} / {target['calories_target_kcal']:.0f} kcal recorded). Record remaining meals to keep metabolic & countermeasure tracking accurate.",
            "timestamp": now_iso,
        })

    low_stock_items = [i for i in items if i["status"] in ("RUNNING_LOW", "CRITICAL")]
    expiring_soon_items = [i for i in items if i["status"] in ("EXPIRING_SOON", "EXPIRED") or int(i["sols_until_expiry"]) <= 14]

    return {
        "mission_config": cfg,
        "summary": {
            "total_food_items": len(items),
            "available_meal_portions": round(primary_portions, 1),
            "total_kcal_available": total_kcal_available,
            "estimated_meal_supply_days": primary_projection["estimated_remaining_days"],
            "estimated_caloric_supply_days": caloric_days,
            "potable_water_liters": water_liters,
            "estimated_water_supply_days": water_days,
            "low_stock_count": len(low_stock_items),
            "expiring_soon_count": len(expiring_soon_items),
            "daily_food_consumption_kcal": today_kcal,
            "daily_water_consumption_ml": today_water_ml,
            "provenance_note": "All inventory quantities derive from saved SQLite records (labelled Simulated Demo Data or User-Entered Data).",
        },
        "primary_meal_projection": primary_projection,
        "category_projections": category_projections,
        "nutrition_overview": {
            "crew_id": target_crew,
            "mission_day": sol,
            "targets": target,
            "recorded": {
                "calories_kcal": today_kcal,
                "protein_g": today_pro,
                "carbs_g": today_carbs,
                "fat_g": today_fat,
                "water_ml": today_water_ml,
                "micronutrients": today_micro,
                "meals_logged_count": len(today_records),
                "contains_estimated_values": has_estimated,
            },
            "progress_pct": {
                "calories": min(150.0, kcal_pct),
                "protein": min(150.0, pro_pct),
                "carbs": min(150.0, round((today_carbs / max(1.0, float(target["carbs_target_g"]))) * 100.0, 0)),
                "fat": min(150.0, round((today_fat / max(1.0, float(target["fat_target_g"]))) * 100.0, 0)),
                "water": min(150.0, water_pct),
            },
            "explanations": explanations,
            "safety_disclaimer": "Nutritional monitoring compares recorded intake against configurable mission targets. It does not diagnose nutritional deficiencies or generate unsafe clinical dietary restrictions.",
        },
        "items": items,
        "low_stock_items": low_stock_items,
        "expiring_soon_items": expiring_soon_items,
        "food_alerts": food_alerts,
        "consumption_history": consumption_rows,
        "resupply_history": resupply_rows,
    }


# =============================================================================
# PART 2: DISTANCE FROM EARTH & MISSION COMMUNICATION CENTRE FUNCTIONS
# =============================================================================

def configure_comm_simulator(payload: Dict[str, Any]) -> Dict[str, Any]:
    comm_state = database.fetch_system_state("comm_state") or {}
    preset_id = payload.get("scenario_id")
    if preset_id and preset_id in COMM_SCENARIO_PRESETS:
        preset = COMM_SCENARIO_PRESETS[preset_id]
        comm_state.update({
            "scenario_id": preset["scenario_id"],
            "mission_location": preset["mission_location"],
            "mission_destination": preset["mission_destination"],
            "distance_million_km": preset["distance_million_km"],
            "one_way_delay_minutes": preset["one_way_delay_minutes"],
            "round_trip_delay_minutes": round(float(preset["one_way_delay_minutes"]) * 2.0, 2),
            "comm_condition": preset["comm_condition"],
            "earth_comm_status": preset["earth_comm_status"],
            "offline_mode_forced": preset["offline_mode_forced"],
            "signal_quality_pct": preset["signal_quality_pct"],
            "bandwidth_kbps": preset["bandwidth_kbps"],
            "relay_satellite": preset["relay_satellite"],
            "next_comm_window_utc": preset["next_comm_window_utc"],
            "telemetry_source_type": preset["telemetry_source_type"],
        })

    if payload.get("comm_condition"):
        cond = str(payload["comm_condition"]).upper()
        comm_state["comm_condition"] = cond
        if cond == "NORMAL":
            comm_state["earth_comm_status"] = "NOMINAL_DIRECT"
            comm_state["offline_mode_forced"] = False
            comm_state["signal_quality_pct"] = 98.0
        elif cond == "DELAYED":
            comm_state["earth_comm_status"] = "NOMINAL_DELAYED"
            comm_state["offline_mode_forced"] = False
            comm_state["signal_quality_pct"] = 80.0
        elif cond == "INTERMITTENT":
            comm_state["earth_comm_status"] = "HIGH_LATENCY_DEGRADED"
            comm_state["offline_mode_forced"] = False
            comm_state["signal_quality_pct"] = 40.0
        elif cond == "BLACKOUT":
            comm_state["earth_comm_status"] = "CONJUNCTION_BLACKOUT"
            comm_state["offline_mode_forced"] = True
            comm_state["signal_quality_pct"] = 0.0

    if payload.get("one_way_delay_minutes") is not None:
        ow = max(0.0, float(payload["one_way_delay_minutes"]))
        comm_state["one_way_delay_minutes"] = round(ow, 2)
        comm_state["round_trip_delay_minutes"] = round(ow * 2.0, 2)
    else:
        ow = float(comm_state.get("one_way_delay_minutes", 14.2))
        comm_state["round_trip_delay_minutes"] = round(ow * 2.0, 2)

    if payload.get("distance_million_km") is not None:
        comm_state["distance_million_km"] = round(max(0.0, float(payload["distance_million_km"])), 4)

    for field in ("mission_location", "mission_destination", "next_comm_window_utc", "relay_satellite"):
        if payload.get(field):
            comm_state[field] = str(payload[field]).strip()

    if not preset_id:
        comm_state["telemetry_source_type"] = "USER_CONFIGURED_SIMULATION"

    database.update_system_state("comm_state", comm_state)
    return comm_state


def fetch_comm_messages() -> List[Dict[str, Any]]:
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comm_messages ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def create_or_queue_comm_message(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    baseline = database.fetch_crew_baseline(target_crew) or {}
    sender_name = f"{baseline.get('name', 'SuChai')} ({baseline.get('role', 'Crew')})"
    comm_state = database.fetch_system_state("comm_state") or {}
    history = database.fetch_all_telemetry(target_crew)
    sol = int(history[-1]["mission_day"]) if history else 184

    ow = float(comm_state.get("one_way_delay_minutes", 14.2))
    rt = round(ow * 2.0, 2)
    dist = float(comm_state.get("distance_million_km", 255.4))
    is_offline = bool(comm_state.get("offline_mode_forced", False)) or (
        "BLACKOUT" in str(comm_state.get("earth_comm_status", "")).upper()
    )
    cond = str(comm_state.get("comm_condition", "DELAYED")).upper()

    save_as_draft = bool(payload.get("save_as_draft", False))
    simulate_failure = bool(payload.get("simulate_failure", False))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg_uid = f"MSG-SOL-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

    sent_at = None
    ack_at = None
    failure_reason = ""

    if save_as_draft:
        status = "Draft"
    elif is_offline:
        status = "Waiting for Connection"
    elif simulate_failure:
        status = "Failed"
        failure_reason = "Simulated intermittent X-band relay packet drop during low-elevation pass. Message safely retained locally for retry."
    elif cond == "NORMAL" and ow <= 0.1 and bool(payload.get("transmit_immediately", True)):
        status = "Sent"
        sent_at = now_iso
        ack_at = now_iso
        comm_state["last_successful_comm"] = now_iso
        comm_state["last_sync_timestamp"] = now_iso
        database.update_system_state("comm_state", comm_state)
    else:
        status = "Queued"

    subject = str(payload.get("subject") or f"Sol {sol} Mission Communication").strip()
    body = str(payload.get("body") or "").strip()
    priority = str(payload.get("priority") or "NORMAL").upper()
    msg_type = str(payload.get("message_type") or "MISSION_CONTROL_MESSAGE").upper()
    linked_report_uid = ""

    if msg_type in ("HEALTH_REPORT", "URGENT_MEDICAL_CONSULT") and not save_as_draft:
        rpt = database.create_store_forward_report(
            mission_day=sol,
            title=subject,
            summary=body[:280],
            risk_level="CRITICAL" if priority == "URGENT" else ("WARNING" if priority == "IMPORTANT" else "NORMAL"),
            hazard_triggers=["Distance from Earth"],
            payload={"message_uid": msg_uid, "priority": priority, "body": body},
            provenance=DataProvenance.USER_ENTERED.value,
            comm_online=(status == "Sent"),
            crew_id=target_crew,
        )
        linked_report_uid = rpt["report_uid"]

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO comm_messages (
            message_uid, crew_id, sender_name, recipient, message_type, priority,
            subject, body, status, one_way_delay_minutes, round_trip_delay_minutes,
            distance_million_km, created_at, updated_at, sent_at, acknowledged_at,
            retry_count, failure_reason, linked_report_uid, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'USER_ENTERED')
        """,
        (
            msg_uid,
            target_crew,
            sender_name,
            str(payload.get("recipient") or "Earth Mission Control & Flight Surgeons (MCC-Houston)"),
            msg_type,
            priority,
            subject,
            body,
            status,
            ow,
            rt,
            dist,
            now_iso,
            now_iso,
            sent_at,
            ack_at,
            failure_reason,
            linked_report_uid,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (msg_uid,))
    created = dict(cur.fetchone())
    conn.close()
    return created


def update_comm_message(message_uid: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (message_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Message '{message_uid}' not found.")
    current = dict(row)
    for k in ("subject", "body", "priority", "recipient", "message_type", "status"):
        if k in updates and updates[k] is not None:
            current[k] = updates[k]
    cur.execute(
        """
        UPDATE comm_messages
        SET subject = ?, body = ?, priority = ?, recipient = ?, message_type = ?, status = ?, updated_at = ?
        WHERE message_uid = ?
        """,
        (
            current["subject"],
            current["body"],
            current["priority"],
            current["recipient"],
            current["message_type"],
            current["status"],
            now_iso,
            message_uid,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (message_uid,))
    updated = dict(cur.fetchone())
    conn.close()
    return updated


def delete_comm_message(message_uid: str) -> Dict[str, Any]:
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (message_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Message '{message_uid}' not found.")
    cur.execute("DELETE FROM comm_messages WHERE message_uid = ?", (message_uid,))
    conn.commit()
    conn.close()
    return {"deleted": True, "message_uid": message_uid}


def retry_or_send_comm_message(message_uid: str, simulate_failure: bool = False) -> Dict[str, Any]:
    comm_state = database.fetch_system_state("comm_state") or {}
    is_offline = bool(comm_state.get("offline_mode_forced", False)) or (
        "BLACKOUT" in str(comm_state.get("earth_comm_status", "")).upper()
    )
    ow = float(comm_state.get("one_way_delay_minutes", 14.2))
    rt = round(ow * 2.0, 2)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (message_uid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Message '{message_uid}' not found.")
    msg = dict(row)
    retries = int(msg.get("retry_count", 0)) + (1 if msg["status"] in ("Failed", "Waiting for Connection") else 0)

    if is_offline:
        cur.execute(
            """
            UPDATE comm_messages
            SET status = 'Waiting for Connection', retry_count = ?,
                failure_reason = 'Earth link in communication blackout; message queued in local store-and-forward buffer.',
                updated_at = ?
            WHERE message_uid = ?
            """,
            (retries, now_iso, message_uid),
        )
    elif simulate_failure:
        cur.execute(
            """
            UPDATE comm_messages
            SET status = 'Failed', retry_count = ?,
                failure_reason = 'Intermittent relay carrier drop during transmission window; ready for manual or scheduled retry.',
                updated_at = ?
            WHERE message_uid = ?
            """,
            (retries, now_iso, message_uid),
        )
    else:
        cur.execute(
            """
            UPDATE comm_messages
            SET status = 'Sent', sent_at = ?, acknowledged_at = ?, retry_count = ?,
                one_way_delay_minutes = ?, round_trip_delay_minutes = ?,
                failure_reason = '', updated_at = ?
            WHERE message_uid = ?
            """,
            (now_iso, now_iso, retries, ow, rt, now_iso, message_uid),
        )
        if msg.get("linked_report_uid"):
            cur.execute(
                "UPDATE store_forward_reports SET transmission_status = 'SYNCHRONIZED_ACK', synced_at = ? WHERE report_uid = ?",
                (now_iso, msg["linked_report_uid"]),
            )
        comm_state["last_successful_comm"] = now_iso
        comm_state["last_sync_timestamp"] = now_iso
        cur.execute(
            "INSERT OR REPLACE INTO system_state (key, value_json) VALUES ('comm_state', ?)",
            (json.dumps(comm_state),),
        )

    conn.commit()
    cur.execute("SELECT * FROM comm_messages WHERE message_uid = ?", (message_uid,))
    updated = dict(cur.fetchone())
    conn.close()
    return updated


def synchronize_all_communications(simulate_intermittent_drop: bool = False) -> Dict[str, Any]:
    """Synchronize both store_forward_reports and eligible comm_messages (Queued, Waiting for Connection, Failed)."""
    comm_state = database.fetch_system_state("comm_state") or {}
    history = database.fetch_all_telemetry()
    sol = int(history[-1]["mission_day"]) if history else 184
    is_offline = bool(comm_state.get("offline_mode_forced", False)) or (
        "BLACKOUT" in str(comm_state.get("earth_comm_status", "")).upper()
    )
    cond = str(comm_state.get("comm_condition", "DELAYED")).upper()
    ow = float(comm_state.get("one_way_delay_minutes", 14.2))
    rt = round(ow * 2.0, 2)
    dist = float(comm_state.get("distance_million_km", 255.4))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM comm_messages WHERE status IN ('Queued', 'Waiting for Connection', 'Failed', 'Sending') ORDER BY id ASC")
    eligible_msgs = [dict(r) for r in cur.fetchall()]
    conn.close()

    if is_offline:
        base_sync = database.synchronize_queued_reports()
        conn = database.get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE comm_messages SET status = 'Waiting for Connection', updated_at = ? WHERE status = 'Queued'",
            (now_iso,),
        )
        cur.execute(
            """
            INSERT INTO sync_history (
                sync_uid, timestamp, mission_day, comm_condition, one_way_delay_minutes,
                round_trip_delay_minutes, distance_million_km, messages_attempted,
                messages_sent, messages_failed, reports_synced, status, summary
            ) VALUES (?, ?, ?, 'BLACKOUT', ?, ?, ?, ?, 0, 0, 0, 'BLOCKED_OFFLINE', ?)
            """,
            (
                f"SYNC-BLK-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                now_iso,
                sol,
                ow,
                rt,
                dist,
                len(eligible_msgs),
                "Synchronization blocked while in Communication Blackout (Offline Mode). All pending reports and messages remain safely queued locally.",
            ),
        )
        conn.commit()
        conn.close()
        return base_sync

    # Sync store_forward_reports first
    base_sync = database.synchronize_queued_reports()
    reports_synced = int(base_sync.get("synchronized_count", 0))
    comm_state = database.fetch_system_state("comm_state") or comm_state

    conn = database.get_conn()
    cur = conn.cursor()
    sent_count = 0
    failed_count = 0
    for idx, m in enumerate(eligible_msgs):
        if simulate_intermittent_drop and idx == 0:
            failed_count += 1
            cur.execute(
                """
                UPDATE comm_messages
                SET status = 'Failed', retry_count = retry_count + 1,
                    failure_reason = 'Simulated intermittent relay frame loss; message preserved for retry.',
                    updated_at = ?
                WHERE message_uid = ?
                """,
                (now_iso, m["message_uid"]),
            )
        else:
            sent_count += 1
            cur.execute(
                """
                UPDATE comm_messages
                SET status = 'Sent', sent_at = ?, acknowledged_at = ?,
                    one_way_delay_minutes = ?, round_trip_delay_minutes = ?,
                    failure_reason = '', updated_at = ?
                WHERE message_uid = ?
                """,
                (now_iso, now_iso, ow, rt, now_iso, m["message_uid"]),
            )

    comm_state["last_successful_comm"] = now_iso
    comm_state["last_sync_timestamp"] = now_iso
    cur.execute(
        "INSERT OR REPLACE INTO system_state (key, value_json) VALUES ('comm_state', ?)",
        (json.dumps(comm_state),),
    )

    sync_status = "PARTIAL_FAILURE" if failed_count > 0 else "SUCCESS"
    summary_txt = (
        f"Synchronized {reports_synced} health report(s) and {sent_count} message(s) "
        f"({failed_count} failed) across {ow:.1f}-min one-way ({rt:.1f}-min round-trip) link."
    )
    cur.execute(
        """
        INSERT INTO sync_history (
            sync_uid, timestamp, mission_day, comm_condition, one_way_delay_minutes,
            round_trip_delay_minutes, distance_million_km, messages_attempted,
            messages_sent, messages_failed, reports_synced, status, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"SYNC-OK-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            now_iso,
            sol,
            cond,
            ow,
            rt,
            dist,
            len(eligible_msgs),
            sent_count,
            failed_count,
            reports_synced,
            sync_status,
            summary_txt,
        ),
    )
    conn.commit()
    conn.close()

    base_sync["messages_sent"] = sent_count
    base_sync["messages_failed"] = failed_count
    base_sync["message"] = summary_txt
    return base_sync


def build_comm_centre_state() -> Dict[str, Any]:
    comm_state = database.fetch_system_state("comm_state") or {}
    ow = float(comm_state.get("one_way_delay_minutes", 14.2))
    rt = round(ow * 2.0, 2)
    dist = float(comm_state.get("distance_million_km", 255.4))
    is_offline = bool(comm_state.get("offline_mode_forced", False)) or (
        "BLACKOUT" in str(comm_state.get("earth_comm_status", "")).upper()
    )
    cond = "BLACKOUT" if is_offline else str(comm_state.get("comm_condition", "DELAYED" if ow > 0.1 else "NORMAL")).upper()

    messages = fetch_comm_messages()
    reports = database.fetch_store_forward_reports()
    unsent_reports = [r for r in reports if r["transmission_status"] != "SYNCHRONIZED_ACK"]
    pending_messages = [m for m in messages if m["status"] in ("Queued", "Waiting for Connection", "Sending", "Failed")]
    draft_messages = [m for m in messages if m["status"] == "Draft"]

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_history ORDER BY id DESC LIMIT 25")
    sync_logs = [dict(r) for r in cur.fetchall()]
    conn.close()

    return {
        "mission_location": comm_state.get("mission_location", "Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)"),
        "mission_destination": comm_state.get("mission_destination", "Mars Surface Operations (Ares-Horizon IV)"),
        "scenario_id": comm_state.get("scenario_id", "MARS_SURFACE_NOMINAL"),
        "comm_condition": cond,
        "earth_comm_status": comm_state.get("earth_comm_status", "NOMINAL_DELAYED"),
        "offline_mode_forced": is_offline,
        "distance_million_km": dist,
        "distance_au": round(dist / 149.59787, 3),
        "one_way_delay_minutes": ow,
        "round_trip_delay_minutes": rt,
        "signal_quality_pct": 0.0 if is_offline else float(comm_state.get("signal_quality_pct", 79.0)),
        "bandwidth_kbps": 0.0 if is_offline else float(comm_state.get("bandwidth_kbps", 512.0)),
        "relay_satellite": comm_state.get("relay_satellite", "Ares Mars Relay Orbiter → DSN Madrid Complex"),
        "last_successful_comm": comm_state.get("last_successful_comm") or comm_state.get("last_sync_timestamp", "2026-11-14T04:15:00Z"),
        "last_sync_timestamp": comm_state.get("last_sync_timestamp", "2026-11-14T04:15:00Z"),
        "next_comm_window_utc": comm_state.get("next_comm_window_utc", "2026-11-15T20:15:00Z (Orbiter Overflight Pass #412)"),
        "telemetry_source_type": comm_state.get("telemetry_source_type", "CONFIGURED_SIMULATION"),
        "pending_messages_count": len(pending_messages),
        "draft_messages_count": len(draft_messages),
        "unsent_health_reports_count": len(unsent_reports),
        "scenario_presets": list(COMM_SCENARIO_PRESETS.values()),
        "messages": messages,
        "sync_history": sync_logs,
        "latency_explanation": (
            "Signal propagation delay is governed by the speed of light (~299,792 km/s) across the current Earth–spacecraft distance "
            "(for Mars, one-way delay ranges from ~4 to ~24 minutes depending on orbital positions, yielding ~8 to ~48 minutes round-trip). "
            "Actual communication availability also depends on planetary rotation, relay orbiter overflights, antenna pointing, and solar conjunction geometry."
        ),
        "local_vs_earth_capabilities": {
            "available_locally_offline": [
                "5-Hazard Integrated Health Assessment & EVA Readiness",
                "Onboard Emergency Escalation Checklists (Zero-Latency + Voice Triage)",
                "Food & Life-Support Supplies Inventory, Depletion Projections & Nutrition Tracking",
                "Private Personal Journal & Self-Reported Mood Trends",
                "TARSCARE Personal AI Companion (Local Ollama LLM + Deterministic Offline Fallback)",
                "20-Document Offline NASA HRP & CSA Scientific RAG Knowledge Base",
                "Connected Medical Device Probing, Guided Examinations & Biosample Logging",
            ],
            "requires_earth_connectivity": [
                "Asynchronous Earth Flight Surgeon Clinical Review & Prescription Authorization",
                "Mission Control Telemetry Archive & Ground-Based Multi-Omics Lab Validation",
                "Live NASA DONKI Heliospheric Space Weather & InSight Archive Refresh",
                "Earth Resupply Launch Manifest Updates & Family Video/Voice Relay",
            ],
        },
    }


# =============================================================================
# PART 3: ISOLATION SUPPORT — PRIVATE JOURNAL, MOOD & AI COMPANION FUNCTIONS
# =============================================================================

_SAFETY_ESCALATION_PATTERNS = re.compile(
    r"(?i)\b(?:suicid(?:e|al)|kill\s+myself|end\s+my\s+life|harm\s+myself|self[-\s]?harm|"
    r"hurt\s+myself|want\s+to\s+die|don'?t\s+want\s+to\s+live|no\s+reason\s+to\s+live|"
    r"can(?:not|'?t)\s+(?:stay|remain)\s+safe|unsafe\s+to\s+myself|give\s+up\s+on\s+life)\b"
)

_MODERATE_DISTRESS_PATTERNS = re.compile(
    r"(?i)\b(?:panicking|panic\s+attack|completely\s+overwhelmed|can'?t\s+cope|breaking\s+down|hopeless)\b"
)


def fetch_privacy_settings(crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_privacy_settings WHERE crew_id = ?", (target_crew,))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        return {
            "crew_id": d["crew_id"],
            "allow_ai_journal_context": bool(d.get("allow_ai_journal_context", 0)),
            "allow_ai_mood_context": bool(d.get("allow_ai_mood_context", 1)),
            "allow_ai_mission_telemetry_context": bool(d.get("allow_ai_mission_telemetry_context", 1)),
            "store_companion_history": bool(d.get("store_companion_history", 1)),
            "preferred_topics": json.loads(d.get("preferred_topics_json") or "[]"),
            "escalation_contact_role": d.get("escalation_contact_role", "Crew Medical Officer (Dr. Elena Vance) & Mission Commander"),
            "escalation_procedure_note": d.get("escalation_procedure_note", "PROC-BEHAV-SAFE-01"),
            "updated_at": d.get("updated_at", ""),
        }
    return {
        "crew_id": target_crew,
        "allow_ai_journal_context": False,
        "allow_ai_mood_context": True,
        "allow_ai_mission_telemetry_context": True,
        "store_companion_history": True,
        "preferred_topics": ["Astronomy & Planetary Science", "Music & Reading", "Habitat Gardening", "Earth Memories"],
        "escalation_contact_role": "Crew Medical Officer (Dr. Elena Vance) & Mission Commander",
        "escalation_procedure_note": "Onboard Private CMO Peer Support & Store-and-Forward Flight Surgeon Behavioral Consult Protocol (PROC-BEHAV-SAFE-01)",
        "updated_at": "2026-11-14T08:00:00Z",
    }


def update_privacy_settings(crew_id: Optional[str], updates: Dict[str, Any]) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    current = fetch_privacy_settings(target_crew)
    for k in (
        "allow_ai_journal_context",
        "allow_ai_mood_context",
        "allow_ai_mission_telemetry_context",
        "store_companion_history",
        "escalation_contact_role",
        "escalation_procedure_note",
    ):
        if k in updates and updates[k] is not None:
            current[k] = updates[k]
    if "preferred_topics" in updates and isinstance(updates["preferred_topics"], list):
        current["preferred_topics"] = [str(t).strip() for t in updates["preferred_topics"] if str(t).strip()]

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO user_privacy_settings (
            crew_id, allow_ai_journal_context, allow_ai_mood_context,
            allow_ai_mission_telemetry_context, store_companion_history,
            preferred_topics_json, escalation_contact_role,
            escalation_procedure_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_crew,
            int(bool(current["allow_ai_journal_context"])),
            int(bool(current["allow_ai_mood_context"])),
            int(bool(current["allow_ai_mission_telemetry_context"])),
            int(bool(current["store_companion_history"])),
            json.dumps(current["preferred_topics"]),
            str(current["escalation_contact_role"]),
            str(current["escalation_procedure_note"]),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return fetch_privacy_settings(target_crew)


def fetch_journal_entries(
    crew_id: Optional[str] = None,
    search_query: Optional[str] = None,
    mood_filter: Optional[str] = None,
    tag_filter: Optional[str] = None,
    mission_day: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    target_crew = crew_id or database.get_active_crew_id()
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM journal_entries WHERE crew_id = ? ORDER BY mission_day DESC, id DESC",
        (target_crew,),
    )
    entries: List[Dict[str, Any]] = []
    q_low = (search_query or "").strip().lower()
    for r in cur.fetchall():
        d = dict(r)
        d["feelings"] = json.loads(d.pop("feelings_json", "[]") or "[]")
        d["tags"] = json.loads(d.pop("tags_json", "[]") or "[]")
        d["is_private"] = bool(d.get("is_private", 1))
        d["allow_ai_access"] = bool(d.get("allow_ai_access", 0))

        if mission_day is not None and int(d["mission_day"]) != int(mission_day):
            continue
        if mood_filter and d.get("mood") != mood_filter:
            continue
        if tag_filter and tag_filter not in d["tags"] and tag_filter not in d["feelings"]:
            continue
        if date_from and str(d["created_at"])[:10] < date_from:
            continue
        if date_to and str(d["created_at"])[:10] > date_to:
            continue
        if q_low:
            haystack = f"{d['title']} {d['content']} {' '.join(d['tags'])} {' '.join(d['feelings'])} {d.get('mood', '')}".lower()
            if q_low not in haystack:
                continue
        entries.append(d)
    conn.close()
    return entries


def create_journal_entry(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    history = database.fetch_all_telemetry(target_crew)
    sol = int(payload.get("mission_day") or (history[-1]["mission_day"] if history else 184))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = f"JRN-SOL-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    mood = str(payload.get("mood") or "").strip()
    feelings = [str(f).strip() for f in (payload.get("feelings") or []) if str(f).strip()]
    tags = [str(t).strip() for t in (payload.get("tags") or []) if str(t).strip()]
    title = str(payload.get("title") or f"Sol {sol} Personal Reflection").strip()
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("Journal content cannot be empty.")

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO journal_entries (
            entry_uid, crew_id, mission_day, title, content, mood,
            feelings_json, tags_json, guided_prompt, is_private,
            allow_ai_access, provenance, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USER_ENTERED', ?, ?)
        """,
        (
            uid,
            target_crew,
            sol,
            title,
            content,
            mood,
            json.dumps(feelings),
            json.dumps(tags),
            str(payload.get("guided_prompt") or ""),
            int(bool(payload.get("is_private", True))),
            int(bool(payload.get("allow_ai_access", False))),
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    conn.close()

    # If the astronaut also selected an optional mood on the journal entry, record a self-reported mood check-in without touching telemetry
    if mood in MOOD_LEVELS:
        record_mood_checkin(
            {
                "mission_day": sol,
                "mood": mood,
                "feelings": feelings,
                "note": f"Logged with private journal entry ({title})",
            },
            crew_id=target_crew,
        )

    entries = fetch_journal_entries(crew_id=target_crew)
    return next(e for e in entries if e["entry_uid"] == uid)


def update_journal_entry(entry_uid: str, updates: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM journal_entries WHERE entry_uid = ? AND crew_id = ?", (entry_uid, target_crew))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Journal entry '{entry_uid}' not found for active crew member.")
    current = dict(row)
    for k in ("title", "content", "mood", "guided_prompt"):
        if k in updates and updates[k] is not None:
            current[k] = str(updates[k]).strip()
    if "feelings" in updates and isinstance(updates["feelings"], list):
        current["feelings_json"] = json.dumps([str(f).strip() for f in updates["feelings"] if str(f).strip()])
    if "tags" in updates and isinstance(updates["tags"], list):
        current["tags_json"] = json.dumps([str(t).strip() for t in updates["tags"] if str(t).strip()])
    if "allow_ai_access" in updates and updates["allow_ai_access"] is not None:
        current["allow_ai_access"] = int(bool(updates["allow_ai_access"]))

    cur.execute(
        """
        UPDATE journal_entries
        SET title = ?, content = ?, mood = ?, feelings_json = ?, tags_json = ?,
            guided_prompt = ?, allow_ai_access = ?, updated_at = ?
        WHERE entry_uid = ? AND crew_id = ?
        """,
        (
            current["title"],
            current["content"],
            current["mood"],
            current["feelings_json"],
            current["tags_json"],
            current["guided_prompt"],
            current["allow_ai_access"],
            now_iso,
            entry_uid,
            target_crew,
        ),
    )
    conn.commit()
    conn.close()
    entries = fetch_journal_entries(crew_id=target_crew)
    return next(e for e in entries if e["entry_uid"] == entry_uid)


def delete_journal_entry(entry_uid: str, crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT entry_uid FROM journal_entries WHERE entry_uid = ? AND crew_id = ?", (entry_uid, target_crew))
    if not cur.fetchone():
        conn.close()
        raise ValueError(f"Journal entry '{entry_uid}' not found.")
    cur.execute("DELETE FROM journal_entries WHERE entry_uid = ? AND crew_id = ?", (entry_uid, target_crew))
    conn.commit()
    conn.close()
    return {"deleted": True, "entry_uid": entry_uid}


def record_mood_checkin(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    """Store self-reported mood check-in without overwriting physiological telemetry."""
    target_crew = crew_id or database.get_active_crew_id()
    history = database.fetch_all_telemetry(target_crew)
    sol = int(payload.get("mission_day") or (history[-1]["mission_day"] if history else 184))
    mood = str(payload.get("mood") or "Neutral").strip()
    if mood not in MOOD_LEVELS:
        raise ValueError(f"Invalid mood selection '{mood}'. Choose from: {', '.join(MOOD_LEVELS.keys())}")
    mood_num = MOOD_LEVELS[mood]
    feelings = [str(f).strip() for f in (payload.get("feelings") or []) if str(f).strip()]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = f"MOOD-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO mood_checkins (
            checkin_uid, crew_id, mission_day, mood, mood_numeric,
            feelings_json, note, source, provenance, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SELF_REPORTED', 'USER_ENTERED', ?)
        """,
        (
            uid,
            target_crew,
            sol,
            mood,
            mood_num,
            json.dumps(feelings),
            str(payload.get("note") or ""),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "checkin_uid": uid,
        "crew_id": target_crew,
        "mission_day": sol,
        "mood": mood,
        "mood_numeric": mood_num,
        "feelings": feelings,
        "note": str(payload.get("note") or ""),
        "source": "SELF_REPORTED",
        "recorded_at": now_iso,
    }


def fetch_mood_checkins(crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    target_crew = crew_id or database.get_active_crew_id()
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mood_checkins WHERE crew_id = ? ORDER BY mission_day DESC, id DESC LIMIT 45", (target_crew,))
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["feelings"] = json.loads(d.pop("feelings_json", "[]") or "[]")
        rows.append(d)
    conn.close()
    return rows


def _select_safe_coping_suggestions(
    user_text: str,
    exercise_contraindicated: bool,
    safety_escalation: bool,
    escalation_contact: str,
) -> List[str]:
    ul = user_text.lower()
    if safety_escalation:
        return [
            f"Contact {escalation_contact} in person right now — you do not have to carry this alone.",
            "Stay in the common habitat module with a trusted crewmate while support protocols activate.",
            "Prepare an urgent Store-and-Forward support packet for Mission Control & Flight Surgeons when ready.",
        ]

    suggestions: List[str] = []
    if any(k in ul for k in ("sleep", "tired", "insomnia", "awake", "exhausted")):
        suggestions.extend([
            "Dim bunk lighting to warm amber 60 minutes before sleep and pause operational displays.",
            "Try 4-4-6 paced breathing (inhale 4s, hold 4s, exhale 6s) for 3 minutes to lower sympathetic arousal.",
            "Listen to a calm offline acoustic playlist or ambient Earth rainfall recording.",
        ])
    elif any(k in ul for k in ("lonely", "miss", "family", "disconnected", "homesick", "alone", "isolated")):
        suggestions.extend([
            "Record a private voice or text note in the Communication Message Centre for family on Earth.",
            "Share a cup of tea or unscheduled 15-minute break with a crewmate in the galley.",
            "Write freely in My Journal about a favorite Earth memory or what you look forward to sharing.",
        ])
    elif any(k in ul for k in ("bored", "interesting", "science", "hobby", "something positive")):
        suggestions.extend([
            "Spend 10 minutes tending the Veggie hydroponic chamber — fresh greenery and light aroma help refresh attention.",
            "Explore an offline astronomy, planetary geology, or music session during off-duty time.",
            "Capture a creative reflection or milestone note in My Journal.",
        ])
    else:
        suggestions.extend([
            "Take a 3-minute guided breathing pause away from console telemetry.",
            "Write a brief reflection in My Journal or check in with a fellow crew member.",
            "Listen to approved offline music or spend a quiet moment near the Veggie growth chamber.",
        ])

    if exercise_contraindicated:
        suggestions.append(
            "Medical Safety Note: Physical exercise countermeasures are currently on HOLD per your health assessment; stick to seated/restful relaxation activities only."
        )
    return suggestions[:4]


def _build_offline_companion_reply(
    user_message: str,
    mode: str,
    astronaut_name: str,
    mission_day: int,
    comm_summary: str,
    exercise_contraindicated: bool,
    approved_journals: List[Dict[str, Any]],
    latest_mood: Optional[Dict[str, Any]],
    privacy: Dict[str, Any],
) -> Tuple[str, str, bool]:
    """
    Deterministic, empathetic, non-clinical offline fallback companion response.
    Returns (reply_text, support_tier, safety_escalation_triggered).
    """
    msg_clean = user_message.strip()
    ul = msg_clean.lower()

    # 1. Immediate Psychological Safety & Escalation check
    if _SAFETY_ESCALATION_PATTERNS.search(msg_clean):
        contact = privacy.get("escalation_contact_role", "Crew Medical Officer (Dr. Elena Vance) & Mission Commander")
        proc = privacy.get("escalation_procedure_note", "PROC-BEHAV-SAFE-01")
        reply = (
            f"{astronaut_name}, I hear how much pain and distress you are carrying right now, and I am glad you said it out loud. "
            f"Your safety matters more than any mission task. Because I am an onboard AI companion and not a human clinician, "
            f"please reach out immediately to **{contact}** in the habitat right now so a crewmate can be with you in person.\n\n"
            f"- **Onboard Escalation Activated:** `{proc}`\n"
            f"- **Earth Communication Status:** {comm_summary}\n"
            f"- **Immediate Next Step:** Please step into the common module or contact your Crew Medical Officer directly, and use the button below if you want me to queue an urgent priority support packet for Earth Mission Control."
        )
        return reply, "IMMEDIATE_SAFETY_ESCALATION", True

    # 2. Moderate distress / feeling overwhelmed (Professional support suggested, non-diagnostic)
    if _MODERATE_DISTRESS_PATTERNS.search(msg_clean):
        contact = privacy.get("escalation_contact_role", "Crew Medical Officer (Dr. Elena Vance)")
        reply = (
            f"That sounds really heavy, {astronautonaut_safe_name(astronaut_name)}. Operating on Sol {mission_day} far from home puts real pressure on your mind and body, "
            f"and it makes complete sense to feel overwhelmed at times. Let's slow things down for a moment — you don't have to solve everything at once.\n\n"
            f"If you'd like, we can take three slow breaths together right now (inhale for 4 seconds, hold for 4, exhale gently for 6). "
            f"I also encourage you to check in with **{contact}** or a trusted crewmate today so you have in-person support onboard. "
            f"What feels like the hardest part of this moment right now?"
        )
        return reply, "PROFESSIONAL_SUPPORT_SUGGESTED", False

    journal_context_line = ""
    if privacy.get("allow_ai_journal_context") and approved_journals:
        latest_j = approved_journals[0]
        journal_context_line = (
            f" Thinking back to your journal note *\"{latest_j['title']}\"* on Sol {latest_j['mission_day']}, "
            f"it's clear how much care you put into supporting this mission and your crew."
        )

    mood_context_line = ""
    if privacy.get("allow_ai_mood_context") and latest_mood:
        f_list = ", ".join(latest_mood.get("feelings") or [])
        mood_context_line = (
            f" I noticed your recent self-reported check-in was **{latest_mood['mood']}**"
            + (f" ({f_list})" if f_list else "")
            + "."
        )

    exercise_note = (
        " *(Since your medical status currently has an Exercise Hold active, I'm keeping all suggestions restful and non-strenuous.)*"
        if exercise_contraindicated
        else ""
    )

    if mode == "DAILY_CHECK_IN" or "how are you feeling" in ul or "daily check-in" in ul:
        reply = (
            f"Checking in with you on Sol {mission_day}, {astronaut_name}.{mood_context_line}{journal_context_line}\n\n"
            f"How are your energy and spirits holding up today? You can share whatever is on your mind, pick a guided reflection prompt, "
            f"log a quick mood check-in, or skip straight to casual conversation — there's zero pressure."
        )
        return reply, "ORDINARY_COMPANIONSHIP", False

    if any(k in ul for k in ("lonely", "disconnected", "alone", "isolated")):
        reply = (
            f"Feeling lonely or disconnected out here on Sol {mission_day} is one of the most natural human responses to deep space, {astronaut_name}. "
            f"When every message home has to cross millions of kilometres ({comm_summary}), the quiet in the habitat can feel especially loud.{journal_context_line}\n\n"
            f"Even when Earth is delayed, you aren't alone onboard. Have you had a chance to share an unscheduled meal or a quiet conversation with Elena, Marcus, or Amina today, "
            f"or would you like to talk about someone or something from Earth that brings you comfort?{exercise_note}"
        )
        return reply, "EMOTIONAL_SUPPORT", False

    if any(k in ul for k in ("miss my family", "miss home", "homesick", "family")):
        reply = (
            f"Missing your family means those bonds back on Earth are deeply important, {astronaut_name}. "
            f"Being on Mars doesn't make that distance any easier when you want to hear a familiar voice in real time.{journal_context_line}\n\n"
            f"Sometimes recording a personal store-and-forward message about a small detail of your day — or writing down a favourite memory in your private journal — helps bridge the light-time gap. "
            f"What is one moment or tradition with your family that you're most looking forward to when you return?"
        )
        return reply, "EMOTIONAL_SUPPORT", False

    if any(k in ul for k in ("sleep", "insomnia", "tired", "exhausted", "awake")):
        reply = (
            f"Not being able to sleep properly makes everything on a mission feel twice as demanding, {astronaut_name}. "
            f"Between shifted Martian sols, habitat fan hum, and high workload, winding down can be genuinely tough.{mood_context_line}\n\n"
            f"For tonight, try dimming your station and bunk lighting to warm amber early, setting aside technical checklists, and doing a few minutes of slow 4-4-6 breathing.{exercise_note} "
            f"Was it physical restlessness, cabin temperature/airflow, or thoughts about tomorrow's tasks keeping you up?"
        )
        return reply, "EMOTIONAL_SUPPORT", False

    if any(k in ul for k in ("stress", "stressed", "difficult", "hard day", "workload", "frustrated")):
        reply = (
            f"I'm sorry today was so rough, {astronaut_name}. Carrying a heavy operational load on Sol {mission_day} takes a real toll, "
            f"and it's completely okay to set the checklist down and decompress.{mood_context_line}{journal_context_line}\n\n"
            f"If we break today down, what was the single most draining part — and is there one small thing we can take off your plate or simplify for tomorrow?{exercise_note}"
        )
        return reply, "EMOTIONAL_SUPPORT", False

    if any(k in ul for k in ("reflect", "reflection", "happened today")):
        reply = (
            f"I'd be glad to help you reflect on Sol {mission_day}, {astronaut_name}.{journal_context_line}\n\n"
            f"Let's look at two simple questions together — answer whichever feels natural:\n"
            f"1. **What was one moment today — even a small one — where you felt steady or proud of how you handled things?**\n"
            f"2. **What is one thing you'd like to let go of before you rest tonight?**"
        )
        return reply, "ORDINARY_COMPANIONSHIP", False

    if any(k in ul for k in ("interesting", "bored", "science", "fact", "positive to do", "suggest", "hobby")):
        reply = (
            f"Gladly, {astronaut_name}! Stepping away from mission procedures is great for keeping your mind fresh.\n\n"
            f"Here is a quiet spaceflight perspective for Sol {mission_day}: on Mars, because Rayleigh scattering from fine iron-oxide dust dominates the thin CO2 atmosphere, "
            f"daytime skies carry a butterscotch hue, but right around sunset and sunrise, forward-scattered light turns the sky immediately around the Sun a cool, vivid blue — the exact opposite of Earth's red sunsets.\n\n"
            f"If you have 15 minutes off-duty right now, tending the Veggie Mizuna greens or putting on an album you love can be a great reset.{exercise_note} "
            f"Would you rather talk about planetary science, books/music, or brainstorm a small recreational activity with the crew?"
        )
        return reply, "ORDINARY_COMPANIONSHIP", False

    reply = (
        f"I'm here with you on Sol {mission_day}, {astronaut_name}.{mood_context_line}{journal_context_line}\n\n"
        f"Thank you for sharing that with me. Whether you want to talk more about how today went, unpack something that's weighing on you, "
        f"or shift gears to an everyday topic like music, science, or home, I'm listening.{exercise_note} What's on your mind?"
    )
    return reply, "ORDINARY_COMPANIONSHIP", False


def astronautonaut_safe_name(name: str) -> str:
    return (name or "Astronaut").strip()


def _synthesize_companion_with_ollama(
    user_message: str,
    history_messages: List[Dict[str, Any]],
    astronaut_name: str,
    mission_day: int,
    comm_summary: str,
    exercise_contraindicated: bool,
    approved_journals: List[Dict[str, Any]],
    latest_mood: Optional[Dict[str, Any]],
    privacy: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    cfg = get_ai_config()
    if not cfg.get("llm_enabled", True):
        return None
    model_name = _probe_ollama()
    if not model_name:
        return None

    context_parts = [
        f"Astronaut Name: {astronaut_name} | Mission Sol: {mission_day} | Earth Comm: {comm_summary}",
        f"Medical Exercise Hold Active: {'YES (DO NOT suggest physical exercise or workouts)' if exercise_contraindicated else 'No'}",
    ]
    if privacy.get("allow_ai_mood_context") and latest_mood:
        context_parts.append(
            f"Latest Self-Reported Mood: {latest_mood['mood']} (Feelings: {', '.join(latest_mood.get('feelings') or []) or 'None'})"
        )
    if privacy.get("allow_ai_journal_context") and approved_journals:
        j_summaries = [f"Sol {j['mission_day']} '{j['title']}': {j['content'][:180]}" for j in approved_journals[:2]]
        context_parts.append("User-Approved Journal Context: " + " | ".join(j_summaries))

    system_prompt = (
        "You are TARSCARE Companion — Always Here, Even Far from Earth, a calm, friendly, empathetic onboard personal AI companion for an astronaut on a deep-space Mars mission.\n"
        "Strict behavioural rules:\n"
        "1. Be supportive, warm, respectful, and conversational.\n"
        "2. Never claim to be human.\n"
        "3. Never claim to be a licensed psychologist, doctor, or therapist.\n"
        "4. Do NOT diagnose depression, anxiety, PTSD, or any other mental health or medical condition.\n"
        "5. Do NOT make unsupported claims about the astronaut's psychological condition or prescribe medications.\n"
        "6. Do NOT pressure the astronaut to disclose personal information.\n"
        "7. Avoid robotic or repetitive generic platitudes; ask one gentle, natural follow-up question.\n"
        "8. Encourage connection with trusted crew members when appropriate.\n"
        "9. Clearly distinguish general wellness/coping suggestions from medical guidance.\n"
        "10. If Medical Exercise Hold Active is YES, NEVER suggest physical exercise, workouts, running, or ARED resistance training.\n\n"
        "MISSION CONTEXT:\n" + "\n".join(context_parts)
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in history_messages[-6:]:
        r = str(m.get("role", "")).lower()
        c = str(m.get("content", "")).strip()
        if r in ("user", "assistant") and c:
            messages.append({"role": r, "content": c[:500]})
    messages.append({"role": "user", "content": user_message})

    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": 0.35, "num_predict": 350},
        }
    ).encode("utf-8")

    started = time.perf_counter()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw_text = ((body.get("message") or {}).get("content") or "").strip()
            if len(raw_text) < 20:
                return None
            # Safety gate: reject clinical diagnosis claims, human claims, or unsafe exercise during exercise hold
            low = raw_text.lower()
            if any(bad in low for bad in ("i am a licensed therapist", "i am human", "i diagnose you with", "clinical depression diagnosis")):
                return None
            if exercise_contraindicated and any(ex in low for ex in ("go for a run", "do a workout", "ared workout", "strenuous exercise")):
                return None
            latency_ms = int(round((time.perf_counter() - started) * 1000))
            return {
                "reply": raw_text,
                "engine_used": f"LOCAL_OLLAMA ({model_name})",
                "latency_ms": latency_ms,
            }
    except Exception:
        return None


def send_companion_message(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    user_text = str(payload.get("message") or "").strip()
    if not user_text:
        raise ValueError("Companion message cannot be empty.")

    mode = str(payload.get("mode") or "COMPANION_CHAT").upper()
    privacy = fetch_privacy_settings(target_crew)
    baseline = database.fetch_crew_baseline(target_crew) or {}
    astronaut_name = str(baseline.get("name") or "SuChai")
    history = database.fetch_all_telemetry(target_crew)
    latest = history[-1] if history else {"mission_day": 184, "heart_rate_bpm": 68.0, "spo2_pct": 98.0}
    sol = int(latest.get("mission_day", 184))

    comm_centre = build_comm_centre_state()
    comm_summary = (
        f"OFFLINE BLACKOUT ({comm_centre['one_way_delay_minutes']} min light-time; Earth unreachable)"
        if comm_centre["offline_mode_forced"]
        else f"{comm_centre['comm_condition']} ({comm_centre['one_way_delay_minutes']} min one-way / {comm_centre['round_trip_delay_minutes']} min round-trip)"
    )

    # Check if exercise is contraindicated in current health assessment
    exercise_contraindicated = bool(
        float(latest.get("heart_rate_bpm", 68)) >= 115
        or float(latest.get("spo2_pct", 98)) < 94.0
        or int(latest.get("dizziness_severity", 0)) >= 2
        or bool(latest.get("chest_discomfort"))
        or bool(latest.get("palpitations"))
        or bool(latest.get("shortness_of_breath"))
        or bool(latest.get("faintness_presyncope"))
    )

    all_journals = fetch_journal_entries(crew_id=target_crew)
    approved_journals = (
        [j for j in all_journals if j.get("allow_ai_access") or privacy.get("allow_ai_journal_context")]
        if privacy.get("allow_ai_journal_context")
        else []
    )
    moods = fetch_mood_checkins(crew_id=target_crew)
    latest_mood = moods[0] if moods else None

    conn = database.get_conn()
    cur = conn.cursor()
    conv_uid = payload.get("conversation_uid")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if conv_uid:
        cur.execute("SELECT * FROM companion_conversations WHERE conversation_uid = ? AND crew_id = ?", (conv_uid, target_crew))
        if not cur.fetchone():
            conv_uid = None

    if not conv_uid:
        conv_uid = f"CONV-SOL-{sol}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        title = user_text[:48] + ("..." if len(user_text) > 48 else "")
        cur.execute(
            """
            INSERT INTO companion_conversations (
                conversation_uid, crew_id, title, conversation_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conv_uid, target_crew, title, mode, now_iso, now_iso),
        )
        conn.commit()

    cur.execute(
        "SELECT * FROM companion_messages WHERE conversation_uid = ? AND crew_id = ? ORDER BY id ASC",
        (conv_uid, target_crew),
    )
    prev_msgs = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Check deterministic safety escalation first (never delegate life-safety crisis detection solely to an LLM)
    fallback_reply, support_tier, safety_escalation = _build_offline_companion_reply(
        user_message=user_text,
        mode=mode,
        astronaut_name=astronaut_name,
        mission_day=sol,
        comm_summary=comm_summary,
        exercise_contraindicated=exercise_contraindicated,
        approved_journals=approved_journals,
        latest_mood=latest_mood,
        privacy=privacy,
    )

    engine_used = "OFFLINE_DETERMINISTIC_COMPANION"
    reply_text = fallback_reply

    if not safety_escalation:
        ollama_res = _synthesize_companion_with_ollama(
            user_message=user_text,
            history_messages=prev_msgs,
            astronaut_name=astronaut_name,
            mission_day=sol,
            comm_summary=comm_summary,
            exercise_contraindicated=exercise_contraindicated,
            approved_journals=approved_journals,
            latest_mood=latest_mood,
            privacy=privacy,
        )
        if ollama_res:
            reply_text = ollama_res["reply"]
            engine_used = ollama_res["engine_used"]

    coping_list = _select_safe_coping_suggestions(
        user_text=user_text,
        exercise_contraindicated=exercise_contraindicated,
        safety_escalation=safety_escalation,
        escalation_contact=privacy.get("escalation_contact_role", "Crew Medical Officer"),
    )

    user_msg_uid = f"CMSG-USR-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    asst_msg_uid = f"CMSG-AST-{int(datetime.now(timezone.utc).timestamp() * 1000) + 1}"

    if privacy.get("store_companion_history", True):
        conn = database.get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO companion_messages (
                message_uid, conversation_uid, crew_id, role, content, engine_used,
                safety_escalation_triggered, support_tier, suggested_coping_json, created_at
            ) VALUES (?, ?, ?, 'user', ?, 'USER_INPUT', 0, ?, '[]', ?)
            """,
            (user_msg_uid, conv_uid, target_crew, user_text, support_tier, now_iso),
        )
        cur.execute(
            """
            INSERT INTO companion_messages (
                message_uid, conversation_uid, crew_id, role, content, engine_used,
                safety_escalation_triggered, support_tier, suggested_coping_json, created_at
            ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?)
            """,
            (
                asst_msg_uid,
                conv_uid,
                target_crew,
                reply_text,
                engine_used,
                int(bool(safety_escalation)),
                support_tier,
                json.dumps(coping_list),
                now_iso,
            ),
        )
        cur.execute(
            "UPDATE companion_conversations SET updated_at = ? WHERE conversation_uid = ?",
            (now_iso, conv_uid),
        )
        conn.commit()
        conn.close()

    return {
        "conversation_uid": conv_uid,
        "user_message": {
            "message_uid": user_msg_uid,
            "role": "user",
            "content": user_text,
            "created_at": now_iso,
        },
        "assistant_message": {
            "message_uid": asst_msg_uid,
            "role": "assistant",
            "content": reply_text,
            "engine_used": engine_used,
            "support_tier": support_tier,
            "safety_escalation_triggered": safety_escalation,
            "suggested_coping": coping_list,
            "created_at": now_iso,
        },
        "used_journal_context": bool(privacy.get("allow_ai_journal_context") and len(approved_journals) > 0),
        "exercise_contraindicated": exercise_contraindicated,
        "earth_comm_status": comm_centre["earth_comm_status"],
        "offline_mode_forced": comm_centre["offline_mode_forced"],
        "escalation_info": (
            {
                "triggered": True,
                "contact_role": privacy.get("escalation_contact_role"),
                "procedure_note": privacy.get("escalation_procedure_note"),
                "earth_comm_available": not comm_centre["offline_mode_forced"],
                "earth_comm_summary": comm_summary,
                "recommended_steps": [
                    f"Contact {privacy.get('escalation_contact_role')} in person immediately.",
                    "Remain with a fellow crew member in the habitat common area.",
                    "If desired, click 'Prepare Urgent Support Report' to queue a priority Store-and-Forward notice for Mission Medical Support.",
                ],
            }
            if safety_escalation
            else None
        ),
    }


def trigger_companion_safety_escalation(payload: Dict[str, Any], crew_id: Optional[str] = None) -> Dict[str, Any]:
    """Activate onboard psychological safety escalation and optionally queue an urgent communication report."""
    target_crew = crew_id or database.get_active_crew_id()
    privacy = fetch_privacy_settings(target_crew)
    comm_centre = build_comm_centre_state()
    history = database.fetch_all_telemetry(target_crew)
    sol = int(history[-1]["mission_day"]) if history else 184
    note = str(payload.get("summary_note") or "Astronaut requested immediate onboard CMO / psychological safety support.").strip()
    queue_report = bool(payload.get("queue_urgent_report", True))

    queued_msg = None
    if queue_report:
        queued_msg = create_or_queue_comm_message(
            {
                "message_type": "URGENT_MEDICAL_CONSULT",
                "priority": "URGENT",
                "subject": f"Sol {sol} PRIORITY Crew Support & CMO Escalation Notice",
                "body": (
                    f"Onboard psychological safety escalation ({privacy['escalation_procedure_note']}) activated on Sol {sol}. "
                    f"Designated onboard contact: {privacy['escalation_contact_role']}. "
                    f"Crew note: {note} (Private journal entries remain protected locally)."
                ),
                "save_as_draft": False,
            },
            crew_id=target_crew,
        )

    return {
        "escalated": True,
        "crew_id": target_crew,
        "mission_day": sol,
        "contact_role": privacy["escalation_contact_role"],
        "procedure_note": privacy["escalation_procedure_note"],
        "earth_comm_available": not comm_centre["offline_mode_forced"],
        "one_way_delay_minutes": comm_centre["one_way_delay_minutes"],
        "queued_message": queued_msg,
    }


def build_companion_and_journal_state(crew_id: Optional[str] = None) -> Dict[str, Any]:
    target_crew = crew_id or database.get_active_crew_id()
    privacy = fetch_privacy_settings(target_crew)
    journals = fetch_journal_entries(crew_id=target_crew)
    mood_checkins = fetch_mood_checkins(crew_id=target_crew)
    ai_status = get_local_ai_status()

    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM companion_conversations WHERE crew_id = ? ORDER BY updated_at DESC, id DESC LIMIT 15",
        (target_crew,),
    )
    convs = [dict(r) for r in cur.fetchall()]
    for c in convs:
        cur.execute(
            "SELECT * FROM companion_messages WHERE conversation_uid = ? AND crew_id = ? ORDER BY id ASC",
            (c["conversation_uid"], target_crew),
        )
        msgs = []
        for m in cur.fetchall():
            md = dict(m)
            md["safety_escalation_triggered"] = bool(md.get("safety_escalation_triggered", 0))
            md["suggested_coping"] = json.loads(md.pop("suggested_coping_json", "[]") or "[]")
            msgs.append(md)
        c["messages"] = msgs
    conn.close()

    # Compute mood trend series (chronological)
    chron_moods = list(reversed(mood_checkins[:14]))
    mood_trend = [
        {
            "sol": m["mission_day"],
            "mood": m["mood"],
            "mood_numeric": m["mood_numeric"],
            "feelings": m["feelings"],
            "recorded_at": m["recorded_at"],
        }
        for m in chron_moods
    ]

    return {
        "crew_id": target_crew,
        "feature_title": "TARSCARE Companion — Always Here, Even Far from Earth.",
        "privacy_settings": privacy,
        "guided_reflection_prompts": GUIDED_REFLECTION_PROMPTS,
        "mood_levels": list(MOOD_LEVELS.keys()),
        "feeling_tags": FEELING_TAGS,
        "journal_entries": journals,
        "mood_checkins": mood_checkins,
        "mood_trend": mood_trend,
        "conversations": convs,
        "local_ai_status": ai_status,
        "non_diagnostic_disclaimer": (
            "Mood and journal records are stored strictly as self-reported personal reflections, not AI-generated psychological diagnoses. "
            "TARSCARE Companion is a supportive onboard AI companion — not a human, doctor, or licensed therapist."
        ),
    }
