import io
import json
import os
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import numpy as np
import pandas as pd


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
      'Overnight Resting HR (bpm)': 'Overnight_Resting_Heart_Rate_bpm',
      'Overnight HRV (ms)': 'Overnight_Average_HRV_RMSSD_ms',
      'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
      'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg',
  }
  df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x))[cite: 1]

  if 'Date_YYYY_MM_DD' in df_garmin.columns:
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_garmin['Date_YYYY_MM_DD'], errors='coerce'
    ).dt.strftime('%Y-%m-%d')
  elif 'Date (YYYY-MM-DD)' in df_garmin.columns:
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_garmin['Date (YYYY-MM-DD)'], errors='coerce'
    ).dt.strftime('%Y-%m-%d')[cite: 1]
  elif 'Date' in df_garmin.columns:
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_garmin['Date'], errors='coerce'
    ).dt.strftime('%Y-%m-%d')
  else:
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_garmin.iloc[:, 0], errors='coerce'
    ).dt.strftime('%Y-%m-%d')

  # Positional fallbacks for Garmin columns if headers differ
  if 'Total_Calories' not in df_g.columns and df_garmin.shape[1] > 27:[cite: 1]
    df_g['Total_Calories'] = df_garmin.iloc[:, 27][cite: 1]
  if (
      'Garmin_Moderate_Intensity_Minutes' not in df_g.columns
      and df_garmin.shape[1] > 43
  ):[cite: 1]
    df_g['Garmin_Moderate_Intensity_Minutes'] = df_garmin.iloc[:, 43][cite: 1]
  if (
      'Garmin_Vigorous_Intensity_Minutes' not in df_g.columns
      and df_garmin.shape[1] > 44
  ):[cite: 1]
    df_g['Garmin_Vigorous_Intensity_Minutes'] = df_garmin.iloc[:, 44][cite: 1]
  if 'Active_Calories' not in df_g.columns and df_garmin.shape[1] > 45:[cite: 1]
    df_g['Active_Calories'] = df_garmin.iloc[:, 45][cite: 1]

  df_g = df_g.loc[:, ~df_g.columns.duplicated()][cite: 1]

  # 2. Process Garmin Activities Data
  act_date_col = (
      'Date (YYYY-MM-DD)'
      if 'Date (YYYY-MM-DD)' in df_activities.columns
      else df_activities.columns[0]
  )
  df_activities['Date_YYYY_MM_DD'] = pd.to_datetime(
      df_activities[act_date_col], errors='coerce'
  ).dt.strftime('%Y-%m-%d')[cite: 1]
  df_a_daily = (
      df_activities.groupby('Date_YYYY_MM_DD')
      .agg({'Activity Training Load': 'sum'})
      .reset_index()
  )[cite: 1]
  df_a_daily = df_a_daily.rename(
      columns={'Activity Training Load': 'Daily_Activity_Training_Load'}
  )[cite: 1]

  # 3. Process Withings Data
  date_col_w = (
      'date' if 'date' in df_withings.columns else df_withings.columns[0]
  )
  df_withings['Date_YYYY_MM_DD'] = pd.to_datetime(
      df_withings[date_col_w], format='mixed', dayfirst=True, errors='coerce'
  ).dt.strftime('%Y-%m-%d')[cite: 1]

  weight_col = (
      'Weight (kg)'
      if 'Weight (kg)' in df_withings.columns
      else df_withings.columns[1]
  )[cite: 1]
  body_fat_col = (
      'Body Fat (%)'
      if 'Body Fat (%)' in df_withings.columns
      else df_withings.columns[2]
  )[cite: 1]
  pwv_col = (
      'Pulse Wave Velocity (m/s)'
      if 'Pulse Wave Velocity (m/s)' in df_withings.columns
      else df_withings.columns[3]
  )[cite: 1]

  df_w_daily = (
      df_withings.groupby('Date_YYYY_MM_DD')
      .agg({weight_col: 'mean', body_fat_col: 'mean', pwv_col: 'mean'})
      .reset_index()
  )[cite: 1]

  withings_mapping = {
      weight_col: 'Daily_Morning_Weight_kg',
      body_fat_col: 'Raw_Body_Fat_Percentage',
      pwv_col: 'Pulse_Wave_Velocity_m_s',
  }[cite: 1]
  df_w_daily = df_w_daily.rename(columns=withings_mapping)[cite: 1]

  # 4. Process Medical Data (Positional: Col A = Date, Col D = Biological Significance, Col E = Note)
  df_med = df_medical.copy()
  df_med['Date_YYYY_MM_DD'] = pd.to_datetime(
      df_med.iloc[:, 0], dayfirst=True, errors='coerce'
  ).dt.strftime('%Y-%m-%d')

  # Filter where Biological Significance (Column D / Index 3) equals 1
  sig_col = df_med.iloc[:, 3]
  is_significant = (pd.to_numeric(sig_col, errors='coerce') == 1) | (
      sig_col.astype(str).str.strip() == '1'
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
  zone_date_col = (
      'Date' if 'Date' in df_zones.columns else df_zones.columns[0]
  )
  df_zones['Date_YYYY_MM_DD'] = pd.to_datetime(
      df_zones[zone_date_col], errors='coerce'
  ).dt.strftime('%Y-%m-%d')[cite: 1]

  zone_mapping = {
      'Time in Home Zone (hours)': 'Time_in_Home_Zone_hours',
      'Time in Work Zone (hours)': 'Time_in_Work_Zone_hours',
  }[cite: 1]
  avail_zone_cols = ['Date_YYYY_MM_DD'] + [
      v for k, v in zone_mapping.items() if k in df_zones.columns
  ]
  df_z_daily = df_zones.rename(columns=zone_mapping)[avail_zone_cols]

  # 6. Merge All Datasets
  df = pd.merge(
      df_g,
      df_a_daily[['Date_YYYY_MM_DD', 'Daily_Activity_Training_Load']],
      on='Date_YYYY_MM_DD',
      how='outer',
  )[cite: 1]
  df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')[cite: 1]
  df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
  df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')[cite: 1]

  df = df.dropna(subset=['Date_YYYY_MM_DD'])[cite: 1]
  df = df.sort_values(by='Date_YYYY_MM_DD', ascending=True).reset_index(
      drop=True
  )[cite: 1]
  df = df.loc[:, ~df.columns.duplicated()][cite: 1]
  df['Daily_Activity_Training_Load'] = df[
      'Daily_Activity_Training_Load'
  ].fillna(0)[cite: 1]

  # 7. Derived Metrics
  if 'Lactate_Threshold_Pace' in df.columns:[cite: 1]
    df['Lactate_Threshold_Pace_decimal_min_km'] = df[
        'Lactate_Threshold_Pace'
    ].apply(convert_pace_to_decimal)[cite: 1]

  def time_to_decimal(time_str):[cite: 1]
    if pd.isna(time_str):[cite: 1]
      return np.nan[cite: 1]
    try:[cite: 1]
      h, m = map(int, str(time_str).split(':'))[cite: 1]
      if h < 12:[cite: 1]
        h += 24[cite: 1]
      return round(h + (m / 60.0), 2)[cite: 1]
    except ValueError:[cite: 1]
      return np.nan[cite: 1]

  if 'Sleep_Start_Time_HH_MM' in df.columns:[cite: 1]
    df['Sleep_Start_Decimal'] = df['Sleep_Start_Time_HH_MM'].apply(
        time_to_decimal
    )[cite: 1]

  acute_load = (
      df['Daily_Activity_Training_Load'].rolling(window=7, min_periods=1).sum()
  )[cite: 1]
  chronic_load = (
      df['Daily_Activity_Training_Load'].rolling(window=28, min_periods=1).sum()
      / 4
  )[cite: 1]
  df['Acute_to_Chronic_Training_Load_Ratio'] = (
      (acute_load / chronic_load).replace([np.inf, -np.inf], np.nan).round(2)
  )[cite: 1]

  if (
      'Sleep_Need_min' in df.columns
      and 'Overnight_Sleep_Duration_min' in df.columns
  ):[cite: 1]
    daily_sleep_deficit = (
        df['Sleep_Need_min'] - df['Overnight_Sleep_Duration_min']
    )[cite: 1]
    df['EWMA_Sleep_Debt_min'] = daily_sleep_deficit.ewm(
        span=7, adjust=False
    ).mean()[cite: 1]

  if 'Daily_Running_Distance_km' in df.columns:[cite: 1]
    df['Running_Distance_28d_Total_km'] = (
        df['Daily_Running_Distance_km']
        .rolling(window=28, min_periods=1)
        .sum()
        .round(2)
    )[cite: 1]

  if 'Overnight_Average_HRV_RMSSD_ms' in df.columns:[cite: 1]
    hrv_7d_avg = (
        df['Overnight_Average_HRV_RMSSD_ms']
        .rolling(window=7, min_periods=1)
        .mean()
    )[cite: 1]
    shifted_hrv = df['Overnight_Average_HRV_RMSSD_ms'].shift(7)[cite: 1]
    shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()[cite: 1]
    shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()[cite: 1]
    df[
        'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore'
    ] = ((hrv_7d_avg - shifted_60d_mean) / shifted_60d_std).round(2)[cite: 1]

  if 'Raw_Body_Fat_Percentage' in df.columns:[cite: 1]
    df['Body_Fat_Percentage_7d_Average'] = (
        df['Raw_Body_Fat_Percentage']
        .rolling(window=7, min_periods=1)
        .mean()
        .round(1)
    )[cite: 1]

  if 'Daily_Morning_Weight_kg' in df.columns:[cite: 1]
    df['Daily_Morning_Weight_7d_Average_kg'] = (
        df['Daily_Morning_Weight_kg']
        .rolling(window=7, min_periods=1)
        .mean()
        .round(2)
    )[cite: 1]

  if 'Active_Calories' in df.columns and 'Daily_Morning_Weight_kg' in df.columns:[cite: 1]
    effective_weight = (
        df['Daily_Morning_Weight_kg']
        .combine_first(
            df.get(
                'Daily_Morning_Weight_7d_Average_kg',
                pd.Series(np.nan, index=df.index),
            )
        )
        .ffill()
        .bfill()
    )[cite: 1]
    df['Net_Active_MET_Minutes'] = (
        pd.to_numeric(df['Active_Calories'], errors='coerce') / effective_weight
    ) * 60.0[cite: 1]

  # 8. Filter, Sort Descending, and Select Target Columns
  df_export = df.tail(730).copy()[cite: 1]
  df_export = df_export.sort_values(
      by='Date_YYYY_MM_DD', ascending=False
  ).reset_index(drop=True)[cite: 1]

  required_columns = [
      'Date_YYYY_MM_DD',
      'Time_in_Home_Zone_hours',
      'Time_in_Work_Zone_hours',
      'Daily_Steps_Count',
      'Daily_Running_Distance_km',
      'Running_Distance_28d_Total_km',
      'Garmin_Moderate_Intensity_Minutes',
      'Garmin_Vigorous_Intensity_Minutes',
      'Net_Active_MET_Minutes',
      'Garmin_7d_Training_Load_Sum',
      'Acute_to_Chronic_Training_Load_Ratio',
      'Garmin_VO2_Max_ml_kg_min',
      'Lactate_Threshold_Heart_Rate_bpm',
      'Lactate_Threshold_Pace_decimal_min_km',
      'Overnight_Sleep_Duration_min',
      'Sleep_Start_Decimal',
      'EWMA_Sleep_Debt_min',
      'Overnight_Resting_Heart_Rate_bpm',
      'Overnight_Average_HRV_RMSSD_ms',
      'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore',
      'Daily_Morning_Weight_7d_Average_kg',
      'Body_Fat_Percentage_7d_Average',
      'Resting_Systolic_Blood_Pressure_mmHg',
      'Resting_Diastolic_Blood_Pressure_mmHg',
      'Pulse_Wave_Velocity_m_s',
      'Medical_Notes',
  ]

  for col in required_columns:[cite: 1]
    if col not in df_export.columns:[cite: 1]
      df_export[col] = np.nan[cite: 1]

  df_export = df_export[required_columns][cite: 1]

  column_rename_map = {
      'Date_YYYY_MM_DD': 'Date (YYYY-MM-DD)',
      'Time_in_Home_Zone_hours': 'Time at Home (hours)',
      'Time_in_Work_Zone_hours': 'Time at Work (hours)',
      'Daily_Steps_Count': 'Step Count - Daily (steps)',
      'Daily_Running_Distance_km': 'Running Distance - Daily (km)',
      'Running_Distance_28d_Total_km': 'Running Distance - 28d Total (km)',
      'Garmin_Moderate_Intensity_Minutes': (
          'Moderate Intensity Minutes - Garmin (min)'
      ),
      'Garmin_Vigorous_Intensity_Minutes': (
          'Vigorous Intensity Minutes - Garmin (min)'
      ),
      'Net_Active_MET_Minutes': 'Net Active MET Minutes',
      'Garmin_7d_Training_Load_Sum': 'Training Load - Garmin 7d Sum',
      'Acute_to_Chronic_Training_Load_Ratio': (
          'Training Load Ratio - Acute:Chronic'
      ),
      'Garmin_VO2_Max_ml_kg_min': 'VO2 Max - Garmin (ml/kg/min)',
      'Lactate_Threshold_Heart_Rate_bpm': 'Lactate Threshold HR (bpm)',
      'Lactate_Threshold_Pace_decimal_min_km': (
          'Lactate Threshold Pace (decimal min/km)'
      ),
      'Overnight_Sleep_Duration_min': 'Sleep Duration - Overnight (min)',
      'Sleep_Start_Decimal': 'Sleep Start Time (Decimal)',
      'EWMA_Sleep_Debt_min': 'Sleep Debt - 7d EWMA (min)',
      'Overnight_Resting_Heart_Rate_bpm': 'Resting Heart Rate - Overnight (bpm)',
      'Overnight_Average_HRV_RMSSD_ms': 'HRV RMSSD - Overnight (ms)',
      'Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore': (
          'HRV RMSSD Z-Score - 7d Avg vs 60d Baseline'
      ),
      'Daily_Morning_Weight_7d_Average_kg': 'Weight - Morning 7d Avg (kg)',
      'Body_Fat_Percentage_7d_Average': 'Body Fat - 7d Avg (%)',
      'Resting_Systolic_Blood_Pressure_mmHg': (
          'Blood Pressure Systolic - Resting (mmHg)'
      ),
      'Resting_Diastolic_Blood_Pressure_mmHg': (
          'Blood Pressure Diastolic - Resting (mmHg)'
      ),
      'Pulse_Wave_Velocity_m_s': 'Pulse Wave Velocity (m/s)',
      'Medical_Notes': 'Medical Notes',
  }[cite: 1]

  df_export = df_export.rename(columns=column_rename_map)[cite: 1]
  df_export = df_export.loc[:, ~df_export.columns.duplicated()][cite: 1]

  # 9. Strict Type & Decimal Precision Formatting
  integer_columns = [
      'Step Count - Daily (steps)',
      'Moderate Intensity Minutes - Garmin (min)',
      'Vigorous Intensity Minutes - Garmin (min)',
      'Net Active MET Minutes',
      'Training Load - Garmin 7d Sum',
      'Lactate Threshold HR (bpm)',
      'Sleep Duration - Overnight (min)',
      'Sleep Debt - 7d EWMA (min)',
      'Resting Heart Rate - Overnight (bpm)',
      'HRV RMSSD - Overnight (ms)',
      'Blood Pressure Systolic - Resting (mmHg)',
      'Blood Pressure Diastolic - Resting (mmHg)',
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
      'Body Fat - 7d Avg (%)',
  ]
  for col in float_1dp_columns:
    if col in df_export.columns:
      df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(1)

  float_2dp_columns = [
      'Running Distance - Daily (km)',
      'Running Distance - 28d Total (km)',
      'Training Load Ratio - Acute:Chronic',
      'Lactate Threshold Pace (decimal min/km)',
      'Sleep Start Time (Decimal)',
      'HRV RMSSD Z-Score - 7d Avg vs 60d Baseline',
      'Weight - Morning 7d Avg (kg)',
      'Pulse Wave Velocity (m/s)',
  ]
  for col in float_2dp_columns:
    if col in df_export.columns:
      df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round(2)

  # 10. Write Out Clean CSV
  df_export.to_csv(output_path, header=True, index=False, na_rep='')


def get_file_id(service, filename, folder_id):
  safe_filename = filename.replace("'", "\\'")[cite: 1]
  query = f"name='{safe_filename}' and '{folder_id}' in parents and trashed=false"[cite: 1]
  results = service.files().list(q=query, fields='files(id, name)').execute()[cite: 1]
  items = results.get('files', [])[cite: 1]
  return items[0]['id'] if items else None[cite: 1]


def download_drive_file(service, file_id):
  request = service.files().get_media(fileId=file_id)[cite: 1]
  downloaded_data = io.BytesIO()[cite: 1]
  downloader = MediaIoBaseDownload(downloaded_data, request)[cite: 1]
  done = False[cite: 1]
  while not done:[cite: 1]
    status, done = downloader.next_chunk()[cite: 1]
  downloaded_data.seek(0)[cite: 1]
  return downloaded_data[cite: 1]


if __name__ == '__main__':
  FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')[cite: 1]
  SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SHEETS_CREDENTIALS')[cite: 1]
  GARMIN_FILENAME = 'drw_garmin_data.csv'[cite: 1]
  ACTIVITIES_FILENAME = 'drw_garmin_activities_list.csv'[cite: 1]
  WITHINGS_FILENAME = 'drw_withings_bodyscan_data.csv'[cite: 1]
  MEDICAL_FILENAME = "Daniel's Medical Test Results.csv"[cite: 1]

  ZONES_BASE_URL = 'https://dfexhoblv7ytpsxp7uiasfchbdxbl8vt.ui.nabu.casa/local/drw_home_assistant_zone_history.csv'[cite: 1]
  ZONES_URL = f'{ZONES_BASE_URL}?v={int(time.time())}'[cite: 1]

  TARGET_FILENAME = 'drw_quantified_self.csv'[cite: 1]

  if not FOLDER_ID:
    raise ValueError('DRIVE_FOLDER_ID environment variable is not set.')[cite: 1]
  if not SERVICE_ACCOUNT_JSON:
    raise ValueError(
        'GOOGLE_SHEETS_CREDENTIALS environment variable is not set.'[cite: 1]
    )

  print('Authenticating with Google Drive...')[cite: 1]
  service_account_info = json.loads(SERVICE_ACCOUNT_JSON)[cite: 1]
  creds = service_account.Credentials.from_service_account_info(
      service_account_info, scopes=['https://www.googleapis.com/auth/drive'][cite: 1]
  )
  drive_service = build('drive', 'v3', credentials=creds)[cite: 1]

  print(f'Locating files in folder {FOLDER_ID}...')[cite: 1]
  garmin_file_id = get_file_id(drive_service, GARMIN_FILENAME, FOLDER_ID)[cite: 1]
  activities_file_id = get_file_id(
      drive_service, ACTIVITIES_FILENAME, FOLDER_ID[cite: 1]
  )
  withings_file_id = get_file_id(drive_service, WITHINGS_FILENAME, FOLDER_ID)[cite: 1]
  medical_file_id = get_file_id(drive_service, MEDICAL_FILENAME, FOLDER_ID)[cite: 1]
  target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)[cite: 1]

  if not garmin_file_id:
    raise FileNotFoundError(f"Could not find '{GARMIN_FILENAME}' in Drive.")[cite: 1]
  if not activities_file_id:
    raise FileNotFoundError(
        f"Could not find '{ACTIVITIES_FILENAME}' in Drive."[cite: 1]
    )
  if not withings_file_id:
    raise FileNotFoundError(f"Could not find '{WITHINGS_FILENAME}' in Drive.")[cite: 1]
  if not medical_file_id:
    raise FileNotFoundError(f"Could not find '{MEDICAL_FILENAME}' in Drive.")[cite: 1]

  print('Downloading raw data from Google Drive and Home Assistant...')[cite: 1]
  garmin_data = download_drive_file(drive_service, garmin_file_id)[cite: 1]
  activities_data = download_drive_file(drive_service, activities_file_id)[cite: 1]
  withings_data = download_drive_file(drive_service, withings_file_id)[cite: 1]
  medical_data = download_drive_file(drive_service, medical_file_id)[cite: 1]

  df_garmin_raw = pd.read_csv(garmin_data)[cite: 1]
  df_activities_raw = pd.read_csv(activities_data)[cite: 1]
  df_withings_raw = pd.read_csv(withings_data)[cite: 1]
  df_medical_raw = pd.read_csv(medical_data)[cite: 1]
  df_zones_raw = pd.read_csv(ZONES_URL)[cite: 1]

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
  media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)[cite: 1]

  if target_file_id:
    drive_service.files().update(
        fileId=target_file_id, media_body=media[cite: 1]
    ).execute()
  else:
    file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID]}[cite: 1]
    drive_service.files().create(
        body=file_metadata, media_body=media[cite: 1]
    ).execute()

  print('Export and upload complete.')[cite: 1]
