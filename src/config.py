"""Configuration constants, headers, mapping rules, and data structures for Garmin sync."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class GarminMetrics:
    date: Optional[str] = None
    user_name: Optional[str] = None
    user_gender: Optional[str] = None
    user_age: Optional[float] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    body_water: Optional[float] = None
    bone_mass: Optional[float] = None
    muscle_mass: Optional[float] = None
    resting_hr: Optional[int] = None
    min_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_hr: Optional[int] = None
    hrv_status: Optional[str] = None
    hrv_weekly_avg: Optional[int] = None
    hrv_last_night_avg: Optional[int] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    blood_pressure_pulse: Optional[int] = None
    vo2_max: Optional[float] = None
    training_status: Optional[str] = None
    lactate_threshold_hr: Optional[int] = None
    lactate_threshold_speed: Optional[float] = None
    training_readiness: Optional[int] = None
    sleep_duration: Optional[float] = None
    sleep_score: Optional[int] = None
    rem_sleep: Optional[float] = None
    light_sleep: Optional[float] = None
    deep_sleep: Optional[float] = None
    awake_time: Optional[float] = None
    average_stress: Optional[Any] = None
    max_stress: Optional[Any] = None
    rest_stress_duration: Optional[float] = None
    activity_stress_duration: Optional[float] = None
    low_stress_duration: Optional[float] = None
    medium_stress_duration: Optional[float] = None
    high_stress_duration: Optional[float] = None
    stress_qualifier: Optional[str] = None
    steps: Optional[Any] = None
    step_goal: Optional[int] = None
    floors_climbed: Optional[Any] = None
    total_calories: Optional[Any] = None
    net_calories: Optional[float] = None
    intensity_minutes: Optional[Any] = None
    body_battery_min: Optional[Any] = None
    body_battery_max: Optional[Any] = None
    body_battery_charged: Optional[Any] = None
    body_battery_drained: Optional[Any] = None
    body_battery_most_recent: Optional[Any] = None
    moderate_intensity_minutes: Optional[Any] = None
    vigorous_intensity_minutes: Optional[Any] = None
    active_calories: Optional[Any] = None
    activities: List[Dict[str, Any]] = field(default_factory=list)


GENERAL_SUMMARY_HEADERS = [
    "Date",
    "User Name",
    "User Gender",
    "User Age",
    "Weight (kg)",
    "BMI",
    "Body Fat (%)",
    "Body Water (%)",
    "Bone Mass (kg)",
    "Muscle Mass (kg)",
    "Resting HR (bpm)",
    "Min HR (bpm)",
    "Max HR (bpm)",
    "Avg HR (bpm)",
    "HRV Status",
    "HRV Weekly Avg (ms)",
    "HRV Last Night Avg (ms)",
    "Blood Pressure Systolic (mmHg)",
    "Blood Pressure Diastolic (mmHg)",
    "Blood Pressure Pulse (bpm)",
    "VO2 Max (ml/kg/min)",
    "Training Status",
    "Lactate Threshold HR (bpm)",
    "Lactate Threshold Speed (m/s)",
    "Training Readiness",
    "Sleep Duration (hours)",
    "Sleep Score",
    "REM Sleep (hours)",
    "Light Sleep (hours)",
    "Deep Sleep (hours)",
    "Awake Time (hours)",
    "Average Stress",
    "Max Stress",
    "Rest Stress Duration (hours)",
    "Activity Stress Duration (hours)",
    "Low Stress Duration (hours)",
    "Medium Stress Duration (hours)",
    "High Stress Duration (hours)",
    "Stress Qualifier",
    "Steps",
    "Step Goal",
    "Floors Climbed",
    "Total Calories (kcal)",
    "Net Calories (kcal)",
    "Intensity Minutes",
    "Body Battery Min",
    "Body Battery Max",
    "Body Battery Charged",
    "Body Battery Drained",
    "Body Battery Most Recent",
    "Daily Moderate Intensity Minutes",
    "Daily Vigorous Intensity Minutes",
    "Daily Active Calories",
]

ACTIVITY_HEADERS = [
    "activityId",
    "activityName",
    "startTimeLocal",
    "activityType",
    "distance",
    "duration",
    "elapsedDuration",
    "movingDuration",
    "elevationGain",
    "elevationLoss",
    "averageSpeed",
    "maxSpeed",
    "calories",
    "averageHR",
    "maxHR",
    "averageRunningCadenceInStepsPerMinute",
    "maxRunningCadenceInStepsPerMinute",
    "steps",
]

HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date",
    "User Name": "user_name",
    "User Gender": "user_gender",
    "User Age": "user_age",
    "Weight (kg)": "weight",
    "BMI": "bmi",
    "Body Fat (%)": "body_fat",
    "Body Water (%)": "body_water",
    "Bone Mass (kg)": "bone_mass",
    "Muscle Mass (kg)": "muscle_mass",
    "Resting HR (bpm)": "resting_hr",
    "Min HR (bpm)": "min_hr",
    "Max HR (bpm)": "max_hr",
    "Avg HR (bpm)": "avg_hr",
    "HRV Status": "hrv_status",
    "HRV Weekly Avg (ms)": "hrv_weekly_avg",
    "HRV Last Night Avg (ms)": "hrv_last_night_avg",
    "Blood Pressure Systolic (mmHg)": "blood_pressure_systolic",
    "Blood Pressure Diastolic (mmHg)": "blood_pressure_diastolic",
    "Blood Pressure Pulse (bpm)": "blood_pressure_pulse",
    "VO2 Max (ml/kg/min)": "vo2_max",
    "Training Status": "training_status",
    "Lactate Threshold HR (bpm)": "lactate_threshold_hr",
    "Lactate Threshold Speed (m/s)": "lactate_threshold_speed",
    "Training Readiness": "training_readiness",
    "Sleep Duration (hours)": "sleep_duration",
    "Sleep Score": "sleep_score",
    "REM Sleep (hours)": "rem_sleep",
    "Light Sleep (hours)": "light_sleep",
    "Deep Sleep (hours)": "deep_sleep",
    "Awake Time (hours)": "awake_time",
    "Average Stress": "average_stress",
    "Max Stress": "max_stress",
    "Rest Stress Duration (hours)": "rest_stress_duration",
    "Activity Stress Duration (hours)": "activity_stress_duration",
    "Low Stress Duration (hours)": "low_stress_duration",
    "Medium Stress Duration (hours)": "medium_stress_duration",
    "High Stress Duration (hours)": "high_stress_duration",
    "Stress Qualifier": "stress_qualifier",
    "Steps": "steps",
    "Step Goal": "step_goal",
    "Floors Climbed": "floors_climbed",
    "Total Calories (kcal)": "total_calories",
    "Net Calories (kcal)": "net_calories",
    "Intensity Minutes": "intensity_minutes",
    "Body Battery Min": "body_battery_min",
    "Body Battery Max": "body_battery_max",
    "Body Battery Charged": "body_battery_charged",
    "Body Battery Drained": "body_battery_drained",
    "Body Battery Most Recent": "body_battery_most_recent",
    "Daily Moderate Intensity Minutes": "moderate_intensity_minutes",
    "Daily Vigorous Intensity Minutes": "vigorous_intensity_minutes",
    "Daily Active Calories": "active_calories",
}
