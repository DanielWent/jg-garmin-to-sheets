# =========================================================
# 1. HEADER LISTS (Columns for the Google Sheets)
# =========================================================

SLEEP_HEADERS = [
    "Date",
    "Sleep Score",
    "Sleep Length (hrs)",
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
    "Skeletal Muscle (kg)",
    "Bone Mass (kg)",
    "Body Water (%)"
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
    "Diastolic (mmHg)",
    "Pulse (bpm)"
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

# =========================================================
# 2. DATA MAPPING (Connects Headers to Garmin Data)
# =========================================================

HEADER_TO_ATTRIBUTE_MAP = {
    # --- Sleep Tab ---
    "Date": "date",
    "Sleep Score": "sleep_score",
    "Sleep Length (hrs)": "sleep_length",
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
    "Skeletal Muscle (kg)": "skeletal_muscle",
    "Bone Mass (kg)": "bone_mass",
    "Body Water (%)": "body_water",

    # --- Stress Tab ---
    "Average Stress": "average_stress",
    "Rest Stress Duration (min)": "rest_stress_duration",
    "Low Stress Duration (min)": "low_stress_duration",
    "Medium Stress Duration (min)": "medium_stress_duration",
    "High Stress Duration (min)": "high_stress_duration",
    "Stress Score": "average_stress", # duplicate mapping if needed

    # --- Blood Pressure Tab ---
    "Systolic (mmHg)": "blood_pressure_systolic",
    "Diastolic (mmHg)": "blood_pressure_diastolic",
    "Pulse (bpm)": "resting_heart_rate", # typically logged with BP or just use RHR

    # --- Activity Summary Tab ---
    "Active Calories": "active_calories",
    "Resting Calories": "resting_calories",
    "Intensity Minutes": "intensity_minutes",
    "Steps": "steps",
    "Floors Climbed": "floors_climbed"
}

# (Optional) If you have a separate mapping for GarminMetrics attributes, ensure they align here.
