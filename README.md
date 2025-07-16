# 🌱 LeaFi: Smart Plant Monitoring System

**An advanced IoT solution for remote plant monitoring, intelligent watering, and eco-friendly care. Powered by ESP8266, MongoDB, MQTT, WeatherAPI, and an interactive FastAPI web dashboard.**  

*“Every leaf has a story. LeaFi listens.”*

---

## 📖 Table of Contents

- [🎯 Project Overview](#-project-overview)
- [🏗️ System Architecture](#️-system-architecture)
- [⚡ Features](#-features)
- [🔧 Hardware Setup](#-hardware-setup)
- [🚀 Software Installation](#-software-installation)
- [📊 API Reference](#-api-reference)
- [⚙️ Configuration](#️-configuration)
- [🔒 Security](#-security)
- [⚠️ Limitations & Future Developments](#-limitations--future-developments)

---

## 🎯 Project Overview

**LeaFi** is a modular, service-oriented IoT system designed to make plant care intelligent, sustainable, and accessible. By continuously monitoring temperature, humidity, and light conditions, LeaFi provides real-time plant health evaluation and automates watering using weather forecasts to avoid waste.

**Ideal for:**  
- Citizens, gardeners, and remote plant owners  
- Users seeking eco-friendly, water-saving, and low-maintenance plant care  
- Anyone needing to monitor plant health and automate irrigation when away from home

---

## 🏗️ System Architecture

**Layered Overview:**

```
┌─────────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│   IoT Sensors   │───▶ │  NodeMCU ESP8266   │───▶ │    FastAPI Server   │
│ (DHT11, LDR)    │     │  (Wi-Fi, MQTTs)    │     │   + MQTT + MongoDB  │
└─────────────────┘     │  Pump + Relay      │     │   Digital Twin,     │
                        └────────────────────┘     │   Plant Logic,      │
                                │                  │   WeatherAPI        │
                                ▼                  └─────────────────────┘
                       ┌─────────────────┐                 │
                       │  Water Pump     │                 │
                       └─────────────────┘                 ▼
                                                ┌───────────────────────────┐
                                                │      Web Dashboard        │
                                                │      (HTML/JS/CSS)        │
                                                └───────────────────────────┘
```

**Main Data Flow:**  
- Sensors (DHT11, LDR) → NodeMCU (MQTTs) → FastAPI (MQTT+REST) → MongoDB  
- FastAPI backend evaluates plant health, stores data, triggers watering, sends notifications  
- Web dashboard visualizes status, trends, and enables remote/auto control

---

## ⚡ Features

### 🖥️ Web Dashboard
| Feature                     | Description                                 |
|-----------------------------|---------------------------------------------|
| **Live Monitoring**         | Real-time temperature, air humidity, light  |
| **Health Evaluation**       | Smart plant status & care recommendations   |
| **Remote Watering Command** | Button to trigger irrigation remotely       |
| **Auto Watering**           | Weather-aware, threshold-based automation   |
| **Historical Charts**       | Interactive graphs (6h–1w)                  |
| **Settings**                | Configurable thresholds & plant location    |
| **Weather Integration**     | Rain forecast for sustainable watering      |
| **Notifications**           | Email alerts for plant issues               |
| **JWT Auth**                | Secure login, user session, data protection |

### 🌱 Plant Status System
| Status         | Condition                                            | Action            |
|----------------|-----------------------------------------------------|-------------------|
| **Healthy**    | All optimal (T/H/L within ranges)                   | —                 |
| **Needs water**| Humidity below threshold, no rain expected          | Water plant       |
| **Change pos.**| Temp or light out of optimal range                   | Move/adjust plant |
| **No data**    | Sensors not reporting                               | Check setup       |

### 🤖 Smart Watering Logic
```
IF humidity < min_threshold AND no_rain_forecasted:
    → Activate pump (10 seconds)
ELSE:
    → Skip watering
```
- **Cooldown:** 30 min between automatic irrigations  
- **Manual override** always available

---

## 🔧 Hardware Setup

### Components
- **NodeMCU ESP8266**: Wi-Fi, MQTT, main controller
- **DHT11**: Temperature & humidity sensor (pin D4)
- **KY-018 LDR**: Light sensor (pin A0)
- **5V Water Pump + Relay**: Irrigation system (relay on D2)
- **Arduino UNO**: 5V power supply for sensors/actuators

### Wiring
```
NodeMCU ESP8266:
├── D4 → DHT11 Data
├── A0 → LDR Signal
├── D2 → Relay IN
└── GND → Common Ground
└── USB → PC (Power)

Arduino UNO:
├── 5V → DHT11 VCC, LDR VCC, Relay VCC/COM
├── GND → Common Ground
└── USB → PC (Power)

Relay:
├── VCC → Arduino 5V
├── GND → Arduino GND
├── IN → NodeMCU D2
├── COM → Arduino 5V
└── NO → Water Pump +

Water Pump:
├── + → Relay NO
└── – → GND
```

---

## 🚀 Software Installation

### Prerequisites

- **Python 3.9+**
- **NodeMCU ESP8266** (Arduino IDE, libraries: ESP8266WiFi, 256dpi/arduino-mqtt, ArduinoJson, DHT)
- **Weather API key** ([WeatherAPI](https://www.weatherapi.com/))
- **MongoDB** (see below)

### 1. Install and Start MongoDB

- **Download MongoDB Community Edition** from [mongodb.com/try/download/community](https://www.mongodb.com/try/download/community)
- **Install MongoDB** following the official instructions for your OS
- **Start the MongoDB server** (usually `mongod` command or via the MongoDB app/service)
- **(Optional) Install MongoDB Compass** for GUI management

MongoDB should be running locally and accessible at `mongodb://localhost:27017/` before starting the backend.

### 2. Clone Repository
```bash
git clone https://github.com/LucaMelis0/smart-plant-system.git
cd smart-plant-system
```

### 3. Install Python Dependencies
```bash
cd web_application
pip install -r requirements.txt
```

### 4. Initialize MongoDB Database and Configure SMTP Email

```bash
python database.py
```
- **During initialization**, you will be prompted to:
  - Set up the admin user (username, password, email)
  - **Configure SMTP**:  
    - Enter SMTP server address (e.g., `smtp.gmail.com`)
    - SMTP port (`465`)
    - Sender email (the Gmail/other account to send notifications from)
    - Application-specific password (for Gmail, generate an “App Password” in your Google account security settings)
    - Recipient email (your notification address)
    - SMTP security (choose SSL/TLS as appropriate)

**Note:** For Gmail, you must enable 2FA and generate an App Password [here](https://myaccount.google.com/apppasswords).

### 5. Generate SSL Certificates (for HTTPS/MQTTs)
```bash
python generate_certificates.py
```

### 6. Configure Weather API

- Sign up at [WeatherAPI](https://www.weatherapi.com/)
- Set your API key as the environment variable `WEATHER_API_KEY` before starting the server:
  ```bash
  export WEATHER_API_KEY=your_api_key_here
  ```

### 7. Upload Arduino Firmware

- Open `arduino/smart_plant/smart_plant.ino` in Arduino IDE
- Edit Wi-Fi credentials and MQTT server address
- Upload to NodeMCU

### 8. Start FastAPI Server
```bash
python main.py
```
- Access at `https://localhost:8000`

### 9. Login to Dashboard

- Open browser: `https://localhost:8000`
- Use the admin credentials set during initialization

---

## 📊 API Reference

| Endpoint                      | Method    | Description                                         |
|-------------------------------|-----------|-----------------------------------------------------|
| `/LeaFi/auth/login`           | POST      | Authenticate user, retrieve JWT                     |
| `/LeaFi/auth/register`        | POST      | User registration                                   |
| `/LeaFi/health`               | GET       | Backend health & status                             |
| `/LeaFi/current-status`       | GET       | Get current plant/sensor data, recommendations      |
| `/LeaFi/historical-data`      | GET       | Get historical sensor data (hours param)            |
| `/LeaFi/weather`              | GET       | Get weather forecast info for configured location   |
| `/LeaFi/manual-water`         | POST      | Trigger manual watering via MQTT                    |
| `/LeaFi/toggle-auto-watering` | POST      | Enable or disable automatic watering                |
| `/LeaFi/settings`             | GET, POST | Get or update plant care thresholds & location      |
| `/LeaFi/config/email`         | POST      | Set or update SMTP email config for notifications   |
| `/`                           | GET       | Serve dashboard (HTML)                              |
| `/login`                      | GET       | Serve login page (HTML)                             |

- All data is exchanged in JSON.
- MQTT topics: `LeaFi/sensor_data`, `LeaFi/commands`, `LeaFi/pump_status`

---

## ⚙️ Configuration

### Default Thresholds
```json
{
  "min_humidity": 30,
  "max_temp": 35,
  "min_temp": 15,
  "min_light": 20,
  "max_light": 80,
  "location": "Cagliari"
}
```
- **Sensor readings:** every 5 min
- **Dashboard refresh:** every 30s
- **Weather cache:** 3h
- **Pump activation:** 10s
- **Cooldown:** 30 min

---

## 🔒 Security

- **User Authentication:** JWT-based, bcrypt password hashing
- **HTTPS & MQTTs:** All communications encrypted (self-signed certs for dev)
- **Data privacy:** User data and settings stored securely in MongoDB, access controlled via JWT
- **Notifications:** Email alerts sent via encrypted SMTP

---

## ⚠️ Limitations & Future Developments

- **Single-plant focus:** The current hardware and software architecture are optimized for monitoring and managing one plant at a time. Multi-plant support would require hardware and software changes.
- **Single-user system:** The platform is designed for single-user access. Only one account per dashboard; no self-service password recovery or multi-user management.
- **Hardware Limitations:** DHT11 and LDR sensors are used for cost and simplicity, but are not suitable for scientific applications or large/specialized plants. The system does not measure soil moisture or nutrients. The pump is sized for small/medium pots with fixed flow/duration.

**Future directions:**  
- Multi-plant/garden interface  
- Support for additional sensors (soil, nutrients)  
- Multi-user management

---

**Repository:** [github.com/LucaMelis0/smart-plant-system](https://github.com/LucaMelis0/smart-plant-system)
