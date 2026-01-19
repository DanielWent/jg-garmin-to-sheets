import logging
import gspread
from gspread.utils import ValueRenderOption
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from typing import List, Any
from .config import (
    HEADERS, SLEEP_HEADERS, BODY_HEADERS, BP_HEADERS, 
    STRESS_HEADERS, ACTIVITIES_HEADERS, 
    HEADER_TO_ATTRIBUTE_MAP, GarminMetrics
)
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class GoogleAuthTokenRefreshError(Exception):
    pass

class GoogleSheetsClient:
    def __init__(self, credentials_path: str, spreadsheet_id: str, sheet_name: str = 'Daily Summaries'):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        
        # Default Sheet Names
        self.main_sheet_name = sheet_name
        self.sleep_tab_name = "Sleep Logs"
        self.body_tab_name = "Body Composition Data"
        self.bp_tab_name = "Blood Pressure Data"
        self.stress_tab_name = "Stress Data"
        self.activities_tab_name = "Activities"
        self.activity_summary_tab_name = "Activity Summaries"

        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=self.scopes
            )
            self.client = gspread.authorize(self.creds)
            self.service = self.client.auth
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise

    def _refresh_auth(self):
        """Force a refresh of the Google Auth token."""
        try:
            self.creds.refresh(Request())
            self.client = gspread.authorize(self.creds)
        except Exception as e:
            logger.error(f"Failed to refresh Google Auth token: {e}")
            raise GoogleAuthTokenRefreshError("Could not refresh authentication token")

    def _update_sheet_generic(self, tab_name: str, headers: List[str], data_rows: List[Any], is_metric_object: bool = True):
        """
        Generic helper to update a specific sheet.
        If is_metric_object is True, data_rows is a list of GarminMetrics, and we map them using headers.
        If is_metric_object is False, data_rows is a list of lists (raw values).
        """
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # 1. Get or Create Worksheet
            try:
                worksheet = spreadsheet.worksheet(tab_name)
            except gspread.WorksheetNotFound:
                logger.info(f"Worksheet '{tab_name}' not found. Creating it...")
                worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
            
            # 2. Update Headers (Always ensure they match config)
            worksheet.update('A1', [headers])
            
            # 3. Prepare New Data
            new_data_map = {} # Keyed by Date string for easy lookup
            
            for item in data_rows:
                if is_metric_object:
                    # Map Metric Object to Row
                    row = []
                    for h in headers:
                        attr = HEADER_TO_ATTRIBUTE_MAP.get(h)
                        val = getattr(item, attr, "") if attr else ""
                        row.append(str(val) if val is not None else "")
                    
                    date_val = item.date.isoformat()
                    new_data_map[date_val] = row
                else:
                    # Raw List (First column MUST be Date)
                    date_val = item[0] 
                    new_data_map[date_val] = [str(x) if x is not None else "" for x in item]

            # 4. Fetch Existing Data to Append/Update (Batch Friendly)
            existing_values = worksheet.get_all_values()
            
            if len(existing_values) > 1:
                # Map existing rows by date (assuming col 0 is Date)
                # We skip the header row [0]
                existing_map = {row[0]: (i + 2, row) for i, row in enumerate(existing_values[1:])}
            else:
                existing_map = {}

            updates = []
            rows_to_append = []

            for date_key, new_row in new_data_map.items():
                if date_key in existing_map:
                    # UPDATE existing row
                    row_idx, _ = existing_map[date_key]
                    # Create a batch update range (e.g., A5:F5)
                    col_letter = chr(64 + len(new_row)) # Simple conversion for A-Z
                    # Note: For many columns this simple char conversion breaks (Z->AA). 
                    # gspread handles list of lists well, but for specific row updates `update` is easier.
                    # For safety with wider sheets, let's use the row update.
                    
                    # We will use batch_update later, but gspread doesn't have a simple "update specific rows" batch method 
                    # without calculating A1 notation for every single one. 
                    # For simplicity in this script, we'll append to a list and overwrite, 
                    # OR just update individually if volume is low. 
                    # Given typical daily use (1-7 rows), individual updates are okay, but let's be cleaner:
                    
                    # We will simply REWRITE the whole sheet if we are mixing updates and appends, 
                    # OR we just append the new ones and let the sort handle it?
                    # Better: Update the specific range for the match.
                    
                    # Check if data actually changed to save API calls?
                    # For now, let's just overwrite the row to ensure latest data.
                    range_name = f"A{row_idx}"
                    updates.append({
                        'range': range_name,
                        'values': [new_row]
                    })
                else:
                    rows_to_append.append(new_row)

            # Execute Updates
            if updates:
                worksheet.batch_update(updates)
            
            # Execute Appends
            if rows_to_append:
                worksheet.append_rows(rows_to_append)

            logger.info(f"Updated {tab_name}: {len(updates)} rows updated, {len(rows_to_append)} rows appended.")

        except Exception as e:
            logger.error(f"Error updating {tab_name}: {e}")
            # Don't raise, let other sheets proceed

    def update_metrics(self, metrics_list: List[GarminMetrics]):
        """Updates the MAIN Daily Summary sheet."""
        self._update_sheet_generic(self.main_sheet_name, HEADERS, metrics_list, is_metric_object=True)

    def update_sleep(self, metrics_list: List[GarminMetrics]):
        """Updates the separate Sleep Logs sheet."""
        # Convert objects to raw rows based on SLEEP_HEADERS logic
        rows = []
        for m in metrics_list:
            # Derived/Specific logic for Sleep Sheet columns
            # [Date, Score, Dur, Start, End, Deep, Light, REM, Awake, Restless, Resp, SpO2]
            row = [
                m.date.isoformat(),
                m.sleep_score,
                m.sleep_length,
                m.sleep_start_time,
                m.sleep_end_time,
                m.sleep_deep,
                m.sleep_light,
                m.sleep_rem,
                m.sleep_awake,
                "", # Restlessness not currently parsed
                m.overnight_respiration,
                m.overnight_pulse_ox
            ]
            rows.append(row)
        
        self._update_sheet_generic(self.sleep_tab_name, SLEEP_HEADERS, rows, is_metric_object=False)

    def update_body_composition(self, metrics_list: List[GarminMetrics]):
        """Syncs body comp data."""
        # HEADERS: Date, Weight, BMI, Body Fat, Muscle, Bone, Water
        rows = []
        for m in metrics_list:
            rows.append([
                m.date.isoformat(),
                m.weight,
                m.bmi,
                m.body_fat,
                "", "", "" # Muscle, Bone, Water not parsed yet
            ])
        self._update_sheet_generic(self.body_tab_name, BODY_HEADERS, rows, is_metric_object=False)

    def update_blood_pressure(self, metrics_list: List[GarminMetrics]):
        """Syncs blood pressure data."""
        rows = []
        for m in metrics_list:
            if m.blood_pressure_systolic:
                rows.append([
                    m.date.isoformat(),
                    m.blood_pressure_systolic,
                    m.blood_pressure_diastolic,
                    "", "" # Pulse, Notes
                ])
        if rows:
            self._update_sheet_generic(self.bp_tab_name, BP_HEADERS, rows, is_metric_object=False)

    def update_stress(self, metrics_list: List[GarminMetrics]):
        """Syncs stress data."""
        # HEADERS: Date, Stress Level, Rest, Low, Med, High, BB Max, BB Min
        rows = []
        for m in metrics_list:
            rows.append([
                m.date.isoformat(),
                m.average_stress,
                m.rest_stress_duration,
                m.low_stress_duration,
                m.medium_stress_duration,
                m.high_stress_duration,
                m.body_battery_max,  # <--- NEW
                m.body_battery_min   # <--- NEW
            ])
        self._update_sheet_generic(self.stress_tab_name, STRESS_HEADERS, rows, is_metric_object=False)

    def update_activity_summary(self, metrics_list: List[GarminMetrics]):
        """
        Syncs activity data. 
        Note: One Daily Metric object can contain MULTIPLE activities.
        """
        rows = []
        for m in metrics_list:
            for act in m.activities:
                # act is a Dictionary matching keys in ACTIVITIES_HEADERS
                row = []
                for h in ACTIVITIES_HEADERS:
                    # Dictionary lookup
                    val = act.get(h, "")
                    row.append(str(val) if val is not None else "")
                rows.append(row)

        # For activities, we allow multiple rows per date, so our generic updater's 
        # "Date key map" logic might overwrite if there are multiple activities on one day.
        # We need a custom handling here or ensure the key is unique (Activity ID).
        
        self._update_sheet_activities_custom(rows)

    def _update_sheet_activities_custom(self, rows: List[List[str]]):
        """
        Custom updater for activities to handle Activity ID as the unique key, not Date.
        """
        tab_name = self.activity_summary_tab_name
        headers = ACTIVITIES_HEADERS
        
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet(tab_name)
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
                worksheet.update('A1', [headers])

            # Get existing Activity IDs (Column 1)
            existing_values = worksheet.get_all_values()
            existing_ids = {}
            if len(existing_values) > 1:
                # Map Activity ID -> Row Index
                for i, row in enumerate(existing_values[1:]):
                    # Activity ID is at index 0
                    if row:
                        existing_ids[row[0]] = i + 2

            updates = []
            rows_to_append = []

            for new_row in rows:
                act_id = new_row[0] # Activity ID
                if act_id in existing_ids:
                    # Update existing row
                    row_idx = existing_ids[act_id]
                    range_name = f"A{row_idx}"
                    updates.append({
                        'range': range_name,
                        'values': [new_row]
                    })
                else:
                    rows_to_append.append(new_row)

            if updates:
                worksheet.batch_update(updates)
            
            if rows_to_append:
                worksheet.append_rows(rows_to_append)
                
            logger.info(f"Updated {tab_name}: {len(updates)} updated, {len(rows_to_append)} appended.")

        except Exception as e:
            logger.error(f"Error updating {tab_name}: {e}")

    def update_activities_tab(self, metrics_list: List[GarminMetrics]):
        # Legacy/Alias for compatibility if needed, or redirect
        self.update_activity_summary(metrics_list)

    def prune_old_data(self, days_to_keep: int = 365):
        # Implementation of pruning if needed...
        pass
    
    def sort_sheets(self):
        # Implementation of sorting...
        pass
