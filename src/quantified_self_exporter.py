```python
import pandas as pd
import numpy as np

def get_col_letter(idx):
    result = ""
    idx += 1
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

def analyze_file(filename):
    try:
        df = pd.read_csv(filename)
        cols = []
        for i, col in enumerate(df.columns):
            sample = df[col].dropna()
            
            # Format detection
            if sample.empty:
                fmt = "Empty"
            else:
                val = sample.iloc[0]
                if isinstance(val, str):
                    if ":" in val and len(val.split(":")) >= 2 and any(char.isdigit() for char in val):
                        fmt = "HH:MM or HH:MM:SS"
                    elif "-" in val and len(val) >= 8 and val[:4].isdigit():
                        fmt = "YYYY-MM-DD"
                    elif "/" in val and ":" in val and len(val) >= 14:
                        fmt = "DD/MM/YYYY HH:MM"
                    else:
                        fmt = "String"
                elif isinstance(val, bool):
                    fmt = "Boolean"
                elif isinstance(val, int) or np.issubdtype(sample.dtype, np.integer):
                    fmt = "Integer"
                elif isinstance(val, float) or np.issubdtype(sample.dtype, np.floating):
                    if all(x.is_integer() for x in sample if pd.notnull(x)):
                        fmt = "Integer (stored as float)"
                    else:
                        fmt = "Decimal"
                else:
                    fmt = str(type(val))
            
            # Unit extraction attempt from column name, else "None"
            unit = "None"
            if "(min)" in col or "(min/km)" in col:
                unit = "Minutes" if "(min)" in col else "min/km"
            elif "(km)" in col: unit = "km"
            elif "(bpm)" in col: unit = "bpm"
            elif "(kcal)" in col: unit = "kcal"
            elif "(ml/kg/min)" in col: unit = "ml/kg/min"
            elif "(0-100)" in col: unit = "Score (0-100)"
            elif "(mmHg)" in col: unit = "mmHg"
            elif "(ms)" in col: unit = "ms"
            elif "(kg)" in col: unit = "kg"
            elif "(%)" in col: unit = "%"
            elif "(m/s)" in col: unit = "m/s"
            elif "(years)" in col: unit = "Years"
            elif "(HH:MM)" in col: unit = "HH:MM"
            elif "(m)" in col and "(ms)" not in col and "(min/km)" not in col and "(m/s)" not in col: unit = "m"
            elif "(Celsius)" in col: unit = "°C"
            elif "(km/h)" in col: unit = "km/h"
            elif "(cm)" in col: unit = "cm"
            elif "(0.0-5.0)" in col: unit = "0.0-5.0"
            elif "(Watts)" in col: unit = "Watts"
            elif "(ml)" in col and "ml/kg/min" not in col: unit = "ml"
            elif "Duration" in col: unit = "Minutes" # Fallbacks
            elif "Time" in col and "Start" not in col and "End" not in col and "Date" not in col: unit = "HH:MM:SS"
            elif "Pace" in col: unit = "min/km"
            elif "Speed" in col: unit = "km/h"
            elif "Ascent" in col or "Descent" in col or "Distance" in col or "Elevation" in col: unit = "m" if "Ascent" in col or "Descent" in col else "km"
            elif "HR " in col or "HR" == col: unit = "bpm"
            elif "Steps" in col: unit = "Steps"
            elif "Floors" in col: unit = "Floors"
            elif "Calories" in col: unit = "kcal"
            elif "Age" in col and "Adjusted" not in col: unit = "Years"
            
            cols.append({
                "name": col, # Exact header
                "col": f"Column {get_col_letter(i)}",
                "unit": unit,
                "fmt": fmt
            })
        return cols
    except Exception as e:
        return str(e)

files = ["drw_garmin_data.csv", "drw_withings_bodyscan_data.csv", "drw_garmin_activities_list.csv"]
results = {f: analyze_file(f) for f in files}
print(results)


```

