
package com.childfocus.ui

import android.content.Intent
import android.provider.Settings
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.childfocus.viewmodel.SafetyViewModel

/**
 * LandingScreen
 *
 * Entry point of the app.
 *   - Safety Mode OFF → HomeContent (landing page + setup banner if needed)
 *   - Safety Mode ON  → SafetyModeScreen (live monitoring)
 */
@Composable
fun LandingScreen(viewModel: SafetyViewModel) {
    val safetyModeOn by viewModel.safetyModeOn.collectAsState()

    AnimatedContent(
        targetState  = safetyModeOn,
        transitionSpec = { fadeIn() togetherWith fadeOut() },
        label        = "safety_mode_transition",
    ) { isOn ->
        if (isOn) {
            SafetyModeScreen(viewModel = viewModel)
        } else {
            HomeContent(onEnableSafetyMode = { viewModel.toggleSafetyMode() })
        }
    }
}

@Composable
private fun HomeContent(onEnableSafetyMode: () -> Unit) {
    val context = LocalContext.current

    // ── Check if Accessibility Service is enabled ─────────────────────────────
    // We check once at composition. User must go to Settings to enable it.
    val isAccessibilityEnabled = remember {
        try {
            val setting = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: ""
            // Package name contains "childfocus" (case-insensitive)
            setting.contains("childfocus", ignoreCase = true)
        } catch (e: Exception) {
            false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {

        // ── Accessibility setup banner (shown only if service not enabled) ─────
        if (!isAccessibilityEnabled) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 24.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                ),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text       = "⚙️  One-Time Setup Required",
                        fontWeight = FontWeight.Bold,
                        fontSize   = 14.sp,
                        color      = MaterialTheme.colorScheme.error,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text     = "Enable ChildFocus in Accessibility Settings so it can automatically monitor YouTube and classify videos without any manual input.",
                        fontSize = 13.sp,
                        color    = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = {
                            context.startActivity(
                                Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                            )
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error,
                        ),
                    ) {
                        Text("Open Accessibility Settings")
                    }
                }
            }
        }

        // ── Branding ──────────────────────────────────────────────────────────
        Text(
            text       = "ChildFocus",
            fontSize   = 32.sp,
            fontWeight = FontWeight.Bold,
            color      = MaterialTheme.colorScheme.primary,
        )

        Spacer(Modifier.height(8.dp))

        Text(
            text      = "A CHILD'S FOCUS, IN SAFE HANDS.",
            fontSize  = 12.sp,
            color     = Color.Gray,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(40.dp))

        // ── Headline ──────────────────────────────────────────────────────────
        Text(
            text       = "Protect what matters most.",
            fontSize   = 18.sp,
            fontWeight = FontWeight.Medium,
            textAlign  = TextAlign.Center,
        )

        Spacer(Modifier.height(12.dp))

        Text(
            text      = "AI-powered analysis that automatically detects\noverstimulating video content for children.",
            fontSize  = 14.sp,
            color     = Color.Gray,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(40.dp))

        // ── Turn On button ────────────────────────────────────────────────────
        Button(
            onClick  = onEnableSafetyMode,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.primary,
            ),
        ) {
            Text(
                text       = "TURN ON SAFETY MODE",
                fontWeight = FontWeight.Bold,
                fontSize   = 15.sp,
            )
        }

        Spacer(Modifier.height(24.dp))

        // ── Feature chips ─────────────────────────────────────────────────────
        Row(
            modifier              = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            FeatureChip("⏱ Screen-time")
            FeatureChip("🌐 Web Blocking")
            FeatureChip("🚫 Content Filter")
        }
    }
}

@Composable
fun FeatureChip(label: String) {
    Surface(
        shape = MaterialTheme.shapes.small,
        color = MaterialTheme.colorScheme.secondaryContainer,
    ) {
        Text(
            text     = label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            fontSize = 12.sp,
        )
    }
}
