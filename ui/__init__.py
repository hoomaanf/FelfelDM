# ui/__init__.py

from .main_window import MainWindow
from .dialogs import (
    AddDownloadDialog,
    SingleDownloadDialog,
    QueueSettingsDialog,
    SettingsDialog
)
from .table_model import DownloadTableModel
from .delegates import ProgressDelegate
from .proxy_dialog import ProxyDialog, QueueProxyDialog