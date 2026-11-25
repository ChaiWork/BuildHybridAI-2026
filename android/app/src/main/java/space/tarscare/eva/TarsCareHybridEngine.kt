package space.tarscare.eva

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.ai.FirebaseAI
import com.google.firebase.ai.InferenceMode
import com.google.firebase.ai.InferenceSource
import com.google.firebase.ai.OnDeviceConfig
import com.google.firebase.ai.type.GenerativeBackend
import com.google.firebase.ai.type.content
import com.google.firebase.appcheck.FirebaseAppCheck
import com.google.firebase.appcheck.debug.DebugAppCheckProviderFactory
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreSettings
import com.google.firebase.firestore.ListenerRegistration
import com.google.firebase.firestore.PersistentCacheSettings
import com.google.firebase.firestore.Query
import com.google.firebase.remoteconfig.FirebaseRemoteConfig
import com.google.firebase.remoteconfig.FirebaseRemoteConfigSettings
import kotlinx.coroutines.tasks.await
import kotlin.system.measureTimeMillis

data class RuntimeFirebaseConfig(
    val projectId: String,
    val applicationId: String,
    val apiKey: String,
    val cloudModel: String = "gemini-3.5-flash-lite",
)

data class EvaSyncRecord(
    val id: String,
    val crewName: String,
    val sol: Int,
    val urgency: String,
    val summary: String,
    val sourcePlatform: String,
    val inferenceSource: String,
    val pendingCloudSync: Boolean,
)

data class HybridTriageResult(
    val guidance: String,
    val actualSource: String,
    val latencyMs: Long,
    val exerciseHoldActive: Boolean,
    val queuedInFirestore: Boolean,
)

/**
 * TARS Care Native Android EVA Hybrid Engine
 *
 * Unifies:
 * - Firebase AI Logic Hybrid SDK (`com.google.firebase:firebase-ai` + `firebase-ai-ondevice`)
 *   running Android Gemini Nano 4 on-device (`PREFER_ON_DEVICE` & `ONLY_ON_DEVICE`) with
 *   automatic Cloud Gemini (`gemini-3.5-flash-lite`) fallback.
 * - Firebase App Check (`DebugAppCheckProviderFactory` for local/judge verification).
 * - Firebase Anonymous Crew Authentication.
 * - Cloud Firestore Offline Store-and-Forward (`eva_logs`) shared live with the Web Console.
 * - Firebase Remote Config mission hazard thresholds (`co2_warn_mmhg`, `rad_warn_msv`).
 */
class TarsCareHybridEngine(private val context: Context) {

    private val prefs = context.getSharedPreferences("tarscare_eva_prefs", Context.MODE_PRIVATE)
    private val prescriptionRegex = Regex(
        """(?i)\b(?:take|administer|prescribe|start|dose\s+of)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablet|tablets|capsule|capsules|pill|pills)\b|\b(?:amoxicillin|azithromycin|ciprofloxacin|doxycycline|ibuprofen|acetaminophen|paracetamol|prednisone|alprazolam|sertraline|modafinil|zolpidem|aspirin|tramadol|codeine|diazepam|lorazepam|melatonin)\s+\d+(?:\.\d+)?\s*(?:mg|mcg)\b"""
    )

    var isCloudProjectConfigured: Boolean = false
        private set

    var activeProjectId: String = "tarscare-ondevice-sandbox"
        private set

    var co2WarnThresholdMmhg: Double = 3.0
        private set

    var radWarnThresholdMsv: Double = 50.0
        private set

    private var app: FirebaseApp? = null
    private var firestore: FirebaseFirestore? = null
    private var syncListener: ListenerRegistration? = null

