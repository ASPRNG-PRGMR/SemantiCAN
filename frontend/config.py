API_BASE_URL = "http://127.0.0.1:5000"

SUMMARY_URL       = f"{API_BASE_URL}/api/summary"
ALERTS_URL        = f"{API_BASE_URL}/api/alerts"
HISTORY_URL       = f"{API_BASE_URL}/api/semantic-history"
RATE_URL          = f"{API_BASE_URL}/api/violation-rate"
TOP_ECUS_URL      = f"{API_BASE_URL}/api/top-anomalous-ecus"

REFRESH_INTERVAL_MS = 2000          # dashboard poll interval
DASHBOARD_TITLE     = "EV Semantic Integrity Monitor"
DASHBOARD_PORT      = 8050
