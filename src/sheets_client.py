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

class GoogleSheetsClient:
    def __init__(self, credentials_path: str, spreadsheet_id: str, sheet_name: str):
        if not spreadsheet_id:
            raise ValueError("Spreadsheet ID is missing.")
            
        self.spreadsheet_id = spreadsheet_id
        # Define fixed tab names as per requirements
        self.sleep_tab_name = "Sleep Data"
        self.stress_tab_name = "Stress Data"
        self.body_tab_name = "Body Composition Data"
        self.activity_sum_tab_name = "Activity Summary Data"
        self.activities_sheet_name = "List of Tracked Activities"
        
        self.credentials_path = credentials_path
        self.credentials = self._get_credentials()
        self.service = build('sheets', 'v4', credentials=self.credentials)

    def _get_credentials(self) -> Credentials:
        """Authenticates using the service account file."""
        try:
            return Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=SCOPES
            )
        except Exception as e:
            logger.error(f"Failed to authenticate with Service Account: {e}")
            raise

    def _get_spreadsheet_details(self):
        """Fetches metadata for all sheets in the spreadsheet."""
        try:
            sheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
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
        """Updates the five distinct tabs with appropriate data filtering."""
        all_sheets_properties = self._get_spreadsheet_details()
        
        # Filter for historical data (excluding today) for Stress and Activity Summary tabs
        today = date.today()
        metrics_historical = []
        for m in metrics:
            m_date = m.date
            if isinstance(m_date, str):
                try:
                    m_date = date.fromisoformat(m_date)
                except ValueError:
                    pass
            if m_date != today:
                metrics_historical.append(m)

        # 1. Update Sleep Data (Includes today)
        self._ensure_tab_exists(self.sleep_tab_name, SLEEP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.sleep_tab_name, SLEEP_HEADERS, metrics)

        # 2. Update Stress Data (Historical only)
        self._ensure_tab_exists(self.stress_tab_name, STRESS_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.stress_tab_name, STRESS_HEADERS, metrics_historical)

        # 3. Update Body Composition Data (Includes today)
        self._ensure_tab_exists(self.body_tab_name, BODY_COMP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.body_tab_name, BODY_COMP_HEADERS, metrics)

        # 4. Update Activity Summary Data (Historical only)
        self._ensure_tab_exists(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, metrics_historical)

        # 5. Update List of Tracked Activities (Appends new activities only)
        self._ensure_tab_exists(self.activities_sheet_name, ACTIVITY_HEADERS, all_sheets_properties)
        self._update_activities(metrics)

    def _update_sheet_generic(self, tab_name: str, headers: List[str], metrics: List[GarminMetrics]):
        """Generic logic to update or append rows in summary-style tabs."""
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
        """Logic to update the List of Tracked Activities tab by appending unique Activity IDs."""
        new_activities_buffer = []
        for metric in metrics:
            if metric.activities:
                new_activities_buffer.extend(metric.activities)
        
        if not new_activities_buffer:
            return

        try:
            id_column_range = f"'{self.activities_sheet_name}'!A:A"
            result = self.service.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=id_column_range).execute()
            existing_ids = {str(row[0]) for row in result.get('values', []) if row}
        except HttpError as e:
            logger.error(f"Could not read existing activity IDs: {e}")
            return

        appends = []
        for act in new_activities_buffer:
            act_id = str(act.get("Activity ID"))
            if act_id not in existing_ids:
                row_data = [act.get(header, "") for header in ACTIVITY_HEADERS]
                appends.append(row_data)
                existing_ids.add(act_id)

        if appends:
            logger.info(f"Appending {len(appends)} new activities to '{self.activities_sheet_name}'.")
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.activities_sheet_name}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': appends}
            ).execute()
