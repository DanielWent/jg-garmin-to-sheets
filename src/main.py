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

def aggregate_monthly_metrics(metrics: list[GarminMetrics], month_date: date) -> Optional[GarminMetrics]:
    """
    Takes a list of daily GarminMetrics and returns a single GarminMetrics object
    containing the average of all numeric fields.
    """
    if not metrics:
        return None

    # Helper to calculate average of a specific attribute, ignoring None values
    def get_avg(attr_name):
        values = [getattr(m, attr_name) for m in metrics if getattr(m, attr_name) is not None]
        return round(mean(values), 2) if values else None

    # Helper to cast average to int
    def get_avg_int(attr_name):
        val = get_avg(attr_name)
        return int(val) if val is not None else None

    # --- Helper to calculate average TIME strings (HH:MM) ---
    def get_avg_time(attr_name, is_start_time=False):
        minutes_list = []
        for m in metrics:
            val = getattr(m, attr_name)
            if val and isinstance(val, str) and ":" in val:
                try:
                    hh, mm = map(int, val.split(':'))
                    total_min = hh * 60 + mm
                    
                    # Logic for sleep start crossing midnight:
                    if is_start_time and total_min < 12 * 60:
                        total_min += 24 * 60
                        
                    minutes_list.append(total_min)
                except ValueError:
                    continue

        if not minutes_list:
            return None

        avg_min = mean(minutes_list)
        
        # Normalize back to 0-24h range if we added 24h
        if avg_min >= 24 * 60:
            avg_min -= 24 * 60
            
        # Convert back to HH:MM
        avg_hh = int(avg_min // 60)
        avg_mm = int(round(avg_min % 60))
        
        # Handle rounding edge case (e.g. 23:59.9 -> 23:60 -> 24:00)
        if avg_mm == 60:
            avg_hh += 1
            avg_mm = 0
        if avg_hh >= 24:
            avg_hh -= 24
            
        return f"{avg_hh:02d}:{avg_mm:02d}"

    return GarminMetrics(
        date=month_date,  # This will be the 1st of the month
        
        # Averages
        sleep_score=get_avg("sleep_score"),
        sleep_length=get_avg("sleep_length"),
        
        # --- Time Averages ---
        sleep_start_time=get_avg_time("sleep_start_time", is_start_time=True),
        sleep_end_time=get_avg_time("sleep_end_time", is_start_time=False),
        # --------------------------

        sleep_need=get_avg_int("sleep_need"),
        sleep_efficiency=get_avg("sleep_efficiency"),
        sleep_deep=get_avg("sleep_deep"),
        sleep_light=get_avg("sleep_light"),
        sleep_rem=get_avg("sleep_rem"),
        sleep_awake=get_avg("sleep_awake"),
        overnight_respiration=get_avg("overnight_respiration"),
        overnight_pulse_ox=get_avg("overnight_pulse_ox"),
        weight=get_avg("weight"),
        bmi=get_avg("bmi"),
        body_fat=get_avg("body_fat"),
        blood_pressure_systolic=get_avg_int("blood_pressure_systolic"),
        blood_pressure_diastolic=get_avg_int("blood_pressure_diastolic"),
        resting_heart_rate=get_avg_int("resting_heart_rate"),
        average_stress=get_avg_int("average_stress"),
        rest_stress_duration=get_avg_int("rest_stress_duration"),
        low_stress_duration=get_avg_int("low_stress_duration"),
        medium_stress_duration=get_avg_int("medium_stress_duration"),
        high_stress_duration=get_avg_int("high_stress_duration"),
        overnight_hrv=get_avg_int("overnight_hrv"),
        vo2max_running=get_avg("vo2max_running"),
        vo2max_cycling=get_avg("vo2max_cycling"),
        
        # --- NEW: Lactate Threshold Averages ---
        lactate_threshold_bpm=get_avg_int("lactate_threshold_bpm"),
        lactate_threshold_pace=get_avg_time("lactate_threshold_pace"),
        # ---------------------------------------

        active_calories=get_avg_int("active_calories"),
        resting_calories=get_avg_int("resting_calories"),
        intensity_minutes=get_avg_int("intensity_minutes"),
        steps=get_avg_int("steps"),
        floors_climbed=get_avg("floors_climbed"),

        # Non-numeric placeholders
        training_status="Monthly Avg",
        hrv_status="Monthly Avg",
        activities=[] 
    )

def get_month_dates(year: int, month: int):
    """Returns the start and end date objects for a specific month."""
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    return start_date, end_date

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
            
            # --- Prune old data (retention: 1 year) ---
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
    # UPDATED REGEX to include MONTHLY_SHEET_ID
    profile_pattern = re.compile(r"^(USER\d+)_(GARMIN_EMAIL|GARMIN_PASSWORD|SHEET_ID|MONTHLY_SHEET_ID|SHEET_NAME|SPREADSHEET_NAME|CSV_PATH)$")

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

@app.command()
def cli_monthly_sync(
    profile: str = typer.Option("USER1", help="The user profile from .env to use."),
    start_month: str = typer.Option(None, help="YYYY-MM format. Start of historical range (inclusive)."),
    end_month: str = typer.Option(None, help="YYYY-MM format. End of historical range (inclusive).")
):
    """
    Calculates monthly averages.
    If no dates provided: Defaults to the PREVIOUS month (standard automation mode).
    If dates provided: Backfills that specific range (e.g., 2023-09 to 2024-01).
    """
    user_profiles = load_user_profiles()
    selected_profile_data = user_profiles.get(profile)

    if not selected_profile_data:
        logger.error(f"Profile '{profile}' not found in .env file.")
        sys.exit(1)

    # --- 1. Determine the Range of Months to Process ---
    months_to_process = []
    
    if start_month:
        # Historical / Manual Mode
        try:
            s_year, s_month = map(int, start_month.split('-'))
            
            if end_month:
                e_year, e_month = map(int, end_month.split('-'))
            else:
                # If only start provided, just do that one month
                e_year, e_month = s_year, s_month

            # Loop from start to end
            curr_y, curr_m = s_year, s_month
            while (curr_y < e_year) or (curr_y == e_year and curr_m <= e_month):
                months_to_process.append((curr_y, curr_m))
                
                # Increment month
                curr_m += 1
                if curr_m > 12:
                    curr_m = 1
                    curr_y += 1
        except ValueError:
            logger.error("Invalid date format. Please use YYYY-MM (e.g., 2023-09)")
            sys.exit(1)
    else:
        # Default / Automated Mode: Previous Month
        today = date.today()
        first_current = today.replace(day=1)
        prev_month_date = first_current - timedelta(days=1)
        months_to_process.append((prev_month_date.year, prev_month_date.month))

    logger.info(f"Processing {len(months_to_process)} month(s)...")

    # --- 2. Authenticate Once ---
    email = selected_profile_data.get('email')
    password = selected_profile_data.get('password')
    garmin_client = GarminClient(email, password)
    try:
        asyncio.run(garmin_client.authenticate())
    except Exception as e:
        logger.error(f"Auth failed: {e}")
        sys.exit(1)

    metrics_buffer = []

    # --- 3. Loop Through Each Month ---
    for (year, month) in months_to_process:
        m_start, m_end = get_month_dates(year, month)
        logger.info(f"Fetching data for {m_start.strftime('%B %Y')} ({m_start} to {m_end})...")
        
        daily_metrics_list = []
        current_date = m_start
        
        # Fetch daily data for this specific month
        while current_date <= m_end:
            # We use print here for a simple progress indicator on the same line
            print(f"  - Fetching {current_date.isoformat()}...", end='\r')
            try:
                # Use standard asyncio run for the single call
                daily_metrics = asyncio.run(garmin_client.get_metrics(current_date))
                daily_metrics_list.append(daily_metrics)
            except Exception as e:
                logger.error(f"\nFailed to fetch {current_date}: {e}")
            
            current_date += timedelta(days=1)
        
        print("") # Clear the progress line
        
        # Aggregate
        monthly_avg = aggregate_monthly_metrics(daily_metrics_list, m_start)
        if monthly_avg:
            metrics_buffer.append(monthly_avg)

    if not metrics_buffer:
        logger.warning("No metrics generated.")
        return

    # --- 4. Write to Google Sheets ---
    monthly_sheet_id = selected_profile_data.get('monthly_sheet_id')
    if not monthly_sheet_id:
        logger.error(f"MONTHLY_SHEET_ID not set for {profile} in .env")
        sys.exit(1)

    ensure_credentials_file_exists()
    
    try:
        logger.info(f"Writing {len(metrics_buffer)} monthly rows to Sheet ID: {monthly_sheet_id}")
        sheets_client = GoogleSheetsClient(
            credentials_path='credentials/client_secret.json',
            spreadsheet_id=monthly_sheet_id,
            sheet_name='Monthly Averages'
        )
        # Update metrics handles lists, so we pass the whole buffer
        sheets_client.update_metrics(metrics_buffer)
        logger.info("Monthly sync completed successfully!")
        
    except Exception as e:
        logger.error(f"Error writing to Google Sheets: {e}", exc_info=True)
        sys.exit(1)

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
    FORCE_BACKFILL = True

    if FORCE_BACKFILL:
        start_date = date(2025, 1, 5)
        end_date = date(2025, 1, 10)
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
