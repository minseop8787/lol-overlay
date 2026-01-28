# LoL ARAM Augment Overlay

A lightweight, intelligent overlay for **League of Legends ARAM** mode that automatically detects augment choices and displays real-time tier information. Designed for speed, accuracy, and zero interference with gameplay.

## 🛠️ Technical Architecture

This application follows a hybrid **Electron + Python** architecture to combine modern UI with powerful computer vision capabilities.

### 🔌 Backend (Python & Flask)
The core logic resides in a Python subprocess managed by the Electron app.
*   **Vision Engine**: Uses `OpenCV` for real-time screen capture (`mss`) and template matching.
*   **OCR**: Integrates `Tesseract 5.0` to read augment text with high precision.
*   **API**: Exposes a local Flask server (`127.0.0.1:5000`) for the frontend to poll data.

### 💻 Frontend (React & Electron)
*   **Overlay UI**: Built with `React` for a dynamic and responsive interface.
*   **Window Management**: `Electron` handles the transparent, click-through window that stays on top of the game client.
*   **Interactivity**: Supports "Click-Through" mode while allowing interactions with tooltips when needed.

## 🚀 Key Features

### 1. Hybrid Perception Engine
To ensure **100% false-positive prevention**, the system uses a two-stage detection process:
1.  **Gatekeeper (Template Matching)**: It first verifies the presence of the "Augment Select Button" on the screen (Threshold: 0.85). If the button is not found, no OCR is performed.
2.  **Recognition (OCR)**: Once the phase is confirmed, Tesseract OCR extracts the text from the card regions.

### 2. Fuzzy Data Matching
OCR errors are automatically corrected using fuzzy string matching logic (`difflib`), mapping imperfect text to a database of **155+ known augments** to retrieve accurate tier data.

### 3. Anti-Ghosting
The overlay includes fail-safes to ensure it never appears during normal gameplay. It constantly monitors specific ROI (Region of Interest) coordinates to distinguish the augment selection screen from the shop or combat interface.

## 📦 Build & Installation

### Requirements
*   Node.js (v16+)
*   Python (3.10+)
*   Tesseract-OCR (Binaries required in `backend/Tesseract-OCR`)

### Build Steps
1.  **Backend**: `cd backend && python -m PyInstaller build.spec`
2.  **Frontend**: `cd frontend && npm run dist`

The final output is a single setup executable that bundles the Python environment, Tesseract engine, and the Electron app.
