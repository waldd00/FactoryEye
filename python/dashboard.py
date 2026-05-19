# ─────────────────────────────────────────────
#  SmartQualityControl — dashboard.py
# ─────────────────────────────────────────────

import sys, os, time, argparse
from datetime import datetime

# torch/YOLO must be imported BEFORE PyQt5 on Windows to avoid DLL conflicts
try:
    import torch
    from ultralytics import YOLO
except Exception:
    pass

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QTextEdit, QFrame,
    QGroupBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont

sys.path.insert(0, os.path.dirname(__file__))
from mock_plc import MockPLC
from vision   import VisionSystem
from agent    import QualityAgent
from config   import DEFECT_THRESHOLD, INSPECTION_DELAY, AGENT_TRIGGER_RATE
from report   import ShiftReport

# ── Palette ──────────────────────────────────
BG      = "#141414"
PANEL   = "#1e1e1e"
BORDER  = "#2e2e2e"
TXT     = "#cccccc"
DIM     = "#555555"
GREEN   = "#00c853"
RED     = "#d32f2f"
YELLOW  = "#f9a825"
WHITE   = "#eeeeee"


# ─────────────────────────────────────────────
#  Worker — production loop
# ─────────────────────────────────────────────
class ProductionWorker(QThread):
    stats_updated = pyqtSignal(dict)
    frame_ready   = pyqtSignal(object)   # numpy BGR array
    log_msg       = pyqtSignal(str)
    alarm         = pyqtSignal(str)

    def __init__(self, plc, vision, agent):
        super().__init__()
        self.plc    = plc
        self.vision = vision
        self.agent  = agent
        self._active = False

    def run(self):
        self._active = True
        last_inspect = 0.0
        FPS          = 15

        while self._active:
            now = time.time()

            if not self.plc.is_line_running():
                time.sleep(1 / FPS)
                continue

            # Always advance video and emit for smooth display
            frame = self.vision.read_frame()
            if frame is not None:
                self.frame_ready.emit(frame)

            # Inspection every INSPECTION_DELAY seconds
            if now - last_inspect >= INSPECTION_DELAY:
                last_inspect = now

                is_defective = self.vision.inspect()
                dets = self.vision.get_last_detections()

                # Show annotated frame at inspection moment
                ann = self.vision.get_last_annotated()
                if ann is not None:
                    self.frame_ready.emit(ann)

                # Only count when a bolt/part is actually detected in frame
                if dets:
                    self.plc.signal_product_detected()
                    self.plc.signal_defective(is_defective)

                    total, defects = self.plc.get_counts()
                    rate = (defects / total * 100.0) if total > 0 else 0.0
                    self.plc.update_defect_rate(rate)

                    status = "DEFECTIVE" if is_defective else "OK      "
                    ts = datetime.now().strftime("%H:%M:%S")
                    self.log_msg.emit(
                        f"{ts}  [{status}]  Total:{total:5d}  Defects:{defects:4d}  Rate:{rate:5.1f}%"
                    )
                    self.stats_updated.emit({
                        'total': total, 'defects': defects,
                        'rate': rate, 'running': self.plc.is_line_running(),
                    })

                    if rate >= DEFECT_THRESHOLD:
                        self.alarm.emit(f"HIGH DEFECT RATE: {rate:.1f}% >= {DEFECT_THRESHOLD:.0f}%")

                    lbl = dets[0]["label"] if dets else "unknown"
                    advice = self.agent.analyze(total, defects, rate, lbl)
                    if advice:
                        sev = advice.get("severity", "ok").upper()
                        rec = advice.get("recommendation", "")
                        act = advice.get("action", "none")
                        self.log_msg.emit(f"         [AGENT/{sev}] {rec} -> {act}")

            time.sleep(1 / FPS)

    def halt(self):
        self._active = False


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def _frame_to_pixmap(frame) -> QPixmap:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape
    qi = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qi)

def _stat_label(val: str, color: str = WHITE) -> QLabel:
    lbl = QLabel(val)
    lbl.setFont(QFont("Consolas", 22, QFont.Bold))
    lbl.setStyleSheet(f"color: {color};")
    return lbl

