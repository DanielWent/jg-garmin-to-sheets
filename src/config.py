from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import date

# =========================================================
# 1. DATA CLASS (Structure to hold fetched Garmin data)
# =========================================================

@dataclass
class GarminMetrics:
    date: Optional[date] = None
    # User Profile
    user_name: Optional[str] = None
    user_age: Optional[int] = None
    user_gender: Optional[str] = None
    max_hr_hunt: Optional[int] = None
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
    visceral_fat: Optional[float] = None
    # Stress
    average_stress: Optional[Any] = None
    # BP
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    # Activity Summary
    active_calories: Optional[Any] = None
    resting_calories: Optional[Any] = None
    total_calories: Optional[Any] = None
    intensity_minutes: Optional[Any] = None
    steps: Optional[Any] = None
    floors_climbed: Optional[Any] = None
    resting_heart_rate: Optional[int] = None
    # Training
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    seven_day_load: Optional[int] = None
    lactate_threshold_bpm: Optional[int] = None
    lactate_threshold_pace: Optional[str] = None
    training_status: Optional[str] = None
    training_readiness: Optional[Any] = None
    training_load_focus: Optional[str] = None
    # Body Battery
    body_battery_max: Optional[int] = None
    body_battery_min: Optional[Any] = None
    body_battery_charged: Optional[Any] = None
    body_battery_drain: Optional[Any] = None
    # Activities
    activities: List[Any] = field(default_factory=list)

# =========================================================
# 2. HEADER LISTS
# =========================================================

GENERAL_SUMMARY_HEADERS = [
    "Date", "User Name", "User Age", "User Gender", "VO2 Max (ml/kg/min)",
    "Lactate Threshold Heart Rate (bpm)", "Lactate Threshold Pace (min/km)",
    "Sleep Score", "Sleep Start Time", "Sleep End Time", "Deep Sleep (min)",
    "Light Sleep (min)", "REM Sleep (min)", "Awake Time (min)", "Sleep Length (min)",
    "Sleep Need (min)", "Overnight Breathing Rate (breaths per minute)",
    "Overnight Pulse Ox (0-100%)", "Avg Stress Score", 
    "Morning Training Readiness (0-100)", "Training Load Focus",
    "Daily Min Body Battery (0-100)", "Daily Max Body Battery (0-100)",
    "Body Battery Charged", "Body Battery Drain", "Daily Steps",
    "Daily Floors Climbed", "Daily Intensity Minutes", "Resting Calories (kcal)",
    "Active Calories (kcal)", "Total Calories (kcal)", "Systolic Blood Pressure (mmHg)",
    "Diastolic Blood Pressure (mmHg)", "Garmin Training Load (7 Day Sum)",
    "Overnight Resting HR (bpm)", "Overnight HRV (ms)", "Garmin HRV Status",
    "Garmin Training Status", "Physiological Max Heart Rate (bpm)"
]

SLEEP_HEADERS = ["Date", "Sleep Score", "Sleep Length (mins)", "Sleep Need (mins)", "Sleep Start Time", "Sleep End Time", "Deep Sleep (min)", "Light Sleep (min)", "REM Sleep (min)", "Awake Time (min)", "Garmin Overnight HRV (ms)", "Garmin HRV Status", "Overnight Resting Heart Rate (bpm)"]
BODY_COMP_HEADERS = ["Date", "Weight (kg)", "BMI", "Body Fat (%)", "Skeletal Muscle Mass (kg)", "Bone Mass (kg)", "Body Water (%)", "Visceral Fat Rating"]
STRESS_HEADERS = ["Date", "Average Stress", "Today's Minimum Body Battery", "Today's Maximum Body Battery", "Body Battery Charged", "Body Battery Drain", "Systolic Blood Pressure (mmHg)", "Diastolic Blood Pressure (mmHg)"]
BP_HEADERS = ["Date", "Systolic (mmHg)", "Diastolic (mmHg)"]
ACTIVITY_SUMMARY_HEADERS = ["Date", "Intensity Minutes", "Steps", "Floors Climbed", "Total Calories (kcal)", "VO2 Max (ml/kg/min)", "Lactate Threshold Heart Rate (bpm)", "Lactate Threshold Pace (min / km)", "Garmin Training Load (7-Day Sum)"]
ACTIVITY_HEADERS = ["Activity ID", "Date (YYYY-MM-DD)", "Start Time (HH:MM)", "Activity Type", "Distance (km)", "Duration (min)", "Avg Pace (min/km)", "Average Grade Adjusted Pace (min/km)", "Avg HR (bpm)", "Max HR (bpm)", "Total Ascent (m)", "Total Descent (m)", "Aerobic TE (0-5.0)", "Anaerobic TE (0-5.0)", "Avg Power (Watts)", "Garmin Training Effect Label", "HR Zone 1 (min)", "HR Zone 2 (min)", "HR Zone 3 (min)", "HR Zone 4 (min)", "HR Zone 5 (min)"]

HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date", "User Name": "user_name", "User Age": "user_age", "User Gender": "user_gender",
    "Physiological Max Heart Rate (bpm)": "max_hr_hunt", "Sleep Score": "sleep_score",
    "Sleep Length (min)": "sleep_length", "Sleep Length (mins)": "sleep_length",
    "Sleep Need (min)": "sleep_need", "Sleep Need (mins)": "sleep_need",
    "Overnight Breathing Rate (breaths per minute)": "overnight_respiration",
    "Overnight Pulse Ox (0-100%)": "overnight_pulse_ox", "Sleep Start Time": "sleep_start_time",
    "Sleep End Time": "sleep_end_time", "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light", "REM Sleep (min)": "sleep_rem", "Awake Time (min)": "sleep_awake",
    "Garmin Overnight HRV (ms)": "overnight_hrv", "Overnight HRV (ms)": "overnight_hrv",
    "Garmin HRV Status": "hrv_status", "Overnight Resting HR (bpm)": "resting_heart_rate",
    "Overnight Resting Heart Rate (bpm)": "resting_heart_rate", "Weight (kg)": "weight",
    "BMI": "bmi", "Body Fat (%)": "body_fat", "Skeletal Muscle Mass (kg)": "skeletal_muscle",
    "Bone Mass (kg)": "bone_mass", "Body Water (%)": "body_water", "Visceral Fat Rating": "visceral_fat",
    "Avg Stress Score": "average_stress", "Average Stress": "average_stress",
    "Daily Min Body Battery (0-100)": "body_battery_min", "Today's Minimum Body Battery": "body_battery_min",
    "Daily Max Body Battery (0-100)": "body_battery_max", "Today's Maximum Body Battery": "body_battery_max",
    "Body Battery Charged": "body_battery_charged", "Body Battery Drain": "body_battery_drain",
    "Morning Training Readiness (0-100)": "training_readiness", "Training Load Focus": "training_load_focus",
    "Systolic Blood Pressure (mmHg)": "blood_pressure_systolic", "Diastolic Blood Pressure (mmHg)": "blood_pressure_diastolic",
    "Systolic (mmHg)": "blood_pressure_systolic", "Diastolic (mmHg)": "blood_pressure_diastolic",
    "Active Calories (kcal)": "active_calories", "Resting Calories (kcal)": "resting_calories",
    "Total Calories (kcal)": "total_calories", "Daily Intensity Minutes": "intensity_minutes",
    "Intensity Minutes": "intensity_minutes", "Daily Steps": "steps", "Steps": "steps",
    "Daily Floors Climbed": "floors_climbed", "Floors Climbed": "floors_climbed",
    "VO2 Max (ml/kg/min)": "vo2max_running", "Lactate Threshold Heart Rate (bpm)": "lactate_threshold_bpm",
    "Lactate Threshold Pace (min/km)": "lactate_threshold_pace", "Garmin Training Load (7 Day Sum)": "seven_day_load",
    "Garmin Training Status": "training_status"
}
