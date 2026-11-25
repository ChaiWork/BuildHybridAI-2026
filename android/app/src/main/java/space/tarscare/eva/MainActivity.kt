package space.tarscare.eva

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.firebase.ai.InferenceMode
import kotlinx.coroutines.launch

// Pinned TARS Care Design System Palette (matches DESIGN.md)
private val SpaceGround = Color(0xFF0B0D1A)
private val SurfacePanel = Color(0xFF121522)
private val SurfaceElevated = Color(0xFF181C2E)
private val AccentGlow = Color(0xFFA5D8FF)
private val CtaFill = Color(0xFFEEF0F6)
private val CtaInk = Color(0xFF040404)
private val TextPrimary = Color(0xFFFAF9FA)
private val TextSecondary = Color(0xFFE5E5E4)
private val StatusNormal = Color(0xFF10B981)
private val StatusWarning = Color(0xFFF59E0B)
private val StatusCritical = Color(0xFFEF4444)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val engine = TarsCareHybridEngine(applicationContext)
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    background = SpaceGround,
                    surface = SurfacePanel,
                    primary = CtaFill,
                    onPrimary = CtaInk,
                    onBackground = TextPrimary,
                    onSurface = TextPrimary,
                )
            ) {
                TarsCareEvaApp(engine)
            }
        }
    }
}

