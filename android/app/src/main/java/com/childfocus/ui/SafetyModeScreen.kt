package com.childfocus.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.childfocus.viewmodel.ClassifyState
import com.childfocus.viewmodel.SafetyViewModel

/**
 * SafetyModeScreen
 *
 * Shown when Safety Mode is ON.
 * Displays live monitoring status as ChildFocusAccessibilityService
 * automatically detects and classifies YouTube videos.
 *
 * Per thesis Figure 3: the user never pastes a URL —
 * the video_id is detected automatically from the YouTube player event.
 *
 * States:
 *   Idle      → "Waiting for video…"
 *   Analyzing → spinner + video ID
 *   Allowed   → green chip (Educational / Neutral)
 *   Blocked   → fullscreen red overlay with dismiss button
 *   Error     → yellow warning chip
 */
@Composable
fun SafetyModeScreen(viewModel: SafetyViewModel) {
    val state by viewModel.classifyState.collectAsState()

    Box(modifier = Modifier.fillMaxSize()) {

        // ── Main monitoring screen ──────────────────────────────────────────
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            // Shield icon
            Text("🛡️", fontSize = 56.sp)

            Spacer(Modifier.height(16.dp))

            Text(
                text       = "Safety Mode Active",
                fontSize   = 24.sp,
                fontWeight = FontWeight.Bold,
                color      = MaterialTheme.colorScheme.primary,
            )

            Spacer(Modifier.height(8.dp))

            Text(
                text      = "ChildFocus is monitoring YouTube automatically.\nOpen YouTube to start watching.",
                fontSize  = 14.sp,
                color     = Color.Gray,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(32.dp))

            // ── Status card ───────────────────────────────────────────────
            when (val s = state) {
                is ClassifyState.Idle -> {
                    StatusChip(
                        text  = "⏳  Waiting for video…",
                        color = Color.Gray,
                    )
                }

                is ClassifyState.Analyzing -> {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(
                            modifier  = Modifier.size(32.dp),
                            strokeWidth = 3.dp,
                        )
                        Spacer(Modifier.height(8.dp))
                        StatusChip(
                            text  = "🔍  Analyzing  ${s.videoId}",
                            color = Color(0xFFFFA000),
                        )
                    }
                }

                is ClassifyState.Allowed -> {
                    val emoji = if (s.label == "Educational") "✅" else "🟡"
                    StatusChip(
                        text  = "$emoji  ${s.label}  •  %.3f${if (s.cached) "  (cached)" else ""}".format(s.score),
                        color = if (s.label == "Educational") Color(0xFF388E3C) else Color(0xFFF57C00),
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text     = "Video ID: ${s.videoId}",
                        fontSize = 11.sp,
                        color    = Color.Gray,
                    )
                }

                is ClassifyState.Error -> {
                    StatusChip(
                        text  = "⚠️  Classification failed — check Flask server",
                        color = Color(0xFFD32F2F),
                    )
                }

                // Blocked state is handled below as a fullscreen overlay
                is ClassifyState.Blocked -> {
                    StatusChip(
                        text  = "🚫  Overstimulating content detected",
                        color = Color(0xFFD32F2F),
                    )
                }
            }

            Spacer(Modifier.height(40.dp))

            // ── Divider + info ────────────────────────────────────────────
            Divider(color = Color.LightGray)
            Spacer(Modifier.height(16.dp))

            Text(
                text      = "How it works",
                fontSize  = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            InfoRow("🎬", "Open YouTube and play any video")
            InfoRow("🔍", "ChildFocus detects the video automatically")
            InfoRow("🤖", "AI scores the content (FCR + CSV + ATT + NB)")
            InfoRow("🚫", "Overstimulating videos are blocked instantly")
            InfoRow("⚡", "Already-seen videos load from cache (<1s)")

            Spacer(Modifier.height(32.dp))

            // ── Turn off button ───────────────────────────────────────────
            OutlinedButton(
                onClick  = { viewModel.toggleSafetyMode() },
                modifier = Modifier.fillMaxWidth(),
                border   = BorderStroke(1.dp, MaterialTheme.colorScheme.error),
            ) {
                Text(
                    text  = "Turn Off Safety Mode",
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }

        // ── Blocked overlay (fullscreen — sits on top of everything) ───────
        val blocked = state as? ClassifyState.Blocked
        if (blocked != null) {
            Box(
                modifier          = Modifier
                    .fillMaxSize()
                    .background(Color(0xEE000000)),
                contentAlignment  = Alignment.Center,
            ) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth(0.88f)
                        .wrapContentHeight(),
                    colors   = CardDefaults.cardColors(
                        containerColor = Color(0xFFB71C1C),
                    ),
                    elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
                ) {
                    Column(
                        modifier              = Modifier.padding(28.dp),
                        horizontalAlignment   = Alignment.CenterHorizontally,
                    ) {
                        Text("🚫", fontSize = 52.sp)

                        Spacer(Modifier.height(12.dp))

                        Text(
                            text       = "Content Blocked",
                            fontSize   = 22.sp,
                            fontWeight = FontWeight.Bold,
                            color      = Color.White,
                        )

                        Spacer(Modifier.height(8.dp))

                        Text(
                            text      = "This video was classified as Overstimulating\nand has been blocked to protect the child.",
                            fontSize  = 14.sp,
                            color     = Color.White.copy(alpha = 0.85f),
                            textAlign = TextAlign.Center,
                        )

                        Spacer(Modifier.height(16.dp))

                        // Score breakdown
                        Surface(
                            color  = Color.White.copy(alpha = 0.15f),
                            shape  = MaterialTheme.shapes.small,
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                BlockedScoreRow("Video ID",     blocked.videoId)
                                BlockedScoreRow("OIR Score",    "%.3f".format(blocked.score))
                                BlockedScoreRow("Label",        blocked.label)
                                BlockedScoreRow("Source",       if (blocked.cached) "Cache" else "Live analysis")
                            }
                        }

                        Spacer(Modifier.height(20.dp))

                        // Dismiss — parent override
                        Button(
                            onClick = { viewModel.dismissBlock() },
                            colors  = ButtonDefaults.buttonColors(
                                containerColor = Color.White,
                            ),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(
                                text  = "Dismiss (Parent Override)",
                                color = Color(0xFFB71C1C),
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
        }
    }
}

// ── Small composable helpers ──────────────────────────────────────────────────

@Composable
private fun StatusChip(text: String, color: Color) {
    Surface(
        shape  = MaterialTheme.shapes.medium,
        color  = color.copy(alpha = 0.10f),
        border = BorderStroke(1.dp, color),
    ) {
        Text(
            text     = text,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            color    = color,
            fontSize = 13.sp,
        )
    }
}

@Composable
private fun InfoRow(emoji: String, text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(emoji, fontSize = 16.sp)
        Spacer(Modifier.width(10.dp))
        Text(text, fontSize = 13.sp, color = Color.DarkGray)
    }
}

@Composable
private fun BlockedScoreRow(label: String, value: String) {
    Row(
        modifier              = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, fontSize = 12.sp, color = Color.White.copy(alpha = 0.7f))
        Text(value, fontSize = 12.sp, color = Color.White, fontWeight = FontWeight.Medium)
    }
}
