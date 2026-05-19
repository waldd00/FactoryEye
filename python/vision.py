# ─────────────────────────────────────────────
#  SmartQualityControl — vision.py
#  YOLOv8 defect detection — webcam or video file
# ─────────────────────────────────────────────

import cv2
from config import (
    VISION_SOURCE, YOLO_MODEL, CONFIDENCE,
    DEFECT_CLASS_IDS, DEFECT_SIZE_MIN, DEFECT_SIZE_MAX,
)

try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except Exception as e:
    print(f"[Vision] YOLO unavailable ({e}) — simulation mode only")
    _YOLO_AVAILABLE = False


class VisionSystem:
    def __init__(self, display: bool = True, sim_defect_prob: float = 0.2,
                 force_simulation: bool = False):
        self._last_frame      = None
        self._last_annotated  = None
        self._last_boxes      = []
        self._last_defective  = False
        self._display         = display
        self._sim_defect_prob = sim_defect_prob
        self._is_video_file   = isinstance(VISION_SOURCE, str)

        if force_simulation or not _YOLO_AVAILABLE:
            self.model = None
            self.cap   = None
            reason = "force_simulation=True" if force_simulation else "YOLO unavailable"
            print(f"[Vision] Pure simulation mode ({reason})")
            return

        # Load model — fall back to COCO nano if custom model missing
        import os
        model_path = YOLO_MODEL
        if not os.path.exists(model_path):
            print(f"[Vision] Model not found: {model_path} — falling back to yolov8n.pt")
            model_path = "models/yolov8n.pt"
        print(f"[Vision] Loading model: {model_path}")
        self.model = YOLO(model_path)

        # Open video source
        self.cap = cv2.VideoCapture(VISION_SOURCE)
        if not self.cap.isOpened():
            print(f"[Vision] Cannot open source '{VISION_SOURCE}' — simulation mode")
            self.cap = None
        else:
            src_type = "video file" if self._is_video_file else "camera"
            fps = self.cap.get(cv2.CAP_PROP_FPS) or 0
            total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            print(f"[Vision] {src_type} opened: {VISION_SOURCE}  fps={fps:.0f}  frames={total}")

    def set_sim_defect_prob(self, prob: float):
        self._sim_defect_prob = max(0.0, min(1.0, prob))

    # ── Read next frame (display only, no inference) ──
    def read_frame(self):
        """Advance video by one frame. Returns annotated frame if available, else raw."""
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret and self._is_video_file:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
        if ret:
            self._last_frame = frame
            # Overlay last known boxes on the new raw frame for smooth display
            if self._last_boxes:
                self._last_annotated = self._overlay_boxes(frame)
            else:
                self._last_annotated = frame.copy()
        return self._last_annotated if self._last_annotated is not None else self._last_frame

    def _overlay_boxes(self, frame):
        """Draw cached bounding boxes on a new frame for smooth display between inspections."""
        out = frame.copy()
        color_ok  = (0, 200, 0)
        color_def = (0, 0, 220)
        for b in self._last_boxes:
            x1, y1, x2, y2 = [int(v) for v in b['bbox']]
            color = color_def if self._last_defective else color_ok
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{b['label']} {b['confidence']:.2f}"
            cv2.putText(out, label, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        status = "DEFECTIVE" if self._last_defective else "OK"
        color  = color_def if self._last_defective else color_ok
        cv2.putText(out, f"[{status}]", (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        return out

    # ── Run inference on the current frame ────
    def inspect(self) -> bool:
        """Run YOLO on the last captured frame (or capture a new one)."""
        if self.cap is None or not self.cap.isOpened():
            return self._simulate_no_camera()

        # Use already-read frame if available, else read one
        frame = self._last_frame
        if frame is None:
            frame = self.read_frame()
        if frame is None:
            return self._simulate_no_camera()

        results = self.model(frame, conf=CONFIDENCE, verbose=False)
        defective, boxes = self._parse_results(results, frame)

        self._last_boxes     = boxes
        self._last_defective = defective
        self._last_annotated = self._make_annotated(frame, results, defective)

        if self._display:
            self._show(self._last_annotated)
        return defective

    # ── Result Parsing ────────────────────────
    def _parse_results(self, results, frame) -> tuple[bool, list]:
        boxes     = []
        defective = False
        h, w      = frame.shape[:2]
        frame_area = h * w

        for result in results:
            for box in result.boxes:
                class_id   = int(box.cls[0])
                confidence = float(box.conf[0])
                xyxy       = box.xyxy[0].tolist()
                label      = self.model.names[class_id]
                x1, y1, x2, y2 = xyxy
                bbox_area  = (x2 - x1) * (y2 - y1)
                size_ratio = bbox_area / frame_area

                boxes.append({
                    'class_id':   class_id,
                    'label':      label,
                    'confidence': confidence,
                    'bbox':       xyxy,
                    'size_ratio': size_ratio,
                })

                # Class-based defect (custom model with defect classes)
                if DEFECT_CLASS_IDS and class_id in DEFECT_CLASS_IDS:
                    defective = True
                    print(f"[Vision] Defect: {label} conf={confidence:.2f}")

                # Size-based defect (bolt too small or too large = wrong size)
                elif not DEFECT_CLASS_IDS:
                    if size_ratio < DEFECT_SIZE_MIN or size_ratio > DEFECT_SIZE_MAX:
                        defective = True
                        print(f"[Vision] Size defect: {label} size_ratio={size_ratio:.4f}")

        return defective, boxes

    # ── Annotated frame builder ───────────────
    def _make_annotated(self, frame, results, defective: bool):
        try:
            annotated   = results[0].plot()
            status_text = "DEFECTIVE" if defective else "OK"
            color       = (0, 0, 255) if defective else (0, 255, 0)
            cv2.putText(
                annotated, f"[{status_text}]",
                (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2,
            )
            return annotated
        except Exception:
            return frame.copy()

    def _show(self, annotated):
        try:
            cv2.imshow("SmartQualityControl", annotated)
            cv2.waitKey(1)
        except cv2.error:
            self._display = False

    # ── Simulation fallback ───────────────────
    def _simulate_no_camera(self) -> bool:
        import random
        result = random.random() < self._sim_defect_prob
        print(f"[Vision] (sim) {'DEFECTIVE' if result else 'OK'}")
        return result

    # ── Getters ───────────────────────────────
    def get_last_detections(self) -> list[dict]:
        return self._last_boxes

    def get_last_frame(self):
        return self._last_frame

    def get_last_annotated(self):
        return self._last_annotated

    # ── Cleanup ───────────────────────────────
    def release(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        print("[Vision] Released")
