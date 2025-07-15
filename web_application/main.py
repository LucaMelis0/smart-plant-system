"""
LeaFi - FastAPI Backend Server

This is the core backend server implementing all functional requirements
for the IoT plant monitoring system LeaFi. It provides RESTful APIs for sensor
data collection, plant status evaluation, user management, and automated
irrigation control. It communicates with NodeMCU via MQTT (MQTTs/TLS).
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient
import requests
import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
import json
import os
import paho.mqtt.client as mqtt  # MQTT client library

# === LeaFi MQTT Setup ===
MQTT_BROKER = "broker.mqttdashboard.com"
MQTT_PORT = 8883
MQTT_TOPICS = {
    "sensor": "LeaFi/sensor_data",
    "command": "LeaFi/commands",
    "pump": "LeaFi/pump_status"
}
MQTT_TLS = True  # Always use MQTTs

# === Global State Variables ===
# Latest data received from NodeMCU via MQTT
latest_sensor_data = {}
latest_pump_status = {}

# === Security and Configuration ===
# JWT configuration and secret key
SECRET_KEY = hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Weather API and system state
WEATHER_API_KEY = None
cached_weather = None
cached_weather_time = None
last_auto_watering_time = None

# System configuration constants
WEATHER_CACHE_DURATION = timedelta(hours=3)     # FR4: Weather data caching
AUTO_WATERING_COOLDOWN = timedelta(minutes=30)  # FR8: Prevent excessive watering

# FR8: Device command state management
device_commands = {
    "auto_watering_enabled": False  # Tracks if automatic irrigation is enabled
}

# === MongoDB Setup ===
# Connection to MongoDB database (NoSQL)
# All persistent system data is stored here
mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["LeaFi_db"]

# === FastAPI Application Setup ===
app = FastAPI(
    title="LeaFi",
    description="LeaFi IoT Plant Monitoring System Backend",
    version="2.0.0"
)

# === CORS Configuration (NFR2) ===
# Ensures secure cross-origin requests from allowed domains only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:8000", "https://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Security Components (NFR5) ===
security = HTTPBearer()

# === Data Models (Pydantic Validation) ===
class UserLogin(BaseModel):
    """User authentication model for login endpoint"""
    username: str
    password: str

class SensorData(BaseModel):
    """FR1: Sensor data validation model for incoming sensor readings"""
    temperature: float = Field(ge=-40, le=80, description="Temperature in Celsius")
    humidity: float = Field(ge=0, le=100, description="Humidity percentage")
    light_level: int = Field(ge=0, le=100, description="Light level percentage")
    timestamp: Optional[str] = None  # ISO 8601 format

class ThresholdUpdate(BaseModel):
    """FR7: Plant care threshold configuration model"""
    min_humidity: float = Field(ge=0, le=100, description="Minimum humidity for watering trigger")
    max_temp: float = Field(ge=0, le=50, description="Maximum safe temperature")
    min_temp: float = Field(ge=-10, le=40, description="Minimum safe temperature")
    min_light: float = Field(ge=0, le=100, description="Minimum light level required")
    max_light: float = Field(ge=0, le=100, description="Maximum light level tolerated")
    location: str = Field(default="Cagliari", description="Location for weather integration")

# === Authentication & Security (NFR5) ===
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify user password against stored bcrypt hash

    Args:
        plain_password: User-provided password
        hashed_password: Stored bcrypt hash

    Returns:
        bool: True if password matches
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict) -> str:
    """
    Create JWT access token for user authentication

    Args:
        data: Token payload data

    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extract and validate current user from JWT token

    Args:
        credentials: HTTP Bearer token

    Returns:
        str: Username of authenticated user

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token validation failed")

