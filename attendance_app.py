from __future__ import annotations

import glob
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
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
        if p.lookback_days not in (1, 2, 3, 4):
            raise ValueError("回溯天数仅支持 1/2/3/4")

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

    def _build_form_group(self) -> QWidget:
        gb = QGroupBox("参数")
        gb.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        gl = QGridLayout(gb)
        gl.setColumnStretch(1, 1)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(10)

        self.punch_edit = QLineEdit()
        self.punch_edit.setPlaceholderText("请选择打卡文件（.xls/.xlsx）")
        self.punch_btn = QPushButton("选择…")
        self.punch_btn.clicked.connect(self._choose_punch)

        self.template_edit = QLineEdit()
        self.template_edit.setPlaceholderText("请选择模板文件（.xlsx）")
        self.template_btn = QPushButton("选择…")
        self.template_btn.clicked.connect(self._choose_template)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        td = _default_target_date()
        self.date_edit.setDate(datetime(td.year, td.month, td.day))

        self.lookback_combo = QComboBox()
        self.lookback_combo.addItem("昨天（1天）", 1)
        self.lookback_combo.addItem("前两天（2天）", 2)
        self.lookback_combo.addItem("前三天（3天）", 3)
        self.lookback_combo.addItem("前四天（4天）", 4)
        self.lookback_combo.setCurrentIndex(0)

        gl.addWidget(QLabel("打卡文件"), 0, 0)
        gl.addWidget(self.punch_edit, 0, 1)
        gl.addWidget(self.punch_btn, 0, 2)

        gl.addWidget(QLabel("模板文件"), 1, 0)
        gl.addWidget(self.template_edit, 1, 1)
        gl.addWidget(self.template_btn, 1, 2)

        gl.addWidget(QLabel("目标日期"), 2, 0)
        gl.addWidget(self.date_edit, 2, 1)
        gl.addItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum), 2, 2)

        gl.addWidget(QLabel("处理范围"), 3, 0)
        gl.addWidget(self.lookback_combo, 3, 1)
        gl.addItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum), 3, 2)

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
            QLineEdit, QDateEdit, QComboBox, QTextEdit {
                background: #FFFFFF;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #1677FF;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {
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
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