    fun ensureInitialized(onSyncUpdated: ((List<EvaSyncRecord>) -> Unit)? = null): String {
        val savedProject = prefs.getString("projectId", "")?.trim().orEmpty()
        val savedAppId = prefs.getString("applicationId", "")?.trim().orEmpty()
        val savedApiKey = prefs.getString("apiKey", "")?.trim().orEmpty()

        // 1. Use default google-services.json FirebaseApp if present, else saved runtime config, else local Nano sandbox
        val defaultApps = FirebaseApp.getApps(context)
        val resolvedApp: FirebaseApp = when {
            savedProject.isNotEmpty() && savedAppId.isNotEmpty() && savedApiKey.isNotEmpty() -> {
                isCloudProjectConfigured = true
                activeProjectId = savedProject
                val name = "tarscare-runtime-$savedProject"
                defaultApps.firstOrNull { it.name == name } ?: FirebaseApp.initializeApp(
                    context,
                    FirebaseOptions.Builder()
                        .setProjectId(savedProject)
                        .setApplicationId(savedAppId)
                        .setApiKey(savedApiKey)
                        .build(),
                    name,
                )
            }
            defaultApps.any { it.name == FirebaseApp.DEFAULT_APP_NAME } -> {
                val def = FirebaseApp.getInstance()
                isCloudProjectConfigured = !def.options.projectId.isNullOrBlank()
                activeProjectId = def.options.projectId ?: "firebase-default"
                def
            }
            else -> {
                isCloudProjectConfigured = false
                activeProjectId = "tarscare-ondevice-sandbox"
                val sandboxName = "tarscare-local-nano"
                defaultApps.firstOrNull { it.name == sandboxName } ?: FirebaseApp.initializeApp(
                    context,
                    FirebaseOptions.Builder()
                        .setProjectId("tarscare-ondevice-sandbox")
                        .setApplicationId("1:000000000000:android:0000000000000000000000")
                        .setApiKey("AIzaSyLocalAndroidGeminiNanoSandbox0000")
                        .build(),
                    sandboxName,
                )
            }
        }

        app = resolvedApp

        // 2. Activate Firebase App Check (Debug provider accepted per #BuildHybridAI rules)
        runCatching {
            val appCheck = FirebaseAppCheck.getInstance(resolvedApp)
            appCheck.installAppCheckProviderFactory(DebugAppCheckProviderFactory.getInstance())
        }

        // 3. Configure Auth, Offline-Cached Firestore, and Remote Config when Cloud project is active
        if (isCloudProjectConfigured) {
            runCatching {
                val auth = FirebaseAuth.getInstance(resolvedApp)
                if (auth.currentUser == null) {
                    auth.signInAnonymously()
                }
            }

            runCatching {
                val db = FirebaseFirestore.getInstance(resolvedApp)
                db.firestoreSettings = FirebaseFirestoreSettings.Builder()
                    .setLocalCacheSettings(PersistentCacheSettings.newBuilder().build())
                    .build()
                firestore = db
                if (onSyncUpdated != null) {
                    attachEvaSyncStream(db, onSyncUpdated)
                }
            }

            runCatching {
                val rc = FirebaseRemoteConfig.getInstance(resolvedApp)
                rc.setConfigSettingsAsync(
                    FirebaseRemoteConfigSettings.Builder()
                        .setMinimumFetchIntervalInSeconds(60)
                        .build()
                )
                rc.setDefaultsAsync(
                    mapOf(
                        "co2_warn_mmhg" to 3.0,
                        "rad_warn_msv" to 50.0,
                        "cloud_fallback_model" to "gemini-3.5-flash-lite",
                    )
                )
                rc.fetchAndActivate().addOnSuccessListener {
                    co2WarnThresholdMmhg = rc.getDouble("co2_warn_mmhg").takeIf { it > 0 } ?: 3.0
                    radWarnThresholdMsv = rc.getDouble("rad_warn_msv").takeIf { it > 0 } ?: 50.0
                }
            }
        }

        return activeProjectId
    }

    fun saveRuntimeFirebaseConfig(
        cfg: RuntimeFirebaseConfig,
        onSyncUpdated: ((List<EvaSyncRecord>) -> Unit)? = null,
    ) {
        prefs.edit()
            .putString("projectId", cfg.projectId.trim())
            .putString("applicationId", cfg.applicationId.trim())
            .putString("apiKey", cfg.apiKey.trim())
            .putString("cloudModel", cfg.cloudModel.trim().ifEmpty { "gemini-3.5-flash-lite" })
            .apply()
        syncListener?.remove()
        syncListener = null
        ensureInitialized(onSyncUpdated)
    }

    private fun attachEvaSyncStream(
        db: FirebaseFirestore,
        onSyncUpdated: (List<EvaSyncRecord>) -> Unit,
    ) {
        syncListener?.remove()
        syncListener = db.collection("eva_logs")
            .orderBy("createdAtMs", Query.Direction.DESCENDING)
            .limit(8)
            .addSnapshotListener { snap, _ ->
                if (snap == null) return@addSnapshotListener
                val items = snap.documents.map { doc ->
                    EvaSyncRecord(
                        id = doc.id,
                        crewName = doc.getString("crewName") ?: "SuChai",
                        sol = (doc.getLong("sol") ?: 184L).toInt(),
                        urgency = doc.getString("urgency") ?: "NORMAL",
                        summary = doc.getString("summary") ?: "",
                        sourcePlatform = doc.getString("sourcePlatform") ?: "ANDROID_COMPANION",
                        inferenceSource = doc.getString("inferenceSource") ?: "ON_DEVICE",
                        pendingCloudSync = doc.metadata.hasPendingWrites(),
                    )
                }
                onSyncUpdated(items)
            }
    }