# === Weather Integration (FR4) ===
def get_weather_forecast(location: str = "Cagliari") -> dict:
    """
    FR4: Weather Forecast Integration

    Retrieves weather forecast data to make intelligent watering decisions.
    Implements caching to reduce API calls.

    Args:
        location: City name for weather lookup

    Returns:
        dict: Weather information with rain forecast
    """
    global cached_weather, cached_weather_time

    # If API key is not configured, provide fallback data
    if not WEATHER_API_KEY:
        print("Weather API not configured - using default no-rain status")
        return {
            "will_rain": False,
            "rain_amount": 0,
            "condition": "API not configured",
            "location": location
        }

    # Check weather cache validity (3 hours)
    now = datetime.now()
    if (cached_weather and cached_weather_time and
            (now - cached_weather_time) < WEATHER_CACHE_DURATION):
        print("Using cached weather data")
        return cached_weather

    try:
        # Integrate with WeatherAPI.com
        url = "https://api.weatherapi.com/v1/forecast.json"
        params = {
            "key": WEATHER_API_KEY,
            "q": location,
            "days": 1,
            "aqi": "no",
            "alerts": "no"
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            forecast_day = data["forecast"]["forecastday"][0]["day"]
            will_rain = forecast_day["daily_will_it_rain"] == 1
            rain_amount = forecast_day["totalprecip_mm"]
            condition = data["current"]["condition"]["text"]

            result = {
                "will_rain": will_rain,
                "rain_amount": rain_amount,
                "condition": condition,
                "location": location
            }

            cached_weather = result
            cached_weather_time = now

            print(f"Weather updated - {location}: {condition}, Rain: {will_rain}")
            return result

        else:
            print(f"Weather API error: HTTP {response.status_code}")

    except Exception as e:
        print(f"Weather API request failed: {e}")

    # Fallback response if weather API unavailable
    return {
        "will_rain": False,
        "rain_amount": 0,
        "condition": "Unknown",
        "location": location
    }

# === Plant Status Evaluation (FR2) ===
def evaluate_plant_status(sensor_data: dict, thresholds: dict, weather_info: dict) -> dict:
    """
    FR2: Plant Status Evaluation

    Analyzes sensor data against user-defined thresholds to determine plant health
    and care requirements. Integrates weather information for intelligent watering.

    Args:
        sensor_data: Current environmental readings
        thresholds: User-configured care parameters
        weather_info: Weather forecast data

    Returns:
        dict: Plant status, recommendations, and watering decision
    """
    recommendations = []
    should_water = False

    # Humidity check for watering
    if sensor_data["humidity"] < thresholds["min_humidity"]:
        if not weather_info["will_rain"]:
            recommendations.append("Plant needs watering - humidity too low")
            should_water = True
        else:
            recommendations.append(
                f"Plant needs water but rain expected ({weather_info['rain_amount']}mm) - skip watering"
            )

    # Temperature check
    if sensor_data["temperature"] > thresholds["max_temp"]:
        recommendations.append(
            f"Temperature too high ({sensor_data['temperature']}°C) - move to cooler location"
        )
    elif sensor_data["temperature"] < thresholds["min_temp"]:
        recommendations.append(
            f"Temperature too low ({sensor_data['temperature']}°C) - move to warmer location"
        )

    # Light level check
    if sensor_data["light_level"] < thresholds["min_light"]:
        recommendations.append(
            f"Insufficient light ({sensor_data['light_level']}%) - move to brighter location"
        )
    elif sensor_data["light_level"] > thresholds["max_light"]:
        recommendations.append(
            f"Too much light ({sensor_data['light_level']}%) - add shade or relocate"
        )

    # Overall status
    if not recommendations:
        status = "Healthy"
    elif should_water:
        status = "Needs water"
    else:
        status = "Change position"

    return {
        "status": status,
        "recommendations": recommendations,
        "should_water": should_water and not weather_info["will_rain"]
    }

# === Database Operations (FR5) ===
def get_settings() -> dict:
    """
    FR7: Retrieve user-configured plant care thresholds

    Returns:
        dict: Current threshold settings or defaults
    """
    try:
        settings = db.settings.find_one({}, {"_id": 0})
        if settings:
            return settings
    except Exception as e:
        print(f"Error loading settings: {e}")

    print("Using default plant care thresholds")
    return {
        "min_humidity": 30,
        "max_temp": 35,
        "min_temp": 15,
        "min_light": 20,
        "max_light": 80,
        "location": "Cagliari"
    }

def store_sensor_data(data):
    """
    Store sensor data in MongoDB (called by MQTT handler)

    Args:
        data: Dictionary with sensor readings and timestamp
    """
    try:
        db.sensor_data.insert_one(data)
    except Exception as e:
        print(f"Failed to store sensor data: {e}")

def store_plant_status(status, recommendations, timestamp):
    """
    Store plant status evaluation in MongoDB

    Args:
        status: Evaluated status string
        recommendations: List of recommendations
        timestamp: ISO8601 string of evaluation time
    """
    try:
        db.plant_status.insert_one({
            "status": status,
            "recommendations": recommendations,
            "timestamp": timestamp
        })
    except Exception as e:
        print(f"Failed to store plant status: {e}")

# === MQTT Client Setup and Handlers ===
def on_connect(client, userdata, flags, rc):
    """
    MQTT connection callback. Subscribes to LeaFi topics.
    """
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPICS["sensor"], qos=1)
    client.subscribe(MQTT_TOPICS["pump"], qos=1)

