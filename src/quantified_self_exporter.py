# DATA METRICS REFERENCE
#
# | Metric Name | File Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- | :--- |
# | Date | drw_garmin_data.csv | Column A | Unit: None | YYYY-MM-DD |
# | User Name | drw_garmin_data.csv | Column B | Unit: None | String |
# | User Age | drw_garmin_data.csv | Column C | Unit: Years | Decimal |
# | User Gender | drw_garmin_data.csv | Column D | Unit: None | String |
# | Physiological Maximum Heart Rate | drw_garmin_data.csv | Column E | Unit: bpm | Integer |
# | VO2 Max | drw_garmin_data.csv | Column F | Unit: ml/kg/min | Decimal |
# | VO2 Max Percentile | drw_garmin_data.csv | Column G | Unit: % | Decimal |
# | Lactate Threshold Pace | drw_garmin_data.csv | Column H | Unit: min/km | MM:SS |
# | Lactate Threshold Heart Rate | drw_garmin_data.csv | Column I | Unit: bpm | Integer |
# | Garmin Sleep Score | drw_garmin_data.csv | Column J | Unit: Score | Integer |
# | Sleep Start Time | drw_garmin_data.csv | Column K | Unit: None | HH:MM |
# | Sleep End Time | drw_garmin_data.csv | Column L | Unit: None | HH:MM |
# | Deep Sleep | drw_garmin_data.csv | Column M | Unit: Minutes | Integer |
# | Light Sleep | drw_garmin_data.csv | Column N | Unit: Minutes | Integer |
# | REM Sleep | drw_garmin_data.csv | Column O | Unit: Minutes | Integer |
# | Awake Time | drw_garmin_data.csv | Column P | Unit: Minutes | Integer |
# | Sleep Length | drw_garmin_data.csv | Column Q | Unit: Minutes | Integer |
# | Sleep Need | drw_garmin_data.csv | Column R | Unit: Minutes | Integer |
# | Overnight Average Pulse Ox / SpO2 | drw_garmin_data.csv | Column S | Unit: % | Integer |
# | Garmin Average Stress Score | drw_garmin_data.csv | Column T | Unit: Score | Integer |
# | Daily Min Body Battery | drw_garmin_data.csv | Column U | Unit: Score | Integer |
# | Daily Max Body Battery | drw_garmin_data.csv | Column V | Unit: Score | Integer |
# | Body Battery Charged | drw_garmin_data.csv | Column W | Unit: Score | Integer |
# | Body Battery Drained | drw_garmin_data.csv | Column X | Unit: Score | Integer |
# | Daily Steps | drw_garmin_data.csv | Column Y | Unit: Steps | Integer |
# | Daily Floors Climbed | drw_garmin_data.csv | Column Z | Unit: Floors | Integer |
# | Daily Intensity Minutes | drw_garmin_data.csv | Column AA | Unit: Minutes | Integer |
# | Total Calories | drw_garmin_data.csv | Column AB | Unit: kcal | Integer |
# | Systolic Blood Pressure | drw_garmin_data.csv | Column AC | Unit: mmHg | Integer |
# | Diastolic Blood Pressure | drw_garmin_data.csv | Column AD | Unit: mmHg | Integer |
# | Garmin Training Load | drw_garmin_data.csv | Column AE | Unit: Load | Integer |
# | Garmin Training Load Focus | drw_garmin_data.csv | Column AF | Unit: None | String |
# | Morning Garmin Training Readiness | drw_garmin_data.csv | Column AG | Unit: Score | Integer |
# | Overnight Resting HR | drw_garmin_data.csv | Column AH | Unit: bpm | Integer |
# | Overnight HRV | drw_garmin_data.csv | Column AI | Unit: ms | Integer |
# | Garmin HRV Status | drw_garmin_data.csv | Column AJ | Unit: None | String |
# | Garmin Training Status | drw_garmin_data.csv | Column AK | Unit: None | String |
# | Total Walking Distance | drw_garmin_data.csv | Column AL | Unit: km | Decimal |
# | Total Walking Duration | drw_garmin_data.csv | Column AM | Unit: Minutes | Decimal |
# | Total Running Activities Count | drw_garmin_data.csv | Column AN | Unit: Count | Integer |
# | Total Running Distance | drw_garmin_data.csv | Column AO | Unit: km | Decimal |
# | Total Running Duration | drw_garmin_data.csv | Column AP | Unit: Minutes | Decimal |
# | Total Strength Training Duration | drw_garmin_data.csv | Column AQ | Unit: Minutes | Decimal |
# | Date and Time | drw_withings_bodyscan_data.csv | Column A | Unit: None | DD/MM/YYYY HH:MM |
# | Weight | drw_withings_bodyscan_data.csv | Column B | Unit: kg | Decimal |
# | Body Mass Index (BMI) | drw_withings_bodyscan_data.csv | Column C | Unit: None | Decimal |
# | Body Fat | drw_withings_bodyscan_data.csv | Column D | Unit: % | Decimal |
# | Visceral Fat Rating | drw_withings_bodyscan_data.csv | Column E | Unit: Rating | Decimal |
# | Pulse Wave Velocity | drw_withings_bodyscan_data.csv | Column F | Unit: m/s | Decimal |
# | AFib Status | drw_withings_bodyscan_data.csv | Column G | Unit: None | String |
# | Vascular Age | drw_withings_bodyscan_data.csv | Column H | Unit: Years | Decimal |
# | Nerve Health Score | drw_withings_bodyscan_data.csv | Column I | Unit: Score | Decimal |

