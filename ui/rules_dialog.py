# ui/rules_dialog.py

"""
Download Rules UI.

A dialog for managing rules with add/edit/delete/reorder.
"""

import os
from typing import Optional

from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from core.rule_engine import (
    Rule,
    RuleEngine,
    parse_size,
    format_size_human,
    expand_path,
)
from utils.helpers import get_icon


class RuleEditDialog(QDialog):
    """Dialog for adding/editing a single rule."""

    def __init__(self, rule: Optional[Rule] = None, queues=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Rule" if rule else "New Rule")
        self.setMinimumWidth(540)
        self.setModal(True)

        self.rule = rule or Rule()
        self.queues = queues or []

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ─── Name ───
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Rule Name:"))
        self.name_edit = QLineEdit(self.rule.name)
        self.name_edit.setPlaceholderText("e.g. Linux ISOs")
        name_row.addWidget(self.name_edit, 1)
        main_layout.addLayout(name_row)

        # ─── Conditions ───
        cond_group = QGroupBox("Conditions (all must match)")
        cond_layout = QFormLayout(cond_group)
        cond_layout.setSpacing(8)

        self.url_contains_edit = QLineEdit(self.rule.url_contains)
        self.url_contains_edit.setPlaceholderText("e.g. .iso  or  ubuntu")
        cond_layout.addRow("URL contains:", self.url_contains_edit)

        self.url_matches_edit = QLineEdit(self.rule.url_matches)
        self.url_matches_edit.setPlaceholderText("e.g. ^https?://.*\\.iso$")
        cond_layout.addRow("URL matches regex:", self.url_matches_edit)

        self.extension_edit = QLineEdit(self.rule.extension)
        self.extension_edit.setPlaceholderText("e.g. iso, zip, mp4")
        cond_layout.addRow("Extension is:", self.extension_edit)

        self.domain_edit = QLineEdit(self.rule.domain)
        self.domain_edit.setPlaceholderText("e.g. github.com  or  *.example.com")
        cond_layout.addRow("Domain is:", self.domain_edit)

        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        self.size_min_edit = QLineEdit(
            format_size_human(self.rule.size_min) if self.rule.size_min else ""
        )
        self.size_min_edit.setPlaceholderText("e.g. 500M")
        self.size_min_edit.setMaximumWidth(120)

        self.size_max_edit = QLineEdit(
            format_size_human(self.rule.size_max) if self.rule.size_max else ""
        )
        self.size_max_edit.setPlaceholderText("e.g. 5G")
        self.size_max_edit.setMaximumWidth(120)

        size_row.addWidget(QLabel("From:"))
        size_row.addWidget(self.size_min_edit)
        size_row.addWidget(QLabel("To:"))
        size_row.addWidget(self.size_max_edit)
        size_row.addStretch()
        cond_layout.addRow("Size:", size_row)

        main_layout.addWidget(cond_group)

        # ─── Actions ───
        act_group = QGroupBox("Actions")
        act_layout = QFormLayout(act_group)
        act_layout.setSpacing(8)

        # Queue
        self.queue_combo = QComboBox()
        self.queue_combo.addItem("(no change)", "")
        for q in self.queues:
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, q.name)
        # Select current
        idx = self.queue_combo.findData(self.rule.queue)
        if idx >= 0:
            self.queue_combo.setCurrentIndex(idx)
        act_layout.addRow("Queue:", self.queue_combo)

        # Folder
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.folder_edit = QLineEdit(self.rule.folder)
        self.folder_edit.setPlaceholderText("e.g. ~/Downloads/ISO")
        folder_row.addWidget(self.folder_edit)
        browse_btn = QPushButton()
        browse_btn.setIcon(get_icon("folder-open"))
        browse_btn.setFixedSize(28, 28)
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        act_layout.addRow("Folder:", folder_row)

        # Connections
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(0, 16)
        self.conn_spin.setSpecialValueText("(no change)")
        self.conn_spin.setValue(self.rule.connections)
        act_layout.addRow("Connections:", self.conn_spin)

        # Speed limit
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 999999)
        self.speed_spin.setSuffix(" KB/s")
        self.speed_spin.setSpecialValueText("(no change)")
        self.speed_spin.setValue(self.rule.speed_limit)
        act_layout.addRow("Speed limit:", self.speed_spin)

        main_layout.addWidget(act_group)

        # ─── Enabled ───
        self.enabled_cb = QCheckBox("Enable this rule")
        self.enabled_cb.setChecked(self.rule.enabled)
        main_layout.addWidget(self.enabled_cb)

        # ─── Buttons ───
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _browse_folder(self):
        current = expand_path(self.folder_edit.text()) or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Folder", current)
        if d:
            self.folder_edit.setText(d)

    def _on_ok(self):
        # Validate name
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Error", "Rule name is required.")
            return

        # Validate at least one condition
        url_contains = self.url_contains_edit.text().strip()
        url_matches = self.url_matches_edit.text().strip()
        extension = self.extension_edit.text().strip()
        domain = self.domain_edit.text().strip()
        size_min = parse_size(self.size_min_edit.text())
        size_max = parse_size(self.size_max_edit.text())

        if not any([url_contains, url_matches, extension, domain, size_min, size_max]):
            QMessageBox.warning(
                self,
                "Error",
                "At least one condition is required.",
            )
            return

        # Validate size range
        if size_min > 0 and size_max > 0 and size_min > size_max:
            QMessageBox.warning(
                self,
                "Error",
                "Minimum size cannot be larger than maximum size.",
            )
            return

        # Validate at least one action
        queue = self.queue_combo.currentData() or ""
        folder = self.folder_edit.text().strip()
        connections = self.conn_spin.value()
        speed_limit = self.speed_spin.value()

        if not any([queue, folder, connections, speed_limit]):
            QMessageBox.warning(
                self,
                "Error",
                "At least one action is required.",
            )
            return

        # Apply to rule
        self.rule.name = self.name_edit.text().strip()
        self.rule.enabled = self.enabled_cb.isChecked()
        self.rule.url_contains = url_contains
        self.rule.url_matches = url_matches
        self.rule.extension = extension
        self.rule.domain = domain
        self.rule.size_min = size_min
        self.rule.size_max = size_max
        self.rule.queue = queue
        self.rule.folder = folder
        self.rule.connections = connections
        self.rule.speed_limit = speed_limit

        self.accept()

    def get_rule(self) -> Rule:
        return self.rule


