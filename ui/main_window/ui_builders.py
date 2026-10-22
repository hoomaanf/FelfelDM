"""Building the widgets: sidebar, toolbar, menus, status bar, tray, shortcuts."""

import os

from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QSystemTrayIcon,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ui.delegates import CategoryDelegate, ProgressDelegate
from ui.table_model import DownloadTableModel
from utils.helpers import get_icon, get_resource_path
from utils.style import make_primary


class UIBuilderMixin:
    """Building the widgets: sidebar, toolbar, menus, status bar, tray, shortcuts."""

    def _detect_theme(self, theme_setting: str) -> bool:
        if theme_setting == "light":
            return False
        if theme_setting == "dark":
            return True

        from utils.style import detect_system_theme

        return detect_system_theme()

    def _resolve_theme_icon(self, candidates: list):
        """Return the first QIcon from `candidates` that resolves in the
        current theme, or None if none of them exist. Used to avoid relying
        on a single icon name that may be missing in some icon themes."""
        for name in candidates:
            icon = get_icon(name)
            if icon is not None and not icon.isNull():
                return icon
        return None

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("splitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        sidebar = self._build_sidebar()
        main_area = self._build_main_area()

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([260, 840])

        root.addWidget(splitter)

        self._build_menubar()

        self._refresh_queue_list()
        self._update_queue_buttons()

        self._update_queue_status()

    def _build_sidebar(self) -> QWidget:
        """Sidebar layout (top to bottom):

        header (title + New)  →  queue list  →  tool row for the selected queue
        →  "queue card" (state, limits, schedule, Start / Pause)  →  connection footer
        """
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(230)
        sidebar.setMaximumWidth(360)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(14, 16, 14, 12)
        sb_lay.setSpacing(10)

        # ── Header: title + New queue ──────────────────────────────
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(2, 0, 0, 0)
        header_lay.setSpacing(8)
        queues_title = QLabel("Queues")
        queues_title.setObjectName("section_title")
        header_lay.addWidget(queues_title)
        header_lay.addStretch()
        new_queue_btn = QPushButton(get_icon("list-add"), "", clicked=self._add_queue)
        new_queue_btn.setFixedSize(36, 36)
        new_queue_btn.setToolTip("Create a new queue")
        new_queue_btn.setProperty("compact", True)
        make_primary(new_queue_btn)
        header_lay.addWidget(new_queue_btn)
        sb_lay.addLayout(header_lay)

        # ── Queue list ─────────────────────────────────────────────
        self.queue_list = QListWidget()
        self.queue_list.setFrameShape(QFrame.Shape.NoFrame)
        self.queue_list.setSpacing(2)
        self.queue_list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.queue_list.currentRowChanged.connect(self._on_queue_changed)
        sb_lay.addWidget(self.queue_list, 1)

        # ── Tools for the selected queue (icon buttons) ────────────
        tools_lay = QHBoxLayout()
        tools_lay.setSpacing(6)

        def tool_button(icon_name, fallback_text, tooltip, slot):
            btn = QPushButton()
            icon = get_icon(icon_name)
            if icon.isNull():
                btn.setText(fallback_text)
            else:
                btn.setIcon(icon)
            btn.setToolTip(tooltip)
            btn.setProperty("tool", True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(slot)
            tools_lay.addWidget(btn)
            return btn

        self.move_up_btn = tool_button(
            "go-up", "↑", "Move queue up", self._move_queue_up
        )
        self.move_down_btn = tool_button(
            "go-down", "↓", "Move queue down", self._move_queue_down
        )
        tools_lay.addSpacing(6)
        tool_button("configure", "⚙", "Queue settings", self._edit_queue)
        delete_queue_btn = tool_button(
            "list-remove", "✕", "Delete queue", self._delete_queue
        )
        delete_queue_btn.setProperty("variant", "danger")
        sb_lay.addLayout(tools_lay)

        # ── Queue card: state + limits + schedule + Start/Pause ────
        card = QFrame()
        card.setObjectName("queue_card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 12, 14, 14)
        card_lay.setSpacing(6)

        # Status row: icon + text
        self.queue_status_row = QWidget()
        qsr_lay = QHBoxLayout(self.queue_status_row)
        qsr_lay.setContentsMargins(0, 0, 0, 0)
        qsr_lay.setSpacing(6)

        self.queue_status_icon = QLabel()
        self.queue_status_icon.setFixedSize(18, 18)
        self.queue_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qsr_lay.addWidget(self.queue_status_icon)

        self.queue_status_lbl = QLabel("Paused")
        self.queue_status_lbl.setStyleSheet(
            "color: #f39c12; font-weight: bold; font-size: 14px;"
        )
        qsr_lay.addWidget(self.queue_status_lbl)
        qsr_lay.addStretch()

        card_lay.addWidget(self.queue_status_row)

        self.speed_limit_lbl = QLabel("")
        self.speed_limit_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
        card_lay.addWidget(self.speed_limit_lbl)

        # Schedule row: icon + text
        self.schedule_status_row = QWidget()
        ssr_lay = QHBoxLayout(self.schedule_status_row)
        ssr_lay.setContentsMargins(0, 0, 0, 0)
        ssr_lay.setSpacing(6)

        self.schedule_status_icon = QLabel()
        self.schedule_status_icon.setFixedSize(14, 14)
        self.schedule_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ssr_lay.addWidget(self.schedule_status_icon, 0, Qt.AlignmentFlag.AlignTop)

        self.schedule_status_lbl = QLabel("")
        self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
        self.schedule_status_lbl.setWordWrap(True)
        ssr_lay.addWidget(self.schedule_status_lbl, 1)

        card_lay.addWidget(self.schedule_status_row)

        card_lay.addSpacing(4)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.start_queue_btn = QPushButton(get_icon("media-playback-start"), "Start")
        self.start_queue_btn.setObjectName("start_btn")
        self.start_queue_btn.setProperty("variant", "success")
        self.start_queue_btn.setMinimumHeight(36)
        self.start_queue_btn.clicked.connect(self._start_current_queue)
        btn_layout.addWidget(self.start_queue_btn)

        self.pause_queue_btn = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.pause_queue_btn.setObjectName("pause_btn")
        self.pause_queue_btn.setProperty("variant", "warning")
        self.pause_queue_btn.setMinimumHeight(36)
        self.pause_queue_btn.clicked.connect(self._pause_current_queue)
        btn_layout.addWidget(self.pause_queue_btn)
        card_lay.addLayout(btn_layout)
        sb_lay.addWidget(card)

        # ── Footer: connection status ──────────────────────────────
        separator = QFrame()
        separator.setObjectName("sidebar_separator")
        separator.setFixedHeight(1)
        sb_lay.addWidget(separator)

        self.status_lbl = QLabel("● Disconnected")
        self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.status_lbl.setContentsMargins(2, 0, 0, 0)
        sb_lay.addWidget(self.status_lbl)
        return sidebar

    def _build_main_area(self) -> QWidget:
        main_area = QWidget()
        ma_lay = QVBoxLayout(main_area)
        ma_lay.setContentsMargins(0, 0, 0, 0)
        ma_lay.setSpacing(0)

        toolbar = self._build_toolbar()
        ma_lay.addWidget(toolbar)

        self.table = QTableView()
        self.table.doubleClicked.connect(self._on_table_double_click)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.model = DownloadTableModel()
        self.progress_delegate = ProgressDelegate(self)
        self.table.setItemDelegateForColumn(2, self.progress_delegate)

        self.category_delegate = CategoryDelegate(self)
        self.table.setItemDelegateForColumn(7, self.category_delegate)
        self.table.setModel(self.model)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setHighlightSections(False)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Size
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Progress
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Speed
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Conns
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # ETA
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)  # Status
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)  # Category

        # Default widths (user can resize freely afterwards)
        self.table.setColumnWidth(0, 260)  # Name
        self.table.setColumnWidth(1, 104)  # Size
        self.table.setColumnWidth(2, 190)  # Progress
        self.table.setColumnWidth(3, 110)  # Speed
        self.table.setColumnWidth(4, 72)  # Conns
        self.table.setColumnWidth(5, 100)  # ETA
        self.table.setColumnWidth(6, 170)  # Status
        self.table.setColumnWidth(7, 120)  # Category

        # Right-click on the header to reset column widths
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_context_menu)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Table + friendly empty-state message stacked on top of each other
        table_holder = QWidget()
        table_stack = QStackedLayout(table_holder)
        table_stack.setContentsMargins(0, 0, 0, 0)
        table_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        table_stack.addWidget(self.table)
        self.empty_state = QLabel()
        self.empty_state.setObjectName("empty_state")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        table_stack.addWidget(self.empty_state)
        ma_lay.addWidget(table_holder, 1)
        self.model.modelReset.connect(self._refresh_empty_state)
        self.model.rowsInserted.connect(self._refresh_empty_state)
        self.model.rowsRemoved.connect(self._refresh_empty_state)
        self._refresh_empty_state()

        if self.table.selectionModel():
            self.table.selectionModel().selectionChanged.connect(
                self._update_toggle_button
            )
        # A model reset / row removal clears the selection without emitting
        # selectionChanged, so refresh the Remove button on those too.
        self.model.modelReset.connect(self._update_remove_button)
        self.model.rowsRemoved.connect(self._update_remove_button)

        self.details_panel = self._build_details_panel()
        self.details_panel.setVisible(True)
        self._details_visible = True
        ma_lay.addWidget(self.details_panel)

        self._build_status_bar()

        return main_area

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(12, 10, 12, 10)
        tb_lay.setSpacing(6)

        icon_size = QSize(20, 20)

        def divider():
            line = QFrame()
            line.setObjectName("toolbar_divider")
            line.setFixedHeight(22)
            return line

        self.btn_add = QPushButton(get_icon("download"), "Add Download")
        self.btn_add.setIconSize(icon_size)
        make_primary(self.btn_add)
        self.btn_add.clicked.connect(self._add_download)
        tb_lay.addWidget(self.btn_add)
        tb_lay.addSpacing(4)
        tb_lay.addWidget(divider())
        tb_lay.addSpacing(4)
        self.btn_toggle = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.btn_toggle.setIconSize(icon_size)
        self.btn_toggle.clicked.connect(self._toggle_pause_resume)
        self.btn_toggle.setEnabled(False)
        tb_lay.addWidget(self.btn_toggle)

        self.btn_move_queue = QPushButton(get_icon("go-next"), "Move to Queue")
        self.btn_move_queue.setIconSize(icon_size)
        self.btn_move_queue.clicked.connect(self._move_selected_to_queue)
        self.btn_move_queue.setEnabled(False)
        tb_lay.addWidget(self.btn_move_queue)

        self.btn_remove = QPushButton(get_icon("edit-delete"), "Remove")
        self.btn_remove.setIconSize(icon_size)
        self.btn_remove.setProperty("variant", "ghost-danger")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_remove.setEnabled(False)  # enabled while rows are selected
        tb_lay.addWidget(self.btn_remove)

        self.btn_clear_completed = QPushButton(
            get_icon("edit-clear"), "Clear Completed"
        )
        self.btn_clear_completed.setIconSize(icon_size)
        self.btn_clear_completed.clicked.connect(self._clear_completed_downloads)
        tb_lay.addWidget(self.btn_clear_completed)
        tb_lay.addSpacing(4)
        tb_lay.addWidget(divider())
        tb_lay.addSpacing(4)

        self.btn_video = QPushButton(get_icon("applications-multimedia"), " Video")
        self.btn_video.setIconSize(icon_size)
        self.btn_video.setText(" Video")
        self.btn_video.clicked.connect(self._video_download)
        tb_lay.addWidget(self.btn_video)

        tb_lay.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search downloads…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(200)
        self.search_box.setMaximumWidth(280)
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._filter_downloads)
        self.search_box.textChanged.connect(self._refresh_empty_state)
        tb_lay.addWidget(self.search_box)

        self.btn_show_details = QPushButton(get_icon("view-list-details"), "")
        self.btn_show_details.setProperty("iconOnly", True)
        self.btn_show_details.setIconSize(icon_size)
        self.btn_show_details.setToolTip("Toggle details panel (Ctrl+D)")
        self.btn_show_details.setCheckable(True)
        self.btn_show_details.toggled.connect(self._toggle_details_panel)
        tb_lay.addWidget(self.btn_show_details)

        self.btn_settings = QPushButton(get_icon("configure"), "")
        self.btn_settings.setProperty("iconOnly", True)
        self.btn_settings.setToolTip("Settings (Ctrl+,)")
        self.btn_settings.setIconSize(icon_size)
        self.btn_settings.clicked.connect(self._open_settings)
        tb_lay.addWidget(self.btn_settings)

        return toolbar

    def _build_status_bar(self) -> None:
        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(4)

        self.speed_icon_label = QLabel()
        self.speed_icon_label.setPixmap(get_icon("go-down").pixmap(16, 16))

        self.speed_status_label = QLabel("0 B/s")
        self.speed_status_label.setObjectName("speed_label")

        speed_layout.addWidget(self.speed_icon_label)
        speed_layout.addWidget(self.speed_status_label)
        self.statusBar().addPermanentWidget(speed_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)

        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.progress_bar.setTextVisible(True)

        self.status_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status_label)

        self.shutdown_cb = QCheckBox("Shutdown on Finish")
        self.shutdown_cb.setStyleSheet("margin:0 8px;")
        self.shutdown_cb.setChecked(
            self.store.settings.get("shutdown_after_finish", False)
        )
        self.shutdown_cb.toggled.connect(self._toggle_shutdown)
        self.statusBar().addPermanentWidget(self.shutdown_cb)

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        add_action = QAction(get_icon("download"), "Add Download", self)
        add_action.triggered.connect(self._add_download)
        add_action.setShortcut("Ctrl+N")
        file_menu.addAction(add_action)

        file_menu.addSeparator()

        export_action = QAction(get_icon("document-save"), "Export Downloads", self)
        export_action.triggered.connect(self._export_downloads)
        export_action.setShortcut("Ctrl+E")
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        settings_action = QAction(get_icon("configure"), "Settings", self)
        settings_action.triggered.connect(self._open_settings)
        settings_action.setShortcut("Ctrl+,")
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction(get_icon("application-exit"), "Quit", self)
        quit_action.triggered.connect(self.quit_app)
        quit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(quit_action)

        queue_menu = mb.addMenu("&Queue")
        queue_menu.addAction(get_icon("list-add"), "New Queue", self._add_queue)
        queue_menu.addAction(get_icon("configure"), "Edit Queue", self._edit_queue)
        queue_menu.addAction(
            get_icon("list-remove"), "Delete Queue", self._delete_queue
        )

        view_menu = mb.addMenu("&View")
        refresh_action = QAction(get_icon("view-refresh"), "Refresh", self)
        refresh_action.triggered.connect(self._refresh_table)
        refresh_action.setShortcut("F5")
        view_menu.addAction(refresh_action)

        log_action = QAction(get_icon("text-x-generic"), "Show Logs", self)
        log_action.triggered.connect(self._show_log_viewer)
        log_action.setShortcut("Ctrl+L")
        view_menu.addAction(log_action)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction("About", self._show_about)
        help_menu.addAction("Shortcuts", self._show_shortcuts)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)

        normal_path = get_resource_path("logo/icon512.png")
        if os.path.exists(normal_path):
            self.tray_icon_normal = QIcon(normal_path)
        else:
            self.tray_icon_normal = get_icon("download-manager")

        active_path = get_resource_path("logo/tray-active.png")
        if os.path.exists(active_path):
            self.tray_icon_active = QIcon(active_path)
        else:
            self.tray_icon_active = self.tray_icon_normal

        self.tray.setIcon(self.tray_icon_normal)

        menu = QMenu()
        menu.addAction(get_icon("window"), "Show", self.show)
        menu.addAction(get_icon("application-exit"), "Quit", self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        """Toggle window visibility when the tray icon is clicked.

        Behavior:
        - Single left click toggles: if the window is visible and
          active, hide it (minimize to tray); otherwise show + raise
          + activate it.
        - Double click always shows and raises (this is what most
          users expect from a tray icon).
        - Middle click and right click are ignored (right click
          opens the context menu automatically).
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()
            return

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show()
                if self.isMinimized():
                    self.showNormal()
                self.raise_()
                self.activateWindow()

    def _minimize_to_tray(self):
        self.hide()

        if hasattr(self, "tray") and self.tray:
            QTimer.singleShot(
                100,
                lambda: self.tray.showMessage(
                    "FelfelDM",
                    "Started minimized to system tray.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                ),
            )

    def _header_context_menu(self, pos) -> None:
        """Context menu shown when right-clicking the table header."""
        menu = QMenu(self)

        menu.addAction(
            get_icon("view-refresh"),
            "Fit Column Widths",
            self._fit_column_widths,
        )

        menu.addSeparator()

        header = self.table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col >= 0:
            menu.addAction(
                f"Fit '{self.model.COLS[col]}' to Contents",
                lambda c=col: self.table.resizeColumnToContents(c),
            )

        menu.exec(header.mapToGlobal(pos))

    def _fit_column_widths(self) -> None:
        """fit all download table columns to fit the viewport exactly.

        Widths are distributed proportionally so the total never exceeds
        the viewport — no horizontal scrollbar appears.
        """
        header = self.table.horizontalHeader()
        available = self.table.viewport().width()
        if available <= 0:
            return

        # Column proportions (sum = 1.00)
        ratios = {
            0: 0.28,  # Name
            1: 0.09,  # Size
            2: 0.16,  # Progress
            3: 0.11,  # Speed
            4: 0.06,  # Conns
            5: 0.10,  # ETA
            6: 0.12,  # Status
            7: 0.08,  # Category
        }

        # Resize interactively so the user can still adjust them later
        for col in ratios:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Compute and apply widths. Rounding errors are absorbed by the
        # last column so the total exactly matches the viewport width.
        total = sum(ratios.values())
        assigned = 0
        cols = sorted(ratios.keys())

        for i, col in enumerate(cols):
            if i == len(cols) - 1:
                width = available - assigned
            else:
                width = int(available * (ratios[col] / total))
                assigned += width

            self.table.setColumnWidth(col, max(40, width))

    def _center_dialog_on_screen(self, dialog: QDialog) -> None:
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )

    def _close_splash(self) -> None:
        if hasattr(self, "splash") and self.splash:
            self.splash.close()
            self.splash = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._drop_overlay is not None and self._drop_overlay.isVisible():
            self._drop_overlay.setGeometry(self.table.viewport().rect())

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts.

        Table-local keys (Space/Delete) are scoped to the widget so they
        don't fire while the user is typing in the search box or
        interacting with the details panel.
        """
        table_context = Qt.ShortcutContext.WidgetWithChildrenShortcut

        for key, slot in (
            ("Space", self._toggle_pause_resume),
            ("Delete", self._remove_selected),
            ("Shift+Delete", self._remove_with_files),
        ):
            shortcut = QShortcut(QKeySequence(key), self.table, slot)
            shortcut.setContext(table_context)

        QShortcut(QKeySequence("Ctrl+P"), self, self._pause_selected)
        QShortcut(QKeySequence("Ctrl+R"), self, self._resume_selected)

        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_details_panel)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Escape"), self, self._clear_search)

        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_queue)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_queue)

        QShortcut(QKeySequence("F5"), self, self._refresh_table)
        QShortcut(QKeySequence("F1"), self, self._show_shortcuts)

    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog"""
        shortcuts = [
            ("Ctrl+N", "Add Download"),
            ("Space", "Pause/Resume selected"),
            ("Ctrl+P", "Pause selected"),
            ("Ctrl+R", "Resume selected"),
            ("Delete", "Remove selected"),
            ("Shift+Delete", "Remove and delete files"),
            ("Ctrl+D", "Toggle details panel"),
            ("Ctrl+F", "Focus search"),
            ("Escape", "Clear search"),
            ("Ctrl+Tab", "Next queue"),
            ("Ctrl+Shift+Tab", "Previous queue"),
            ("Ctrl+,", "Settings"),
            ("F5", "Refresh"),
            ("F1", "Show shortcuts"),
            ("Ctrl+E", "Export Downloads"),
            ("Ctrl+L", "Show logs"),
        ]

        msg = "<h3>Keyboard Shortcuts</h3><br>"
        for key, action in shortcuts:
            msg += f"<b>{key}</b> — {action}<br>"

        QMessageBox.information(self, "Shortcuts", msg)

    def _focus_search(self) -> None:
        """Focus the search box"""
        if hasattr(self, "search_box"):
            self.search_box.setFocus()
            self.search_box.selectAll()

    def _clear_search(self) -> None:
        """Clear search box and restore focus to table"""
        if hasattr(self, "search_box"):
            self.search_box.clear()
            self.table.setFocus()