```text
{'drw_garmin_data.csv': [{'name': 'Date (YYYY-MM-DD)', 'col': 'Column A', 'unit': 'None', 'fmt': 'YYYY-MM-DD'}, {'name': 'User Name', 'col': 'Column B', 'unit': 'None', 'fmt': 'String'}, {'name': 'User Age', 'col': 'Column C', 'unit': 'Years', 'fmt': 'Decimal'}, {'name': 'User Gender', 'col': 'Column D', 'unit': 'None', 'fmt': 'String'}, {'name': 'Physiological Maximum Heart Rate (bpm)', 'col': 'Column E', 'unit': 'bpm', 'fmt': 'Integer'}, {'name': 'VO2 Max (ml/kg/min)', 'col': 'Column F', 'unit': 'ml/kg/min', 'fmt': 'Decimal'}, {'name': 'VO2 Max Percentile (Age-Gender Adjusted)', 'col': 'Column G', 'unit': 'None', 'fmt': 'Decimal'}, {'name': 'Lactate Threshold Pace (min/km)', 'col': 'Column H', 'unit': 'min/km', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Lactate Threshold Heart Rate (bpm)', 'col': 'Column I', 'unit': 'bpm', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin Sleep Score (0-100)', 'col': 'Column J', 'unit': 'Score (0-100)', 'fmt': 'Integer (stored as float)'}, {'name': 'Sleep Start Time', 'col': 'Column K', 'unit': 'None', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Sleep End Time', 'col': 'Column L', 'unit': 'None', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Deep Sleep (min)', 'col': 'Column M', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'Light Sleep (min)', 'col': 'Column N', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'REM Sleep (min)', 'col': 'Column O', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'Awake Time (min)', 'col': 'Column P', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'Sleep Length (min)', 'col': 'Column Q', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'Sleep Need (min)', 'col': 'Column R', 'unit': 'Minutes', 'fmt': 'Integer (stored as float)'}, {'name': 'Overnight Average Pulse Ox / SpO2 (%)', 'col': 'Column S', 'unit': '%', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin Average Stress Score (0-100)', 'col': 'Column T', 'unit': 'Score (0-100)', 'fmt': 'String'}, {'name': 'Daily Min Body Battery (0-100)', 'col': 'Column U', 'unit': 'Score (0-100)', 'fmt': 'String'}, {'name': 'Daily Max Body Battery (0-100)', 'col': 'Column V', 'unit': 'Score (0-100)', 'fmt': 'String'}, {'name': 'Body Battery Charged (0-100)', 'col': 'Column W', 'unit': 'Score (0-100)', 'fmt': 'String'}, {'name': 'Body Battery Drained (0-100)', 'col': 'Column X', 'unit': 'Score (0-100)', 'fmt': 'String'}, {'name': 'Daily Steps', 'col': 'Column Y', 'unit': 'Steps', 'fmt': 'String'}, {'name': 'Daily Floors Climbed', 'col': 'Column Z', 'unit': 'Floors', 'fmt': 'String'}, {'name': 'Daily Intensity Minutes', 'col': 'Column AA', 'unit': 'None', 'fmt': 'String'}, {'name': 'Total Calories (kcal)', 'col': 'Column AB', 'unit': 'kcal', 'fmt': 'String'}, {'name': 'Systolic Blood Pressure (mmHg)', 'col': 'Column AC', 'unit': 'mmHg', 'fmt': 'Integer (stored as float)'}, {'name': 'Diastolic Blood Pressure (mmHg)', 'col': 'Column AD', 'unit': 'mmHg', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin Training Load (7 Day Sum)', 'col': 'Column AE', 'unit': 'None', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin Training Load Focus', 'col': 'Column AF', 'unit': 'None', 'fmt': 'String'}, {'name': 'Morning Garmin Training Readiness (0-100)', 'col': 'Column AG', 'unit': 'Score (0-100)', 'fmt': 'Integer (stored as float)'}, {'name': 'Overnight Resting HR (bpm)', 'col': 'Column AH', 'unit': 'bpm', 'fmt': 'Integer (stored as float)'}, {'name': 'Overnight HRV (ms)', 'col': 'Column AI', 'unit': 'ms', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin HRV Status (Text Label)', 'col': 'Column AJ', 'unit': 'None', 'fmt': 'String'}, {'name': 'Garmin Training Status (Text Label)', 'col': 'Column AK', 'unit': 'None', 'fmt': 'String'}, {'name': 'Total Walking Distance (km)', 'col': 'Column AL', 'unit': 'km', 'fmt': 'Decimal'}, {'name': 'Total Walking Duration (min)', 'col': 'Column AM', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Total Running Activities Count', 'col': 'Column AN', 'unit': 'None', 'fmt': 'Integer'}, {'name': 'Total Running Distance (km)', 'col': 'Column AO', 'unit': 'km', 'fmt': 'Decimal'}, {'name': 'Total Running Duration (min)', 'col': 'Column AP', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Total Strength Training Duration (min)', 'col': 'Column AQ', 'unit': 'Minutes', 'fmt': 'Decimal'}], 'drw_withings_bodyscan_data.csv': [{'name': 'date', 'col': 'Column A', 'unit': 'None', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Weight (kg)', 'col': 'Column B', 'unit': 'kg', 'fmt': 'Decimal'}, {'name': 'BMI', 'col': 'Column C', 'unit': 'None', 'fmt': 'Decimal'}, {'name': 'Body Fat (%)', 'col': 'Column D', 'unit': '%', 'fmt': 'Decimal'}, {'name': 'Visceral Fat Rating', 'col': 'Column E', 'unit': 'None', 'fmt': 'Decimal'}, {'name': 'Pulse Wave Velocity (m/s)', 'col': 'Column F', 'unit': 'm/s', 'fmt': 'Decimal'}, {'name': 'AFib Status', 'col': 'Column G', 'unit': 'None', 'fmt': 'String'}, {'name': 'Vascular Age (years)', 'col': 'Column H', 'unit': 'Years', 'fmt': 'Decimal'}, {'name': 'Nerve Health Score', 'col': 'Column I', 'unit': 'None', 'fmt': 'Decimal'}], 'drw_garmin_activities_list.csv': [{'name': 'Activity ID', 'col': 'Column A', 'unit': 'None', 'fmt': 'Integer (stored as float)'}, {'name': 'Date (YYYY-MM-DD)', 'col': 'Column B', 'unit': 'None', 'fmt': 'YYYY-MM-DD'}, {'name': 'Start Time (HH:MM)', 'col': 'Column C', 'unit': 'HH:MM', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Activity Type', 'col': 'Column D', 'unit': 'None', 'fmt': 'String'}, {'name': 'Activity Name', 'col': 'Column E', 'unit': 'None', 'fmt': 'String'}, {'name': 'Distance (km)', 'col': 'Column F', 'unit': 'km', 'fmt': 'Decimal'}, {'name': 'Duration (min)', 'col': 'Column G', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Avg Pace (min/km)', 'col': 'Column H', 'unit': 'min/km', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Average Grade Adjusted Pace (min/km)', 'col': 'Column I', 'unit': 'min/km', 'fmt': 'HH:MM or HH:MM:SS'}, {'name': 'Total Ascent (m)', 'col': 'Column J', 'unit': 'm', 'fmt': 'Integer (stored as float)'}, {'name': 'Total Descent (m)', 'col': 'Column K', 'unit': 'm', 'fmt': 'Integer (stored as float)'}, {'name': 'Feels Like Temperature (Celsius)', 'col': 'Column L', 'unit': '°C', 'fmt': 'Decimal'}, {'name': 'Weather Condition', 'col': 'Column M', 'unit': 'None', 'fmt': 'String'}, {'name': 'Sustained Wind Speed (km/h)', 'col': 'Column N', 'unit': 'km/h', 'fmt': 'Integer (stored as float)'}, {'name': 'Avg HR (bpm)', 'col': 'Column O', 'unit': 'bpm', 'fmt': 'Integer (stored as float)'}, {'name': 'Max HR (bpm)', 'col': 'Column P', 'unit': 'bpm', 'fmt': 'Integer (stored as float)'}, {'name': 'Average Cadence (spm)', 'col': 'Column Q', 'unit': 'None', 'fmt': 'Integer (stored as float)'}, {'name': 'Average Stride Length (m)', 'col': 'Column R', 'unit': 'm', 'fmt': 'Decimal'}, {'name': 'Average Ground Contact Time (ms)', 'col': 'Column S', 'unit': 'ms', 'fmt': 'Integer (stored as float)'}, {'name': 'Vertical Oscillation (cm)', 'col': 'Column T', 'unit': 'cm', 'fmt': 'Decimal'}, {'name': 'Aerobic Training Effect (0.0-5.0)', 'col': 'Column U', 'unit': '0.0-5.0', 'fmt': 'Decimal'}, {'name': 'Anaerobic Training Effect (0.0-5.0)', 'col': 'Column V', 'unit': '0.0-5.0', 'fmt': 'Decimal'}, {'name': 'Activity Training Load', 'col': 'Column W', 'unit': 'None', 'fmt': 'Decimal'}, {'name': 'Avg Power (Watts)', 'col': 'Column X', 'unit': 'Watts', 'fmt': 'Integer (stored as float)'}, {'name': 'Max Power (Watts)', 'col': 'Column Y', 'unit': 'Watts', 'fmt': 'Integer (stored as float)'}, {'name': 'Normalized Power (Watts)', 'col': 'Column Z', 'unit': 'Watts', 'fmt': 'Integer (stored as float)'}, {'name': 'Estimated Sweat Loss (ml)', 'col': 'Column AA', 'unit': 'ml', 'fmt': 'Integer (stored as float)'}, {'name': 'Garmin Training Effect Label', 'col': 'Column AB', 'unit': 'None', 'fmt': 'String'}, {'name': 'HR Zone 1 (min)', 'col': 'Column AC', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'HR Zone 2 (min)', 'col': 'Column AD', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'HR Zone 3 (min)', 'col': 'Column AE', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'HR Zone 4 (min)', 'col': 'Column AF', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'HR Zone 5 (min)', 'col': 'Column AG', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Power Zone 1 (min)', 'col': 'Column AH', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Power Zone 2 (min)', 'col': 'Column AI', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Power Zone 3 (min)', 'col': 'Column AJ', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Power Zone 4 (min)', 'col': 'Column AK', 'unit': 'Minutes', 'fmt': 'Decimal'}, {'name': 'Power Zone 5 (min)', 'col': 'Column AL', 'unit': 'Minutes', 'fmt': 'Decimal'}]}


```

