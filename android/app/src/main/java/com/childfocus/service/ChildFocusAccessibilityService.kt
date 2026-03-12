package com.childfocus.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
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

class ChildFocusAccessibilityService : AccessibilityService() {

    private val scope   = CoroutineScope(Dispatchers.IO)
    private var lastTitle = ""

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    // YouTube exposes: "Minimized player <Title> <Title> @Channel ..."
    // The title always appears right after "Minimized player" and is repeated once
    private val TITLE_PATTERN = Pattern.compile(
        "Minimized player\\s+(.+?)\\s+\\1",
        Pattern.DOTALL
    )

    // Also match URL-based video IDs if YouTube ever exposes them
    private val URL_PATTERN = Pattern.compile("(?:v=|youtu\\.be/)([a-zA-Z0-9_-]{11})")

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
        event ?: return

        // Strategy 1: direct URL in event text (rare but handle it)
        val eventText = event.text?.joinToString(" ") ?: ""
        val urlMatch  = URL_PATTERN.matcher(eventText)
        if (urlMatch.find()) {
            val vid = urlMatch.group(1) ?: return
            handleVideoId(vid)
            return
        }

        // Strategy 2: extract title from node tree
        val root    = rootInActiveWindow ?: return
        val allText = collectAllNodeText(root)
        root.recycle()

        // Try URL pattern in full tree first
        val urlInTree = URL_PATTERN.matcher(allText)
        if (urlInTree.find()) {
            handleVideoId(urlInTree.group(1) ?: return)
            return
        }

        // Extract title using "Minimized player <Title> <Title>" pattern
        val titleMatch = TITLE_PATTERN.matcher(allText)
        if (titleMatch.find()) {
            val title = titleMatch.group(1)?.trim() ?: return
            if (title != lastTitle && title.length > 5) {
                lastTitle = title
                println("[CF_SERVICE] ✓ Detected title: $title")
                scope.launch { classifyByTitle(title) }
            }
        }
    }

    private fun handleVideoId(videoId: String) {
        // Convert ID directly to URL and classify
        scope.launch {
            classifyByUrl(
                videoId  = videoId,
                videoUrl = "https://www.youtube.com/watch?v=$videoId",
                thumbUrl = "https://i.ytimg.com/vi/$videoId/hqdefault.jpg"
            )
        }
    }

    private fun collectAllNodeText(node: AccessibilityNodeInfo): String {
        val sb = StringBuilder()
        try {
            node.text?.let               { sb.append(it).append(" ") }
            node.contentDescription?.let { sb.append(it).append(" ") }
            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                sb.append(collectAllNodeText(child))
                child.recycle()
            }
        } catch (_: Exception) { }
        return sb.toString()
    }

    // ── Title-based classification (main path) ────────────────────────────────

    private fun classifyByTitle(title: String) {
        try {
            val body = JSONObject().apply {
                put("title", title)
            }

            val request = Request.Builder()
                .url("http://10.0.2.2:5000/classify_by_title")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()

            val response = http.newCall(request).execute()
            val json     = JSONObject(response.body?.string() ?: return)

            handleClassificationResult(json)

        } catch (e: Exception) {
            println("[CF_SERVICE] ✗ classify_by_title error: ${e.message}")
        }
    }

    // ── Direct URL classification (fallback when video ID is known) ───────────

    private fun classifyByUrl(videoId: String, videoUrl: String, thumbUrl: String) {
        try {
            val body = JSONObject().apply {
                put("video_url",     videoUrl)
                put("thumbnail_url", thumbUrl)
            }

            val request = Request.Builder()
                .url("http://10.0.2.2:5000/classify_full")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()

            val response = http.newCall(request).execute()
            val json     = JSONObject(response.body?.string() ?: return)

            handleClassificationResult(json)

        } catch (e: Exception) {
            println("[CF_SERVICE] ✗ classify_full error: ${e.message}")
        }
    }

    private fun handleClassificationResult(json: JSONObject) {
        val label   = json.optString("oir_label", "Neutral")
        val score   = json.optDouble("score_final", 0.5)
        val cached  = json.optBoolean("cached", false)
        val videoId = json.optString("video_id", "unknown")

        println("[CF_SERVICE] $videoId → $label ($score) cached=$cached")

        val intent = Intent("com.childfocus.CLASSIFICATION_RESULT").apply {
            putExtra("video_id",    videoId)
            putExtra("oir_label",   label)
            putExtra("score_final", score.toFloat())
            putExtra("cached",      cached)
        }
        sendBroadcast(intent)
    }

    override fun onInterrupt() {
        println("[CF_SERVICE] Interrupted")
    }
}
