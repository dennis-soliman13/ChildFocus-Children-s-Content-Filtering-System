package com.childfocus.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.childfocus.model.ClassificationResult

/**
 * ResultScreen
 *
 * Detailed view of a classification result.
 * Shows OIR score breakdown, per-segment heuristic scores,
 * NB probabilities, and recommended action.
 */
@Composable
fun ResultScreen(
    result: ClassificationResult,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        // ── Back button ──────────────────────────────────────────────────────
        TextButton(onClick = onBack) {
            Text("← Back")
        }

        Spacer(Modifier.height(8.dp))

        // ── Title ────────────────────────────────────────────────────────────
        Text(
            text       = "Classification Report",
            fontSize   = 22.sp,
            fontWeight = FontWeight.Bold,
        )

        if (result.videoTitle.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text     = result.videoTitle,
                fontSize = 13.sp,
                color    = Color.Gray,
            )
        }

        Spacer(Modifier.height(20.dp))

        // ── OIR Label ────────────────────────────────────────────────────────
        ClassificationResultCard(result = result)

        Spacer(Modifier.height(20.dp))

        // ── Score breakdown ──────────────────────────────────────────────────
        SectionHeader("Score Breakdown")
        InfoCard {
            ScoreRow("Score_NB  (metadata, α=0.4)",  result.scoreNb)
            ScoreRow("Score_H   (heuristic, β=0.6)", result.scoreH)
            Divider(modifier = Modifier.padding(vertical = 6.dp))
            ScoreRow("Score_final (OIR)", result.scoreFinal)
        }

        // ── NB probabilities ─────────────────────────────────────────────────
        result.nbDetails?.let { nb ->
            Spacer(Modifier.height(16.dp))
            SectionHeader("Naïve Bayes Probabilities")
            InfoCard {
                nb.probabilities.entries.sortedByDescending { it.value }.forEach { (label, prob) ->
                    ScoreRow(label, prob)
                }
            }
        }

        // ── Heuristic segments ───────────────────────────────────────────────
        result.hDetails?.let { h ->
            if (h.segments.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                SectionHeader("Heuristic Segments (FCR / CSV / ATT)")
                h.segments.forEachIndexed { i, seg ->
                    Spacer(Modifier.height(8.dp))
                    InfoCard {
                        Text(
                            text       = "Segment ${i + 1} — offset ${seg.offsetSeconds}s",
                            fontWeight = FontWeight.SemiBold,
                            fontSize   = 13.sp,
                        )
                        Spacer(Modifier.height(4.dp))
                        ScoreRow("Frame-Change Rate (FCR)",     seg.fcr)
                        ScoreRow("Color Saturation Var. (CSV)", seg.csv)
                        ScoreRow("Audio Tempo (ATT)",           seg.att)
                        ScoreRow("Segment Score_H",             seg.scoreH)
                    }
                }
            }
        }

        Spacer(Modifier.height(24.dp))
    }
}

// ── ClassificationResultCard ──────────────────────────────────────────────────

@Composable
fun ClassificationResultCard(result: ClassificationResult) {
    val (bgColor, labelColor) = when (result.oirLabel) {
        "Educational"    -> Color(0xFFE8F5E9) to Color(0xFF2E7D32)
        "Overstimulating" -> Color(0xFFFFEBEE) to Color(0xFFC62828)
        else              -> Color(0xFFFFF8E1) to Color(0xFFF57F17)  // Neutral
    }

    val emoji = when (result.oirLabel) {
        "Educational"    -> "✅"
        "Overstimulating" -> "🚫"
        else              -> "⚠️"
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors   = CardDefaults.cardColors(containerColor = bgColor),
    ) {
        Column(
            modifier            = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(text = emoji, fontSize = 40.sp)
            Spacer(Modifier.height(8.dp))
            Text(
                text       = result.oirLabel,
                fontSize   = 20.sp,
                fontWeight = FontWeight.Bold,
                color      = labelColor,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text     = "Final Score: ${String.format("%.3f", result.scoreFinal)}",
                fontSize = 13.sp,
                color    = labelColor.copy(alpha = 0.8f),
            )

        }
    }
}

// ── ScoreRow ──────────────────────────────────────────────────────────────────

@Composable
fun ScoreRow(label: String, value: Float) {
    Row(
        modifier          = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text     = label,
            fontSize = 13.sp,
            color    = Color.DarkGray,
            modifier = Modifier.weight(1f),
        )
        Text(
            text       = String.format("%.4f", value),
            fontSize   = 13.sp,
            fontWeight = FontWeight.Medium,
            color      = Color.Black,
        )
    }
}

// ── SectionHeader ─────────────────────────────────────────────────────────────

@Composable
fun SectionHeader(title: String) {
    Text(
        text       = title,
        fontSize   = 15.sp,
        fontWeight = FontWeight.SemiBold,
        modifier   = Modifier.padding(bottom = 6.dp),
    )
}

// ── InfoCard ──────────────────────────────────────────────────────────────────

@Composable
fun InfoCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier  = Modifier.fillMaxWidth(),
        colors    = CardDefaults.cardColors(containerColor = Color(0xFFF5F5F5)),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            content  = content,
        )
    }
}
