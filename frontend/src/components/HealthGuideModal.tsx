import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Compass,
  Eye,
  HeartPulse,
  HelpCircle,
  Radiation,
  Radio,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Stethoscope,
  Users,
  Wind,
  X,
} from 'lucide-react';

export type GuideSection = 'walkthrough' | 'measure' | 'indicators' | 'risks';

export interface GuideModalProps {
  initialSection?: GuideSection;
  initialStepId?: string;
  onClose: () => void;
  onNavigateTab: (tab: string) => void;
  onOpenBaseline?: () => void;
  onOpenSansModal?: () => void;
}

interface WalkthroughStep {
  id: string;
  tabTarget?: string;
  actionType?: 'baseline' | 'sans' | 'tab';
  actionLabel: string;
  title: string;
  whatItDoes: string;
  steps: string[];
  beginnerTip: string;
}

const WALKTHROUGH_STEPS: WalkthroughStep[] = [
  {
    id: 'overview',
    tabTarget: 'overview',
    actionType: 'tab',
    actionLabel: 'Open Mission Overview',
    title: 'Mission Overview & Daily Health Glance',
    whatItDoes:
      'Summarizes your current condition in three plain questions: "How am I doing?", "What has changed?", and "Should I take any action?" without forcing you to read raw numbers first.',
    steps: [
      'Check the Mission Sol card at the top left to see your overall health color and EVA (spacewalk) readiness.',
      'Click any organ or numbered marker on the Interactive Human Body map to inspect specific readings for that region.',
      'Scroll to Recent Trends to spot gradual drifts in heart rate, sleep, radiation, or cabin air over multiple Sols.',
      'Click Start Assessment whenever you are ready to log fresh measurements or symptoms.',
    ],
    beginnerTip:
      'Green (Normal) means your values stay close to your own baseline. Amber (Warning) asks you to re-check and adjust daily habits; Red (Critical) activates priority medical steps.',
  },
  {
    id: 'assessment',
    tabTarget: 'assessment',
    actionType: 'tab',
    actionLabel: 'Open Health Assessment',
    title: 'Health Assessment — Measuring & Logging Vitals',
    whatItDoes:
      'Lets you record new measurements in three flexible ways so you never have to guess where to start: connect a simulated/streamed device, run a guided exam, or type values manually.',
    steps: [
      'Before measuring: sit calmly for 5 minutes, keep hands warm for finger sensors, and avoid caffeine right before checking vitals.',
      'Pick Method A to pull readings from a device (such as Bio-Monitor or Blood Pressure Cuff), Method B for guided exams, or Method C for Manual Entry / CSV import.',
      'Fill in what you measured (any optional field you skip stays safely marked rather than inventing numbers) and tick any symptoms you feel.',
      'Submit the evaluation to immediately compare today’s values against your personal baseline.',
    ],
    beginnerTip:
      'If you ever get a headache or dry cough inside the habitat, log BOTH your physical symptoms and your cabin CO₂ / humidity readings together so TARS Care checks environmental causes too.',
  },
  {
    id: 'baseline',
    actionType: 'baseline',
    actionLabel: 'Open Personal Baseline',
    title: 'Personal Baseline — Why "Normal" Is Personal',
    whatItDoes:
      'Stores your own pre-flight and healthy resting targets (resting heart rate, blood pressure, SpO₂, sleep hours, and radiation/CO₂ thresholds) so alerts reflect changes in YOU rather than generic Earth averages.',
    steps: [
      'Click the Sol / Baseline button in the top bar at any time to review your personal resting targets.',
      'Remember that spaceflight (0g or 0.38g Mars gravity) shifts body fluids upward and alters resting heart rate compared to Earth (1g).',
      'Update baseline numbers only with mission-approved calibration values; every change is logged in your local audit history.',
    ],
    beginnerTip:
      'Comparing against your own baseline catches subtle changes early—for instance, a resting heart rate of 78 BPM can be normal for one crewmate yet a clear jump for someone whose baseline is 54 BPM.',
  },
  {
    id: 'hazards',
    tabTarget: 'hazards',
    actionType: 'tab',
    actionLabel: 'Open Spaceflight Hazards',
    title: '5 Spaceflight Hazards & Space Weather',
    whatItDoes:
      'Breaks down NASA’s five deep-space health risks into four consistent questions for each hazard: what we monitor, what changed, what might happen, and what action you can take.',
    steps: [
      'Select any of the five hazard tabs: Space Radiation, Isolation & Confinement, Distance from Earth, Gravity Fields, or Hostile Environments.',
      'Keep Gy/mGy (physical radiation energy deposited) distinct from Sv/mSv (weighted biological risk) when checking dosimetry charts.',
      'Review cached NASA DONKI space weather alerts before scheduling an outdoor EVA so solar storms are spotted early.',
    ],
    beginnerTip:
      'Use the Gravity Explorer toggle (1g vs. 0g vs. 0.38g) inside Gravity Fields to see how fluid shift, bone load, and dizziness risks change between Earth, transit, and Mars.',
  },
  {
    id: 'devices',
    tabTarget: 'sans',
    actionType: 'sans',
    actionLabel: 'Try 1-Minute SANS Eye Check',
    title: 'Medical Devices, SANS Eye Check & Biosamples',
    whatItDoes:
      'Catalogs onboard instruments and guides you through non-wearable tests—like the SANS visual Amsler grid check, eye-pressure tonometry, ultrasound, and saliva paper sample kits.',
    steps: [
      'Open Medical Devices when using specialized kits that do not stream automatically over Bluetooth.',
      'Select a device to inspect whether it supports live connection, file import, guided manual examination, or demo simulation.',
      'For Vision Check (SANS): wear your glasses if prescribed, cover one eye at a time, stare at the center dot, and click any grid squares that appear wavy or missing.',
    ],
    beginnerTip:
      'Microgravity fluid shifts can flatten the back of the eye over weeks in space (SANS). A quick 1-minute Amsler grid check catches subtle vision shifts early without specialized imaging.',
  },
  {
    id: 'companion',
    tabTarget: 'food',
    actionType: 'tab',
    actionLabel: 'Open Food & Supplies',
    title: 'Food, Hydration, Journal & Personal Companion',
    whatItDoes:
      'Tracks daily rations, potable water, expiry safety, private mood check-ins, and confidential journaling—connecting hydration and nutrition directly to your physical recovery.',
    steps: [
      'In Food & Supplies, log meals and water pouches; watch expiry warnings so fresh items are eaten first.',
      'In Personal Companion & My Journal, record private thoughts or mood reflections stored locally in SQLite.',
      'Control AI Privacy Consent settings explicitly so private journal entries are never shared unless you opt in.',
    ],
    beginnerTip:
      'If an Exercise Hold is active due to dizziness, elevated heart rate, or low SpO₂, Personal Companion automatically switches to restful coping suggestions instead of physical workouts.',
  },
  {
    id: 'ai_comm',
    tabTarget: 'assistant',
    actionType: 'tab',
    actionLabel: 'Open AI Health Assistant',
    title: 'AI Health Assistant, Distance Delay & Local vs. API LLM',
    whatItDoes:
      'Answers spaceflight health questions backed by indexed NASA & CSA scientific documents, and queues non-urgent Earth messages cleanly during 4–24 minute Mars communication delays or blackouts.',
    steps: [
      'Use the Local LLM | API LLM toggle button (in the left sidebar footer or top of AI pages) to choose your engine.',
      'Select API LLM for fast cloud synthesis via Groq (default suitable model: qwen/qwen3.8-27b) when Earth/network link is active.',
      'Select Local LLM for strict local/offline operation (local Ollama if running, or deterministic offline NASA/CSA RAG fallback—automatically enforced during Blackout mode).',
    ],
    beginnerTip:
      'Whether Local or API LLM is selected, TARS Care never invents citations, refuses to prescribe medication dosages, and falls back seamlessly to local offline reference lookup.',
  },
  {
    id: 'emergency',
    tabTarget: 'overview',
    actionType: 'tab',
    actionLabel: 'Return to Overview',
    title: 'Emergency Escalation Checklist (When Numbers Turn Red)',
    whatItDoes:
      'Provides immediate, step-by-step zero-latency onboard stabilization actions and voice readouts when critical vitals or red-flag symptoms (chest discomfort, shortness of breath, faintness, high CO₂) appear.',
    steps: [
      'Stop any physical exertion immediately if Critical Status or an Exercise Hold warning appears.',
      'Click the Status badge in the top header (or Launch Emergency Checklist) to open high-contrast Crew Medical Officer (CMO) steps.',
      'Verify habitat air (O₂, CO₂, cabin pressure) first so an environmental leak or scrubber fault is never mistaken for an isolated medical issue.',
      'Check off completed steps and queue a Priority Store-and-Forward Flight Surgeon packet once Earth sync is reachable.',
    ],
    beginnerTip:
      'Under 22-minute light-time delays, Earth cannot guide acute emergencies in real time—this checklist works 100% locally with zero network latency.',
  },
];

