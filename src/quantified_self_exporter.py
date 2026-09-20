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
    if pd.isna(time_str):
        return np.nan
    try:
        h, m = map(int, str(time_str).split(':'))
        return h + (m / 60.0)
    except ValueError:
        return np.nan


def pace_to_decimal(pace_str):
    if pd.isna(pace_str):
        return np.nan
    try:
        m, s = map(int, str(pace_str).split(':'))
        return m + (s / 60.0)
    except ValueError:
        return np.nan


def adjust_for_midnight(val):
    """Shifts decimal sleep times < 12:00 PM to the next day for accurate std dev math"""
    if pd.isna(val):
        return np.nan
    if val < 12.0:
        return val + 24.0
    return val


def generate_quantified_self_csv(
    df_garmin: pd.DataFrame,
    df_withings: pd.DataFrame,
    df_medical: pd.DataFrame,
    df_activities: pd.DataFrame,
    df_zones: pd.DataFrame,
    output_path: str = 'drw_quantified_self.csv',
):

    # 1. Process Garmin Daily Data
    df_g = df_garmin.copy()
    date_col_g = next((c for c in ['Date (YYYY-MM-DD)', 'Date'] if c in df_g.columns), df_g.columns[0])
    df_g['Date_YYYY_MM_DD'] = parse_to_iso_date(df_g[date_col_g])
    
    # Drop the original date column to strictly prevent duplicate date columns in the output
    if date_col_g != 'Date_YYYY_MM_DD':
        df_g = df_g.drop(columns=[date_col_g])

    # 2. Process Garmin Activities Data 
    df_a = df_activities.copy()
    act_date_col = next((c for c in ['Date (YYYY-MM-DD)', 'Date'] if c in df_a.columns), df_a.columns[1])
    df_a['Date_YYYY_MM_DD'] = parse_to_iso_date(df_a[act_date_col])

    # Base CTL/ATL Training Load Sum
    df_a_daily = df_a.groupby('Date_YYYY_MM_DD')['Activity Training Load'].sum().reset_index()
    df_a_daily.rename(columns={'Activity Training Load': 'Daily_Activity_Training_Load'}, inplace=True)

    # Process Running-Specific Metrics (Highest Load Start Time & Easy % calculations)
    runs = df_a[df_a['Activity Type'].astype(str).str.lower() == 'running'].copy()
    if not runs.empty:
        # Get start time of highest load run per day
        highest_load_runs = runs.sort_values('Activity Training Load', ascending=False).drop_duplicates('Date_YYYY_MM_DD')
        highest_load_runs = highest_load_runs[['Date_YYYY_MM_DD', 'Start Time (HH:MM)']]
        highest_load_runs.rename(columns={'Start Time (HH:MM)': 'Highest Load Run Start Time'}, inplace=True)
        
        # Calculate daily easy running duration based on VO2 Max
        vo2_col = 'VO2 Max (ml/kg/min)' if 'VO2 Max (ml/kg/min)' in df_g.columns else next((c for c in df_g.columns if 'VO2 Max' in c), None)
        if vo2_col:
            vo2_df = df_g[['Date_YYYY_MM_DD', vo2_col]].dropna()
            runs = pd.merge(runs, vo2_df, on='Date_YYYY_MM_DD', how='left')
            runs[vo2_col] = runs[vo2_col].ffill().bfill()
            
            runs['Avg Pace (decimal)'] = runs['Avg Pace (min/km)'].apply(pace_to_decimal)
            
            # Approximate LT Pace from VO2 Max (e.g. VO2 50 = ~4.4 min/km or 4:24 min/km)
            runs['Calculated LT Pace (decimal)'] = 220.0 / runs[vo2_col]
            
            # Categorize as easy if pace is slower (numerically higher) than threshold pace
            runs['Is Easy'] = runs['Avg Pace (decimal)'] > runs['Calculated LT Pace (decimal)']
            runs['Easy Duration'] = np.where(runs['Is Easy'], runs['Duration (min)'], 0)
            runs['Total Duration'] = runs['Duration (min)']
            
            daily_dur = runs.groupby('Date_YYYY_MM_DD')[['Easy Duration', 'Total Duration']].sum().reset_index()
            
            df_a_daily = pd.merge(df_a_daily, highest_load_runs, on='Date_YYYY_MM_DD', how='left')
            df_a_daily = pd.merge(df_a_daily, daily_dur, on='Date_YYYY_MM_DD', how='left')
        else:
            df_a_daily = pd.merge(df_a_daily, highest_load_runs, on='Date_YYYY_MM_DD', how='left')
            df_a_daily['Easy Duration'] = np.nan
            df_a_daily['Total Duration'] = np.nan
    else:
        df_a_daily['Highest Load Run Start Time'] = np.nan
        df_a_daily['Easy Duration'] = np.nan
        df_a_daily['Total Duration'] = np.nan

    # 3. Process Withings Data
    df_w = df_withings.copy()
    date_col_w = next((c for c in ['date', 'Date', 'Date (YYYY-MM-DD)'] if c in df_w.columns), df_w.columns[0])
    df_w['Date_YYYY_MM_DD'] = parse_to_iso_date(df_w[date_col_w])

    weight_col = 'Weight (kg)' if 'Weight (kg)' in df_w.columns else df_w.columns[1]
    pwv_col = 'Pulse Wave Velocity (m/s)' if 'Pulse Wave Velocity (m/s)' in df_w.columns else next((c for c in df_w.columns if 'Pulse Wave' in c), None)
    fat_col = 'Body Fat (%)' if 'Body Fat (%)' in df_w.columns else next((c for c in df_w.columns if 'Fat' in c), None)

    agg_dict = {weight_col: 'mean'}
    if pwv_col: agg_dict[pwv_col] = 'mean'
    if fat_col: agg_dict[fat_col] = 'mean'

    df_w_daily = df_w.groupby('Date_YYYY_MM_DD').agg(agg_dict).reset_index()
    w_rename = {weight_col: 'Daily_Morning_Weight_kg'}
    if pwv_col: w_rename[pwv_col] = 'Pulse_Wave_Velocity_m_s'
    if fat_col: w_rename[fat_col] = 'Daily_Body_Fat_pct'
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
        df_z_daily = df_z[['Date_YYYY_MM_DD', 'Time in Work Zone (hours)']].rename(columns={'Time in Work Zone (hours)': 'Time at Work (hours)'})
    else:
        df_z_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD', 'Time at Work (hours)'])

    # 6. Merge Datasets
    df = df_g.copy()
    df = pd.merge(df, df_a_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')

    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df['_sort_date'] = pd.to_datetime(df['Date_YYYY_MM_DD'])
    df = df.sort_values('_sort_date').reset_index(drop=True)

    # 7. EWMA, Rolling, and Derived Calculations
    df['Daily_Activity_Training_Load'] = df['Daily_Activity_Training_Load'].fillna(0)
    df['Chronic Training Load - CTL (28d EWMA)'] = df['Daily_Activity_Training_Load'].ewm(span=28, adjust=False).mean()
    df['ATL_7d'] = df['Daily_Activity_Training_Load'].ewm(span=7, adjust=False).mean()
    df['Acute-to-Chronic Workload Ratio - ACWR'] = df['ATL_7d'] / df['Chronic Training Load - CTL (28d EWMA)']

    if 'Easy Duration' in df.columns and 'Total Duration' in df.columns:
        df['Easy Duration'] = df['Easy Duration'].fillna(0)
        df['Total Duration'] = df['Total Duration'].fillna(0)
        df['Rolling 28d Easy Minutes'] = df.rolling('28D', on='_sort_date')['Easy Duration'].sum()
        df['Rolling 28d Total Minutes'] = df.rolling('28D', on='_sort_date')['Total Duration'].sum()
        df['% Easy Runs (28d Rolling)'] = (df['Rolling 28d Easy Minutes'] / df['Rolling 28d Total Minutes']) * 100

    if 'Sleep Start Time' in df.columns:
        df['Sleep Start Time (decimal hours)'] = df['Sleep Start Time'].apply(time_to_decimal)
        sleep_adj = df['Sleep Start Time (decimal hours)'].apply(adjust_for_midnight)
        df['Sleep Start Time Variance - 7d Rolling Std Dev (hours)'] = sleep_adj.rolling(window=7, min_periods=3).std()

    if 'Sleep Need (min)' in df.columns and 'Sleep Length (min)' in df.columns:
        sleep_deficit = (df['Sleep Need (min)'] - df['Sleep Length (min)']).clip(lower=0)
        df['Sleep Deficit EWMA (min)'] = sleep_deficit.ewm(span=4, adjust=False).mean()

    # Z-scores computed against a backward-shifted 60d baseline to prevent data leakage
    if 'Overnight Resting HR (bpm)' in df.columns:
        shifted_rhr = df['Overnight Resting HR (bpm)'].shift(7)
        rhr_mean = shifted_rhr.rolling(60, min_periods=30).mean()
        rhr_std = shifted_rhr.rolling(60, min_periods=30).std()
        daily_rhr_z = (df['Overnight Resting HR (bpm)'] - rhr_mean) / rhr_std
        df['Resting HR Z-Score - 3d EWMA (SD)'] = daily_rhr_z.ewm(span=3, adjust=False).mean()

    if 'Overnight HRV (ms)' in df.columns:
        shifted_hrv = df['Overnight HRV (ms)'].shift(7)
        hrv_mean = shifted_hrv.rolling(60, min_periods=30).mean()
        hrv_std = shifted_hrv.rolling(60, min_periods=30).std()
        daily_hrv_z = (df['Overnight HRV (ms)'] - hrv_mean) / hrv_std
        df['HRV RMSSD Z-Score - 3d EWMA (SD)'] = daily_hrv_z.ewm(span=3, adjust=False).mean()

    if 'Daily_Morning_Weight_kg' in df.columns:
        df['Weight - Morning 7d Avg (kg)'] = df['Daily_Morning_Weight_kg'].rolling(window=7, min_periods=1).mean()

    if 'Daily_Body_Fat_pct' in df.columns:
        df['Body Fat - US Army Calibrated 7d Avg (%)'] = df['Daily_Body_Fat_pct'].rolling(window=7, min_periods=1).mean()

    # 8. Column Mapping & Selecting Exact User Structure
    target_columns = [
        'Date (YYYY-MM-DD)',
        'Time at Work (hours)',
        'Weight - Morning 7d Avg (kg)',
        'Sleep Length (min)',
        'Sleep Start Time (decimal hours)',
        'Sleep Start Time Variance - 7d Rolling Std Dev (hours)',
        'Sleep Deficit EWMA (min)',
        'Garmin Sleep Score (raw 0–100)',
        'Overnight Respiration Rate (breaths/min)',
        'Overnight Resting HR (raw bpm)',
        'Resting HR Z-Score - 3d EWMA (SD)',
        'HRV RMSSD Z-Score - 3d EWMA (SD)',
        'Garmin Waking Average Stress Score (raw 0–100)',
        'Daily Steps',
        'Daily Moderate Intensity Minutes',
        'Daily Vigorous Intensity Minutes',
        'Chronic Training Load - CTL (28d EWMA)',
        'Acute-to-Chronic Workload Ratio - ACWR',
        'Daily Running Distance (km)',
        'Highest Load Run Start Time',
        '% Easy Runs (28d Rolling)',
        'Average Grade Adjusted Pace - GAP (min/km)',
        'Total Strength Training Duration (min)',
        'VO2 Max (ml/kg/min)',
        'Lactate Threshold Pace (min/km)',
        'Body Fat - US Army Calibrated 7d Avg (%)',
        'Withings Pulse Wave Velocity (m/s)',
        'Systolic Blood Pressure (mmHg)',
        'Diastolic Blood Pressure (mmHg)',
        'Medical Note'
    ]

    rename_map = {
        'Date_YYYY_MM_DD': 'Date (YYYY-MM-DD)',
        'Garmin Sleep Score (0-100)': 'Garmin Sleep Score (raw 0–100)',
        'Overnight Respiration Rate (brpm)': 'Overnight Respiration Rate (breaths/min)',
        'Overnight Resting HR (bpm)': 'Overnight Resting HR (raw bpm)',
        'Waking Average Stress Score (0-100)': 'Garmin Waking Average Stress Score (raw 0–100)',
        'Total Running Distance (km)': 'Daily Running Distance (km)',
        "Average Grade Adjusted Pace for that day's runs (weighted by distance or time)": 'Average Grade Adjusted Pace - GAP (min/km)',
        'Pulse_Wave_Velocity_m_s': 'Withings Pulse Wave Velocity (m/s)',
        'Medical_Notes': 'Medical Note'
    }

    df.rename(columns=rename_map, inplace=True)

    for col in target_columns:
        if col not in df.columns:
            df[col] = np.nan

    df_export = df.sort_values('_sort_date', ascending=False).reset_index(drop=True)
    df_export = df_export[target_columns]

    # 9. Strict Type & Decimal Formatting
    float_1dp = [
        'Time at Work (hours)', 'Garmin Waking Average Stress Score (raw 0–100)', 
        'Overnight Respiration Rate (breaths/min)', 'VO2 Max (ml/kg/min)', '% Easy Runs (28d Rolling)'
    ]
    float_2dp = [
        'Weight - Morning 7d Avg (kg)', 'Sleep Start Time (decimal hours)', 
        'Sleep Start Time Variance - 7d Rolling Std Dev (hours)', 'Sleep Deficit EWMA (min)', 
        'Resting HR Z-Score - 3d EWMA (SD)', 'HRV RMSSD Z-Score - 3d EWMA (SD)', 
        'Chronic Training Load - CTL (28d EWMA)', 'Acute-to-Chronic Workload Ratio - ACWR', 
        'Daily Running Distance (km)', 'Body Fat - US Army Calibrated 7d Avg (%)', 
        'Withings Pulse Wave Velocity (m/s)'
    ]
    int_cols = [
        'Sleep Length (min)', 'Garmin Sleep Score (raw 0–100)', 'Overnight Resting HR (raw bpm)', 
        'Daily Steps', 'Daily Moderate Intensity Minutes', 'Daily Vigorous Intensity Minutes', 
        'Total Strength Training Duration (min)', 'Systolic Blood Pressure (mmHg)', 
        'Diastolic Blood Pressure (mmHg)'
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

    # 10. Output Clean CSV
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

    target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)

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

    print('Processing physiological metrics...')
    generate_quantified_self_csv(
        df_garmin_raw, df_withings_raw, df_medical_raw, df_activities_raw, df_zones_raw, output_path=TARGET_FILENAME
    )

    print('Uploading updated CSV...')
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)

    if target_file_id:
        drive_service.files().update(
            fileId=target_file_id, media_body=media, fields='id, modifiedTime'
        ).execute()
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID], 'mimeType': 'text/csv'}
        drive_service.files().create(
            body=file_metadata, media_body=media, fields='id, modifiedTime'
        ).execute()

    print('Export and upload complete.')
