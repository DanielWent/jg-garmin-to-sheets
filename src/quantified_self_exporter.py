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
    s_str = series.astype(str).str.strip().str.split('T').str[0].str.split(' ').str[0]
    s_dt = pd.to_datetime(s_str, format='%Y-%m-%d', errors='coerce')
    missing_mask = s_dt.isna() & series.notna() & ~series.astype(str).str.lower().isin(['nan', 'none', '', 'null'])
    if missing_mask.any():
        s_dt.loc[missing_mask] = pd.to_datetime(series.loc[missing_mask], dayfirst=True, format='mixed', errors='coerce')
    return s_dt.dt.strftime('%Y-%m-%d')


def time_to_decimal(time_str):
    """Converts HH:MM string to continuous decimal hours (e.g. 17:30 -> 17.50)."""
    if pd.isna(time_str):
        return np.nan
    try:
        parts = str(time_str).strip().split(':')
        h, m = int(parts[0]), int(parts[1])
        return round(h + (m / 60.0), 2)
    except (ValueError, IndexError):
        return np.nan


def pace_to_seconds(pace_str):
    """Converts MM:SS or decimal min/km into total seconds/km."""
    if pd.isna(pace_str):
        return np.nan
    try:
        val_str = str(pace_str).strip()
        if ':' in val_str:
            m, s = map(float, val_str.split(':'))
            return m * 60.0 + s
        else:
            return float(val_str) * 60.0
    except ValueError:
        return np.nan


def adjust_for_midnight_offset(val):
    """
    Shifts sleep start time to a continuous signed offset from midnight (hours):
      - 22:45 (22.75) -> -1.25 h
      - 23:30 (23.50) -> -0.50 h
      - 00:30 (0.50)  -> +0.50 h
    Enables linear calculations across midnight without modulo or polar conversions.
    """
    if pd.isna(val):
        return np.nan
    return val - 24.0 if val >= 12.0 else val


