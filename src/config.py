    "Awake Time (min)",
    "Overnight HRV (ms)",  # <--- NEW
    "HRV Status",          # <--- NEW
    "Overnight Resting Heart Rate (bpm)"
]

# Separate "Body Composition" Sheet
BODY_COMP_HEADERS = [
    "Restlessness (x)": "sleep_restlessness", 
    "Avg Respiration (brpm)": "overnight_respiration",
    "Avg SpO2 (%)": "overnight_pulse_ox",

    # --- NEW MAPPINGS ---
    "Overnight HRV (ms)": "overnight_hrv",
    "HRV Status": "hrv_status",
    "Overnight Resting Heart Rate (bpm)": "resting_heart_rate",
    # --------------------

    "BMI": "bmi",
    "Skeletal Muscle (kg)": "skeletal_muscle", 
