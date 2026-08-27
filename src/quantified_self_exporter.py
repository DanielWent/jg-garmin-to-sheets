import pandas as pd
import numpy as np
import os

# Configurable Demographic Variables
AGE = 40
HEIGHT_CM = 185
MAX_HR = 190

def convert_pace_to_decimal(pace_str):
    """Converts a MM:SS pace string to decimal minutes as a float."""
    if pd.isna(pace_str) or not isinstance(pace_str, str) or ':' not in pace_str:
        return np.nan
    try:
        minutes, seconds = pace_str.split(':')
        return float(minutes) + (float(seconds) / 60.0)
    except ValueError:
        return np.nan

def generate_quantified_self_csv(df: pd.DataFrame, output_path: str = "drw_quantified_self.csv"):
    """
    Processes daily health data and exports an LLM-optimized CSV.
    Assumes incoming raw DataFrame includes 'Raw_Body_Fat_Percentage' and 'Lactate_Threshold_Pace'.
    """
    
    # 1. Global Processing: Enforce strict chronological order
    df = df.sort_values(by="Date_YYYY_MM_DD", ascending=True).reset_index(drop=True)
    
    # Pre-processing: Pace and Time Conversions
    if "Lactate_Threshold_Pace" in df.columns:
        df["Lactate_Threshold_Pace_decimal_min_km"] = df["Lactate_Threshold_Pace"].apply(convert_pace_to_decimal)
        
    for col in ["Sleep_Start_Time_HH_MM", "Sleep_End_Time_HH_MM"]:
        if col in df.columns:
            # Enforce strict 24-hour HH:MM formatting
            df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce").dt.strftime("%H:%M")

    # 2. Tier 1 Derived Metrics (Right-aligned standard rolling windows)
    df["Running_Distance_28d_Total_km"] = df["Daily_Running_Distance_km"].rolling(window=28, min_periods=1).sum().round(2)
    df["Resting_Heart_Rate_7d_Average_bpm"] = df["Overnight_Resting_Heart_Rate_bpm"].rolling(window=7, min_periods=1).mean().round(1)
    df["HRV_RMSSD_7d_Average_ms"] = df["Overnight_HRV_RMSSD_ms"].rolling(window=7, min_periods=1).mean().round(1)
    
    if "Raw_Body_Fat_Percentage" in df.columns:
        df["Body_Fat_Percentage_7d_Average"] = df["Raw_Body_Fat_Percentage"].rolling(window=7, min_periods=1).mean().round(1)

    # 3. Tier 2 Derived Metrics: Non-Overlapping Baseline HRV Z-Score
    shifted_hrv = df["Overnight_HRV_RMSSD_ms"].shift(7)
    shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
    shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()
    
    df["HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore"] = (
        (df["HRV_RMSSD_7d_Average_ms"] - shifted_60d_mean) / shifted_60d_std
    ).round(2)

    # 4. Slice to export window (Most recent 730 days only)
    df_export = df.tail(730).copy()

    # 5. Schema Alignment
    required_columns = [
        "Date_YYYY_MM_DD",
        "Daily_Running_Distance_km",
        "Daily_Running_Duration_min",
        "Daily_Walking_Distance_km",
        "Daily_Strength_Duration_min",
        "Daily_Steps_Count",
        "Running_Distance_28d_Total_km",
        "Garmin_7d_Training_Load_Sum",
        "Garmin_VO2_Max_ml_kg_min",
        "Lactate_Threshold_Pace_decimal_min_km",
        "Lactate_Threshold_Heart_Rate_bpm",
        "Overnight_Sleep_Duration_min",
        "Sleep_Start_Time_HH_MM",
        "Sleep_End_Time_HH_MM",
        "Overnight_Resting_Heart_Rate_bpm",
        "Resting_Heart_Rate_7d_Average_bpm",
        "Overnight_HRV_RMSSD_ms",
        "HRV_RMSSD_7d_Average_ms",
        "HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore",
        "Daily_Morning_Weight_kg",
        "Body_Fat_Percentage_7d_Average",
        "Resting_Systolic_Blood_Pressure_mmHg",
        "Resting_Diastolic_Blood_Pressure_mmHg"
    ]

    # Generate missing columns gracefully before selection to avoid KeyError
    for col in required_columns:
        if col not in df_export.columns:
            df_export[col] = np.nan

    # Filter to exact column order (automatically drops raw Body Fat column)
    df_export = df_export[required_columns]

    # 6. Injection & Export
    header_string = f"# Context: Male, Age: {AGE}, Height: {HEIGHT_CM} cm, Max HR: {MAX_HR} bpm\n"
    
    with open(output_path, "w") as f:
        f.write(header_string)
        
    df_export.to_csv(output_path, mode="a", header=True, index=False, na_rep="")
    print(f"Successfully exported LLM-ready metrics to {output_path}")
