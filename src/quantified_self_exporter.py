import io
import json
import os
import time
import urllib.request
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
            parts = pace_val.strip().split(':')
            if len(parts) == 2:
                minutes, seconds = parts
                return round(float(minutes) + (float(seconds) / 60.0), 2)
            elif len(parts) == 3:
                hours, minutes, seconds = parts
                return round(float(hours) * 60.0 + float(minutes) + (float(seconds) / 60.0), 2)
        except ValueError:
            return np.nan
    try:
        return round(float(pace_val), 2)
    except ValueError:
        return np.nan


def parse_duration_to_minutes(val):
    if pd.isna(val):
        return np.nan
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ['nan', 'none', '', 'null']:
        return np.nan
    if ':' in val_str:
        parts = val_str.split(':')
        try:
            if len(parts) == 3:
                return round(float(parts[0]) * 60.0 + float(parts[1]) + (float(parts[2]) / 60.0), 2)
            elif len(parts) == 2:
                return round(float(parts[0]) + (float(parts[1]) / 60.0), 2)
        except ValueError:
            return np.nan
    try:
        return round(float(val_str), 2)
    except ValueError:
        return np.nan


def find_column_by_keywords(df: pd.DataFrame, include_keywords: list, exclude_keywords: list = None):
    for col in df.columns:
        col_lower = str(col).lower()
        if all(kw in col_lower for kw in include_keywords):
            if exclude_keywords and any(ex in col_lower for ex in exclude_keywords):
                continue
            return col
    return None


def load_zones_data(url: str) -> pd.DataFrame:
    fallback_df = pd.DataFrame(columns=['Date', 'Time in Work Zone (hours)'])
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status != 200:
                print(f"Warning: HTTP status {response.status} when fetching zone history.")
                return fallback_df
            raw_bytes = response.read()

        preview = raw_bytes[:300].decode('utf-8', errors='ignore').strip().lower()
        if preview.startswith('<!doctype') or '<html' in preview:
            print("Warning: Zone endpoint returned HTML instead of CSV.")
            return fallback_df

        df = pd.read_csv(
            io.BytesIO(raw_bytes),
            on_bad_lines='skip',
            engine='python'
        )
        return df
    except Exception as e:
        print(f"Warning: Failed to retrieve Home Assistant zone data ({e}).")
        return fallback_df


