# ui/rules_dialog.py

"""
Download Rules UI.

A dialog for managing rules with add/edit/delete/reorder.
"""

import os
from typing import Optional

from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QPalette, QPen

from core.rule_engine import (
    Rule,
    RuleEngine,
    parse_size,
    format_size_human,
    expand_path,
)
from utils.helpers import get_icon

# ─────────────────────────────────────────────────────────────
# Theme-aware color helpers
# ─────────────────────────────────────────────────────────────


class ThemeColors:
    """Resolve colors from the current QPalette."""

    def __init__(self, widget: QWidget):
        pal = widget.palette()
        self.window = pal.color(QPalette.ColorRole.Window)
        self.base = pal.color(QPalette.ColorRole.Base)
        self.text = pal.color(QPalette.ColorRole.WindowText)
        self.mid = pal.color(QPalette.ColorRole.Mid)
        self.midlight = pal.color(QPalette.ColorRole.Midlight)
        self.highlight = pal.color(QPalette.ColorRole.Highlight)
        self.highlighted_text = pal.color(QPalette.ColorRole.HighlightedText)
        self.is_dark = self.window.lightness() < 128

        # standard "disabled" foreground from palette (matches other widgets)
        self.palette_disabled_text = pal.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText
        )
        self.palette_disabled_button_text = pal.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText
        )

    @property
    def muted(self) -> QColor:
        c = QColor(self.text)
        c.setAlpha(160 if self.is_dark else 180)
        return c

    @property
    def faint(self) -> QColor:
        c = QColor(self.text)
        c.setAlpha(100 if self.is_dark else 120)
        return c

    @property
    def disabled(self) -> QColor:
        c = QColor(self.text)
        c.setAlpha(110 if self.is_dark else 130)
        return c

    @property
    def success(self) -> QColor:
        return QColor("#3ecf8e") if self.is_dark else QColor("#1f9d55")

    # ── card colors ──
    @property
    def card_border(self) -> QColor:
        c = QColor(self.text)
        c.setAlpha(55 if self.is_dark else 75)
        return c

    @property
    def card_border_hover(self) -> QColor:
        c = QColor(self.highlight)
        c.setAlpha(160)
        return c

    @property
    def card_border_selected(self) -> QColor:
        return QColor(self.highlight)

    @property
    def card_bg(self) -> QColor:
        c = QColor(self.base)
        if self.is_dark:
            c = c.lighter(118)
        else:
            c = c.lighter(102)
        return c

    @property
    def card_bg_hover(self) -> QColor:
        c = QColor(self.card_bg)
        if self.is_dark:
            c = c.lighter(112)
        else:
            c = c.darker(103)
        return c

    @property
    def card_bg_selected(self) -> QColor:
        c = QColor(self.highlight)
        c.setAlpha(45)
        # blend on top of card_bg for better contrast
        bg = self.card_bg
        r = int(bg.red() * 0.7 + c.red() * 0.3)
        g = int(bg.green() * 0.7 + c.green() * 0.3)
        b = int(bg.blue() * 0.7 + c.blue() * 0.3)
        return QColor(r, g, b)

    @staticmethod
    def css(c: QColor) -> str:
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


# ─────────────────────────────────────────────────────────────
# Rule item (card)
# ─────────────────────────────────────────────────────────────


