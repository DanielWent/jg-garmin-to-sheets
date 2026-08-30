from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import date

# =========================================================
# 1. DATA CLASS (Structure to hold fetched Garmin data)
# =========================================================

@dataclass
class GarminMetrics:
    date: Optional[date] = None
    user_name: Optional[str] = None
    user_age: Optional[float] = None
    user_gender: Optional[str] = None
    max_hr_hunt: Optional[int] = None
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
    overnight_hrv: Optional[float] = None
    hrv_status: Optional[str] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    skeletal_muscle: Optional[float] = None
    bone_mass: Optional[float] = None
    body_water: Optional[float] = None
    visceral_fat: Optional[float] = None
    average_stress: Optional[Any] = None
    average_waking_stress: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    total_calories: Optional[Any] = None
    intensity_minutes: Optional[Any] = None
    steps: Optional[Any] = None
    floors_climbed: Optional[Any] = None
    resting_heart_rate: Optional[int] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    vo2_max_percentile: Optional[float] = None
    seven_day_load: Optional[int] = None
    lactate_threshold_bpm: Optional[int] = None
    lactate_threshold_pace: Optional[str] = None
    training_status: Optional[str] = None
    training_load_focus: Optional[str] = None
    training_readiness: Optional[int] = None
    body_battery_max: Optional[Any] = None
    body_battery_min: Optional[Any] = None
    body_battery_charged: Optional[Any] = None
    body_battery_drained: Optional[Any] = None
    total_walking_distance: Optional[float] = None
    total_walking_duration: Optional[float] = None
    total_running_count: Optional[int] = None
    total_running_distance: Optional[float] = None
    total_running_duration: Optional[float] = None
    total_strength_duration: Optional[float] = None
    moderate_intensity_minutes: Optional[Any] = None
    vigorous_intensity_minutes: Optional[Any] = None
    rest_stress_duration: Optional[float] = None
    low_stress_duration: Optional[float] = None
    medium_stress_duration: Optional[float] = None
    high_stress_duration: Optional[float] = None
    anaerobic_training_load: Optional[int] = None
    high_aerobic_training_load: Optional[int] = None
    low_aerobic_training_load: Optional[int] = None
    avg_run_pace: Optional[str] = None
    avg_run_gap_pace: Optional[str] = None
    activities: List[Any] = field(default_factory=list)

# =========================================================
# 2. HEADER LISTS (Columns for the CSVs)
# =========================================================

GENERAL_SUMMARY_HEADERS = [
    "Date (YYYY-MM-DD)",
    "User Name",
    "User Age",
    "User Gender",
    "Physiological Maximum Heart Rate (bpm)",
    "VO2 Max (ml/kg/min)",
    "VO2 Max Percentile (Age-Gender Adjusted)",
    "Lactate Threshold Pace (min/km)",
    "Lactate Threshold Heart Rate (bpm)",
    "Garmin Sleep Score (0-100)",
    "Sleep Start Time",
    "Sleep End Time",
    "Deep Sleep (min)",
    "Light Sleep (min)",
    "REM Sleep (min)",
    "Awake Time (min)",
    "Sleep Length (min)",
    "Sleep Need (min)",
    "Overnight Average Pulse Ox / SpO2 (%)",
    "Garmin Average Stress Score (0-100)",
    "Daily Min Body Battery (0-100)",
    "Daily Max Body Battery (0-100)",
    "Body Battery Charged (0-100)",
    "Body Battery Drained (0-100)",
    "Daily Steps",
    "Daily Floors Climbed",
    "Daily Intensity Minutes",
    "Total Calories (kcal)",
    "Systolic Blood Pressure (mmHg)",
    "Diastolic Blood Pressure (mmHg)",
    "Garmin Training Load (7 Day Sum)",
    "Garmin Training Load Focus",
    "Morning Garmin Training Readiness (0-100)",
    "Overnight Resting HR (bpm)",
    "Overnight HRV (ms)",
    "Garmin HRV Status (Text Label)",
    "Garmin Training Status (Text Label)",
    "Total Walking Distance (km)",
    "Total Walking Duration (min)",
    "Total Running Activities Count",
    "Total Running Distance (km)",
    "Total Running Duration (min)",
    "Total Strength Training Duration (min)",
    "Daily Moderate Intensity Minutes",
    "Daily Vigorous Intensity Minutes",
    "Daily Active Calories",
    "Time spent at rest (mins)",
    "Time spent at low stress (mins)",
    "Time spent at medium stress (mins)",
    "Time spent at high stress (mins)",
    "Anaerobic Training Load (7d sum)",
    "High Aerobic Training Load (7d sum)",
    "Low Aerobic Training Load (7d sum)",
    "Average Pace for that day's runs",
    "Average Grade Adjusted Pace for that day's runs (weighted by distance or time)",
    "Waking Average Stress Score (0-100)"
]