def generate_quantified_self_csv(
    df_garmin: pd.DataFrame,
    df_withings: pd.DataFrame,
    df_medical: pd.DataFrame,
    df_activities: pd.DataFrame,
    df_zones: pd.DataFrame,
    output_path: str = 'drw_quantified_self.csv',
):
    # ---------------------------------------------------------
    # 1. Process Garmin Daily Data
    # ---------------------------------------------------------
    garmin_mapping = {
        'Date (YYYY-MM-DD)': 'Date_YYYY_MM_DD',
        'Date': 'Date_YYYY_MM_DD',
        'Total Running Distance (km)': 'Daily_Running_Distance_km',
        'Daily Steps': 'Daily_Steps_Count',
        'VO2 Max (ml/kg/min)': 'Garmin_VO2_Max_ml_kg_min',
        'Lactate Threshold Pace (min/km)': 'Lactate_Threshold_Pace',
        'Moderate Intensity Minutes': 'Garmin_Moderate_Intensity_Minutes',
        'Moderate Intensity Minutes (min)': 'Garmin_Moderate_Intensity_Minutes',
        'Garmin Moderate Intensity Minutes': 'Garmin_Moderate_Intensity_Minutes',
        'Vigorous Intensity Minutes': 'Garmin_Vigorous_Intensity_Minutes',
        'Vigorous Intensity Minutes (min)': 'Garmin_Vigorous_Intensity_Minutes',
        'Garmin Vigorous Intensity Minutes': 'Garmin_Vigorous_Intensity_Minutes',
        'Sleep Length (min)': 'Overnight_Sleep_Duration_min',
        'Sleep Need (min)': 'Sleep_Need_min',
        'Sleep Start Time': 'Sleep_Start_Time_HH_MM',
        'Garmin Sleep Score (0-100)': 'Garmin_Sleep_Score',
        'Overnight Resting HR (bpm)': 'Overnight_Resting_Heart_Rate_bpm',
        'Overnight HRV (ms)': 'Overnight_Average_HRV_RMSSD_ms',
        'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
        'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg',
        'Overnight Respiration Rate (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Overnight Respiration (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Avg Overnight Respiration (brpm)': 'Overnight_Respiration_Rate_brpm',
        'Respiration Rate (brpm)': 'Overnight_Respiration_Rate_brpm',
        # Direct daily aerobic & anaerobic training load mapping
        'Garmin Low Aerobic Exercise Load - Daily Sum (Score)': 'Garmin_Low_Aerobic_Daily_Sum',
        'Garmin High Aerobic Exercise Load - Daily Sum (Score)': 'Garmin_High_Aerobic_Daily_Sum',
        'Garmin Anaerobic Exercise Load - Daily Sum (Score)': 'Garmin_Anaerobic_Daily_Sum',
        'Low Aerobic Load': 'Garmin_Low_Aerobic_Daily_Sum',
        'High Aerobic Load': 'Garmin_High_Aerobic_Daily_Sum',
        'Anaerobic Load': 'Garmin_Anaerobic_Daily_Sum',
        'Low Aerobic Training Load': 'Garmin_Low_Aerobic_Daily_Sum',
        'High Aerobic Training Load': 'Garmin_High_Aerobic_Daily_Sum',
        'Anaerobic Training Load': 'Garmin_Anaerobic_Daily_Sum',
    }

    df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x)).copy()
    date_col_g = next(
        (c for c in ['Date_YYYY_MM_DD', 'Date (YYYY-MM-DD)', 'Date'] if c in df_g.columns),
        df_g.columns[0],
    )
    df_g['Date_YYYY_MM_DD'] = parse_to_iso_date(df_g[date_col_g])

    if 'Garmin_Moderate_Intensity_Minutes' not in df_g.columns and df_garmin.shape[1] > 43:
        df_g['Garmin_Moderate_Intensity_Minutes'] = df_garmin.iloc[:, 43]
    if 'Garmin_Vigorous_Intensity_Minutes' not in df_g.columns and df_garmin.shape[1] > 44:
        df_g['Garmin_Vigorous_Intensity_Minutes'] = df_garmin.iloc[:, 44]

    waking_stress_col = find_column_by_keywords(df_garmin, ['stress'], exclude_keywords=['sleep', 'rest'])
    if waking_stress_col:
        df_g['Garmin_Waking_Average_Stress_Score'] = pd.to_numeric(df_garmin[waking_stress_col], errors='coerce')
    elif df_garmin.shape[1] > 55:
        df_g['Garmin_Waking_Average_Stress_Score'] = pd.to_numeric(df_garmin.iloc[:, 55], errors='coerce')

    if 'Overnight_Respiration_Rate_brpm' not in df_g.columns and df_garmin.shape[1] > 56:
        df_g['Overnight_Respiration_Rate_brpm'] = pd.to_numeric(df_garmin.iloc[:, 56], errors='coerce')

    df_g = df_g.loc[:, ~df_g.columns.duplicated()]

    # ---------------------------------------------------------
    # 2. Process Garmin Activities Data
    # ---------------------------------------------------------
    act_date_col = next(
        (c for c in ['Date (YYYY-MM-DD)', 'Date', 'Date_YYYY_MM_DD'] if c in df_activities.columns),
        df_activities.columns[0],
    )
    df_act = df_activities.copy()
    df_act['Date_YYYY_MM_DD'] = parse_to_iso_date(df_act[act_date_col])

    activity_type_col = next((c for c in df_act.columns if 'activity type' in c.lower() or c.lower() == 'type'), None)
    load_col = next(
        (c for c in df_act.columns if 'activity training load' in c.lower() or 'exercise load' in c.lower() or c.lower() == 'training load'),
        None,
    )
    if load_col:
        df_act['Activity_Load_Numeric'] = pd.to_numeric(df_act[load_col], errors='coerce').fillna(0)
    else:
        df_act['Activity_Load_Numeric'] = 0.0

    # Independent column lookup for training loads
    low_col = find_column_by_keywords(df_act, ['low', 'aerobic']) or find_column_by_keywords(df_act, ['low_aerobic'])
    high_col = find_column_by_keywords(df_act, ['high', 'aerobic']) or find_column_by_keywords(df_act, ['high_aerobic'])
    anaerobic_col = find_column_by_keywords(df_act, ['anaerobic'], exclude_keywords=['high', 'low'])

    if low_col:
        df_act['Low_Aerobic_Load'] = pd.to_numeric(df_act[low_col], errors='coerce').fillna(0)
    if high_col:
        df_act['High_Aerobic_Load'] = pd.to_numeric(df_act[high_col], errors='coerce').fillna(0)
    if anaerobic_col:
        df_act['Anaerobic_Load'] = pd.to_numeric(df_act[anaerobic_col], errors='coerce').fillna(0)

    # Fallback using benefit descriptor if individual load columns do not exist
    benefit_col = next((c for c in df_act.columns if 'benefit' in c.lower() or 'training effect' in c.lower()), None)
    if benefit_col:
        b_str = df_act[benefit_col].astype(str).str.lower()
        if 'Low_Aerobic_Load' not in df_act.columns:
            df_act['Low_Aerobic_Load'] = np.where(b_str.str.contains('recovery|base|low aerobic'), df_act['Activity_Load_Numeric'], 0.0)
        if 'High_Aerobic_Load' not in df_act.columns:
            df_act['High_Aerobic_Load'] = np.where(b_str.str.contains('tempo|threshold|vo2|high aerobic'), df_act['Activity_Load_Numeric'], 0.0)
        if 'Anaerobic_Load' not in df_act.columns:
            df_act['Anaerobic_Load'] = np.where(b_str.str.contains('sprint|anaerobic'), df_act['Activity_Load_Numeric'], 0.0)

    for col in ['Low_Aerobic_Load', 'High_Aerobic_Load', 'Anaerobic_Load']:
        if col not in df_act.columns:
            df_act[col] = 0.0

    duration_col = next(
        (c for c in df_act.columns if any(k in c.lower() for k in ['duration', 'elapsed time', 'time']) and 'zone' not in c.lower() and 'work' not in c.lower()),
        None,
    )
    if activity_type_col and duration_col:
        strength_mask = df_act[activity_type_col].astype(str).str.contains('strength|weight|resistance', case=False, na=False)
        df_act['Strength_Duration_min'] = np.where(
            strength_mask,
            df_act[duration_col].apply(parse_duration_to_minutes),
            0.0,
        )
    else:
        df_act['Strength_Duration_min'] = 0.0

    if activity_type_col:
        runs_mask = df_act[activity_type_col].astype(str).str.contains('run', case=False, na=False)
    else:
        runs_mask = pd.Series(True, index=df_act.index)

    df_runs = df_act[runs_mask].copy()
    gap_col = find_column_by_keywords(df_runs, ['gap']) or find_column_by_keywords(df_runs, ['grade', 'adjusted'])
    if not gap_col:
        gap_col = next((c for c in df_runs.columns if 'pace' in c.lower() and 'lactate' not in c.lower()), None)

    if gap_col:
        df_runs['Run_GAP_Decimal'] = df_runs[gap_col].apply(convert_pace_to_decimal)
    else:
        df_runs['Run_GAP_Decimal'] = np.nan

    df_runs_daily = (
        df_runs.groupby('Date_YYYY_MM_DD')['Run_GAP_Decimal']
        .mean()
        .reset_index()
        .rename(columns={'Run_GAP_Decimal': 'Daily_Avg_Run_GAP_decimal'})
    )

    df_a_daily = (
        df_act.groupby('Date_YYYY_MM_DD')
        .agg({
            'Activity_Load_Numeric': 'sum',
            'Low_Aerobic_Load': 'sum',
            'High_Aerobic_Load': 'sum',
            'Anaerobic_Load': 'sum',
            'Strength_Duration_min': 'sum',
        })
        .reset_index()
        .rename(columns={
            'Activity_Load_Numeric': 'Daily_Activity_Training_Load',
            'Low_Aerobic_Load': 'Garmin_Low_Aerobic_Daily_Sum',
            'High_Aerobic_Load': 'Garmin_High_Aerobic_Daily_Sum',
            'Anaerobic_Load': 'Garmin_Anaerobic_Daily_Sum',
            'Strength_Duration_min': 'Total_Strength_Training_Duration_min',
        })
    )
    df_a_daily = pd.merge(df_a_daily, df_runs_daily, on='Date_YYYY_MM_DD', how='left')

    # Avoid merge suffix conflicts with df_g
    for load_metric in ['Garmin_Low_Aerobic_Daily_Sum', 'Garmin_High_Aerobic_Daily_Sum', 'Garmin_Anaerobic_Daily_Sum']:
        if load_metric in df_g.columns:
            df_g[load_metric] = pd.to_numeric(df_g[load_metric], errors='coerce')
            df_a_daily[load_metric] = pd.to_numeric(df_a_daily[load_metric], errors='coerce')
            df_g[load_metric] = df_g[load_metric].fillna(df_a_daily.set_index('Date_YYYY_MM_DD')[load_metric].reindex(df_g['Date_YYYY_MM_DD']).values)
            df_a_daily = df_a_daily.drop(columns=[load_metric])

    # ---------------------------------------------------------
    # 3. Process Withings Data
    # ---------------------------------------------------------
    date_col_w = next(
        (c for c in ['date', 'Date', 'Date (YYYY-MM-DD)'] if c in df_withings.columns),
        df_withings.columns[0],
    )
    df_w = df_withings.copy()
    df_w['Date_YYYY_MM_DD'] = parse_to_iso_date(df_w[date_col_w])

    weight_col = next((c for c in df_w.columns if 'weight' in c.lower()), df_w.columns[1])
    pwv_col = next((c for c in df_w.columns if 'pulse wave' in c.lower() or 'pwv' in c.lower()), None)
    if not pwv_col:
        pwv_col = df_w.columns[4] if df_w.shape[1] > 4 else df_w.columns[3]

    army_fat_col = find_column_by_keywords(df_w, ['army'])
    if army_fat_col:
        fat_col = army_fat_col
    else:
        fat_col = next((c for c in ['Fat Ratio (%)', 'Body Fat (%)', 'Fat Mass (%)'] if c in df_w.columns), None)
        if not fat_col:
            fat_col = df_w.columns[3] if df_w.shape[1] > 3 else df_w.columns[-1]

    agg_w = {weight_col: 'mean', pwv_col: 'mean', fat_col: 'mean'}
    w_sys_col = find_column_by_keywords(df_w, ['systolic'])
    w_dia_col = find_column_by_keywords(df_w, ['diastolic'])
    if w_sys_col:
        agg_w[w_sys_col] = 'mean'
    if w_dia_col:
        agg_w[w_dia_col] = 'mean'

    df_w_daily = df_w.groupby('Date_YYYY_MM_DD').agg(agg_w).reset_index()
    rename_w = {
        weight_col: 'Daily_Morning_Weight_kg',
        pwv_col: 'Pulse_Wave_Velocity_m_s',
        fat_col: 'Daily_Body_Fat_pct',
    }
    if w_sys_col:
        rename_w[w_sys_col] = 'Withings_Systolic_mmHg'
    if w_dia_col:
        rename_w[w_dia_col] = 'Withings_Diastolic_mmHg'
    df_w_daily = df_w_daily.rename(columns=rename_w)

    # ---------------------------------------------------------
    # 4. Process Medical Data
    # ---------------------------------------------------------
    df_med = df_medical.copy()
    df_med['Date_YYYY_MM_DD'] = parse_to_iso_date(df_med.iloc[:, 0])
    sig_col = df_med.iloc[:, 3]
    is_significant = (pd.to_numeric(sig_col, errors='coerce') == 1) | (
        sig_col.astype(str).str.strip().isin(['1', '1.0', 'True', 'true'])
    )
    df_med_filtered = df_med[is_significant].copy()
    if not df_med_filtered.empty:
        df_med_filtered['Medical_Notes'] = df_med_filtered.iloc[:, 4].astype(str).str.strip()
        df_med_filtered = df_med_filtered[
            ~df_med_filtered['Medical_Notes'].str.lower().isin(['nan', 'none', '', 'null'])
        ]
        df_m_daily = (
            df_med_filtered.groupby('Date_YYYY_MM_DD')['Medical_Notes']
            .apply(lambda x: ' | '.join(x))
            .reset_index()
        )
    else:
        df_m_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Medical_Notes'])

    # ---------------------------------------------------------
    # 5. Process Home Assistant Zone Data
    # ---------------------------------------------------------
    if not df_zones.empty:
        zone_date_col = next(
            (c for c in ['Date', 'date', 'Date (YYYY-MM-DD)'] if c in df_zones.columns),
            df_zones.columns[0] if len(df_zones.columns) > 0 else None,
        )
        if zone_date_col:
            df_z = df_zones.copy()
            df_z['Date_YYYY_MM_DD'] = parse_to_iso_date(df_z[zone_date_col])
            work_col = next((c for c in df_z.columns if 'work' in c.lower()), None)
            if work_col:
                df_z_daily = df_z[['Date_YYYY_MM_DD', work_col]].rename(columns={work_col: 'Time_in_Work_Zone_hours'})
            else:
                df_z_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Time_in_Work_Zone_hours'])
        else:
            df_z_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Time_in_Work_Zone_hours'])
    else:
        df_z_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Time_in_Work_Zone_hours'])

    # ---------------------------------------------------------
    # 6. Merge Datasets
    # ---------------------------------------------------------
    df = pd.merge(df_g, df_a_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')

    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df['_sort_date'] = pd.to_datetime(df['Date_YYYY_MM_DD'], format='%Y-%m-%d', errors='coerce')
    df = df.dropna(subset=['_sort_date'])
    df = df.sort_values(by='_sort_date', ascending=True).reset_index(drop=True)
    df = df.drop(columns=['_sort_date'])
    df = df.loc[:, ~df.columns.duplicated()]

    if 'Resting_Systolic_Blood_Pressure_mmHg' not in df.columns or df['Resting_Systolic_Blood_Pressure_mmHg'].isna().all():
        if 'Withings_Systolic_mmHg' in df.columns:
            df['Resting_Systolic_Blood_Pressure_mmHg'] = df['Withings_Systolic_mmHg']
    elif 'Withings_Systolic_mmHg' in df.columns:
        df['Resting_Systolic_Blood_Pressure_mmHg'] = df['Resting_Systolic_Blood_Pressure_mmHg'].fillna(df['Withings_Systolic_mmHg'])

    if 'Resting_Diastolic_Blood_Pressure_mmHg' not in df.columns or df['Resting_Diastolic_Blood_Pressure_mmHg'].isna().all():
        if 'Withings_Diastolic_mmHg' in df.columns:
            df['Resting_Diastolic_Blood_Pressure_mmHg'] = df['Withings_Diastolic_mmHg']
    elif 'Withings_Diastolic_mmHg' in df.columns:
        df['Resting_Diastolic_Blood_Pressure_mmHg'] = df['Resting_Diastolic_Blood_Pressure_mmHg'].fillna(df['Withings_Diastolic_mmHg'])

    # ---------------------------------------------------------
    # 7. Derived Metrics & Mathematical Formulations
    # ---------------------------------------------------------
    if 'Daily_Activity_Training_Load' not in df.columns:
        df['Daily_Activity_Training_Load'] = 0.0
    else:
        df['Daily_Activity_Training_Load'] = df['Daily_Activity_Training_Load'].fillna(0.0)

    df['Date_Datetime'] = pd.to_datetime(df['Date_YYYY_MM_DD'])

    df['Chronic_Training_Load_28d_EWMA'] = df['Daily_Activity_Training_Load'].ewm(
        halflife=pd.Timedelta(days=28), times=df['Date_Datetime']
    ).mean()
    df['Acute_Training_Load_7d_EWMA'] = df['Daily_Activity_Training_Load'].ewm(
        halflife=pd.Timedelta(days=7), times=df['Date_Datetime']
    ).mean()
    df['ACWR'] = df['Acute_Training_Load_7d_EWMA'] / df['Chronic_Training_Load_28d_EWMA'].replace(0, np.nan)

    if 'Daily_Morning_Weight_kg' in df.columns:
        df['Weight_Morning_7d_Avg_kg'] = df['Daily_Morning_Weight_kg'].rolling(window=7, min_periods=1).mean()
    if 'Daily_Body_Fat_pct' in df.columns:
        df['Body_Fat_7d_Avg_pct'] = df['Daily_Body_Fat_pct'].rolling(window=7, min_periods=1).mean()

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
        df['Sleep_Start_Decimal'] = df['Sleep_Start_Time_HH_MM'].apply(time_to_decimal)
        df['Sleep_Start_7d_Variance'] = df['Sleep_Start_Decimal'].rolling(window=7, min_periods=3).std()

    if 'Overnight_Sleep_Duration_min' in df.columns and 'Sleep_Need_min' in df.columns:
        sleep_target = df['Sleep_Need_min'].fillna(480)
        daily_sleep_deficit = (sleep_target - df['Overnight_Sleep_Duration_min']).clip(lower=0)
        df['Sleep_Deficit_EWMA_min'] = daily_sleep_deficit.ewm(
            halflife=pd.Timedelta(days=4), times=df['Date_Datetime']
        ).mean()

    if 'Overnight_Resting_Heart_Rate_bpm' in df.columns:
        shifted_rhr = df['Overnight_Resting_Heart_Rate_bpm'].shift(7)
        shifted_60d_rhr_mean = shifted_rhr.rolling(window=60, min_periods=30).mean()
        shifted_60d_rhr_std = shifted_rhr.rolling(window=60, min_periods=30).std()
        df['Daily_RHR_ZScore'] = (df['Overnight_Resting_Heart_Rate_bpm'] - shifted_60d_rhr_mean) / shifted_60d_rhr_std
        df['RHR_ZScore_3d_EWMA'] = df['Daily_RHR_ZScore'].ewm(
            halflife=pd.Timedelta(days=3), times=df['Date_Datetime']
        ).mean()

    if 'Overnight_Average_HRV_RMSSD_ms' in df.columns:
        shifted_hrv = df['Overnight_Average_HRV_RMSSD_ms'].shift(7)
        shifted_60d_hrv_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
        shifted_60d_hrv_std = shifted_hrv.rolling(window=60, min_periods=30).std()
        df['Daily_HRV_ZScore'] = (df['Overnight_Average_HRV_RMSSD_ms'] - shifted_60d_hrv_mean) / shifted_60d_hrv_std
        df['HRV_RMSSD_ZScore_3d_EWMA'] = df['Daily_HRV_ZScore'].ewm(
            halflife=pd.Timedelta(days=3), times=df['Date_Datetime']
        ).mean()

    if 'Lactate_Threshold_Pace' in df.columns:
        df['Lactate_Threshold_Pace_decimal'] = df['Lactate_Threshold_Pace'].apply(convert_pace_to_decimal)

    # ---------------------------------------------------------
    # 8. Export Column Selection and Exact Renaming
    # ---------------------------------------------------------
    df_export = df.tail(730).copy()
    df_export['_sort_date'] = pd.to_datetime(df_export['Date_YYYY_MM_DD'], format='%Y-%m-%d', errors='coerce')
    df_export = df_export.sort_values(by='_sort_date', ascending=False).reset_index(drop=True)
    df_export = df_export.drop(columns=['_sort_date'])

    target_columns_map = {
        'Date_YYYY_MM_DD': 'Date (YYYY-MM-DD)',
        'Medical_Notes': 'Medical Note',
        'Time_in_Work_Zone_hours': 'Time at Work (hours)',
        'Weight_Morning_7d_Avg_kg': 'Weight - Morning 7d Avg (kg)',
        'Body_Fat_7d_Avg_pct': 'Body Fat - US Army Calibrated 7d Avg (%)',
        'Resting_Systolic_Blood_Pressure_mmHg': 'Systolic Blood Pressure (mmHg)',
        'Resting_Diastolic_Blood_Pressure_mmHg': 'Diastolic Blood Pressure (mmHg)',
        'Pulse_Wave_Velocity_m_s': 'Withings Pulse Wave Velocity (m/s)',
        'Overnight_Sleep_Duration_min': 'Sleep Length (min)',
        'Sleep_Start_Decimal': 'Sleep Start Time (decimal hours)',
        'Sleep_Start_7d_Variance': 'Sleep Start Time Variance - 7d Rolling Std Dev (hours)',
        'Sleep_Deficit_EWMA_min': 'Sleep Deficit EWMA (Garmin Dynamic Need) (min)',
        'Garmin_Sleep_Score': 'Garmin Sleep Score (raw 0–100)',
        'Overnight_Respiration_Rate_brpm': 'Overnight Respiration Rate (breaths/min)',
        'Overnight_Resting_Heart_Rate_bpm': 'Overnight Resting HR (raw bpm)',
        'RHR_ZScore_3d_EWMA': 'Resting HR Z-Score - 3d EWMA vs 60d Baseline (SD)',
        'HRV_RMSSD_ZScore_3d_EWMA': 'HRV RMSSD Z-Score - 3d EWMA vs 60d Baseline (SD)',
        'Garmin_Waking_Average_Stress_Score': 'Garmin Waking Average Stress Score (raw 0–100)',
        'Daily_Steps_Count': 'Daily Steps',
        'Garmin_Moderate_Intensity_Minutes': 'Daily Moderate Intensity Minutes',
        'Garmin_Vigorous_Intensity_Minutes': 'Daily Vigorous Intensity Minutes',
        'Garmin_Low_Aerobic_Daily_Sum': 'Garmin Low Aerobic Exercise Load - Daily Sum (Score)',
        'Garmin_High_Aerobic_Daily_Sum': 'Garmin High Aerobic Exercise Load - Daily Sum (Score)',
        'Garmin_Anaerobic_Daily_Sum': 'Garmin Anaerobic Exercise Load - Daily Sum (Score)',
        'Chronic_Training_Load_28d_EWMA': 'Chronic Training Load (28d EWMA)',
        'ACWR': 'Acute-to-Chronic Workload Ratio - ACWR (7d EWMA / 28d EWMA Ratio)',
        'Daily_Running_Distance_km': 'Daily Running Distance (km)',
        'Daily_Avg_Run_GAP_decimal': 'Average Grade Adjusted Pace - GAP (min/km)',
        'Total_Strength_Training_Duration_min': 'Total Strength Training Duration (min)',
        'Garmin_VO2_Max_ml_kg_min': 'VO2 Max (ml/kg/min)',
        'Lactate_Threshold_Pace_decimal': 'Lactate Threshold Pace (min/km)',
    }

    clean_export = pd.DataFrame(index=df_export.index)
    for internal_col, target_col in target_columns_map.items():
        if internal_col in df_export.columns:
            series = df_export[internal_col]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[:, 0]
            clean_export[target_col] = series
        else:
            clean_export[target_col] = np.nan

    df_export = clean_export

    # ---------------------------------------------------------
    # 9. Strict Type & Decimal Precision Formatting
    # ---------------------------------------------------------
    integer_columns = [
        'Systolic Blood Pressure (mmHg)',
        'Diastolic Blood Pressure (mmHg)',
        'Sleep Length (min)',
        'Sleep Deficit EWMA (Garmin Dynamic Need) (min)',
        'Garmin Sleep Score (raw 0–100)',
        'Overnight Resting HR (raw bpm)',
        'Daily Steps',
        'Daily Moderate Intensity Minutes',
        'Daily Vigorous Intensity Minutes',
        'Garmin Low Aerobic Exercise Load - Daily Sum (Score)',
        'Garmin High Aerobic Exercise Load - Daily Sum (Score)',
        'Garmin Anaerobic Exercise Load - Daily Sum (Score)',
        'Total Strength Training Duration (min)',
    ]
    for col in integer_columns:
        if col in df_export.columns:
            s = df_export[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            df_export[col] = pd.to_numeric(s, errors='coerce').round().astype('Int64')

    float_1dp_columns = [
        'Time at Work (hours)',
        'Overnight Respiration Rate (breaths/min)',
        'Garmin Waking Average Stress Score (raw 0–100)',
        'Chronic Training Load (28d EWMA)',
        'VO2 Max (ml/kg/min)',
    ]
    for col in float_1dp_columns:
        if col in df_export.columns:
            s = df_export[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            df_export[col] = pd.to_numeric(s, errors='coerce').round(1)

    float_2dp_columns = [
        'Weight - Morning 7d Avg (kg)',
        'Body Fat - US Army Calibrated 7d Avg (%)',
        'Withings Pulse Wave Velocity (m/s)',
        'Sleep Start Time (decimal hours)',
        'Sleep Start Time Variance - 7d Rolling Std Dev (hours)',
        'Resting HR Z-Score - 3d EWMA vs 60d Baseline (SD)',
        'HRV RMSSD Z-Score - 3d EWMA vs 60d Baseline (SD)',
        'Acute-to-Chronic Workload Ratio - ACWR (7d EWMA / 28d EWMA Ratio)',
        'Daily Running Distance (km)',
        'Average Grade Adjusted Pace - GAP (min/km)',
        'Lactate Threshold Pace (min/km)',
    ]
    for col in float_2dp_columns:
        if col in df_export.columns:
            s = df_export[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            df_export[col] = pd.to_numeric(s, errors='coerce').round(2)

    # ---------------------------------------------------------
    # 10. Write Out Clean CSV
    # ---------------------------------------------------------
    df_export.to_csv(output_path, header=True, index=False, na_rep='')
    return df_export