const MEASUREMENT_CARDS = [
  {
    title: 'Heart Rate & Blood Pressure',
    icon: HeartPulse,
    target: 'Typical rest delta: within ±12 BPM / ±15 mmHg of personal baseline',
    steps: [
      'Rest quietly sitting or lying down for 5 full minutes before measuring.',
      'Keep legs uncrossed and support the cuff arm level with your heart.',
      'Avoid coffee, decongestants, or ARED exercise for 30 minutes beforehand.',
      'If checking dizziness, record resting pressure first, then stand calmly and re-check after 2–3 minutes.',
    ],
  },
  {
    title: 'Oxygen Saturation (SpO₂) & Breathing',
    icon: Wind,
    target: 'Typical SpO₂: ≥ 95% · Alert threshold: < 94% (Check cabin O₂ immediately)',
    steps: [
      'Warm cold hands by rubbing palms together—cold fingers cause false low readings.',
      'Clip the pulse oximeter onto a relaxed finger and stay still for 20 seconds until waves steady.',
      'Count full breaths silently for 30 seconds and multiply by 2 while resting.',
    ],
  },
  {
    title: 'Body Temperature',
    icon: Activity,
    target: 'Compare against personal baseline (~36.4–37.2°C); watch persistent ≥ 37.8°C',
    steps: [
      'Wait at least 15 minutes after hot beverages, meals, or heavy suit work.',
      'Use the same body site (forehead, ear, or oral) each time so trends stay comparable.',
      'Never rely on a single border reading alone—log symptoms and habitat temp alongside it.',
    ],
  },
  {
    title: 'Vision / SANS Check (Amsler Grid)',
    icon: Eye,
    target: 'Checks subtle fluid-shift pressure behind the eyes',
    steps: [
      'Put on your prescribed reading or distance glasses if you normally wear them.',
      'Cover your left eye gently without pressing on the eyelid; stare at the center dot.',
      'Notice if any lines look wavy, blurry, gray, or missing, then repeat with your right eye covered.',
    ],
  },
  {
    title: 'Radiation Dosimetry (mGy vs. mSv)',
    icon: Radiation,
    target: 'Keep physical absorbed dose (mGy) separate from biological risk (mSv)',
    steps: [
      'Check your personal crew badge and the habitat TEPC dosimeter once per Sol.',
      'Log mGy / mGy·hr (energy absorbed) and mSv / mSv·day (biological risk) into their distinct boxes.',
      'Check DONKI solar particle alerts before exiting into unshielded airlocks or EVA.',
    ],
  },
  {
    title: 'Cabin Air Check (CO₂, O₂, Humidity)',
    icon: Stethoscope,
    target: 'Watch cabin CO₂ ≥ 3.0 mmHg · Target RH ~40–60% · O₂ ~20–21%',
    steps: [
      'Read the habitat ECLSS air monitor near your sleeping rack or workbench (CO₂ pockets form in low-airflow microgravity).',
      'Confirm portable circulation fans and CO₂ scrubbers are running smoothly.',
      'Pair air readings with any unexplained headache, grogginess, or dry cough before assuming illness.',
    ],
  },
];

