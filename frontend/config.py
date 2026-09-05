API_BASE         = "http://127.0.0.1:5000"
REFRESH_INTERVAL = 2000   # milliseconds

TITLE    = "SemantiCAN"
SUBTITLE = "EV semantic integrity monitor"

# Vehicle under observation. The simulator models one vehicle, so this is a
# fixed label rather than a selector; it exists so the console reads like a
# tool pointed at something specific.
VEHICLE_LABEL = "SIM-EV-01"

# Individual traces drawn on the confidence chart. Everything else is
# collapsed into the normal envelope. /api/semantic-history returns every
# one of the ~120 ECUs across a 60s window; drawing them all is unreadable.
MAX_ANOMALOUS_TRACES = 5

# ECU chips shown in the advisory deck before the overflow modal.
MAX_DECK_CHIPS = 8

# Matches ANOMALY_THRESHOLD in backend/api_state.py. Kept here so the
# frontend never silently disagrees with the backend about what "anomalous"
# means; if the backend value moves, this needs to move with it.
ANOMALY_THRESHOLD = 70.0

# Feed liveness thresholds, in seconds since the newest telemetry frame.
FEED_STALE_AFTER = 6
FEED_DOWN_AFTER  = 20
