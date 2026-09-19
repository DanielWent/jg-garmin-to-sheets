import io
import json
import os
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import numpy as np
import pandas as pd


def parse_to_iso_date(series: pd.Series) -> pd.Series:
    s_str = (
        series.astype(str)
        .str.strip()
        .str.split('T')
        .str[0]
        .str.split(' ')
        .str[0]
    )
    s_dt = pd.to_datetime(s_str, format='%Y-%m-%d', errors='coerce')
    missing_mask = (
        s_dt.isna()
        & series.notna()
        & ~series.astype(str).str.lower().isin(['nan', 'none', '', 'null'])
    )
    if missing_mask.any():
        s_dt.loc[missing_mask] = pd.to_datetime(
            series.loc[missing_mask], dayfirst=True, format='mixed', errors='coerce'
        )
    return s_dt.dt.strftime('%Y-%m-%d')


def convert_pace_to_decimal(pace_val):
    if pd.isna(pace_val):
        return np.nan
    if isinstance(pace_val, (int, float)):
        return round(float(pace_val), 2)
    if isinstance(pace_val, str) and ':' in pace_val:
        try:
            minutes, seconds = pace_val.split(':')
            return round(float(minutes) + (float(seconds) / 60.0), 2)
        except ValueError:
            return np.nan
    try:
        return round(float(pace_val), 2)
    except ValueError:
        return np.nan


