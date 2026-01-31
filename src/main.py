import os
import sys
import csv
import logging
import re
import asyncio
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from statistics import mean
import calendar

import typer
from dotenv import load_dotenv, find_dotenv

from src.garmin_client import GarminClient
from src.sheets_client import GoogleSheetsClient, GoogleAuthTokenRefreshError
from src.drive_client import GoogleDriveClient
from src.exceptions import MFARequiredException
from src.config import (
    HEADERS, 
    HEADER_TO_ATTRIBUTE_MAP, 
    GarminMetrics,
    SLEEP_HEADERS,
    BODY_COMP_HEADERS,
    BP_HEADERS,
    STRESS_HEADERS,
    ACTIVITY_SUMMARY_HEADERS,
    ACTIVITY_HEADERS
)

# Suppress noisy library warnings
logging.getLogger('google_auth_oauthlib.flow').setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

# Configure logging via Environment Variable
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer()

def ensure_credentials_file_exists():
    """
    Checks if credentials/client_secret.json exists.
    If not, tries to create it from the GOOGLE_SHEETS_CREDENTIALS environment variable.
    """
    creds_path = Path('credentials/client_secret.json')
    
    if creds_path.exists():
        return

    logger.info("client_secret.json not found. Attempting to create from environment variable...")
    
    raw_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    
    if not raw_json:
        logger.error("CRITICAL: 'credentials/client_secret.json' is missing and 'GOOGLE_SHEETS_CREDENTIALS' env var is empty.")
        sys.exit(1)

    try:
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        json_content = json.loads(raw_json)
        with open(creds_path, 'w') as f:
            json.dump(json_content, f, indent=2)
        logger.info(f"Successfully created {creds_path} from environment secret.")
        
    except Exception as e:
        logger.error(f"Failed to write credentials file: {e}")
        sys.exit(1)

async def sync(email: str, password: str, start_date: date, end_date: date, output_type: str, profile_data: dict, profile_name: str = ""):
    """Core sync logic with Sheets toggle."""
    try:
        garmin_client = GarminClient(email, password)
        await garmin_client.authenticate()
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Fetching metrics from {start_date.isoformat()} to {end_date.isoformat()}...")
    metrics_to_write = []
    current_date = start_date
    while current_date <= end_date:
        logger.info(f"Fetching metrics for {current_date.isoformat()}")
        daily_metrics = await garmin_client.get_metrics(current_date)
        metrics_to_write.append(daily_metrics)
        current_date += timedelta(days=1)

    if not metrics_to_write:
        logger.warning("No metrics fetched. Nothing to write.")
        return

    # Filter for Stress/Activity Summary tabs (historical only)
    today = date.today()
    metrics_historical = [m for m in metrics_to_write if m.date < today]

    # === GOOGLE DRIVE (CSV) SYNC ===
    if output_type == 'drive':
        folder_id = profile_data.get('drive_folder_id')
        if not folder_id:
            logger.error(f"DRIVE_FOLDER_ID not set for {profile_name}.")
            sys.exit(1)

        ensure_credentials_file_exists()
        
        try:
            drive_client = GoogleDriveClient('credentials/client_secret.json', folder_id)
            drive_client.update_csv("garmin_sleep.csv", metrics_to_write, SLEEP_HEADERS)
            drive_client.update_csv("garmin_body_composition.csv", metrics_to_write, BODY_COMP_HEADERS)
            drive_client.update_csv("garmin_blood_pressure.csv", metrics_to_write, BP_HEADERS)
            
            if metrics_historical:
                drive_client.update_csv("garmin_stress.csv", metrics_historical, STRESS_HEADERS)
                drive_client.update_csv("garmin_activity_summary.csv", metrics_historical, ACTIVITY_SUMMARY_HEADERS)
            
            drive_client.update_activities_csv("garmin_activities_list.csv", metrics_to_write, ACTIVITY_HEADERS)
            logger.info("Google Drive CSV sync completed successfully!")
        except Exception as e:
            logger.error(f"Drive Sync Failed: {e}", exc_info=True)
            sys.exit(1)

    # === GOOGLE SHEETS SYNC (WITH TOGGLE) ===
    # Check if sheets are explicitly requested or enabled via global toggle
    sheets_enabled_globally = os.getenv("ENABLE_SHEETS_UPDATE", "FALSE").upper() == "TRUE"
    
    if output_type == 'sheets' or sheets_enabled_globally:
        ensure_credentials_file_exists()
        try:
            sheets_id = profile_data.get('sheet_id')
            if not sheets_id:
                logger.warning(f"Sheets update requested for {profile_name}, but no SHEET_ID is configured.")
            else:
                sheet_name = profile_data.get('sheet_name', 'Daily Summaries')
                sheets_client = GoogleSheetsClient('credentials/client_secret.json', sheets_id, sheet_name)
                sheets_client.update_metrics(metrics_to_write)
                sheets_client.sort_sheets()

                # Activities Sheet Logic
                ACTIVITIES_SHEET_ID = "1EglkT03d_9RCPLXUay63G2b0GdyPKP62ljZa0ruEx1g"
                try:
                    act_client = GoogleSheetsClient('credentials/client_secret.json', ACTIVITIES_SHEET_ID, 'Activities')
                    act_client.update_activities_tab(metrics_to_write)
                    act_client.sort_sheets()
                except Exception as e:
                    logger.error(f"Failed to sync activities sheet: {e}")

                logger.info("Google Sheets sync completed successfully!")
        except Exception as sheet_error:
            logger.error(f"Google Sheets operation failed: {sheet_error}", exc_info=True)
            sys.exit(1)

    # === LOCAL CSV SYNC ===
    elif output_type == 'csv':
        output_dir = Path("./output")
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"garmingo_{profile_name if profile_name else 'output'}.csv"
        
        logger.info(f"Writing metrics to local CSV: {csv_path}")
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if f.tell() == 0: 
                writer.writerow(HEADERS)
            for metric in metrics_to_write:
                writer.writerow([getattr(metric, HEADER_TO_ATTRIBUTE_MAP.get(h, ""), "") for h in HEADERS])
        logger.info("Local CSV sync completed.")

