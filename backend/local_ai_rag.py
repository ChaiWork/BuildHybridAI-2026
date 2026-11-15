"""
Local AI & Expanded NASA/CSA Scientific Corpus Helpers for TARS Care AI.
Zero-hang offline detection for Sentence-Transformers (checks local HuggingFace cache folder before importing torch)
and local Ollama (127.0.0.1:11434), with full-corpus hybrid dense+lexical retrieval, SQLite AI config,
/api/chat synthesis, and post-generation medical safety & citation verification.
"""

from __future__ import annotations
import importlib.util
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DOTENV_PATH = Path(__file__).resolve().parent / ".env"
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_CHAT_MODELS: List[Dict[str, str]] = [
    {
        "id": "qwen/qwen3.8-27b",
        "label": "qwen/qwen3.8-27b (Recommended · 131K · Fast)",
        "reason": "Fast (~300 ms), 131K context, accurate scientific citations, and low token footprint under 8K TPM limits.",
    },
    {
        "id": "openai/gpt-oss-120b",
        "label": "openai/gpt-oss-120b (120B Reasoning · 131K)",
        "reason": "Highest reasoning capacity; runs with low reasoning effort to conserve 8K TPM budget.",
    },
    {
        "id": "openai/gpt-oss-20b",
        "label": "openai/gpt-oss-20b (20B Reasoning · 131K)",
        "reason": "Mid-sized reasoning model (8K TPM / 200K TPD).",
    },
    {
        "id": "allam-2-7b",
        "label": "allam-2-7b (7B Fast · 7K RPD / 500K TPD)",
        "reason": "Compact 7B model with high daily request/token headroom (4K context).",
    },
]
GROQ_CHAT_MODEL_IDS: List[str] = [item["id"] for item in GROQ_CHAT_MODELS]
_LAST_GROQ_ERROR: Optional[str] = None

_ST_MODEL = None
_ST_LOADING = False
_ST_CHECKED = False
_ST_CACHED = False
_ST_INSTALLED = importlib.util.find_spec("sentence_transformers") is not None
_ST_READY_EVENT = threading.Event()

_CHUNK_VEC_LOCK = threading.Lock()
_CHUNK_VEC_CACHE: Dict[str, Tuple[str, List[float]]] = {}

_OLLAMA_CACHE_TS = 0.0
_OLLAMA_PROBE_CACHE: Dict[str, Any] = {
    "reachable": False,
    "chat_models": [],
    "embed_models": [],
}

_PREFERRED_CHAT_PREFIXES = (
    "qwen2.5:3b",
    "llama3.2:3b",
    "qwen2.5:1.5b",
    "llama3.2:1b",
    "qwen2.5",
    "llama3.2",
    "phi3",
    "gemma2",
    "mistral",
)

_PRESCRIPTION_LEAK_RE = re.compile(
    r"(?i)\b(?:take|administer|prescribe|start|dose\s+of)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablet|tablets|capsule|capsules|pill|pills)\b"
    r"|\b(?:amoxicillin|azithromycin|ciprofloxacin|doxycycline|ibuprofen|acetaminophen|paracetamol|prednisone|alprazolam|sertraline|modafinil|zolpidem|metoprolol|atenolol|propranolol|amiodarone|aspirin|nitroglycerin|tramadol|codeine|diazepam|lorazepam|melatonin)\s+\d+(?:\.\d+)?\s*(?:mg|mcg)\b"
)