def on_message(client, userdata, msg):
    """
    MQTT message callback. Handles sensor data and pump status.
    Called automatically by paho-mqtt when message is received.
    """
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"[MQTT] Message received: {topic}\n{payload}")

    try:
        data = json.loads(payload)
    except Exception as e:
        print(f"[MQTT] Error decoding JSON: {e}")
        return

    if topic == MQTT_TOPICS["sensor"]:
        # Update global state and store to DB
        global latest_sensor_data
        latest_sensor_data = data
        store_sensor_data(data)

        # Evaluate and store plant status
        thresholds = get_settings()
        weather_info = get_weather_forecast(thresholds["location"])
        evaluation = evaluate_plant_status(data, thresholds, weather_info)
        store_plant_status(evaluation["status"], evaluation["recommendations"], data["timestamp"])

    elif topic == MQTT_TOPICS["pump"]:
        # Update global pump status
        global latest_pump_status
        latest_pump_status = data

def start_mqtt():
    """
    Start MQTT client (in background thread).

    Handles encrypted MQTTs communication with the NodeMCU.
    """
    client = mqtt.Client()
    if MQTT_TLS:
        client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client

# Start MQTT client at import time
mqtt_client = start_mqtt()

# === API Endpoints (LeaFi REST API) ===

@app.post("/LeaFi/auth/login")
async def login(user: UserLogin):
    """
    NFR5: User authentication endpoint.
    Validates credentials and returns JWT token for secure API access.

    Args:
        user: Login credentials

    Returns:
        dict: Access token and token type

    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        db_user = db.users.find_one({"username": user.username})
        if not db_user or not verify_password(user.password, db_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        access_token = create_access_token(data={"sub": user.username})
        print(f"User authenticated: {user.username}")

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")

@app.get("/LeaFi/current-status")
async def get_current_status():
    """
    FR6: User Query Interface - Get current plant status

    Returns:
        dict: Complete current system status, including sensor readings,
        plant health evaluation, and control flags.
    """
    try:
        data = latest_sensor_data.copy() if latest_sensor_data else None
        pump = latest_pump_status.copy() if latest_pump_status else None

        # If no live data available, fallback to latest in DB
        if not data:
            row = db.sensor_data.find_one(sort=[("timestamp", -1)])
            if row:
                data = {
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "light_level": row["light_level"],
                    "timestamp": row["timestamp"]
                }

        if not pump:
            pump = {"status": "unknown", "timestamp": datetime.now().isoformat()}

        if not data:
            return {
                "temperature": 0.0,
                "humidity": 0.0,
                "light_level": 0,
                "timestamp": datetime.now().isoformat(),
                "status": "No data",
                "recommendations": ["Connect sensors and wait for data"],
                "auto_watering_enabled": device_commands["auto_watering_enabled"],
                "pump_status": pump
            }

        thresholds = get_settings()
        weather_info = get_weather_forecast(thresholds["location"])
        evaluation = evaluate_plant_status(data, thresholds, weather_info)

        return {
            "temperature": data["temperature"],
            "humidity": data["humidity"],
            "light_level": data["light_level"],
            "timestamp": data["timestamp"],
            "status": evaluation["status"],
            "recommendations": evaluation["recommendations"],
            "auto_watering_enabled": device_commands["auto_watering_enabled"],
            "pump_status": pump
        }
    except Exception as e:
        print(f"Error retrieving current status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system status")

@app.get("/LeaFi/historical-data")
async def get_historical_data(hours: int = 24, current_user: str = Depends(get_current_user)):
    """
    FR5 & FR6: Historical data retrieval for trend analysis.
    Returns environmental data for dashboard visualization.

    Args:
        hours: Number of hours of historical data to retrieve
        current_user: Authenticated user (from JWT token)

    Returns:
        dict: Historical sensor data array
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_iso = cutoff_time.isoformat()

        data = list(db.sensor_data.find(
            {"timestamp": {"$gt": cutoff_iso}},
            {"_id": 0, "temperature": 1, "humidity": 1, "light_level": 1, "timestamp": 1}
        ).sort("timestamp", 1))

        print(f"Historical data request by {current_user} - {len(data)} records ({hours}h)")
        return {"data": data}

    except Exception as e:
        print(f"Error retrieving historical data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve historical data")

@app.get("/LeaFi/weather")
async def get_weather():
    """
    FR4: Weather forecast information for dashboard display.

    Returns:
        dict: Current weather information including rain forecast
    """
    thresholds = get_settings()
    weather_info = get_weather_forecast(thresholds["location"])
    return weather_info

