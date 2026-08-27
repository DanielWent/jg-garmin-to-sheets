import os
import io
import json
import pandas as pd
import numpy as np
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# Configurable Demographic Variables
AGE = 40
HEIGHT_CM = 185
MAX_HR = 190

def convert_pace_to_decimal(pace_str):
    if pd.isna(pace_str) or not isinstance(pace_str, str) or ':' not in pace_str:
        return np.nan
    try:
        minutes, seconds = pace_str.split(':')
        return float(minutes) + (float(seconds) / 60.0)
    except ValueError:
        return np.nan

def generate_quantified_self_csv(df_garmin: pd.DataFrame, df_withings: pd.DataFrame, output_path: str = "drw_quantified_self.csv"):
    
    # 1. Process Garmin Data
    garmin_mapping = {
        'Date (YYYY-MM-DD)': 'Date_YYYY_MM_DD',
        'Total Running Distance (km)': 'Daily_Running_Distance_km',
        'Total Running Duration (min)': 'Daily_Running_Duration_min',
        'Total Walking Distance (km)': 'Daily_Walking_Distance_km',
        'Total Strength Training Duration (min)': 'Daily_Strength_Duration_min',
        'Daily Steps': 'Daily_Steps_Count',
        'Garmin Training Load (7 Day Sum)': 'Garmin_7d_Training_Load_Sum',
        'VO2 Max (ml/kg/min)': 'Garmin_VO2_Max_ml_kg_min',
        'Lactate Threshold Pace (min/km)': 'Lactate_Threshold_Pace', 
        'Lactate Threshold Heart Rate (bpm)': 'Lactate_Threshold_Heart_Rate_bpm',
        'Sleep Length (min)': 'Overnight_Sleep_Duration_min',
        'Sleep Start Time': 'Sleep_Start_Time_HH_MM',
        'Sleep End Time': 'Sleep_End_Time_HH_MM',
        'Overnight Resting HR (bpm)': 'Overnight_Resting_Heart_Rate_bpm',
        'Overnight HRV (ms)': 'Overnight_HRV_RMSSD_ms',
        'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
        'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg'
    }
    df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x))
    
    # 2. Process Withings Data
    df_withings['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_withings['date'], format='mixed', dayfirst=True, errors='coerce'
    ).dt.strftime('%Y-%m-%d')
    
    # Aggregate multiple readings per day to a single daily mean
    df_w_daily = df_withings.groupby('Date_YYYY_MM_DD').agg({
        'Weight (kg)': 'mean',
        'Body Fat (%)': 'mean',
        'Pulse Wave Velocity (m/s)': 'mean'
    }).reset_index()
    
    withings_mapping = {
        'Weight (kg)': 'Daily_Morning_Weight_kg',
        'Body Fat (%)': 'Raw_Body_Fat_Percentage',
        'Pulse Wave Velocity (m/s)': 'Pulse_Wave_Velocity_m_s'
    }
    df_w_daily = df_w_daily.rename(columns=withings_mapping)
    
    # 3. Merge Datasets
    df = pd.merge(df_g, df_w_daily, on='Date_YYYY_MM_DD', how='left')
    df = df.sort_values(by="Date_YYYY_MM_DD", ascending=True).reset_index(drop=True)
    
    # 4. Pace and Time Formatting
    if "Lactate_Threshold_Pace" in df.columns:
        df["Lactate_Threshold_Pace_decimal_min_km"] = df["Lactate_Threshold_Pace"].apply(convert_pace_to_decimal)
        
    for col in ["Sleep_Start_Time_HH_MM", "Sleep_End_Time_HH_MM"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce").dt.strftime("%H:%M")

    # 5. Derived Metrics (Rolling Windows)
    if "Daily_Running_Distance_km" in df.columns:
        df["Running_Distance_28d_Total_km"] = df["Daily_Running_Distance_km"].rolling(window=28, min_periods=1).sum().round(2)
    
    if "Overnight_Resting_Heart_Rate_bpm" in df.columns:
        df["Resting_Heart_Rate_7d_Average_bpm"] = df["Overnight_Resting_Heart_Rate_bpm"].rolling(window=7, min_periods=1).mean().round(1)
        
    if "Overnight_HRV_RMSSD_ms" in df.columns:
        df["HRV_RMSSD_7d_Average_ms"] = df["Overnight_HRV_RMSSD_ms"].rolling(window=7, min_periods=1).mean().round(1)
        shifted_hrv = df["Overnight_HRV_RMSSD_ms"].shift(7)
        shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
        shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()
        df["HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore"] = ((df["HRV_RMSSD_7d_Average_ms"] - shifted_60d_mean) / shifted_60d_std).round(2)
    
    if "Raw_Body_Fat_Percentage" in df.columns:
        df["Body_Fat_Percentage_7d_Average"] = df["Raw_Body_Fat_Percentage"].rolling(window=7, min_periods=1).mean().round(1)
        
    if "Daily_Morning_Weight_kg" in df.columns:
        df["Daily_Morning_Weight_kg"] = df["Daily_Morning_Weight_kg"].round(2)
        
    if "Pulse_Wave_Velocity_m_s" in df.columns:
        df["Pulse_Wave_Velocity_m_s"] = df["Pulse_Wave_Velocity_m_s"].round(2)

    # 6. Slice and align to strict export schema
    df_export = df.tail(730).copy()

    required_columns = [
        "Date_YYYY_MM_DD", "Daily_Running_Distance_km", "Daily_Running_Duration_min",
        "Daily_Walking_Distance_km", "Daily_Strength_Duration_min", "Daily_Steps_Count",
        "Running_Distance_28d_Total_km", "Garmin_7d_Training_Load_Sum", "Garmin_VO2_Max_ml_kg_min",
        "Lactate_Threshold_Pace_decimal_min_km", "Lactate_Threshold_Heart_Rate_bpm", 
        "Overnight_Sleep_Duration_min", "Sleep_Start_Time_HH_MM", "Sleep_End_Time_HH_MM",
        "Overnight_Resting_Heart_Rate_bpm", "Resting_Heart_Rate_7d_Average_bpm",
        "Overnight_HRV_RMSSD_ms", "HRV_RMSSD_7d_Average_ms", 
        "HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore", "Daily_Morning_Weight_kg",
        "Body_Fat_Percentage_7d_Average", "Pulse_Wave_Velocity_m_s", 
        "Resting_Systolic_Blood_Pressure_mmHg", "Resting_Diastolic_Blood_Pressure_mmHg"
    ]

    for col in required_columns:
        if col not in df_export.columns:
            df_export[col] = np.nan

    df_export = df_export[required_columns]

    # Explicit integer targeting prevents floating point crash
    integer_columns = [
        "Daily_Running_Duration_min",
        "Daily_Strength_Duration_min",
        "Daily_Steps_Count",
        "Garmin_7d_Training_Load_Sum",
        "Lactate_Threshold_Heart_Rate_bpm",
        "Overnight_Sleep_Duration_min",
        "Overnight_Resting_Heart_Rate_bpm",
        "Overnight_HRV_RMSSD_ms",
        "Resting_Systolic_Blood_Pressure_mmHg",
        "Resting_Diastolic_Blood_Pressure_mmHg"
    ]
    
    for col in integer_columns:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round().astype('Int64')

    # 7. Injection & Export
    header_string = f"# Context: Male, Age: {AGE}, Height: {HEIGHT_CM} cm, Max HR: {MAX_HR} bpm\n"
    with open(output_path, "w") as f:
        f.write(header_string)
        
    df_export.to_csv(output_path, mode="a", header=True, index=False, na_rep="")


def get_file_id(service, filename, folder_id):
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
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


if __name__ == "__main__":
    FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
    SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    GARMIN_FILENAME = "drw_garmin_data.csv"
    WITHINGS_FILENAME = "drw_withings_bodyscan_data.csv"
    TARGET_FILENAME = "drw_quantified_self.csv"
    
    if not FOLDER_ID:
        raise ValueError("DRIVE_FOLDER_ID environment variable is not set.")
    if not SERVICE_ACCOUNT_JSON:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable is not set.")
        
    print("Authenticating with Google Drive...")
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, 
        scopes=['https://www.googleapis.com/auth/drive']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    
    print(f"Locating files in folder {FOLDER_ID}...")
    garmin_file_id = get_file_id(drive_service, GARMIN_FILENAME, FOLDER_ID)
    withings_file_id = get_file_id(drive_service, WITHINGS_FILENAME, FOLDER_ID)
    target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)
    
    if not garmin_file_id:
        raise FileNotFoundError(f"Could not find '{GARMIN_FILENAME}' in Drive folder.")
    if not withings_file_id:
        raise FileNotFoundError(f"Could not find '{WITHINGS_FILENAME}' in Drive folder.")

    print("Downloading raw data...")
    garmin_data = download_drive_file(drive_service, garmin_file_id)
    withings_data = download_drive_file(drive_service, withings_file_id)
    
    df_garmin_raw = pd.read_csv(garmin_data)
    df_withings_raw = pd.read_csv(withings_data)
    
    print("Processing physiological metrics...")
    generate_quantified_self_csv(df_garmin_raw, df_withings_raw, output_path=TARGET_FILENAME)
    
    print("Uploading updated CSV to Google Drive...")
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)
    
    if target_file_id:
        drive_service.files().update(fileId=target_file_id, media_body=media).execute()
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID]}
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        
    print("Export and upload complete.")