class RulesDialog(QDialog):
    """Manage all download rules."""

    def __init__(self, rule_engine: RuleEngine, queues=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Rules")
        self.setMinimumWidth(700)
        self.setMinimumHeight(480)
        self.setModal(True)

        self.rule_engine = rule_engine
        self.queues = queues or []

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel(
            "<b>Download Rules</b><br>"
            "<span style='color:#888; font-size:11px;'>"
            "Rules are applied automatically when you add a new download. "
            "Rules are evaluated top-to-bottom; the first match wins."
            "</span>"
        )
        header.setWordWrap(True)
        main_layout.addWidget(header)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self._on_edit)
        self.list_widget.itemSelectionChanged.connect(self._update_buttons)
        main_layout.addWidget(self.list_widget, 1)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.add_btn = QPushButton(get_icon("list-add"), "Add")
        self.add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton(get_icon("configure"), "Edit")
        self.edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self.edit_btn)

        self.remove_btn = QPushButton(get_icon("list-remove"), "Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(self.remove_btn)

        btn_row.addSpacing(12)

        self.up_btn = QPushButton(get_icon("go-up"), "Move Up")
        self.up_btn.clicked.connect(self._on_move_up)
        btn_row.addWidget(self.up_btn)

        self.down_btn = QPushButton(get_icon("go-down"), "Move Down")
        self.down_btn.clicked.connect(self._on_move_down)
        btn_row.addWidget(self.down_btn)

        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        # Close
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        main_layout.addWidget(close_box)

        self._refresh_list()

    # ─────────────────────────────────────────────
    # List rendering
    # ─────────────────────────────────────────────

    def _refresh_list(self):
        self.list_widget.clear()
        for rule in self.rule_engine.rules:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, rule.id)
            item.setText(self._format_rule_label(rule))
            if not rule.enabled:
                item.setForeground(QColor("#888"))
            self.list_widget.addItem(item)

        self._update_buttons()

    def _format_rule_label(self, rule: Rule) -> str:
        parts = []
        if rule.url_contains:
            parts.append(f"URL contains '{rule.url_contains}'")
        if rule.url_matches:
            parts.append(f"URL matches /{rule.url_matches}/")
        if rule.extension:
            parts.append(f"ext = .{rule.extension}")
        if rule.domain:
            parts.append(f"domain = {rule.domain}")
        if rule.size_min or rule.size_max:
            smin = format_size_human(rule.size_min) or "0"
            smax = format_size_human(rule.size_max) or "∞"
            parts.append(f"size in [{smin}..{smax}]")

        cond_str = " AND ".join(parts) if parts else "(no conditions)"

        actions = []
        if rule.queue:
            actions.append(f"queue='{rule.queue}'")
        if rule.folder:
            actions.append(f"folder='{rule.folder}'")
        if rule.connections:
            actions.append(f"conn={rule.connections}")
        if rule.speed_limit:
            actions.append(f"speed={rule.speed_limit}K")

        act_str = ", ".join(actions) if actions else "(no actions)"

        status = "" if rule.enabled else "  [disabled]"
        return f"{rule.name}{status}\n   IF {cond_str}\n   THEN {act_str}"

    def _selected_rule_id(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _update_buttons(self):
        has_selection = self._selected_rule_id() is not None
        self.edit_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)
        self.up_btn.setEnabled(has_selection)
        self.down_btn.setEnabled(has_selection)

    # ─────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────

    def _on_add(self):
        dlg = RuleEditDialog(rule=None, queues=self.queues, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_rule = dlg.get_rule()
            self.rule_engine.add(new_rule)
            self._refresh_list()
            # Select the new rule
            for i in range(self.list_widget.count()):
                if (
                    self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                    == new_rule.id
                ):
                    self.list_widget.setCurrentRow(i)
                    break

    def _on_edit(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            return
        rule = self.rule_engine.get(rule_id)
        if not rule:
            return

        dlg = RuleEditDialog(rule=rule, queues=self.queues, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_list()

    def _on_remove(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            return
        rule = self.rule_engine.get(rule_id)
        if not rule:
            return
        reply = QMessageBox.question(
            self,
            "Remove Rule",
            f"Remove rule '{rule.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.rule_engine.remove(rule_id)
            self._refresh_list()

    def _on_move_up(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            return
        if self.rule_engine.move_up(rule_id):
            self._refresh_list()
            self._select_by_id(rule_id)

    def _on_move_down(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            return
        if self.rule_engine.move_down(rule_id):
            self._refresh_list()
            self._select_by_id(rule_id)

    def _select_by_id(self, rule_id: str):
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == rule_id:
                self.list_widget.setCurrentRow(i)
                return
