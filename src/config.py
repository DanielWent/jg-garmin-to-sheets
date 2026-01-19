from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Any, Dict

# -----------------------------------------------------------------------------
# 1. GOOGLE SHEETS HEADERS
# -----------------------------------------------------------------------------

# Main "Daily Summaries" Sheet
HEADERS = [
    "Date (YYYY-MM-DD)", 
    "Sleep Score (0-100)", 
    "Total Sleep (hr)", 
    "Sleep Need (hr)", 
    "Sleep Efficiency (%)",
    "Resting HR (bpm)", 
    "Overnight HRV Avg (ms)", 
    "Daily Stress Avg (0-100)", 
    "Training Status", 
    "VO2 Max Run (ml/kg/min)", 
    "Training Load (7-Day Sum)",
    "Daily Steps (count)", 
    "Active Calories (kcal)", 
    "Weight (kg)", 
    "Body Fat (%)"
]

# Separate "Sleep Logs" Sheet
SLEEP_HEADERS = [
    "Date (YYYY-MM-DD)", 
    "Sleep Score (0-100)", 
    "Total Sleep (min)", 
    "Bedtime (HH:MM)", 
    "Wake Time (HH:MM)",
    "Deep Sleep (min)", 
    "Light Sleep (min)", 
    "REM Sleep (min)", 
    "Awake Time (min)",
    "Restlessness (x)", 
    "Avg Respiration (brpm)", 
    "Avg SpO2 (%)"
]

# Separate "Body Composition" Sheet
BODY_COMP_HEADERS = [
    "Date (YYYY-MM-DD)", 
    "Weight (kg)", 
    "BMI", 
    "Body Fat (%)", 
    "Skeletal Muscle (kg)", 
    "Bone Mass (kg)", 
    "Water (%)"
]

# Separate "Blood Pressure" Sheet
BP_HEADERS = [
    "Date (YYYY-MM-DD)", 
    "Systolic (mmHg)", 
    "Diastolic (mmHg)", 
    "Pulse (bpm)", 
    "Notes"
]

# Separate "Stress Data" Sheet
STRESS_HEADERS = [
    "Date (YYYY-MM-DD)", 
    "Daily Stress Avg (0-100)", 
    "Rest Stress Total (s)", 
    "Low Stress Total (s)", 
    "Med Stress Total (s)", 
    "High Stress Total (s)",
    "Body Battery Max (0-100)", 
    "Body Battery Min (0-100)"
]

# Separate "List of Tracked Activities" Sheet
ACTIVITY_HEADERS = [
    "Activity ID", 
    "Date (YYYY-MM-DD)", 
    "Start Time (HH:MM)", 
    "Activity Type", 
    "Activity Name", 
    "Distance (km)", 
    "Duration (min)",
    "Avg Pace (min/km)", 
    "Avg HR (bpm)", 
    "Max HR (bpm)", 
    "Total Calories (kcal)", 
    "Avg Cadence (spm)", 
    "Elevation Gain (m)", 
    "Aerobic TE (0-5.0)", 
    "Anaerobic TE (0-5.0)",
    "Avg Power (Watts)", 
    "Avg GCT (ms)", 
    "Avg Vert Osc (cm)", 
    "Avg Stride Len (m)",
    "HR Zone 1 (min)", 
    "HR Zone 2 (min)", 
    "HR Zone 3 (min)", 
    "HR Zone 4 (min)", 
    "HR Zone 5 (min)"
]

# For the generic summary tab (if used)
ACTIVITY_SUMMARY_HEADERS = HEADERS

# -----------------------------------------------------------------------------
# 2. INTERNAL DATA MODEL
# -----------------------------------------------------------------------------

# Map headers to attribute names in GarminMetrics
HEADER_TO_ATTRIBUTE_MAP = {
    # Main Sheet
    "Date (YYYY-MM-DD)": "date",
    "Sleep Score (0-100)": "sleep_score",
    "Total Sleep (hr)": "sleep_length_hours",
    "Sleep Need (hr)": "sleep_need_hours",
    "Sleep Efficiency (%)": "sleep_efficiency",
    "Resting HR (bpm)": "resting_heart_rate",
    "Overnight HRV Avg (ms)": "overnight_hrv",
    "Daily Stress Avg (0-100)": "average_stress",
    "Training Status": "training_status",
    "VO2 Max Run (ml/kg/min)": "vo2max_running",
    "Training Load (7-Day Sum)": "seven_day_load",
    "Daily Steps (count)": "steps",
    "Active Calories (kcal)": "active_calories",
    "Weight (kg)": "weight",
    "Body Fat (%)": "body_fat",
    
    # Sleep Sheet
    "Total Sleep (min)": "sleep_length",
    "Bedtime (HH:MM)": "sleep_start_time",
    "Wake Time (HH:MM)": "sleep_end_time",
    "Deep Sleep (min)": "sleep_deep",
    "Light Sleep (min)": "sleep_light",
    "REM Sleep (min)": "sleep_rem",
    "Awake Time (min)": "sleep_awake",
    "Restlessness (x)": "sleep_restlessness", # Note: Placeholder in client
    "Avg Respiration (brpm)": "overnight_respiration",
    "Avg SpO2 (%)": "overnight_pulse_ox",

    # Body Sheet
    "BMI": "bmi",
    "Skeletal Muscle (kg)": "skeletal_muscle", # Placeholder
    "Bone Mass (kg)": "bone_mass",             # Placeholder
    "Water (%)": "body_water",                 # Placeholder

    # BP Sheet
    "Systolic (mmHg)": "blood_pressure_systolic",
    "Diastolic (mmHg)": "blood_pressure_diastolic",
    "Pulse (bpm)": "blood_pressure_pulse",     # Placeholder
    "Notes": "blood_pressure_notes",           # Placeholder

    # Stress Sheet
    "Rest Stress Total (s)": "rest_stress_duration",
    "Low Stress Total (s)": "low_stress_duration",
    "Med Stress Total (s)": "medium_stress_duration",
    "High Stress Total (s)": "high_stress_duration",
    "Body Battery Max (0-100)": "body_battery_max",
    "Body Battery Min (0-100)": "body_battery_min"
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
    sleep_restlessness: Optional[Any] = None # Placeholder
    
    # Body / Health
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    skeletal_muscle: Optional[float] = None # Placeholder
    bone_mass: Optional[float] = None       # Placeholder
    body_water: Optional[float] = None      # Placeholder
    
    # Blood Pressure
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    blood_pressure_pulse: Optional[int] = None # Placeholder
    blood_pressure_notes: Optional[str] = None # Placeholder
    
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
