from dataclasses import dataclass, fields
from datetime import date
from typing import Optional

# 1. The Dataclass defines the data structure
@dataclass
class GarminMetrics:
    date: date
    # Sleep Details
    sleep_score: Optional[float] = None
    sleep_length: Optional[float] = None
    sleep_start_time: Optional[str] = None    # HH:MM
    sleep_end_time: Optional[str] = None      # HH:MM
    sleep_need: Optional[int] = None          # NEW: Minutes
    sleep_deep: Optional[float] = None        # Minutes
    sleep_light: Optional[float] = None       # Minutes
    sleep_rem: Optional[float] = None         # Minutes
    sleep_awake: Optional[float] = None       # Minutes
    overnight_respiration: Optional[float] = None # NEW: brpm
    overnight_pulse_ox: Optional[float] = None    # NEW: %
    
    # Body & Health
    weight: Optional[float] = None
    body_fat: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    average_stress: Optional[int] = None
    overnight_hrv: Optional[int] = None
    hrv_status: Optional[str] = None
    
    # Performance & Training
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    training_status: Optional[str] = None
    lactate_threshold_pace: Optional[str] = None # MM:SS / km
    lactate_threshold_hr: Optional[int] = None   # BPM
    
    # Activity Stats
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    intensity_minutes: Optional[int] = None
    steps: Optional[int] = None
    floors_climbed: Optional[float] = None # NEW
    all_activity_count: Optional[int] = None
    running_activity_count: Optional[int] = None
    running_distance: Optional[float] = None
    cycling_activity_count: Optional[int] = None
    cycling_distance: Optional[float] = None
    strength_activity_count: Optional[int] = None
    strength_duration: Optional[float] = None
    cardio_activity_count: Optional[int] = None
    cardio_duration: Optional[float] = None
    tennis_activity_count: Optional[int] = None
    tennis_activity_duration: Optional[float] = None

# 2. The Headers list defines the columns in your Google Sheet
HEADERS = [
    "Date",
    # Sleep
    "Sleep Score", "Sleep Need (min)", "Sleep Length (hrs)", 
    "Fall Asleep Time", "Wake Up Time",
    "Deep Sleep (min)", "Light Sleep (min)", "REM Sleep (min)", "Awake/Restless (min)",
    "Overnight Respiration (brpm)", "Overnight Pulse Ox (%)",
    # Health
    "Resting Heart Rate", "HRV (ms)", "HRV Status", "Average Stress",
    "Weight (kg)", "Body Fat %",
    # Performance
    "Lactate Threshold Pace (min/km)", "Lactate Threshold HR (bpm)",
    "VO2 Max Running", "VO2 Max Cycling", "Training Status",
    # Activity
    "Steps", "Floors Climbed", 
    "Active Calories", "Resting Calories", "Intensity Minutes",
    "All Activity Count",
    "Running Activity Count", "Running Distance (km)",
    "Cycling Activity Count", "Cycling Distance (km)",
    "Strength Activity Count", "Strength Duration (min)",
    "Cardio Activity Count", "Cardio Duration (min)",
    "Tennis Activity Count", "Tennis Duration (min)"
]

# 3. The Map connects the Headers to the Dataclass attributes
HEADER_TO_ATTRIBUTE_MAP = {
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Sleep Need (min)": "sleep_need",
    "Sleep Length (hrs)": "sleep_length",
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
    "Lactate Threshold Pace (min/km)": "lactate_threshold_pace",
    "Lactate Threshold HR (bpm)": "lactate_threshold_hr",
    "VO2 Max Running": "vo2max_running",
    "VO2 Max Cycling": "vo2max_cycling",
    "Training Status": "training_status",
    "Steps": "steps",
    "Floors Climbed": "floors_climbed",
    "Active Calories": "active_calories",
    "Resting Calories": "resting_calories",
    "Intensity Minutes": "intensity_minutes",
    "All Activity Count": "all_activity_count",
    "Running Activity Count": "running_activity_count",
    "Running Distance (km)": "running_distance",
    "Cycling Activity Count": "cycling_activity_count",
    "Cycling Distance (km)": "cycling_distance",
    "Strength Activity Count": "strength_activity_count",
    "Strength Duration (min)": "strength_duration",
    "Cardio Activity Count": "cardio_activity_count",
    "Cardio Duration (min)": "cardio_duration",
    "Tennis Activity Count": "tennis_activity_count",
    "Tennis Duration (min)": "tennis_activity_duration"
}
