# FactoryEye

![demo](docs/dashboard-demo.gif)

Real-time industrial quality control system combining a **Beckhoff TwinCAT 3 PLC**, **YOLOv8 computer vision**, and a **Google Gemini LLM agent** to detect defective parts on a production line.

---

## Important Note on Scope

> **The vision model is intentionally not the focus of this project.**
>
> The core of FactoryEye is the **PLC communication layer** and the **control algorithm** — how Python talks to a real TwinCAT 3 runtime over ADS protocol, how defect signals propagate to physical outputs (belt motor, reject cylinder, indicator lights), and how the entire pipeline is tested end-to-end without hardware using the built-in mock mode.
>
> The YOLOv8 model (trained on a small Roboflow dataset, mAP50 ≈ 0.46) is used purely as a detection source to drive the system. Any model — or even simulated random defects — produces the same PLC and dashboard behavior. Swapping in a better model is a one-line config change.

---

## Dashboard

![screenshot](docs/dashboard-screenshot.png)

---

## Architecture

```
[Camera / Video File]
        │
        ▼
[YOLOv8 Inference]  ──→  [Size / Class Defect Logic]
        │
        ▼
[Python ↔ TwinCAT ADS Bridge]
        │
        ▼
[TwinCAT 3 PLC — MAIN.TcPOU]
  Belt Motor | Reject Cylinder | Indicator Lights | Alarm Buzzer
        │
        ▼
[Gemini LLM Agent]  ──→  Recommend: slow_belt / stop_line / maintenance_check
        │
        ▼
[PyQt5 Dashboard]  +  [PDF Shift Report]
```

---

## Features

- **Real-time detection** — YOLOv8 inference on webcam or video file at 15 fps; inspection every 2 seconds
- **Defect logic** — class-based (custom model) or size-based (bounding box area ratio)
- **PLC integration** — reads/writes TwinCAT GVL variables over ADS protocol; fully controllable from Python
- **Mock mode** — runs entirely without hardware (`--mock` flag); simulated PLC with configurable defect probability
- **LLM advisory agent** — Gemini 2.0 Flash activates at configurable defect rate threshold and recommends corrective actions
- **Industrial HMI dashboard** — PyQt5 window with live video feed, production statistics, PLC log, and controls
- **Shift report** — one-click PDF export with defect rate trend and inspection table

---

## Tech Stack