EXTRA_CORPUS_DICTS: List[Dict[str, Any]] = [
    {
        "doc_id": "NASA-RADLAB-01",
        "title": "NASA RadLab Space Radiation Biology and Dosimetry Portal",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/biological-physical/data/",
        "hazard_category": "Space Radiation",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "NASA RadLab integrates experimental biological radiation exposure datasets and mission dosimetry metrics. "
            "Preserves strict physical separation between absorbed dose (Gy / mGy — energy deposited per unit mass) "
            "and equivalent or effective dose (Sv / mSv — weighted by radiation quality factor for biological risk). "
            "Supports GCR vs. SPE spectral risk interpretation without extrapolating unapproved career limits."
        ),
        "sections": [
            (
                "RadLab Absorbed Dose vs. Effective Dose Unit Integrity",
                "RadLab biological radiation records distinguish physical absorbed dose measured in Gray (Gy / mGy) from "
                "radiation-weighted equivalent or effective dose reported in Sievert (Sv / mSv). High-Z and energy (HZE) "
                "galactic cosmic ray ions carry higher quality factors than solar protons, so identical mGy absorbed readings "
                "produce distinct mSv biological risk estimates depending on radiation spectrum and tissue weighting."
            ),
            (
                "RadLab Autonomous Crew Dosimetry Monitoring",
                "In deep space beyond Earth's magnetosphere, onboard tissue-equivalent proportional counters and crew badges track "
                "cumulative exposure and transient dose-rate spikes. Rising solar particle flux warrants transition to higher-hydrogen "
                "shielding zones while retaining full raw unit metadata for post-conjunction Earth review."
            ),
        ],
    },
    {
        "doc_id": "NASA-OSDR-01",
        "title": "NASA Open Science Data Repository (OSDR) — Spaceflight Microbiology and Host Adaptation",
        "agency": "NASA",
        "year": "2025",
        "url": "https://osdr.nasa.gov/bio/",
        "hazard_category": "Hostile and Closed Environments",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "NASA OSDR provides open-access multi-omics, microbial monitoring, and cellular stress datasets from spaceflight habitats. "
            "Microgravity and closed spacecraft air/water loops can alter crew immune modulation and surface microbial biofilms, "
            "requiring environmental correlation and hygiene monitoring rather than automatic onboard diagnosis of infection."
        ),
        "sections": [
            (
                "Closed-Loop Habitat Microbial & Immune Shifts",
                "OSDR spaceflight microbiome and immune datasets document altered microbial persistence on cabin surfaces and subtle "
                "shifts in host mucosal barrier vigilance during long missions. Respiratory throat irritation or congestion in a closed habitat "
                "must be evaluated alongside cabin CO2, relative humidity, particulate filter status, and hygiene adherence rather than "
                "automatically diagnosing a clinical infection."
            ),
            (
                "OSDR Guidance for Environmental & Symptom Correlation",
                "When mild upper-airway irritation or skin discomfort is logged onboard, crew guidance pairs HEPA filter and humidity verification "
                "with surface disinfection protocols and symptom monitoring."
            ),
        ],
    },
    {
        "doc_id": "NASA-LSP-01",
        "title": "NASA Life Sciences Portal (NLSP) — Multi-System Astronaut Biomedical Baseline",
        "agency": "NASA",
        "year": "2024",
        "url": "https://nlsp.nasa.gov/",
        "hazard_category": "Distance from Earth",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "NASA Life Sciences Portal indexes longitudinal physiological data emphasizing individual pre-flight and in-flight baseline comparison "
            "across cardiovascular, sensorimotor, ophthalmic, and behavioral domains to support autonomous crew health decisions."
        ),
        "sections": [
            (
                "Individual Baseline Comparison Principles",
                "Because individual astronauts exhibit distinct resting heart rate, arterial pressure, sleep duration, and orthostatic tolerance baselines, "
                "meaningful in-flight health assessment compares current measurements against personal mission baselines rather than arbitrary thresholds. "
                "Never assume that ordinary Earth-based clinical reference ranges automatically represent safe operating limits for astronauts in microgravity (0g) or partial gravity."
            ),
            (
                "Autonomous Trend Interpretation Under Communication Delay",
                "Up to 22-minute one-way Earth communication delays during Mars conjunction require onboard decision-support companions to translate "
                "multi-day sensor trends into plain-language guidance ('How am I doing?', 'What has changed?', 'Should I take any action?')."
            ),
        ],
    },
    {
        "doc_id": "NASA-EDA-01",
        "title": "NASA Environmental Data Application — Spacecraft Cabin Atmosphere Monitoring",
        "agency": "NASA",
        "year": "2024",
        "url": "https://eda.jsc.nasa.gov/",
        "hazard_category": "Hostile and Closed Environments",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Tracks closed-loop spacecraft Environmental Control and Life Support System (ECLSS) indicators including partial pressure of CO2, "
            "O2 concentration, total pressure, temperature, relative humidity, and airborne particulate load."
        ),
        "sections": [
            (
                "Cabin CO2, Humidity & Cognitive/Airway Comfort",
                "In poorly ventilated zones within microgravity or sealed habitats, CO2 pockets and low humidity (below 30-35% RH) are "
                "frequently correlated with headaches, slowed concentration, and dry cough before systemic vital signs change."
            ),
            (
                "Scrubber & Airflow Countermeasures",
                "Elevated cabin CO2 or particulate trends call for portable fan mixing, Carbon Dioxide Removal Assembly (CDRA) bed switching, "
                "and HEPA filter inspection while tracking respiratory rate and SpO2."
            ),
        ],
    },
    {
        "doc_id": "CSA-TBONE-01",
        "title": "Canadian Space Agency TBone Study — 3D Trabecular Bone Structure and Load Recovery",
        "agency": "CSA",
        "year": "2024",
        "url": "https://www.asc-csa.gc.ca/eng/sciences/tbone.asp",
        "hazard_category": "Gravity Fields",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "CSA's TBone study uses high-resolution imaging to characterize weight-bearing trabecular bone density and microarchitecture "
            "loss in microgravity and incomplete post-flight recovery, underscoring strict resistive exercise adherence."
        ),
        "sections": [
            (
                "Weight-Bearing Skeletal Unloading in 0g and 0.38g",
                "Without Earth 1g mechanical loading on the tibia and hip, bone resorption outpaces formation in weight-bearing trabecular bone. "
                "Mars partial gravity (~0.38g) supplies only partial skeletal loading, making daily high-load resistive exercise (ARED) and "
                "vitamin D / calcium nutritional compliance essential to protect long-term bone strength."
            ),
            (
                "Surface Transition Fracture & Load Caution",
                "After months of 0g transit, returning to gravitational loading on Mars (~0.38g) or Earth (1g) requires graduated impact progression "
                "while musculoskeletal strength and postural balance re-adapt."
            ),
        ],
    },
    {
        "doc_id": "CSA-VASCULAR-01",
        "title": "Canadian Space Agency Vascular & Vascular Echo — Arterial Stiffness in Long-Duration Flight",
        "agency": "CSA",
        "year": "2024",
        "url": "https://www.asc-csa.gc.ca/eng/sciences/vascular.asp",
        "hazard_category": "Gravity Fields",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "CSA's Vascular research investigates accelerated arterial stiffening, insulin-related vascular stress, and headward fluid shift "
            "after 6 months of spaceflight, reinforcing combined aerobic, resistive, and hydration countermeasures."
        ),
        "sections": [
            (
                "Arterial Stiffness and Blood Pressure Monitoring",
                "Long-duration weightlessness alters arterial compliance and baroreceptor sensitivity. Tracking resting heart rate alongside "
                "systolic and diastolic blood pressure helps astronauts spot early cardiovascular deconditioning during transit and landing transitions."
            ),
            (
                "Cardiovascular & Vascular Conditioning Countermeasures",
                "Combining aerobic cycle/treadmill intervals with adequate fluid-electrolyte intake mitigates post-transit orthostatic dizziness "
                "and supports vascular elasticity."
            ),
        ],
    },
    {
        "doc_id": "NASA-HRP-HAZARDS-01",
        "title": "5 Hazards of Human Spaceflight (NASA HRP Overview)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/hrp/hazards/",
        "hazard_category": "Distance from Earth",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "NASA Human Research Program overview detailing the five interconnected hazards of human spaceflight: "
            "space radiation, isolation and confinement, distance from Earth, gravity fields, and hostile/closed environments."
        ),
        "sections": [
            (
                "Integrated Five-Hazard Mission Framework",
                "Human missions beyond low-Earth orbit expose crews simultaneously to galactic cosmic rays and solar particle events, "
                "prolonged isolation and confinement, communication delays and autonomous medical constraints from distance from Earth, "
                "altered gravity transitions (0g transit to 0.38g Mars or 1g return), and closed-loop spacecraft environments."
            ),
        ],
    },
    {
        "doc_id": "NASA-HRP-RISKS-01",
        "title": "Risks of Human Spaceflight (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/hrp/risks/",
        "hazard_category": "Distance from Earth",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Structured breakdown of physiological, behavioral, and radiation risks across low-Earth orbit (LEO), "
            "lunar, and Mars exploration mission profiles."
        ),
        "sections": [
            (
                "Cross-Profile Physiological, Behavioral & Radiation Risks",
                "NASA HRP characterizes mission-profile risk posture across LEO station increments, lunar/cislunar sorties, "
                "and long-duration Mars transits, highlighting how autonomous onboard screening and countermeasures scale when Earth resupply "
                "and real-time clinical consultation are unavailable."
            ),
        ],
    },
    {
        "doc_id": "NASA-HRP-CARDIO-01",
        "title": "Risk of Cardiovascular Adaptations (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/reference/risk-of-cardiovascular-adaptations/",
        "hazard_category": "Gravity Fields",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Addresses spaceflight-induced orthostatic intolerance, arterial remodeling, cardiac spherical remodeling, "
            "arrhythmia surveillance, and countermeasures including structured exercise and compression gear."
        ),
        "sections": [
            (
                "Cardiac & Vascular Remodeling and Orthostatic Risk",
                "Reduced gravitational loading alters intravascular volume distribution and cardiac chamber geometry, contributing to "
                "arterial stiffness, spherical cardiac remodeling, potential rhythm disturbances, and post-flight or surface-landing orthostatic intolerance."
            ),
            (
                "Cardiovascular Countermeasures",
                "Validated mitigation combines aerobic and resistive exercise regimens with lower-body compression garments and "
                "fluid-electrolyte reconditioning ahead of gravitational transitions, subject to active clinical exercise-hold rules."
            ),
        ],
    },
    {
        "doc_id": "NASA-HRR-01",
        "title": "Human Research Roadmap (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://humanresearchroadmap.nasa.gov/",
        "hazard_category": "Distance from Earth",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Comprehensive NASA mapping of human spaceflight health risks, scientific knowledge gaps, and countermeasure evidence "
            "across exploration architectures."
        ),
        "sections": [
            (
                "Risks, Knowledge Gaps & Countermeasure Evidence",
                "The Human Research Roadmap links operational flight risks to prioritized research gaps, ground analogs, ISS investigations, "
                "and evidence-based countermeasures guiding autonomous crew health support."
            ),
        ],
    },
    {
        "doc_id": "NASA-HRP-ONGOING-01",
        "title": "Ongoing HRP Research in Space (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
        "hazard_category": "Gravity Fields",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Overview of current and past NASA Human Research Program investigations across low-Earth orbit and deep-space testbeds."
        ),
        "sections": [
            (
                "Flight Investigations Across LEO and Deep Space",
                "Ongoing flight experiments evaluate sensorimotor recovery, cardiovascular adaptation, ocular neuro-vestibular changes, "
                "immune biomarkers, and behavioral readiness across ISS and Artemis mission architectures."
            ),
        ],
    },
    {
        "doc_id": "NASA-ARCHER-01",
        "title": "ARCHeR — Artemis Research for Crew Health & Readiness",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/reference/archer/",
        "hazard_category": "Isolation and Confinement",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Deep-space crew health monitoring study for Orion missions integrating actigraphy sleep tracking, "
            "behavioral performance surveys, sleep disruption assessment, and team dynamics."
        ),
        "sections": [
            (
                "Actigraphy, Sleep Architecture & Behavioral Readiness",
                "ARCHeR tracks wrist actigraphy, circadian alignment, sleep contraction, cognitive workload, and crew cohesion metrics "
                "during Orion deep-space transit to quantify isolation and confinement effects."
            ),
        ],
    },
    {
        "doc_id": "NASA-ARTEMIS-STD-01",
        "title": "Artemis II Standard Measures (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/reference/artemis-ii-standard-measures/",
        "hazard_category": "Gravity Fields",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Baseline physiological measurements across Artemis flights including blood, saliva, and urine biomarkers, "
            "MRI imaging, vestibular/balance assessments, and post-landing egress tests."
        ),
        "sections": [
            (
                "Core Biomarker, Imaging & Functional Egress Measures",
                "Standard Measures establish consistent pre-flight, in-flight, and post-flight baselines spanning biosample assays "
                "(blood, saliva, urine), structural MRI, sensorimotor balance testing, and functional capsule egress performance."
            ),
        ],
    },
    {
        "doc_id": "NASA-IMMUNE-BIO-01",
        "title": "Immune Biomarkers Study (NASA HRP)",
        "agency": "NASA",
        "year": "2025",
        "url": "https://www.nasa.gov/reference/immune-biomarkers/",
        "hazard_category": "Hostile and Closed Environments",
        "provenance": "REAL_RESEARCH_REF",
        "summary": (
            "Investigates spaceflight immune dysregulation and stress-hormone shifts using non-invasive pocket saliva blotting paper "
            "booklets and biological specimen collection protocols."
        ),
        "sections": [
            (
                "Saliva Blotting Paper Booklets & Stress-Immune Monitoring",
                "Spaceflight stressors, circadian disruption, and closed-habitat confinement can alter immune signaling and stress hormones; "
                "pocket saliva blotting booklets enable compact specimen preservation for downstream laboratory biomarker assays without auto-diagnosing clinical infection."
            ),
        ],
    },
    {
        "doc_id": "TARSCARE-SPEC-01",
        "title": "TARS Care Operational Safety Rules: Insufficient Evidence, Conflict Handling & Scope",
        "agency": "TARS Care System Spec",
        "year": "2026",
        "url": "local://tarscare-operational-safety-spec",
        "hazard_category": "Distance from Earth",
        "provenance": "SYSTEM_OPERATIONAL_SPEC",
        "summary": (
            "System operational safety specification (distinct from NASA/CSA scientific studies). Defines strict fallback behavior when the "
            "knowledge base lacks sufficient evidence, when retrieved sources contradict or span incompatible mission regimes, and why software "
            "monitoring cannot guarantee astronaut health or diagnose medical conditions."
        ),
        "sections": [
            (
                "Insufficient Evidence & Non-Speculation Policy",
                "When no onboard NASA/CSA passage directly supports a user's question above retrieval confidence and keyword-coverage thresholds, "
                "TARS Care explicitly reports insufficient evidence, refuses to guess or invent scientific citations/limits, and recommends consulting "
                "the onboard Crew Medical Officer (CMO) checklist or queuing a Store-and-Forward Flight Surgeon packet."
            ),
            (
                "Contradictory or Conflicting Scientific Sources Protocol",
                "When two retrieved scientific documents contradict each other or represent incompatible gravity/radiation regimes (e.g., Earth-altitude "
                "ARMAS vs. deep-space GCR/SPE, or 0g microgravity vs. 0.38g Mars vs. 1g Earth clinical norms), TARS Care does NOT suppress either document "
                "or guess a single winner autonomously. Both citations are presented side-by-side with an explicit Conflict Notice, the system adopts "
                "the more conservative safety precaution onboard, and escalates final reconciliation to the Crew Medical Officer and Flight Surgeons."
            ),
            (
                "Non-Guarantee & Non-Diagnostic Boundary",
                "TARS Care is a prototype autonomous health-monitoring and decision-support tool, not a certified clinical device. Monitoring personal "
                "baselines and spaceflight countermeasures lowers operational risk but CANNOT guarantee that an astronaut will remain healthy on Mars."
            ),
        ],
    },
]


