package com.childfocus.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

/**
 * ChildFocusAccessibilityService
 *
 * Monitors the YouTube app and automatically detects when a new video
 * is being watched. When detected it sends the video_id to the Flask
 * backend for full OIR classification.
 *
 * Per thesis Figure 3 (Hybrid Algorithm Flowchart):
 *   "Detect video_id (page DOM / player event)"
 *
 * How to enable:
 *   Android Settings → Accessibility → ChildFocus → Toggle ON
 *
 * NOTE: On a physical device, change BASE_URL from 10.0.2.2 to your
 *       PC's local IP address (e.g. 192.168.1.x).
 *       On emulator, 10.0.2.2 maps to the host machine's localhost.
 */
class ChildFocusAccessibilityService : AccessibilityService() {

    // ── Backend URL ────────────────────────────────────────────────────────────
    // Emulator  → 10.0.2.2:5000  (host machine localhost)
    // Real device → change to your PC's IP e.g. 192.168.1.100:5000
    private val BASE_URL = "http://10.0.2.2:5000"

    // ── State ──────────────────────────────────────────────────────────────────
    private val scope  = CoroutineScope(Dispatchers.IO)
    private var lastId = ""                     // avoid re-classifying same video

    // ── HTTP client (90s read timeout — full analysis takes ~15-20s) ──────────
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    // ── Regex: extract 11-char video ID from any YouTube URL format ───────────
    private val VIDEO_ID_PATTERN: Pattern = Pattern.compile(
        "(?:v=|youtu\\.be/|/shorts/)([a-zA-Z0-9_-]{11})"
    )

    // ── Lifecycle ──────────────────────────────────────────────────────────────
    override fun onServiceConnected() {
        serviceInfo = AccessibilityServiceInfo().apply {
            eventTypes   = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                           AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            packageNames = arrayOf("com.google.android.youtube")
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags        = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        }
        println("[CF_SERVICE] ✓ Connected — monitoring YouTube")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Collect all text nodes from the event
        val allText = buildString {
            event?.text?.forEach { append(it).append(" ") }
            event?.source?.let { node ->
                // Also check the URL bar content if accessible
                for (i in 0 until node.childCount) {
                    node.getChild(i)?.text?.let { append(it).append(" ") }
                }
            }
        }

        val videoId = extractVideoId(allText) ?: return

        // Skip if we already processed this video
        if (videoId == lastId) return
        lastId = videoId

        println("[CF_SERVICE] ✓ New video detected: $videoId")

        // Broadcast "analyzing" state to UI immediately
        sendBroadcast(Intent("com.childfocus.CLASSIFICATION_RESULT").apply {
            putExtra("video_id",  videoId)
            putExtra("oir_label", "Analyzing")
            putExtra("score_final", 0.5f)
            putExtra("cached",    false)
        })

        // Run classification on IO thread (never block accessibility thread)
        scope.launch { classifyVideo(videoId) }
    }

    override fun onInterrupt() {
        println("[CF_SERVICE] Interrupted")
    }

    // ── Helpers ────────────────────────────────────────────────────────────────
    private fun extractVideoId(text: String): String? {
        val matcher = VIDEO_ID_PATTERN.matcher(text)
        return if (matcher.find()) matcher.group(1) else null
    }

    private fun classifyVideo(videoId: String) {
        try {
            println("[CF_SERVICE] Classifying: $videoId")

            val body = JSONObject().apply {
                put("video_url",     "https://www.youtube.com/watch?v=$videoId")
                put("thumbnail_url", "https://i.ytimg.com/vi/$videoId/hqdefault.jpg")
            }.toString().toRequestBody("application/json".toMediaType())

            val request = Request.Builder()
                .url("$BASE_URL/classify_full")
                .post(body)
                .build()

            val response = http.newCall(request).execute()

            if (!response.isSuccessful) {
                println("[CF_SERVICE] ✗ HTTP ${response.code} for $videoId")
                broadcastError(videoId)
                return
            }

            val json     = JSONObject(response.body?.string() ?: return)
            val label    = json.optString("oir_label",   json.optString("label", "Neutral"))
            val score    = json.optDouble("final_score", 0.5).toFloat()
            val cached   = json.optBoolean("cached", false)
            val title    = json.optString("video_title", "")

            println("[CF_SERVICE] ✓ $videoId → $label ($score) cached=$cached")

            // Broadcast result → SafetyViewModel → SafetyModeScreen
            sendBroadcast(Intent("com.childfocus.CLASSIFICATION_RESULT").apply {
                putExtra("video_id",    videoId)
                putExtra("video_title", title)
                putExtra("oir_label",   label)
                putExtra("score_final", score)
                putExtra("cached",      cached)
            })

        } catch (e: Exception) {
            println("[CF_SERVICE] ✗ Error classifying $videoId: ${e.message}")
            broadcastError(videoId)
        }
    }

    private fun broadcastError(videoId: String) {
        sendBroadcast(Intent("com.childfocus.CLASSIFICATION_RESULT").apply {
            putExtra("video_id",    videoId)
            putExtra("oir_label",   "Error")
            putExtra("score_final", 0.5f)
            putExtra("cached",      false)
        })
    }
}