const INDICATOR_CARDS = [
  {
    name: 'Resting Heart Rate (BPM)',
    meaning: 'Shows how hard your heart works at rest. Fluid loss, stress, infection, or cardiovascular deconditioning raise resting BPM.',
    watchOut: 'Sustained rise ≥ +15 BPM above your personal baseline, or > 100 BPM at rest.',
    firstStep: 'Rest 10 minutes, hydrate with electrolyte fluid, and re-measure before logging exercise.',
  },
  {
    name: 'Blood Pressure (Systolic / Diastolic mmHg)',
    meaning: 'Force of blood pushing on artery walls. Too low upon standing causes lightheadedness (orthostatic intolerance).',
    watchOut: 'Big drop (> 20 mmHg systolic) on standing, faintness, or sharp jump ≥ 140/90 with symptoms.',
    firstStep: 'Sit or lie down immediately if dizzy; never perform EVA or ARED while presyncope persists.',
  },
  {
    name: 'Oxygen Saturation (SpO₂ %)',
    meaning: 'Percentage of red blood cells carrying oxygen. Reflects both lung gas exchange and cabin oxygen supply.',
    watchOut: 'SpO₂ below 94% on repeat reading, especially with shortness of breath.',
    firstStep: 'Verify finger warmth/probe fit, inspect cabin O₂ pressure, and open CMO Oxygen Protocol if < 94%.',
  },
  {
    name: 'Sleep Duration & Mood Score',
    meaning: 'Tracks recovery quality and isolation fatigue across light-shifted Mars Sols.',
    watchOut: 'Consistent sleep under 6.0 hrs/night, rising fatigue/stress, or drops in focus.',
    firstStep: 'Protect dark quiet sleep schedule, reduce pre-sleep blue light, and check cabin CO₂ levels.',
  },
  {
    name: 'Cabin CO₂ (mmHg / ppm)',
    meaning: 'Accumulated carbon dioxide in closed habitat air. Even mild pockets can cause headache and slowed thinking.',
    watchOut: 'Sustained ≥ 3.0 mmHg (~3,950 ppm) or crew headaches in one module.',
    firstStep: 'Check circulation fans, switch CDRA scrubber beds, and rotate crew out of dead-air corners.',
  },
  {
    name: 'Absorbed (mGy) vs. Effective Dose (mSv)',
    meaning: 'mGy tells you raw radiation energy deposited; mSv adjusts that energy for how damaging cosmic rays vs. solar protons are to human tissue.',
    watchOut: 'Sudden dose-rate spikes during solar flares or approaching cumulative mission advisory limits.',
    firstStep: 'Relocate to hydrogen-rich water/polyethylene storm shelter and delay non-essential EVAs.',
  },
];