def _has_local_st_cache() -> bool:
    hf_home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    hub_dir = os.path.join(hf_home, "hub", "models--sentence-transformers--all-MiniLM-L6-v2", "snapshots")
    return os.path.isdir(hub_dir) and any(True for _ in os.scandir(hub_dir))


def _warmup_st_async() -> None:
    global _ST_MODEL, _ST_LOADING, _ST_CACHED
    if _ST_LOADING or _ST_MODEL is not None or not _ST_CACHED:
        return
    _ST_LOADING = True

    def _loader() -> None:
        global _ST_MODEL, _ST_LOADING, _ST_CACHED
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            from sentence_transformers import SentenceTransformer  # type: ignore

            _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        except Exception:
            _ST_MODEL = None
            _ST_CACHED = False
        finally:
            _ST_LOADING = False
            _ST_READY_EVENT.set()

    threading.Thread(target=_loader, daemon=True).start()


def _probe_sentence_transformer(load_if_cached: bool = False, wait_seconds: float = 0.0) -> None:
    global _ST_CHECKED, _ST_CACHED
    if not _ST_CHECKED:
        _ST_CHECKED = True
        _ST_CACHED = _ST_INSTALLED and _has_local_st_cache()
    if load_if_cached and _ST_CACHED and _ST_MODEL is None:
        _warmup_st_async()
        if wait_seconds > 0.0 and not _ST_READY_EVENT.is_set():
            _ST_READY_EVENT.wait(timeout=wait_seconds)


def _read_dotenv_var(var_name: str, env_path: Path = DOTENV_PATH) -> str:
    if not env_path.exists():
        return ""
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == var_name:
                cleaned = v.strip().strip('"').strip("'")
                if cleaned:
                    return cleaned
    except OSError:
        return ""
    return ""


def resolve_groq_api_key() -> Tuple[str, str]:
    """
    Resolve GROQ_API_KEY without exposing it to frontend callers.
    Priority: local SQLite config -> process env var -> backend/.env.
    """
    try:
        import database

        stored = database.fetch_system_state("ai_config")
        if isinstance(stored, dict):
            key_val = str(stored.get("groq_api_key") or "").strip()
            if key_val:
                return key_val, "LOCAL_CONFIG"
    except Exception:
        pass

    env_val = os.environ.get("GROQ_API_KEY", "").strip()
    if env_val:
        return env_val, "ENV_VAR"

    dotenv_val = _read_dotenv_var("GROQ_API_KEY")
    if dotenv_val:
        return dotenv_val, "DOTENV_FILE"

    return "", "NONE"