@app.post("/LeaFi/manual-water")
async def manual_water(current_user: str = Depends(get_current_user)):
    """
    FR8: Manual watering trigger.
    Allows authenticated users to manually trigger plant watering.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        dict: Command confirmation
    """
    command = {
        "action": "water",
        "reason": "manual"
    }
    mqtt_client.publish(MQTT_TOPICS["command"], json.dumps(command), qos=1)
    print(f"[MQTT] Manual watering triggered by user: {current_user}")
    return {
        "status": "success",
        "message": "Manual watering command sent to device"
    }

@app.post("/LeaFi/toggle-auto-watering")
async def toggle_auto_watering(current_user: str = Depends(get_current_user)):
    """
    FR8: Toggle automatic watering system.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        dict: New auto-watering state
    """
    global device_commands

    device_commands["auto_watering_enabled"] = not device_commands["auto_watering_enabled"]
    status = "enabled" if device_commands["auto_watering_enabled"] else "disabled"

    print(f"Auto-watering {status} by user: {current_user}")

    return {
        "status": "success",
        "auto_watering_enabled": device_commands["auto_watering_enabled"],
        "message": f"Automatic watering {status}"
    }

@app.get("/LeaFi/settings")
async def get_user_settings(current_user: str = Depends(get_current_user)):
    """
    FR7: Get current plant care thresholds

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        dict: Current threshold settings
    """
    return get_settings()

@app.post("/LeaFi/settings")
async def update_settings(settings: ThresholdUpdate, current_user: str = Depends(get_current_user)):
    """
    FR7: System Calibration - Update and customize plant care thresholds.

    Args:
        settings: New threshold configuration
        current_user: Authenticated user from JWT token

    Returns:
        dict: Update confirmation
    """
    global cached_weather_time, cached_weather

    try:
        old_settings = get_settings()
        update_result = db.settings.update_one(
            {"user_id": current_user},
            {"$set": {
                "min_humidity": settings.min_humidity,
                "max_temp": settings.max_temp,
                "min_temp": settings.min_temp,
                "min_light": settings.min_light,
                "max_light": settings.max_light,
                "location": settings.location
            }}
        )
        # If no settings found for user, create new
        if update_result.matched_count == 0:
            db.settings.insert_one({
                "user_id": current_user,
                "min_humidity": settings.min_humidity,
                "max_temp": settings.max_temp,
                "min_temp": settings.min_temp,
                "min_light": settings.min_light,
                "max_light": settings.max_light,
                "location": settings.location
            })

        # Clear weather cache if location changed
        if old_settings["location"] != settings.location:
            cached_weather_time = None
            cached_weather = None
            print(f"Location changed: {old_settings['location']} → {settings.location}")

        print(f"Settings updated by {current_user}")
        return {
            "status": "success",
            "message": "Plant care settings updated successfully"
        }

    except Exception as e:
        print(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")

@app.get("/LeaFi/health")
async def health_check():
    """
    NFR3: System health and status endpoint

    Returns:
        dict: System health information
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "weather_api": "configured" if WEATHER_API_KEY else "not configured",
        "auto_watering": device_commands["auto_watering_enabled"]
    }

# === Static Files and Web Interface ===
# Serve all static files under /static (JS, CSS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def dashboard():
    """Serve main dashboard page (HTML)"""
    return FileResponse('templates/index.html')

@app.get("/login")
async def login_page():
    """Serve login page (HTML)"""
    return FileResponse('templates/login.html')

# === Application Startup and Weather API Configuration ===
def setup_weather_api():
    """
    FR4: Configure weather API integration

    Prompts for WeatherAPI key or uses environment variable.
    Weather integration is optional - system works without it.
    """
    global WEATHER_API_KEY

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

    if not WEATHER_API_KEY:
        print("\nWeather API Configuration (Optional)")
        print("API key at: https://www.weatherapi.com/")

        try:
            api_key = input("Enter WeatherAPI key (or press Enter to skip): ").strip()
            if api_key:
                WEATHER_API_KEY = api_key
                print("Weather API configured successfully")
            else:
                print("Weather API skipped - system will work without weather integration")
        except KeyboardInterrupt:
            print("\nWeather API setup cancelled")

if __name__ == "__main__":
    print("🌱 LeaFi - Backend Server")
    print("=====================================")

    # Setup weather API (optional)
    setup_weather_api()

    print("\nStarting HTTPS server...")
    print("Dashboard: https://localhost:8000")
    print("LeaFi MQTT endpoint (cloud): broker.mqttdashboard.com")
    print("Press Ctrl+C to stop server\n")

    try:
        import uvicorn
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=False,
            access_log=True,
            log_level="info",
            ssl_certfile="certs/cert.pem",
            ssl_keyfile="certs/key.pem"
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Server error: {e}")