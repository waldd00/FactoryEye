# ─────────────────────────────────────────────
#  SmartQualityControl — config.py
# ─────────────────────────────────────────────

# TwinCAT ADS Connection
AMS_NET_ID  = '127.0.0.1.1.1'   # Local TwinCAT runtime
ADS_PORT    = 851                 # TC3 PLC port

# GVL variable names (must match GVL_PythonBridge exactly)
VAR_START          = 'GVL_PythonBridge.Start_Button'
VAR_EMERGENCY      = 'GVL_PythonBridge.Emergency_Stop'
VAR_PRODUCT_SENSOR = 'GVL_PythonBridge.Product_Sensor'
VAR_DEFECTIVE      = 'GVL_PythonBridge.Product_Defective'
VAR_STOP_LINE      = 'GVL_PythonBridge.Stop_Line'
VAR_LINE_RUNNING   = 'GVL_PythonBridge.Line_Running'
VAR_TOTAL_COUNT    = 'GVL_PythonBridge.Total_Count'
VAR_DEFECT_COUNT   = 'GVL_PythonBridge.Defect_Count'
VAR_DEFECT_RATE    = 'GVL_PythonBridge.Defect_Rate'

# Vision source — int for webcam index, str for video file path
# Examples:
#   VISION_SOURCE = 0                                  # webcam
#   VISION_SOURCE = 'test_videos/bolt-detection.mp4'   # video file
VISION_SOURCE  = 'test_videos/bolt-detection.mp4'

YOLO_MODEL     = 'models/bolt_detector.pt'
CONFIDENCE     = 0.12   # model trained on limited data, low threshold needed

# DEFECT_CLASS_IDS: empty = use size-based logic.
# Model classes: {0:Bolt, 1:Nut, 2:Screw, 3:Washer}
DEFECT_CLASS_IDS = []

# Size-based defect detection.
# Calibrated on bolt-detection.mp4 (1024x576):
# Normal bolt: 0.010-0.030  |  Too small: <0.005  |  Oversized: >0.030
DEFECT_SIZE_MIN  = 0.005   # below = undersized / partial detection
DEFECT_SIZE_MAX  = 0.030   # above = oversized bolt

# Thresholds
DEFECT_THRESHOLD  = 10.0   # % defect rate → auto stop line
INSPECTION_DELAY  = 2.0    # seconds between inspection cycles

# LLM Agent (Phase 2)
# Set your API key in .env file: GEMINI_API_KEY=...
LLM_PROVIDER      = 'gemini'
LLM_MODEL         = 'gemini-2.0-flash'
LLM_MAX_TOKENS    = 512
AGENT_TRIGGER_RATE = 8.0   # % defect rate at which agent starts advising