const SPACEFLIGHT_RISKS = [
  {
    title: '1. Gravity Fields (0g Transit & 0.38g Mars)',
    icon: Activity,
    whatHappens:
      'Without Earth’s full 1g pull, fluid shifts toward your chest and head while leg muscles and weight-bearing bones gradually lose strength.',
    earlySigns: 'Puffy face, nasal congestion, subtle near-vision blur (SANS), stiff back, or dizziness when standing up.',
    actions: 'Complete prescribed resistance + aerobic countermeasures, stay hydrated, and run periodic SANS vision & balance checks.',
  },
  {
    title: '2. Space Radiation (Cosmic Rays & Solar Storms)',
    icon: Radiation,
    whatHappens:
      'Beyond Earth’s magnetic field, continuous galactic cosmic rays and sudden solar particle eruptions pass through thin hull walls.',
    earlySigns: 'No immediate physical sensation at typical cruise levels—detected strictly by crew badges, cabin TEPC sensors, and DONKI storm alerts.',
    actions: 'Log daily mGy and mSv accurately without mixing units; move into storm-shielded sleeping quarters when solar alerts rise.',
  },
  {
    title: '3. Hostile & Closed Environments (Cabin Air & Microbes)',
    icon: Wind,
    whatHappens:
      'Every breath, dust particle, and surface microbe stays inside the spacecraft closed loop unless filtered.',
    earlySigns: 'Headache, brain fog, dry throat/cough, or eye irritation—often tied to localized CO₂ pockets or low humidity rather than infection.',
    actions: 'Check cabin CO₂, O₂, humidity (40–60%), and HEPA airflow alongside physical symptoms before assuming contagious illness.',
  },
  {
    title: '4. Isolation & Confinement',
    icon: Users,
    whatHappens:
      'Living months in compact quarters with a small crew, sensory monotony, and delayed Earth contact strains sleep and mood.',
    earlySigns: 'Shortened sleep (< 6 hrs), irritability, low motivation, or feeling disconnected from crewmates and family.',
    actions: 'Maintain regular sleep-wake lighting cues, stay in routine crew check-ins, and use My Journal or Personal Companion for low-pressure decompression.',
  },
  {
    title: '5. Distance from Earth (4–24 Min Delay & Blackouts)',
    icon: Radio,
    whatHappens:
      'Light-speed radio delay prevents real-time conversations with Earth Flight Surgeons, and solar conjunctions periodically sever contact completely.',
    earlySigns: 'Delayed or queued acknowledgments under Delayed/Blackout link status.',
    actions: 'Practice reading your onboard personal baseline trends, keep Local LLM / offline protocols ready, and queue non-urgent packets via Store-and-Forward.',
  },
];

