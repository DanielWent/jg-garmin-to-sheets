from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Dict, Any

@dataclass
class GarminMetrics:
    date: date
    # Daily Totals
    sleep_score: Optional[float] = None
    sleep_length: Optional[float] = None
    sleep_start_time: Optional[str] = None
    sleep_end_time: Optional[str] = None
    sleep_need: Optional[int] = None
    sleep_efficiency: Optional[float] = None # NEW
    sleep_deep: Optional[float] = None
    sleep_light: Optional[float] = None
    sleep_rem: Optional[float] = None
    sleep_awake: Optional[float] = None
    overnight_respiration: Optional[float] = None
    overnight_pulse_ox: Optional[float] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None # NEW
    body_fat: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    average_stress: Optional[int] = None
    rest_stress_duration: Optional[int] = None # NEW
    low_stress_duration: Optional[int] = None # NEW
    medium_stress_duration: Optional[int] = None # NEW
    high_stress_duration: Optional[int] = None # NEW
    overnight_hrv: Optional[int] = None
    hrv_status: Optional[str] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    training_status: Optional[str] = None
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    intensity_minutes: Optional[int] = None
    steps: Optional[int] = None
    floors_climbed: Optional[float] = None
    
    # Body Battery
    max_body_battery: Optional[int] = None
    min_body_battery: Optional[int] = None

    # List to hold individual activities for the secondary tab
    activities: List[Dict[str, Any]] = field(default_factory=list)

# Headers for Daily Summary Tab (Renamed for AI Clarity)
HEADERS = [
    "Date",
    "Sleep Score", "Recommended Sleep Need (min)", "Sleep Length (min)", "Sleep Efficiency (%)",
    "Fall Asleep Time", "Wake Up Time",
    "Deep Sleep (min)", "Light Sleep (min)", "REM Sleep (min)", "Awake/Restless (min)",
    "Avg Overnight Respiration (breaths/min)", "Avg Overnight SpO2 (%)",
    "Resting Heart Rate", "HRV (ms)", "HRV Status", 
    "Daily Avg Stress Score (0-100)", 
    "Rest Stress Duration (sec)", "Low Stress Duration (sec)", 
    "Medium Stress Duration (sec)", "High Stress Duration (sec)",
    "Weight (kg)", "BMI", "Body Fat %",
    "VO2 Max Running", "VO2 Max Cycling", "Training Status Phase",
    "Steps", "Floors Climbed", 
    "Active Calories (kcal)", "BMR Calories (kcal)", "Daily Intensity Minutes",
    "Max Body Battery", "Min Body Battery"
]

# Activity Headers (Unchanged)
ACTIVITY_HEADERS = [
    "Activity ID", "Date", "Time", "Type", "Name",
    "Distance (km)", "Duration (min)", "Avg Pace (min/km)",
    "Avg HR", "Max HR", "Calories", "Avg Cadence (spm)",
    "Elevation Gain (m)", "Aerobic TE", "Anaerobic TE"
]

HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Recommended Sleep Need (min)": "sleep_need",
    "Sleep Length (min)": "sleep_length",
    "Sleep Efficiency (%)": "sleep_efficiency",
    "Fall Asleep Time": "sleep_start_time",
    "Wake Up Time": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake/Restless (min)": "sleep_awake",
    "Avg Overnight Respiration (breaths/min)": "overnight_respiration",
    "Avg Overnight SpO2 (%)": "overnight_pulse_ox",
    "Resting Heart Rate": "resting_heart_rate",
    "HRV (ms)": "overnight_hrv",
    "HRV Status": "hrv_status",
    "Daily Avg Stress Score (0-100)": "average_stress",
    "Rest Stress Duration (sec)": "rest_stress_duration",
    "Low Stress Duration (sec)": "low_stress_duration",
    "Medium Stress Duration (sec)": "medium_stress_duration",
    "High Stress Duration (sec)": "high_stress_duration",
    "Weight (kg)": "weight",
    "BMI": "bmi",
    "Body Fat %": "body_fat",
    "VO2 Max Running": "vo2max_running",
    "VO2 Max Cycling": "vo2max_cycling",
    "Training Status Phase": "training_status",
    "Steps": "steps",
    "Floors Climbed": "floors_climbed",
    "Active Calories (kcal)": "active_calories",
    "BMR Calories (kcal)": "resting_calories",
    "Daily Intensity Minutes": "intensity_minutes",
    "Max Body Battery": "max_body_battery",
    "Min Body Battery": "min_body_battery"
}
