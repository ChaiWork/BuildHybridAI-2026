# TARSCARE — Your Personal Health Companion in Deep Space
**NASA Space Apps Challenge 2026 · Team Milky Has Its Own Way**

**TARSCARE** is a calm, offline-first autonomous health-monitoring and self-assessment web application designed for astronauts on long-duration deep-space missions, particularly Mars missions. Built atop the **TARSCARE** FastAPI + SQLite + local RAG backend (`backend/`, `tarscare_local.db`, `/api/*`), TARSCARE enables astronauts to answer three urgent questions at a glance — **How am I doing?**, **What has changed?**, and **Should I take any action?** — explore their body systems interactively, monitor NASA's five human-spaceflight hazards, run self-assessments with dual manual/symptom entry, and consult offline NASA & CSA research without relying on Earth connectivity.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Frontend["TARSCARE Frontend (React + TypeScript + Tailwind + Host Grotesk + Recharts)"]
        V1["1. Mission Overview & Interactive Human Body"]
        V2["2. Health Assessment (Manual + Symptoms + Behavioral Check-In)"]
        V3["3. Spaceflight Hazards (5 Four-Step Modules)"]
        V4["4. AI Health Assistant (Offline NASA/CSA RAG Chat)"]
        V5["5. Health History (7/14/30-Sol Logs & Export Reports)"]
        V6["6. Communication Status (Connected / Delayed / Offline + Stack)"]
    end

    subgraph Backend["TARSCARE AI Autonomous Backend (Python + FastAPI + Pydantic)"]
        API["REST API (/api/state, /api/baseline, /api/measurements, /api/assessment/evaluate, /api/emergency/escalate, /api/rag/query, /api/ai/*, /api/comm/*, /api/reports/generate)"]
        ENG["Integrated 5-Hazard + Cardiopulmonary Assessment Engine & Priority Safety Gate"]
        RAG["Full-Corpus Hybrid RAG Engine (BM25/TF-IDF + Cached Sentence-Transformers + Local Ollama /api/chat + Conflict & Safety Verifier)"]
        SF["Simulated Store-and-Forward Earth Sync Queue"]
        EMG["Zero-Latency Onboard Emergency Escalation Checklist & Client Fallback"]
    end

    subgraph Storage["Local Persistence & Scientific Knowledge"]
        DB[("SQLite Database (tarscare_local.db, 30-Sol Baseline + Calibration Audit + User Logs)")]
        CORPUS[("16 Offline Docs: 15 NASA/CSA Research Refs + TARSCARE-SPEC-01 Operational Spec")]
    end

    Frontend <--> API
    API --> ENG
    ENG --> RAG
    API --> SF
    API --> EMG
    ENG <--> DB
    SF <--> DB
    RAG <--> CORPUS
```

---

## 2. Quick-Start Installation & How to Run

### Prerequisites
- **Python 3.10+** (`fastapi`, `uvicorn`, `pydantic`, plus optional local `sentence-transformers` or local `ollama` if available)
- **Node.js 18+** and `npm`

### Step 1: Start the Local Backend Server (`http://127.0.0.1:8000`)
```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
On startup, `backend/database.py` initializes or non-destructively migrates `backend/tarscare_local.db` with 30 Sols of realistic synthetic Mars mission telemetry (`Sol 155–184`), personal baseline calibration audit storage, and 16 pre-bundled offline documents (`15` NASA/CSA research references plus `TARSCARE-SPEC-01` operational safety specification).
- **Offline Semantic RAG & Local Ollama LLM (`127.0.0.1:11434`):**
  - Install [Ollama](https://ollama.com) locally and pull an offline chat model (for example `ollama pull qwen2.5:3b` or `ollama pull llama3.2:3b`), plus optional embedding model `ollama pull nomic-embed-text`.
  - `backend/local_ai_rag.py` probes `http://127.0.0.1:11434/api/tags` (filtering out embedding-only models), runs full-corpus hybrid retrieval blending TF-IDF lexical relevance with locally cached `all-MiniLM-L6-v2` embeddings (`HF_HUB_OFFLINE=1` — zero cloud requests), injects live telemetry and personal baseline comparisons for `SuChai`, synthesizes grounded answers via `/api/chat` (`keep_alive: 15m`), and verifies `[DOC-ID]` citations and medication safety constraints before returning responses.
  - If Ollama is stopped or toggled off (`POST /api/ai/config`), TARSCARE falls back automatically to deterministic offline RAG (`OFFLINE_SENTENCE_TRANSFORMERS` or `DETERMINISTIC_OFFLINE_RAG`).

### Step 2: Start the TARSCARE Frontend (`http://127.0.0.1:5173`)
In a second terminal:
```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```
Open **http://localhost:5173** in your browser. Vite proxies `/api/*` requests to `http://127.0.0.1:8000`.