def generate_quantified_self_csv(
    df_garmin: pd.DataFrame,
    df_withings: pd.DataFrame,
    df_medical: pd.DataFrame,
    df_activities: pd.DataFrame,
    df_zones: pd.DataFrame,
    output_path: str = 'drw_quantified_self.csv',
):

    # 1. Process Garmin Daily Data
    garmin_mapping = {
        'Date (YYYY-MM-DD)': 'Date_YYYY_MM_DD',
        'Date': 'Date_YYYY_MM_DD',
        'Total Running Distance (km)': 'Daily_Running_Distance_km',
        'Daily Steps': 'Daily_Steps_Count',
        'Garmin Training Load (7 Day Sum)': 'Garmin_7d_Training_Load_Sum',
        'VO2 Max (ml/kg/min)': 'Garmin_VO2_Max_ml_kg_min',
        'Lactate Threshold Pace (min/km)': 'Lactate_Threshold_Pace',
        'Lactate Threshold Heart Rate (bpm)': 'Lactate_Threshold_Heart_Rate_bpm',
        'Moderate Intensity Minutes': 'Garmin_Moderate_Intensity_Minutes',
        'Moderate Intensity Minutes (min)': 'Garmin_Moderate_Intensity_Minutes',
        'Garmin Moderate Intensity Minutes': 'Garmin_Moderate_Intensity_Minutes',
        'Vigorous Intensity Minutes': 'Garmin_Vigorous_Intensity_Minutes',
        'Vigorous Intensity Minutes (min)': 'Garmin_Vigorous_Intensity_Minutes',
        'Garmin Vigorous Intensity Minutes': 'Garmin_Vigorous_Intensity_Minutes',
        'Total Calories': 'Total_Calories',
        'Total Calories (kcal)': 'Total_Calories',
        'Calories': 'Total_Calories',
        'Active Calories': 'Active_Calories',
        'Active Calories (kcal)': 'Active_Calories',
        'Sleep Length (min)': 'Overnight_Sleep_Duration_min',
        'Sleep Need (min)': 'Sleep_Need_min',
        'Sleep Start Time': 'Sleep_Start_Time_HH_MM',
        'Garmin Sleep Score (0-100)': 'Garmin_Sleep_Score',
        'Daily Max Body Battery (0-100)': 'Morning_Max_Body_Battery',
        'Overnight Resting HR (bpm)': 'Overnight_Resting_Heart_Rate_bpm',
        'Overnight HRV (ms)': 'Overnight_Average_HRV_RMSSD_ms',
        'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
        'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg',
        'Overnight Respiration Rate (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Overnight Respiration (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Avg Overnight Respiration (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Respiration Rate (brpm)': 'Overnight_Respiration_Rate_brpm',
    }
    df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x))

    date_col_g = next(
        (
            c
            for c in ['Date_YYYY_MM_DD', 'Date (YYYY-MM-DD)', 'Date']
            if c in df_g.columns
        ),
        df_g.columns[0],
    )
    df_g['Date_YYYY_MM_DD'] = parse_to_iso_date(df_g[date_col_g])

    if 'Total_Calories' not in df_g.columns and df_garmin.shape[1] > 27:
        df_g['Total_Calories'] = df_garmin.iloc[:, 27]
    if (
        'Garmin_Moderate_Intensity_Minutes' not in df_g.columns
        and df_garmin.shape[1] > 43
    ):
        df_g['Garmin_Moderate_Intensity_Minutes'] = df_garmin.iloc[:, 43]
    if (
        'Garmin_Vigorous_Intensity_Minutes' not in df_g.columns
        and df_garmin.shape[1] > 44
    ):
        df_g['Garmin_Vigorous_Intensity_Minutes'] = df_garmin.iloc[:, 44]
    if 'Active_Calories' not in df_g.columns and df_garmin.shape[1] > 45:
        df_g['Active_Calories'] = df_garmin.iloc[:, 45]

    if 'Garmin_Avg_Awake_Stress_Score' not in df_g.columns and df_garmin.shape[1] > 55:
        df_g['Garmin_Avg_Awake_Stress_Score'] = pd.to_numeric(
            df_garmin.iloc[:, 55], errors='coerce'
        )

    if (
        'Overnight_Respiration_Rate_brpm' not in df_g.columns
        and df_garmin.shape[1] > 56
    ):
        df_g['Overnight_Respiration_Rate_brpm'] = pd.to_numeric(
            df_garmin.iloc[:, 56], errors='coerce'
        )

    df_g = df_g.loc[:, ~df_g.columns.duplicated()]

    # 2. Process Garmin Activities Data
    act_date_col = next(
        (
            c
            for c in ['Date (YYYY-MM-DD)', 'Date', 'Date_YYYY_MM_DD']
            if c in df_activities.columns
        ),
        df_activities.columns[0],
    )
    df_activities['Date_YYYY_MM_DD'] = parse_to_iso_date(
        df_activities[act_date_col]
    )
    
    # Calculate High Aerobic / Anaerobic Minutes
    hr_cols = [c for c in ['HR Zone 3 (min)', 'HR Zone 4 (min)', 'HR Zone 5 (min)'] if c in df_activities.columns]
    df_activities['High_Aerobic_Anaerobic_min'] = df_activities[hr_cols].sum(axis=1) if hr_cols else np.nan
    zone2_col = 'HR Zone 2 (min)' if 'HR Zone 2 (min)' in df_activities.columns else None

    # Filter for Running activities to calculate HR and Pace averages
    runs_mask = df_activities['Activity Type'].astype(str).str.contains('running', case=False, na=False)
    df_runs = df_activities[runs_mask].copy()
    
    if 'Avg Pace (min/km)' in df_runs.columns:
        df_runs['Run_Pace_Decimal'] = df_runs['Avg Pace (min/km)'].apply(convert_pace_to_decimal)
    else:
        df_runs['Run_Pace_Decimal'] = np.nan
        
    avg_hr_col = 'Avg HR (bpm)' if 'Avg HR (bpm)' in df_runs.columns else None
    
    df_runs_daily = df_runs.groupby('Date_YYYY_MM_DD').agg({
        avg_hr_col: 'mean' if avg_hr_col else lambda x: np.nan,
        'Run_Pace_Decimal': 'mean'
    }).reset_index().rename(columns={
        avg_hr_col: 'Daily_Avg_Run_HR_bpm',
        'Run_Pace_Decimal': 'Daily_Avg_Run_Pace_decimal'
    })

    agg_dict = {'Activity Training Load': 'sum', 'High_Aerobic_Anaerobic_min': 'sum'}
    if zone2_col:
        agg_dict[zone2_col] = 'sum'

    df_a_daily = df_activities.groupby('Date_YYYY_MM_DD').agg(agg_dict).reset_index()
    df_a_daily = df_a_daily.rename(columns={
        'Activity Training Load': 'Daily_Activity_Training_Load',
        zone2_col: 'HR_Zone_2_min'
    })
    
    df_a_daily = pd.merge(df_a_daily, df_runs_daily, on='Date_YYYY_MM_DD', how='left')

    # 3. Process Withings Data
    date_col_w = next(
        (
            c
            for c in ['date', 'Date', 'Date (YYYY-MM-DD)']
            if c in df_withings.columns
        ),
        df_withings.columns[0],
    )
    df_withings['Date_YYYY_MM_DD'] = parse_to_iso_date(df_withings[date_col_w])

    weight_col = (
        'Weight (kg)'
        if 'Weight (kg)' in df_withings.columns
        else df_withings.columns[1]
    )
    pwv_col = (
        'Pulse Wave Velocity (m/s)'
        if 'Pulse Wave Velocity (m/s)' in df_withings.columns
        else (
            df_withings.columns[4]
            if df_withings.shape[1] > 4
            else df_withings.columns[3]
        )
    )
    fat_col = (
        'Fat Ratio (%)'
        if 'Fat Ratio (%)' in df_withings.columns
        else (
            'Body Fat (%)'
            if 'Body Fat (%)' in df_withings.columns
            else (
                'Fat Mass (%)'
                if 'Fat Mass (%)' in df_withings.columns
                else (
                    df_withings.columns[3]
                    if df_withings.shape[1] > 3
                    else df_withings.columns[-1]
                )
            )
        )
    )

    df_w_daily = (
        df_withings.groupby('Date_YYYY_MM_DD')
        .agg({weight_col: 'mean', pwv_col: 'mean', fat_col: 'mean'})
        .reset_index()
    )

    withings_mapping = {
        weight_col: 'Daily_Morning_Weight_kg',
        pwv_col: 'Pulse_Wave_Velocity_m_s',
        fat_col: 'Daily_Body_Fat_pct',
    }
    df_w_daily = df_w_daily.rename(columns=withings_mapping)

    # 4. Process Medical Data
    df_med = df_medical.copy()
    df_med['Date_YYYY_MM_DD'] = parse_to_iso_date(df_med.iloc[:, 0])

    sig_col = df_med.iloc[:, 3]
    is_significant = (pd.to_numeric(sig_col, errors='coerce') == 1) | (
        sig_col.astype(str).str.strip().isin(['1', '1.0', 'True', 'true'])
    )
    df_med_filtered = df_med[is_significant].copy()

    if not df_med_filtered.empty:
        df_med_filtered['Medical_Notes'] = (
            df_med_filtered.iloc[:, 4].astype(str).str.strip()
        )
        df_med_filtered = df_med_filtered[
            ~df_med_filtered['Medical_Notes']
            .str.lower()
            .isin(['nan', 'none', '', 'null'])
        ]
        df_m_daily = (
            df_med_filtered.groupby('Date_YYYY_MM_DD')['Medical_Notes']
            .apply(lambda x: ' | '.join(x))
            .reset_index()
        )
    else:
        df_m_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Medical_Notes'])

    # 5. Process Home Assistant Zone Data
    zone_date_col = next(
        (
            c
            for c in ['Date', 'date', 'Date (YYYY-MM-DD)']
            if c in df_zones.columns
        ),
        df_zones.columns[0],
    )
    df_zones['Date_YYYY_MM_DD'] = parse_to_iso_date(df_zones[zone_date_col])

    zone_mapping = {
        'Time in Home Zone (hours)': 'Time_in_Home_Zone_hours',
        'Time in Work Zone (hours)': 'Time_in_Work_Zone_hours',
    }
    avail_zone_cols = ['Date_YYYY_MM_DD'] + [
        v for k, v in zone_mapping.items() if k in df_zones.columns
    ]
    df_z_daily = df_zones.rename(columns=zone_mapping)[avail_zone_cols]

    # 6. Merge All Datasets
    cols_to_merge = ['Date_YYYY_MM_DD', 'Daily_Activity_Training_Load']
    for col in ['HR_Zone_2_min', 'High_Aerobic_Anaerobic_min', 'Daily_Avg_Run_HR_bpm', 'Daily_Avg_Run_Pace_decimal']:
        if col in df_a_daily.columns:
            cols_to_merge.append(col)
            
    df = pd.merge(
        df_g,
        df_a_daily[cols_to_merge],
        on='Date_YYYY_MM_DD',
        how='outer',
    )
    df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')

    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df['_sort_date'] = pd.to_datetime(
        df['Date_YYYY_MM_DD'], format='%Y-%m-%d', errors='coerce'
    )
    df = df.dropna(subset=['_sort_date'])
    df = df.sort_values(by='_sort_date', ascending=True).reset_index(drop=True)
    df = df.drop(columns=['_sort_date'])
    df = df.loc[:, ~df.columns.duplicated()]
    df['Daily_Activity_Training_Load'] = df[
        'Daily_Activity_Training_Load'
    ].fillna(0)

    # Convert date for accurate time-aware EWMAs
    df['Date_Datetime'] = pd.to_datetime(df['Date_YYYY_MM_DD'])

    # 7. Derived Metrics & Precision
    
    # 28-Day Load and ACWR
    df['Garmin_28d_Training_Load_Sum'] = df['Daily_Activity_Training_Load'].rolling(window=28, min_periods=7).sum()
    if 'Garmin_7d_Training_Load_Sum' in df.columns:
        df['ACWR'] = df['Garmin_7d_Training_Load_Sum'] / df['Garmin_28d_Training_Load_Sum']
        
    # Aerobic Efficiency Factor
    if 'Daily_Avg_Run_Pace_decimal' in df.columns and 'Daily_Avg_Run_HR_bpm' in df.columns:
        df['Aerobic_Efficiency_Factor'] = df['Daily_Avg_Run_Pace_decimal'] / df['Daily_Avg_Run_HR_bpm']
        
    if 'Lactate_Threshold_Pace' in df.columns:
        df['Lactate_Threshold_Pace_decimal_min_km'] = df[
            'Lactate_Threshold_Pace'
        ].apply(convert_pace_to_decimal)

    def time_to_decimal(time_str):
        if pd.isna(time_str):
            return np.nan
        try:
            h, m = map(int, str(time_str).split(':'))
            if h < 12:
                h += 24
            return round(h + (m / 60.0), 2)
        except ValueError:
            return np.nan

    if 'Sleep_Start_Time_HH_MM' in df.columns:
        df['Sleep_Start_Decimal'] = df['Sleep_Start_Time_HH_MM'].apply(
            time_to_decimal
        )

    # Architectural Pillar 1: Accumulated Sleep Deficit (EWMA)
    if 'Overnight_Sleep_Duration_min' in df.columns and 'Sleep_Need_min' in df.columns:
        sleep_target = df['Sleep_Need_min'].fillna(480)
        daily_sleep_deficit = (sleep_target - df['Overnight_Sleep_Duration_min']).clip(lower=0)
        
        df['EWMA_Sleep_Deficit_min'] = daily_sleep_deficit.ewm(
            halflife=pd.Timedelta(days=4), 
            times=df['Date_Datetime']
        ).mean()

    # Clean Sleep Deficit (14d EWMA)
    if 'Overnight_Sleep_Duration_min' in df.columns:
        df['Daily_Clean_Sleep_Deficit'] = (480 - df['Overnight_Sleep_Duration_min']).clip(lower=0)
        df['EWMA_14d_Clean_Sleep_Deficit_min'] = df['Daily_Clean_Sleep_Deficit'].ewm(
            halflife=pd.Timedelta(days=14), 
            times=df['Date_Datetime']
        ).mean()

    # Sleep Start Time Variance (7d Rolling Std Dev)
    if 'Sleep_Start_Decimal' in df.columns:
        df['Sleep_Start_7d_Variance'] = df['Sleep_Start_Decimal'].rolling(window=7, min_periods=3).std()

    # Resting Heart Rate Baseline and Z-Score Calculation
    if 'Overnight_Resting_Heart_Rate_bpm' in df.columns:
        shifted_rhr = df['Overnight_Resting_Heart_Rate_bpm'].shift(7)
        shifted_60d_rhr_mean = shifted_rhr.rolling(window=60, min_periods=30).mean()
        shifted_60d_rhr_std = shifted_rhr.rolling(window=60, min_periods=30).std()
        
        df['Daily_RHR_ZScore'] = (df['Overnight_Resting_Heart_Rate_bpm'] - shifted_60d_rhr_mean) / shifted_60d_rhr_std
        df['EWMA_RHR_ZScore'] = df['Daily_RHR_ZScore'].ewm(
            halflife=pd.Timedelta(days=2), 
            times=df['Date_Datetime']
        ).mean()

    # HRV Baseline and Z-Score Calculation
    if 'Overnight_Average_HRV_RMSSD_ms' in df.columns:
        hrv_7d_avg = (
            df['Overnight_Average_HRV_RMSSD_ms']
            .rolling(window=7, min_periods=1)
            .mean()
        )
        shifted_hrv = df['Overnight_Average_HRV_RMSSD_ms'].shift(7)
        shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
        shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()
        df[
            'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore'
        ] = ((hrv_7d_avg - shifted_60d_mean) / shifted_60d_std).round(2)

        df['Daily_HRV_ZScore'] = (df['Overnight_Average_HRV_RMSSD_ms'] - shifted_60d_mean) / shifted_60d_std
        df['EWMA_HRV_ZScore'] = df['Daily_HRV_ZScore'].ewm(
            halflife=pd.Timedelta(days=2), 
            times=df['Date_Datetime']
        ).mean()

    if 'Daily_Morning_Weight_kg' in df.columns:
        df['Daily_Morning_Weight_7d_Average_kg'] = (
            df['Daily_Morning_Weight_kg']
            .rolling(window=7, min_periods=1)
            .mean()
            .round(2)
        )

    if 'Daily_Body_Fat_pct' in df.columns:
        df['Body_Fat_7d_Average_pct'] = (
            df['Daily_Body_Fat_pct']
            .rolling(window=7, min_periods=1)
            .mean()
            .round(2)
        )

    if 'Sleep_Start_Decimal' in df.columns:
        df['Sleep_Start_14d_Median'] = df['Sleep_Start_Decimal'].rolling(window=14, min_periods=7).median().shift(1)
        df['Circadian_Difference_hours'] = (df['Sleep_Start_Decimal'] - df['Sleep_Start_14d_Median']).abs()

    # Integrated Dual-Timescale Morning State Composite Recovery Score
    if (
        'EWMA_HRV_ZScore' in df.columns
        and 'EWMA_RHR_ZScore' in df.columns
        and 'EWMA_Sleep_Deficit_min' in df.columns
        and 'Garmin_Sleep_Score' in df.columns
        and 'Morning_Max_Body_Battery' in df.columns
        and 'Circadian_Difference_hours' in df.columns
    ):
        # --- Accumulated State Variables (60% Weight) ---
        
        # 1. Autonomic/CV History (HRV + RHR EWMA) combined geometrically 
        h_raw = np.where(pd.isna(df['EWMA_HRV_ZScore']), np.nan, 
                         np.where(df['EWMA_HRV_ZScore'] >= 1.0, 1.0, 
                         np.where(df['EWMA_HRV_ZScore'] >= 0, 0.90 + (df['EWMA_HRV_ZScore'] / 1.0) * 0.10, 
                         np.where(df['EWMA_HRV_ZScore'] <= -1.5, 0.0, (df['EWMA_HRV_ZScore'] + 1.5) / 1.5 * 0.90))))
        
        rhr_raw = np.where(pd.isna(df['EWMA_RHR_ZScore']), np.nan,
                           np.where(df['EWMA_RHR_ZScore'] <= 0.5, 1.0, 
                           np.where(df['EWMA_RHR_ZScore'] >= 2.0, 0.0, 
                           (2.0 - df['EWMA_RHR_ZScore']) / 1.5)))
        
        a_history_raw = (h_raw ** 0.6) * (rhr_raw ** 0.4)

        # 2. Sleep Deficit History (Exponential Decay Penalty)
        s_history_raw = np.where(pd.isna(df['EWMA_Sleep_Deficit_min']), np.nan,
                                 np.exp(-df['EWMA_Sleep_Deficit_min'] / 90.0))


        # --- Acute State Variables (35% Weight) ---
        
        # 3. Acute Sleep Restoration
        s_acute_raw = df['Garmin_Sleep_Score'] / 100.0

        # 4. Morning Energy
        bb_raw = df['Morning_Max_Body_Battery'] / 100.0


        # --- Context Variable (5% Weight) ---
        
        # 5. Circadian Regularity
        c_raw = np.where(pd.isna(df['Circadian_Difference_hours']), np.nan,
                         np.where(df['Circadian_Difference_hours'] <= 0.5, 1.0,
                         np.where(df['Circadian_Difference_hours'] >= 1.5, 0.0,
                         (1.5 - df['Circadian_Difference_hours']) / 1.0)))


        # Apply Floors to prevent single zeros from collapsing the geometric multiplication
        a_history_floored = 0.25 + (0.75 * a_history_raw)
        s_history_floored = 0.15 + (0.85 * s_history_raw)
        s_acute_floored = 0.15 + (0.85 * s_acute_raw)
        bb_floored = 0.10 + (0.90 * bb_raw)
        c_floored = 0.05 + (0.95 * c_raw)

        # Weighted Geometric Mean
        # S_history (30%), A_history (30%), S_acute (25%), Body Battery (10%), Timing (5%)
        df['Composite_Recovery_Score'] = 100 * (s_history_floored ** 0.30) * (a_history_floored ** 0.30) * (s_acute_floored ** 0.25) * (bb_floored ** 0.10) * (c_floored ** 0.05)

    # 8. Filter, Sort Descending, and Select Target Columns
    df_export = df.tail(730).copy()
    df_export['_sort_date'] = pd.to_datetime(
        df_export['Date_YYYY_MM_DD'], format='%Y-%m-%d', errors='coerce'
    )
    df_export = df_export.sort_values(
        by='_sort_date', ascending=False
    ).reset_index(drop=True)
    df_export = df_export.drop(columns=['_sort_date'])

    required_columns = [
        'Date_YYYY_MM_DD',
        'Time_in_Home_Zone_hours',
        'Time_in_Work_Zone_hours',
        'Daily_Steps_Count',
        'Daily_Running_Distance_km',
        'Garmin_Moderate_Intensity_Minutes',
        'Garmin_Vigorous_Intensity_Minutes',
        'Garmin_Avg_Awake_Stress_Score',
        'Daily_Activity_Training_Load',
        'Garmin_7d_Training_Load_Sum',
        'Garmin_28d_Training_Load_Sum',
        'ACWR',
        'Garmin_VO2_Max_ml_kg_min',
        'Daily_Avg_Run_HR_bpm',
        'Aerobic_Efficiency_Factor',
        'HR_Zone_2_min',
        'High_Aerobic_Anaerobic_min',
        'Lactate_Threshold_Heart_Rate_bpm',
        'Lactate_Threshold_Pace_decimal_min_km',
        'Overnight_Sleep_Duration_min',
        'Garmin_Sleep_Score',
        'Sleep_Start_Decimal',
        'Sleep_Start_7d_Variance',
        'EWMA_Sleep_Deficit_min',
        'EWMA_14d_Clean_Sleep_Deficit_min',
        'Overnight_Resting_Heart_Rate_bpm',
        'EWMA_RHR_ZScore',
        'Overnight_Average_HRV_RMSSD_ms',
        'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore',
        'Morning_Max_Body_Battery',
        'Daily_Morning_Weight_7d_Average_kg',
        'Resting_Systolic_Blood_Pressure_mmHg',
        'Resting_Diastolic_Blood_Pressure_mmHg',
        'Pulse_Wave_Velocity_m_s',
        'Overnight_Respiration_Rate_brpm',
        'Body_Fat_7d_Average_pct',
        'Composite_Recovery_Score',
        'Medical_Notes',
    ]

    for col in required_columns:
        if col not in df_export.columns:
            df_export[col] = np.nan

    df_export = df_export[required_columns]

    column_rename_map = {
        'Date_YYYY_MM_DD': 'Date (YYYY-MM-DD)',
        'Time_in_Home_Zone_hours': 'Time at Home (hours)',
        'Time_in_Work_Zone_hours': 'Time at Work (hours)',
        'Daily_Steps_Count': 'Step Count - Daily (steps)',
        'Daily_Running_Distance_km': 'Running Distance - Daily (km)',
        'Garmin_Moderate_Intensity_Minutes': (
            'Moderate Intensity Minutes - Garmin (min)'
        ),
        'Garmin_Vigorous_Intensity_Minutes': (
            'Vigorous Intensity Minutes - Garmin (min)'
        ),
        'Garmin_Avg_Awake_Stress_Score': 'Average Awake Hours Garmin Stress Score (0-100)',
        'Daily_Activity_Training_Load': 'Exercise Load - Daily Sum',
        'Garmin_7d_Training_Load_Sum': 'Training Load - Garmin 7d Sum',
        'Garmin_28d_Training_Load_Sum': 'Chronic Training Load (28-Day Sum)',
        'ACWR': 'Acute-to-Chronic Workload Ratio (ACWR)',
        'Garmin_VO2_Max_ml_kg_min': 'VO2 Max - Garmin (ml/kg/min)',
        'Daily_Avg_Run_HR_bpm': 'Average Heart Rate for Runs (bpm)',
        'Aerobic_Efficiency_Factor': 'Aerobic Efficiency Factor (Pace/HR)',
        'HR_Zone_2_min': 'Time in HR Zone 2 - Low Aerobic (min)',
        'High_Aerobic_Anaerobic_min': 'Time in HR Zones 3-5 - High Aerobic/Anaerobic (min)',
        'Lactate_Threshold_Heart_Rate_bpm': 'Lactate Threshold HR (bpm)',
        'Lactate_Threshold_Pace_decimal_min_km': (
            'Lactate Threshold Pace (decimal min/km)'
        ),
        'Overnight_Sleep_Duration_min': 'Sleep Duration - Overnight (min)',
        'Garmin_Sleep_Score': 'Sleep Score - Garmin (0-100)',
        'Sleep_Start_Decimal': 'Sleep Start Time (Decimal)',
        'Sleep_Start_7d_Variance': 'Sleep Start Time Variance (7d Rolling Std Dev)',
        'EWMA_Sleep_Deficit_min': 'Sleep Deficit - 4d EWMA (min)',
        'EWMA_14d_Clean_Sleep_Deficit_min': 'Clean Sleep Deficit - 14d EWMA (min)',
        'Overnight_Resting_Heart_Rate_bpm': 'Resting Heart Rate - Overnight (bpm)',
        'EWMA_RHR_ZScore': 'Resting HR Z-Score - 2d EWMA vs 60d Baseline',
        'Overnight_Average_HRV_RMSSD_ms': 'HRV RMSSD - Overnight (ms)',
        'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore': (
            'HRV RMSSD Z-Score - 7d Avg vs 60d Baseline'
        ),
        'Morning_Max_Body_Battery': 'Morning Max Body Battery (0-100)',
        'Daily_Morning_Weight_7d_Average_kg': 'Weight - Morning 7d Avg (kg)',
        'Resting_Systolic_Blood_Pressure_mmHg': (
            'Blood Pressure Systolic - Resting (mmHg)'
        ),
        'Resting_Diastolic_Blood_Pressure_mmHg': (
            'Blood Pressure Diastolic - Resting (mmHg)'
        ),
        'Pulse_Wave_Velocity_m_s': 'Pulse Wave Velocity (m/s)',
        'Overnight_Respiration_Rate_brpm': 'Overnight Respiration Rate (brpm)',
        'Body_Fat_7d_Average_pct': 'Body Fat % - Withings Body Scan US Army Calibrated 7d Avg',
        'Composite_Recovery_Score': 'Composite Recovery Score (0-100)',
        'Medical_Notes': 'Medical Note',
    }

    df_export = df_export.rename(columns=column_rename_map)
    df_export = df_export.loc[:, ~df_export.columns.duplicated()]

    # 9. Strict Type & Decimal Precision Formatting
    integer_columns = [
        'Step Count - Daily (steps)',
        'Moderate Intensity Minutes - Garmin (min)',
        'Vigorous Intensity Minutes - Garmin (min)',
        'Exercise Load - Daily Sum',
        'Training Load - Garmin 7d Sum',
        'Chronic Training Load (28-Day Sum)',
        'Average Heart Rate for Runs (bpm)',
        'Time in HR Zone 2 - Low Aerobic (min)',
        'Time in HR Zones 3-5 - High Aerobic/Anaerobic (min)',
        'Lactate Threshold HR (bpm)',
        'Sleep Duration - Overnight (min)',
        'Sleep Score - Garmin (0-100)',
        'Sleep Deficit - 4d EWMA (min)',
        'Clean Sleep Deficit - 14d EWMA (min)',
        'Resting Heart Rate - Overnight (bpm)',
        'HRV RMSSD - Overnight (ms)',
        'Morning Max Body Battery (0-100)',
        'Blood Pressure Systolic - Resting (mmHg)',
        'Blood Pressure Diastolic - Resting (mmHg)',
        'Composite Recovery Score (0-100)',
    ]
    for col in integer_columns:
        if col in df_export.columns:
            df_export[col] = (
                pd.to_numeric(df_export[col], errors='coerce').round().astype('Int64')
            )

    float_1dp_columns = [
        'Time at Home (hours)',
        'Time at Work (hours)',
        'VO2 Max - Garmin (ml/kg/min)',
        'Average Awake Hours Garmin Stress Score (0-100)',
        'Overnight Respiration Rate (brpm)',
    ]
    for col in float_1dp_columns:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(1)

    float_2dp_columns = [
        'Running Distance - Daily (km)',
        'Acute-to-Chronic Workload Ratio (ACWR)',
        'Aerobic Efficiency Factor (Pace/HR)',
        'Lactate Threshold Pace (decimal min/km)',
        'Sleep Start Time (Decimal)',
        'Sleep Start Time Variance (7d Rolling Std Dev)',
        'Resting HR Z-Score - 2d EWMA vs 60d Baseline',
        'HRV RMSSD Z-Score - 7d Avg vs 60d Baseline',
        'Weight - Morning 7d Avg (kg)',
        'Pulse Wave Velocity (m/s)',
        'Body Fat % - Withings Body Scan US Army Calibrated 7d Avg',
    ]
    for col in float_2dp_columns:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(2)

    # 10. Write Out Clean CSV
    df_export.to_csv(output_path, header=True, index=False, na_rep='')
    return df_export


