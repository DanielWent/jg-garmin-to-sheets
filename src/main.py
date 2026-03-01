import os
import sys
import csv
import logging
import re
import asyncio
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict

import typer
from dotenv import load_dotenv, find_dotenv

from src.garmin_client import GarminClient
from src.drive_client import GoogleDriveClient
from src.exceptions import MFARequiredException
from src.config import (
    GENERAL_SUMMARY_HEADERS,
    HEADER_TO_ATTRIBUTE_MAP, 
    GarminMetrics
)

logging.getLogger("hpack").setLevel(logging.WARNING)

log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer()

def ensure_credentials_file_exists():
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

def calculate_age(dob_str: Optional[str]) -> Optional[int]:
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        logger.warning(f"Invalid DOB format: {dob_str}")
        return None

async def sync(email: str, password: str, start_date: date, end_date: date, output_type: str, profile_data: dict, profile_name: str = ""):
    try:
        garmin_client = GarminClient(email, password, profile_name=profile_name)
        await garmin_client.authenticate()
    except Exception as e:
        logger.error(f"Authentication failed for {profile_name}: {e}")
        return

    logger.info(f"[{profile_name}] Fetching metrics from {start_date.isoformat()} to {end_date.isoformat()}...")
    metrics_to_write = []
    current_date = start_date
    
    manual_name = profile_data.get('manual_name')
    manual_gender = profile_data.get('manual_gender')
    manual_age = calculate_age(profile_data.get('manual_dob'))
    
    file_prefix = ""
    if profile_name == "USER1":
        file_prefix = "drw_"
    elif profile_name == "USER2":
        file_prefix = "aflw_"

    fields_to_validate = [
        'average_stress', 'rest_stress_duration', 'low_stress_duration', 
        'medium_stress_duration', 'high_stress_duration',
        'steps', 'floors_climbed', 'total_calories', 'intensity_minutes',
        'body_battery_min'
    ]

    while current_date <= end_date:
        logger.info(f"[{profile_name}] Fetching metrics for {current_date.isoformat()}")
        daily_metrics = await garmin_client.get_metrics(current_date)
        
        if manual_name:
            daily_metrics.user_name = manual_name
        if manual_gender:
            daily_metrics.user_gender = manual_gender
        if manual_age:
            daily_metrics.user_age = manual_age
        
        if profile_name == "USER1" and current_date >= date(2026, 1, 25):
            if daily_metrics.body_fat is not None:
                original_bf = daily_metrics.body_fat
                daily_metrics.body_fat = original_bf + 3.0
                logger.info(f"[{current_date}] Adjusted Body Fat for {profile_name}: {original_bf}% -> {daily_metrics.body_fat}%")
        
        if current_date >= date.today():
            for f in fields_to_validate:
                setattr(daily_metrics, f, "PENDING")
        else:
            for f in fields_to_validate:
                val = getattr(daily_metrics, f)
                if val is None:
                    setattr(daily_metrics, f, "NA")

        metrics_to_write.append(daily_metrics)
        current_date += timedelta(days=1)

    if not metrics_to_write:
        logger.warning(f"[{profile_name}] No metrics fetched. Nothing to write.")
        return

    # === GOOGLE DRIVE (CSV) SYNC ===
    if output_type == 'drive':
        folder_id = profile_data.get('drive_folder_id')
        if not folder_id:
            logger.error(f"DRIVE_FOLDER_ID not set for {profile_name}.")
            return

        ensure_credentials_file_exists()
        
        try:
            drive_client = GoogleDriveClient('credentials/client_secret.json', folder_id)
            drive_client.update_csv(f"{file_prefix}garmin_data.csv", metrics_to_write, GENERAL_SUMMARY_HEADERS)
            logger.info(f"[{profile_name}] Google Drive CSV sync completed successfully!")
        except Exception as e:
            logger.error(f"[{profile_name}] Drive Sync Failed: {e}", exc_info=True)
            return

    # === LOCAL CSV SYNC ===
    elif output_type == 'csv':
        output_dir = Path("./output")
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{file_prefix}garmin_data.csv"
        
        logger.info(f"Writing metrics to local CSV: {csv_path}")
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists or f.tell() == 0: 
                writer.writerow(GENERAL_SUMMARY_HEADERS)
            for metric in metrics_to_write:
                writer.writerow([getattr(metric, HEADER_TO_ATTRIBUTE_MAP.get(h, ""), "") for h in GENERAL_SUMMARY_HEADERS])
        logger.info(f"[{profile_name}] Local CSV sync completed.")

