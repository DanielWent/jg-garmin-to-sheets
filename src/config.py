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
    # Stress (Typed as Any to allow "NA" or "PENDING")
    average_stress: Optional[Any] = None
    rest_stress_duration: Optional[Any] = None
    low_stress_duration: Optional[Any] = None
    medium_stress_duration: Optional[Any] = None
    high_stress_duration: Optional[Any] = None
    # BP
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    # Activity Summary (Typed as Any to allow "NA" or "PENDING")
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    total_calories: Optional[Any] = None
    intensity_minutes: Optional[Any] = None
    steps: Optional[Any] = None
    floors_climbed: Optional[Any] = None
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
    body_battery_min: Optional[Any] = None
    # Activities
    activities: List[Any] = field(default_factory=list)

# =========================================================
# 2. HEADER LISTS (Columns for the Google Sheets)
# =========================================================

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
    "Total Calories (kcal)",
    "Weight (kg)"
]

GENERAL_SUMMARY_HEADERS = [
    "Date",
    "User Name",
    "User Age",
    "User Gender",
    "VO2 Max (ml/kg/min)",
    "Lactate Threshold Pace (min/km)",
    "Sleep Score",
    "Sleep Start Time",
    "Sleep End Time",
    "Deep Sleep (min)",
    "Light Sleep (min)",
    "REM Sleep (min)",
    "Awake Time (min)",
    "Sleep Length (min)",
    "Sleep Need (min)",
    "Overnight Breathing Rate (breaths per minute)",
    "Avg Stress Score",
    "Rest Stress Duration (min)",
    "Low Stress Duration (min)",
    "Medium Stress Duration (min)",
    "High Stress Duration (min)",
    "Daily Min Body Battery (0-100)",
    "Daily Max Body Battery (0-100)",
    "Daily Steps",
    "Daily Floors Climbed",
    "Daily Intensity Minutes",
    "Total Calories (kcal)",
    "Systolic Blood Pressure (mmHg)",
    "Diastolic Blood Pressure (mmHg)",
    "Garmin Training Load (7 Day Sum)",
    "Overnight Resting HR (bpm)",
    "Overnight HRV (ms)",
    "Garmin HRV Status",
    "Garmin Training Status"
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
    "Body Fat (%)",
    "Skeletal Muscle Mass (kg)",
    "Bone Mass (kg)",
    "Body Water (%)",
    "Visceral Fat Rating"
]

STRESS_HEADERS = [
    "Date",
    "Average Stress",
    "Rest Stress Duration (min)",
    "Low Stress Duration (min)",
    "Medium Stress Duration (min)",
    "High Stress Duration (min)",
    "Today's Minimum Body Battery",
    "Today's Maximum Body Battery",
    "Systolic Blood Pressure (mmHg)", 
    "Diastolic Blood Pressure (mmHg)" 
]

BP_HEADERS = [
    "Date",
    "Systolic (mmHg)", 
    "Diastolic (mmHg)" 
]

ACTIVITY_SUMMARY_HEADERS = [
    "Date",
    "Intensity Minutes",
    "Steps",
    "Floors Climbed",
    "Total Calories (kcal)",
    "VO2 Max (ml/kg/min)",
    "Lactate Threshold Heart Rate (bpm)",
    "Lactate Threshold Pace (min / km)",
    "Garmin Training Load (7-Day Sum)"
]

ACTIVITY_HEADERS = [
    "Activity ID",
    "Date (YYYY-MM-DD)",
    "Start Time (HH:MM)",
    "Activity Type",
    "Distance (km)",
    "Duration (min)",
    "Avg Pace (min/km)",
    "Average Grade Adjusted Pace (min/km)",
    "Avg HR (bpm)",
    "Max HR (bpm)",
    "Total Ascent (m)",
    "Total Descent (m)",
    "Aerobic TE (0-5.0)",
    "Anaerobic TE (0-5.0)",
    "Avg Power (Watts)",
    "Garmin Training Effect Label",
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
    "Date": "date",
    "User Name": "user_name",
    "User Age": "user_age",
    "User Gender": "user_gender",
    
    "Sleep Score": "sleep_score",
    "Sleep Length (mins)": "sleep_length",
    "Sleep Length (min)": "sleep_length",
    "Sleep Need (mins)": "sleep_need",
    "Sleep Need (min)": "sleep_need",
    "Overnight Breathing Rate (breaths per minute)": "overnight_respiration",
    "Sleep Start Time": "sleep_start_time",
    "Sleep End Time": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake Time (min)": "sleep_awake",
    "Garmin Overnight HRV (ms)": "overnight_hrv",
    "Overnight HRV (ms)": "overnight_hrv",
    "Garmin HRV Status": "hrv_status",
    "Overnight Resting Heart Rate (bpm)": "resting_heart_rate",
    "Overnight Resting HR (bpm)": "resting_heart_rate",

    "Weight (kg)": "weight",
    "BMI": "bmi",
    "Body Fat (%)": "body_fat",
    "Skeletal Muscle Mass (kg)": "skeletal_muscle",
    "Bone Mass (kg)": "bone_mass",
    "Body Water (%)": "body_water",
    "Visceral Fat Rating": "visceral_fat",

    "Average Stress": "average_stress",
    "Avg Stress Score": "average_stress",
    "Rest Stress Duration (min)": "rest_stress_duration",
    "Low Stress Duration (min)": "low_stress_duration",
    "Medium Stress Duration (min)": "medium_stress_duration",
    "High Stress Duration (min)": "high_stress_duration",
    "Today's Minimum Body Battery": "body_battery_min",
    "Today's Maximum Body Battery": "body_battery_max",
    "Daily Min Body Battery (0-100)": "body_battery_min",
    "Daily Max Body Battery (0-100)": "body_battery_max",

    # Original Mappings for BP Sheet
    "Systolic (mmHg)": "blood_pressure_systolic",
    "Diastolic (mmHg)": "blood_pressure_diastolic",
    
    # New Mappings for Stress Sheet and General Summary
    "Systolic Blood Pressure (mmHg)": "blood_pressure_systolic",
    "Diastolic Blood Pressure (mmHg)": "blood_pressure_diastolic",

    "Active Calories": "active_calories",
    "Resting Calories": "resting_calories",
    "Total Calories (kcal)": "total_calories",
    "Intensity Minutes": "intensity_minutes",
    "Daily Intensity Minutes": "intensity_minutes",
    "Steps": "steps",
    "Daily Steps": "steps",
    "Floors Climbed": "floors_climbed",
    "Daily Floors Climbed": "floors_climbed",
    "VO2 Max (ml/kg/min)": "vo2max_running",
    "Lactate Threshold Heart Rate (bpm)": "lactate_threshold_bpm",
    "Lactate Threshold Pace (min / km)": "lactate_threshold_pace",
    "Lactate Threshold Pace (min/km)": "lactate_threshold_pace",
    "Garmin Training Load (7-Day Sum)": "seven_day_load",
    "Garmin Training Load (7 Day Sum)": "seven_day_load",
    
    "Body Battery Max": "body_battery_max",
    "Body Battery Min": "body_battery_min",
    "Training Status": "training_status",
    "Garmin Training Status": "training_status",
    "VO2 Max Running": "vo2max_running"
}