```python
out = "```python\n"

out += "# --------------------------------------------------\n"
out += "# FILE: drw_garmin_data.csv\n"
out += "# NOTE: Contains daily aggregated physiological, sleep, and activity metrics recorded by Garmin.\n"
out += "# STRUCTURE: One row per day.\n"
out += "# --------------------------------------------------\n"
out += "# | Metric Name | Column | Unit | Format |\n"
out += "# | :--- | :--- | :--- | :--- |\n"
for m in results['drw_garmin_data.csv']:
    fmt = "Integer" if "Integer" in m['fmt'] else m['fmt']
    out += f"# | {m['name']} | {m['col']} | Unit: {m['unit']} | {fmt} |\n"

out += "#\n# --------------------------------------------------\n"
out += "# FILE: drw_withings_bodyscan_data.csv\n"
out += "# NOTE: Contains body composition, cardiovascular, and nerve health measurements from a Withings scale.\n"
out += "# STRUCTURE: One row per recorded scan/weigh-in event.\n"
out += "# --------------------------------------------------\n"
out += "# | Metric Name | Column | Unit | Format |\n"
out += "# | :--- | :--- | :--- | :--- |\n"
for m in results['drw_withings_bodyscan_data.csv']:
    fmt = "Integer" if "Integer" in m['fmt'] else m['fmt']
    fmt = "DD/MM/YYYY HH:MM" if m['name'] == 'date' else fmt
    out += f"# | {m['name']} | {m['col']} | Unit: {m['unit']} | {fmt} |\n"

