"""FocusLog：离线优先的番茄钟、统计与桌面应用。"""

from .cli import main
from .gui import launch_gui

__version__ = "0.1.0"

__all__ = ["main", "launch_gui", "__version__"]
