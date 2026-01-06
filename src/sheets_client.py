import logging
from typing import List, Any
from datetime import date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import (
    GarminMetrics, 
    HEADER_TO_ATTRIBUTE_MAP, 
    ACTIVITY_HEADERS,
    SLEEP_HEADERS, 
    STRESS_HEADERS, 
    BODY_COMP_HEADERS, 
    ACTIVITY_SUMMARY_HEADERS
)

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

class GoogleAuthTokenRefreshError(Exception):
    pass

class GoogleSheetsClient:
    def __init__(self, credentials_path: str, spreadsheet_id: str, sheet_name: str):
        if not spreadsheet_id:
            raise ValueError("Spreadsheet ID is missing.")
            
        self.spreadsheet_id = spreadsheet_id
        # We ignore the passed 'sheet_name' now as we have fixed tab names
        self.sleep_tab_name = "Sleep Data"
        self.stress_tab_name = "Stress Data"
        self.body_tab_name = "Body Composition Data"
        self.activity_sum_tab_name = "Activity Summary Data"
        self.activities_sheet_name = "Activities"
        
        self.credentials_path = credentials_path
        self.credentials = self._get_credentials()
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.spreadsheet_title = None 

    def _get_credentials(self) -> Credentials:
        try:
            return Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=SCOPES
            )
        except Exception as e:
            logger.error(f"Failed to authenticate with Service Account: {e}")
            raise

    def _get_spreadsheet_details(self):
        try:
            sheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            self.spreadsheet_title = sheet_metadata['properties']['title']
            return sheet_metadata.get('sheets', [])
        except HttpError as e:
            logger.error(f"An error occurred fetching spreadsheet details: {e}")
            raise

    def _ensure_tab_exists(self, tab_name: str, headers: List[str], all_sheets_properties):
        """Ensures a specific tab exists and has headers."""
        sheet_exists = any(s['properties']['title'] == tab_name for s in all_sheets_properties)
        
        if not sheet_exists:
            logger.info(f"Sheet '{tab_name}' not found. Creating it now.")
            body = {'requests': [{'addSheet': {'properties': {'title': tab_name}}}]}
            self.service.spreadsheets().batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()

        range_to_check = f"'{tab_name}'!A1"
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=range_to_check
        ).execute()

        if 'values' not in result:
            logger.info(f"Sheet '{tab_name}' is empty. Writing headers.")
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_to_check,
                valueInputOption='RAW',
                body={'values': [headers]}
            ).execute()

    def update_metrics(self, metrics: List[GarminMetrics]):
        """Updates all 5 tabs."""
        all_sheets_properties = self._get_spreadsheet_details()
        
        # --- NEW LOGIC: Filter out 'today' for specific tabs ---
        today = date.today()
        metrics_historical = []
        
        for m in metrics:
            # Handle cases where m.date might be a string or a date object
            m_date = m.date
            if isinstance(m_date, str):
                try:
                    m_date = date.fromisoformat(m_date)
                except ValueError:
                    pass # If we can't parse it, we leave it alone (or skip)
            
            # Only add to historical list if it is NOT today
            if m_date != today:
                metrics_historical.append(m)
        # -------------------------------------------------------

        # 1. Update Sleep Data (Keep ALL data, including today)
        self._ensure_tab_exists(self.sleep_tab_name, SLEEP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.sleep_tab_name, SLEEP_HEADERS, metrics)

        # 2. Update Stress Data (HISTORICAL ONLY - deletes/excludes today)
        self._ensure_tab_exists(self.stress_tab_name, STRESS_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.stress_tab_name, STRESS_HEADERS, metrics_historical)

        # 3. Update Body Composition Data (Keep ALL data)
        self._ensure_tab_exists(self.body_tab_name, BODY_COMP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.body_tab_name, BODY_COMP_HEADERS, metrics)

        # 4. Update Activity Summary Data (HISTORICAL ONLY - deletes/excludes today)
        self._ensure_tab_exists(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, metrics_historical)

        # 5. Update Activities Tab (Keep ALL data - specific activities are valid today)
        self._ensure_tab_exists(self.activities_sheet_name, ACTIVITY_HEADERS, all_sheets_properties)
        self._update_activities(metrics)

    def _update_sheet_generic(self, tab_name: str, headers: List[str], metrics: List[GarminMetrics]):
        """Generic logic to update any summary-style tab based on provided headers."""
        try:
            date_column_range = f"'{tab_name}'!A:A"
            result = self.service.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=date_column_range).execute()
            existing_dates_list = result.get('values', [])
            date_to_row_map = {row[0]: i + 1 for i, row in enumerate(existing_dates_list) if row}
        except HttpError as e:
            logger.error(f"Could not read existing dates for {tab_name}: {e}")
            return

        updates = []
        appends = []

        for metric in metrics:
            metric_date_str = metric.date.isoformat() if isinstance(metric.date, date) else metric.date
            
            row_data = []
            for header in headers:
                attribute_name = HEADER_TO_ATTRIBUTE_MAP.get(header)
                value = getattr(metric, attribute_name, "") if attribute_name else ""
                
                if attribute_name == 'date':
                    value = metric_date_str

                if value is None:
                    value = ""
                elif isinstance(value, float):
                    value = round(value, 2)
                
                row_data.append(value)

            if metric_date_str in date_to_row_map:
                row_number = date_to_row_map[metric_date_str]
                updates.append({
                    'range': f"'{tab_name}'!A{row_number}",
                    'values': [row_data]
                })
            else:
                appends.append(row_data)

        if updates:
            logger.info(f"Updating {len(updates)} rows in '{tab_name}'.")
            body = {'valueInputOption': 'USER_ENTERED', 'data': updates}
            self.service.spreadsheets().values().batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()

        if appends:
            logger.info(f"Appending {len(appends)} rows to '{tab_name}'.")
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': appends}
            ).execute()

    def _update_activities(self, metrics: List[GarminMetrics]):
        """Logic to update the Activities tab (No updates, only appends new IDs)."""
        
        # 1. Flatten all activities from all days into a single list
        new_activities_buffer = []
        for metric in metrics:
            if metric.activities:
                new_activities_buffer.extend(metric.activities)
        
        if not new_activities_buffer:
            return

        # 2. Get existing Activity IDs to prevent duplicates
        try:
            id_column_range = f"'{self.activities_sheet_name}'!A:A"
            result = self.service.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=id_column_range).execute()
            existing_ids = set()
            for row in result.get('values', []):
                if row: existing_ids.add(str(row[0])) # Store as string
        except HttpError as e:
            logger.error(f"Could not read existing activity IDs: {e}")
            return

        # 3. Filter for unique new activities
        appends = []
        for act in new_activities_buffer:
            act_id = str(act.get("Activity ID"))
            if act_id not in existing_ids:
                # Prepare row based on ACTIVITY_HEADERS
                row_data = []
                for header in ACTIVITY_HEADERS:
                    val = act.get(header, "")
                    row_data.append(val)
                appends.append(row_data)
                existing_ids.add(act_id) # Prevent dupes within the same batch

        # 4. Write to sheet
        if appends:
            logger.info(f"Appending {len(appends)} new activities to '{self.activities_sheet_name}'.")
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.activities_sheet_name}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': appends}
            ).execute()
        else:
            logger.info("No new unique activities found.")