def load_user_profiles():
    """Parses .env for user profiles (maintains full multi-user support)."""
    profiles = {}
    profile_pattern = re.compile(r"^(USER\d+)_(GARMIN_EMAIL|GARMIN_PASSWORD|SHEET_ID|MONTHLY_SHEET_ID|DRIVE_FOLDER_ID|SHEET_NAME|SPREADSHEET_NAME|CSV_PATH)$")

    for key, value in os.environ.items():
        match = profile_pattern.match(key)
        if match:
            profile_name, var_type = match.groups()
            if profile_name not in profiles:
                profiles[profile_name] = {}
            
            key_map = {
                "GARMIN_EMAIL": "email",
                "GARMIN_PASSWORD": "password",
                "SHEET_ID": "sheet_id",
                "MONTHLY_SHEET_ID": "monthly_sheet_id",
                "DRIVE_FOLDER_ID": "drive_folder_id",
                "SHEET_NAME": "sheet_name",
                "SPREADSHEET_NAME": "spreadsheet_name",
                "CSV_PATH": "csv_path"
            }
            profiles[profile_name][key_map[var_type]] = value
    return profiles

@app.command()
def cli_sync(
    start_date: datetime = typer.Option(..., help="Start date YYYY-MM-DD."),
    end_date: datetime = typer.Option(..., help="End date YYYY-MM-DD."),
    profile: str = typer.Option("USER1", help="Profile from .env."),
    output_type: str = typer.Option("drive", help="'drive', 'sheets' or 'csv'.")
):
    """Run sync via CLI."""
    user_profiles = load_user_profiles()
    selected_profile_data = user_profiles.get(profile)

    if not selected_profile_data:
        logger.error(f"Profile '{profile}' not found.")
        sys.exit(1)

    asyncio.run(sync(
        email=selected_profile_data.get('email'),
        password=selected_profile_data.get('password'),
        start_date=start_date.date(),
        end_date=end_date.date(),
        output_type=output_type,
        profile_data=selected_profile_data,
        profile_name=profile
    ))

# (Rest of main, automated mode, and CLI setup remains unchanged)
def main():
    env_file_path = find_dotenv(usecwd=True)
    if env_file_path:
        load_dotenv(dotenv_path=env_file_path)
    
    if len(sys.argv) > 1:
        app()
    else:
        # Automated session defaults to drive
        asyncio.run(run_interactive_sync())

if __name__ == "__main__":
    main()
