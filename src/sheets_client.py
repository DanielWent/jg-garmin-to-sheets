# [Modify imports at the top]
from datetime import date, timedelta  # <--- Add timedelta here
# ... existing imports ...

class GoogleSheetsClient:
    # ... existing __init__ and other methods ...

    # [Add these new methods at the end of the class]
    def prune_old_data(self, days_to_keep: int = 365):
        """Removes rows older than the retention period from all managed sheets."""
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        logger.info(f"Pruning data older than {cutoff_date.isoformat()}...")

        # Configuration: List of (Tab Name, Date Column Index)
        # Note: Most tabs have Date in column A (index 0).
        # Activities tab has Date in column B (index 1) per ACTIVITY_HEADERS.
        sheet_configs = [
            (self.sleep_tab_name, 0),
            (self.stress_tab_name, 0),
            (self.body_tab_name, 0),
            (self.activity_sum_tab_name, 0),
            (self.activities_sheet_name, 1)
        ]

        for tab_name, date_col_idx in sheet_configs:
            self._prune_single_sheet(tab_name, date_col_idx, cutoff_date)

    def _prune_single_sheet(self, tab_name: str, date_col_idx: int, cutoff_date: date):
        try:
            # 1. Read all data from the sheet
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, 
                range=f"'{tab_name}'" 
            ).execute()
            
            rows = result.get('values', [])
            if not rows or len(rows) < 2:
                return # Empty or just headers, nothing to prune

            headers = rows[0]
            data_rows = rows[1:]
            
            kept_rows = []
            rows_removed = 0

            # 2. Filter rows locally
            for row in data_rows:
                # If row is too short to have a date, keep it to be safe (or drop it)
                if len(row) <= date_col_idx:
                    kept_rows.append(row)
                    continue
                
                date_str = row[date_col_idx]
                try:
                    # Parse YYYY-MM-DD
                    row_date = date.fromisoformat(date_str)
                    if row_date >= cutoff_date:
                        kept_rows.append(row)
                    else:
                        rows_removed += 1
                except ValueError:
                    # If date parsing fails, keep the row to prevent accidental data loss
                    kept_rows.append(row)

            # 3. If we removed data, clear and rewrite the sheet
            if rows_removed > 0:
                logger.info(f"Removing {rows_removed} old rows from '{tab_name}'.")
                
                # Clear existing content
                self.service.spreadsheets().values().clear(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab_name}'"
                ).execute()
                
                # Write back headers + kept rows
                body = {'values': [headers] + kept_rows}
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab_name}'!A1",
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()

        except Exception as e:
            logger.warning(f"Could not prune sheet '{tab_name}': {e}")