@Composable
fun TarsCareEvaApp(engine: TarsCareHybridEngine) {
    val scope = rememberCoroutineScope()
    var activeTab by remember { mutableStateOf(0) }
    var offlineBlackout by remember { mutableStateOf(false) }
    var syncItems by remember { mutableStateOf<List<EvaSyncRecord>>(emptyList()) }
    var projectLabel by remember { mutableStateOf("Initializing...") }
    var nanoStatus by remember { mutableStateOf("Tap 'Warm Up Nano 4' to probe Android AICore") }

    // EVA Telemetry Inputs
    var hrText by remember { mutableStateOf("104") }
    var spo2Text by remember { mutableStateOf("96.4") }
    var co2Text by remember { mutableStateOf("3.2") }
    var mgyText by remember { mutableStateOf("0.52") }
    var msvText by remember { mutableStateOf("1.28") }
    var selectedMode by remember { mutableStateOf(InferenceMode.PREFER_ON_DEVICE) }
    val symptomOptions = listOf(
        "Headache",
        "Throat irritation",
        "Dizziness",
        "Shortness of breath",
        "Chest pain / discomfort",
    )
    var selectedSymptoms by remember { mutableStateOf(setOf("Headache")) }
    var triageBusy by remember { mutableStateOf(false) }
    var triageResult by remember { mutableStateOf<HybridTriageResult?>(null) }

    // Private Journal State (ONLY_ON_DEVICE)
    var journalText by remember {
        mutableStateOf("Completed 4-hour Jezero ridge EVA. Missing family audio calls during Mars delay, but feeling calm watching the dust horizon.")
    }
    var journalBusy by remember { mutableStateOf(false) }
    var journalReply by remember { mutableStateOf<String?>(null) }

    // Runtime Firebase Config State
    var cfgProjectId by remember { mutableStateOf("") }
    var cfgAppId by remember { mutableStateOf("") }
    var cfgApiKey by remember { mutableStateOf("") }
    var cfgNotice by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        projectLabel = engine.ensureInitialized { items -> syncItems = items }
    }

    Scaffold(
        containerColor = SpaceGround,
        topBar = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(SurfacePanel)
                    .padding(horizontal = 16.dp, vertical = 14.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column {
                        Text(
                            text = "TARS Care · EVA Companion",
                            color = TextPrimary,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "Sol 184 · SuChai · Firebase AI Logic Hybrid",
                            color = AccentGlow,
                            fontSize = 12.sp,
                        )
                    }
                    Box(
                        modifier = Modifier
                            .clip(CircleShape)
                            .background(if (offlineBlackout) StatusCritical.copy(alpha = 0.2f) else StatusNormal.copy(alpha = 0.2f))
                            .border(
                                1.dp,
                                if (offlineBlackout) StatusCritical else StatusNormal,
                                CircleShape,
                            )
                            .clickable {
                                val next = !offlineBlackout
                                offlineBlackout = next
                                scope.launch { engine.setBlackoutMode(next) }
                            }
                            .padding(horizontal = 12.dp, vertical = 6.dp)
                    ) {
                        Text(
                            text = if (offlineBlackout) "BLACKOUT (Offline)" else "LINK ACTIVE",
                            color = if (offlineBlackout) StatusCritical else StatusNormal,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf("EVA Triage", "Private Journal", "Sync & Config").forEachIndexed { idx, title ->
                        val active = activeTab == idx
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .clip(CircleShape)
                                .background(if (active) CtaFill else SpaceGround)
                                .clickable { activeTab = idx }
                                .padding(vertical = 8.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                text = title,
                                color = if (active) CtaInk else TextSecondary,
                                fontSize = 12.sp,
                                fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                            )
                        }
                    }
                }
            }
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            if (activeTab == 0) {
                // TAB 0: EVA HYBRID TRIAGE
                CardPanel {
                    Text(
                        text = "Hybrid Inference Policy (Gemini Nano 4 ↔ Cloud)",
                        color = AccentGlow,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf(
                            InferenceMode.PREFER_ON_DEVICE to "PREFER_ON_DEVICE",
                            InferenceMode.ONLY_ON_DEVICE to "ONLY_ON_DEVICE",
                            InferenceMode.PREFER_IN_CLOUD to "PREFER_CLOUD",
                        ).forEach { (mode, label) ->
                            val selected = selectedMode == mode
                            Box(
                                modifier = Modifier
                                    .clip(CircleShape)
                                    .background(if (selected) AccentGlow.copy(alpha = 0.22f) else SpaceGround)
                                    .border(1.dp, if (selected) AccentGlow else Color.White.copy(alpha = 0.12f), CircleShape)
                                    .clickable { selectedMode = mode }
                                    .padding(horizontal = 10.dp, vertical = 6.dp)
                            ) {
                                Text(label, color = TextPrimary, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(nanoStatus, color = TextSecondary.copy(alpha = 0.8f), fontSize = 11.sp, modifier = Modifier.weight(1f))
                        Spacer(modifier = Modifier.width(8.dp))
                        OutlinedButton(
                            onClick = {
                                scope.launch { nanoStatus = engine.checkAndWarmupGeminiNano() }
                            },
                            shape = CircleShape,
                        ) {
                            Text("Warm Up Nano 4", color = AccentGlow, fontSize = 11.sp)
                        }
                    }
                }

                CardPanel {
                    Text("EVA Suit Vitals & Dosimetry (mGy vs mSv)", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricField("HR (BPM)", hrText, { hrText = it }, Modifier.weight(1f))
                        MetricField("SpO₂ (%)", spo2Text, { spo2Text = it }, Modifier.weight(1f))
                        MetricField("CO₂ (mmHg)", co2Text, { co2Text = it }, Modifier.weight(1f))
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricField("Absorbed (mGy)", mgyText, { mgyText = it }, Modifier.weight(1f))
                        MetricField("Equiv (mSv/d)", msvText, { msvText = it }, Modifier.weight(1f))
                    }

                    Spacer(modifier = Modifier.height(10.dp))
                    Text("Selectable EVA Symptoms", color = AccentGlow, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(modifier = Modifier.height(6.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        symptomOptions.forEach { sym ->
                            val checked = selectedSymptoms.contains(sym)
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(if (checked) AccentGlow.copy(alpha = 0.16f) else SpaceGround)
                                    .border(1.dp, if (checked) AccentGlow else Color.White.copy(alpha = 0.08f), RoundedCornerShape(10.dp))
                                    .clickable {
                                        selectedSymptoms = if (checked) selectedSymptoms - sym else selectedSymptoms + sym
                                    }
                                    .padding(horizontal = 12.dp, vertical = 8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(sym, color = TextPrimary, fontSize = 12.sp)
                                Text(if (checked) "Selected" else "Tap", color = AccentGlow, fontSize = 11.sp)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = {
                            triageBusy = true
                            scope.launch {
                                triageResult = engine.runEvaHybridTriage(
                                    crewId = "ARES-IV-SUCHAI",
                                    crewName = "SuChai",
                                    sol = 184,
                                    heartRateBpm = hrText.toIntOrNull() ?: 104,
                                    spo2Pct = spo2Text.toDoubleOrNull() ?: 96.4,
                                    co2Mmhg = co2Text.toDoubleOrNull() ?: 3.2,
                                    absorbedDoseMgy = mgyText.toDoubleOrNull() ?: 0.52,
                                    equivRateMsvDay = msvText.toDoubleOrNull() ?: 1.28,
                                    symptoms = selectedSymptoms.toList(),
                                    offlineBlackout = offlineBlackout,
                                    preferredMode = selectedMode,
                                )
                                triageBusy = false
                            }
                        },
                        enabled = !triageBusy,
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = CtaFill, contentColor = CtaInk),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            if (triageBusy) "Running Hybrid Inference..." else "Run Hybrid EVA Triage & Sync to Habitat",
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }

                triageResult?.let { res ->
                    CardPanel {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text("Source: ${res.actualSource}", color = AccentGlow, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            Text("${res.latencyMs} ms", color = TextSecondary, fontSize = 12.sp)
                        }
                        if (res.exerciseHoldActive) {
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                "EXERCISE HOLD ACTIVE — Suspend physical EVA exertion immediately",
                                color = StatusCritical,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(res.guidance, color = TextPrimary, fontSize = 13.sp, lineHeight = 19.sp)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            if (res.queuedInFirestore) {
                                if (offlineBlackout) "Queued in Firestore Offline Cache — will auto-sync to Web Console on link restore."
                                else "Synced live to Cloud Firestore (`eva_logs`) & Web Habitat Workstation."
                            } else {
                                "Stored locally on EVA wrist pad (configure Firebase project in Tab 3 to sync to Web)."
                            },
                            color = StatusNormal,
                            fontSize = 11.sp,
                        )
                    }
                }
            } else if (activeTab == 1) {
                // TAB 1: ZERO-EGRESS PRIVATE JOURNAL (ONLY_ON_DEVICE)
                CardPanel {
                    Text("PIN-Protected Crew Reflection (ONLY_ON_DEVICE)", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "Enforces OnDeviceConfig(InferenceMode.ONLY_ON_DEVICE). Raw mental-health entries never transmit to Cloud Gemini or Firestore.",
                        color = TextSecondary.copy(alpha = 0.8f),
                        fontSize = 12.sp,
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedTextField(
                        value = journalText,
                        onValueChange = { journalText = it },
                        minLines = 4,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Private Sol 184 Journal Entry", color = AccentGlow) },
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Button(
                        onClick = {
                            journalBusy = true
                            scope.launch {
                                val (reply, ms) = engine.runPrivateJournalOnDevice("SuChai", 184, journalText)
                                journalReply = "$reply\n(${ms} ms · Zero Network Bytes)"
                                journalBusy = false
                            }
                        },
                        enabled = !journalBusy && journalText.isNotBlank(),
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = CtaFill, contentColor = CtaInk),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            if (journalBusy) "Running Local Gemini Nano 4..." else "Reflect On-Device Only (Zero Cloud Egress)",
                            fontWeight = FontWeight.Bold,
                        )
                    }
                    journalReply?.let { reply ->
                        Spacer(modifier = Modifier.height(10.dp))
                        Text(reply, color = TextPrimary, fontSize = 13.sp, lineHeight = 19.sp)
                    }
                }
            } else {
                // TAB 2: STORE-AND-FORWARD SYNC STREAM & RUNTIME FIREBASE CONFIG
                CardPanel {
                    Text("Firestore Store-and-Forward & Remote Config", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text("Active Project: $projectLabel", color = AccentGlow, fontSize = 12.sp)
                    Text(
                        "Remote Config Thresholds: CO₂ ${engine.co2WarnThresholdMmhg} mmHg · Rad ${engine.radWarnThresholdMsv} mSv",
                        color = TextSecondary,
                        fontSize = 12.sp,
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    if (syncItems.isEmpty()) {
                        Text(
                            "No cloud sync logs yet — run an EVA triage on Tab 1 or connect your shared Firebase project below.",
                            color = TextSecondary.copy(alpha = 0.75f),
                            fontSize = 12.sp,
                        )
                    } else {
                        syncItems.forEach { item ->
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(SpaceGround)
                                    .padding(10.dp)
                            ) {
                                Text(
                                    "${item.sourcePlatform} · Sol ${item.sol} · ${if (item.pendingCloudSync) "QUEUED OFFLINE" else "SYNCED"}",
                                    color = if (item.pendingCloudSync) StatusWarning else StatusNormal,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                )
                                Text(item.summary, color = TextPrimary, fontSize = 12.sp)
                            }
                        }
                    }
                }

                CardPanel {
                    Text("Connect Shared Firebase Project (Web ↔ Android)", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "Drop google-services.json in android/app/ before building OR enter your Firebase project credentials at runtime:",
                        color = TextSecondary.copy(alpha = 0.8f),
                        fontSize = 12.sp,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    MetricField("Firebase projectId", cfgProjectId, { cfgProjectId = it }, Modifier.fillMaxWidth())
                    Spacer(modifier = Modifier.height(6.dp))
                    MetricField("Android App ID (1:...:android:...)", cfgAppId, { cfgAppId = it }, Modifier.fillMaxWidth())
                    Spacer(modifier = Modifier.height(6.dp))
                    MetricField("Web/Android API Key (AIza...)", cfgApiKey, { cfgApiKey = it }, Modifier.fillMaxWidth())
                    Spacer(modifier = Modifier.height(10.dp))
                    Button(
                        onClick = {
                            engine.saveRuntimeFirebaseConfig(
                                RuntimeFirebaseConfig(
                                    projectId = cfgProjectId,
                                    applicationId = cfgAppId,
                                    apiKey = cfgApiKey,
                                )
                            ) { items -> syncItems = items }
                            projectLabel = engine.activeProjectId
                            cfgNotice = "Connected to Firebase project $projectLabel with App Check Debug Provider & Firestore Offline Cache."
                        },
                        enabled = cfgProjectId.isNotBlank() && cfgAppId.isNotBlank() && cfgApiKey.isNotBlank(),
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = CtaFill, contentColor = CtaInk),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("Save & Connect Firebase", fontWeight = FontWeight.Bold)
                    }
                    cfgNotice?.let {
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(it, color = StatusNormal, fontSize = 11.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun CardPanel(content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(SurfacePanel)
            .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(16.dp))
            .padding(16.dp),
        content = content,
    )
}

@Composable
private fun MetricField(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        singleLine = true,
        label = { Text(label, fontSize = 11.sp, color = TextSecondary) },
        modifier = modifier,
    )
}

