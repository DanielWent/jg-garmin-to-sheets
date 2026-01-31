import logging
import io
import pandas as pd
from typing import List, Optional
from datetime import date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveClient:
    def __init__(self, credentials_path: str, folder_id: str):
        self.credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self.service = build('drive', 'v3', credentials=self.credentials)
        self.folder_id = folder_id

    def _get_file_id(self, filename: str) -> Optional[str]:
        """Checks if a file exists in the specific folder and returns its ID."""
        # Query specifically looks for file with name in the folder and not trashed
        query = f"name = '{filename}' and '{self.folder_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def _metrics_to_df(self, metrics: List[GarminMetrics], headers: List[str]) -> pd.DataFrame:
        """Converts GarminMetrics objects to a Pandas DataFrame based on config headers."""
        data = []
        for m in metrics:
            row = {}
            for h in headers:
                attr = HEADER_TO_ATTRIBUTE_MAP.get(h)
                # getattr retrieves the value from the GarminMetrics object
                val = getattr(m, attr, None) if attr else None
                # Ensure dates are strings for CSV consistency
                if isinstance(val, date):
                    val = val.isoformat()
                row[h] = val
            data.append(row)
        return pd.DataFrame(data)

    def _activities_to_df(self, metrics: List[GarminMetrics]) -> pd.DataFrame:
        """Flattens the list of activities from daily metrics into a DataFrame."""
        all_activities = []
        for m in metrics:
            if m.activities:
                all_activities.extend(m.activities)
        
        if not all_activities:
            return pd.DataFrame()

        # The activities are already dicts matching the keys needed (from parser.py)
        return pd.DataFrame(all_activities)

    def update_csv(self, filename: str, metrics: List[GarminMetrics], headers: List[str], sort_date_desc: bool = True):
        """Downloads existing CSV, merges new data, removes duplicates, and re-uploads."""
        new_df = self._metrics_to_df(metrics, headers)
        if new_df.empty:
            return

        file_id = self._get_file_id(filename)
        
        if file_id:
            # 1. Download existing content
            try:
                # get_media returns the file content directly
                content = self.service.files().get_media(fileId=file_id).execute()
                existing_df = pd.read_csv(io.BytesIO(content))
                
                # 2. Merge (Upsert based on Date)
                if 'Date' in existing_df.columns:
                    combined_df = pd.concat([existing_df, new_df])
                    # Drop duplicates keeping the LAST (newest) version of that date
                    combined_df = combined_df.drop_duplicates(subset=['Date'], keep='last')
                else:
                    combined_df = new_df
            except Exception as e:
                logger.warning(f"Could not merge with existing file {filename}, overwriting. Error: {e}")
                combined_df = new_df
        else:
            combined_df = new_df

        # 3. Sort
        if 'Date' in combined_df.columns:
            combined_df = combined_df.sort_values(by='Date', ascending=False if sort_date_desc else True)

        # 4. Upload
        csv_buffer = io.StringIO()
        combined_df.to_csv(csv_buffer, index=False)
        
        media_body = MediaIoBaseUpload(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')), 
            mimetype='text/csv',
            resumable=True
        )

        if file_id:
            logger.info(f"Updating existing CSV: {filename}")
            self.service.files().update(
                fileId=file_id,
                media_body=media_body
            ).execute()
        else:
            logger.info(f"Creating new CSV: {filename}")
            file_metadata = {
                'name': filename, 
                'parents': [self.folder_id],
                'mimeType': 'text/csv'
            }
            self.service.files().create(
                body=file_metadata,
                media_body=media_body
            ).execute()

    def update_activities_csv(self, filename: str, metrics: List[GarminMetrics]):
        """Special handler for activities list which merges on Activity ID."""
        new_df = self._activities_to_df(metrics)
        if new_df.empty:
            return

        file_id = self._get_file_id(filename)
        
        if file_id:
            try:
                content = self.service.files().get_media(fileId=file_id).execute()
                existing_df = pd.read_csv(io.BytesIO(content))
                
                combined_df = pd.concat([existing_df, new_df])
                # Deduplicate by Activity ID
                if 'Activity ID' in combined_df.columns:
                    combined_df = combined_df.drop_duplicates(subset=['Activity ID'], keep='last')
                    
                    # Sort by Date desc if available
                    date_col = next((c for c in combined_df.columns if 'Date' in c), None)
                    if date_col:
                         combined_df = combined_df.sort_values(by=date_col, ascending=False)
            except Exception as e:
                logger.warning(f"Error merging activities, overwriting: {e}")
                combined_df = new_df
        else:
            combined_df = new_df

        # Upload Logic
        csv_buffer = io.StringIO()
        combined_df.to_csv(csv_buffer, index=False)
        media_body = MediaIoBaseUpload(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')), 
            mimetype='text/csv', 
            resumable=True
        )

        if file_id:
            logger.info(f"Updating activities CSV: {filename}")
            self.service.files().update(fileId=file_id, media_body=media_body).execute()
        else:
            logger.info(f"Creating new activities CSV: {filename}")
            file_metadata = {
                'name': filename, 
                'parents': [self.folder_id], 
                'mimeType': 'text/csv'
            }
            self.service.files().create(
                body=file_metadata, 
                media_body=media_body
            ).execute()
