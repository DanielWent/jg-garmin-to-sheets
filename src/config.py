from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import date

# =========================================================
# 1. DATA CLASS (Structure to hold fetched Garmin data)
# =========================================================

@dataclass
class GarminMetrics:
    date: Optional[date] = None
    # Sleep
    sleep_score: Optional[int] = None
    sleep_length: Optional[float] = None
    sleep_start_time: Optional[str] = None
    sleep_end_time: Optional[str] = None
    sleep_deep: Optional[float] = None
    sleep_light: Optional[float] = None
    sleep_rem: Optional[float] = None
    sleep_awake: Optional[float] = None
    sleep_need: Optional[int] = None
    sleep_efficiency: Optional[int] = None
    overnight_respiration: Optional[float] = None
    overnight_pulse_ox: Optional[float] = None
    # HRV
    overnight_hrv: Optional[float] = None
    hrv_status: Optional[str] = None
    # Body
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    skeletal_muscle: Optional[float] = None
    bone_mass: Optional[float] = None
    body_water: Optional[float] = None
    # Stress
    average_stress: Optional[int] = None
    rest_stress_duration: Optional[int] = None
    low_stress_duration: Optional[int] = None
    medium_stress_duration: Optional[int] = None
    high_stress_duration: Optional[int] = None
    # BP
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    # Activity Summary
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    intensity_minutes: Optional[int] = None
    steps: Optional[int] = None
    floors_climbed: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    # Training / VO2 / Lactate
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    seven_day_load: Optional[int] = None
    lactate_threshold_bpm: Optional[int] = None
    lactate_threshold_pace: Optional[str] = None
    training_status: Optional[str] = None
    # Body Battery
    body_battery_max: Optional[int] = None
    body_battery_min: Optional[int] = None
    # Activities
    activities: List[Any] = field(default_factory=list)

# =========================================================
# 2. HEADER LISTS (Columns for the Google Sheets)
# =========================================================

# Master List (Fallback for CSV or main sheets)
HEADERS = [
    "Date",
    "Sleep Score",
    "Sleep Length (mins)",
    "Garmin Overnight HRV (ms)",
    "Garmin HRV Status",
    "Overnight Resting Heart Rate (bpm)",
    "Body Battery Max",
    "Body Battery Min",
    "Training Status",
    "VO2 Max Running",
    "Steps",
    "Active Calories",
    "Resting Calories",
    "Weight (kg)"
]

SLEEP_HEADERS = [
    "Date",
    "Sleep Score",
    "Sleep Length (mins)",
    "Sleep Need (mins)",
    "Sleep Start Time",
    "Sleep End Time",
    "Deep Sleep (min)",
    "Light Sleep (min)",
    "REM Sleep (min)",
    "Awake Time (min)",
    "Garmin Overnight HRV (ms)",          
    "Garmin HRV Status",                  
    "Overnight Resting Heart Rate (bpm)"  
]

BODY_COMP_HEADERS = [
    "Date",
    "Weight (kg)",
    "BMI",
    "Body Fat (%)"
]

STRESS_HEADERS = [
    "Date",
    "Average Stress",
    "Rest Stress Duration (min)",
    "Low Stress Duration (min)",
    "Medium Stress Duration (min)",
    "High Stress Duration (min)",
    "Stress Score"
]

BP_HEADERS = [
    "Date",
    "Systolic (mmHg)",
    "Diastolic (mmHg)"
]

ACTIVITY_SUMMARY_HEADERS = [
    "Date",
    "Active Calories",
    "Resting Calories",
    "Intensity Minutes",
    "Steps",
    "Floors Climbed"
]

ACTIVITY_HEADERS = [
    "Activity ID",
    "Date (YYYY-MM-DD)",
    "Start Time (HH:MM)",
    "Activity Type",
    "Distance (km)",
    "Duration (min)",
    "Avg Pace (min/km)",
    "Avg HR (bpm)",
    "Max HR (bpm)",
    "Elevation Gain (m)",
    "Aerobic TE (0-5.0)",
    "Anaerobic TE (0-5.0)",
    "Avg Power (Watts)",
    "Garmin Training Effect",
    "HR Zone 1 (min)",
    "HR Zone 2 (min)",
    "HR Zone 3 (min)",
    "HR Zone 4 (min)",
    "HR Zone 5 (min)"
]

# =========================================================
# 3. DATA MAPPING (Connects Headers to Garmin Data)
# =========================================================

HEADER_TO_ATTRIBUTE_MAP = {
    # --- Sleep Tab ---
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Sleep Length (mins)": "sleep_length",
    "Sleep Need (mins)": "sleep_need",
    "Sleep Start Time": "sleep_start_time",
    "Sleep End Time": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake Time (min)": "sleep_awake",
    "Garmin Overnight HRV (ms)": "overnight_hrv",
    "Garmin HRV Status": "hrv_status",
    "Overnight Resting Heart Rate (bpm)": "resting_heart_rate",

    # --- Body Comp Tab ---
    "Weight (kg)": "weight",
    "BMI": "bmi",
    "Body Fat (%)": "body_fat",

    # --- Stress Tab ---
    "Average Stress": "average_stress",
    "Rest Stress Duration (min)": "rest_stress_duration",
    "Low Stress Duration (min)": "low_stress_duration",
    "Medium Stress Duration (min)": "medium_stress_duration",
    "High Stress Duration (min)": "high_stress_duration",
    "Stress Score": "average_stress", 

    # --- Blood Pressure Tab ---
    "Systolic (mmHg)": "blood_pressure_systolic",
    "Diastolic (mmHg)": "blood_pressure_diastolic",

    # --- Activity Summary Tab ---
    "Active Calories": "active_calories",
    "Resting Calories": "resting_calories",
    "Intensity Minutes": "intensity_minutes",
    "Steps": "steps",
    "Floors Climbed": "floors_climbed",
    
    # --- Headers for Master List (CSV/General) ---
    "Body Battery Max": "body_battery_max",
    "Body Battery Min": "body_battery_min",
    "Training Status": "training_status",
    "VO2 Max Running": "vo2max_running"
}