import os
import io
import json
import pandas as pd
import numpy as np
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# Configurable Demographic Variables
DOB = "1985-10-25"
HEIGHT_CM = 185
LPA_NMOL_L = 263

def convert_pace_to_decimal(pace_str):
    if pd.isna(pace_str) or not isinstance(pace_str, str) or ':' not in pace_str:
        return np.nan
    try:
        minutes, seconds = pace_str.split(':')
        return float(minutes) + (float(seconds) / 60.0)
    except ValueError:
        return np.nan

def generate_quantified_self_csv(df_garmin: pd.DataFrame, df_withings: pd.DataFrame, df_medical: pd.DataFrame, output_path: str = "drw_quantified_self.csv"):
    
    # 1. Process Garmin Data
    garmin_mapping = {
        'Date (YYYY-MM-DD)': 'Date_YYYY_MM_DD',
        'Physiological Maximum Heart Rate (bpm)': 'Physiological_Max_HR_bpm',
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
        'Overnight HRV (ms)': 'Overnight_Average_HRV_RMSSD_ms',
        'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
        'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg'
    }
    df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x))
    if 'Date_YYYY_MM_DD' not in df_g.columns:
        df_g['Date_YYYY_MM_DD'] = np.nan
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(df_g['Date_YYYY_MM_DD'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    # 2. Process Withings Data
    df_withings['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_withings['date'], format='mixed', dayfirst=True, errors='coerce'
    ).dt.strftime('%Y-%m-%d')
    
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
    
    # 3. Process Medical Data (with explicit unit headers)
    df_medical['Date_YYYY_MM_DD'] = pd.to_datetime(
        df_medical['Test Date'], format='%d/%m/%Y', errors='coerce'
    ).dt.strftime('%Y-%m-%d')
    df_medical['clean_test'] = df_medical['Test Name'].astype(str).str.lower().str.strip()
    
    test_map = {
        'ApoB_g_L': ['apolipoprotein b', 'apob'],
        'LDL_Cholesterol_mmol_L': ['ldl cholesterol', 'ldl', 'ldl cholesterol (calculated)'],
        'HDL_Cholesterol_mmol_L': ['hdl cholesterol', 'hdl'],
        'Triglycerides_mmol_L': ['triglycerides', 'triglyceride'],
        'HbA1c_mmol_mol': ['hba1c'],
        'Ferritin_ug_L': ['ferritin'],
        'Vitamin_D_nmol_L': ['vitamin d', '25-oh vitamin d', 'vit d', '25(oh)d'],
        'hs_CRP_mg_L': ['hs-crp', 'crp high sensitivity', 'high sensitivity crp', 'hscrp', 'crp'],
        'ALT_U_L': ['alt', 'alanine transferase', 'alanine aminotransferase', 'sgpt'],
        'GGT_IU_L': ['ggt', 'gamma-gt', 'gamma glutamyl transferase', 'gamma-glutamyl transferase'],
        'Creatinine_umol_L': ['creatinine', 'creatine'],
        'eGFR_ml_min_1_73m2': ['egfr', 'estimated glomerular filtration rate'],
        'TSH_mIU_L': ['tsh', 'thyroid stimulating hormone']
    }

    mapped_medical_data = []
    for test_col, aliases in test_map.items():
        mask = df_medical['clean_test'].isin(aliases)
        subset = df_medical[mask].copy()
        if not subset.empty:
            subset_daily = subset.groupby('Date_YYYY_MM_DD')['Result'].first().reset_index()
            subset_daily = subset_daily.rename(columns={'Result': test_col})
            mapped_medical_data.append(subset_daily)

    if mapped_medical_data:
        df_m_daily = mapped_medical_data[0]
        for m in mapped_medical_data[1:]:
            df_m_daily = pd.merge(df_m_daily, m, on='Date_YYYY_MM_DD', how='outer')
    else:
        df_m_daily = pd.DataFrame(columns=['Date_YYYY_MM_DD'] + list(test_map.keys()))

    # 4. Merge All Datasets
    df = pd.merge(df_g, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    
    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df = df.sort_values(by="Date_YYYY_MM_DD", ascending=True).reset_index(drop=True)
    
    # 5. Pace and Time Formatting
    if "Lactate_Threshold_Pace" in df.columns:
        df["Lactate_Threshold_Pace_decimal_min_km"] = df["Lactate_Threshold_Pace"].apply(convert_pace_to_decimal)
        
    for col in ["Sleep_Start_Time_HH_MM", "Sleep_End_Time_HH_MM"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce").dt.strftime("%H:%M")

    # 6. Derived Metrics
    if "Daily_Running_Distance_km" in df.columns:
        df["Running_Distance_28d_Total_km"] = df["Daily_Running_Distance_km"].rolling(window=28, min_periods=1).sum().round(2)
    
    if "Overnight_Resting_Heart_Rate_bpm" in df.columns:
        df["Resting_Heart_Rate_7d_Average_bpm"] = df["Overnight_Resting_Heart_Rate_bpm"].rolling(window=7, min_periods=1).mean().round(1)
        
    if "Overnight_Average_HRV_RMSSD_ms" in df.columns:
        df["Overnight_Average_HRV_RMSSD_7d_Average_ms"] = df["Overnight_Average_HRV_RMSSD_ms"].rolling(window=7, min_periods=1).mean().round(1)
        shifted_hrv = df["Overnight_Average_HRV_RMSSD_ms"].shift(7)
        shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
        shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()
        df["Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore"] = ((df["Overnight_Average_HRV_RMSSD_7d_Average_ms"] - shifted_60d_mean) / shifted_60d_std).round(2)
    
    if "Raw_Body_Fat_Percentage" in df.columns:
        df["Body_Fat_Percentage_7d_Average"] = df["Raw_Body_Fat_Percentage"].rolling(window=7, min_periods=1).mean().round(1)
        
    if "Daily_Morning_Weight_kg" in df.columns:
        df["Daily_Morning_Weight_kg"] = df["Daily_Morning_Weight_kg"].round(2)
        
    if "Pulse_Wave_Velocity_m_s" in df.columns:
        df["Pulse_Wave_Velocity_m_s"] = df["Pulse_Wave_Velocity_m_s"].round(2)

    # 7. Filter, Re-sort Descending, and Align Output Schema
    df_export = df.tail(730).copy()
    df_export = df_export.sort_values(by="Date_YYYY_MM_DD", ascending=False).reset_index(drop=True)

    required_columns = [
        "Date_YYYY_MM_DD", "Daily_Running_Distance_km", "Daily_Running_Duration_min",
        "Daily_Walking_Distance_km", "Daily_Strength_Duration_min", "Daily_Steps_Count",
        "Running_Distance_28d_Total_km", "Garmin_7d_Training_Load_Sum", "Garmin_VO2_Max_ml_kg_min",
        "Lactate_Threshold_Pace_decimal_min_km", "Lactate_Threshold_Heart_Rate_bpm", 
        "Physiological_Max_HR_bpm", "Overnight_Sleep_Duration_min", "Sleep_Start_Time_HH_MM", 
        "Sleep_End_Time_HH_MM", "Overnight_Resting_Heart_Rate_bpm", "Resting_Heart_Rate_7d_Average_bpm",
        "Overnight_Average_HRV_RMSSD_ms", "Overnight_Average_HRV_RMSSD_7d_Average_ms", 
        "Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore", "Daily_Morning_Weight_kg",
        "Body_Fat_Percentage_7d_Average", "Pulse_Wave_Velocity_m_s", 
        "Resting_Systolic_Blood_Pressure_mmHg", "Resting_Diastolic_Blood_Pressure_mmHg",
        "ApoB_g_L", "LDL_Cholesterol_mmol_L", "HDL_Cholesterol_mmol_L", "Triglycerides_mmol_L", "HbA1c_mmol_mol",
        "Ferritin_ug_L", "Vitamin_D_nmol_L", "hs_CRP_mg_L", "ALT_U_L", "GGT_IU_L", "Creatinine_umol_L", "eGFR_ml_min_1_73m2", "TSH_mIU_L"
    ]

    for col in required_columns:
        if col not in df_export.columns:
            df_export[col] = np.nan

    df_export = df_export[required_columns]

    integer_columns = [
        "Daily_Running_Duration_min",
        "Daily_Strength_Duration_min",
        "Daily_Steps_Count",
        "Garmin_7d_Training_Load_Sum",
        "Lactate_Threshold_Heart_Rate_bpm",
        "Physiological_Max_HR_bpm",
        "Overnight_Sleep_Duration_min",
        "Overnight_Resting_Heart_Rate_bpm",
        "Overnight_Average_HRV_RMSSD_ms",
        "Resting_Systolic_Blood_Pressure_mmHg",
        "Resting_Diastolic_Blood_Pressure_mmHg"
    ]
    
    for col in integer_columns:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round().astype('Int64')

    # 8. Demographic Header Injection & Export
    header_string = f"# Context: Male, DOB: {DOB}, Height: {HEIGHT_CM} cm, Lp(a): {LPA_NMOL_L} nmol/l\n"
    with open(output_path, "w") as f:
        f.write(header_string)
        
    df_export.to_csv(output_path, mode="a", header=True, index=False, na_rep="")


def get_file_id(service, filename, folder_id):
    safe_filename = filename.replace("'", "\\'")
    query = f"name='{safe_filename}' and '{folder_id}' in parents and trashed=false"
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
    MEDICAL_FILENAME = "Daniel's Medical Test Results.csv"
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
    medical_file_id = get_file_id(drive_service, MEDICAL_FILENAME, FOLDER_ID)
    target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)
    
    if not garmin_file_id:
        raise FileNotFoundError(f"Could not find '{GARMIN_FILENAME}' in Drive folder.")
    if not withings_file_id:
        raise FileNotFoundError(f"Could not find '{WITHINGS_FILENAME}' in Drive folder.")
    if not medical_file_id:
        raise FileNotFoundError(f"Could not find '{MEDICAL_FILENAME}' in Drive folder.")

    print("Downloading raw data...")
    garmin_data = download_drive_file(drive_service, garmin_file_id)
    withings_data = download_drive_file(drive_service, withings_file_id)
    medical_data = download_drive_file(drive_service, medical_file_id)
    
    df_garmin_raw = pd.read_csv(garmin_data)
    df_withings_raw = pd.read_csv(withings_data)
    df_medical_raw = pd.read_csv(medical_data)
    
    print("Processing physiological metrics...")
    generate_quantified_self_csv(df_garmin_raw, df_withings_raw, df_medical_raw, output_path=TARGET_FILENAME)
    
    print("Uploading updated CSV to Google Drive...")
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)
    
    if target_file_id:
        drive_service.files().update(fileId=target_file_id, media_body=media).execute()
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID]}
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        
    print("Export and upload complete.")
