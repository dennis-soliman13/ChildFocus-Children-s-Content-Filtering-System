package com.childfocus.viewmodel

import android.app.Application
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.lifecycle.AndroidViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * ClassifyState
 *
 * Represents every possible state the UI can be in
 * after a video is detected and classified.
 */
sealed class ClassifyState {
    /** No video detected yet, or safety mode just turned on */
    object Idle : ClassifyState()

    /** Video detected, waiting for backend response */
    data class Analyzing(val videoId: String) : ClassifyState()

    /** Backend returned Educational or Neutral → allow playback */
    data class Allowed(
        val videoId: String,
        val label:   String,
        val score:   Float,
        val cached:  Boolean = false,
    ) : ClassifyState()

    /** Backend returned Overstimulating → block/blur screen */
    data class Blocked(
        val videoId: String,
        val label:   String,
        val score:   Float,
        val cached:  Boolean = false,
    ) : ClassifyState()

    /** Classification failed (network error, backend down, etc.) */
    data class Error(val videoId: String) : ClassifyState()
}

/**
 * SafetyViewModel
 *
 * Manages:
 *   - Safety Mode toggle (ON/OFF)
 *   - Receiving classification results from ChildFocusAccessibilityService
 *     via LocalBroadcast
 *   - Exposing ClassifyState to the UI layer (SafetyModeScreen)
 */
class SafetyViewModel(application: Application) : AndroidViewModel(application) {

    // ── Safety Mode toggle ─────────────────────────────────────────────────────
    private val _safetyModeOn  = MutableStateFlow(false)
    val safetyModeOn: StateFlow<Boolean> = _safetyModeOn

    // ── Classification state ───────────────────────────────────────────────────
    private val _classifyState = MutableStateFlow<ClassifyState>(ClassifyState.Idle)
    val classifyState: StateFlow<ClassifyState> = _classifyState

    // ── BroadcastReceiver: listens to ChildFocusAccessibilityService ───────────
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context?, intent: Intent?) {
            val videoId = intent?.getStringExtra("video_id")    ?: return
            val label   = intent.getStringExtra("oir_label")    ?: return
            val score   = intent.getFloatExtra("score_final", 0.5f)
            val cached  = intent.getBooleanExtra("cached", false)

            _classifyState.value = when (label) {
                "Analyzing" -> ClassifyState.Analyzing(videoId)
                "Overstimulating" -> ClassifyState.Blocked(videoId, label, score, cached)
                "Error"     -> ClassifyState.Error(videoId)
                else        -> ClassifyState.Allowed(videoId, label, score, cached)
            }
        }
    }

    init {
        // Register receiver — scoped to this app only (NOT_EXPORTED = safe)
        val filter = IntentFilter("com.childfocus.CLASSIFICATION_RESULT")
        application.registerReceiver(
            receiver,
            filter,
            Context.RECEIVER_NOT_EXPORTED,
        )
    }

    // ── Public actions ─────────────────────────────────────────────────────────

    fun toggleSafetyMode() {
        _safetyModeOn.value = !_safetyModeOn.value
        // Reset classification state when turning off
        if (!_safetyModeOn.value) {
            _classifyState.value = ClassifyState.Idle
        }
    }

    /** Called when the parent taps "Dismiss" on the block overlay */
    fun dismissBlock() {
        _classifyState.value = ClassifyState.Idle
    }

    override fun onCleared() {
        super.onCleared()
        getApplication<Application>().unregisterReceiver(receiver)
    }
}
