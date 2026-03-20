import logging
import io
import pandas as pd
import numpy as np
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
        query = f"name = '{filename}' and '{self.folder_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def _metrics_to_df(self, metrics: List, headers: List[str]) -> pd.DataFrame:
        data = []
        for m in metrics:
            row = {}
            for h in headers:
                attr = HEADER_TO_ATTRIBUTE_MAP.get(h)
                
                if not attr and h == 'Date (YYYY-MM-DD)':
                    attr = HEADER_TO_ATTRIBUTE_MAP.get('Date')
                    
                val = getattr(m, attr, None) if attr else None
                
                # Aggressively standardize date objects to YYYY-MM-DD strings immediately
                if isinstance(val, date):
                    val = val.isoformat()
                    # Strip out any time/timezone data Garmin might attach
                    if 'T' in val:
                        val = val.split('T')[0]
                elif isinstance(val, float):
                    if "VO2 Max" in h:
                        val = round(val, 1)
                    else:
                        val = round(val, 2)
                
                row[h] = val
            data.append(row)
        return pd.DataFrame(data, columns=headers)

    def update_csv(self, filename: str, metrics: List, headers: List[str], sort_date_desc: bool = True):
        new_df = self._metrics_to_df(metrics, headers)
        if new_df.empty:
            return
            
        self._upload_df(filename, new_df, dedup_col='Date (YYYY-MM-DD)', sort_date_col='Date (YYYY-MM-DD)', sort_date_desc=sort_date_desc)

    def update_activities_csv(self, filename: str, activities: List[dict], headers: List[str], sort_date_desc: bool = True):
        if not activities:
            return
        new_df = pd.DataFrame(activities, columns=headers)
        if new_df.empty:
            return
        self._upload_df(filename, new_df, dedup_col='Activity ID', sort_date_col='Date (YYYY-MM-DD)', sort_date_desc=sort_date_desc)

    def _upload_df(self, filename: str, new_df: pd.DataFrame, dedup_col: str, sort_date_col: str, sort_date_desc: bool):
        file_id = self._get_file_id(filename)
        combined_df = None
        
        if file_id:
            try:
                content = self.service.files().get_media(fileId=file_id).execute()
                existing_df = pd.read_csv(io.BytesIO(content))
                existing_df = existing_df.loc[:, ~existing_df.columns.str.contains('^Unnamed')]
                
                # === SMART MERGE: PREVENT NA OVERWRITES ===
                # Convert explicit "NA" and empty strings in the newly fetched data to actual NaN (null) values
                new_df_cleaned = new_df.replace(["NA", "", "NaN"], np.nan)
                
                # Align both dataframes by their unique identifier (e.g., the Date)
                existing_idx = existing_df.set_index(dedup_col)
                new_idx = new_df_cleaned.set_index(dedup_col)
                
                # combine_first prioritizes the new data. If the new data is NaN (because of a rate limit), 
                # it safely falls back to preserving the numerical value from the existing spreadsheet.
                combined_idx = new_idx.combine_first(existing_idx)
                
                # Reset the index to turn the Date back into a normal column
                combined_df = combined_idx.reset_index()
                
                # Ensure the final column order strictly matches your expected headers
                valid_cols = [col for col in new_df.columns if col in combined_df.columns]
                combined_df = combined_df[valid_cols]
                
            except Exception as e:
                logger.warning(f"Error merging {filename}, overwriting: {e}")
                combined_df = new_df
        else:
            combined_df = new_df

        # === BULLETPROOF DATE PARSING, DEDUPLICATION & SORTING ===
        try:
            if sort_date_col in combined_df.columns:
                # 1. Safely parse dates. Try strict YYYY-MM-DD first to prevent ISO day/month flipping
                combined_df['_temp_date'] = pd.to_datetime(
                    combined_df[sort_date_col], 
                    format='%Y-%m-%d',
                    errors='coerce',
                    utc=True
                )
                
                # 2. For any older dates (DD/MM/YYYY) that failed the strict parse, safely use dayfirst=True
                missing_mask = combined_df['_temp_date'].isna()
                if missing_mask.any():
                    combined_df.loc[missing_mask, '_temp_date'] = pd.to_datetime(
                        combined_df.loc[missing_mask, sort_date_col], 
                        dayfirst=True, 
                        errors='coerce',
                        utc=True
                    )
                
                # 3. Standardize all valid dates to YYYY-MM-DD to guarantee deduplication works
                valid_dates = combined_df['_temp_date'].notna()
                combined_df.loc[valid_dates, sort_date_col] = combined_df.loc[valid_dates, '_temp_date'].dt.strftime('%Y-%m-%d')
                
                # 4. Deduplicate using the newly standardized exact strings
                # (Safety net: combine_first already merges exact index matches, but this catches rogue duplicates)
                if dedup_col in combined_df.columns:
                    combined_df = combined_df.drop_duplicates(subset=[dedup_col], keep='last')
                
                # 5. Apply 5-Year Retention Policy
                cutoff_date = pd.Timestamp.now(tz='UTC').normalize() - pd.Timedelta(days=1826)
                valid_mask = combined_df['_temp_date'].isna() | (combined_df['_temp_date'] >= cutoff_date)
                combined_df = combined_df[valid_mask]

                # 6. Sort mathematically
                if sort_date_desc:
                    combined_df = combined_df.sort_values(by='_temp_date', ascending=False, na_position='last')
                else:
                    combined_df = combined_df.sort_values(by='_temp_date', ascending=True, na_position='last')

                # 7. Cleanup
                combined_df = combined_df.drop(columns=['_temp_date'])
                
        except Exception as e:
            logger.warning(f"Could not apply date processing to {filename}: {e}")
            if dedup_col in combined_df.columns:
                combined_df = combined_df.drop_duplicates(subset=[dedup_col], keep='last')
            if sort_date_desc and sort_date_col in combined_df.columns:
                combined_df = combined_df.sort_values(by=sort_date_col, ascending=False)

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
