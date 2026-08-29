"""Main entrypoint for Garmin data sync and export workflows."""

from datetime import date, datetime, timedelta
import logging
import os
import sys
from typing import List, Optional
import pandas as pd

from src.config import Config
from src.garmin_client import GarminClient
from src.parser import GarminParser
from src.sheets_client import SheetsClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DAILY_METRICS_COLUMNS = [
    "Date",
    "Daily Steps",
    "Daily Step Goal",
    "Daily Total Distance (m)",
    "Daily Total Calories",
    "Daily BMR Calories",
    "Daily Resting Heart Rate",
    "Daily Min Heart Rate",
    "Daily Max Heart Rate",
    "Daily Average Stress Level",
    "Daily Max Stress Level",
    "Daily Body Battery Lowest",
    "Daily Body Battery Highest",
    "Daily Body Battery Most Recent",
    "Daily Sleep Duration (s)",
    "Daily Sleep Score",
    "Daily Floors Ascended",
    "Daily Moderate Intensity Minutes",
    "Daily Vigorous Intensity Minutes",
    "Daily Active Calories",
]


def fetch_daily_dataframe(
    garmin_client: GarminClient, start_date: date, end_date: date
) -> pd.DataFrame:
    """Fetch and parse daily metrics for a date range into a DataFrame."""
    records: List[dict] = []
    curr = start_date

    while curr <= end_date:
        date_str = curr.isoformat()
        logger.info(f"Retrieving daily Garmin metrics for {date_str}")
        try:
            summary = garmin_client.get_user_summary(date_str)
            sleep_data = garmin_client.get_sleep_data(date_str)
            stress_data = garmin_client.get_stress_data(date_str)
            body_battery = garmin_client.get_body_battery(date_str)

            row = GarminParser.parse_daily_summary(
                summary=summary,
                sleep_data=sleep_data,
                stress_data=stress_data,
                body_battery_data=body_battery,
            )
            if row and row.get("Date"):
                records.append(row)
        except Exception as e:
            logger.warning(f"Skipping date {date_str} due to error: {e}")

        curr += timedelta(days=1)

    df = pd.DataFrame(records)
    if not df.empty:
        for col in DAILY_METRICS_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[[col for col in DAILY_METRICS_COLUMNS if col in df.columns]]
        df.sort_values(by="Date", ascending=True, inplace=True)

    return df


def sync_daily_data(
    config: Config, start_date: Optional[date] = None, end_date: Optional[date] = None
) -> None:
    """Sync daily data to configured CSV and/or Google Sheets destinations."""
    garmin_client = GarminClient(
        email=config.GARMIN_EMAIL,
        password=config.GARMIN_PASSWORD,
        token_store=config.GARMIN_TOKEN_STORE,
    )
    garmin_client.login()

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=config.SYNC_DAYS_LOOKBACK or 7)

    df = fetch_daily_dataframe(garmin_client, start_date, end_date)

    if df.empty:
        logger.warning("No daily records fetched.")
        return

    output_dir = getattr(config, "OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "garmin_data.csv")

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        try:
            existing_df = pd.read_csv(csv_path)
            combined = pd.concat([existing_df, df], ignore_index=True)
            combined.drop_duplicates(subset=["Date"], keep="last", inplace=True)
            for col in DAILY_METRICS_COLUMNS:
                if col not in combined.columns:
                    combined[col] = None
            combined = combined[[col for col in DAILY_METRICS_COLUMNS if col in combined.columns]]
            combined.sort_values(by="Date", ascending=True, inplace=True)
            combined.to_csv(csv_path, index=False)
            logger.info(f"Updated {csv_path} with {len(combined)} records.")
        except Exception as e:
            logger.error(f"Error merging with existing {csv_path}: {e}")
            df.to_csv(csv_path, index=False)
    else:
        df.to_csv(csv_path, index=False)
        logger.info(f"Created {csv_path} with {len(df)} records.")

    if getattr(config, "SPREADSHEET_ID", None):
        sheets_client = SheetsClient(
            credentials_path=config.GOOGLE_CREDENTIALS_PATH,
            spreadsheet_id=config.SPREADSHEET_ID,
        )
        sheets_client.sync_dataframe(df, sheet_name=config.DAILY_SHEET_NAME or "Daily")


def main() -> None:
    config = Config()
    sync_daily_data(config)


if __name__ == "__main__":
    main()
