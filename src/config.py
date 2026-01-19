from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Any, Dict

# -----------------------------------------------------------------------------
# 1. GOOGLE SHEETS HEADERS
# -----------------------------------------------------------------------------

# Main "Daily Summaries" Sheet
HEADERS = [
    "Date", "Sleep Score", "Sleep Duration (hr)", "Sleep Need (hr)", "Sleep Efficiency (%)",
    "Resting HR", "HRV (ms)", "Stress Avg", "Training Status", "VO2 Max (Run)", "7-Day Load",
    "Steps", "Active Calories", "Weight (kg)", "Body Fat (%)"
]

# Separate "Sleep Logs" Sheet
SLEEP_HEADERS = [
    "Date", "Sleep Score", "Duration (min)", "Start Time", "End Time",
    "Deep (min)", "Light (min)", "REM (min)", "Awake (min)",
    "Restlessness", "Avg Respiration", "Avg SpO2"
]

# Separate "Body Composition" Sheet
BODY_COMP_HEADERS = [
    "Date", "Weight (kg)", "BMI", "Body Fat (%)", "Skeletal Muscle (kg)", 
    "Bone Mass (kg)", "Water (%)"
]

# Separate "Blood Pressure" Sheet
BP_HEADERS = [
    "Date", "Systolic", "Diastolic", "Pulse", "Notes"
]

# Separate "Stress Data" Sheet
# UPDATED: Added Body Battery Max/Min
STRESS_HEADERS = [
    "Date", "Stress Level", "Rest Stress Duration", "Low Stress Duration", 
    "Medium Stress Duration", "High Stress Duration",
    "Body Battery Max", "Body Battery Min"
]

# Separate "List of Tracked Activities" Sheet
# UPDATED: Added Power, Run Dynamics, and HR Zones
ACTIVITY_HEADERS = [
    "Activity ID", "Date", "Time", "Type", "Name", "Distance (km)", "Duration (min)",
    "Avg Pace (min/km)", "Avg HR", "Max HR", "Calories", 
    "Avg Cadence (spm)", "Elevation Gain (m)", "Aerobic TE", "Anaerobic TE",
    "Avg Power", "GCT (ms)", "Vert Osc (cm)", "Stride Len (m)",
    "Zone 1 (min)", "Zone 2 (min)", "Zone 3 (min)", "Zone 4 (min)", "Zone 5 (min)"
]

# For the generic summary tab (if used)
ACTIVITY_SUMMARY_HEADERS = HEADERS

# -----------------------------------------------------------------------------
# 2. INTERNAL DATA MODEL
# -----------------------------------------------------------------------------

# Map headers to attribute names in GarminMetrics
HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Sleep Duration (hr)": "sleep_length_hours",
    "Sleep Need (hr)": "sleep_need_hours",
    "Sleep Efficiency (%)": "sleep_efficiency",
    "Resting HR": "resting_heart_rate",
    "HRV (ms)": "overnight_hrv",
    "Stress Avg": "average_stress",
    "Training Status": "training_status",
    "VO2 Max (Run)": "vo2max_running",
    "7-Day Load": "seven_day_load",
    "Steps": "steps",
    "Active Calories": "active_calories",
    "Weight (kg)": "weight",
    "Body Fat (%)": "body_fat",
    
    # Stress Sheet Mappings
    "Stress Level": "average_stress",
    "Rest Stress Duration": "rest_stress_duration",
    "Low Stress Duration": "low_stress_duration",
    "Medium Stress Duration": "medium_stress_duration",
    "High Stress Duration": "high_stress_duration",
    "Body Battery Max": "body_battery_max",
    "Body Battery Min": "body_battery_min"
}

@dataclass
class GarminMetrics:
    date: date
    
    # Sleep
    sleep_score: Optional[int] = None
    sleep_need: Optional[int] = None        # minutes
    sleep_efficiency: Optional[int] = None
    sleep_length: Optional[int] = None      # minutes
    sleep_start_time: Optional[str] = None
    sleep_end_time: Optional[str] = None
    sleep_deep: Optional[int] = None        # minutes
    sleep_light: Optional[int] = None       # minutes
    sleep_rem: Optional[int] = None         # minutes
    sleep_awake: Optional[int] = None       # minutes
    overnight_respiration: Optional[float] = None
    overnight_pulse_ox: Optional[float] = None
    
    # Body / Health
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    
    # Stress & Battery
    average_stress: Optional[int] = None
    rest_stress_duration: Optional[int] = None
    low_stress_duration: Optional[int] = None
    medium_stress_duration: Optional[int] = None
    high_stress_duration: Optional[int] = None
    body_battery_max: Optional[int] = None
    body_battery_min: Optional[int] = None

    # HRV & Training
    overnight_hrv: Optional[int] = None     # ms
    hrv_status: Optional[str] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    seven_day_load: Optional[int] = None
    training_status: Optional[str] = None
    lactate_threshold_bpm: Optional[int] = None
    lactate_threshold_pace: Optional[str] = None

    # Daily Activity
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    intensity_minutes: Optional[int] = None
    steps: Optional[int] = None
    floors_climbed: Optional[float] = None
    
    # List of detailed activities (runs, swims, etc.)
    activities: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def sleep_length_hours(self):
        return round(self.sleep_length / 60, 1) if self.sleep_length else None

    @property
    def sleep_need_hours(self):
        return round(self.sleep_need / 60, 1) if self.sleep_need else None