def load_user_profiles():
    profiles = {}
    profile_pattern = re.compile(r"^(USER\d+)_(GARMIN_EMAIL|GARMIN_PASSWORD|DRIVE_FOLDER_ID|NAME|DOB|GENDER)$")

    for key, value in os.environ.items():
        match = profile_pattern.match(key)
        if match:
            profile_name, var_type = match.groups()
            if profile_name not in profiles:
                profiles[profile_name] = {}
            
            key_map = {
                "GARMIN_EMAIL": "email",
                "GARMIN_PASSWORD": "password",
                "DRIVE_FOLDER_ID": "drive_folder_id",
                "NAME": "manual_name",
                "DOB": "manual_dob",
                "GENDER": "manual_gender"
            }
            if var_type in key_map:
                profiles[profile_name][key_map[var_type]] = value
    return profiles

async def interactive_mode():
    print("\n" + "="*60)
    print("Welcome to GarminGo Interactive Mode!")
    print("="*60 + "\n")

    user_profiles = load_user_profiles()
    if not user_profiles:
        print("No user profiles found in .env file.")
        return

    print("Select Output Type:")
    print("1. Local CSV")
    print("2. Google Drive")
    out_choice = input("Enter choice (1 or 2): ").strip()
    output_type = 'drive' if out_choice == '2' else 'csv'

    print("\nAvailable User Profiles:")
    profile_keys = sorted(user_profiles.keys())
    for i, key in enumerate(profile_keys):
        email_display = user_profiles[key].get('email', 'Unknown')
        print(f"{i + 1}. {key} ({email_display})")
    
    try:
        p_idx = int(input(f"Select profile number (1-{len(profile_keys)}): ").strip()) - 1
        if 0 <= p_idx < len(profile_keys):
            selected_profile_name = profile_keys[p_idx]
            selected_profile_data = user_profiles[selected_profile_name]
        else:
            print("Invalid selection.")
            return
    except ValueError:
        print("Invalid input.")
        return

    print(f"\nSelected Profile: {selected_profile_name}")
    start_str = input("Enter start date (YYYY-MM-DD): ").strip()
    end_str = input("Enter end date (YYYY-MM-DD): ").strip()

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Use YYYY-MM-DD.")
        return

    await sync(
        email=selected_profile_data['email'],
        password=selected_profile_data['password'],
        start_date=start_date,
        end_date=end_date,
        output_type=output_type,
        profile_data=selected_profile_data,
        profile_name=selected_profile_name
    )

async def run_automated_sync():
    user_profiles = load_user_profiles()
    if not user_profiles:
        logger.error("No user profiles found in environment variables.")
        return

    today = date.today()
    yesterday = today - timedelta(days=1)
    
    logger.info(f"--- Starting Daily Sync for {len(user_profiles)} Profiles (Target: {yesterday} to {today}) ---")

    for profile_name, profile_data in user_profiles.items():
        logger.info(f"Processing {profile_name}...")
        try:
            await sync(
                email=profile_data['email'],
                password=profile_data['password'],
                start_date=yesterday,
                end_date=today,
                output_type='drive', 
                profile_data=profile_data,
                profile_name=profile_name
            )
        except Exception as e:
            logger.error(f"Failed to sync {profile_name}: {e}")

@app.command(name="cli-sync")
def cli_sync(
    start_date: datetime = typer.Option(..., help="Start date YYYY-MM-DD."),
    end_date: datetime = typer.Option(..., help="End date YYYY-MM-DD."),
    profile: str = typer.Option("USER1", help="Profile from .env."),
    output_type: str = typer.Option("drive", help="'drive' or 'csv'.")
):
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

@app.command(name="automated")
def automated_sync_cmd():
    asyncio.run(run_automated_sync())

def main():
    env_file_path = find_dotenv(usecwd=True)
    if env_file_path:
        load_dotenv(dotenv_path=env_file_path)
    
    if len(sys.argv) > 1:
        app()
    else:
        if os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true":
            logger.info("Automated environment detected. Running batch sync for ALL users...")
            asyncio.run(run_automated_sync())
        else:
            try:
                asyncio.run(interactive_mode())
            except KeyboardInterrupt:
                print("\nOperation cancelled.")

if __name__ == "__main__":
    main()
