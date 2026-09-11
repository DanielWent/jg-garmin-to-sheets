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
    output_path: str = 'aflw_quantified_self.csv',
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

    # Average Awake Hours Garmin Stress Score (Column BD / 55)
    if 'Garmin_Avg_Awake_Stress_Score' not in df_g.columns and df_garmin.shape[1] > 55:
        df_g['Garmin_Avg_Awake_Stress_Score'] = pd.to_numeric(
            df_garmin.iloc[:, 55], errors='coerce'
        )

    # Daily Max Garmin Body Battery (Column V / 21)
    if (
        'Daily_Max_Garmin_Body_Battery' not in df_g.columns
        and df_garmin.shape[1] > 21
    ):
        df_g['Daily_Max_Garmin_Body_Battery'] = pd.to_numeric(
            df_garmin.iloc[:, 21], errors='coerce'
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
    df_a_daily = (
        df_activities.groupby('Date_YYYY_MM_DD')
        .agg({'Activity Training Load': 'sum'})
        .reset_index()
    )
    df_a_daily = df_a_daily.rename(
        columns={'Activity Training Load': 'Daily_Activity_Training_Load'}
    )

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
    body_fat_col = (
        'Body Fat (%)'
        if 'Body Fat (%)' in df_withings.columns
        else df_withings.columns[2]
    )
    pwv_col = (
        'Pulse Wave Velocity (m/s)'
        if 'Pulse Wave Velocity (m/s)' in df_withings.columns
        else df_withings.columns[3]
    )

    df_w_daily = (
        df_withings.groupby('Date_YYYY_MM_DD')
        .agg({weight_col: 'mean', body_fat_col: 'mean', pwv_col: 'mean'})
        .reset_index()
    )

    withings_mapping = {
        weight_col: 'Daily_Morning_Weight_kg',
        body_fat_col: 'Raw_Body_Fat_Percentage',
        pwv_col: 'Pulse_Wave_Velocity_m_s',
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
    df = pd.merge(
        df_g,
        df_a_daily[['Date_YYYY_MM_DD', 'Daily_Activity_Training_Load']],
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

    # 7. Derived Metrics & Precision
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

    acute_load = (
        df['Daily_Activity_Training_Load'].rolling(window=7, min_periods=1).sum()
    )
    chronic_load = (
        df['Daily_Activity_Training_Load'].rolling(window=28, min_periods=1).sum()
        / 4
    )
    df['Acute_to_Chronic_Training_Load_Ratio'] = (
        (acute_load / chronic_load).replace([np.inf, -np.inf], np.nan).round(2)
    )

    if (
        'Sleep_Need_min' in df.columns
        and 'Overnight_Sleep_Duration_min' in df.columns
    ):
        daily_sleep_deficit = (
            df['Sleep_Need_min'] - df['Overnight_Sleep_Duration_min']
        )
        df['EWMA_Sleep_Debt_min'] = daily_sleep_deficit.ewm(
            halflife=4, adjust=False
        ).mean()

    if 'Daily_Running_Distance_km' in df.columns:
        df['Running_Distance_28d_Total_km'] = (
            df['Daily_Running_Distance_km']
            .rolling(window=28, min_periods=1)
            .sum()
            .round(2)
        )

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

    if 'Raw_Body_Fat_Percentage' in df.columns:
        df['Body_Fat_Percentage_7d_Average'] = (
            df['Raw_Body_Fat_Percentage']
            .rolling(window=7, min_periods=1)
            .mean()
            .round(1)
        )

    if 'Daily_Morning_Weight_kg' in df.columns:
        df['Daily_Morning_Weight_7d_Average_kg'] = (
            df['Daily_Morning_Weight_kg']
            .rolling(window=7, min_periods=1)
            .mean()
            .round(2)
        )

    if 'Active_Calories' in df.columns and 'Daily_Morning_Weight_kg' in df.columns:
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
        )
        df['Net_Active_MET_Minutes'] = (
            pd.to_numeric(df['Active_Calories'], errors='coerce') / effective_weight
        ) * 60.0

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
        'Running_Distance_28d_Total_km',
        'Garmin_Moderate_Intensity_Minutes',
        'Garmin_Vigorous_Intensity_Minutes',
        'Garmin_Avg_Awake_Stress_Score',
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
        'Daily_Max_Garmin_Body_Battery',
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
        'Running_Distance_28d_Total_km': 'Running Distance - 28d Total (km)',
        'Garmin_Moderate_Intensity_Minutes': (
            'Moderate Intensity Minutes - Garmin (min)'
        ),
        'Garmin_Vigorous_Intensity_Minutes': (
            'Vigorous Intensity Minutes - Garmin (min)'
        ),
        'Garmin_Avg_Awake_Stress_Score': 'Average Awake Hours Garmin Stress Score (0-100)',
        'Net_Active_MET_Minutes': 'Net Active MET Minutes',
        'Garmin_7d_Training_Load_Sum': 'Training Load - Garmin 7d Sum',
        'Acute_to_Chronic_Training_Load_Ratio': (
            'Training Load Ratio - Acute:Chronic'
        ),
        'Garmin_VO2_Max_ml_kg_min': 'VO2 Max - Garmin (ml/kg/min)',
        'Lactate_Threshold_Heart_Rate_bpm': 'Lactate Threshold HR (bpm)',
        'Lactate_Threshold_Pace_decimal_min_km': (
            'LactThe error occurs because Pandas is attempting to aggregate a column (`'Pulse dynamics Velocity (m/s)'`, assigned to `pwv_col`) that is not present in the DataFrame columns when `groupby().agg(...)` is called at line 183.

This typically happens if the raw export has a slightly different header name (for example, a typo for `'Pulse Wave Velocity (m/s)'`) or if PWV data was omitted entirely from that dataset.

Here are the two cleanest ways to fix it in `src/aflw_quantified_self_exporter.py`:

**Option 1: Filter the aggregation dictionary dynamically (Recommended)**

Build the aggregation mapping dynamically so it only aggregates columns that actually exist in the DataFrame:

```python
# Build agg dict only for columns present in the DataFrame
cols_to_agg = [weight_col, body_fat_col, pwv_col]
agg_dict = {col: 'mean' for col in cols_to_agg if col and col in df.columns}

# Perform aggregation
df_daily = df.groupby('Date').agg(agg_dict).reset_index()
