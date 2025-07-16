# 🌱 LeaFi: Smart Plant Monitoring System

**An advanced IoT solution for remote plant monitoring, intelligent watering, and eco-friendly care—powered by ESP8266, MongoDB, MQTT, WeatherAPI, and an interactive FastAPI web dashboard.**  
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
│   IoT Sensors   │───▶ │  NodeMCU ESP8266   │───▶│    FastAPI Server   │
│ (DHT11, LDR)    │     │  (Wi-Fi, MQTTs)    │     │  + MQTT + MongoDB  │
└─────────────────┘     │  Pump + Relay      │     │  Digital Twin,     │
                        └────────────────────┘     │  Plant Logic,      │
                                │                  │  WeatherAPI        │
                                ▼                  └─────────────────────┘
                       ┌─────────────────┐                 │
                       │  Water Pump     │                 │
                       └─────────────────┘                 ▼
                                                ┌───────────────────────────┐
                                                │      Web Dashboard        │
                                                │  (HTML/JS/CSS, Chart.js) │
                                                └───────────────────────────┘
```

**Main Data Flow:**  
- Sensors (DHT11, LDR) → NodeMCU (MQTTs) → FastAPI (MQTT+REST) → MongoDB  
- FastAPI backend evaluates plant health, stores data, triggers watering, sends notifications  
- Web dashboard visualizes status, trends, and enables manual/auto control

---

## ⚡ Features

### 🖥️ Web Dashboard
| Feature                | Description                                       |
|------------------------|---------------------------------------------------|
| **Live Monitoring**    | Real-time temperature, humidity, light            |
| **Health Evaluation**  | Smart plant status & care recommendations         |
| **Manual Watering**    | Button to trigger irrigation remotely             |
| **Auto Watering**      | Weather-aware, threshold-based automation         |
| **Historical Charts**  | Interactive Chart.js graphs (6h–1w)               |
| **Settings**           | Configurable thresholds & plant location          |
| **Weather Integration**| Rain forecast for sustainable watering            |
| **Notifications**      | Email alerts for plant issues                     |
| **JWT Auth**           | Secure login, user session, data protection       |

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
- Python 3.8+
- NodeMCU ESP8266 (Arduino IDE, libraries: ESP8266WiFi, PubSubClient, ArduinoJson, DHT, etc.)
- Weather API key (register at [WeatherAPI](https://www.weatherapi.com/))
- MongoDB running locally (`mongodb://localhost:27017/`)

### Steps

1. **Clone repository**
   ```bash
   git clone https://github.com/LucaMelis0/smart-plant-system.git
   cd smart-plant-system
   ```

2. **Install Python dependencies**
   ```bash
   cd web_application
   pip install -r requirements.txt
   ```

3. **Initialize MongoDB database**
   ```bash
   python database.py
   ```
   - Follow prompts to setup admin and email config (SMTP, notification email)

4. **Generate SSL Certificates (for HTTPS/MQTTs)**
   ```bash
   python generate_certificates.py
   ```

5. **Configure Weather API**
   - Sign up at [WeatherAPI](https://www.weatherapi.com/)
   - Set API key as `WEATHER_API_KEY` environment variable

6. **Upload Arduino Firmware**
   - Open `arduino/smart_plant/smart_plant.ino` in Arduino IDE
   - Edit Wi-Fi credentials
   - Upload to NodeMCU

7. **Start FastAPI Server**
   ```bash
   python main.py
   ```
   - Access at `https://localhost:8000`

8. **Login to Dashboard**
   - Open browser: `https://localhost:8000`
   - Use admin credentials set during initialization

---

## 📊 API Reference

| Endpoint                 | Method | Description                          | Auth Required |
|--------------------------|--------|--------------------------------------|--------------|
| `/LeaFi/auth/login`      | POST   | Authenticate user, retrieve JWT      | No           |
| `/LeaFi/health`          | GET    | Backend health & status              | No           |
| `/LeaFi/current-status`  | GET    | Get current plant/sensor data        | No           |
| `/LeaFi/historical-data` | GET    | Get historical sensor data           | Yes          |
| `/LeaFi/weather`         | GET    | Get weather forecast info            | No           |
| `/LeaFi/manual-water`    | POST   | Trigger manual watering              | Yes          |
| `/LeaFi/toggle-auto-watering` | POST | Enable/disable auto watering        | Yes          |
| `/LeaFi/settings`        | GET/POST | Get or update plant care thresholds | Yes          |
| `/LeaFi/config/email`    | POST   | Update SMTP email config (admin)     | Yes          |

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
- **Notifications:** Email alerts sent via encrypted SMTP (admin-configurable)

---

## ⚠️ Limitations & Future Developments

- **Single-plant focus:** Each instance manages one plant. Multi-plant support would require extension.
- **Single-user system:** Only one user per dashboard; no password recovery, no multi-user roles.
- **Sensor granularity:** No soil moisture/nutrient sensing; DHT11/LDR are suitable for home use, not scientific/large-scale.
- **Actuator constraints:** Pump flow and duration are fixed; suitable for home pots, not large gardens.
- **Connectivity:** Requires stable Wi-Fi and power supply.
- **No advanced fault tolerance:** Basic error handling; persistent hardware or network issues may need manual intervention.
- **Outdoor/weather protection:** For outdoor use, additional casing or waterproofing is recommended.

**Future directions:**  
- Multi-plant/garden interface  
- Support for additional sensors (soil, nutrients)  
- Advanced analytics and AI-based care  
- Multi-user management and password recovery  
- Mobile app or push notifications (Telegram, etc.)

---

**Repository:** [github.com/LucaMelis0/smart-plant-system](https://github.com/LucaMelis0/smart-plant-system)
