# ─────────────────────────────────────────────
#  setup_model.py — Bolt detection model download
#  Usage: python setup_model.py --api-key YOUR_KEY
# ─────────────────────────────────────────────

import os
import sys
import argparse
import shutil

ROBOFLOW_WORKSPACE = "bolts"
ROBOFLOW_PROJECT   = "bolts-final"
ROBOFLOW_VERSION   = 1
OUTPUT_MODEL       = "models/bolt_detector.pt"


def download_roboflow(api_key: str):
    try:
        from roboflow import Roboflow
    except ImportError:
        print("Installing roboflow...")
        os.system(f"{sys.executable} -m pip install roboflow -q")
        from roboflow import Roboflow

    print(f"Connecting to Roboflow ({ROBOFLOW_WORKSPACE}/{ROBOFLOW_PROJECT} v{ROBOFLOW_VERSION})...")
    rf      = Roboflow(api_key=api_key)
    project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)
    version = project.version(ROBOFLOW_VERSION)

    print("Downloading dataset (YOLOv8 format)...")
    dataset = version.download("yolov8", location="datasets/bolts_dataset", overwrite=True)
    print(f"Dataset saved to: {dataset.location}")

    print("\nTraining YOLOv8n on bolt dataset (20 epochs)...")
    from ultralytics import YOLO
    model = YOLO("yolov8n.pt")
    results = model.train(
        data=os.path.join(dataset.location, "data.yaml"),
        epochs=20,
        imgsz=640,
        batch=16,
        project="models",
        name="bolt_train",
        exist_ok=True,
        device="cpu",
        verbose=False,
    )

    best_pt = os.path.join("models", "bolt_train", "weights", "best.pt")
    if os.path.exists(best_pt):
        shutil.copy(best_pt, OUTPUT_MODEL)
        print(f"\nModel saved: {OUTPUT_MODEL}")
    else:
        print(f"Training complete. Find model at: models/bolt_train/weights/best.pt")


def use_pretrained_fallback():
    """
    Falls back to COCO yolov8n and uses size-based defect logic.
    Bolts are NOT in COCO, but size anomaly detection still works on the video.
    """
    src = "models/yolov8n.pt"
    if not os.path.exists(src):
        print("Downloading YOLOv8n (COCO)...")
        from ultralytics import YOLO
        YOLO("yolov8n.pt")
        import glob
        found = glob.glob("yolov8n.pt")
        if found:
            shutil.move(found[0], src)

    shutil.copy(src, OUTPUT_MODEL)
    print(f"Using COCO model as fallback: {OUTPUT_MODEL}")
    print("Size-based defect detection active (config: DEFECT_CLASS_IDS = [])")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default="", help="Roboflow API key (free at roboflow.com)")
    parser.add_argument("--fallback", action="store_true", help="Use COCO model with size-based detection")
    args = parser.parse_args()

    os.makedirs("models", exist_ok=True)

    if args.fallback or not args.api_key:
        print("No API key provided — using size-based fallback mode.")
        print("To get a free Roboflow key: https://app.roboflow.com -> Settings -> API Keys\n")
        use_pretrained_fallback()
    else:
        download_roboflow(args.api_key)

    print("\nDone. Run: python python/main.py --mock")