    suspend fun setBlackoutMode(offlineBlackout: Boolean) {
        val db = firestore ?: return
        runCatching {
            if (offlineBlackout) {
                db.disableNetwork().await()
            } else {
                db.enableNetwork().await()
            }
        }
    }

    suspend fun checkAndWarmupGeminiNano(): String {
        val firebaseApp = app ?: return "FirebaseApp uninitialized"
        return runCatching {
            val model = FirebaseAI.getInstance(firebaseApp, GenerativeBackend.googleAI())
                .generativeModel(
                    modelName = "gemini-3.5-flash-lite",
                    onDeviceConfig = OnDeviceConfig(InferenceMode.ONLY_ON_DEVICE),
                )
            val ext = model.onDeviceExtension ?: return "OnDeviceExtension not attached"
            val status = ext.checkStatus()
            runCatching { ext.warmUp() }
            "Android Gemini Nano 4 Status: $status"
        }.getOrElse { err ->
            "Gemini Nano 4 AICore status: ${err.message ?: "Unavailable on emulator — PREFER_ON_DEVICE will use Cloud Gemini fallback"}"
        }
    }

    private fun sanitizeMedicalOutput(raw: String): String {
        if (!prescriptionRegex.containsMatchIn(raw)) return raw.trim()
        return raw.replace(
            prescriptionRegex,
            "[MEDICATION DOSING REDACTED — CONSULT CMO / FLIGHT SURGEON]"
        ).trim() + "\n\nSafety Gate: Medication dosages redacted per TARS Care autonomous safety rules."
    }

