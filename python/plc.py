# ─────────────────────────────────────────────
#  SmartQualityControl — plc.py
#  Real TwinCAT ADS connection via pyads
# ─────────────────────────────────────────────

import pyads
from config import (
    AMS_NET_ID, ADS_PORT,
    VAR_START, VAR_EMERGENCY, VAR_PRODUCT_SENSOR,
    VAR_DEFECTIVE, VAR_STOP_LINE, VAR_LINE_RUNNING,
    VAR_TOTAL_COUNT, VAR_DEFECT_COUNT, VAR_DEFECT_RATE,
)


class PLC:
    def __init__(self):
        self.plc = pyads.Connection(AMS_NET_ID, ADS_PORT)

    # ── Connection ────────────────────────────
    def connect(self):
        self.plc.open()
        print(f"[PLC] Connected to TwinCAT @ {AMS_NET_ID}:{ADS_PORT}")

    def disconnect(self):
        self.plc.close()
        print("[PLC] Disconnected")

    # ── Writes (Python → PLC) ─────────────────
    def start_line(self):
        self.plc.write_by_name(VAR_START, True, pyads.PLCTYPE_BOOL)
        print("[PLC] Start command sent")

    def emergency_stop(self):
        self.plc.write_by_name(VAR_EMERGENCY, True, pyads.PLCTYPE_BOOL)
        print("[PLC] EMERGENCY STOP sent")

    def signal_product_detected(self):
        self.plc.write_by_name(VAR_PRODUCT_SENSOR, True, pyads.PLCTYPE_BOOL)

    def signal_defective(self, is_defective: bool):
        self.plc.write_by_name(VAR_DEFECTIVE, is_defective, pyads.PLCTYPE_BOOL)

    def update_defect_rate(self, rate: float):
        self.plc.write_by_name(VAR_DEFECT_RATE, rate, pyads.PLCTYPE_REAL)

    def stop_line(self, stop: bool = True):
        self.plc.write_by_name(VAR_STOP_LINE, stop, pyads.PLCTYPE_BOOL)

    # ── Reads (PLC → Python) ──────────────────
    def is_line_running(self) -> bool:
        return self.plc.read_by_name(VAR_LINE_RUNNING, pyads.PLCTYPE_BOOL)

    def get_counts(self) -> tuple[int, int]:
        total  = self.plc.read_by_name(VAR_TOTAL_COUNT,  pyads.PLCTYPE_INT)
        defect = self.plc.read_by_name(VAR_DEFECT_COUNT, pyads.PLCTYPE_INT)
        return total, defect
