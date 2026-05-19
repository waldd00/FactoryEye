# ─────────────────────────────────────────────
#  SmartQualityControl — main.py
#  Main production loop
# ─────────────────────────────────────────────

import argparse
import time
from vision import VisionSystem
from agent  import QualityAgent
from config import DEFECT_THRESHOLD, INSPECTION_DELAY

parser = argparse.ArgumentParser(description="SmartQualityControl production loop")
parser.add_argument("--mock", action="store_true", help="Use MockPLC instead of TwinCAT")
parser.add_argument(
    "--defect-prob", type=float, default=0.2,
    metavar="P",
    help="Simulated defect probability in mock/no-camera mode (0.0-1.0, default=0.2)",
)
args = parser.parse_args()

if args.mock:
    from mock_plc import MockPLC as PLC
else:
    from plc import PLC


# ─────────────────────────────────────────────
def calculate_defect_rate(total: int, defects: int) -> float:
    return (defects / total * 100.0) if total > 0 else 0.0


# ─────────────────────────────────────────────
def main():
    plc    = PLC(defect_probability=args.defect_prob) if args.mock else PLC()
    vision = VisionSystem(
        display=not args.mock,
        sim_defect_prob=args.defect_prob,
        force_simulation=args.mock,
    )
    agent  = QualityAgent()   # Phase 2 — safe to use, disables itself if no key

    plc.connect()
    plc.start_line()
    print("[SYSTEM] SmartQualityControl started")
    print("-" * 50)

    try:
        while True:
            # ── Wait for next inspection cycle
            time.sleep(INSPECTION_DELAY)

            # ── Skip if line is not running
            if not plc.is_line_running():
                print("[SYSTEM] Line is stopped. Waiting for restart...")
                time.sleep(1.0)
                continue

            # ── Run computer vision
            is_defective = vision.inspect()
            detections = vision.get_last_detections()

            # Only count when a part is actually detected in frame
            if not detections:
                continue

            # ── Signal product on belt
            plc.signal_product_detected()
            plc.signal_defective(is_defective)

            # ── Update stats
            total, defects = plc.get_counts()
            rate = calculate_defect_rate(total, defects)
            plc.update_defect_rate(rate)

            # ── Console output
            status = "DEFECTIVE" if is_defective else "OK"
            print(
                f"[VISION] {status} | "
                f"Total: {total} | Defects: {defects} | Rate: {rate:.1f}%"
            )

            # ── LLM Agent advice (Phase 2)
            last_label = detections[0]["label"] if detections else "unknown"
            advice = agent.analyze(total, defects, rate, last_label)

            if advice:
                action = advice.get("action", "none")
                if action == "stop_line":
                    print("[AGENT] STOP recommended — executing")
                    plc.stop_line(True)
                elif action == "slow_belt":
                    print("[AGENT] SLOW BELT recommended")
                elif action == "maintenance_check":
                    print("[AGENT] MAINTENANCE CHECK recommended")

            # ── Hard threshold stop
            if rate >= DEFECT_THRESHOLD:
                print(f"[ALARM] Defect rate {rate:.1f}% >= {DEFECT_THRESHOLD}% — line stopped")
                plc.stop_line(True)
                break

    except KeyboardInterrupt:
        print("\n[SYSTEM] Stopped by user (Ctrl+C)")

    finally:
        vision.release()
        plc.disconnect()
        print("[SYSTEM] Shutdown complete.")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