### Step 3: Automated Safety & Build Verification
```powershell
# Backend medical safety, API, offline RAG & sync tests (isolated temp SQLite DB)
python -m pytest backend/tests/test_tarscare_safety.py -v

# Frontend TypeScript check and production bundle
cd frontend
npx tsc --noEmit
npm run build
```

---

## 3. Six Core Navigation Views

1. **Mission Overview** — Opens immediately with a **3-question crew wayfinding triage band** (*How am I doing?*, *What has changed?*, *Should I take any action?*), centered **Interactive Human Body** with 7-Sol sparklines and baseline comparisons, **Vital Signs vs. Personal Baseline** (`BPM`, `mmHg`, `SpO₂`, `°C`, sleep, explicit `Mood` and `Stress` scores), **Five Spaceflight Hazard** cards, dual-axis **7 / 14 / 30-Sol Health Trends** (with `<Legend />` and Cabin Temp), **Important Alerts & Prioritized Actions**, and direct **Personal Baseline Calibration** (`GET/POST /api/baseline`) plus emergency escalation launch.
2. **Health Assessment** — Dual-method entry: **Method 1** manual core & extended ECLSS/behavioral/musculoskeletal/radiation inputs across `0g`, `0.38g`, and `1g`, plus **Method 2** structured symptom pills including **Cardiopulmonary Red Flags (Urgent)** (`Chest pain / discomfort`, `Palpitations`, `Shortness of breath`, `Faintness / presyncope`), and an optional **Behavioral & Sleep Check-In** stored independently without duplicating telemetry rows. Produces a deterministic severity-sorted recommendation stack (`IMMEDIATE > HIGH > ROUTINE`), active **Exercise Hold** gating during `CRITICAL` states, and critical auto-escalation banners.
3. **Spaceflight Hazards** — Detailed modules for **Space Radiation**, **Isolation & Confinement**, **Distance from Earth**, **Gravity Fields** (with `1g` / `0g` / `0.38g` explorer synced to active telemetry and exercise-hold warnings), and **Hostile and Closed Environments**. Each displays dual-series 14-Sol charts (`mSv/day` vs `mGy`, `CO₂` vs `Cabin Temp`), four-step guidance, and synced configured warning threshold controls.
4. **AI Health Assistant** — Offline-first companion backed by `/api/rag/query`, live Ollama model selector & `Local LLM` toggle, full-text **Offline Document Reader** (`Read Offline` modal without requiring external internet URLs), explicit **Conflict & Regime Distinction Notices**, separated **NASA/CSA Scientific Evidence** vs **TARSCARE Operational Procedures**, and strict medication/out-of-scope surgical refusal plus post-LLM safety verification gates.
5. **Health History** — Filter longitudinal physiological logs (`7d` / `14d` / `30d`, `All Data` / `Simulated` / `User-Entered`), inspect separate **Behavioral & Sleep Check-In History** (with Show/Hide toggle for private reflections), review historical alerts, generate queued autonomous health summary reports, and export comprehensive Markdown reports locally.
6. **Communication Status** — Switch between **Connected**, **Delayed (Mars Nominal)**, and **Offline (Blackout)**, verify **Store-and-Forward** queue blocking during `OFFLINE` blackout (`BLOCKED_OFFLINE`) and synchronization on reconnect, launch zero-latency Emergency Escalation Protocols (`EMG-CMO-CARDIOPULM-01` etc. with client-side fallback), and manage Local Ollama + Offline RAG diagnostics.

---

## 4. Scientific Accuracy, Provenance & Medical Safety Guardrails

- **Deterministic Critical Priority & Exercise Safety Gate:** All recommendations sort strictly `IMMEDIATE > HIGH > ROUTINE`. During `CRITICAL` vitals, hypoxemia (`SpO₂ < 94%`), presyncope, or cardiopulmonary red-flag symptoms, routine exercise/ARED prescriptions are suppressed and replaced with explicit Exercise Hold instructions and mandatory Crew Medical Officer (CMO) hardware/ECG gap notices.
- **Radiation Unit Separation:** Always preserves and separates physical **absorbed dose (`Gy` / `mGy`)** from biologically weighted **equivalent/effective dose (`Sv` / `mSv`)**; never invents NASA-approved flight limits (user-configurable alert thresholds are explicitly labeled non-NASA prototype defaults).
- **NASA RDP / ARMAS Context:** Explicitly states that ARMAS measurements represent Earth high-altitude aircraft datasets benchmarking dosimetry pipelines, not direct Martian surface dosimetry.
- **Non-Diagnostic, Non-Prescribing & Prototype Boundary:** Tracks mood, stress, sleep, and cabin environment trends without automatically diagnosing psychiatric conditions or clinical infections, refuses medication dosage or invasive/surgical procedure requests, and is a software prototype decision-support aid — **not** clinically certified or flight-qualified medical software.
- **Explicit Data Provenance:** Distinguishes `Simulated Data`, `User-Entered Data`, `Simulated Env`, `Real Research Data`, and `System Operational Spec` throughout UI, SQLite persistence, and exported reports.