| Layer | Technology |
|---|---|
| PLC | Beckhoff TwinCAT 3, Structured Text (IEC 61131-3) |
| PLC ↔ Python | pyads (ADS protocol) |
| Vision | YOLOv8n (Ultralytics), OpenCV |
| LLM Agent | Google Gemini 2.0 Flash (google-genai SDK) |
| Dashboard | PyQt5 |
| Reporting | fpdf2 |
| Dataset | Roboflow — [Bolts Final v1](https://universe.roboflow.com/bolts/bolts-final) (645 images, 4 classes) |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get a detection model

The model is trained on the **[Bolts Final](https://universe.roboflow.com/bolts/bolts-final)** dataset from Roboflow Universe — 645 images, 4 classes: Bolt, Nut, Screw, Washer.

```bash
# Option A — train with your Roboflow API key (free at roboflow.com)
python python/setup_model.py --api-key YOUR_KEY

# Option B — use COCO yolov8n with size-based defect detection (no key required)
python python/setup_model.py --fallback
```

### 3. Run the dashboard (mock mode — no TwinCAT needed)

```bash
python python/dashboard.py
```

Press **START** to begin inspection. The video feed, bounding boxes, and production stats update in real time.

### 4. Run the CLI loop

```bash
python python/main.py --mock --defect-prob 0.15
```

---

## LLM Agent Setup (optional)

Create a `.env` file in the project root (see `.env.example`):

```
GEMINI_API_KEY=your_key_here
```

Get a free key at [aistudio.google.com](https://aistudio.google.com). The agent activates automatically when the defect rate exceeds `AGENT_TRIGGER_RATE` (default 8%) and returns structured JSON advice (severity, recommendation, action).

---

## PLC Control Algorithm

The heart of FactoryEye is the Structured Text program running on TwinCAT 3 (`MAIN.TcPOU`). It implements a complete production line control sequence following IEC 61131-3 conventions.

### Belt Motor Interlock

```iecst
IF (GVL_PythonBridge.Start_Button OR GVL_PythonBridge.Belt_Motor)
   AND NOT GVL_PythonBridge.Emergency_Stop
   AND NOT GVL_PythonBridge.Stop_Line THEN
    GVL_PythonBridge.Belt_Motor   := TRUE;
    GVL_PythonBridge.Line_Running := TRUE;
ELSE
    GVL_PythonBridge.Belt_Motor   := FALSE;
    GVL_PythonBridge.Line_Running := FALSE;
END_IF;
```

The belt motor uses a latching interlock: once started, `Belt_Motor` holds itself ON until either an emergency stop or a stop-line command is received. Priority order is Emergency > Stop_Line > Start — standard industrial safety practice.

### Inspection Timer & Reject Cylinder

```iecst
Timer_Inspection(IN := GVL_PythonBridge.Product_Sensor AND GVL_PythonBridge.Belt_Motor,
                 PT := T#2S);

GVL_PythonBridge.Reject_Cylinder := Timer_Inspection.Q AND GVL_PythonBridge.Product_Defective;
```

A `TON` (on-delay timer) starts when a part is detected on the belt. The reject cylinder fires only when the timer completes **and** the vision system has flagged the part as defective. This 2-second window gives Python time to complete YOLO inference before the rejection decision is made — the PLC and the vision pipeline are intentionally synchronized through this timer.

### Rising-Edge Counters

```iecst
Product_Sensor_Rise(CLK := GVL_PythonBridge.Product_Sensor);
Counter_Total.CU := Product_Sensor_Rise.Q;
Counter_Total();
GVL_PythonBridge.Total_Count := Counter_Total.CV;

Defect_Rise(CLK := GVL_PythonBridge.Product_Defective);
Counter_Defect.CU := Defect_Rise.Q;
Counter_Defect();
GVL_PythonBridge.Defect_Count := Counter_Defect.CV;
```

`R_TRIG` blocks detect the rising edge of each signal so that a part held in the sensor field is counted exactly once, not on every scan cycle. Both counters (`CTU`) are read back by Python over ADS and displayed on the dashboard.

### Auto-Stop & Manual Reset

```iecst
IF GVL_PythonBridge.Defect_Rate >= 10.0 THEN
    GVL_PythonBridge.Stop_Line := TRUE;
END_IF;
IF GVL_PythonBridge.Start_Button AND GVL_PythonBridge.Stop_Line THEN
    GVL_PythonBridge.Stop_Line := FALSE;
END_IF;
```

When the defect rate (written by Python) reaches the 10% threshold the PLC stops the line autonomously — independent of Python. The operator must press Start again to clear the stop latch, preventing automatic restart after a fault.

### Output Map

| Output | Condition |
|---|---|
| `Belt_Motor` | Line running (no stop, no emergency) |
| `Reject_Cylinder` | Inspection timer elapsed AND part defective |
| `Green_Light` | Belt motor ON |
| `Red_Light` | Stop_Line active |
| `Alarm_Buzzer` | Stop_Line active |

---

## TwinCAT Integration

> Requires Beckhoff TwinCAT 3 Runtime and an XAR license.

1. Open `twincat/SmartQualityControl.sln` in TwinCAT XAE
2. Activate configuration and set runtime to **Run** mode
3. Run without the `--mock` flag:

```bash
python python/dashboard.py
```

Python communicates with the PLC over the ADS protocol (`pyads`). All shared state lives in `GVL_PythonBridge` — a Global Variable List visible to both the ST program and the Python bridge:

| Variable | Direction | Purpose |
|---|---|---|
| `GVL_PythonBridge.Start_Button` | Python → PLC | Start the line |
| `GVL_PythonBridge.Product_Sensor` | Python → PLC | Part detected |
| `GVL_PythonBridge.Product_Defective` | Python → PLC | Defect flag |
| `GVL_PythonBridge.Stop_Line` | Python → PLC | Stop command |
| `GVL_PythonBridge.Defect_Rate` | Python → PLC | Current defect % |
| `GVL_PythonBridge.Line_Running` | PLC → Python | Line status |
| `GVL_PythonBridge.Total_Count` | PLC → Python | Total products |
| `GVL_PythonBridge.Defect_Count` | PLC → Python | Defective products |

---

## Vision Model

The detection model is a YOLOv8n trained for 20 epochs on the Roboflow Bolts dataset. As noted above, model accuracy is secondary — it is used to generate detection events that drive the PLC logic.

| Metric | Value |
|---|---|
| Architecture | YOLOv8n |
| Dataset | Roboflow Bolts Final v1 |
| Classes | Bolt, Nut, Screw, Washer |
| Training images | 645 |
| Epochs | 20 |
| mAP50 | 0.46 |
| Confidence threshold | 0.12 |

**Training results:**

![training results](docs/training-results.png)

| F1 Curve | Confusion Matrix |
|---|---|
| ![f1](docs/f1-curve.png) | ![cm](docs/confusion-matrix.png) |

---

## Configuration

All tunable parameters are in `python/config.py`:

```python
VISION_SOURCE      = 'test_videos/bolt-multi-size-detection.mp4'  # 0 for webcam
YOLO_MODEL         = 'models/bolt_detector.pt'
CONFIDENCE         = 0.12        # YOLO confidence threshold
DEFECT_SIZE_MIN    = 0.005       # bbox/frame area — undersized
DEFECT_SIZE_MAX    = 0.030       # bbox/frame area — oversized
DEFECT_THRESHOLD   = 10.0        # % defect rate shown as alarm
INSPECTION_DELAY   = 2.0         # seconds between YOLO inference cycles
AGENT_TRIGGER_RATE = 8.0         # % rate at which LLM agent activates
```

---

## Project Structure

```
FactoryEye/
├── python/
│   ├── dashboard.py       # PyQt5 HMI — main entry point
│   ├── main.py            # CLI production loop
│   ├── vision.py          # YOLOv8 inference + defect logic
│   ├── agent.py           # Gemini LLM advisory agent
│   ├── plc.py             # TwinCAT ADS bridge
│   ├── mock_plc.py        # Simulated PLC (no hardware needed)
│   ├── report.py          # PDF shift report generator
│   ├── setup_model.py     # Model download / training helper
│   └── config.py          # All configuration constants
├── twincat/               # TwinCAT 3 PLC project
│   └── SmartQualityControl_PLC/
│       ├── POUs/MAIN.TcPOU
│       └── GVLs/GVL_PythonBridge.TcGVL
├── docs/                  # Screenshots and training visuals
├── models/                # YOLOv8 weights — generated by setup_model.py
├── test_videos/           # Sample production line videos
├── requirements.txt
└── .env.example
```

---

## Credits

- Test videos sourced from [Intel IoT DevKit — Sample Videos](https://github.com/intel-iot-devkit/sample-videos)
- Detection dataset: [Bolts Final v1](https://universe.roboflow.com/bolts/bolts-final) on Roboflow Universe

---

## License

MIT