class RuleItemWidget(QWidget):
    """
    A single row rendered as a bordered card.
    Uses paintEvent so the border actually shows inside QListWidget.
    """

    def __init__(self, rule: Rule, parent=None):
        super().__init__(parent)
        self.rule = rule
        self._colors = ThemeColors(self)
        self._hovered = False
        self._selected = False

        # ensure stylesheet background doesn't fight our painting
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        # ── Title row ──
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        title_row.addWidget(self.status_dot)

        self.name_label = QLabel(rule.name or "(unnamed)")
        f = QFont()
        f.setBold(True)
        self.name_label.setFont(f)
        title_row.addWidget(self.name_label, 1)

        self.badge = QLabel(self._actions_badge(rule))
        title_row.addWidget(self.badge)

        layout.addLayout(title_row)

        # ── IF line ──
        self.cond_label = QLabel()
        self.cond_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.cond_label)

        # ── THEN line ──
        self.act_label = QLabel()
        self.act_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.act_label)

        self._apply_theme()

    # ── paint ──

    def paintEvent(self, event):
        """Draw rounded rect border + background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = self._colors

        # background
        if self._selected:
            bg = c.card_bg_selected
            border = c.card_border_selected
            border_width = 2.0
        elif self._hovered:
            bg = c.card_bg_hover
            border = c.card_border_hover
            border_width = 1.0
        else:
            bg = c.card_bg
            border = c.card_border
            border_width = 1.0

        painter.setBrush(bg)
        pen = QPen(border)
        pen.setWidthF(border_width)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 6, 6)

        painter.end()
        super().paintEvent(event)

    # ── hover / selection ──

    def set_selected(self, selected: bool):
        if self._selected != selected:
            self._selected = selected
            self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # clicking on the card should select the list row
        super().mousePressEvent(event)
        # bubble up to parent list widget
        lw = self.parent()
        while lw is not None and not isinstance(lw, QListWidget):
            lw = lw.parent()
        if isinstance(lw, QListWidget):
            for i in range(lw.count()):
                item = lw.item(i)
                if lw.itemWidget(item) is self or (
                    lw.itemWidget(item) and lw.itemWidget(item).isAncestorOf(self)
                ):
                    lw.setCurrentRow(i)
                    break

    # ── theme ──

    def refresh_theme(self):
        self._colors = ThemeColors(self)
        self._apply_theme()
        self.update()

    def _apply_theme(self):
        c = self._colors
        enabled = self.rule.enabled

        dot_color = c.success if enabled else c.faint
        self.status_dot.setStyleSheet(
            f"background-color: {c.css(dot_color)};" f"border-radius: 4px;"
        )

        name_color = c.text if enabled else c.disabled
        self.name_label.setStyleSheet(
            f"color: {c.css(name_color)}; background: transparent;"
        )

        badge_text = c.muted if enabled else c.faint
        self.badge.setStyleSheet(
            f"color: {c.css(badge_text)};"
            f"background: {c.css(c.card_border)};"
            f"border-radius: 3px;"
            f"font-size: 10px;"
        )
        self.badge.setContentsMargins(8, 2, 8, 2)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setVisible(bool(self.badge.text()))

        kw_color = c.muted if enabled else c.faint
        txt_color = c.text if enabled else c.disabled

        self.cond_label.setText(
            f"<span style='color:{c.css(kw_color)}; font-weight:600;'>IF</span>"
            f"<span style='color:{c.css(txt_color)};'>  {self._format_conditions(self.rule)}</span>"
        )
        self.cond_label.setStyleSheet("font-size: 11px; background: transparent;")

        self.act_label.setText(
            f"<span style='color:{c.css(kw_color)}; font-weight:600;'>THEN</span>"
            f"<span style='color:{c.css(txt_color)};'>  {self._format_actions(self.rule)}</span>"
        )
        self.act_label.setStyleSheet("font-size: 11px; background: transparent;")

    # ── formatting ──

    @staticmethod
    def _actions_badge(rule: Rule) -> str:
        n = sum(
            1
            for v in (rule.queue, rule.folder, rule.connections, rule.speed_limit)
            if v
        )
        if n == 0:
            return ""
        return f"{n} action" + ("s" if n != 1 else "")

    @staticmethod
    def _format_conditions(rule: Rule) -> str:
        parts = []
        if rule.url_contains:
            parts.append(f'url ~ "{rule.url_contains}"')
        if rule.url_matches:
            parts.append(f"url ~ /{rule.url_matches}/")
        if rule.extension:
            parts.append(f"ext = .{rule.extension}")
        if rule.domain:
            parts.append(f"domain = {rule.domain}")
        if rule.size_min or rule.size_max:
            smin = format_size_human(rule.size_min) or "0"
            smax = format_size_human(rule.size_max) or "∞"
            parts.append(f"size ∈ [{smin} .. {smax}]")
        return "  AND  ".join(parts) if parts else "(no conditions)"

    @staticmethod
    def _format_actions(rule: Rule) -> str:
        parts = []
        if rule.queue:
            parts.append(f'queue = "{rule.queue}"')
        if rule.folder:
            parts.append(f'folder = "{rule.folder}"')
        if rule.connections:
            parts.append(f"connections = {rule.connections}")
        if rule.speed_limit:
            parts.append(f"speed = {rule.speed_limit} KB/s")
        return ",  ".join(parts) if parts else "(no actions)"


# ─────────────────────────────────────────────────────────────
# Rule edit dialog
# ─────────────────────────────────────────────────────────────


class RuleEditDialog(QDialog):
    """Dialog for adding/editing a single rule."""

    def __init__(self, rule: Optional[Rule] = None, queues=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Rule" if rule else "New Rule")
        self.setMinimumWidth(560)
        self.setModal(True)

        self.rule = rule or Rule()
        self.queues = queues or []

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # ─── Name ───
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("Rule Name:")
        name_label.setFixedWidth(110)
        name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        name_row.addWidget(name_label)
        self.name_edit = QLineEdit(self.rule.name)
        self.name_edit.setPlaceholderText("e.g. Linux ISOs")
        name_row.addWidget(self.name_edit, 1)
        main_layout.addLayout(name_row)

        # ─── Conditions ───
        cond_group = QGroupBox("Conditions (all must match)")
        cond_layout = QFormLayout(cond_group)
        cond_layout.setSpacing(10)
        cond_layout.setContentsMargins(14, 16, 14, 14)
        cond_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.url_contains_edit = QLineEdit(self.rule.url_contains)
        self.url_contains_edit.setPlaceholderText("e.g. .iso  or  ubuntu")
        cond_layout.addRow("URL contains:", self.url_contains_edit)

        self.url_matches_edit = QLineEdit(self.rule.url_matches)
        self.url_matches_edit.setPlaceholderText(r"e.g. ^https?://.*\.iso$")
        cond_layout.addRow("URL matches regex:", self.url_matches_edit)

        self.extension_edit = QLineEdit(self.rule.extension)
        self.extension_edit.setPlaceholderText("e.g. iso, zip, mp4")
        cond_layout.addRow("Extension is:", self.extension_edit)

        self.domain_edit = QLineEdit(self.rule.domain)
        self.domain_edit.setPlaceholderText("e.g. github.com  or  *.example.com")
        cond_layout.addRow("Domain is:", self.domain_edit)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
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
        act_layout.setSpacing(10)
        act_layout.setContentsMargins(14, 16, 14, 14)
        act_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.queue_combo = QComboBox()
        self.queue_combo.addItem("(no change)", "")
        for q in self.queues:
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, q.name)
        idx = self.queue_combo.findData(self.rule.queue)
        if idx >= 0:
            self.queue_combo.setCurrentIndex(idx)
        act_layout.addRow("Queue:", self.queue_combo)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.folder_edit = QLineEdit(self.rule.folder)
        self.folder_edit.setPlaceholderText("e.g. ~/Downloads/ISO")
        folder_row.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton()
        browse_btn.setIcon(get_icon("folder-open"))
        browse_btn.setFixedSize(28, 28)
        browse_btn.setToolTip("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        act_layout.addRow("Folder:", folder_row)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(0, 16)
        self.conn_spin.setSpecialValueText("(no change)")
        self.conn_spin.setValue(self.rule.connections)
        act_layout.addRow("Connections:", self.conn_spin)

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
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _browse_folder(self):
        current = expand_path(self.folder_edit.text()) or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Folder", current)
        if d:
            self.folder_edit.setText(d)

    def _on_ok(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Error", "Rule name is required.")
            return

        url_contains = self.url_contains_edit.text().strip()
        url_matches = self.url_matches_edit.text().strip()
        extension = self.extension_edit.text().strip()
        domain = self.domain_edit.text().strip()
        size_min = parse_size(self.size_min_edit.text())
        size_max = parse_size(self.size_max_edit.text())

        if not any([url_contains, url_matches, extension, domain, size_min, size_max]):
            QMessageBox.warning(self, "Error", "At least one condition is required.")
            return

        if size_min > 0 and size_max > 0 and size_min > size_max:
            QMessageBox.warning(
                self,
                "Error",
                "Minimum size cannot be larger than maximum size.",
            )
            return

        queue = self.queue_combo.currentData() or ""
        folder = self.folder_edit.text().strip()
        connections = self.conn_spin.value()
        speed_limit = self.speed_spin.value()

        if not any([queue, folder, connections, speed_limit]):
            QMessageBox.warning(self, "Error", "At least one action is required.")
            return

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


# ─────────────────────────────────────────────────────────────
# Rules manager dialog
# ─────────────────────────────────────────────────────────────


class RulesDialog(QDialog):
    """Manage all download rules."""

    def __init__(self, rule_engine: RuleEngine, queues=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Rules")
        self.setMinimumWidth(720)
        self.setMinimumHeight(500)
        self.setModal(True)

        self.rule_engine = rule_engine
        self.queues = queues or []
        self._colors = ThemeColors(self)
        self._item_widgets: dict[str, RuleItemWidget] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # ─── Header ───
        c = self._colors
        header = QLabel(
            f"<b style='font-size:14px; color:{c.css(c.text)};'>Download Rules</b><br>"
            f"<span style='color:{c.css(c.muted)}; font-size:11px;'>"
            "Rules are applied automatically when you add a new download. "
            "Rules are evaluated top-to-bottom; the first match wins. "
            "<b>Changes only affect new downloads</b>, not ones already in progress."
            "</span>"
        )
        header.setWordWrap(True)
        main_layout.addWidget(header)

        # ─── List ───
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("RulesList")
        self.list_widget.setSpacing(8)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.setStyleSheet(
            "QListWidget#RulesList {"
            "  background: transparent;"
            "  border: none;"
            "  outline: none;"
            "}"
            "QListWidget#RulesList::item {"
            "  background: transparent;"
            "  border: none;"
            "  padding: 0;"
            "}"
            "QListWidget#RulesList::item:selected,"
            "QListWidget#RulesList::item:hover {"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        self.list_widget.itemDoubleClicked.connect(self._on_edit)
        self.list_widget.itemSelectionChanged.connect(self._update_buttons)
        self.list_widget.itemSelectionChanged.connect(self._update_card_selection)
        main_layout.addWidget(self.list_widget, 1)

        # ─── Buttons row ───
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

        btn_row.addStretch()

        self.up_btn = QPushButton(get_icon("go-up"), "Move Up")
        self.up_btn.clicked.connect(self._on_move_up)
        btn_row.addWidget(self.up_btn)

        self.down_btn = QPushButton(get_icon("go-down"), "Move Down")
        self.down_btn.clicked.connect(self._on_move_down)
        btn_row.addWidget(self.down_btn)

        main_layout.addLayout(btn_row)

        # ─── Close ───
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        close_box.rejected.connect(self.reject)
        main_layout.addWidget(close_box)

        self._apply_button_theme()
        self._refresh_list()

    # ─────────────────────────────────────────────
    # Theme hooks
    # ─────────────────────────────────────────────

    def _button_list(self):
        return [
            self.add_btn,
            self.edit_btn,
            self.remove_btn,
            self.up_btn,
            self.down_btn,
        ]

    def _apply_button_theme(self):
        """Ensure disabled buttons look consistent with our theme."""
        c = self._colors
        disabled_text = c.palette_disabled_button_text
        if not disabled_text.isValid():
            disabled_text = c.faint

        css_disabled = c.css(disabled_text)
        for btn in self._button_list():
            btn.setStyleSheet(
                f"QPushButton:disabled {{" f"  color: {css_disabled};" f"}}"
            )

    # ─────────────────────────────────────────────
    # List rendering
    # ─────────────────────────────────────────────

    def _refresh_list(self):
        self.list_widget.clear()
        self._item_widgets.clear()

        for rule in self.rule_engine.rules:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, rule.id)

            widget = RuleItemWidget(rule, parent=self.list_widget)
            # wrapper with horizontal margin so card doesn't touch scrollbar
            wrapper = QWidget()
            wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(widget)

            item.setSizeHint(wrapper.sizeHint() + QSize(0, 4))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, wrapper)
            self._item_widgets[rule.id] = widget

        self._update_buttons()
        self._update_card_selection()

    def _update_card_selection(self):
        selected_id = self._selected_rule_id()
        for rule_id, w in self._item_widgets.items():
            w.set_selected(rule_id == selected_id)

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
    # Theme change hook
    # ─────────────────────────────────────────────

    def changeEvent(self, event):
        if event.type() == event.Type.PaletteChange:
            self._colors = ThemeColors(self)
            for w in self._item_widgets.values():
                w.refresh_theme()
            self._update_card_selection()
            self._apply_button_theme()
        super().changeEvent(event)

    # ─────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────

    def _on_add(self):
        dlg = RuleEditDialog(rule=None, queues=self.queues, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_rule = dlg.get_rule()
            self.rule_engine.add(new_rule)
            self._refresh_list()
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
            self._select_by_id(rule_id)

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
