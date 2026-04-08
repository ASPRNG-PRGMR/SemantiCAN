import dash
import dash_bootstrap_components as dbc

from frontend.dashboard.layout import build_layout
from frontend.dashboard import callbacks  # noqa: F401 — registers callbacks

from frontend.config import DASHBOARD_TITLE, DASHBOARD_PORT

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title=DASHBOARD_TITLE,
    update_title=None,
)

app.layout = build_layout()

if __name__ == "__main__":
    print(f"[*] Dashboard running on http://127.0.0.1:{DASHBOARD_PORT}")
    app.run(debug=False, port=DASHBOARD_PORT)