export const HealthGuideModal: React.FC<GuideModalProps> = ({
  initialSection = 'walkthrough',
  initialStepId,
  onClose,
  onNavigateTab,
  onOpenBaseline,
  onOpenSansModal,
}) => {
  const [section, setSection] = useState<GuideSection>(initialSection);
  const initialIndex = initialStepId
    ? Math.max(
        0,
        WALKTHROUGH_STEPS.findIndex((s) => s.id === initialStepId || s.tabTarget === initialStepId),
      )
    : 0;
  const [stepIndex, setStepIndex] = useState<number>(initialIndex);
  const bodyScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (bodyScrollRef.current) {
      bodyScrollRef.current.scrollTop = 0;
    }
  }, [section, stepIndex]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const activeStep = WALKTHROUGH_STEPS[stepIndex] || WALKTHROUGH_STEPS[0];

  const handleLaunchStepFunction = () => {
    onClose();
    if (activeStep.actionType === 'baseline' && onOpenBaseline) {
      onOpenBaseline();
      return;
    }
    if (activeStep.actionType === 'sans' && onOpenSansModal) {
      onOpenSansModal();
      return;
    }
    if (activeStep.tabTarget) {
      onNavigateTab(activeStep.tabTarget);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#040610]/80 backdrop-blur-md p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="health-guide-modal-title"
      onClick={onClose}
    >
      <div
        className="flex flex-col max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-white/[0.14] bg-[#121522] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Fixed Modal Header & Section Tabs */}
        <div className="shrink-0 border-b border-white/[0.08] bg-[#121522] px-5 sm:px-7 py-4 space-y-3.5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-full bg-[#0B0D1A] border border-[#A5D8FF]/40 flex items-center justify-center shrink-0 mt-0.5">
                <HelpCircle className="w-4 h-4 text-[#A5D8FF]" />
              </div>
              <div>
                <h2 id="health-guide-modal-title" className="text-lg sm:text-xl font-bold text-[#FAF9FA]">
                  Astronaut Health Guide &amp; Step-by-Step Walkthrough
                </h2>
                <p className="text-xs sm:text-sm text-[#E5E5E4]/75 mt-0.5">
                  Plain-language instructions covering what each function does, how to take measurements, health indicators, and deep-space risks.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close guide popup"
              className="min-w-[36px] min-h-[36px] flex items-center justify-center rounded-xl border border-white/[0.12] bg-[#0B0D1A] text-[#E5E5E4]/80 hover:text-[#FAF9FA] hover:border-[#A5D8FF]/45 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Health guide sections">
            {[
              { id: 'walkthrough' as const, label: 'Step-by-Step Walkthrough', icon: Compass },
              { id: 'measure' as const, label: 'How to Measure', icon: Stethoscope },
              { id: 'indicators' as const, label: 'Health Indicators', icon: HeartPulse },
              { id: 'risks' as const, label: '5 Spaceflight Risks', icon: AlertTriangle },
            ].map((tab) => {
              const Icon = tab.icon;
              const active = section === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setSection(tab.id)}
                  className={`px-3.5 py-2 rounded-full text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${
                    active
                      ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                      : 'bg-[#0B0D1A] text-[#E5E5E4]/85 border border-white/[0.1] hover:border-[#A5D8FF]/40 hover:text-[#FAF9FA]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Scrollable Popup Body */}
        <div ref={bodyScrollRef} className="flex-1 min-h-0 overflow-y-auto p-5 sm:p-7 space-y-6">
          {/* TAB 1: STEP-BY-STEP WALKTHROUGH */}
          {section === 'walkthrough' && (
            <div className="space-y-5">
              {/* Step Selector Strip */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5" role="list" aria-label="Walkthrough steps">
                  {WALKTHROUGH_STEPS.map((st, idx) => {
                    const active = idx === stepIndex;
                    return (
                      <button
                        key={st.id}
                        type="button"
                        onClick={() => setStepIndex(idx)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                          active
                            ? 'bg-[#A5D8FF]/20 text-[#A5D8FF] border border-[#A5D8FF]/55 font-semibold'
                            : 'bg-[#0B0D1A] text-[#E5E5E4]/75 border border-white/[0.08] hover:text-[#FAF9FA] hover:border-white/25'
                        }`}
                      >
                        Step {idx + 1}
                      </button>
                    );
                  })}
                </div>
                <span className="text-xs text-[#E5E5E4]/70 tabular-data">
                  Step {stepIndex + 1} of {WALKTHROUGH_STEPS.length}
                </span>
              </div>

              {/* Active Step Detail Card */}
              <div className="rounded-2xl bg-[#0B0D1A] border border-white/[0.1] p-5 sm:p-6 space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.07]">
                  <div>
                    <div className="text-xs font-semibold text-[#A5D8FF] mb-1">
                      Step {stepIndex + 1} of {WALKTHROUGH_STEPS.length} · Function Guide
                    </div>
                    <h3 className="text-lg sm:text-xl font-bold text-[#FAF9FA]">
                      {activeStep.title}
                    </h3>
                  </div>
                  <button
                    type="button"
                    onClick={handleLaunchStepFunction}
                    className="mc-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5 shrink-0"
                  >
                    <span>{activeStep.actionLabel}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* What the function does */}
                <div className="space-y-1.5">
                  <div className="text-xs font-semibold text-[#A5D8FF] inline-flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>What this function does</span>
                  </div>
                  <p className="text-sm text-[#FAF9FA] leading-relaxed">
                    {activeStep.whatItDoes}
                  </p>
                </div>

                {/* Step-by-step instructions */}
                <div className="space-y-2.5">
                  <div className="text-xs font-semibold text-[#E5E5E4]/90 inline-flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#A5D8FF]" />
                    <span>How to do it step by step</span>
                  </div>
                  <ol className="space-y-2.5">
                    {activeStep.steps.map((instruction, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-3 rounded-xl bg-[#121522] px-4 py-3 border border-white/[0.06]"
                      >
                        <span className="w-6 h-6 rounded-full bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/35 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5 tabular-data">
                          {i + 1}
                        </span>
                        <span className="text-sm text-[#E5E5E4] leading-relaxed">{instruction}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                {/* Practical Beginner Tip */}
                <div className="rounded-xl bg-[#121522] border border-[#A5D8FF]/25 px-4 py-3 text-xs sm:text-sm text-[#E5E5E4]/90 leading-relaxed flex items-start gap-2.5">
                  <BookOpen className="w-4 h-4 text-[#A5D8FF] shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-[#FAF9FA]">Good to know: </strong>
                    {activeStep.beginnerTip}
                  </div>
                </div>
              </div>

              {/* Footer Next / Prev Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <button
                  type="button"
                  disabled={stepIndex === 0}
                  onClick={() => setStepIndex((prev) => Math.max(0, prev - 1))}
                  className="mc-btn-secondary px-4 py-2 text-xs inline-flex items-center gap-1.5 disabled:opacity-40"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Previous Step</span>
                </button>

                <div className="flex items-center gap-2">
                  {stepIndex < WALKTHROUGH_STEPS.length - 1 ? (
                    <button
                      type="button"
                      onClick={() =>
                        setStepIndex((prev) => Math.min(WALKTHROUGH_STEPS.length - 1, prev + 1))
                      }
                      className="mc-btn-primary px-5 py-2 text-xs inline-flex items-center gap-1.5"
                    >
                      <span>Next Step</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={onClose}
                      className="mc-btn-primary px-5 py-2 text-xs inline-flex items-center gap-1.5"
                    >
                      <span>Finish Walkthrough</span>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: HOW TO MEASURE */}
          {section === 'measure' && (
            <div className="space-y-5">
              <div className="rounded-xl bg-[#0B0D1A] border border-white/[0.08] p-4 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs sm:text-sm text-[#E5E5E4] leading-relaxed max-w-2xl">
                  You do not need medical training to record accurate readings. Follow these simple steps before typing numbers or connecting sensors in{' '}
                  <strong className="text-[#FAF9FA]">Health Assessment</strong>.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onNavigateTab('assessment');
                  }}
                  className="mc-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5 shrink-0"
                >
                  <span>Go to Health Assessment</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {MEASUREMENT_CARDS.map((card) => {
                  const Icon = card.icon;
                  return (
                    <div
                      key={card.title}
                      className="rounded-2xl bg-[#0B0D1A] border border-white/[0.08] p-5 space-y-3"
                    >
                      <div className="flex items-start gap-2.5">
                        <Icon className="w-5 h-5 text-[#A5D8FF] shrink-0 mt-0.5" />
                        <div>
                          <h3 className="text-base font-semibold text-[#FAF9FA]">{card.title}</h3>
                          <div className="text-xs text-[#A5D8FF] mt-0.5">{card.target}</div>
                        </div>
                      </div>
                      <ol className="space-y-2 pt-1">
                        {card.steps.map((s, idx) => (
                          <li key={idx} className="flex items-start gap-2.5 text-xs sm:text-sm text-[#E5E5E4]/90 leading-relaxed">
                            <span className="font-semibold text-[#A5D8FF] shrink-0 tabular-data">
                              {idx + 1}.
                            </span>
                            <span>{s}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 3: HEALTH INDICATORS */}
          {section === 'indicators' && (
            <div className="space-y-5">
              {/* Traffic-Light Status & Baseline Explainer */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                <div className="rounded-xl bg-[#0B0D1A] border border-emerald-500/30 p-4 space-y-1.5">
                  <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Normal · EVA: GO</span>
                  </div>
                  <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
                    Indicators stay aligned with your personal baseline and cabin life-support looks stable. Continue routine exercise and daily logging.
                  </p>
                </div>

                <div className="rounded-xl bg-[#0B0D1A] border border-amber-500/35 p-4 space-y-1.5">
                  <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Warning · EVA: CAUTION</span>
                  </div>
                  <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
                    One or more indicators shifted from your baseline (or radiation/CO₂ climbed). Re-measure calmly, hydrate/rest, and check the cabin air or shielding.
                  </p>
                </div>

                <div className="rounded-xl bg-[#0B0D1A] border border-red-500/40 p-4 space-y-1.5">
                  <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-300">
                    <ShieldAlert className="w-4 h-4" />
                    <span>Critical · EVA: HOLD</span>
                  </div>
                  <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
                    High-risk reading or red-flag symptom detected. Stop physical workouts immediately, open the CMO Emergency Checklist, and verify habitat O₂/CO₂.
                  </p>
                </div>
              </div>

              {onOpenBaseline && (
                <div className="rounded-xl bg-[#0B0D1A] border border-[#A5D8FF]/25 p-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-start gap-2.5 text-xs sm:text-sm text-[#E5E5E4] max-w-2xl">
                    <SlidersHorizontal className="w-4 h-4 text-[#A5D8FF] shrink-0 mt-0.5" />
                    <span>
                      <strong className="text-[#FAF9FA]">Why Personal Baseline comes first:</strong> Earth normal numbers do not automatically apply in microgravity (0g) or Mars gravity (0.38g). TARS Care tracks how far your readings move relative to <strong className="text-[#FAF9FA]">your own</strong> resting values.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onOpenBaseline();
                    }}
                    className="mc-btn-secondary px-3.5 py-2 text-xs shrink-0"
                  >
                    Open Personal Baseline
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {INDICATOR_CARDS.map((ind) => (
                  <div
                    key={ind.name}
                    className="rounded-2xl bg-[#0B0D1A] border border-white/[0.08] p-4 sm:p-5 space-y-2.5"
                  >
                    <h3 className="text-sm sm:text-base font-semibold text-[#FAF9FA]">{ind.name}</h3>
                    <p className="text-xs sm:text-sm text-[#E5E5E4]/85 leading-relaxed">{ind.meaning}</p>
                    <div className="rounded-lg bg-[#121522] px-3 py-2 text-xs text-[#E5E5E4] space-y-1">
                      <div>
                        <strong className="text-[#A5D8FF]">Watch out: </strong>
                        {ind.watchOut}
                      </div>
                      <div>
                        <strong className="text-[#FAF9FA]">First step: </strong>
                        {ind.firstStep}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 4: 5 SPACEFLIGHT RISKS */}
          {section === 'risks' && (
            <div className="space-y-4">
              <div className="rounded-xl bg-[#0B0D1A] border border-white/[0.08] p-4 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs sm:text-sm text-[#E5E5E4] leading-relaxed max-w-2xl">
                  Deep-space risks rarely feel dramatic at the start. Here is what NASA’s five spaceflight hazards look like in everyday life onboard, and what protects you early.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onNavigateTab('hazards');
                  }}
                  className="mc-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5 shrink-0"
                >
                  <span>Explore 5 Hazard Modules</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="space-y-3.5">
                {SPACEFLIGHT_RISKS.map((risk) => {
                  const Icon = risk.icon;
                  return (
                    <div
                      key={risk.title}
                      className="rounded-2xl bg-[#0B0D1A] border border-white/[0.08] p-5 space-y-2.5"
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className="w-5 h-5 text-[#A5D8FF] shrink-0" />
                        <h3 className="text-base font-semibold text-[#FAF9FA]">{risk.title}</h3>
                      </div>
                      <p className="text-xs sm:text-sm text-[#E5E5E4] leading-relaxed">{risk.whatHappens}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs">
                        <div className="rounded-xl bg-[#121522] p-3 border border-white/[0.06]">
                          <div className="font-semibold text-[#A5D8FF] mb-1">Early signs to notice</div>
                          <div className="text-[#E5E5E4]/90 leading-relaxed">{risk.earlySigns}</div>
                        </div>
                        <div className="rounded-xl bg-[#121522] p-3 border border-white/[0.06]">
                          <div className="font-semibold text-[#FAF9FA] mb-1">Simple preventive actions</div>
                          <div className="text-[#E5E5E4]/90 leading-relaxed">{risk.actions}</div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
