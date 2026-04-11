import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dash
import dash_bootstrap_components as dbc

from frontend.dashboard.layout    import build_layout
from frontend.dashboard.callbacks import register_callbacks
from frontend.config              import TITLE

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title=TITLE,
    assets_folder=str(Path(__file__).parent / "assets"),
    suppress_callback_exceptions=True,
)

app.layout = build_layout()
register_callbacks(app)


def start_dashboard(host: str = "127.0.0.1", port: int = 8050, debug: bool = False):
    app.run(host=host, port=port, debug=debug)
