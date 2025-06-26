# 🌱 Smart Plant Monitor

**IoT Plant Monitoring System with Automated Care**

An intelligent plant monitoring solution that combines environmental sensing, weather integration, and automated irrigation to provide remote plant care through a modern web dashboard.

## 📖 Table of Contents
- [🎯 Project Overview](#-project-overview)
- [🏗️ System Architecture](#️-system-architecture)
- [⚡ Features](#-features)
- [🔧 Hardware Setup](#-hardware-setup)
- [🚀 Software Installation](#-software-installation)
- [📊 API Reference](#-api-reference)
- [⚙️ Configuration](#️-configuration)

## 🎯 Project Overview

The Smart Plant Monitor system provides automated monitoring and intelligent watering decisions. The system continuously tracks environmental conditions (temperature, humidity, light) and integrates weather forecasts to make sustainable watering decisions, promoting efficient water use and optimal plant health.

**Target Users**: Citizens and gardeners seeking automated plant monitoring solutions, especially when away from home for extended periods.

### 📋 System Requirements

#### Functional Requirements
| ID | Requirement | Implementation |
|----|-------------|---------------|
| **FR1** | Plant Condition Monitoring | DHT11 + LDR sensors with 5 minutes reading interval |
| **FR2** | Status Evaluation | Real-time plant status based on configurable thresholds |
| **FR3** | User Notifications | Web dashboard alerts and recommendations |
| **FR4** | Weather Forecast Integration | WeatherAPI for intelligent watering decisions |
| **FR5** | Historical Data Logging | SQLite database with 7-day data retention |
| **FR6** | User Query Interface | Responsive web dashboard with real-time data |
| **FR7** | System Calibration | User-configurable thresholds for different plant types |
| **FR8** | Automated & Manual Watering | Smart watering with weather consideration + manual override |

#### Non-Functional Requirements
| ID | Requirement | Target | Implementation |
|----|-------------|--------|----------------|
| **NFR1** | Performance | <2s response, 5min sensor updates | 5 minutes sensor updates, optimized queries |
| **NFR2** | Reliability | 99% uptime, secure communication | FastAPI web application with auto-reconnection |
| **NFR3** | Portability | Various environments | Usable in different environments, accessible with different devices |
| **NFR4** | Resource Efficiency | Minimize water use | Weather-aware watering, automatic watering cooldown protection |
| **NFR5** | Data Security | Protect user data | JWT authentication, bcrypt hashing, HTTPS encryption |

## 🏗️ System Architecture

```
┌─────────────────┐     ┌────────────────────┐     ┌───────────────────┐
│   IoT Sensors   │───▶ │  NodeMCU ESP8266   │───▶│  FastAPI Server   │
│                 │     │                    │     │                   │
│ • DHT11 (T&H)   │     │ • Wi-Fi Control    │     │ • Data Processing │
│ • LDR (Light)   │     │ • HTTP/HTTPS       │     │ • Plant Analysis  │
└─────────────────┘     │ • Pump Control     │     │ • Weather API     │
                        └────────────────────┘     └───────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Water Pump     │    │   SQLite DB     │
                       │                 │    │                 │
                       │ • 5V Actuator   │    │ • Sensor Data   │
                       │ • Relay Control │    │ • Plant Status  │
                       │ • Auto/Manual   │    │ • User Settings │
                       └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │  Web Dashboard   │
                                               │                  │
                                               │ • Real-time UI   │
                                               │ • Charts/Graphs  │
                                               │ • Manual Control │
                                               └──────────────────┘
```

### 📁 Project Structure
```
smart-plant_IoT/
├── arduino/smart_plant/
│   └── smart_plant.ino             # NodeMCU ESP8266 firmware
├── web_application/
│   ├── main.py                     # FastAPI backend server
│   ├── database.py                 # Database initialization
│   ├── generate_certificates.py    # SSL certificate generation script
│   ├── requirements.txt            # Python dependencies
│   ├── templates/                  # HTML templates
│   │   ├── index.html              # Main dashboard page
│   │   └── login.html              # Authentication page
│   ├── static/                     # CSS, JS, assets
│   │   ├── css/
│   │   │   ├── auth.css            # Authentication page styles
│   │   │   └── dashboard.css       # Dashboard interface styles
│   │   └── js/
│   │       ├── auth.js             # Authentication handling
│   │       └── dashboard.js        # Dashboard functionality
│   └── certs/                      # Automatically generated SSL certificates
└── README.md                       # Project documentation

```

## ⚡ Features

### 🖥️ Web Dashboard
| Feature | Description | Functionality |
|---------|-------------|---------------|
| **Real-time Monitoring** | Live sensor data display | Current temperature, humidity, and light levels with 30s updates |
| **Plant Status** | Health evaluation with recommendations | Overall plant health with actionable care recommendations |
| **Manual Controls** | Trigger watering and toggle automation | Manual watering button and auto-watering toggle with feedback |
| **Historical Charts** | Environmental trends visualization | Interactive Chart.js graphs over selectable periods (6h to 1 week) |
| **Settings** | Configurable thresholds | Customizable plant care parameters with validation |
| **Weather Integration** | Rain forecast consideration | Real-time weather data with rain predictions for smart watering |

### 🌱 Plant Status System
| Status | Condition | Description | Action Required |
|--------|-----------|-------------|-----------------|
| **Healthy** | All conditions optimal | Temperature, humidity, and light within ranges | Continue monitoring |
| **Needs water** | Humidity below threshold | Insufficient soil moisture (considers weather) | Water if no rain expected |
| **Change position** | Temperature or light issues | Environmental conditions outside optimal range | Relocate plant |
| **No data** | Sensors not connected | No recent sensor readings from NodeMCU | Check connections and Wi-Fi |

### 🤖 Smart Watering Logic
```
IF humidity < min_threshold AND no_rain_forecasted:
    → Activate pump for 10 seconds
ELSE:
    → Skip watering (weather-aware decision)
```

## 🔧 Hardware Setup

### Components Required
- **NodeMCU ESP8266**: Wi-Fi connectivity and communication
- **DHT11**: Temperature and humidity monitoring (D4)
- **LDR (Photoresistor)**: Light level detection (A0)
- **5V Water Pump + Relay**: Automated and manual irrigation system (D2)
- **Arduino UNO**: 5V power supply for sensors and actuators

### Wiring Diagram
```
NodeMCU ESP8266 (Main Controller):
├── D4 → DHT11 Data Pin
├── A0 → LDR Signal Pin
├── D2 → Relay Control Signal
├── USB → PC (Programming & Power)
└── GND → Common Ground

Arduino UNO (5V Power Supply):
├── 5V → DHT11 VCC, LDR VCC, Relay VCC, Relay COM
├── GND → Common Ground (all components)
└── USB → PC (Power)

Relay Module:
├── VCC → Arduino UNO 5V
├── GND → Arduino UNO GND
├── IN → NodeMCU D2
├── COM → Arduino UNO 5V
└── NO → Water Pump Positive

Water Pump:
├── Positive → Relay NO (Normally Open)
└── Negative → Common Ground

DHT11 Sensor:
├── VCC → Arduino UNO 5V
├── Data → NodeMCU D4
└── GND → Common Ground

LDR Sensor:
├── VCC → Arduino UNO 5V
├── Signal → NodeMCU A0
└── GND → Common Ground
```

## 🚀 Software Installation

### Prerequisites
- Python 3.8+
- NodeMCU ESP8266 with Arduino IDE and related components
- Weather API key (free registration at [WeatherAPI](https://www.weatherapi.com/))

### Step-by-Step Installation

1. **Clone Repository**
   ```bash
   git clone https://github.com/LucaMelis0/smart-plant_IoT.git
   cd smart-plant_IoT
   ```

2. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize Database**
   ```bash
   cd web_application
   python database.py
   ```

4. **Configure SSL Certificates (Optional)**
   ```bash
   python generate_certificates.py
   ```

5. **Setup Weather API**
   - Sign up at [WeatherAPI](https://www.weatherapi.com/)
   - Obtain API key for when running `main.py`

6. **Configure Arduino Code**
   - Open `arduino/smart_plant/smart_plant.ino` in Arduino IDE
   - Update Wi-Fi credentials and server URL
   - Upload to NodeMCU ESP8266

7. **Start Server**
   ```bash
   python main.py
   ```

8. **Access Dashboard**
   - Local: `http://localhost:8000`
   - Remote: `http://YOUR_SERVER_IP:8000`
   - Login with admin credentials

## 📊 API Reference

### Authentication (NFR5)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | User authentication with username/password |
| `GET` | `/api/health` | System health check and status |

### Sensor Data (FR1)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sensor-data` | Receive sensor readings from NodeMCU |
| `GET` | `/api/current-status` | Get current plant status and sensor data |
| `GET` | `/api/historical-data?hours=24` | Historical environmental data |

### Device Communication (FR8)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/device-commands` | Get control commands for NodeMCU |
| `POST` | `/api/pump-status` | Update pump status from device |
| `GET` | `/api/pump-status` | Get current pump operation status |

### Plant Control (FR8)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/manual-water` | Trigger manual watering |
| `POST` | `/api/toggle-auto-watering` | Enable/disable automatic watering |

### Configuration (FR7)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Get current plant care thresholds |
| `POST` | `/api/settings` | Update plant care thresholds |

### Weather Integration (FR4)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/weather` | Get weather forecast information |

## ⚙️ Configuration

### Default Plant Thresholds
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

### System Intervals
- **Sensor readings**: 5 minutes
- **Server communication**: 5 minutes
- **Dashboard refresh**: 30 seconds
- **Weather API cache**: 3 hours
- **Pump operation**: 10 seconds
- **Auto-watering cooldown**: 30 minutes

---

**Repository**: [smart-plant_IoT](https://github.com/LucaMelis0/smart-plant_IoT)  
