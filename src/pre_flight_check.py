import os
import io
import pandas as pd
from datetime import datetime, timezone
from src.main import ensure_credentials_file_exists
from src.drive_client import GoogleDriveClient

def needs_sync(folder_id: str, file_prefix: str) -> bool:
    if not folder_id:
        return False
    
    try:
        client = GoogleDriveClient('credentials/client_secret.json', folder_id)
        filename = f"{file_prefix}garmin_data.csv"
        file_id = client._get_file_id(filename)
        
        if not file_id:
            return True 
        
        content = client.service.files().get_media(fileId=file_id).execute()
        df = pd.read_csv(io.BytesIO(content))
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        today_row = df[df['Date (YYYY-MM-DD)'] == today_str]
        if today_row.empty:
            return True
            
        sleep_score = today_row['Garmin Sleep Score (0-100)'].iloc[0]
        if pd.isna(sleep_score) or str(sleep_score).strip() in ["", "NA", "PENDING"]:
            return True 
            
        return False
    except Exception as e:
        print(f"Error checking {file_prefix}: {e}")
        return True 

if __name__ == "__main__":
    ensure_credentials_file_exists()
    
    run_user1 = needs_sync(os.environ.get('USER1_DRIVE_FOLDER_ID'), 'drw_')
    run_user2 = needs_sync(os.environ.get('USER2_DRIVE_FOLDER_ID'), 'aflw_')
    
    print(f"USER1 needs sync: {run_user1}")
    print(f"USER2 needs sync: {run_user2}")
    
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f"run_user1={'true' if run_user1 else 'false'}\n")
        f.write(f"run_user2={'true' if run_user2 else 'false'}\n")
