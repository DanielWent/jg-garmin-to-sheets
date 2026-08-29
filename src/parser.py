"""Parser for Garmin Connect API response data."""

import logging
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class GarminParser:
    """Parses raw Garmin Connect JSON responses into structured dictionaries and DataFrames."""

    @staticmethod
    def parse_daily_summary(
        summary: Optional[Dict[str, Any]],
        sleep_data: Optional[Dict[str, Any]] = None,
        stress_data: Optional[Dict[str, Any]] = None,
        body_battery_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Parse daily health, activity, and wellness metrics into a structured dictionary.
        """
        if not summary:
            return {}

        date_str = summary.get("calendarDate")

        # Sleep Metrics
        sleep_duration_seconds = None
        sleep_score = None
        if sleep_data and "dailySleepDTO" in sleep_data:
            dto = sleep_data.get("dailySleepDTO", {})
            sleep_duration_seconds = dto.get("sleepTimeSeconds")
            sleep_score = dto.get("sleepScores", {}).get("overall", {}).get("value")
        elif sleep_data and "sleepTimeSeconds" in sleep_data:
            sleep_duration_seconds = sleep_data.get("sleepTimeSeconds")
            sleep_score = sleep_data.get("sleepScore")

        # Stress Metrics
        avg_stress_level = summary.get("averageStressLevel")
        max_stress_level = summary.get("maxStressLevel")
        if avg_stress_level is None and stress_data:
            avg_stress_level = stress_data.get("avgStressLevel")
            max_stress_level = stress_data.get("maxStressLevel")

        # Body Battery Metrics
        bb_lowest = summary.get("bodyBatteryLowestValue")
        bb_highest = summary.get("bodyBatteryHighestValue")
        bb_most_recent = summary.get("bodyBatteryMostRecentValue")

        if (bb_lowest is None or bb_highest is None) and body_battery_data:
            bb_values = [
                entry.get("bodyBatteryValues", [])
                for entry in body_battery_data
                if isinstance(entry, dict)
            ]
            flat_bb = [
                val[1]
                for sublist in bb_values
                for val in sublist
                if len(val) > 1 and val[1] is not None
            ]
            if flat_bb:
                bb_lowest = min(flat_bb)
                bb_highest = max(flat_bb)
                bb_most_recent = flat_bb[-1]

        # Calories & Intensity
        active_calories = summary.get("activeKilocalories")
        if active_calories is None:
            active_calories = summary.get("activeCalories")

        moderate_intensity_minutes = summary.get("moderateIntensityMinutes")
        vigorous_intensity_minutes = summary.get("vigorousIntensityMinutes")

        return {
            "Date": date_str,
            "Daily Steps": summary.get("totalSteps"),
            "Daily Step Goal": summary.get("dailyStepGoal"),
            "Daily Total Distance (m)": summary.get("totalDistanceMeters"),
            "Daily Total Calories": summary.get("totalKilocalories"),
            "Daily BMR Calories": summary.get("bmrKilocalories"),
            "Daily Resting Heart Rate": summary.get("restingHeartRate"),
            "Daily Min Heart Rate": summary.get("minHeartRate"),
            "Daily Max Heart Rate": summary.get("maxHeartRate"),
            "Daily Average Stress Level": avg_stress_level,
            "Daily Max Stress Level": max_stress_level,
            "Daily Body Battery Lowest": bb_lowest,
            "Daily Body Battery Highest": bb_highest,
            "Daily Body Battery Most Recent": bb_most_recent,
            "Daily Sleep Duration (s)": sleep_duration_seconds,
            "Daily Sleep Score": sleep_score,
            "Daily Floors Ascended": summary.get("floorsAscended"),
            "Daily Moderate Intensity Minutes": moderate_intensity_minutes,
            "Daily Vigorous Intensity Minutes": vigorous_intensity_minutes,
            "Daily Active Calories": active_calories,
        }

    @staticmethod
    def parse_activities(activities: List[Dict[str, Any]]) -> pd.DataFrame:
        """Parse Garmin Connect activity list into a structured DataFrame."""
        if not activities:
            return pd.DataFrame()

        records = []
        for act in activities:
            records.append({
                "Activity ID": act.get("activityId"),
                "Activity Name": act.get("activityName"),
                "Activity Type": act.get("activityType", {}).get("typeKey"),
                "Start Time": act.get("startTimeLocal"),
                "Distance (m)": act.get("distance"),
                "Duration (s)": act.get("duration"),
                "Elapsed Duration (s)": act.get("elapsedDuration"),
                "Moving Duration (s)": act.get("movingDuration"),
                "Elevation Gain (m)": act.get("elevationGain"),
                "Elevation Loss (m)": act.get("elevationLoss"),
                "Average Speed (m/s)": act.get("averageSpeed"),
                "Max Speed (m/s)": act.get("maxSpeed"),
                "Calories": act.get("calories"),
                "Average HR": act.get("averageHR"),
                "Max HR": act.get("maxHR"),
                "Average Running Cadence": act.get("averageRunningCadenceInStepsPerMinute"),
                "Max Running Cadence": act.get("maxRunningCadenceInStepsPerMinute"),
                "Steps": act.get("steps"),
                "Moderate Intensity Minutes": act.get("moderateIntensityMinutes"),
                "Vigorous Intensity Minutes": act.get("vigorousIntensityMinutes"),
            })

        return pd.DataFrame(records)
