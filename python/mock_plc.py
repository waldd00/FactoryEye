# ─────────────────────────────────────────────
#  SmartQualityControl — mock_plc.py
#  Simulated PLC — no TwinCAT required
# ─────────────────────────────────────────────


class MockPLC:
    def __init__(self, defect_probability: float = 0.2):
        self._running  = False
        self._total    = 0
        self._defects  = 0
        self._rate     = 0.0
        self._stopped  = False   # simulates Stop_Line
        self.defect_probability = defect_probability  # used by VisionSystem simulation

    # ── Connection ────────────────────────────
    def connect(self):
        print("[MockPLC] Connected (simulation mode)")

    def disconnect(self):
        print("[MockPLC] Disconnected")

    # ── Writes ────────────────────────────────
    def start_line(self):
        self._stopped = False
        self._running = True
        print("[MockPLC] Line started")

    def emergency_stop(self):
        self._running = False
        print("[MockPLC] EMERGENCY STOP")

    def signal_product_detected(self):
        if not self._running:
            return
        self._total += 1
        print(f"[MockPLC] Product detected — Total: {self._total}")

    def signal_defective(self, is_defective: bool):
        if is_defective:
            self._defects += 1
        status = "DEFECTIVE" if is_defective else "OK"
        print(f"[MockPLC] {status} — Defects: {self._defects}")

    def update_defect_rate(self, rate: float):
        self._rate = rate

    def stop_line(self, stop: bool = True):
        self._stopped = stop
        self._running = not stop
        print(f"[MockPLC] Line {'STOPPED' if stop else 'RESUMED'}")

    # ── Reads ─────────────────────────────────
    def is_line_running(self) -> bool:
        return self._running

    def get_counts(self) -> tuple[int, int]:
        return self._total, self._defects

    def get_rate(self) -> float:
        return self._rate

    # ── Reset ─────────────────────────────────
    def reset(self):
        self._total   = 0
        self._defects = 0
        self._rate    = 0.0
        self._stopped = False
        self._running = False
        print("[MockPLC] Reset — counters cleared")
