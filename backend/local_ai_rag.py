"""
Local AI & Expanded NASA/CSA Scientific Corpus Helpers for TARSCARE AI.
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
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

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
        "doc_id": "TARSCARE-SPEC-01",
        "title": "TARSCARE Operational Safety Rules: Insufficient Evidence, Conflict Handling & Scope",
        "agency": "TARSCARE System Spec",
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
                "TARSCARE explicitly reports insufficient evidence, refuses to guess or invent scientific citations/limits, and recommends consulting "
                "the onboard Crew Medical Officer (CMO) checklist or queuing a Store-and-Forward Flight Surgeon packet."
            ),
            (
                "Contradictory or Conflicting Scientific Sources Protocol",
                "When two retrieved scientific documents contradict each other or represent incompatible gravity/radiation regimes (e.g., Earth-altitude "
                "ARMAS vs. deep-space GCR/SPE, or 0g microgravity vs. 0.38g Mars vs. 1g Earth clinical norms), TARSCARE does NOT suppress either document "
                "or guess a single winner autonomously. Both citations are presented side-by-side with an explicit Conflict Notice, the system adopts "
                "the more conservative safety precaution onboard, and escalates final reconciliation to the Crew Medical Officer and Flight Surgeons."
            ),
            (
                "Non-Guarantee & Non-Diagnostic Boundary",
                "TARSCARE is a prototype autonomous health-monitoring and decision-support tool, not a certified clinical device. Monitoring personal "
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


def get_ai_config() -> Dict[str, Any]:
    """Read persisted AI engine settings (llm_enabled, selected_model) from SQLite system_state."""
    cfg: Dict[str, Any] = {"llm_enabled": True, "selected_model": None}
    try:
        import database

        stored = database.fetch_system_state("ai_config")
        if isinstance(stored, dict):
            if "llm_enabled" in stored:
                cfg["llm_enabled"] = bool(stored["llm_enabled"])
            if stored.get("selected_model"):
                cfg["selected_model"] = str(stored["selected_model"])
    except Exception:
        pass
    return cfg


def set_ai_config(
    llm_enabled: Optional[bool] = None,
    selected_model: Optional[str] = None,
    clear_selected_model: bool = False,
) -> Dict[str, Any]:
    """Persist AI preferences into SQLite and invalidate the Ollama tags probe cache."""
    global _OLLAMA_CACHE_TS
    cfg = get_ai_config()
    if llm_enabled is not None:
        cfg["llm_enabled"] = bool(llm_enabled)
    if clear_selected_model:
        cfg["selected_model"] = None
    elif selected_model is not None:
        cfg["selected_model"] = selected_model.strip() or None
    try:
        import database

        database.update_system_state("ai_config", cfg)
    except Exception:
        pass
    _OLLAMA_CACHE_TS = 0.0
    return cfg


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
    active_model = _select_active_chat_model(reg["chat_models"], cfg.get("selected_model"))
    embed_ready = _ST_CACHED or bool(reg["embed_models"])
    ollama_active = bool(reg["reachable"] and active_model and llm_enabled)

    if ollama_active and embed_ready:
        mode = "LOCAL_OLLAMA_PLUS_EMBEDDINGS"
    elif ollama_active:
        mode = "LOCAL_OLLAMA_PLUS_TFIDF"
    elif embed_ready:
        mode = "OFFLINE_SENTENCE_TRANSFORMERS"
    else:
        mode = "DETERMINISTIC_OFFLINE_RAG"

    return {
        "ollama_available": bool(reg["reachable"] and active_model is not None),
        "ollama_reachable": bool(reg["reachable"]),
        "ollama_model": active_model,
        "installed_chat_models": reg["chat_models"],
        "installed_embed_models": reg["embed_models"],
        "llm_enabled": llm_enabled,
        "llm_active": ollama_active,
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

    context_lines = "\n\n".join(
        f"[{c['doc_id']}] ({c['agency']}, {c['year']}) {c['title']}:\n{c['excerpt']}"
        for c in citations[:4]
    )
    telemetry_block = _format_telemetry_context(astronaut_context)
    system_prompt = (
        "You are TARSCARE, an autonomous deep-space astronaut health companion engineered for NASA Artemis/Mars operations.\n"
        "Strict rules:\n"
        "1. Ground every medical/spaceflight explanation ONLY in the provided [DOC-ID] NASA/CSA/TARSCARE reference passages and the live telemetry shown below.\n"
        "2. Cite supporting sources inline using exact bracketed IDs such as [NASA-HRP-RAD-01] or [CSA-CARDIO-CCISS-01]. NEVER invent a citation ID.\n"
        "3. Compare readings against the astronaut's personal baseline shown in telemetry when available (never print None or claim WARNING/CRITICAL vitals are normal). Note that ordinary Earth-based clinical reference ranges do not automatically represent safe operating limits in microgravity or partial gravity.\n"
        "4. Distinguish physical absorbed dose (Gy / mGy) from biological equivalent/effective dose (Sv / mSv); never invent NASA exposure limits.\n"
        "5. Never treat ARMAS Earth atmospheric aircraft radiation data as direct Mars surface telemetry, and explicitly identify synthetic demo vs. user-entered telemetry.\n"
        "6. Never diagnose psychiatric disorders or clinical infections from sensors, NEVER guarantee health outcomes, and NEVER prescribe medications or drug dosages.\n"
        "7. Keep answers concise, complete (finish every sentence), clearly separated between scientific evidence and operational procedure, and practical for autonomous crew action."
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
            }
    except Exception:
        return None


def synthesize_with_ollama_if_available(
    question: str,
    citations: List[Dict[str, Any]],
    astronaut_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    res = synthesize_with_ollama(question, citations, astronaut_context)
    return res["answer"] if res else None


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
