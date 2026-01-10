import logging
from typing import List, Any
from datetime import date, timedelta
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
    BP_HEADERS,
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
        # Define fixed tab names
        self.sleep_tab_name = "Sleep Data"
        self.stress_tab_name = "Stress Data"
        self.body_tab_name = "Body Composition Data"
        self.bp_tab_name = "Blood Pressure Data"
        self.activity_sum_tab_name = "Activity Summary Data"
        self.activities_sheet_name = "List of Tracked Activities"
        
        self.credentials_path = credentials_path
        self.credentials = self._get_credentials()
        self.service = build('sheets', 'v4', credentials=self.credentials)

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
            return sheet_metadata.get('sheets', [])
        except HttpError as e:
            logger.error(f"An error occurred fetching spreadsheet details: {e}")
            raise

    def _ensure_tab_exists(self, tab_name: str, headers: List[str], all_sheets_properties):
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
        """Updates the daily metric tabs (Sleep, Stress, Body, BP, Summary)."""
        all_sheets_properties = self._get_spreadsheet_details()
        
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

        self._ensure_tab_exists(self.sleep_tab_name, SLEEP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.sleep_tab_name, SLEEP_HEADERS, metrics)

        self._ensure_tab_exists(self.stress_tab_name, STRESS_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.stress_tab_name, STRESS_HEADERS, metrics_historical)

        self._ensure_tab_exists(self.body_tab_name, BODY_COMP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.body_tab_name, BODY_COMP_HEADERS, metrics)
        
        self._ensure_tab_exists(self.bp_tab_name, BP_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.bp_tab_name, BP_HEADERS, metrics)

        self._ensure_tab_exists(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, all_sheets_properties)
        self._update_sheet_generic(self.activity_sum_tab_name, ACTIVITY_SUMMARY_HEADERS, metrics_historical)

        # Removed: Activities update (now handled separately)

    def update_activities_tab(self, metrics: List[GarminMetrics]):
        """Updates ONLY the 'List of Tracked Activities' tab."""
        all_sheets_properties = self._get_spreadsheet_details()
        self._ensure_tab_exists(self.activities_sheet_name, ACTIVITY_HEADERS, all_sheets_properties)
        self._update_activities(metrics)

    def _update_sheet_generic(self, tab_name: str, headers: List[str], metrics: List[GarminMetrics]):
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
            body = {'valueInputOption': 'USER_ENTERED', 'data': updates}
            self.service.spreadsheets().values().batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()

        if appends:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': appends}
            ).execute()

    def _update_activities(self, metrics: List[GarminMetrics]):
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
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.activities_sheet_name}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': appends}
            ).execute()

    def prune_old_data(self, days_to_keep: int = 365):
        """Removes rows older than the retention period from managed sheets (excluding activities)."""
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        logger.info(f"Pruning data older than {cutoff_date.isoformat()}...")

        sheet_configs = [
            (self.sleep_tab_name, 0),
            (self.stress_tab_name, 0),
            (self.body_tab_name, 0),
            (self.bp_tab_name, 0),
            (self.activity_sum_tab_name, 0),
            # Activities removed from here
        ]

        for tab_name, date_col_idx in sheet_configs:
            self._prune_single_sheet(tab_name, date_col_idx, cutoff_date)

    def prune_activities_tab(self, days_to_keep: int = 365):
        """Removes rows older than the retention period from the activities sheet."""
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        self._prune_single_sheet(self.activities_sheet_name, 1, cutoff_date)

    def _prune_single_sheet(self, tab_name: str, date_col_idx: int, cutoff_date: date):
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, 
                range=f"'{tab_name}'" 
            ).execute()
            
            rows = result.get('values', [])
            if not rows or len(rows) < 2:
                return 

            headers = rows[0]
            data_rows = rows[1:]
            
            kept_rows = []
            rows_removed = 0

            for row in data_rows:
                if len(row) <= date_col_idx:
                    kept_rows.append(row)
                    continue
                
                date_str = row[date_col_idx]
                try:
                    row_date = date.fromisoformat(date_str)
                    if row_date >= cutoff_date:
                        kept_rows.append(row)
                    else:
                        rows_removed += 1
                except ValueError:
                    kept_rows.append(row)

            if rows_removed > 0:
                logger.info(f"Removing {rows_removed} old rows from '{tab_name}'.")
                
                self.service.spreadsheets().values().clear(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab_name}'"
                ).execute()
                
                body = {'values': [headers] + kept_rows}
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab_name}'!A1",
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()

        except Exception as e:
            logger.warning(f"Could not prune sheet '{tab_name}': {e}")
