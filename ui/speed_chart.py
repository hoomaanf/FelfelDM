# ui/speed_chart.py
"""
Real-time speed chart using PyQtChart.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel

from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QCategoryAxis

from utils.helpers import format_speed

logger = logging.getLogger(__name__)


class SpeedChart(QWidget):
    """
    Widget that displays a real-time speed chart.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Speed Chart")
        self.setMinimumSize(600, 400)

        self._speed_history: List[int] = []
        self._max_points = 60  # 60 points (1 minute with 1s interval)
        self._timer: Optional[QTimer] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Chart view
        self._chart_view = QChartView()
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self._chart_view)

        # Controls
        controls = QHBoxLayout()
        self._status_label = QLabel("Speed: 0 B/s")
        controls.addWidget(self._status_label)

        controls.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        controls.addWidget(clear_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        controls.addWidget(close_btn)

        layout.addLayout(controls)

        # Setup chart
        self._series = QLineSeries()
        self._series.setName("Download Speed")
        self._series.setColor(QColor("#89b4fa"))

        self._chart = QChart()
        self._chart.addSeries(self._series)
        self._chart.setTitle("Download Speed Over Time")
        self._chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        # Axes
        self._axis_x = QValueAxis()
        self._axis_x.setRange(0, self._max_points)
        self._axis_x.setTitleText("Time (s)")
        self._axis_x.setLabelFormat("%d")

        self._axis_y = QValueAxis()
        self._axis_y.setTitleText("Speed (B/s)")
        self._axis_y.setLabelFormat("%.0f")

        self._chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)

        self._series.attachAxis(self._axis_x)
        self._series.attachAxis(self._axis_y)

        self._chart_view.setChart(self._chart)

        # Start timer for auto-update
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_chart)
        self._timer.start(1000)

    def add_speed(self, speed: int) -> None:
        """Add a new speed data point."""
        self._speed_history.append(speed)
        if len(self._speed_history) > self._max_points:
            self._speed_history.pop(0)

        # Update status label
        self._status_label.setText(f"Speed: {format_speed(speed)}")

        # Update chart automatically (the timer will handle it)

    def _update_chart(self) -> None:
        """Update the chart with current data."""
        if not self._speed_history:
            return

        # Clear and repopulate series
        self._series.clear()
        for i, speed in enumerate(self._speed_history):
            self._series.append(i, speed)

        # Adjust Y axis range
        max_speed = max(self._speed_history) if self._speed_history else 1024
        if max_speed == 0:
            max_speed = 1024
        self._axis_y.setRange(0, max_speed * 1.2)

        # Adjust X axis range
        if len(self._speed_history) < self._max_points:
            self._axis_x.setRange(0, self._max_points)
        else:
            self._axis_x.setRange(
                len(self._speed_history) - self._max_points,
                len(self._speed_history)
            )

        self._chart.update()

    def clear(self) -> None:
        """Clear the chart data."""
        self._speed_history.clear()
        self._series.clear()
        self._status_label.setText("Speed: 0 B/s")
        self._chart.update()

    def closeEvent(self, event) -> None:
        """Handle close event to stop timer."""
        if self._timer:
            self._timer.stop()
        super().closeEvent(event)