def generate_quantified_self_csv(
    df_garmin: pd.DataFrame,
    df_withings: pd.DataFrame,
    df_medical: pd.DataFrame,
    df_activities: pd.DataFrame,
    df_zones: pd.DataFrame,
    df_sleep: pd.DataFrame = None,
    output_path: str = 'drw_quantified_self.csv',
):

    # 1. Process Garmin Daily Data (Deduplicate keeping latest sync)
    df_g = df_garmin.copy()
    date_col_g = next((c for c in ['Date (YYYY-MM-DD)', 'Date'] if c in df_g.columns), df_g.columns[0])
    df_g['Date_YYYY_MM_DD'] = parse_to_iso_date(df_g[date_col_g])
    if date_col_g != 'Date_YYYY_MM_DD':
        df_g = df_g.drop(columns=[date_col_g])
    if len(df_garmin.columns) > 21:
        df_g['Daily Max Body Battery (0 - 100)'] = df_garmin.iloc[:, 21]
    # Column AI is index 34 (0-based)
    if len(df_garmin.columns) > 34:
        df_g['Average Overnight RMSSD HRV (ms)'] = df_garmin.iloc[:, 34]
    elif 'Average Overnight RMSSD HRV (ms)' in df_garmin.columns:
        df_g['Average Overnight RMSSD HRV (ms)'] = df_garmin['Average Overnight RMSSD HRV (ms)']
    df_g = df_g.drop_duplicates(subset=['Date_YYYY_MM_DD'], keep='last')

    # 2. Process Garmin Activities Data
    df_a = df_activities.copy()
    act_date_col = next((c for c in ['Date (YYYY-MM-DD)', 'Date'] if c in df_a.columns), df_a.columns[1])
    df_a['Date_YYYY_MM_DD'] = parse_to_iso_date(df_a[act_date_col])
    df_a['Activity Training Load'] = pd.to_numeric(df_a['Activity Training Load'], errors='coerce')

    # Sum of daily Garmin Activity Training Load
    df_a_daily = df_a.groupby('Date_YYYY_MM_DD')['Activity Training Load'].sum(min_count=1).reset_index()
    df_a_daily.rename(columns={'Activity Training Load': 'Daily_Activity_Training_Load'}, inplace=True)

    # Process Running-Specific Metrics
    runs = df_a[df_a['Activity Type'].astype(str).str.lower() == 'running'].copy()
    if not runs.empty:
        runs['Distance (km)'] = pd.to_numeric(runs['Distance (km)'], errors='coerce')
        runs['Duration (min)'] = pd.to_numeric(runs['Duration (min)'], errors='coerce')
        runs['GAP_sec'] = runs['Average Grade Adjusted Pace (min/km)'].apply(pace_to_seconds)
        runs['GAP_weight'] = runs['GAP_sec'] * runs['Distance (km)']

        daily_run_dist = runs.groupby('Date_YYYY_MM_DD')['Distance (km)'].sum(min_count=1).reset_index()
        daily_run_dist.rename(columns={'Distance (km)': 'Daily Running Distance (km)'}, inplace=True)

        def calc_daily_gap(x):
            mask = x['GAP_sec'].notna() & x['Distance (km)'].notna()
            total_dist = x.loc[mask, 'Distance (km)'].sum()
            if total_dist > 0:
                return x.loc[mask, 'GAP_weight'].sum() / total_dist
            return np.nan

        daily_gap = runs.groupby('Date_YYYY_MM_DD').apply(calc_daily_gap).reset_index(name='_daily_gap_sec')

        # Extract primary session label from the highest-load run of the day
        highest_load_runs = runs.sort_values('Activity Training Load', ascending=False).drop_duplicates('Date_YYYY_MM_DD').copy()
        if 'Garmin Training Effect Label' in highest_load_runs.columns:
            highest_load_runs['Daily Run Training Effect Label'] = (
                highest_load_runs['Garmin Training Effect Label']
                .astype(str)
                .str.strip()
                .replace({'nan': '', 'None': '', 'null': '', '': ''})
            )
            run_labels = highest_load_runs[['Date_YYYY_MM_DD', 'Daily Run Training Effect Label']]
        else:
            run_labels = pd.DataFrame({'Date_YYYY_MM_DD': highest_load_runs['Date_YYYY_MM_DD'], 'Daily Run Training Effect Label': np.nan})

        vo2_col = 'VO2 Max (ml/kg/min)' if 'VO2 Max (ml/kg/min)' in df_g.columns else next((c for c in df_g.columns if 'VO2 Max' in c), None)
        if vo2_col:
            vo2_df = df_g[['Date_YYYY_MM_DD', vo2_col]].dropna()
            runs = pd.merge(runs, vo2_df, on='Date_YYYY_MM_DD', how='left')
            runs[vo2_col] = pd.to_numeric(runs[vo2_col], errors='coerce').ffill().bfill()
            runs['Avg Pace (sec/km)'] = runs['Avg Pace (min/km)'].apply(pace_to_seconds)
            runs['Calculated LT Pace (sec/km)'] = (220.0 / runs[vo2_col]) * 60.0
            fallback_is_easy = runs['Avg Pace (sec/km)'] > runs['Calculated LT Pace (sec/km)']
        else:
            fallback_is_easy = pd.Series(True, index=runs.index)

        if 'Garmin Training Effect Label' in runs.columns:
            labels = runs['Garmin Training Effect Label'].astype(str).str.strip().str.upper()
        else:
            labels = pd.Series('UNKNOWN', index=runs.index)

        easy_labels = {'AEROBIC_BASE', 'BASE', 'RECOVERY', 'LOW_AEROBIC', 'NO_BENEFIT', 'NONE'}
        hard_labels = {'TEMPO', 'LACTATE_THRESHOLD', 'THRESHOLD', 'VO2MAX', 'VO2_MAX', 'ANAEROBIC_CAPACITY', 'ANAERIC', 'SPEED', 'SPRINT', 'HIGH_AEROBIC'}

        runs['Is Easy'] = np.where(
            labels.isin(easy_labels), True,
            np.where(labels.isin(hard_labels), False, fallback_is_easy)
        )

        runs['Easy Duration'] = np.where(runs['Is Easy'], runs['Duration (min)'], 0)
        runs['Total Duration'] = runs['Duration (min)']

        daily_dur = runs.groupby('Date_YYYY_MM_DD')[['Easy Duration', 'Total Duration']].sum().reset_index()

        df_a_daily = pd.merge(df_a_daily, run_labels, on='Date_YYYY_MM_DD', how='left')
        df_a_daily = pd.merge(df_a_daily, daily_dur, on='Date_YYYY_MM_DD', how='left')
        df_a_daily = pd.merge(df_a_daily, daily_run_dist, on='Date_YYYY_MM_DD', how='left')
        df_a_daily = pd.merge(df_a_daily, daily_gap, on='Date_YYYY_MM_DD', how='left')
    else:
        df_a_daily['Daily Run Training Effect Label'] = np.nan
        df_a_daily['Easy Duration'] = np.nan
        df_a_daily['Total Duration'] = np.nan
        df_a_daily['Daily Running Distance (km)'] = np.nan
        df_a_daily['_daily_gap_sec'] = np.nan

    # 3. Process Withings Data
    df_w = df_withings.copy()
    date_col_w = next((c for c in ['date', 'Date', 'Date (YYYY-MM-DD)'] if c in df_w.columns), df_w.columns[0])
    df_w['Date_YYYY_MM_DD'] = parse_to_iso_date(df_w[date_col_w])

    weight_col = 'Weight (kg)' if 'Weight (kg)' in df_w.columns else df_w.columns[1]
    pwv_col = 'Pulse Wave Velocity (m/s)' if 'Pulse Wave Velocity (m/s)' in df_w.columns else next((c for c in df_w.columns if 'Pulse Wave' in c), None)
    fat_col = 'Body Fat (%)' if 'Body Fat (%)' in df_w.columns else next((c for c in df_w.columns if 'Fat' in c), None)

    agg_dict = {weight_col: 'mean'}
    if pwv_col:
        agg_dict[pwv_col] = 'mean'
    if fat_col:
        agg_dict[fat_col] = 'mean'

    for col in agg_dict.keys():
        df_w[col] = pd.to_numeric(df_w[col], errors='coerce')

    df_w_daily = df_w.groupby('Date_YYYY_MM_DD').agg(agg_dict).reset_index()
    w_rename = {weight_col: 'Daily_Morning_Weight_kg'}
    if pwv_col:
        w_rename[pwv_col] = 'Pulse_Wave_Velocity_m_s'
    if fat_col:
        w_rename[fat_col] = 'Daily_Body_Fat_pct'
    df_w_daily.rename(columns=w_rename, inplace=True)

    # 4. Process Medical Data
    df_med = df_medical.copy()
    df_med['Date_YYYY_MM_DD'] = parse_to_iso_date(df_med.iloc[:, 0])
    sig_col = df_med.iloc[:, 3]
    is_significant = (pd.to_numeric(sig_col, errors='coerce') == 1) | (sig_col.astype(str).str.strip().str.lower().isin(['1', '1.0', 'true']))
    df_med_filtered = df_med[is_significant].copy()

    if not df_med_filtered.empty:
        df_med_filtered['Medical_Notes'] = df_med_filtered.iloc[:, 4].astype(str).str.strip()
        df_med_filtered = df_med_filtered[~df_med_filtered['Medical_Notes'].str.lower().isin(['nan', 'none', '', 'null'])]
        df_m_daily = df_med_filtered.groupby('Date_YYYY_MM_DD')['Medical_Notes'].apply(lambda x: ' | '.join(x)).reset_index()
    else:
        df_m_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Medical_Notes'])

    # 5. Process Home Assistant Zone Data
    df_z = df_zones.copy()
    zone_date_col = next((c for c in ['Date', 'date', 'Date (YYYY-MM-DD)'] if c in df_z.columns), df_z.columns[0])
    df_z['Date_YYYY_MM_DD'] = parse_to_iso_date(df_z[zone_date_col])
    if 'Time in Work Zone (hours)' in df_z.columns:
        df_z['Time in Work Zone (hours)'] = pd.to_numeric(df_z['Time in Work Zone (hours)'], errors='coerce')
        df_z_daily = (
            df_z.groupby('Date_YYYY_MM_DD', as_index=False)['Time in Work Zone (hours)']
            .max()
            .rename(columns={'Time in Work Zone (hours)': 'Time at Work (hours)'})
        )
    else:
        df_z_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Time at Work (hours)'])

    # 6. Process Home Assistant Sleep Data
    if df_sleep is not None and not df_sleep.empty:
        df_s = df_sleep.copy()
        sleep_date_col = next((c for c in ['Date', 'date', 'Date (YYYY-MM-DD)'] if c in df_s.columns), df_s.columns[0])
        df_s['Date_YYYY_MM_DD'] = parse_to_iso_date(df_s[sleep_date_col])
        sleep_cols = ['Date_YYYY_MM_DD']
        for col in ['Sleep Onset Latency (mins)', 'Sleep Efficiency (%)']:
            if col in df_s.columns:
                sleep_cols.append(col)
        df_s_daily = df_s[sleep_cols].drop_duplicates(subset=['Date_YYYY_MM_DD'], keep='last')
    else:
        df_s_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Sleep Onset Latency (mins)', 'Sleep Efficiency (%)'])

    # 7. Merge Datasets (Guaranteed 1-to-1 joins)
    df = df_g.copy()
    df = pd.merge(df, df_a_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_s_daily, on='Date_YYYY_MM_DD', how='outer')

    # Drop nulls, sort chronologically, and deduplicate before rolling calculations
    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df['_sort_date'] = pd.to_datetime(df['Date_YYYY_MM_DD'])
    df = df.sort_values('_sort_date').reset_index(drop=True)
    df = df.drop_duplicates(subset=['Date_YYYY_MM_DD'], keep='last').reset_index(drop=True)

    # Derive explicit Day of Week to prevent LLM calendar arithmetic hallucinations
    df['Day of Week (Mon-Sun)'] = df['_sort_date'].dt.strftime('%a')

    # 8. EWMA, Rolling, and Derived Calculations (Chronologically ascending on full history)
    df['Daily_Activity_Training_Load'] = pd.to_numeric(df['Daily_Activity_Training_Load'], errors='coerce').fillna(0)
    df['Daily Activity Training Load (load)'] = df['Daily_Activity_Training_Load']
    df['Chronic Training Load - CTL - 28d Span / 9.7d Half-Life EWMA (load)'] = df['Daily_Activity_Training_Load'].ewm(span=28, adjust=False).mean()
    df['ATL_7d'] = df['Daily_Activity_Training_Load'].ewm(span=7, adjust=False).mean()
    df['Acute-to-Chronic Workload Ratio - ACWR (ratio)'] = df['ATL_7d'] / df['Chronic Training Load - CTL - 28d Span / 9.7d Half-Life EWMA (load)']

    if 'Easy Duration' in df.columns and 'Total Duration' in df.columns:
        df['Easy Duration'] = pd.to_numeric(df['Easy Duration'], errors='coerce').fillna(0)
        df['Total Duration'] = pd.to_numeric(df['Total Duration'], errors='coerce').fillna(0)
        df['Rolling 28d Easy Minutes'] = df.rolling('28D', on='_sort_date')['Easy Duration'].sum()
        df['Rolling 28d Total Minutes'] = df.rolling('28D', on='_sort_date')['Total Duration'].sum()
        df['Easy Running Duration - 28d Rolling (%)'] = (df['Rolling 28d Easy Minutes'] / df['Rolling 28d Total Minutes']) * 100

    if 'Sleep Start Time' in df.columns:
        raw_dec = df['Sleep Start Time'].apply(time_to_decimal)
        df['Sleep Start Time - Midnight Offset (hours)'] = raw_dec.apply(adjust_for_midnight_offset)

    if 'Sleep Need (min)' in df.columns and 'Sleep Length (min)' in df.columns:
        sleep_need = pd.to_numeric(df['Sleep Need (min)'], errors='coerce')
        sleep_len = pd.to_numeric(df['Sleep Length (min)'], errors='coerce')
        sleep_deficit = (sleep_need - sleep_len).clip(lower=0)
        df['Sleep Deficit vs Garmin Sleep Need - 4d Span / 1.4d Half-Life EWMA (min)'] = sleep_deficit.ewm(span=4, adjust=False).mean()

    # Z-scores computed against backward-shifted 60d baseline
    hrv_source_col = 'Average Overnight RMSSD HRV (ms)' if 'Average Overnight RMSSD HRV (ms)' in df.columns else ('Overnight HRV (ms)' if 'Overnight HRV (ms)' in df.columns else None)
    if hrv_source_col:
        hrv_series = pd.to_numeric(df[hrv_source_col], errors='coerce')
        shifted_hrv = hrv_series.shift(7)
        hrv_mean = shifted_hrv.rolling(60, min_periods=30).mean()
        hrv_std = shifted_hrv.rolling(60, min_periods=30).std()
        daily_hrv_z = (hrv_series - hrv_mean) / hrv_std
        df['HRV RMSSD Z-Score (60d baseline) (SD)'] = daily_hrv_z

    # Time-aware 7-calendar-day rolling averages for body composition and arterial stiffness
    if 'Daily_Morning_Weight_kg' in df.columns:
        df['Daily_Morning_Weight_kg'] = pd.to_numeric(df['Daily_Morning_Weight_kg'], errors='coerce')
        df['Weight - Morning 7d Avg (kg)'] = df.rolling('7D', on='_sort_date', min_periods=1)['Daily_Morning_Weight_kg'].mean()

    if 'Daily_Body_Fat_pct' in df.columns:
        df['Daily_Body_Fat_pct'] = pd.to_numeric(df['Daily_Body_Fat_pct'], errors='coerce')
        df['Body Fat - US Army Calibrated 7d Avg (%)'] = df.rolling('7D', on='_sort_date', min_periods=1)['Daily_Body_Fat_pct'].mean()

    if 'Pulse_Wave_Velocity_m_s' in df.columns:
        df['Pulse_Wave_Velocity_m_s'] = pd.to_numeric(df['Pulse_Wave_Velocity_m_s'], errors='coerce')
        df['Withings Pulse Wave Velocity - 7d Avg (m/s)'] = df.rolling('7D', on='_sort_date', min_periods=1)['Pulse_Wave_Velocity_m_s'].mean()

    # 9. Renaming & Metric Harmonisation
    rename_map = {
        'Date_YYYY_MM_DD': 'Date (YYYY-MM-DD)',
        'Overnight Respiration Rate (brpm)': 'Overnight Respiration Rate (breaths/min)',
        'Overnight Resting HR (bpm)': 'Overnight Resting HR (raw bpm)',
        'Waking Average Stress Score (0-100)': 'Garmin Waking Average Stress Score (raw 0-100)',
        'Garmin Waking Average Stress Score (raw 0–100)': 'Garmin Waking Average Stress Score (raw 0-100)',
        'Lactate Threshold Pace (min/km)': 'Lactate Threshold Pace (sec/km)',
        'Medical_Notes': 'Medical Note',
        'Daily Steps': 'Daily Steps (count)',
        'Daily Moderate Intensity Minutes': 'Garmin Daily Moderate Intensity - LTHR-Calibrated Zone 2/3 Time (min)',
        'Daily Moderate Intensity (min)': 'Garmin Daily Moderate Intensity - LTHR-Calibrated Zone 2/3 Time (min)',
        'Garmin Daily Moderate Intensity Minutes (min)': 'Garmin Daily Moderate Intensity - LTHR-Calibrated Zone 2/3 Time (min)',
        'Daily Vigorous Intensity Minutes': 'Garmin Daily Vigorous Intensity - LTHR-Calibrated Zone 4/5 Time (min)',
        'Daily Vigorous Intensity (min)': 'Garmin Daily Vigorous Intensity - LTHR-Calibrated Zone 4/5 Time (min)',
        'Garmin Daily Vigorous Intensity Minutes (min)': 'Garmin Daily Vigorous Intensity - LTHR-Calibrated Zone 4/5 Time (min)'
    }
    df.rename(columns=rename_map, inplace=True)

    for p_col in ['Lactate Threshold Pace (sec/km)']:
        if p_col in df.columns:
            df[p_col] = df[p_col].apply(pace_to_seconds)

    if '_daily_gap_sec' in df.columns:
        gap_sec = df['_daily_gap_sec']
        df['Average Grade Adjusted Speed - GAS (m/s)'] = np.where(gap_sec > 0, 1000.0 / gap_sec, np.nan)

    # 10. Filter to strictly 2 years of rolling data
    if not df.empty and df['_sort_date'].notna().any():
        cutoff_date = df['_sort_date'].max() - pd.DateOffset(years=2)
        df = df[df['_sort_date'] >= cutoff_date].copy()

    target_columns = [
        # Block A: Context & Routine
        'Date (YYYY-MM-DD)',
        'Day of Week (Mon-Sun)',
        'Time at Work (hours)',
        # Block B: Sleep Architecture & Circadian Timing
        'Sleep Start Time - Midnight Offset (hours)',
        'Sleep Length (min)',
        'Sleep Onset Latency (mins)',
        'Sleep Efficiency (%)',
        'Sleep Deficit vs Garmin Sleep Need - 4d Span / 1.4d Half-Life EWMA (min)',
        # Block C: Autonomic Readiness & Mental Stress
        'Daily Max Body Battery (0 - 100)',
        'Overnight Resting HR (raw bpm)',
        'Average Overnight RMSSD HRV (ms)',
        'HRV RMSSD Z-Score (60d baseline) (SD)',
        'Overnight Respiration Rate (breaths/min)',
        'Garmin Waking Average Stress Score (raw 0-100)',
        # Block D: Daily Activity & Session-Level Intensity
        'Daily Steps (count)',
        'Garmin Daily Moderate Intensity - LTHR-Calibrated Zone 2/3 Time (min)',
        'Garmin Daily Vigorous Intensity - LTHR-Calibrated Zone 4/5 Time (min)',
        'Daily Activity Training Load (load)',
        'Daily Running Distance (km)',
        'Daily Run Training Effect Label',
        'Average Grade Adjusted Speed - GAS (m/s)',
        # Block E: Macro Fitness & Workload Ratios
        'Chronic Training Load - CTL - 28d Span / 9.7d Half-Life EWMA (load)',
        'Acute-to-Chronic Workload Ratio - ACWR (ratio)',
        'Easy Running Duration - 28d Rolling (%)',
        'VO2 Max (ml/kg/min)',
        'Lactate Threshold Pace (sec/km)',
        # Block F: Body Composition, Cardiovascular & Clinical
        'Weight - Morning 7d Avg (kg)',
        'Body Fat - US Army Calibrated 7d Avg (%)',
        'Withings Pulse Wave Velocity - 7d Avg (m/s)',
        'Systolic Blood Pressure (mmHg)',
        'Diastolic Blood Pressure (mmHg)',
        'Medical Note'
    ]

    for col in target_columns:
        if col not in df.columns:
            df[col] = np.nan

    # Sort strictly descending (newest at top) for export
    df_export = df.sort_values('_sort_date', ascending=False).reset_index(drop=True)
    df_export = df_export[target_columns]

    # 11. Strict Type & Decimal Formatting
    float_1dp = [
        'Time at Work (hours)',
        'Garmin Waking Average Stress Score (raw 0-100)',
        'Overnight Respiration Rate (breaths/min)',
        'VO2 Max (ml/kg/min)',
        'Easy Running Duration - 28d Rolling (%)',
        'Sleep Efficiency (%)'
    ]
    float_2dp = [
        'Weight - Morning 7d Avg (kg)',
        'Sleep Start Time - Midnight Offset (hours)',
        'Sleep Deficit vs Garmin Sleep Need - 4d Span / 1.4d Half-Life EWMA (min)',
        'HRV RMSSD Z-Score (60d baseline) (SD)',
        'Chronic Training Load - CTL - 28d Span / 9.7d Half-Life EWMA (load)',
        'Acute-to-Chronic Workload Ratio - ACWR (ratio)',
        'Daily Running Distance (km)',
        'Average Grade Adjusted Speed - GAS (m/s)',
        'Body Fat - US Army Calibrated 7d Avg (%)',
        'Withings Pulse Wave Velocity - 7d Avg (m/s)'
    ]
    int_cols = [
        'Sleep Length (min)',
        'Daily Max Body Battery (0 - 100)',
        'Overnight Resting HR (raw bpm)',
        'Average Overnight RMSSD HRV (ms)',
        'Daily Steps (count)',
        'Garmin Daily Moderate Intensity - LTHR-Calibrated Zone 2/3 Time (min)',
        'Garmin Daily Vigorous Intensity - LTHR-Calibrated Zone 4/5 Time (min)',
        'Daily Activity Training Load (load)',
        'Systolic Blood Pressure (mmHg)',
        'Diastolic Blood Pressure (mmHg)',
        'Lactate Threshold Pace (sec/km)',
        'Sleep Onset Latency (mins)'
    ]

    for col in float_1dp:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(1)
    for col in float_2dp:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(2)
    for col in int_cols:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round().astype('Int64')

    # 12. Output CSV without trailing whitespace in headers
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

    drw_quantified_self_folder = '0B06ZX4hUnMRtT2VLR2pNYnJEVkE'

    GARMIN_FILENAME = 'drw_garmin_data.csv'
    ACTIVITIES_FILENAME = 'drw_garmin_activities_list.csv'
    WITHINGS_FILENAME = 'drw_withings_bodyscan_data.csv'
    MEDICAL_FILENAME = "Daniel's Full Medical Notes.csv"
    ZONES_BASE_URL = 'https://dfexhoblv7ytpsxp7uiasfchbdxbl8vt.ui.nabu.casa/local/drw_home_assistant_zone_history.csv'
    ZONES_URL = f'{ZONES_BASE_URL}?v={int(time.time())}'
    SLEEP_BASE_URL = 'https://dfexhoblv7ytpsxp7uiasfchbdxbl8vt.ui.nabu.casa/local/drw_sleep_history.csv'
    SLEEP_URL = f'{SLEEP_BASE_URL}?v={int(time.time())}'
    TARGET_FILENAME = 'drw_quantified_self.csv'

    if not FOLDER_ID:
        raise ValueError('DRIVE_FOLDER_ID environment variable is not set.')
    if not SERVICE_ACCOUNT_JSON:
        raise ValueError('GOOGLE_SHEETS_CREDENTIALS environment variable is not set.')

    print('Authenticating with Google Drive...')
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    drive_service = build('drive', 'v3', credentials=creds)

    print(f'Locating files in folder {FOLDER_ID}...')
    garmin_file_id = get_file_id(drive_service, GARMIN_FILENAME, FOLDER_ID)
    activities_file_id = get_file_id(drive_service, ACTIVITIES_FILENAME, FOLDER_ID)
    withings_file_id = get_file_id(drive_service, WITHINGS_FILENAME, FOLDER_ID)
    medical_file_id = get_file_id(drive_service, MEDICAL_FILENAME, FOLDER_ID)

    if not medical_file_id:
        medical_file_id = get_file_id(drive_service, "Daniel's Medical Test Results.csv", FOLDER_ID)

    target_file_id = get_file_id(drive_service, TARGET_FILENAME, drw_quantified_self_folder)

    for name, f_id in zip(
        [GARMIN_FILENAME, ACTIVITIES_FILENAME, WITHINGS_FILENAME, MEDICAL_FILENAME],
        [garmin_file_id, activities_file_id, withings_file_id, medical_file_id]
    ):
        if not f_id:
            raise FileNotFoundError(f"Could not find '{name}' in Drive.")

    print('Downloading raw data...')
    df_garmin_raw = pd.read_csv(download_drive_file(drive_service, garmin_file_id))
    df_activities_raw = pd.read_csv(download_drive_file(drive_service, activities_file_id))
    df_withings_raw = pd.read_csv(download_drive_file(drive_service, withings_file_id))
    df_medical_raw = pd.read_csv(download_drive_file(drive_service, medical_file_id))
    df_zones_raw = pd.read_csv(ZONES_URL)
    df_sleep_raw = pd.read_csv(SLEEP_URL)

    print('Processing physiological metrics...')
    generate_quantified_self_csv(
        df_garmin_raw,
        df_withings_raw,
        df_medical_raw,
        df_activities_raw,
        df_zones_raw,
        df_sleep_raw,
        output_path=TARGET_FILENAME,
    )

    print('Uploading updated CSV...')
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)

    if target_file_id:
        drive_service.files().update(
            fileId=target_file_id, media_body=media, fields='id, modifiedTime'
        ).execute(num_retries=5)
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [drw_quantified_self_folder], 'mimeType': 'text/csv'}
        drive_service.files().create(
            body=file_metadata, media_body=media, fields='id, modifiedTime'
        ).execute(num_retries=5)

    print('Export and upload complete.')