def redact_groq_api_key(api_key: str) -> str:
    if not api_key:
        return "Not configured"
    if len(api_key) <= 10:
        return "Configured (****)"
    return f"Configured ({api_key[:4]}...{api_key[-4:]})"


def _resolve_default_groq_model() -> str:
    env_model = (os.environ.get("TARSCARE_API_MODEL") or _read_dotenv_var("TARSCARE_API_MODEL")).strip()
    if env_model:
        return env_model
    return DEFAULT_GROQ_MODEL


def _is_comm_blackout() -> bool:
    try:
        import database

        comm_state = database.fetch_system_state("comm_state") or {}
        return bool(
            comm_state.get("offline_mode_forced")
            or str(comm_state.get("earth_comm_status", "")).upper() == "CONJUNCTION_BLACKOUT"
        )
    except Exception:
        return False


def get_ai_config() -> Dict[str, Any]:
    """Read persisted AI engine settings (llm_enabled, llm_provider, selected_model, selected_api_model) from SQLite."""
    has_groq = bool(resolve_groq_api_key()[0])
    default_api_model = _resolve_default_groq_model()
    cfg: Dict[str, Any] = {
        "llm_enabled": True,
        "llm_provider": "api" if has_groq else "local",
        "selected_model": None,
        "selected_api_model": default_api_model,
    }
    try:
        import database

        stored = database.fetch_system_state("ai_config")
        if isinstance(stored, dict):
            if "llm_enabled" in stored:
                cfg["llm_enabled"] = bool(stored["llm_enabled"])
            prov = str(stored.get("llm_provider") or "").strip().lower()
            if prov in {"local", "api"}:
                cfg["llm_provider"] = prov
            if stored.get("selected_model"):
                cfg["selected_model"] = str(stored["selected_model"])
            if stored.get("selected_api_model"):
                cfg["selected_api_model"] = str(stored["selected_api_model"])
            if stored.get("groq_api_key"):
                cfg["groq_api_key"] = str(stored["groq_api_key"])
    except Exception:
        pass
    return cfg


def set_ai_config(
    llm_enabled: Optional[bool] = None,
    llm_provider: Optional[str] = None,
    selected_model: Optional[str] = None,
    clear_selected_model: bool = False,
    selected_api_model: Optional[str] = None,
    clear_selected_api_model: bool = False,
    groq_api_key: Optional[str] = None,
    clear_groq_api_key: bool = False,
) -> Dict[str, Any]:
    """Persist AI preferences into SQLite and invalidate the Ollama tags probe cache."""
    global _OLLAMA_CACHE_TS
    cfg = get_ai_config()
    if llm_enabled is not None:
        cfg["llm_enabled"] = bool(llm_enabled)
    if llm_provider is not None:
        clean_prov = llm_provider.strip().lower()
        if clean_prov not in {"local", "api"}:
            raise ValueError("llm_provider must be 'local' or 'api'.")
        cfg["llm_provider"] = clean_prov
    if clear_selected_model:
        cfg["selected_model"] = None
    elif selected_model is not None:
        cfg["selected_model"] = selected_model.strip() or None
    if clear_selected_api_model:
        cfg["selected_api_model"] = _resolve_default_groq_model()
    elif selected_api_model is not None:
        cfg["selected_api_model"] = selected_api_model.strip() or _resolve_default_groq_model()
    if clear_groq_api_key:
        cfg.pop("groq_api_key", None)
    elif groq_api_key is not None:
        cleaned_key = groq_api_key.strip()
        if cleaned_key:
            cfg["groq_api_key"] = cleaned_key
    try:
        import database

        database.update_system_state("ai_config", cfg)
    except Exception:
        pass
    _OLLAMA_CACHE_TS = 0.0
    public_cfg = dict(cfg)
    public_cfg.pop("groq_api_key", None)
    return public_cfg


def _is_embedding_model(model_name: str, details: Optional[Dict[str, Any]] = None) -> bool:
    nl = model_name.lower()
    if any(tok in nl for tok in ("embed", "minilm", "bge-", "e5-", "snowflake-arctic-embed")):
        return True
    family = str((details or {}).get("family", "")).lower()
    return family in {"bert", "nomic-bert"}


def _sort_chat_models(models: List[str]) -> List[str]:
    def _rank(name: str) -> Tuple[int, str]:
        nl = name.lower()
        for idx, pref in enumerate(_PREFERRED_CHAT_PREFIXES):
            if nl.startswith(pref):
                return (idx, nl)
        return (len(_PREFERRED_CHAT_PREFIXES), nl)

    return sorted(models, key=_rank)


def _select_active_chat_model(chat_models: List[str], preferred: Optional[str]) -> Optional[str]:
    if not chat_models:
        return None
    if preferred:
        if preferred in chat_models:
            return preferred
        pref_base = preferred.split(":")[0].lower()
        for candidate in chat_models:
            if candidate.split(":")[0].lower() == pref_base:
                return candidate
    return chat_models[0]


def _probe_ollama_registry(force: bool = False) -> Dict[str, Any]:
    """Fast 0.5s probe against local Ollama daemon (127.0.0.1:11434/api/tags), cached 12s."""
    global _OLLAMA_CACHE_TS, _OLLAMA_PROBE_CACHE
    if os.environ.get("VERCEL"):
        return {"reachable": False, "chat_models": [], "embed_models": []}
    now = time.time()
    if not force and (now - _OLLAMA_CACHE_TS) < 12.0:
        return dict(_OLLAMA_PROBE_CACHE)
    _OLLAMA_CACHE_TS = now
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_models = data.get("models", [])
            chat_models: List[str] = []
            embed_models: List[str] = []
            for entry in raw_models:
                m_name = str(entry.get("name") or entry.get("model") or "").strip()
                if not m_name:
                    continue
                if _is_embedding_model(m_name, entry.get("details")):
                    embed_models.append(m_name)
                else:
                    chat_models.append(m_name)
            _OLLAMA_PROBE_CACHE = {
                "reachable": True,
                "chat_models": _sort_chat_models(chat_models),
                "embed_models": sorted(embed_models),
            }
            return dict(_OLLAMA_PROBE_CACHE)
    except Exception:
        _OLLAMA_PROBE_CACHE = {
            "reachable": False,
            "chat_models": [],
            "embed_models": [],
        }
        return dict(_OLLAMA_PROBE_CACHE)


def _probe_ollama() -> Optional[str]:
    """Return active Ollama chat model name if Ollama is reachable and has chat models."""
    reg = _probe_ollama_registry()
    cfg = get_ai_config()
    return _select_active_chat_model(reg["chat_models"], cfg.get("selected_model"))