def _cap_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {DIM}; font-family: Consolas; font-size: 10px;")
    return lbl

def _btn(text: str, color: str) -> QPushButton:
    b = QPushButton(text)
    b.setMinimumHeight(32)
    b.setStyleSheet(f"""
        QPushButton {{
            color:{color}; border:1px solid {color};
            background:transparent;
            font-family:Consolas; font-size:11px; font-weight:bold;
            letter-spacing:1px; padding:2px 8px;
        }}
        QPushButton:hover   {{ background:{color}22; }}
        QPushButton:pressed {{ background:{color}55; }}
    """)
    return b

def _group(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setStyleSheet(f"""
        QGroupBox {{
            color:{DIM}; border:1px solid {BORDER};
            margin-top:14px; padding-top:6px;
            font-family:Consolas; font-size:10px; letter-spacing:1px;
        }}
        QGroupBox::title {{ subcontrol-origin:margin; left:8px; padding:0 4px; }}
    """)
    return g


# ─────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, defect_prob: float = 0.2):
        super().__init__()
        self.setWindowTitle("SmartQualityControl")
        self.resize(1100, 650)
        self.setStyleSheet(f"background:{BG}; color:{TXT};")

        self._shift_report = ShiftReport()

        self.plc    = MockPLC(defect_probability=defect_prob)
        self.vision = VisionSystem(display=False, sim_defect_prob=defect_prob)
        self.agent  = QualityAgent()

        self._build_ui()
        self._make_worker()

    # ── UI ────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        hl = QHBoxLayout(root)
        hl.setContentsMargins(8, 8, 8, 8)
        hl.setSpacing(8)

        # ── Left: video panel ─────────────────
        left = QVBoxLayout()
        vid_grp = _group("CAMERA / VIDEO FEED")
        vl = QVBoxLayout(vid_grp)
        self.video_lbl = QLabel()
        self.video_lbl.setAlignment(Qt.AlignCenter)
        self.video_lbl.setMinimumSize(640, 400)
        self.video_lbl.setStyleSheet(f"background:{PANEL};")
        self.video_lbl.setText("[ waiting for start ]")
        vl.addWidget(self.video_lbl)
        left.addWidget(vid_grp)

        # Line status below video
        self.status_lbl = QLabel("LINE: IDLE")
        self.status_lbl.setFont(QFont("Consolas", 11, QFont.Bold))
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet(
            f"color:{DIM}; background:{PANEL}; border:1px solid {BORDER}; padding:4px;"
        )
        left.addWidget(self.status_lbl)
        hl.addLayout(left, stretch=3)

        # ── Right: stats + controls + log ─────
        right = QVBoxLayout()
        right.setSpacing(6)

        # Stats
        stats_grp = _group("PRODUCTION STATS")
        sg = QGridLayout(stats_grp)
        sg.setSpacing(4)

        self.v_total   = _stat_label("--")
        self.v_defects = _stat_label("--")
        self.v_rate    = _stat_label("--")

        sg.addWidget(_cap_label("TOTAL PRODUCTS"), 0, 0)
        sg.addWidget(_cap_label("DEFECTS"),        0, 1)
        sg.addWidget(_cap_label("DEFECT RATE"),    0, 2)
        sg.addWidget(self.v_total,   1, 0)
        sg.addWidget(self.v_defects, 1, 1)
        sg.addWidget(self.v_rate,    1, 2)
        right.addWidget(stats_grp)

        # Controls
        ctrl_grp = _group("CONTROLS")
        cl = QGridLayout(ctrl_grp)
        cl.setSpacing(4)
        self.btn_start  = _btn("START",  GREEN)
        self.btn_stop   = _btn("STOP",   RED)
        self.btn_reset  = _btn("RESET",  YELLOW)
        self.btn_report = _btn("REPORT", "#1565c0")
        cl.addWidget(self.btn_start,  0, 0)
        cl.addWidget(self.btn_stop,   0, 1)
        cl.addWidget(self.btn_reset,  1, 0)
        cl.addWidget(self.btn_report, 1, 1)
        right.addWidget(ctrl_grp)

        # Log
        log_grp = _group("PLC / INSPECTION LOG")
        ll = QVBoxLayout(log_grp)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            f"background:{PANEL}; color:#999999; font-family:Consolas; font-size:10px; border:none;"
        )
        ll.addWidget(self.log)
        right.addWidget(log_grp, stretch=1)

        hl.addLayout(right, stretch=1)

        # Wire buttons
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_report.clicked.connect(self._report)

        self.statusBar().setStyleSheet(f"color:{DIM}; font-family:Consolas; font-size:10px;")
        self.statusBar().showMessage("Ready — press START")

    # ── Worker ────────────────────────────────
    def _make_worker(self):
        self.worker = ProductionWorker(self.plc, self.vision, self.agent)
        self.worker.stats_updated.connect(self._on_stats)
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.log_msg.connect(self._on_log)
        self.worker.alarm.connect(self._on_alarm)

    # ── Slots ─────────────────────────────────
    @pyqtSlot(object)
    def _on_frame(self, frame):
        if frame is None:
            return
        px = _frame_to_pixmap(frame)
        scaled = px.scaled(
            self.video_lbl.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_lbl.setPixmap(scaled)

    @pyqtSlot(dict)
    def _on_stats(self, d):
        total, defects, rate = d['total'], d['defects'], d['rate']
        self.v_total.setText(str(total))
        self.v_defects.setText(str(defects))
        self.v_defects.setStyleSheet(f"color:{RED if defects else WHITE}; font-size:22px; font-family:Consolas; font-weight:bold;")

        rc = RED if rate >= DEFECT_THRESHOLD else YELLOW if rate >= AGENT_TRIGGER_RATE else GREEN
        self.v_rate.setText(f"{rate:.1f}%")
        self.v_rate.setStyleSheet(f"color:{rc}; font-size:22px; font-family:Consolas; font-weight:bold;")

        if d['running']:
            self._set_status("RUNNING", GREEN)
        else:
            self._set_status("STOPPED", RED)

        self._shift_report.add_record(total, defects, rate, rate > self.plc.get_rate() - 0.1)
        self.statusBar().showMessage(
            f"Total: {total}  Defects: {defects}  Rate: {rate:.1f}%"
        )

    @pyqtSlot(str)
    def _on_log(self, msg):
        self.log.append(msg)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    @pyqtSlot(str)
    def _on_alarm(self, reason):
        self._set_status("ALARM", RED)
        self.statusBar().showMessage(f"ALARM: {reason}")
        self._on_log(f"*** {reason} ***")

    # ── Button handlers ───────────────────────
    def _start(self):
        self.plc.start_line()
        self._set_status("RUNNING", GREEN)
        self._on_log(f"[PLC] Start line command sent")
        if not self.worker.isRunning():
            self._make_worker()
            self.worker.start()

    def _stop(self):
        self.plc.stop_line(True)
        self._set_status("STOPPED", RED)
        self._on_log(f"[PLC] Stop line command sent")

    def _reset(self):
        self.worker.halt()
        self.worker.wait(2000)
        self.plc.reset()
        self._shift_report = ShiftReport()
        self.v_total.setText("--")
        self.v_defects.setText("--")
        self.v_rate.setText("--")
        self.log.clear()
        self.video_lbl.setPixmap(QPixmap())
        self.video_lbl.setText("[ waiting for start ]")
        self._set_status("IDLE", DIM)
        self.statusBar().showMessage("Reset — press START")
        self._on_log("[SYSTEM] Reset complete")

    def _report(self):
        path = self._shift_report.save_pdf(output_dir="..")
        self.statusBar().showMessage(f"Report saved: {path}")
        self._on_log(f"[REPORT] {path}")

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(f"LINE: {text}")
        self.status_lbl.setStyleSheet(
            f"color:{color}; background:{PANEL}; border:1px solid {color}; "
            f"font-family:Consolas; font-size:11px; font-weight:bold; padding:4px;"
        )

    def closeEvent(self, event):
        self.worker.halt()
        self.worker.wait(2000)
        self.vision.release()
        event.accept()


# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--defect-prob", type=float, default=0.2, metavar="P")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(defect_prob=args.defect_prob)
    win.show()
    sys.exit(app.exec_())