def get_file_id(service, filename, folder_id):
    safe_filename = filename.replace("'", "\\'")
    query = f"name='{safe_filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None


def download_drive_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    downloaded_data = io.BytesIO()
    downloader = MediaIoBaseDownload(downloaded_data, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    downloaded_data.seek(0)
    return downloaded_data


if __name__ == '__main__':
    FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
    SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
    GARMIN_FILENAME = 'drw_garmin_data.csv'
    ACTIVITIES_FILENAME = 'drw_garmin_activities_list.csv'
    WITHINGS_FILENAME = 'drw_withings_bodyscan_data.csv'
    MEDICAL_FILENAME = "Daniel's Full Medical Notes.csv"

    ZONES_BASE_URL = 'https://dfexhoblv7ytpsxp7uiasfchbdxbl8vt.ui.nabu.casa/local/drw_home_assistant_zone_history.csv'
    ZONES_URL = f'{ZONES_BASE_URL}?v={int(time.time())}'

    TARGET_FILENAME = 'drw_quantified_self.csv'

    if not FOLDER_ID:
        raise ValueError('DRIVE_FOLDER_ID environment variable is not set.')
    if not SERVICE_ACCOUNT_JSON:
        raise ValueError(
            'GOOGLE_SHEETS_CREDENTIALS environment variable is not set.'
        )

    print('Authenticating with Google Drive...')
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    drive_service = build('drive', 'v3', credentials=creds)

    print(f'Locating files in folder {FOLDER_ID}...')
    garmin_file_id = get_file_id(drive_service, GARMIN_FILENAME, FOLDER_ID)
    activities_file_id = get_file_id(
        drive_service, ACTIVITIES_FILENAME, FOLDER_ID
    )
    withings_file_id = get_file_id(drive_service, WITHINGS_FILENAME, FOLDER_ID)
    medical_file_id = get_file_id(drive_service, MEDICAL_FILENAME, FOLDER_ID)

    if not medical_file_id:
        medical_file_id = get_file_id(
            drive_service, "Daniel's Medical Test Results.csv", FOLDER_ID
        )

    target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)

    if not garmin_file_id:
        raise FileNotFoundError(f"Could not find '{GARMIN_FILENAME}' in Drive.")
    if not activities_file_id:
        raise FileNotFoundError(
            f"Could not find '{ACTIVITIES_FILENAME}' in Drive."
        )
    if not withings_file_id:
        raise FileNotFoundError(f"Could not find '{WITHINGS_FILENAME}' in Drive.")
    if not medical_file_id:
        raise FileNotFoundError(f"Could not find '{MEDICAL_FILENAME}' in Drive.")

    print('Downloading raw data from Google Drive and Home Assistant...')
    garmin_data = download_drive_file(drive_service, garmin_file_id)
    activities_data = download_drive_file(drive_service, activities_file_id)
    withings_data = download_drive_file(drive_service, withings_file_id)
    medical_data = download_drive_file(drive_service, medical_file_id)

    df_garmin_raw = pd.read_csv(garmin_data)
    df_activities_raw = pd.read_csv(activities_data)
    df_withings_raw = pd.read_csv(withings_data)
    df_medical_raw = pd.read_csv(medical_data)
    df_zones_raw = pd.read_csv(ZONES_URL)

    print('Processing physiological metrics...')
    generate_quantified_self_csv(
        df_garmin_raw,
        df_withings_raw,
        df_medical_raw,
        df_activities_raw,
        df_zones_raw,
        output_path=TARGET_FILENAME,
    )

    print('Uploading updated CSV to Google Drive...')
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)

    if target_file_id:
        drive_service.files().update(
            fileId=target_file_id, media_body=media
        ).execute()
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID]}
        drive_service.files().create(
            body=file_metadata, media_body=media
        ).execute()

    print('Export and upload complete.')