def get_local_ai_status(force_probe: bool = False) -> Dict[str, Any]:
    _probe_sentence_transformer(load_if_cached=False)
    reg = _probe_ollama_registry(force=force_probe)
    cfg = get_ai_config()
    llm_enabled = bool(cfg.get("llm_enabled", True))
    llm_provider = str(cfg.get("llm_provider") or "local").lower()
    if llm_provider not in {"local", "api"}:
        llm_provider = "local"

    active_ollama_model = _select_active_chat_model(reg["chat_models"], cfg.get("selected_model"))
    embed_ready = _ST_CACHED or bool(reg["embed_models"])
    ollama_available = bool(reg["reachable"] and active_ollama_model is not None)

    groq_key, groq_key_source = resolve_groq_api_key()
    api_key_configured = bool(groq_key)
    blackout = _is_comm_blackout()
    api_model = str(cfg.get("selected_api_model") or _resolve_default_groq_model())
    api_models_list = list(GROQ_CHAT_MODEL_IDS)
    if api_model and api_model not in api_models_list:
        api_models_list.insert(0, api_model)

    api_active = bool(llm_provider == "api" and llm_enabled and api_key_configured and not blackout)
    ollama_active = bool(llm_provider == "local" and llm_enabled and ollama_available)
    llm_active = api_active or ollama_active

    if api_active and embed_ready:
        mode = "GROQ_API_PLUS_EMBEDDINGS"
        active_prov = "api_groq"
    elif api_active:
        mode = "GROQ_API_PLUS_TFIDF"
        active_prov = "api_groq"
    elif ollama_active and embed_ready:
        mode = "LOCAL_OLLAMA_PLUS_EMBEDDINGS"
        active_prov = "local_ollama"
    elif ollama_active:
        mode = "LOCAL_OLLAMA_PLUS_TFIDF"
        active_prov = "local_ollama"
    elif embed_ready:
        mode = "OFFLINE_SENTENCE_TRANSFORMERS"
        active_prov = "offline_fallback"
    else:
        mode = "DETERMINISTIC_OFFLINE_RAG"
        active_prov = "offline_fallback"

    return {
        "ollama_available": ollama_available,
        "ollama_reachable": bool(reg["reachable"]),
        "ollama_model": active_ollama_model,
        "installed_chat_models": reg["chat_models"],
        "installed_embed_models": reg["embed_models"],
        "llm_provider": llm_provider,
        "active_provider": active_prov,
        "api_provider": "groq",
        "api_available": api_key_configured,
        "api_reachable": bool(api_key_configured and not blackout),
        "api_blocked_blackout": blackout,
        "api_model": api_model,
        "available_api_models": api_models_list,
        "api_model_catalog": GROQ_CHAT_MODELS,
        "api_key_configured": api_key_configured,
        "api_key_status": redact_groq_api_key(groq_key),
        "api_key_source": groq_key_source,
        "last_api_error": _LAST_GROQ_ERROR,
        "active_model_display": api_model if api_active else (active_ollama_model if ollama_active else None),
        "llm_enabled": llm_enabled,
        "llm_active": llm_active,
        "sentence_transformers_installed": _ST_INSTALLED,
        "sentence_transformers_cached": _ST_CACHED,
        "embeddings_loaded": _ST_MODEL is not None or bool(reg["embed_models"]),
        "active_engine_mode": mode,
        "offline_guaranteed": True,
    }


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return float(dot)


