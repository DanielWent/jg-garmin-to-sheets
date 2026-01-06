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

import typer
from dotenv import load_dotenv, find_dotenv

from src.garmin_client import GarminClient
from src.sheets_client import GoogleSheetsClient, GoogleAuthTokenRefreshError
from src.exceptions import MFARequiredException
from src.config import HEADERS, HEADER_TO_ATTRIBUTE_MAP, GarminMetrics

# Suppress noisy library warnings to clean up output
logging.getLogger('google_auth_oauthlib.flow').setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    
    # Retrieve the JSON string from the environment
    raw_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    
    if not raw_json:
        logger.error("CRITICAL: 'credentials/client_secret.json' is missing and 'GOOGLE_SHEETS_CREDENTIALS' env var is empty.")
        logger.error("Please ensure you have added the contents of client_secret.json to your GitHub Secrets.")
        sys.exit(1)

    try:
        # Ensure the directory exists
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Verify it's valid JSON before writing
        json_content = json.loads(raw_json)
        
        with open(creds_path, 'w') as f:
            json.dump(json_content, f, indent=2)
            
        logger.info(f"Successfully created {creds_path} from environment secret.")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GOOGLE_SHEETS_CREDENTIALS: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to write credentials file: {e}")
        sys.exit(1)

async def sync(email: str, password: str, start_date: date, end_date: date, output_type: str, profile_data: dict, profile_name: str = ""):
    """Core sync logic. Fetches data and writes to the specified output."""
    try:
        garmin_client = GarminClient(email, password)
        await garmin_client.authenticate()

    except MFARequiredException as e:
        logger.error("MFA required but cannot be entered in headless mode.")
        sys.exit(1)
        
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

    if output_type == 'sheets':
        # >>> CRITICAL FIX: Ensure the file exists before the client looks for it <<<
        ensure_credentials_file_exists()

        sheets_id = profile_data.get('sheet_id')
        sheet_name = profile_data.get('sheet_name', 'Daily Summaries')
        display_name = profile_data.get('spreadsheet_name', f"ID: {sheets_id}")

        logger.info(f"Initializing Google Sheets client for spreadsheet: '{display_name}'")
        try:
            sheets_client = GoogleSheetsClient(
                credentials_path='credentials/client_secret.json',
                spreadsheet_id=sheets_id,
                sheet_name=sheet_name
            )
            sheets_client.update_metrics(metrics_to_write)
            
            # --- NEW: Prune old data (retention: 1 year) ---
            sheets_client.prune_old_data(days_to_keep=365)
            # -----------------------------------------------

            logger.info("Google Sheets sync completed successfully!")
        
        except GoogleAuthTokenRefreshError as auth_error:
            logger.error(f"Google authentication error: {auth_error}")
            sys.exit(1)
        
        except Exception as sheet_error:
            logger.error(f"An error occurred during Google Sheets operation: {str(sheet_error)}", exc_info=True)
            sys.exit(1)

    elif output_type == 'csv':
        if 'csv_path' in profile_data and profile_data['csv_path']:
            csv_path = Path(profile_data['csv_path'])
        else:
            output_dir = Path("./output")
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / f"garmingo_{profile_name if profile_name else 'output'}.csv"
        
        logger.info(f"Writing metrics to CSV file: {csv_path}")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if f.tell() == 0: 
                writer.writerow(HEADERS)
            for metric in metrics_to_write:
                writer.writerow([getattr(metric, HEADER_TO_ATTRIBUTE_MAP.get(h, ""), "") for h in HEADERS])
        logger.info("CSV file sync completed successfully!")

def load_user_profiles():
    """Parses .env for user profiles."""
    profiles = {}
    profile_pattern = re.compile(r"^(USER\d+)_(GARMIN_EMAIL|GARMIN_PASSWORD|SHEET_ID|SHEET_NAME|SPREADSHEET_NAME|CSV_PATH)$")

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
                "SHEET_NAME": "sheet_name",
                "SPREADSHEET_NAME": "spreadsheet_name",
                "CSV_PATH": "csv_path"
            }
            profiles[profile_name][key_map[var_type]] = value
    return profiles

@app.command()
def cli_sync(
    start_date: datetime = typer.Option(..., help="Start date in YYYY-MM-DD format."),
    end_date: datetime = typer.Option(..., help="End date in YYYY-MM-DD format."),
    profile: str = typer.Option("USER1", help="The user profile from .env to use (e.g., USER1)."),
    output_type: str = typer.Option("sheets", help="Output type: 'sheets' or 'csv'.")
):
    """Run the Garmin sync from the command line."""
    user_profiles = load_user_profiles()
    selected_profile_data = user_profiles.get(profile)

    if not selected_profile_data:
        logger.error(f"Profile '{profile}' not found in .env file.")
        sys.exit(1)

    email = selected_profile_data.get('email')
    password = selected_profile_data.get('password')

    if not email or not password:
        logger.error(f"Email or password not configured for profile '{profile}'.")
        sys.exit(1)

    asyncio.run(sync(
        email=email,
        password=password,
        start_date=start_date.date(),
        end_date=end_date.date(),
        output_type=output_type,
        profile_data=selected_profile_data,
        profile_name=profile
    ))

async def run_interactive_sync():
    """Automated session logic for GitHub Actions."""
    logger.info("Starting automated sync setup...")

    output_type = "sheets"
    logger.info(f"Selected output type: {output_type}")

    user_profiles = load_user_profiles()
    if not user_profiles:
        logger.error("No user profiles found. Check your secrets.")
        sys.exit(1)
    
    profile_names = list(user_profiles.keys())
    selected_profile_name = profile_names[0]
    selected_profile_data = user_profiles[selected_profile_name]
    logger.info(f"Using profile: {selected_profile_name}")

# ---------------------------------------------------------
    # AUTOMATION CONFIGURATION: DATE RANGE
    # ---------------------------------------------------------
    # Set to False for daily sync (now configured for a rolling 7-day window)
    FORCE_BACKFILL = False

    if FORCE_BACKFILL:
        start_date = date(2023, 8, 28)
        end_date = date.today()
    else:
        # Rolling sync: Fetch the last 7 days INCLUDING today
        # Today = Day 0. Today minus 6 days = 7 days total.
        end_date = date.today()
        start_date = end_date - timedelta(days=6)

    logger.info(f"Date range selected: {start_date} to {end_date}")
    # ---------------------------------------------------------

    await sync(
        email=selected_profile_data.get('email'),
        password=selected_profile_data.get('password'),
        start_date=start_date,
        end_date=end_date,
        output_type=output_type,
        profile_data=selected_profile_data,
        profile_name=selected_profile_name
    )

def main():
    env_file_path = find_dotenv(usecwd=True)
    if env_file_path:
        load_dotenv(dotenv_path=env_file_path)
    
    try:
        if len(sys.argv) > 1:
            app()
        else:
            print("\nWelcome to GarminGo (Automated Mode)!")
            asyncio.run(run_interactive_sync())
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
