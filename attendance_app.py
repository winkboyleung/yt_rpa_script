from __future__ import annotations

import glob
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QThread,
    QTimer,
    Signal,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 确保 exe / 源码两种运行方式都能 import 到项目代码
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from script.rpa_4_clock_in import analyze_attendance  # noqa: E402
from script.fill_attendance_template import fill_attendance_template  # noqa: E402

FILE_OPEN_MESSAGE = "文件正在打开，操作前请先关闭。"
ANOMALY_FILE_PATTERN = "打卡异常_*.xlsx"
# 优先 PNG，避免 ICO 多尺寸在标题栏显示不一致
APP_ICON_NAMES = ("app_icon.png", "app_icon.ico")


def _resource_path(filename: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).resolve().parent / filename


def _load_app_icon() -> QIcon | None:
    for name in APP_ICON_NAMES:
        path = _resource_path(name)
        if path.exists():
            return QIcon(str(path))
    return None


def _cleanup_anomaly_files(out_dir: str, log) -> None:
    """操作成功后删除临时异常表（含历史遗留的同类文件）。"""
    for path in glob.glob(os.path.join(out_dir, ANOMALY_FILE_PATTERN)):
        try:
            os.remove(path)
            log(f"- 已删除临时文件：{path}")
        except OSError as exc:
            log(f"- 删除临时文件失败：{path}（{exc}）")


def _permission_error_detail(exc: PermissionError) -> str:
    path = getattr(exc, "filename", None)
    if path:
        return f"{FILE_OPEN_MESSAGE}\n文件：{path}"
    return FILE_OPEN_MESSAGE


def _qdate_to_date(qd) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _default_target_date() -> date:
    return datetime.now().date() - timedelta(days=1)


def _configure_form_field(widget) -> None:
    """统一表单输入框尺寸策略，保证各行宽度一致。"""
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    widget.setMinimumHeight(36)
    widget.setFont(QFont("Microsoft YaHei", 10))


def _dropdown_arrow_image_url(filename: str, upward: bool = False) -> str:
    """生成下拉箭头图片，供 QSS 使用（Windows 上比纯 CSS 三角形更稳定）。"""
    cache_dir = Path(PROJECT_ROOT) / ".ui_cache"
    cache_dir.mkdir(exist_ok=True)
    arrow_path = cache_dir / filename
    if not arrow_path.exists():
        pm = QPixmap(12, 8)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#1677FF"))
        painter.setPen(Qt.NoPen)
        if upward:
            painter.drawPolygon(QPolygon([QPoint(0, 8), QPoint(12, 8), QPoint(6, 0)]))
        else:
            painter.drawPolygon(QPolygon([QPoint(0, 0), QPoint(12, 0), QPoint(6, 8)]))
        painter.end()
        pm.save(str(arrow_path))
    return arrow_path.as_posix()


_POPUP_ANIM_MS = 180


def _run_popup_open_animation(popup: QWidget, slide_px: int = 8) -> None:
    """下拉/日历弹出：淡入 + 轻微下滑，结束后移除特效避免后续卡顿。"""
    if popup is None or not popup.isVisible():
        return

    end_rect = popup.geometry()
    start_rect = QRect(
        end_rect.x(),
        end_rect.y() - slide_px,
        end_rect.width(),
        end_rect.height(),
    )
    popup.setGeometry(start_rect)

    effect = QGraphicsOpacityEffect(popup)
    effect.setOpacity(0.0)
    popup.setGraphicsEffect(effect)

    opacity_anim = QPropertyAnimation(effect, b"opacity", popup)
    opacity_anim.setDuration(_POPUP_ANIM_MS)
    opacity_anim.setStartValue(0.0)
    opacity_anim.setEndValue(1.0)
    opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

    geo_anim = QPropertyAnimation(popup, b"geometry", popup)
    geo_anim.setDuration(_POPUP_ANIM_MS)
    geo_anim.setStartValue(start_rect)
    geo_anim.setEndValue(end_rect)
    geo_anim.setEasingCurve(QEasingCurve.OutCubic)

    group = QParallelAnimationGroup(popup)
    group.addAnimation(opacity_anim)
    group.addAnimation(geo_anim)
    group.finished.connect(lambda: popup.setGraphicsEffect(None))
    group.start(QAbstractAnimation.DeleteWhenStopped)


class SmoothComboBox(QComboBox):
    def showPopup(self):
        super().showPopup()
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if popup is self.window():
            return
        _run_popup_open_animation(popup)