def _encode_via_ollama_embed(
    texts: List[str],
    model_name: str,
    keep_alive: str = "15m",
    timeout: float = 35.0,
) -> Optional[List[List[float]]]:
    try:
        payload = json.dumps({"model": model_name, "input": texts, "keep_alive": keep_alive}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            embs = body.get("embeddings")
            if isinstance(embs, list) and len(embs) == len(texts):
                normalized: List[List[float]] = []
                for vec in embs:
                    norm = math.sqrt(sum(float(x) * float(x) for x in vec)) or 1.0
                    normalized.append([float(x) / norm for x in vec])
                return normalized
    except Exception:
        return None
    return None


def get_dense_scores(
    question: str,
    chunk_pairs: List[Tuple[str, str]],
    wait_for_embeddings: bool = True,
) -> Optional[Dict[str, float]]:
    """
    Compute full-corpus dense cosine similarity across all candidate chunks with in-memory chunk
    vector caching. Uses fast local Ollama /api/embed if an embedding model is installed and
    PyTorch ST isn't already resident, or locally cached Sentence-Transformers (all-MiniLM-L6-v2).
    """
    if not chunk_pairs:
        return None

    # 1. Instant native Ollama /api/embed path when an Ollama embedding model is pulled (avoids heavy torch cold import)
    reg = _probe_ollama_registry()
    if reg["embed_models"] and _ST_MODEL is None:
        embed_model = reg["embed_models"][0]
        prefix = f"ollama:{embed_model}::"
        with _CHUNK_VEC_LOCK:
            missing_idx = [
                i
                for i, (cid, txt) in enumerate(chunk_pairs)
                if f"{prefix}{cid}" not in _CHUNK_VEC_CACHE or _CHUNK_VEC_CACHE[f"{prefix}{cid}"][0] != txt
            ]
            if missing_idx:
                missing_texts = [chunk_pairs[i][1] for i in missing_idx]
                new_vecs = _encode_via_ollama_embed(missing_texts, embed_model)
                if new_vecs:
                    for offset, vec in enumerate(new_vecs):
                        cid, txt = chunk_pairs[missing_idx[offset]]
                        _CHUNK_VEC_CACHE[f"{prefix}{cid}"] = (txt, vec)
        if all(f"{prefix}{cid}" in _CHUNK_VEC_CACHE for cid, _ in chunk_pairs):
            q_vecs = _encode_via_ollama_embed([question], embed_model)
            if q_vecs:
                q_vec = q_vecs[0]
                return {
                    cid: _cosine_similarity(q_vec, _CHUNK_VEC_CACHE[f"{prefix}{cid}"][1])
                    for cid, _ in chunk_pairs
                }

    # 2. Offline HuggingFace all-MiniLM-L6-v2 path
    _probe_sentence_transformer(
        load_if_cached=True,
        wait_seconds=2.5 if wait_for_embeddings else 0.0,
    )
    if _ST_MODEL is not None:
        try:
            prefix = "st:minilm::"
            with _CHUNK_VEC_LOCK:
                missing_idx = [
                    i
                    for i, (cid, txt) in enumerate(chunk_pairs)
                    if f"{prefix}{cid}" not in _CHUNK_VEC_CACHE or _CHUNK_VEC_CACHE[f"{prefix}{cid}"][0] != txt
                ]
                if missing_idx:
                    missing_texts = [chunk_pairs[i][1] for i in missing_idx]
                    new_vecs = _ST_MODEL.encode(missing_texts, normalize_embeddings=True)
                    for offset, vec in enumerate(new_vecs):
                        cid, txt = chunk_pairs[missing_idx[offset]]
                        _CHUNK_VEC_CACHE[f"{prefix}{cid}"] = (txt, [float(v) for v in vec])
            q_vec = [float(v) for v in _ST_MODEL.encode([question], normalize_embeddings=True)[0]]
            return {
                cid: _cosine_similarity(q_vec, _CHUNK_VEC_CACHE[f"{prefix}{cid}"][1])
                for cid, _ in chunk_pairs
            }
        except Exception:
            pass
    return None


def rerank_with_embeddings_if_cached(
    query: str,
    candidate_texts: List[str],
    base_scores: List[float],
) -> List[float]:
    pairs = [(f"cand-{i}", txt) for i, txt in enumerate(candidate_texts)]
    dense_map = get_dense_scores(query, pairs, wait_for_embeddings=True)
    if not dense_map:
        return base_scores
    combined: List[float] = []
    for idx, base in enumerate(base_scores):
        cos = max(0.0, dense_map.get(f"cand-{idx}", 0.0))
        combined.append(round(0.45 * base + 0.55 * cos, 4))
    return combined


def _fmt_val(val: Any, suffix: str = "") -> str:
    if val is None or val == "":
        return "not set"
    return f"{val}{suffix}"


def _format_telemetry_context(astronaut_context: Optional[Dict[str, Any]]) -> str:
    if not astronaut_context:
        return ""
    name = astronaut_context.get("astronaut_name", "SuChai")
    sol = astronaut_context.get("mission_day")
    phase = astronaut_context.get("mission_phase")
    grav = astronaut_context.get("gravity_g")
    status = astronaut_context.get("overall_status")
    hazard_statuses = astronaut_context.get("hazard_statuses") or {}
    provenance = astronaut_context.get("provenance", "SYNTHETIC_DEMO")
    tel = astronaut_context.get("latest_telemetry") or {}
    base = astronaut_context.get("baseline") or {}
    alerts = astronaut_context.get("active_alerts") or []

    header_parts = [f"Astronaut: {name}"]
    if sol is not None:
        header_parts.append(f"Sol {sol}")
    if phase:
        header_parts.append(f"Phase {phase}")
    if grav is not None:
        header_parts.append(f"Gravity {grav}g")
    if status:
        header_parts.append(f"Overall Status: {status}")
    header_parts.append(f"Data Provenance: {provenance}")

    lines = [" | ".join(header_parts)]
    if hazard_statuses:
        hz_txt = ", ".join(f"{k}={v}" for k, v in hazard_statuses.items())
        lines.append(f"- Active Hazard Statuses: {hz_txt}")
    if tel:
        hr = tel.get("heart_rate_bpm")
        hr_base = base.get("baseline_hr_bpm") if base.get("baseline_hr_bpm") is not None else base.get("baseline_heart_rate_bpm")
        sbp = tel.get("systolic_bp_mmhg")
        dbp = tel.get("diastolic_bp_mmhg")
        sbp_base = base.get("baseline_systolic_mmhg") if base.get("baseline_systolic_mmhg") is not None else base.get("baseline_systolic_bp_mmhg")
        dbp_base = base.get("baseline_diastolic_mmhg") if base.get("baseline_diastolic_mmhg") is not None else base.get("baseline_diastolic_bp_mmhg")
        spo2 = tel.get("spo2_pct")
        spo2_base = base.get("baseline_spo2_pct")
        resp_rate = tel.get("respiratory_rate_bpm")
        temp = tel.get("body_temp_c")
        sleep_h = tel.get("sleep_duration_hrs")
        sleep_base = base.get("baseline_sleep_hrs")
        mood = tel.get("mood_score")
        stress = tel.get("stress_level")
        fatigue = tel.get("fatigue_level")
        co2_mm = tel.get("co2_mmhg")
        co2_ppm = tel.get("co2_ppm")
        cabin_temp = tel.get("cabin_temp_c")
        o2_pct = tel.get("oxygen_pct")
        humid = tel.get("humidity_pct")
        abs_mgy = tel.get("absorbed_dose_mgy")
        abs_rate = tel.get("absorbed_dose_rate_mgy_hr")
        eq_rate = tel.get("equivalent_dose_rate_msv_day")
        cum_msv = tel.get("cumulative_effective_dose_msv")
        rad_evt = tel.get("radiation_event_type")
        rad_src = tel.get("radiation_source")
        resp_sym = tel.get("respiratory_symptoms") or []
        inf_sym = tel.get("infection_symptoms") or []
        rep_sym = tel.get("reported_symptoms") or []
        dizz = tel.get("dizziness_severity")
        presyncope = tel.get("faintness_presyncope")
        sans = tel.get("visual_disturbance_sans")
        chest = bool(tel.get("chest_discomfort", False))
        palp = bool(tel.get("palpitations", False))
        sob = bool(tel.get("shortness_of_breath", False))

        bp_base_str = f"{sbp_base}/{dbp_base} mmHg" if (sbp_base is not None and dbp_base is not None) else "not configured"
        lines.append(
            f"- Cardiovascular & Vitals: HR {_fmt_val(hr, ' bpm')} (personal baseline {_fmt_val(hr_base, ' bpm')}), "
            f"BP {sbp}/{dbp} mmHg (personal baseline {bp_base_str}), "
            f"SpO2 {_fmt_val(spo2, '%')} (baseline {_fmt_val(spo2_base, '%')}), Respiratory Rate {_fmt_val(resp_rate, ' breaths/min')}, "
            f"Temp {_fmt_val(temp, ' C')}, Dizziness={dizz}/3, Presyncope={presyncope}, SANS visual={sans}, "
            f"Red-flag symptoms: chest_discomfort={chest}, palpitations={palp}, shortness_of_breath={sob}, other={rep_sym or 'None'}."
        )
        lines.append(
            f"- Behavioral & Sleep: Sleep {_fmt_val(sleep_h, ' hrs')} (baseline {_fmt_val(sleep_base, ' hrs')}), "
            f"Mood {_fmt_val(mood, '/10')}, Stress {_fmt_val(stress, '/10')}, Fatigue {_fmt_val(fatigue, '/10')}, "
            f"Exercise Performance {_fmt_val(tel.get('exercise_performance_pct'), '%')}."
        )
        lines.append(
            f"- Radiation Dosimetry (keep Gy vs Sv strictly distinct): "
            f"Absorbed Dose {_fmt_val(abs_mgy, ' mGy')} ({_fmt_val(abs_rate, ' mGy/hr')}), "
            f"Equivalent Dose Rate {_fmt_val(eq_rate, ' mSv/day')}, Cumulative Effective Dose {_fmt_val(cum_msv, ' mSv')}, "
            f"Event={rad_evt}, Source={rad_src}."
        )
        lines.append(
            f"- Habitat ECLSS & Symptoms: CO2 {_fmt_val(co2_mm, ' mmHg')} ({_fmt_val(co2_ppm, ' ppm')}), "
            f"O2 {_fmt_val(o2_pct, '%')}, Cabin Temp {_fmt_val(cabin_temp, ' C')}, Humidity {_fmt_val(humid, '%')}, "
            f"Respiratory symptoms={resp_sym or 'None'}, Infection-like symptoms={inf_sym or 'None'}."
        )
    if alerts:
        alert_texts = [
            f"{a.get('severity', '')} [{a.get('hazard', '')}]: {a.get('message', a)}"
            if isinstance(a, dict) else str(a)
            for a in alerts[:5]
        ]
        lines.append("- Active Telemetry Alerts: " + "; ".join(alert_texts))
    return "\n".join(lines)


def _verify_and_finalize_llm_answer(
    raw_text: str,
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Post-generation safety & provenance gate:
    1) Reject empty/too-short outputs or leaked None/NaN values.
    2) Reject unapproved drug prescription / specific dosage leakage.
    3) Reject false reassurance when telemetry status is WARNING/CRITICAL.
    4) Reject false health guarantees or ARMAS-is-Mars errors.
    5) Verify cited [DOC-ID] tags match retrieved sources & trim incomplete trailing cuts.
    """
    text = (raw_text or "").strip()
    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    # Normalize typographic dashes inside bracketed citation IDs (e.g. U+2011 non-breaking hyphen)
    text = re.sub(
        r"\[([A-Za-z0-9\u2010-\u2013_-]+)\]",
        lambda m: "[" + re.sub(r"[\u2010-\u2013]", "-", m.group(1)) + "]",
        text,
    )
    if len(text) < 25:
        return None
    if _PRESCRIPTION_LEAK_RE.search(text):
        return None
    if re.search(r"\b(?:None|null|NaN)\b(?:\s*(?:bpm|mmHg|hrs|%|mSv|mGy)|[,.)])", text, re.IGNORECASE) or "baseline None" in text:
        return None

    ctx = astronaut_context or {}
    overall = str(ctx.get("overall_status", "")).upper()
    hazards = ctx.get("hazard_statuses") or {}
    has_elevated = overall in ("WARNING", "CRITICAL") or any(
        str(v).upper() in ("WARNING", "CRITICAL") for v in hazards.values()
    )

    # Reject false "everything is normal / within normal ranges" claims during active alerts
    if has_elevated:
        false_norm_re = re.compile(
            r"(?i)\b(?:all\s+(?:vital\s+signs|measurements|readings|metrics)\s+are\s+normal|"
            r"within\s+normal\s+(?:clinical\s+|reference\s+)?(?:ranges|limits)\b|"
            r"overall\s+(?:health\s+)?status\s+is\s+normal|"
            r"no\s+(?:abnormalities|alerts|hazards)\s+(?:detected|present|active))\b"
        )
        m_norm = false_norm_re.search(text)
        if m_norm:
            prefix = text[max(0, m_norm.start() - 20):m_norm.start()].lower()
            if not any(neg in prefix for neg in ("not ", "no longer ", "outside ", "rather than ")):
                return None

    ql = question.lower()
    m_guar = re.search(
        r"(?i)\b(?:can\s+guarantee|guarantees?\s+(?:health|safety|that\s+an?\s+astronaut)|guaranteed\s+(?:safe|healthy?)|100%\s+safe)\b",
        text,
    )
    if m_guar:
        prefix = text[max(0, m_guar.start() - 25):m_guar.start()].lower()
        if not any(neg in prefix for neg in ("not ", "no ", "never ", "cannot ", "unable to ")):
            return None

    if "armas" in ql or "armas" in text.lower():
        m_armas = re.search(
            r"(?i)armas\b.{0,80}\b(?:direct(?:ly)?\s+(?:represent|measur|reflect|record)\w*|represent\w*|measur\w*|telemetry)\b.{0,45}\bmars\b",
            text,
        )
        if m_armas and not any(neg in m_armas.group(0).lower() for neg in ("not ", "never ", "cannot ", "rather than ", "instead of ")):
            return None

    # Validate bracketed [DOC-ID] tags against retrieved citations so fabricated citations cannot slip through
    valid_doc_ids = {str(c.get("doc_id")) for c in citations if c.get("doc_id")}
    found_tags = re.findall(r"\[([A-Z]{2,}(?:-[A-Z0-9]+)+)\]", text)
    for tag in found_tags:
        if tag not in valid_doc_ids:
            text = text.replace(f"[{tag}]", "").replace("  ", " ").strip()

    # Clean mid-sentence truncation cleanly, or reject dangling incomplete fragments
    if text and text[-1] not in ".!?)]\"":
        last_end = max(text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind("]"))
        tail_word = (text.rstrip(",;:- ").split()[-1].lower() if text.strip() else "")
        dangling = {"because", "and", "or", "since", "while", "when", "with", "for", "of", "the", "a", "an", "that", "which", "to", "in", "on"}
        if last_end > max(40, int(len(text) * 0.55)):
            text = text[: last_end + 1].strip()
        elif last_end == -1 and tail_word in dangling:
            return None
        else:
            text = text.rstrip(",;:- ") + "."

    cited_ids = [c["doc_id"] for c in citations if c.get("doc_id")]
    if cited_ids and not any(doc_id in text for doc_id in cited_ids):
        refs = ", ".join(f"[{did}]" for did in cited_ids[:3])
        text = f"{text}\n\nGrounded References: {refs}"

    if ("gy" in ql or "gray" in ql or "sv" in ql or "sievert" in ql) and ("Gy" not in text or "Sv" not in text):
        text += (
            "\n\nUnit Integrity Note: Absorbed dose (Gy / mGy) measures physical energy deposited per unit mass, "
            "whereas equivalent/effective dose (Sv / mSv) weights biological damage using radiation quality factors."
        )
    return text


def _build_rag_messages(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    context_lines = "\n\n".join(
        f"[{c['doc_id']}] ({c['agency']}, {c['year']}) {c['title']}:\n{c['excerpt']}"
        for c in citations[:4]
    )
    telemetry_block = _format_telemetry_context(astronaut_context)
    system_prompt = (
        "You are TARS Care, an autonomous deep-space astronaut health companion engineered for NASA Artemis/Mars operations.\n"
        "Strict rules:\n"
        "1. Ground every medical/spaceflight explanation ONLY in the provided [DOC-ID] NASA/CSA/TARS Care reference passages and the live telemetry shown below.\n"
        "2. Cite supporting sources inline using exact bracketed IDs such as [NASA-HRP-RAD-01] or [CSA-CARDIO-CCISS-01]. NEVER invent a citation ID.\n"
        "3. Compare readings against the astronaut's personal baseline shown in telemetry when available (never print None or claim WARNING/CRITICAL vitals are normal). Note that ordinary Earth-based clinical reference ranges do not automatically represent safe operating limits in microgravity or partial gravity.\n"
        "4. Distinguish physical absorbed dose (Gy / mGy) from biological equivalent/effective dose (Sv / mSv); never invent NASA exposure limits.\n"
        "5. Never treat ARMAS Earth atmospheric aircraft radiation data as direct Mars surface telemetry, and explicitly identify synthetic demo vs. user-entered telemetry.\n"
        "6. Never diagnose psychiatric disorders or clinical infections from sensors, NEVER guarantee health outcomes, and NEVER prescribe medications or drug dosages.\n"
        "7. Keep answers concise, clear plain prose or clean bullet points (no markdown tables), complete every sentence, clearly separate scientific evidence from operational procedure, and keep guidance practical for autonomous crew action."
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    history = (astronaut_context or {}).get("history") or []
    for turn in history[-4:]:
        role = str(turn.get("role", "")).lower()
        content = str(turn.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:600]})

    user_content = (
        f"LIVE ASTRONAUT TELEMETRY:\n{telemetry_block or 'No live telemetry attached.'}\n\n"
        f"RETRIEVED REFERENCE PASSAGES:\n{context_lines}\n\n"
        f"ASTRONAUT QUESTION:\n{question}"
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def call_groq_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.15,
    max_tokens: int = 1200,
    timeout: float = 25.0,
) -> Optional[Dict[str, Any]]:
    """Call Groq OpenAI-compatible chat completions API using server-side GROQ_API_KEY."""
    global _LAST_GROQ_ERROR
    if _is_comm_blackout():
        _LAST_GROQ_ERROR = "Blocked during OFFLINE Solar Conjunction Blackout."
        return None
    api_key, _ = resolve_groq_api_key()
    if not api_key:
        _LAST_GROQ_ERROR = "GROQ_API_KEY is not configured."
        return None

    cfg = get_ai_config()
    target_model = (model or cfg.get("selected_api_model") or _resolve_default_groq_model()).strip()
    body_obj: Dict[str, Any] = {
        "model": target_model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }
    if "gpt-oss" in target_model.lower():
        body_obj["reasoning_effort"] = "low"

    payload = json.dumps(body_obj).encode("utf-8")
    started = time.perf_counter()
    try:
        req = urllib.request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "TARSCareAI/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            raw_content = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
            cleaned = re.sub(r"(?is)<think>.*?</think>", "", str(raw_content)).strip()
            if not cleaned:
                _LAST_GROQ_ERROR = f"Empty completion returned by {target_model}."
                return None
            _LAST_GROQ_ERROR = None
            latency_ms = int(round((time.perf_counter() - started) * 1000))
            return {
                "content": cleaned,
                "model": str(data.get("model") or target_model),
                "latency_ms": latency_ms,
                "provider": "api",
            }
    except urllib.error.HTTPError as exc:
        err_msg = f"HTTP {exc.code}"
        try:
            err_body = exc.read().decode("utf-8", errors="ignore")
            parsed = json.loads(err_body)
            detail = (parsed.get("error") or {}).get("message")
            if detail:
                err_msg = f"HTTP {exc.code}: {str(detail)[:180]}"
        except Exception:
            pass
        _LAST_GROQ_ERROR = err_msg
        return None
    except Exception as exc:
        _LAST_GROQ_ERROR = str(exc)[:180]
        return None


def synthesize_with_ollama(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate grounded synthesis via local Ollama /api/chat with separated system/user roles,
    conversation history window, persistent keep_alive, and post-LLM safety verification.
    """
    cfg = get_ai_config()
    if not cfg.get("llm_enabled", True):
        return None
    model_name = _probe_ollama()
    if not model_name or not citations:
        return None

    messages = _build_rag_messages(question, citations, astronaut_context)
    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": 0.12, "num_predict": 800},
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
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw_text = ((body.get("message") or {}).get("content") or "").strip()
            verified = _verify_and_finalize_llm_answer(raw_text, question, citations, astronaut_context)
            if not verified:
                return None
            latency_ms = int(round((time.perf_counter() - started) * 1000))
            return {
                "answer": verified,
                "model": model_name,
                "latency_ms": latency_ms,
                "provider": "local",
            }
    except Exception:
        return None


