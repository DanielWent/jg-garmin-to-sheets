# ... imports ...

HEADERS = [
    "Date", "Weight (kg)", "BMI", "Body Fat (%)",
    "Sleep Score", "Sleep Need (min)", "Sleep Efficiency (%)", "Sleep Duration (min)",
    "Sleep Start", "Sleep End",
    "Deep Sleep (min)", "Light Sleep (min)", "REM Sleep (min)", "Awake (min)",
    "Respiration (brpm)", "SpO2 (%)",
    "Resting HR", "Avg Stress",
    "Rest Stress (min)", "Low Stress (min)", "Medium Stress (min)", "High Stress (min)",
    "Overnight HRV (ms)", "HRV Status",
    "VO2 Max (Run)", "VO2 Max (Cycle)",
    "Lactate Threshold HR", "Lactate Threshold Pace",  # <--- NEW COLUMNS
    "Training Status",
    "BP Systolic", "BP Diastolic",
    "Active Calories", "Resting Calories", "Intensity Minutes",
    "Steps", "Floors Climbed",
    "Activity 1", "Activity 2", "Activity 3"
]

class GoogleSheetsClient:
    # ... (init and other methods remain the same) ...

    def _map_metrics_to_row(self, metrics: GarminMetrics) -> List[str]:
        # Format activities
        activity_strs = []
        for activity in metrics.activities:
            summary = (
                f"{activity['Type']} - {activity['Name']}: "
                f"{activity['Distance (km)']}km in {activity['Duration (min)']}m "
                f"({activity['Avg Pace (min/km)']}/km)"
            )
            activity_strs.append(summary)
        
        # Ensure we have 3 activity slots
        while len(activity_strs) < 3:
            activity_strs.append("")

        return [
            metrics.date.isoformat(),
            str(metrics.weight) if metrics.weight else "",
            str(metrics.bmi) if metrics.bmi else "",
            str(metrics.body_fat) if metrics.body_fat else "",
            str(metrics.sleep_score) if metrics.sleep_score is not None else "",
            str(metrics.sleep_need) if metrics.sleep_need is not None else "",
            str(metrics.sleep_efficiency) if metrics.sleep_efficiency is not None else "",
            str(metrics.sleep_length) if metrics.sleep_length is not None else "",
            str(metrics.sleep_start_time) if metrics.sleep_start_time else "",
            str(metrics.sleep_end_time) if metrics.sleep_end_time else "",
            str(metrics.sleep_deep) if metrics.sleep_deep is not None else "",
            str(metrics.sleep_light) if metrics.sleep_light is not None else "",
            str(metrics.sleep_rem) if metrics.sleep_rem is not None else "",
            str(metrics.sleep_awake) if metrics.sleep_awake is not None else "",
            str(metrics.overnight_respiration) if metrics.overnight_respiration else "",
            str(metrics.overnight_pulse_ox) if metrics.overnight_pulse_ox else "",
            str(metrics.resting_heart_rate) if metrics.resting_heart_rate else "",
            str(metrics.average_stress) if metrics.average_stress else "",
            str(metrics.rest_stress_duration) if metrics.rest_stress_duration is not None else "",
            str(metrics.low_stress_duration) if metrics.low_stress_duration is not None else "",
            str(metrics.medium_stress_duration) if metrics.medium_stress_duration is not None else "",
            str(metrics.high_stress_duration) if metrics.high_stress_duration is not None else "",
            str(metrics.overnight_hrv) if metrics.overnight_hrv else "",
            str(metrics.hrv_status) if metrics.hrv_status else "",
            str(metrics.vo2max_running) if metrics.vo2max_running else "",
            str(metrics.vo2max_cycling) if metrics.vo2max_cycling else "",
            str(metrics.lactate_threshold_bpm) if metrics.lactate_threshold_bpm else "",   # <--- NEW
            str(metrics.lactate_threshold_pace) if metrics.lactate_threshold_pace else "", # <--- NEW
            str(metrics.training_status) if metrics.training_status else "",
            str(metrics.blood_pressure_systolic) if metrics.blood_pressure_systolic else "",
            str(metrics.blood_pressure_diastolic) if metrics.blood_pressure_diastolic else "",
            str(metrics.active_calories) if metrics.active_calories else "",
            str(metrics.resting_calories) if metrics.resting_calories else "",
            str(metrics.intensity_minutes) if metrics.intensity_minutes else "",
            str(metrics.steps) if metrics.steps else "",
            str(metrics.floors_climbed) if metrics.floors_climbed else "",
        ] + activity_strs[:3]