class CalendarDayDelegate(QStyledItemDelegate):
    """日历日期格：圆角选中/悬停，替代默认表格风格。"""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        text = index.data()
        if not text:
            painter.restore()
            return

        cell = option.rect.adjusted(4, 4, -4, -4)
        enabled = bool(option.state & QStyle.State_Enabled)

        if option.state & QStyle.State_Selected:
            painter.setBrush(QColor("#1677FF"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(cell, 8, 8)
            painter.setPen(QColor("#FFFFFF"))
        elif enabled and option.state & QStyle.State_MouseOver:
            painter.setBrush(QColor(22, 119, 255, 30))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(cell, 8, 8)
            painter.setPen(QColor("#1677FF"))
        elif enabled:
            painter.setPen(QColor(0, 0, 0, 220))
        else:
            painter.setPen(QColor(0, 0, 0, 90))

        painter.setFont(option.font)
        painter.drawText(option.rect, Qt.AlignCenter, str(text))
        painter.restore()


class ModernCalendarWidget(QCalendarWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("modernCalendar")
        self.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        self.setGridVisible(False)
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setMinimumSize(340, 300)
        self.setNavigationBarVisible(True)

        table = self.findChild(QTableView)
        if table is not None:
            table.setObjectName("modernCalendarTable")
            table.setShowGrid(False)
            table.setFocusPolicy(Qt.NoFocus)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setItemDelegate(CalendarDayDelegate(table))
            header = table.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignCenter)
            header.setSectionResizeMode(QHeaderView.Stretch)
            header.setFixedHeight(34)
            header.setHighlightSections(False)


class SmoothDateEdit(QDateEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cal = ModernCalendarWidget()
        self.setCalendarWidget(cal)
        self.setCalendarPopup(True)
        cal.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            popup = obj.window()
            if popup is not self.window():
                popup.setObjectName("calendarPopup")
                QTimer.singleShot(0, lambda p=popup: _run_popup_open_animation(p))
        return super().eventFilter(obj, event)


@dataclass(frozen=True)
class RunParams:
    punch_path: str
    template_path: str
    target_date: date
    lookback_days: int


class RunnerWorker(QObject):
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    file_locked = Signal(str)

    def __init__(self, params: RunParams):
        super().__init__()
        self._params = params

    def run(self):
        try:
            self._run_impl()
        except PermissionError as exc:
            self.file_locked.emit(_permission_error_detail(exc))
        except Exception:
            self.failed.emit(traceback.format_exc())

    def _run_impl(self):
        p = self._params

        if not os.path.exists(p.punch_path):
            raise FileNotFoundError(f"打卡文件不存在：{p.punch_path}")
        if not os.path.exists(p.template_path):
            raise FileNotFoundError(f"模板文件不存在：{p.template_path}")
        if not 1 <= p.lookback_days <= 7:
            raise ValueError("回溯天数仅支持 1~7")

        out_dir = os.path.dirname(os.path.abspath(p.template_path))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        anomaly_path = os.path.join(out_dir, f"打卡异常_{stamp}.xlsx")

        self.log.emit("步骤 1/2：生成整月异常表…")
        self.log.emit(f"- 打卡文件：{p.punch_path}")
        self.log.emit(f"- 异常输出：{anomaly_path}")
        analyze_attendance(p.punch_path, anomaly_path)

        self.log.emit("")
        self.log.emit("步骤 2/2：写入考勤模板（覆盖原文件）…")
        self.log.emit(f"- 模板文件：{p.template_path}")
        self.log.emit(f"- 目标日期：{p.target_date.isoformat()}")
        self.log.emit(f"- 回溯天数：{p.lookback_days}")

        # fill_attendance_template 的 reference_date 语义是“参考日”，实际写入的是参考日前 N 天
        reference_date = p.target_date + timedelta(days=1)
        fill_attendance_template(
            template_path=p.template_path,
            punch_path=p.punch_path,
            anomaly_path=anomaly_path,
            reference_date=reference_date,
            lookback_days=p.lookback_days,
            output_path=p.template_path,  # 覆盖原模板
        )

        self.log.emit("")
        self.log.emit("清理临时异常表…")
        _cleanup_anomaly_files(out_dir, self.log.emit)

        self.finished.emit("完成：已生成异常表并覆盖写入模板。")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("考勤自动填表")
        icon = _load_app_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self.setMinimumSize(1280, 1020)

        self._thread: QThread | None = None
        self._worker: RunnerWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("考勤自动填表")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        subtitle = QLabel("选择打卡文件与模板，设置日期与回溯天数，然后点击启动。")
        subtitle.setFont(QFont("Microsoft YaHei", 10))
        subtitle.setStyleSheet("color: rgba(0,0,0,0.65);")
        layout.addWidget(subtitle)

        layout.addWidget(self._build_form_group())
        layout.addWidget(self._build_actions_row())
        layout.addWidget(self._build_log_group(), stretch=1)

        self._apply_ding_style()
        self._style_premium_controls()

    def _build_form_group(self) -> QWidget:
        gb = QGroupBox("参数")
        gb.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        gl = QGridLayout(gb)
        gl.setColumnStretch(1, 1)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(10)

        self.punch_edit = QLineEdit()
        self.punch_edit.setObjectName("formLineEdit")
        self.punch_edit.setPlaceholderText("请选择打卡文件（.xls/.xlsx）")
        _configure_form_field(self.punch_edit)
        self.punch_btn = QPushButton("选择…")
        self.punch_btn.setMinimumHeight(36)
        self.punch_btn.clicked.connect(self._choose_punch)

        self.template_edit = QLineEdit()
        self.template_edit.setObjectName("formLineEdit")
        self.template_edit.setPlaceholderText("请选择模板文件（.xlsx）")
        _configure_form_field(self.template_edit)
        self.template_btn = QPushButton("选择…")
        self.template_btn.setMinimumHeight(36)
        self.template_btn.clicked.connect(self._choose_template)

        self.date_edit = SmoothDateEdit()
        self.date_edit.setObjectName("targetDateEdit")
        self.date_edit.setDisplayFormat("yyyy 年 MM 月 dd 日")
        _configure_form_field(self.date_edit)
        td = _default_target_date()
        self.date_edit.setDate(datetime(td.year, td.month, td.day))

        self.lookback_combo = SmoothComboBox()
        self.lookback_combo.setObjectName("lookbackCombo")
        self.lookback_combo.setMaxVisibleItems(7)
        _configure_form_field(self.lookback_combo)
        _lookback_labels = {
            1: "昨天（1天）",
            2: "前两天（2天）",
            3: "前三天（3天）",
            4: "前四天（4天）",
            5: "前五天（5天）",
            6: "前六天（6天）",
            7: "前七天（7天）",
        }
        for days in range(1, 8):
            self.lookback_combo.addItem(_lookback_labels[days], days)
        self.lookback_combo.setCurrentIndex(0)

        lookback_view = QListView()
        lookback_view.setObjectName("lookbackList")
        lookback_view.setSpacing(2)
        lookback_view.setUniformItemSizes(True)
        lookback_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.lookback_combo.setView(lookback_view)

        gl.addWidget(QLabel("打卡文件"), 0, 0)
        gl.addWidget(self.punch_edit, 0, 1)
        gl.addWidget(self.punch_btn, 0, 2)

        gl.addWidget(QLabel("模板文件"), 1, 0)
        gl.addWidget(self.template_edit, 1, 1)
        gl.addWidget(self.template_btn, 1, 2)

        btn_size = self.punch_btn.sizeHint()
        date_placeholder = QWidget()
        date_placeholder.setFixedSize(btn_size)
        lookback_placeholder = QWidget()
        lookback_placeholder.setFixedSize(btn_size)

        gl.addWidget(QLabel("目标日期"), 2, 0)
        gl.addWidget(self.date_edit, 2, 1)
        gl.addWidget(date_placeholder, 2, 2)

        gl.addWidget(QLabel("处理范围"), 3, 0)
        gl.addWidget(self.lookback_combo, 3, 1)
        gl.addWidget(lookback_placeholder, 3, 2)

        return gb

    def _build_actions_row(self) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        self.start_btn = QPushButton("启动")
        self.start_btn.setMinimumHeight(36)
        self.start_btn.clicked.connect(self._start)

        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.setMinimumHeight(36)
        self.clear_btn.clicked.connect(lambda: self.log_edit.setPlainText(""))

        hl.addWidget(self.start_btn)
        hl.addWidget(self.clear_btn)
        hl.addStretch(1)
        return row

    def _build_log_group(self) -> QWidget:
        gb = QGroupBox("运行日志")
        gb.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        vl = QVBoxLayout(gb)
        vl.setContentsMargins(10, 10, 10, 10)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 10))
        vl.addWidget(self.log_edit)
        return gb

    def _apply_ding_style(self):
        # 简洁的“钉钉风格”蓝色主题（不依赖外部资源）
        self.setStyleSheet(
            """
            QMainWindow { background: #F5F7FA; }
            QGroupBox {
                background: #FFFFFF;
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 10px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: rgba(0,0,0,0.75);
            }
            QLabel { color: rgba(0,0,0,0.85); font-family: "Microsoft YaHei"; }
            QLineEdit#formLineEdit, QTextEdit {
                background: #FFFFFF;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #1677FF;
            }
            QLineEdit#formLineEdit:focus, QTextEdit:focus {
                border: 1px solid #1677FF;
            }
            QPushButton {
                background: #1677FF;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-family: "Microsoft YaHei";
                font-weight: 600;
            }
            QPushButton:hover { background: #3C8CFF; }
            QPushButton:pressed { background: #0E63D6; }
            QPushButton:disabled { background: rgba(22,119,255,0.35); }
            """
        )

        # 次按钮做“描边”风格
        self.clear_btn.setStyleSheet(
            """
            QPushButton {
                background: #FFFFFF;
                color: #1677FF;
                border: 1px solid rgba(22,119,255,0.55);
                border-radius: 10px;
                padding: 8px 14px;
                font-family: "Microsoft YaHei";
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(22,119,255,0.06); }
            QPushButton:pressed { background: rgba(22,119,255,0.12); }
            """
        )

    def _style_premium_controls(self):
        arrow_down = _dropdown_arrow_image_url("dropdown_arrow_down.png")
        arrow_up = _dropdown_arrow_image_url("dropdown_arrow_up.png", upward=True)
        arrow_styles = f"""
            QDateEdit#targetDateEdit::down-arrow,
            QComboBox#lookbackCombo::down-arrow {{
                width: 12px;
                height: 8px;
                image: url({arrow_down});
            }}
            QComboBox#lookbackCombo::down-arrow:on {{
                image: url({arrow_up});
            }}
        """
        self.setStyleSheet(
            self.styleSheet()
            + """
            QLineEdit#formLineEdit {
                min-height: 36px;
                padding: 8px 10px;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #F8FAFF
                );
                border: 1px solid rgba(22, 119, 255, 0.22);
                border-radius: 10px;
                color: rgba(0, 0, 0, 0.88);
                font-family: "Microsoft YaHei";
            }
            QDateEdit#targetDateEdit, QComboBox#lookbackCombo {
                min-height: 36px;
                padding: 8px 40px 8px 10px;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #F8FAFF
                );
                border: 1px solid rgba(22, 119, 255, 0.22);
                border-radius: 10px;
                color: rgba(0, 0, 0, 0.88);
                font-family: "Microsoft YaHei";
            }
            QLineEdit#formLineEdit:hover, QDateEdit#targetDateEdit:hover, QComboBox#lookbackCombo:hover {
                border: 1px solid rgba(22, 119, 255, 0.45);
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #F2F7FF
                );
            }
            QLineEdit#formLineEdit:focus, QDateEdit#targetDateEdit:focus, QComboBox#lookbackCombo:focus {
                border: 1px solid #1677FF;
                background: #FFFFFF;
            }
            QLineEdit#formLineEdit:disabled, QDateEdit#targetDateEdit:disabled, QComboBox#lookbackCombo:disabled {
                background: #F5F7FA;
                color: rgba(0, 0, 0, 0.35);
                border: 1px solid rgba(0, 0, 0, 0.08);
            }
            QDateEdit#targetDateEdit::drop-down,
            QComboBox#lookbackCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 36px;
                border-left: 1px solid rgba(22, 119, 255, 0.14);
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                background: rgba(22, 119, 255, 0.06);
            }
            QDateEdit#targetDateEdit::drop-down:hover,
            QComboBox#lookbackCombo::drop-down:hover {
                background: rgba(22, 119, 255, 0.12);
            }
            """
            + arrow_styles
            + """
            QComboBox#lookbackCombo QAbstractItemView#lookbackList {
                background: #FFFFFF;
                border: 1px solid rgba(22, 119, 255, 0.22);
                border-radius: 10px;
                padding: 6px;
                outline: 0;
                selection-background-color: transparent;
            }
            QComboBox#lookbackCombo QAbstractItemView#lookbackList::item {
                min-height: 36px;
                padding: 8px 12px;
                border-radius: 8px;
                color: rgba(0, 0, 0, 0.85);
            }
            QComboBox#lookbackCombo QAbstractItemView#lookbackList::item:hover {
                background: rgba(22, 119, 255, 0.08);
                color: #1677FF;
            }
            QComboBox#lookbackCombo QAbstractItemView#lookbackList::item:selected {
                background: rgba(22, 119, 255, 0.14);
                color: #1677FF;
                font-weight: 600;
            }
            QWidget#calendarPopup {
                background: #FFFFFF;
                border: 1px solid rgba(22, 119, 255, 0.18);
                border-radius: 14px;
                padding: 4px;
            }
            QCalendarWidget#modernCalendar {
                background: #FFFFFF;
                border: none;
                border-radius: 12px;
                padding: 8px 10px 12px 10px;
            }
            QCalendarWidget#modernCalendar QWidget#qt_calendar_navigationbar {
                background: transparent;
                border: none;
                min-height: 44px;
                padding: 0 4px;
            }
            QCalendarWidget#modernCalendar QToolButton {
                color: #1677FF;
                background: rgba(22, 119, 255, 0.06);
                border: 1px solid rgba(22, 119, 255, 0.12);
                border-radius: 8px;
                min-width: 32px;
                min-height: 32px;
                padding: 4px;
                font-family: "Microsoft YaHei";
                font-weight: 600;
            }
            QCalendarWidget#modernCalendar QToolButton:hover {
                background: rgba(22, 119, 255, 0.14);
                border: 1px solid rgba(22, 119, 255, 0.28);
            }
            QCalendarWidget#modernCalendar QToolButton:pressed {
                background: rgba(22, 119, 255, 0.22);
            }
            QCalendarWidget#modernCalendar QSpinBox,
            QCalendarWidget#modernCalendar QComboBox {
                background: #F5F8FF;
                border: 1px solid rgba(22, 119, 255, 0.16);
                border-radius: 8px;
                padding: 4px 8px;
                color: rgba(0, 0, 0, 0.88);
                font-family: "Microsoft YaHei";
                font-weight: 600;
            }
            QCalendarWidget#modernCalendar QSpinBox:hover,
            QCalendarWidget#modernCalendar QComboBox:hover {
                border: 1px solid rgba(22, 119, 255, 0.35);
                background: #FFFFFF;
            }
            QCalendarWidget#modernCalendar QTableView#modernCalendarTable {
                background: #FFFFFF;
                border: none;
                outline: 0;
                selection-background-color: transparent;
            }
            QCalendarWidget#modernCalendar QHeaderView::section {
                background: transparent;
                border: none;
                color: rgba(0, 0, 0, 0.45);
                font-family: "Microsoft YaHei";
                font-size: 12px;
                font-weight: 600;
                padding: 6px 0 10px 0;
            }
            """
        )

    def _choose_punch(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择打卡文件",
            "",
            "Excel 文件 (*.xls *.xlsx);;所有文件 (*.*)",
        )
        if path:
            self.punch_edit.setText(path)

    def _choose_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择模板文件",
            "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)",
        )
        if path:
            self.template_edit.setText(path)

    def _append_log(self, text: str):
        self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def _set_running(self, running: bool):
        self.start_btn.setDisabled(running)
        self.punch_btn.setDisabled(running)
        self.template_btn.setDisabled(running)
        self.punch_edit.setDisabled(running)
        self.template_edit.setDisabled(running)
        self.date_edit.setDisabled(running)
        self.lookback_combo.setDisabled(running)

    def _start(self):
        punch = self.punch_edit.text().strip()
        template = self.template_edit.text().strip()
        if not punch or not template:
            QMessageBox.warning(self, "提示", "请先选择打卡文件与模板文件。")
            return

        target = _qdate_to_date(self.date_edit.date())
        days = int(self.lookback_combo.currentData())

        params = RunParams(
            punch_path=punch,
            template_path=template,
            target_date=target,
            lookback_days=days,
        )

        self._append_log("开始执行…")
        self._set_running(True)

        self._thread = QThread()
        self._worker = RunnerWorker(params)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.file_locked.connect(self._on_file_locked)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.file_locked.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_finished(self, msg: str):
        self._append_log("")
        self._append_log(msg)
        self._set_running(False)
        QMessageBox.information(self, "完成", msg)

    def _on_failed(self, err: str):
        self._append_log("")
        self._append_log("执行失败：")
        self._append_log(err)
        self._set_running(False)
        QMessageBox.critical(self, "失败", "执行失败，详情见日志。")

    def _on_file_locked(self, msg: str):
        self._append_log("")
        self._append_log(msg)
        self._set_running(False)
        QMessageBox.warning(self, "提示", FILE_OPEN_MESSAGE)


def main():
    app = QApplication(sys.argv)
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    _dropdown_arrow_image_url("dropdown_arrow_down.png")
    _dropdown_arrow_image_url("dropdown_arrow_up.png", upward=True)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