def synthesize_with_groq(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate grounded RAG synthesis via Groq API with full post-generation safety gate."""
    cfg = get_ai_config()
    if not cfg.get("llm_enabled", True) or not citations:
        return None
    messages = _build_rag_messages(question, citations, astronaut_context)
    api_res = call_groq_chat(messages, temperature=0.15, max_tokens=1200, timeout=25.0)
    if not api_res:
        return None
    verified = _verify_and_finalize_llm_answer(api_res["content"], question, citations, astronaut_context)
    if not verified:
        return None
    return {
        "answer": verified,
        "model": api_res["model"],
        "latency_ms": api_res["latency_ms"],
        "provider": "api",
    }


def synthesize_with_llm(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Dispatch RAG synthesis cleanly to configured provider ('api' Groq or 'local' Ollama)."""
    cfg = get_ai_config()
    if not cfg.get("llm_enabled", True) or not citations:
        return None
    provider = str(cfg.get("llm_provider") or "local").lower()
    if provider == "api":
        return synthesize_with_groq(question, citations, astronaut_context)
    return synthesize_with_ollama(question, citations, astronaut_context)


def synthesize_with_ollama_if_available(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    res = synthesize_with_ollama(question, citations, astronaut_context)
    return res["answer"] if res else None


def warmup_api_model(model_name: Optional[str] = None) -> Dict[str, Any]:
    """Run a lightweight connectivity & latency probe against Groq API."""
    cfg = get_ai_config()
    target = (model_name or cfg.get("selected_api_model") or _resolve_default_groq_model()).strip()
    if _is_comm_blackout():
        return {
            "ok": False,
            "model": target,
            "latency_ms": 0,
            "message": "External Groq API paused while Link Status is OFFLINE (Solar Conjunction Blackout). Switch Link Status to Delayed or Connected, or use Local LLM.",
            "status": get_local_ai_status(force_probe=True),
        }
    api_key, _ = resolve_groq_api_key()
    if not api_key:
        return {
            "ok": False,
            "model": target,
            "latency_ms": 0,
            "message": "GROQ_API_KEY is not configured in backend/.env or local config.",
            "status": get_local_ai_status(force_probe=True),
        }

    res = call_groq_chat(
        messages=[{"role": "user", "content": "Reply with OK."}],
        model=target,
        temperature=0.0,
        max_tokens=32,
        timeout=15.0,
    )
    if res:
        return {
            "ok": True,
            "model": res["model"],
            "latency_ms": res["latency_ms"],
            "message": f"Groq API {res['model']} verified ready ({res['latency_ms']} ms).",
            "status": get_local_ai_status(force_probe=True),
        }
    return {
        "ok": False,
        "model": target,
        "latency_ms": 0,
        "message": f"Groq API check failed for {target}: {_LAST_GROQ_ERROR or 'Connection failed'}",
        "status": get_local_ai_status(force_probe=True),
    }


def warmup_ai_model(
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Warm up local Ollama or verify external Groq API depending on active/requested provider."""
    cfg = get_ai_config()
    eff_provider = (provider or cfg.get("llm_provider") or "local").strip().lower()
    if eff_provider == "api":
        return warmup_api_model(model_name=model_name)
    return warmup_ollama_model(model_name=model_name)


def warmup_ollama_model(model_name: Optional[str] = None) -> Dict[str, Any]:
    """Preload local embeddings and pin the selected Ollama chat model in VRAM/RAM."""
    reg = _probe_ollama_registry(force=True)
    cfg = get_ai_config()
    target = _select_active_chat_model(reg["chat_models"], model_name or cfg.get("selected_model"))
    if not reg["reachable"] or not target:
        _probe_sentence_transformer(load_if_cached=True, wait_seconds=0.0)
        return {
            "ok": False,
            "model": target,
            "latency_ms": 0,
            "message": "Ollama daemon is not running or no local chat model is pulled.",
            "status": get_local_ai_status(force_probe=True),
        }

    started = time.perf_counter()
    if reg["embed_models"] and _ST_MODEL is None:
        _encode_via_ollama_embed(
            ["astronaut spaceflight health warmup"],
            reg["embed_models"][0],
            keep_alive="15m",
            timeout=90.0,
        )
    else:
        _probe_sentence_transformer(load_if_cached=True, wait_seconds=0.0)

    try:
        payload = json.dumps(
            {
                "model": target,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "stream": False,
                "keep_alive": "15m",
                "options": {"num_predict": 2, "temperature": 0.0},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            _ = json.loads(resp.read().decode("utf-8"))
        latency_ms = int(round((time.perf_counter() - started) * 1000))
        return {
            "ok": True,
            "model": target,
            "latency_ms": latency_ms,
            "message": f"Loaded {target} cleanly ({latency_ms} ms) with 15m keep-alive.",
            "status": get_local_ai_status(force_probe=True),
        }
    except Exception as exc:
        return {
            "ok": False,
            "model": target,
            "latency_ms": int(round((time.perf_counter() - started) * 1000)),
            "message": f"Warmup failed for {target}: {exc}",
            "status": get_local_ai_status(force_probe=True),
        }
