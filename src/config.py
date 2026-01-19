from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Any, Dict

# ... (Previous imports and logging config)

# Updated Headers
STRESS_HEADERS = [
    "Date", "Stress Level", "Rest Stress Duration", "Low Stress Duration", 
    "Medium Stress Duration", "High Stress Duration", 
    "Body Battery Max", "Body Battery Min"  # <--- NEW
]

# ... (Body Comp and Sleep Headers remain unchanged) ...

ACTIVITIES_HEADERS = [
    "Activity ID", "Date", "Time", "Type", "Name", "Distance (km)", "Duration (min)",
    "Avg Pace (min/km)", "Avg HR", "Max HR", "Calories", 
    "Avg Cadence (spm)", "Elevation Gain (m)", "Aerobic TE", "Anaerobic TE",
    "Avg Power", "GCT (ms)", "Vert Osc (cm)", "Stride Len (m)",  # <--- NEW METRICS
    "Zone 1 (min)", "Zone 2 (min)", "Zone 3 (min)", "Zone 4 (min)", "Zone 5 (min)" # <--- NEW ZONES
]

# Map headers to GarminMetrics attributes or dictionary keys
# This map helps the Sheets client know where to pull data from
HEADER_TO_ATTRIBUTE_MAP = {
    # ... (Existing mappings) ...
    "Body Battery Max": "body_battery_max",
    "Body Battery Min": "body_battery_min",
    # Note: Activities are usually a list of dicts, so they are handled dynamically, 
    # but we define them here for completeness if needed by your CSV logic
}

@dataclass
class GarminMetrics:
    date: date
    # ... (Existing fields) ...
    
    # Body Battery
    body_battery_max: Optional[int] = None
    body_battery_min: Optional[int] = None
    
    # ... (Existing fields) ...
    
    # Activities is a list of dicts, so the new fields will be keys inside these dicts
    activities: List[Dict[str, Any]] = field(default_factory=list)

# ... (Rest of the file)
