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
    sleep_deep: Optional[float] = None
    sleep_light: Optional[float] = None
    sleep_rem: Optional[float] = None
    sleep_awake: Optional[float] = None
    overnight_respiration: Optional[float] = None
    overnight_pulse_ox: Optional[float] = None
    weight: Optional[float] = None
    body_fat: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    average_stress: Optional[int] = None
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
    
    # NEW FIELDS
    max_body_battery: Optional[int] = None
    min_body_battery: Optional[int] = None

    # List to hold individual activities for the secondary tab
    activities: List[Dict[str, Any]] = field(default_factory=list)

# Headers for Daily Summary Tab
HEADERS = [
    "Date",
    "Sleep Score", "Sleep Need (min)", "Sleep Length (min)", 
    "Fall Asleep Time", "Wake Up Time",
    "Deep Sleep (min)", "Light Sleep (min)", "REM Sleep (min)", "Awake/Restless (min)",
    "Overnight Respiration (brpm)", "Overnight Pulse Ox (%)",
    "Resting Heart Rate", "HRV (ms)", "HRV Status", "Average Stress",
    "Weight (kg)", "Body Fat %",
    "VO2 Max Running", "VO2 Max Cycling", "Training Status",
    "Steps", "Floors Climbed", 
    "Active Calories", "Resting Calories", "Intensity Minutes",
    # DELETED: All Activity Count columns (AA-AK)
    # ADDED: Body Battery
    "Max Body Battery", "Min Body Battery"
]

ACTIVITY_HEADERS = [
    "Activity ID", "Date", "Time", "Type", "Name",
    "Distance (km)", "Duration (min)", "Avg Pace (min/km)",
    "Avg HR", "Max HR", "Calories", "Avg Cadence (spm)",
    "Elevation Gain (m)", "Aerobic TE", "Anaerobic TE"
]

HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Sleep Need (min)": "sleep_need",
    "Sleep Length (min)": "sleep_length",
    "Fall Asleep Time": "sleep_start_time",
    "Wake Up Time": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake/Restless (min)": "sleep_awake",
    "Overnight Respiration (brpm)": "overnight_respiration",
    "Overnight Pulse Ox (%)": "overnight_pulse_ox",
    "Resting Heart Rate": "resting_heart_rate",
    "HRV (ms)": "overnight_hrv",
    "HRV Status": "hrv_status",
    "Average Stress": "average_stress",
    "Weight (kg)": "weight",
    "Body Fat %": "body_fat",
    "VO2 Max Running": "vo2max_running",
    "VO2 Max Cycling": "vo2max_cycling",
    "Training Status": "training_status",
    "Steps": "steps",
    "Floors Climbed": "floors_climbed",
    "Active Calories": "active_calories",
    "Resting Calories": "resting_calories",
    "Intensity Minutes": "intensity_minutes",
    
    # NEW MAPPINGS
    "Max Body Battery": "max_body_battery",
    "Min Body Battery": "min_body_battery"
}
