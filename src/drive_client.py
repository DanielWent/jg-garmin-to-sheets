import logging
import io
import pandas as pd
from typing import List, Optional
from datetime import date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .config import HEADER_TO_ATTRIBUTE_MAP

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveClient:
    def __init__(self, credentials_path: str, folder_id: str):
        self.credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self.service = build('drive', 'v3', credentials=self.credentials)
        self.folder_id = folder_id

    def _get_file_id(self, filename: str) -> Optional[str]:
        """Checks if a file exists in the specific folder and returns its ID."""
        query = f"name = '{filename}' and '{self.folder_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def _metrics_to_df(self, metrics: List, headers: List[str]) -> pd.DataFrame:
        """Converts GarminMetrics objects to a DataFrame with strict column ordering."""
        data = []
        for m in metrics:
            row = {}
            for h in headers:
                attr = HEADER_TO_ATTRIBUTE_MAP.get(h)
                val = getattr(m, attr, None) if attr else None
                
                # Formatting Logic
                if isinstance(val, date):
                    val = val.isoformat()
                elif isinstance(val, float):
                    if "VO2 Max" in h:
                        val = round(val, 1)
                    else:
                        val = round(val, 2)
                
                row[h] = val
            data.append(row)
        
        # enforce column order matching headers exactly
        return pd.DataFrame(data, columns=headers)

    def _activities_to_df(self, metrics: List, headers: List[str]) -> pd.DataFrame:
        """Flattens activities and enforces strict adherence to config headers."""
        all_activities = []
        for m in metrics:
            if m.activities:
                all_activities.extend(m.activities)
        
        if not all_activities:
            return pd.DataFrame(columns=headers)

        df = pd.DataFrame(all_activities)
        
        # Strict column enforcement
        df = df.reindex(columns=headers)
        
        return df

    def update_csv(self, filename: str, metrics: List, headers: List[str], sort_date_desc: bool = True):
        """Standard metrics update."""
        new_df = self._metrics_to_df(metrics, headers)
        if new_df.empty:
            return
            
        self._upload_df(filename, new_df, 'Date', sort_date_desc)

    def update_activities_csv(self, filename: str, metrics: List, headers: List[str]):
        """Activities update with strict header enforcement."""
        new_df = self._activities_to_df(metrics, headers)
        if new_df.empty:
            return

        # Deduplication based on Activity ID
        self._upload_df(filename, new_df, 'Activity ID', sort_date_desc=False, is_activity=True)

    def _upload_df(self, filename: str, new_df: pd.DataFrame, dedup_col: str, sort_date_desc: bool, is_activity: bool = False):
        file_id = self._get_file_id(filename)
        
        combined_df = None
        
        if file_id:
            try:
                # Download existing
                content = self.service.files().get_media(fileId=file_id).execute()
                existing_df = pd.read_csv(io.BytesIO(content))
                
                # === FIX: Remove garbage "Unnamed" columns from placeholder files ===
                existing_df = existing_df.loc[:, ~existing_df.columns.str.contains('^Unnamed')]
                
                # Merge
                combined_df = pd.concat([existing_df, new_df])
                
                # Deduplicate
                if dedup_col in combined_df.columns:
                    combined_df = combined_df.drop_duplicates(subset=[dedup_col], keep='last')
                    
            except Exception as e:
                logger.warning(f"Error merging {filename}, overwriting: {e}")
                combined_df = new_df
        else:
            combined_df = new_df

        # === 5-YEAR RETENTION POLICY ===
        # Filter combined_df to keep only the last 5 years
        try:
            # Identify the correct date column
            date_col = 'Date (YYYY-MM-DD)' if is_activity else 'Date'
            
            if date_col in combined_df.columns:
                # Convert to datetime for comparison
                combined_df[date_col] = pd.to_datetime(combined_df[date_col])
                
                # Calculate cutoff date (Today - 1826 days)
                cutoff_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=1826)
                
                # Filter rows
                combined_df = combined_df[combined_df[date_col] >= cutoff_date]
                
                # Convert back to string format YYYY-MM-DD
                combined_df[date_col] = combined_df[date_col].dt.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"Could not apply 1826-day retention policy to {filename}: {e}")

        # === SORTING ===
        if is_activity:
            if 'Date (YYYY-MM-DD)' in combined_df.columns:
                combined_df = combined_df.sort_values(by='Date (YYYY-MM-DD)', ascending=False)
        elif sort_date_desc and 'Date' in combined_df.columns:
            combined_df = combined_df.sort_values(by='Date', ascending=False)

        # Upload
        csv_buffer = io.StringIO()
        combined_df.to_csv(csv_buffer, index=False)
        media_body = MediaIoBaseUpload(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')), 
            mimetype='text/csv', 
            resumable=True
        )

        if file_id:
            logger.info(f"Updating CSV: {filename}")
            self.service.files().update(fileId=file_id, media_body=media_body).execute()
        else:
            logger.info(f"Creating CSV: {filename}")
            file_metadata = {'name': filename, 'parents': [self.folder_id], 'mimeType': 'text/csv'}
            self.service.files().create(body=file_metadata, media_body=media_body).execute()
