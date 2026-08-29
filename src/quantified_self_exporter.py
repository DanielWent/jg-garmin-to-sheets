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

def generate_quantified_self_csv(df_garmin: pd.DataFrame, df_withings: pd.DataFrame, df_medical: pd.DataFrame, df_activities: pd.DataFrame, df_zones: pd.DataFrame, output_path: str = "drw_quantified_self.csv"):
    
    # 1. Process Garmin Daily Data
    # Mapped 'Garmin HRV Status (Text Label)' directly from drw_garmin_data.csv to 'HRV_Status'
    garmin_mapping = {
        'Date (YYYY-MM-DD)': 'Date_YYYY_MM_DD',
        'Physiological Maximum Heart Rate (bpm)': 'Physiological_Max_HR_bpm',
        'Total Running Distance (km)': 'Daily_Running_Distance_km',
        'Daily Steps': 'Daily_Steps_Count',
        'Garmin Training Load (7 Day Sum)': 'Garmin_7d_Training_Load_Sum',
        'VO2 Max (ml/kg/min)': 'Garmin_VO2_Max_ml_kg_min',
        'Lactate Threshold Pace (min/km)': 'Lactate_Threshold_Pace', 
        'Lactate Threshold Heart Rate (bpm)': 'Lactate Threshold_Heart_Rate_bpm',
        'Intensity Minutes': 'Garmin_Intensity_Minutes_Lactate_Threshold_Zones_min',
        'Sleep Length (min)': 'Overnight_Sleep_Duration_min',
        'Sleep Need (min)': 'Sleep_Need_min',
        'Sleep Start Time': 'Sleep_Start_Time_HH_MM',
        'Sleep End Time': 'Sleep_End_Time_HH_MM',
        'Overnight Resting HR (bpm)': 'Overnight_Resting_Heart_Rate_bpm',
        'Overnight HRV (ms)': 'Overnight_Average_HRV_RMSSD_ms',
        'Garmin HRV Status (Text Label)': 'HRV_Status',
        'Systolic Blood Pressure (mmHg)': 'Resting_Systolic_Blood_Pressure_mmHg',
        'Diastolic Blood Pressure (mmHg)': 'Resting_Diastolic_Blood_Pressure_mmHg'
    }
    df_g = df_garmin.rename(columns=lambda x: garmin_mapping.get(x, x))
    if 'Date_YYYY_MM_DD' not in df_g.columns:
        df_g['Date_YYYY_MM_DD'] = np.nan
    df_g['Date_YYYY_MM_DD'] = pd.to_datetime(df_g['Date_YYYY_MM_DD'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    # 2. Process Garmin Activities Data
    df_activities['Date_YYYY_MM_DD'] = pd.to_datetime(df_activities['Date (YYYY-MM-DD)'], errors='coerce').dt.strftime('%Y-%m-%d')
    df_a_daily = df_activities.groupby('Date_YYYY_MM_DD').agg({
        'Activity Training Load': 'sum',
        'HR Zone 2 (min)': 'sum',
        'HR Zone 3 (min)': 'sum',
        'HR Zone 4 (min)': 'sum',
        'HR Zone 5 (min)': 'sum'
    }).reset_index()
    
    df_a_daily['Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min'] = df_a_daily['HR Zone 2 (min)'] + df_a_daily['HR Zone 3 (min)']
    df_a_daily['Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min'] = df_a_daily['HR Zone 4 (min)'] + df_a_daily['HR Zone 5 (min)']
    df_a_daily = df_a_daily.rename(columns={'Activity Training Load': 'Daily_Activity_Training_Load'})
    
    # 3. Process Withings Data
    df_withings['Date_YYYY_MM_DD'] = pd.to_datetime(df_withings['date'], format='mixed', dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
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
    
    # 4. Process Medical Data
    df_medical['Date_YYYY_MM_DD'] = pd.to_datetime(df_medical['Test Date'], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')
    df_medical['clean_test'] = df_medical['Test Name'].astype(str).str.lower().str.strip()
    
    test_map = {
        'ApoB_g_L': ['apolipoprotein b', 'apob'],
        'LDL_Cholesterol_mmol_L': ['ldl cholesterol', 'ldl', 'ldl cholesterol (calculated)'],
        'HDL_Cholesterol_mmol_L': ['hdl cholesterol', 'hdl'],
        'Triglycerides_mmol_L': ['triglycerides', 'triglyceride'],
        'HbA1c_mmol_mol': ['hba1c'],
        'hs_CRP_mg_L': ['hs-crp', 'crp high sensitivity', 'high sensitivity crp', 'hscrp', 'crp']
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

    # 5. Process Home Assistant Zone Data
    df_zones['Date_YYYY_MM_DD'] = pd.to_datetime(df_zones['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
    zone_mapping = {
        'Time in Home Zone (hours)': 'Time_in_Home_Zone_hours',
        'Time in Work Zone (hours)': 'Time_in_Work_Zone_hours'
    }
    df_z_daily = df_zones.rename(columns=zone_mapping)[['Date_YYYY_MM_DD', 'Time_in_Home_Zone_hours', 'Time_in_Work_Zone_hours']]

    # 6. Merge All Datasets
    df = pd.merge(df_g, df_a_daily[['Date_YYYY_MM_DD', 'Daily_Activity_Training_Load', 'Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min', 'Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min']], on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_w_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_m_daily, on='Date_YYYY_MM_DD', how='outer')
    df = pd.merge(df, df_z_daily, on='Date_YYYY_MM_DD', how='outer')
    
    df = df.dropna(subset=['Date_YYYY_MM_DD'])
    df = df.sort_values(by="Date_YYYY_MM_DD", ascending=True).reset_index(drop=True)
    
    df['Daily_Activity_Training_Load'] = df['Daily_Activity_Training_Load'].fillna(0)
    df['Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min'] = df['Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min'].fillna(0)
    df['Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min'] = df['Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min'].fillna(0)
    
    # 7. Derived Metrics & Formatting
    df['Date_Obj'] = pd.to_datetime(df['Date_YYYY_MM_DD'])
    df['Day_of_Week'] = df['Date_Obj'].dt.day_name()
    df['Is_Work_Day'] = df['Time_in_Work_Zone_hours'].apply(lambda x: (x > 0.5) if pd.notna(x) else "")

    if "Lactate_Threshold_Pace" in df.columns:
        df["Lactate_Threshold_Pace_decimal_min_km"] = df["Lactate_Threshold_Pace"].apply(convert_pace_to_decimal)
        
    for col in ["Sleep_Start_Time_HH_MM", "Sleep_End_Time_HH_MM"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce").dt.strftime("%H:%M")

    def time_to_decimal(time_str):
        if pd.isna(time_str): return np.nan
        try:
            h, m = map(int, str(time_str).split(':'))
            if h < 12: h += 24 
            return round(h + (m / 60.0), 2)
        except ValueError:
            return np.nan
            
    df['Sleep_Start_Decimal'] = df['Sleep_Start_Time_HH_MM'].apply(time_to_decimal)

    acute_load = df['Daily_Activity_Training_Load'].rolling(window=7, min_periods=1).sum()
    chronic_load = df['Daily_Activity_Training_Load'].rolling(window=28, min_periods=1).sum() / 4
    df['Acute_to_Chronic_Training_Load_Ratio'] = (acute_load / chronic_load).replace([np.inf, -np.inf], np.nan).round(2)

    if "Sleep_Need_min" in df.columns and "Overnight_Sleep_Duration_min" in df.columns:
        daily_sleep_deficit = df["Sleep_Need_min"] - df["Overnight_Sleep_Duration_min"]
        df["EWMA_Sleep_Debt_min"] = daily_sleep_deficit.ewm(span=7, adjust=False).mean()

    if "Daily_Running_Distance_km" in df.columns:
        df["Running_Distance_28d_Total_km"] = df["Daily_Running_Distance_km"].rolling(window=28, min_periods=1).sum().round(2)
        
    if "Overnight_Average_HRV_RMSSD_ms" in df.columns:
        hrv_7d_avg = df["Overnight_Average_HRV_RMSSD_ms"].rolling(window=7, min_periods=1).mean()
        shifted_hrv = df["Overnight_Average_HRV_RMSSD_ms"].shift(7)
        shifted_60d_mean = shifted_hrv.rolling(window=60, min_periods=30).mean()
        shifted_60d_std = shifted_hrv.rolling(window=60, min_periods=30).std()
        df["Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore"] = ((hrv_7d_avg - shifted_60d_mean) / shifted_60d_std).round(2)
    
    if "Raw_Body_Fat_Percentage" in df.columns:
        df["Body_Fat_Percentage_7d_Average"] = df["Raw_Body_Fat_Percentage"].rolling(window=7, min_periods=1).mean().round(1)
        
    if "Daily_Morning_Weight_kg" in df.columns:
        df["Daily_Morning_Weight_7d_Average_kg"] = df["Daily_Morning_Weight_kg"].rolling(window=7, min_periods=1).mean().round(2)
        
    if "Pulse_Wave_Velocity_m_s" in df.columns:
        df["Pulse_Wave_Velocity_m_s"] = df["Pulse_Wave_Velocity_m_s"].round(2)

    # 8. Filter, Re-sort Descending, and Align Output Schema
    df_export = df.tail(730).copy()
    df_export = df_export.sort_values(by="Date_YYYY_MM_DD", ascending=False).reset_index(drop=True)

    required_columns = [
        "Date_YYYY_MM_DD",
        "Day_of_Week",
        "Is_Work_Day",
        "Time_in_Home_Zone_hours",
        "Time_in_Work_Zone_hours",
        "Daily_Steps_Count",
        "Daily_Running_Distance_km",
        "Running_Distance_28d_Total_km",
        "Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min",
        "Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min",
        "Garmin_Intensity_Minutes_Lactate_Threshold_Zones_min",
        "Garmin_7d_Training_Load_Sum",
        "Acute_to_Chronic_Training_Load_Ratio",
        "Garmin_VO2_Max_ml_kg_min",
        "Lactate_Threshold_Heart_Rate_bpm",
        "Lactate_Threshold_Pace_decimal_min_km",
        "Physiological_Max_HR_bpm",
        "Overnight_Sleep_Duration_min",
        "Sleep_Start_Time_HH_MM",
        "Sleep_Start_Decimal",
        "Sleep_End_Time_HH_MM",
        "EWMA_Sleep_Debt_min",
        "Overnight_Resting_Heart_Rate_bpm",
        "Overnight_Average_HRV_RMSSD_ms",
        "Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore",
        "HRV_Status",
        "Daily_Morning_Weight_7d_Average_kg",
        "Body_Fat_Percentage_7d_Average",
        "Resting_Systolic_Blood_Pressure_mmHg",
        "Resting_Diastolic_Blood_Pressure_mmHg",
        "Pulse_Wave_Velocity_m_s",
        "ApoB_g_L",
        "LDL_Cholesterol_mmol_L",
        "HDL_Cholesterol_mmol_L",
        "Triglycerides_mmol_L",
        "HbA1c_mmol_mol",
        "hs_CRP_mg_L"
    ]

    for col in required_columns:
        if col not in df_export.columns:
            df_export[col] = np.nan

    df_export = df_export[required_columns]

    integer_columns = [
        "Daily_Steps_Count",
        "Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min",
        "Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min",
        "Garmin_Intensity_Minutes_Lactate_Threshold_Zones_min",
        "Garmin_7d_Training_Load_Sum",
        "Lactate_Threshold_Heart_Rate_bpm",
        "Physiological_Max_HR_bpm",
        "Overnight_Sleep_Duration_min",
        "EWMA_Sleep_Debt_min",
        "Overnight_Resting_Heart_Rate_bpm",
        "Overnight_Average_HRV_RMSSD_ms",
        "Resting_Systolic_Blood_Pressure_mmHg",
        "Resting_Diastolic_Blood_Pressure_mmHg"
    ]
    
    for col in integer_columns:
        if col in df_export.columns:
            df_export[col] = pd.to_numeric(df_export[col], errors='coerce').round().astype('Int64')

    column_rename_map = {
        "Date_YYYY_MM_DD": "Date (YYYY-MM-DD)",
        "Day_of_Week": "Day of Week",
        "Is_Work_Day": "Work Day (Bool)",
        "Time_in_Home_Zone_hours": "Time at Home (hours)",
        "Time_in_Work_Zone_hours": "Time at Work (hours)",
        "Daily_Steps_Count": "Step Count - Daily (steps)",
        "Daily_Running_Distance_km": "Running Distance - Daily (km)",
        "Running_Distance_28d_Total_km": "Running Distance - 28d Total (km)",
        "Time_in_HR_Zone_2_and_3_combined_percent_Lactate_Threshold_min": "HR Zone 2 & 3 Time - %LTHR (min)",
        "Time_in_HR_Zone_4_and_5_combined_percent_Lactate_Threshold_min": "HR Zone 4 & 5 Time - %LTHR (min)",
        "Garmin_Intensity_Minutes_Lactate_Threshold_Zones_min": "Intensity Minutes - %LTHR Zones (min)",
        "Garmin_7d_Training_Load_Sum": "Training Load - Garmin 7d Sum",
        "Acute_to_Chronic_Training_Load_Ratio": "Training Load Ratio - Acute:Chronic",
        "Garmin_VO2_Max_ml_kg_min": "VO2 Max - Garmin (ml/kg/min)",
        "Lactate_Threshold_Heart_Rate_bpm": "Lactate Threshold HR (bpm)",
        "Lactate_Threshold_Pace_decimal_min_km": "Lactate Threshold Pace (decimal min/km)",
        "Physiological_Max_HR_bpm": "Max Heart Rate - Physiological (bpm)",
        "Overnight_Sleep_Duration_min": "Sleep Duration - Overnight (min)",
        "Sleep_Start_Time_HH_MM": "Sleep Start Time (HH:MM)",
        "Sleep_Start_Decimal": "Sleep Start Time (Decimal)",
        "Sleep_End_Time_HH_MM": "Sleep End Time (HH:MM)",
        "EWMA_Sleep_Debt_min": "Sleep Debt - 7d EWMA (min)",
        "Overnight_Resting_Heart_Rate_bpm": "Resting Heart Rate - Overnight (bpm)",
        "Overnight_Average_HRV_RMSSD_ms": "HRV RMSSD - Overnight (ms)",
        "Overnight_Average_HRV_RMSSD_7d_Average_vs_Previous_60d_Baseline_ZScore": "HRV RMSSD Z-Score - 7d Avg vs 60d Baseline",
        "HRV_Status": "HRV Status",
        "Daily_Morning_Weight_7d_Average_kg": "Weight - Morning 7d Avg (kg)",
        "Body_Fat_Percentage_7d_Average": "Body Fat - 7d Avg (%)",
        "Resting_Systolic_Blood_Pressure_mmHg": "Blood Pressure Systolic - Resting (mmHg)",
        "Resting_Diastolic_Blood_Pressure_mmHg": "Blood Pressure Diastolic - Resting (mmHg)",
        "Pulse_Wave_Velocity_m_s": "Pulse Wave Velocity (m/s)",
        "ApoB_g_L": "ApoB (g/L)",
        "LDL_Cholesterol_mmol_L": "LDL Cholesterol (mmol/L)",
        "HDL_Cholesterol_mmol_L": "HDL Cholesterol (mmol/L)",
        "Triglycerides_mmol_L": "Triglycerides (mmol/L)",
        "HbA1c_mmol_mol": "HbA1c (mmol/mol)",
        "hs_CRP_mg_L": "hs-CRP (mg/L)"
    }
    
    df_export = df_export.rename(columns=column_rename_map)
    df_export["Work Day (Bool)"] = df_export["Work Day (Bool)"].fillna("")

    # 9. Demographic Header Injection & Export
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
    ACTIVITIES_FILENAME = "drw_garmin_activities_list.csv"
    WITHINGS_FILENAME = "drw_withings_bodyscan_data.csv"
    MEDICAL_FILENAME = "Daniel's Medical Test Results.csv"
    ZONES_URL = "https://dfexhoblv7ytpsxp7uiasfchbdxbl8vt.ui.nabu.casa/local/drw_home_assistant_zone_history.csv?v=1"
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
    activities_file_id = get_file_id(drive_service, ACTIVITIES_FILENAME, FOLDER_ID)
    withings_file_id = get_file_id(drive_service, WITHINGS_FILENAME, FOLDER_ID)
    medical_file_id = get_file_id(drive_service, MEDICAL_FILENAME, FOLDER_ID)
    target_file_id = get_file_id(drive_service, TARGET_FILENAME, FOLDER_ID)
    
    if not garmin_file_id:
        raise FileNotFoundError(f"Could not find '{GARMIN_FILENAME}' in Drive folder.")
    if not activities_file_id:
        raise FileNotFoundError(f"Could not find '{ACTIVITIES_FILENAME}' in Drive folder.")
    if not withings_file_id:
        raise FileNotFoundError(f"Could not find '{WITHINGS_FILENAME}' in Drive folder.")
    if not medical_file_id:
        raise FileNotFoundError(f"Could not find '{MEDICAL_FILENAME}' in Drive folder.")

    print("Downloading raw data from Google Drive and Home Assistant URL...")
    garmin_data = download_drive_file(drive_service, garmin_file_id)
    activities_data = download_drive_file(drive_service, activities_file_id)
    withings_data = download_drive_file(drive_service, withings_file_id)
    medical_data = download_drive_file(drive_service, medical_file_id)
    
    df_garmin_raw = pd.read_csv(garmin_data)
    df_activities_raw = pd.read_csv(activities_data)
    df_withings_raw = pd.read_csv(withings_data)
    df_medical_raw = pd.read_csv(medical_data)
    df_zones_raw = pd.read_csv(ZONES_URL)
    
    print("Processing physiological metrics...")
    generate_quantified_self_csv(df_garmin_raw, df_withings_raw, df_medical_raw, df_activities_raw, df_zones_raw, output_path=TARGET_FILENAME)
    
    print("Uploading updated CSV to Google Drive...")
    media = MediaFileUpload(TARGET_FILENAME, mimetype='text/csv', resumable=True)
    
    if target_file_id:
        drive_service.files().update(fileId=target_file_id, media_body=media).execute()
    else:
        file_metadata = {'name': TARGET_FILENAME, 'parents': [FOLDER_ID]}
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        
    print("Export and upload complete.")