ACTIVITY_HEADERS = [
    "Activity ID",
    "Date (YYYY-MM-DD)",
    "Start Time (HH:MM)",
    "Activity Type",
    "Activity Name",
    "Distance (km)",
    "Duration (min)",
    "Avg Pace (min/km)",
    "Average Grade Adjusted Pace (min/km)",
    "Total Ascent (m)",
    "Total Descent (m)",
    "Feels Like Temperature (Celsius)",
    "Weather Condition",
    "Sustained Wind Speed (km/h)",
    "Avg HR (bpm)",
    "Max HR (bpm)",
    "Average Cadence (spm)",
    "Average Stride Length (m)",
    "Average Ground Contact Time (ms)",
    "Vertical Oscillation (cm)",
    "Aerobic Training Effect (0.0-5.0)",
    "Anaerobic Training Effect (0.0-5.0)",
    "Activity Training Load",
    "Avg Power (Watts)",
    "Max Power (Watts)",
    "Normalized Power (Watts)",
    "Estimated Sweat Loss (ml)",
    "Garmin Training Effect Label",
    "HR Zone 1 (min)",
    "HR Zone 2 (min)",
    "HR Zone 3 (min)",
    "HR Zone 4 (min)",
    "HR Zone 5 (min)",
    "Power Zone 1 (min)",
    "Power Zone 2 (min)",
    "Power Zone 3 (min)",
    "Power Zone 4 (min)",
    "Power Zone 5 (min)"
]

# =========================================================
# 3. DATA MAPPING (Connects Headers to Garmin Data)
# =========================================================

HEADER_TO_ATTRIBUTE_MAP = {
    "Date (YYYY-MM-DD)": "date",
    "User Name": "user_name",
    "User Age": "user_age",
    "User Gender": "user_gender",
    "Physiological Maximum Heart Rate (bpm)": "max_hr_hunt",
    "Garmin Sleep Score (0-100)": "sleep_score",
    "Sleep Length (min)": "sleep_length",
    "Sleep Need (min)": "sleep_need",
    "Sleep Start Time": "sleep_start_time",
    "Sleep End Time": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake Time (min)": "sleep_awake",
    "Overnight Average Pulse Ox / SpO2 (%)": "overnight_pulse_ox",
    "Overnight HRV (ms)": "overnight_hrv",
    "Garmin HRV Status (Text Label)": "hrv_status",
    "Overnight Resting HR (bpm)": "resting_heart_rate",
    "Garmin Average Stress Score (0-100)": "average_stress",
    "Daily Min Body Battery (0-100)": "body_battery_min",
    "Daily Max Body Battery (0-100)": "body_battery_max",
    "Body Battery Charged (0-100)": "body_battery_charged",
    "Body Battery Drained (0-100)": "body_battery_drained",
    "Systolic Blood Pressure (mmHg)": "blood_pressure_systolic",
    "Diastolic Blood Pressure (mmHg)": "blood_pressure_diastolic",
    "Total Calories (kcal)": "total_calories",
    "Daily Intensity Minutes": "intensity_minutes",
    "Daily Steps": "steps",
    "Daily Floors Climbed": "floors_climbed",
    "VO2 Max (ml/kg/min)": "vo2max_running",
    "VO2 Max Percentile (Age-Gender Adjusted)": "vo2_max_percentile",
    "Lactate Threshold Pace (min/km)": "lactate_threshold_pace",
    "Lactate Threshold Heart Rate (bpm)": "lactate_threshold_bpm",
    "Garmin Training Load (7 Day Sum)": "seven_day_load",
    "Garmin Training Load Focus": "training_load_focus",
    "Morning Garmin Training Readiness (0-100)": "training_readiness",
    "Garmin Training Status (Text Label)": "training_status",
    "Total Walking Distance (km)": "total_walking_distance",
    "Total Walking Duration (min)": "total_walking_duration",
    "Total Running Activities Count": "total_running_count",
    "Total Running Distance (km)": "total_running_distance",
    "Total Running Duration (min)": "total_running_duration",
    "Total Strength Training Duration (min)": "total_strength_duration",
    "Daily Moderate Intensity Minutes": "moderate_intensity_minutes",
    "Daily Vigorous Intensity Minutes": "vigorous_intensity_minutes",
    "Daily Active Calories": "active_calories",
    "Time spent at rest (mins)": "rest_stress_duration",
    "Time spent at low stress (mins)": "low_stress_duration",
    "Time spent at medium stress (mins)": "medium_stress_duration",
    "Time spent at high stress (mins)": "high_stress_duration",
    "Anaerobic Training Load (7d sum)": "anaerobic_training_load",
    "High Aerobic Training Load (7d sum)": "high_aerobic_training_load",
    "Low Aerobic Training Load (7d sum)": "low_aerobic_training_load",
    "Average Pace for that day's runs": "avg_run_pace",
    "Average Grade Adjusted Pace for that day's runs (weighted by distance or time)": "avg_run_gap_pace",
    "Waking Average Stress Score (0-100)": "average_waking_stress"
}
