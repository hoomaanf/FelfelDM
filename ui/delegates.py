from PyQt6.QtWidgets import QStyledItemDelegate, QApplication, QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPalette, QPainter, QBrush, QPen

from utils.style import theme_color


class ProgressDelegate(QStyledItemDelegate):
    """Slim rounded progress bar with the percentage next to it.

    The bar colour follows the row's status colour (blue while downloading,
    green when complete, amber when paused, red on error).
    """

    COL_PROGRESS = 2
    COL_STATUS = 6
    BAR_H = 8

    def paint(self, painter, option, index):
        if index.column() != self.COL_PROGRESS:
            super().paint(painter, option, index)
            return

        text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        try:
            val = max(0, min(100, int(str(text).replace("%", ""))))
        except (ValueError, TypeError):
            super().paint(painter, option, index)
            return

        # 1) row background (selection / hover / border) without text
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        # 2) geometry
        area = option.rect.adjusted(12, 0, -12, 0)
        show_text = area.width() >= 90
        text_w = 38 if show_text else 0
        gap = 8 if show_text else 0
        h = float(self.BAR_H)
        bar = QRectF(
            area.x(),
            option.rect.y() + (option.rect.height() - h) / 2,
            max(10, area.width() - text_w - gap),
            h,
        )

        # 3) colours
        dark = option.palette.color(QPalette.ColorRole.Window).lightness() < 128
        track = QColor(255, 255, 255, 26) if dark else QColor(0, 0, 0, 22)
        if val >= 100:
            fill = theme_color("success")
        else:
            status_color = index.sibling(index.row(), self.COL_STATUS).data(
                Qt.ItemDataRole.ForegroundRole
            )
            fill = QColor(status_color) if isinstance(status_color, QColor) else theme_color("accent")
            if status_color is not None and fill == theme_color("muted"):
                fill = theme_color("accent")

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(bar, h / 2, h / 2)
        if val > 0:
            fw = max(h, bar.width() * val / 100.0)
            painter.setBrush(QBrush(fill))
            painter.drawRoundedRect(QRectF(bar.x(), bar.y(), fw, h), h / 2, h / 2)

        if show_text:
            font = option.font
            font.setPointSizeF(max(8.0, font.pointSizeF() - 0.5))
            painter.setFont(font)
            painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Text)))
            painter.drawText(
                QRectF(bar.right() + gap, option.rect.y(), text_w, option.rect.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                f"{val}%",
            )
        painter.restore()