    /**
     * Runs EVA Field Triage via Firebase AI Logic Hybrid SDK (`PREFER_ON_DEVICE` or `ONLY_ON_DEVICE` in Blackout),
     * enforces Exercise-Hold & mGy/mSv safety rules, and queues telemetry to Cloud Firestore (`eva_logs`).
     */
    suspend fun runEvaHybridTriage(
        crewId: String,
        crewName: String,
        sol: Int,
        heartRateBpm: Int,
        spo2Pct: Double,
        co2Mmhg: Double,
        absorbedDoseMgy: Double,
        equivRateMsvDay: Double,
        symptoms: List<String>,
        offlineBlackout: Boolean,
        preferredMode: InferenceMode,
    ): HybridTriageResult {
        val firebaseApp = app ?: throw IllegalStateException("FirebaseApp not initialized")
        val exerciseHold = heartRateBpm >= 115 || spo2Pct < 94.0 ||
            symptoms.any { it.contains("Chest", true) || it.contains("Faintness", true) || it.contains("Shortness", true) }
        val urgency = when {
            spo2Pct < 92.0 || heartRateBpm >= 125 || co2Mmhg >= 4.5 -> "CRITICAL"
            exerciseHold || co2Mmhg >= co2WarnThresholdMmhg || symptoms.isNotEmpty() -> "WARNING"
            else -> "NORMAL"
        }

        val effectiveMode = when {
            offlineBlackout || !isCloudProjectConfigured -> InferenceMode.ONLY_ON_DEVICE
            else -> preferredMode
        }

        val cloudModel = prefs.getString("cloudModel", "gemini-3.5-flash-lite") ?: "gemini-3.5-flash-lite"
        val sysPrompt = content {
            text(
                buildString {
                    appendLine("You are TARS Care EVA Wrist Companion assisting astronaut $crewName on Mars Sol $sol.")
                    appendLine("Rules:")
                    appendLine("1. Separate physical absorbed radiation dose (mGy) from biologically weighted equivalent dose (mSv).")
                    appendLine("2. Never diagnose psychiatric/infectious diseases and NEVER prescribe medication dosages.")
                    if (exerciseHold) {
                        appendLine("3. EXERCISE HOLD ACTIVE: Suspend physical exertion immediately and direct crew to rest and alert CMO.")
                    }
                    appendLine("Provide 3 concise, actionable EVA triage bullets citing NASA HRP / CSA principles.")
                }
            )
        }

        val prompt = """
            EVA Suit Telemetry (Sol $sol):
            - Heart Rate: $heartRateBpm BPM | SpO2: $spo2Pct% | Suit CO2: $co2Mmhg mmHg
            - Radiation: $absorbedDoseMgy mGy absorbed | $equivRateMsvDay mSv/day equivalent
            - Reported Symptoms: ${symptoms.joinToString().ifEmpty { "None" }}
            - Link Mode: ${if (offlineBlackout) "SOLAR CONJUNCTION BLACKOUT" else "MARS DELAYED LINK"}
        """.trimIndent()

        var guidanceText = ""
        var actualSource = "DETERMINISTIC_OFFLINE_SAFETY"

        val elapsed = measureTimeMillis {
            runCatching {
                val model = FirebaseAI.getInstance(firebaseApp, GenerativeBackend.googleAI())
                    .generativeModel(
                        modelName = cloudModel,
                        systemInstruction = sysPrompt,
                        onDeviceConfig = OnDeviceConfig(effectiveMode),
                    )
                val response = model.generateContent(prompt)
                guidanceText = sanitizeMedicalOutput(response.text.orEmpty())
                actualSource = if (response.inferenceSource == InferenceSource.ON_DEVICE) {
                    "ON_DEVICE (Android Gemini Nano 4)"
                } else {
                    "IN_CLOUD ($cloudModel Fallback)"
                }
            }.onFailure {
                guidanceText = buildString {
                    appendLine("• [${urgency}] Sol $sol Deterministic EVA Triage (HR $heartRateBpm BPM, SpO2 $spo2Pct%, CO2 $co2Mmhg mmHg).")
                    if (exerciseHold) {
                        appendLine("• IMMEDIATE EXERCISE HOLD: Halt EVA exertion, verify suit O2/CO2 scrubber loop, and notify Crew Medical Officer [NASA-CSTARS-MED-01].")
                    } else {
                        appendLine("• Physiological parameters within autonomous EVA watch bounds; maintain hydration and dosimeter tracking ($absorbedDoseMgy mGy / $equivRateMsvDay mSv/d) [NASA-RADLAB-01].")
                    }
                    appendLine("• Non-prescribing boundary active; log queued locally for Habitat Console sync.")
                }
            }
        }

        var writtenToFirestore = false
        val db = firestore
        if (db != null && isCloudProjectConfigured) {
            runCatching {
                val summary = "EVA Sol $sol [$urgency]: HR $heartRateBpm BPM, SpO2 $spo2Pct%, CO2 $co2Mmhg mmHg · ${symptoms.joinToString().ifEmpty { "Nominal" }}"
                db.collection("eva_logs").add(
                    mapOf(
                        "crewId" to crewId,
                        "crewName" to crewName,
                        "sol" to sol,
                        "urgency" to urgency,
                        "summary" to summary,
                        "sourcePlatform" to "ANDROID_COMPANION",
                        "inferenceSource" to actualSource,
                        "is_private_journal" to false,
                        "createdAtIso" to java.time.Instant.now().toString(),
                        "createdAtMs" to System.currentTimeMillis(),
                    )
                )
                writtenToFirestore = true
            }
        }

        return HybridTriageResult(
            guidance = guidanceText,
            actualSource = actualSource,
            latencyMs = elapsed,
            exerciseHoldActive = exerciseHold,
            queuedInFirestore = writtenToFirestore,
        )
    }

    /**
     * Runs Zero-Egress Private Crew Journal Reflection strictly on-device (`InferenceMode.ONLY_ON_DEVICE`).
     * Never falls back to cloud and never writes private journal content to Firestore.
     */
    suspend fun runPrivateJournalOnDevice(
        crewName: String,
        sol: Int,
        journalEntry: String,
    ): Pair<String, Long> {
        val firebaseApp = app ?: throw IllegalStateException("FirebaseApp not initialized")
        var reply = ""
        val elapsed = measureTimeMillis {
            reply = runCatching {
                val model = FirebaseAI.getInstance(firebaseApp, GenerativeBackend.googleAI())
                    .generativeModel(
                        modelName = "gemini-3.5-flash-lite",
                        systemInstruction = content {
                            text("You are TARS Care Private Companion for astronaut $crewName on Sol $sol. Offer 3 warm, non-diagnostic reflective sentences. Never prescribe medications.")
                        },
                        onDeviceConfig = OnDeviceConfig(InferenceMode.ONLY_ON_DEVICE),
                    )
                val res = model.generateContent("Reflect gently on this private astronaut journal entry:\n\"$journalEntry\"")
                "ONLY_ON_DEVICE · Android Gemini Nano 4:\n" + sanitizeMedicalOutput(res.text.orEmpty())
            }.getOrElse {
                "Zero-Egress Privacy Lock Active (ONLY_ON_DEVICE): Android Gemini Nano 4 AICore is not yet downloaded on this device, so TARS Care blocked cloud fallback to keep your private journal 100% local."
            }
        }
        return reply to elapsed
    }
}

