import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dash

from frontend.dashboard.layout    import build_layout
from frontend.dashboard.callbacks import register_callbacks
from frontend.config              import TITLE

# No Bootstrap theme. DARKLY sets its own body background, font stack, card
# shadows and border colours, all of which fight the soft-depth surfaces in
# assets/style.css and have to be fought back with !important. Dropping it
# means the stylesheet is the only thing styling the page.
app = dash.Dash(
    __name__,
    title=TITLE,
    assets_folder=str(Path(__file__).parent / "assets"),
    suppress_callback_exceptions=True,
    update_title=None,          # no "Updating..." flicker in the tab on every poll
)

app.layout = build_layout()
register_callbacks(app)


def start_dashboard(host: str = "127.0.0.1", port: int = 8050, debug: bool = False):
    app.run(host=host, port=port, debug=debug)
