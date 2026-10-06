"""Dashboard charts, built on QtCharts."""

from __future__ import annotations

import calendar
from typing import Callable

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QStackedLayout, QToolTip, QVBoxLayout

from expense_tracker.services.summary import CategoryTotal
from expense_tracker.ui.style import ACCENT, BORDER, MUTED, SURFACE, TEXT

Money = Callable[[int], str]


def _axis_format(currency: str) -> str:
    """printf-style label format for a money axis, e.g. ``$%.0f``."""
    return currency.replace("%", "%%") + "%.0f"


def _style_axis(axis) -> None:
    font = QFont("Segoe UI", 8)
    axis.setLabelsFont(font)
    axis.setLabelsColor(QColor(MUTED))
    axis.setLinePenColor(QColor(BORDER))
    axis.setGridLineColor(QColor("#EEF1F5"))


class ChartCard(QFrame):
    """A titled card holding one chart, with a message shown when there is no data."""

    def __init__(self, title: str, empty_text: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(290)

        self.title = QLabel(title)
        self.title.setObjectName("sectionTitle")

        self.chart = QChart()
        self.chart.setBackgroundBrush(QColor(SURFACE))
        self.chart.setBackgroundRoundness(0)
        self.chart.setMargins(QMargins(0, 0, 0, 0))
        self.chart.legend().setFont(QFont("Segoe UI", 9))
        self.chart.legend().setLabelColor(QColor(TEXT))
        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet(f"background: {SURFACE};")

        self.empty = QLabel(empty_text)
        self.empty.setObjectName("emptyLabel")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._stack = QStackedLayout()
        self._stack.addWidget(self.view)
        self._stack.addWidget(self.empty)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 8)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addLayout(self._stack, 1)

    def _reset(self, has_data: bool) -> None:
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)
        self._stack.setCurrentWidget(self.view if has_data else self.empty)

    @property
    def is_empty(self) -> bool:
        return self._stack.currentWidget() is self.empty


class CategoryDonut(ChartCard):
    """Spending by category for one month, in the categories' own colors."""

    def __init__(self) -> None:
        super().__init__("By category", "No spending this month")
        self.chart.legend().hide()
        self.series: QPieSeries | None = None

    def set_data(self, breakdown: list[CategoryTotal], money: Money) -> None:
        self._reset(bool(breakdown))
        self.series = None
        if not breakdown:
            return
        series = QPieSeries()
        series.setHoleSize(0.55)
        series.setPieSize(0.86)
        for entry in breakdown:
            slice_ = series.append(entry.name, entry.total_cents / 100)
            slice_.setColor(QColor(entry.color))
            slice_.setBorderColor(QColor(SURFACE))
            slice_.setBorderWidth(2)
            slice_.setProperty(
                "tip",
                f"{entry.name}: {money(entry.total_cents)} ({entry.percent:.1f}%)",
            )
        series.hovered.connect(self._on_hover)
        self.chart.addSeries(series)
        self.series = series

    def _on_hover(self, slice_, hovering: bool) -> None:
        slice_.setExploded(hovering)
        slice_.setExplodeDistanceFactor(0.05)
        if hovering:
            QToolTip.showText(QCursor.pos(), slice_.property("tip"), self.view)
        else:
            QToolTip.hideText()


class MonthlyBars(ChartCard):
    """Total spending per month, oldest month on the left."""

    def __init__(self) -> None:
        super().__init__("Last 12 months", "No spending in these months")
        self.chart.legend().hide()
        self.bar_set: QBarSet | None = None
        self._tips: list[str] = []

    def set_data(
        self, totals: list[tuple[int, int, int]], currency: str, money: Money
    ) -> None:
        has_data = any(cents for _, _, cents in totals)
        self._reset(has_data)
        self.bar_set = None
        if not has_data:
            return

        bar_set = QBarSet("Spending")
        bar_set.setColor(QColor(ACCENT))
        bar_set.setBorderColor(QColor(ACCENT))
        labels = []
        self._tips = []
        for year, month, cents in totals:
            bar_set.append(cents / 100)
            labels.append(calendar.month_abbr[month])
            self._tips.append(f"{calendar.month_name[month]} {year}: {money(cents)}")
        bar_set.hovered.connect(self._on_hover)

        series = QBarSeries()
        series.setBarWidth(0.6)
        series.append(bar_set)
        self.chart.addSeries(series)

        x_axis = QBarCategoryAxis()
        x_axis.append(labels)
        x_axis.setGridLineVisible(False)
        y_axis = QValueAxis()
        y_axis.setLabelFormat(_axis_format(currency))
        y_axis.setRange(0, max(cents for _, _, cents in totals) / 100)
        y_axis.applyNiceNumbers()
        for axis, alignment in (
            (x_axis, Qt.AlignmentFlag.AlignBottom),
            (y_axis, Qt.AlignmentFlag.AlignLeft),
        ):
            _style_axis(axis)
            self.chart.addAxis(axis, alignment)
            series.attachAxis(axis)
        self.bar_set = bar_set

    def _on_hover(self, hovering: bool, index: int) -> None:
        if hovering and 0 <= index < len(self._tips):
            QToolTip.showText(QCursor.pos(), self._tips[index], self.view)
        else:
            QToolTip.hideText()


class CumulativeLines(ChartCard):
    """Running total through the month, compared with the month before."""

    def __init__(self) -> None:
        super().__init__("Cumulative spending", "No spending in either month")
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.current_series: QLineSeries | None = None
        self.previous_series: QLineSeries | None = None
        self._money: Money = str

    def set_data(
        self,
        current: list[int],
        previous: list[int],
        current_label: str,
        previous_label: str,
        currency: str,
        money: Money,
    ) -> None:
        highest = max([*current, *previous, 0])
        self._reset(highest > 0)
        self.current_series = self.previous_series = None
        self._money = money
        if highest == 0:
            return

        previous_series = QLineSeries()
        previous_series.setName(previous_label)
        previous_series.setPen(QPen(QColor("#A0A8B4"), 2, Qt.PenStyle.DashLine))
        current_series = QLineSeries()
        current_series.setName(current_label)
        current_series.setPen(QPen(QColor(ACCENT), 3))
        for series, values in ((previous_series, previous), (current_series, current)):
            series.append([QPointF(day, cents / 100) for day, cents in enumerate(values, 1)])
            series.hovered.connect(self._on_hover)
            self.chart.addSeries(series)

        x_axis = QValueAxis()
        x_axis.setRange(1, 31)
        x_axis.setTickCount(7)
        x_axis.setLabelFormat("%d")
        x_axis.setGridLineVisible(False)
        y_axis = QValueAxis()
        y_axis.setLabelFormat(_axis_format(currency))
        y_axis.setRange(0, highest / 100)
        y_axis.applyNiceNumbers()
        for axis, alignment in (
            (x_axis, Qt.AlignmentFlag.AlignBottom),
            (y_axis, Qt.AlignmentFlag.AlignLeft),
        ):
            _style_axis(axis)
            self.chart.addAxis(axis, alignment)
            previous_series.attachAxis(axis)
            current_series.attachAxis(axis)
        self.current_series = current_series
        self.previous_series = previous_series

    def _on_hover(self, point: QPointF, hovering: bool) -> None:
        if not hovering:
            QToolTip.hideText()
            return
        series = self.sender()
        day = max(1, min(round(point.x()), series.count()))
        cents = round(series.at(day - 1).y() * 100)
        QToolTip.showText(
            QCursor.pos(), f"{series.name()}, day {day}: {self._money(cents)}", self.view
        )