out += "#\n# --------------------------------------------------\n"
out += "# FILE: drw_garmin_activities_list.csv\n"
out += "# NOTE: Contains detailed statistics for individual recorded workouts and activities.\n"
out += "# STRUCTURE: One row per tracked activity.\n"
out += "# --------------------------------------------------\n"
out += "# | Metric Name | Column | Unit | Format |\n"
out += "# | :--- | :--- | :--- | :--- |\n"
for m in results['drw_garmin_activities_list.csv']:
    fmt = "Integer" if "Integer" in m['fmt'] else m['fmt']
    out += f"# | {m['name']} | {m['col']} | Unit: {m['unit']} | {fmt} |\n"

out += "```"
print(out)


```

```text
```python
# --------------------------------------------------
# FILE: drw_garmin_data.csv
# NOTE: Contains daily aggregated physiological, sleep, and activity metrics recorded by Garmin.
# STRUCTURE: One row per day.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | Date (YYYY-MM-DD) | Column A | Unit: None | YYYY-MM-DD |
# | User Name | Column B | Unit: None | String |
# | User Age | Column C | Unit: Years | Decimal |
# | User Gender | Column D | Unit: None | String |
# | Physiological Maximum Heart Rate (bpm) | Column E | Unit: bpm | Integer |
# | VO2 Max (ml/kg/min) | Column F | Unit: ml/kg/min | Decimal |
# | VO2 Max Percentile (Age-Gender Adjusted) | Column G | Unit: None | Decimal |
# | Lactate Threshold Pace (min/km) | Column H | Unit: min/km | HH:MM or HH:MM:SS |
# | Lactate Threshold Heart Rate (bpm) | Column I | Unit: bpm | Integer |
# | Garmin Sleep Score (0-100) | Column J | Unit: Score (0-100) | Integer |
# | Sleep Start Time | Column K | Unit: None | HH:MM or HH:MM:SS |
# | Sleep End Time | Column L | Unit: None | HH:MM or HH:MM:SS |
# | Deep Sleep (min) | Column M | Unit: Minutes | Integer |
# | Light Sleep (min) | Column N | Unit: Minutes | Integer |
# | REM Sleep (min) | Column O | Unit: Minutes | Integer |
# | Awake Time (min) | Column P | Unit: Minutes | Integer |
# | Sleep Length (min) | Column Q | Unit: Minutes | Integer |
# | Sleep Need (min) | Column R | Unit: Minutes | Integer |
# | Overnight Average Pulse Ox / SpO2 (%) | Column S | Unit: % | Integer |
# | Garmin Average Stress Score (0-100) | Column T | Unit: Score (0-100) | String |
# | Daily Min Body Battery (0-100) | Column U | Unit: Score (0-100) | String |
# | Daily Max Body Battery (0-100) | Column V | Unit: Score (0-100) | String |
# | Body Battery Charged (0-100) | Column W | Unit: Score (0-100) | String |
# | Body Battery Drained (0-100) | Column X | Unit: Score (0-100) | String |
# | Daily Steps | Column Y | Unit: Steps | String |
# | Daily Floors Climbed | Column Z | Unit: Floors | String |
# | Daily Intensity Minutes | Column AA | Unit: None | String |
# | Total Calories (kcal) | Column AB | Unit: kcal | String |
# | Systolic Blood Pressure (mmHg) | Column AC | Unit: mmHg | Integer |
# | Diastolic Blood Pressure (mmHg) | Column AD | Unit: mmHg | Integer |
# | Garmin Training Load (7 Day Sum) | Column AE | Unit: None | Integer |
# | Garmin Training Load Focus | Column AF | Unit: None | String |
# | Morning Garmin Training Readiness (0-100) | Column AG | Unit: Score (0-100) | Integer |
# | Overnight Resting HR (bpm) | Column AH | Unit: bpm | Integer |
# | Overnight HRV (ms) | Column AI | Unit: ms | Integer |
# | Garmin HRV Status (Text Label) | Column AJ | Unit: None | String |
# | Garmin Training Status (Text Label) | Column AK | Unit: None | String |
# | Total Walking Distance (km) | Column AL | Unit: km | Decimal |
# | Total Walking Duration (min) | Column AM | Unit: Minutes | Decimal |
# | Total Running Activities Count | Column AN | Unit: None | Integer |
# | Total Running Distance (km) | Column AO | Unit: km | Decimal |
# | Total Running Duration (min) | Column AP | Unit: Minutes | Decimal |
# | Total Strength Training Duration (min) | Column AQ | Unit: Minutes | Decimal |
#
# --------------------------------------------------
# FILE: drw_withings_bodyscan_data.csv
# NOTE: Contains body composition, cardiovascular, and nerve health measurements from a Withings scale.
# STRUCTURE: One row per recorded scan/weigh-in event.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | date | Column A | Unit: None | DD/MM/YYYY HH:MM |
# | Weight (kg) | Column B | Unit: kg | Decimal |
# | BMI | Column C | Unit: None | Decimal |
# | Body Fat (%) | Column D | Unit: % | Decimal |
# | Visceral Fat Rating | Column E | Unit: None | Decimal |
# | Pulse Wave Velocity (m/s) | Column F | Unit: m/s | Decimal |
# | AFib Status | Column G | Unit: None | String |
# | Vascular Age (years) | Column H | Unit: Years | Decimal |
# | Nerve Health Score | Column I | Unit: None | Decimal |
#
# --------------------------------------------------
# FILE: drw_garmin_activities_list.csv
# NOTE: Contains detailed statistics for individual recorded workouts and activities.
# STRUCTURE: One row per tracked activity.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | Activity ID | Column A | Unit: None | Integer |
# | Date (YYYY-MM-DD) | Column B | Unit: None | YYYY-MM-DD |
# | Start Time (HH:MM) | Column C | Unit: HH:MM | HH:MM or HH:MM:SS |
# | Activity Type | Column D | Unit: None | String |
# | Activity Name | Column E | Unit: None | String |
# | Distance (km) | Column F | Unit: km | Decimal |
# | Duration (min) | Column G | Unit: Minutes | Decimal |
# | Avg Pace (min/km) | Column H | Unit: min/km | HH:MM or HH:MM:SS |
# | Average Grade Adjusted Pace (min/km) | Column I | Unit: min/km | HH:MM or HH:MM:SS |
# | Total Ascent (m) | Column J | Unit: m | Integer |
# | Total Descent (m) | Column K | Unit: m | Integer |
# | Feels Like Temperature (Celsius) | Column L | Unit: °C | Decimal |
# | Weather Condition | Column M | Unit: None | String |
# | Sustained Wind Speed (km/h) | Column N | Unit: km/h | Integer |
# | Avg HR (bpm) | Column O | Unit: bpm | Integer |
# | Max HR (bpm) | Column P | Unit: bpm | Integer |
# | Average Cadence (spm) | Column Q | Unit: None | Integer |
# | Average Stride Length (m) | Column R | Unit: m | Decimal |
# | Average Ground Contact Time (ms) | Column S | Unit: ms | Integer |
# | Vertical Oscillation (cm) | Column T | Unit: cm | Decimal |
# | Aerobic Training Effect (0.0-5.0) | Column U | Unit: 0.0-5.0 | Decimal |
# | Anaerobic Training Effect (0.0-5.0) | Column V | Unit: 0.0-5.0 | Decimal |
# | Activity Training Load | Column W | Unit: None | Decimal |
# | Avg Power (Watts) | Column X | Unit: Watts | Integer |
# | Max Power (Watts) | Column Y | Unit: Watts | Integer |
# | Normalized Power (Watts) | Column Z | Unit: Watts | Integer |
# | Estimated Sweat Loss (ml) | Column AA | Unit: ml | Integer |
# | Garmin Training Effect Label | Column AB | Unit: None | String |
# | HR Zone 1 (min) | Column AC | Unit: Minutes | Decimal |
# | HR Zone 2 (min) | Column AD | Unit: Minutes | Decimal |
# | HR Zone 3 (min) | Column AE | Unit: Minutes | Decimal |
# | HR Zone 4 (min) | Column AF | Unit: Minutes | Decimal |
# | HR Zone 5 (min) | Column AG | Unit: Minutes | Decimal |
# | Power Zone 1 (min) | Column AH | Unit: Minutes | Decimal |
# | Power Zone 2 (min) | Column AI | Unit: Minutes | Decimal |
# | Power Zone 3 (min) | Column AJ | Unit: Minutes | Decimal |
# | Power Zone 4 (min) | Column AK | Unit: Minutes | Decimal |
# | Power Zone 5 (min) | Column AL | Unit: Minutes | Decimal |

```

