package com.childfocus

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import com.childfocus.ui.LandingScreen
import com.childfocus.viewmodel.SafetyViewModel

class MainActivity : ComponentActivity() {

    private val safetyViewModel: SafetyViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface {
                    LandingScreen(viewModel = safetyViewModel)
                }
            }
        }
    }
}