```

```python
# --------------------------------------------------
# FILE: drw_garmin_data.csv
# NOTE: Contains daily aggregated physiological, sleep, and activity metrics recorded by Garmin.
# STRUCTURE: One row per day.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | Date (YYYY-MM-DD) | Column A | Unit: None | YYYY-MM-DD |
# | User Name | Column B | Unit: None | String |
# | User Age | Column C | Unit: Years | Decimal |
# | User Gender | Column D | Unit: None | String |
# | Physiological Maximum Heart Rate (bpm) | Column E | Unit: bpm | Integer |
# | VO2 Max (ml/kg/min) | Column F | Unit: ml/kg/min | Decimal |
# | VO2 Max Percentile (Age-Gender Adjusted) | Column G | Unit: None | Decimal |
# | Lactate Threshold Pace (min/km) | Column H | Unit: min/km | HH:MM or HH:MM:SS |
# | Lactate Threshold Heart Rate (bpm) | Column I | Unit: bpm | Integer |
# | Garmin Sleep Score (0-100) | Column J | Unit: Score (0-100) | Integer |
# | Sleep Start Time | Column K | Unit: None | HH:MM or HH:MM:SS |
# | Sleep End Time | Column L | Unit: None | HH:MM or HH:MM:SS |
# | Deep Sleep (min) | Column M | Unit: Minutes | Integer |
# | Light Sleep (min) | Column N | Unit: Minutes | Integer |
# | REM Sleep (min) | Column O | Unit: Minutes | Integer |
# | Awake Time (min) | Column P | Unit: Minutes | Integer |
# | Sleep Length (min) | Column Q | Unit: Minutes | Integer |
# | Sleep Need (min) | Column R | Unit: Minutes | Integer |
# | Overnight Average Pulse Ox / SpO2 (%) | Column S | Unit: % | Integer |
# | Garmin Average Stress Score (0-100) | Column T | Unit: Score (0-100) | String |
# | Daily Min Body Battery (0-100) | Column U | Unit: Score (0-100) | String |
# | Daily Max Body Battery (0-100) | Column V | Unit: Score (0-100) | String |
# | Body Battery Charged (0-100) | Column W | Unit: Score (0-100) | String |
# | Body Battery Drained (0-100) | Column X | Unit: Score (0-100) | String |
# | Daily Steps | Column Y | Unit: Steps | String |
# | Daily Floors Climbed | Column Z | Unit: Floors | String |
# | Daily Intensity Minutes | Column AA | Unit: None | String |
# | Total Calories (kcal) | Column AB | Unit: kcal | String |
# | Systolic Blood Pressure (mmHg) | Column AC | Unit: mmHg | Integer |
# | Diastolic Blood Pressure (mmHg) | Column AD | Unit: mmHg | Integer |
# | Garmin Training Load (7 Day Sum) | Column AE | Unit: None | Integer |
# | Garmin Training Load Focus | Column AF | Unit: None | String |
# | Morning Garmin Training Readiness (0-100) | Column AG | Unit: Score (0-100) | Integer |
# | Overnight Resting HR (bpm) | Column AH | Unit: bpm | Integer |
# | Overnight HRV (ms) | Column AI | Unit: ms | Integer |
# | Garmin HRV Status (Text Label) | Column AJ | Unit: None | String |
# | Garmin Training Status (Text Label) | Column AK | Unit: None | String |
# | Total Walking Distance (km) | Column AL | Unit: km | Decimal |
# | Total Walking Duration (min) | Column AM | Unit: Minutes | Decimal |
# | Total Running Activities Count | Column AN | Unit: None | Integer |
# | Total Running Distance (km) | Column AO | Unit: km | Decimal |
# | Total Running Duration (min) | Column AP | Unit: Minutes | Decimal |
# | Total Strength Training Duration (min) | Column AQ | Unit: Minutes | Decimal |
#
# --------------------------------------------------
# FILE: drw_withings_bodyscan_data.csv
# NOTE: Contains body composition, cardiovascular, and nerve health measurements from a Withings scale.
# STRUCTURE: One row per recorded scan/weigh-in event.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | date | Column A | Unit: None | DD/MM/YYYY HH:MM |
# | Weight (kg) | Column B | Unit: kg | Decimal |
# | BMI | Column C | Unit: None | Decimal |
# | Body Fat (%) | Column D | Unit: % | Decimal |
# | Visceral Fat Rating | Column E | Unit: None | Decimal |
# | Pulse Wave Velocity (m/s) | Column F | Unit: m/s | Decimal |
# | AFib Status | Column G | Unit: None | String |
# | Vascular Age (years) | Column H | Unit: Years | Decimal |
# | Nerve Health Score | Column I | Unit: None | Decimal |
#
# --------------------------------------------------
# FILE: drw_garmin_activities_list.csv
# NOTE: Contains detailed statistics for individual recorded workouts and activities.
# STRUCTURE: One row per tracked activity.
# --------------------------------------------------
# | Metric Name | Column | Unit | Format |
# | :--- | :--- | :--- | :--- |
# | Activity ID | Column A | Unit: None | Integer |
# | Date (YYYY-MM-DD) | Column B | Unit: None | YYYY-MM-DD |
# | Start Time (HH:MM) | Column C | Unit: HH:MM | HH:MM or HH:MM:SS |
# | Activity Type | Column D | Unit: None | String |
# | Activity Name | Column E | Unit: None | String |
# | Distance (km) | Column F | Unit: km | Decimal |
# | Duration (min) | Column G | Unit: Minutes | Decimal |
# | Avg Pace (min/km) | Column H | Unit: min/km | HH:MM or HH:MM:SS |
# | Average Grade Adjusted Pace (min/km) | Column I | Unit: min/km | HH:MM or HH:MM:SS |
# | Total Ascent (m) | Column J | Unit: m | Integer |
# | Total Descent (m) | Column K | Unit: m | Integer |
# | Feels Like Temperature (Celsius) | Column L | Unit: °C | Decimal |
# | Weather Condition | Column M | Unit: None | String |
# | Sustained Wind Speed (km/h) | Column N | Unit: km/h | Integer |
# | Avg HR (bpm) | Column O | Unit: bpm | Integer |
# | Max HR (bpm) | Column P | Unit: bpm | Integer |
# | Average Cadence (spm) | Column Q | Unit: None | Integer |
# | Average Stride Length (m) | Column R | Unit: m | Decimal |
# | Average Ground Contact Time (ms) | Column S | Unit: ms | Integer |
# | Vertical Oscillation (cm) | Column T | Unit: cm | Decimal |
# | Aerobic Training Effect (0.0-5.0) | Column U | Unit: 0.0-5.0 | Decimal |
# | Anaerobic Training Effect (0.0-5.0) | Column V | Unit: 0.0-5.0 | Decimal |
# | Activity Training Load | Column W | Unit: None | Decimal |
# | Avg Power (Watts) | Column X | Unit: Watts | Integer |
# | Max Power (Watts) | Column Y | Unit: Watts | Integer |
# | Normalized Power (Watts) | Column Z | Unit: Watts | Integer |
# | Estimated Sweat Loss (ml) | Column AA | Unit: ml | Integer |
# | Garmin Training Effect Label | Column AB | Unit: None | String |
# | HR Zone 1 (min) | Column AC | Unit: Minutes | Decimal |
# | HR Zone 2 (min) | Column AD | Unit: Minutes | Decimal |
# | HR Zone 3 (min) | Column AE | Unit: Minutes | Decimal |
# | HR Zone 4 (min) | Column AF | Unit: Minutes | Decimal |
# | HR Zone 5 (min) | Column AG | Unit: Minutes | Decimal |
# | Power Zone 1 (min) | Column AH | Unit: Minutes | Decimal |
# | Power Zone 2 (min) | Column AI | Unit: Minutes | Decimal |
# | Power Zone 3 (min) | Column AJ | Unit: Minutes | Decimal |
# | Power Zone 4 (min) | Column AK | Unit: Minutes | Decimal |
# | Power Zone 5 (min) | Column AL | Unit: Minutes | Decimal |

```
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
