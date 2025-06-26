"""
Smart Plant Monitor - FastAPI Backend Server

This is the core backend server implementing all functional requirements
for the IoT plant monitoring system. It provides RESTful APIs for sensor
data collection, plant status evaluation, user management, and automated
irrigation control.
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import sqlite3
import requests
import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
import json
import os

# Security configuration
SECRET_KEY = hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Global system state
WEATHER_API_KEY = None
cached_weather = None
cached_weather_time = None
last_auto_watering_time = None

# System configuration constants
WEATHER_CACHE_DURATION = timedelta(hours=3)     # FR4: Weather data caching
AUTO_WATERING_COOLDOWN = timedelta(minutes=30)  # FR8: Prevent excessive watering
DATA_RETENTION_DAYS = 7                         # FR5: Historical data retention

# FR8: Real-time pump status tracking with timestamps
pump_status = {
    "is_on": False,
    "last_changed": datetime.now().isoformat(),
    "last_updated": datetime.now().isoformat()
}

# FR8: Device command state management
device_commands = {
    "manual_water": False,
    "auto_watering_enabled": False
}

# FastAPI application setup
app = FastAPI(
    title="Smart Plant Monitor API",
    description="IoT Plant Monitoring System Backend",
    version="1.0.0"
)

# NFR2: CORS configuration for web application security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:8000", "https://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NFR5: Security components
security = HTTPBearer()

# === Data Models (Input Validation) ===
class UserLogin(BaseModel):
    """User authentication model"""
    username: str
    password: str


class SensorData(BaseModel):
    """FR1: Sensor data validation model"""
    temperature: float = Field(ge=-40, le=80, description="Temperature in Celsius")
    humidity: float = Field(ge=0, le=100, description="Humidity percentage")
    light_level: int = Field(ge=0, le=100, description="Light level percentage")
    timestamp: Optional[int] = None


class ThresholdUpdate(BaseModel):
    """FR7: Plant care threshold configuration model"""
    min_humidity: float = Field(ge=0, le=100, description="Minimum humidity for watering trigger")
    max_temp: float = Field(ge=0, le=50, description="Maximum safe temperature")
    min_temp: float = Field(ge=-10, le=40, description="Minimum safe temperature")
    min_light: float = Field(ge=0, le=100, description="Minimum light level required")
    max_light: float = Field(ge=0, le=100, description="Maximum light level tolerated")
    location: str = Field(default="Cagliari", description="Location for weather integration")


class PumpStatusUpdate(BaseModel):
    """FR8: Pump status update model"""
    is_on: bool


# === Authentication & Security (NFR5) ===
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify user password against stored hash

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

    if not WEATHER_API_KEY:
        print("Weather API not configured - using default no-rain status")
        return {
            "will_rain": False,
            "rain_amount": 0,
            "condition": "API not configured",
            "location": location
        }

    # Check cache validity (3-hour cache duration)
    now = datetime.now()
    if (cached_weather and cached_weather_time and
            (now - cached_weather_time) < WEATHER_CACHE_DURATION):
        print("Using cached weather data")
        return cached_weather

    try:
        # WeatherAPI.com integration
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

            # Extract rain forecast information
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

            # Update cache
            cached_weather = result
            cached_weather_time = now

            print(f"Weather updated - {location}: {condition}, Rain: {will_rain}")
            return result

        else:
            print(f"Weather API error: HTTP {response.status_code}")

    except Exception as e:
        print(f"Weather API request failed: {e}")

    # Fallback response when API unavailable
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

    # Humidity analysis for watering decisions (FR8)
    if sensor_data["humidity"] < thresholds["min_humidity"]:
        if not weather_info["will_rain"]:
            recommendations.append("Plant needs watering - humidity too low")
            should_water = True
        else:
            recommendations.append(
                f"Plant needs water but rain expected ({weather_info['rain_amount']}mm) - skip watering"
            )

    # Temperature monitoring
    if sensor_data["temperature"] > thresholds["max_temp"]:
        recommendations.append(
            f"Temperature too high ({sensor_data['temperature']}°C) - move to cooler location"
        )
    elif sensor_data["temperature"] < thresholds["min_temp"]:
        recommendations.append(
            f"Temperature too low ({sensor_data['temperature']}°C) - move to warmer location"
        )

    # Light level monitoring
    if sensor_data["light_level"] < thresholds["min_light"]:
        recommendations.append(
            f"Insufficient light ({sensor_data['light_level']}%) - move to brighter location"
        )
    elif sensor_data["light_level"] > thresholds["max_light"]:
        recommendations.append(
            f"Too much light ({sensor_data['light_level']}%) - add shade or relocate"
        )

    # Determine overall plant status
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
def get_db_connection():
    """
    Create SQLite database connection with timeout

    Returns:
        sqlite3.Connection: Database connection object
    """
    return sqlite3.connect('plant_monitor.db', timeout=30.0)


def get_settings() -> dict:
    """
    FR7: Retrieve user-configured plant care thresholds

    Returns:
        dict: Current threshold settings or defaults
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT min_humidity, max_temp, min_temp, min_light, max_light, location
                           FROM settings
                           LIMIT 1
                           ''')
            row = cursor.fetchone()

            if row:
                return {
                    "min_humidity": row[0],
                    "max_temp": row[1],
                    "min_temp": row[2],
                    "min_light": row[3],
                    "max_light": row[4],
                    "location": row[5]
                }
    except Exception as e:
        print(f"Error loading settings: {e}")

    # Default thresholds if none configured
    print("Using default plant care thresholds")
    return {
        "min_humidity": 30,
        "max_temp": 35,
        "min_temp": 15,
        "min_light": 20,
        "max_light": 80,
        "location": "Cagliari"
    }


def cleanup_old_data():
    """
    FR5: Historical Data Logging - Cleanup old records

    Removes sensor data and plant status records older than configured retention period
    to comply with data retention policies.
    """
    cutoff_date = datetime.now() - timedelta(days=DATA_RETENTION_DAYS)
    cutoff_iso = cutoff_date.isoformat()

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Clean sensor data
            cursor.execute('DELETE FROM sensor_data WHERE timestamp < ?', (cutoff_iso,))
            sensor_deleted = cursor.rowcount

            # Clean plant status records
            cursor.execute('DELETE FROM plant_status WHERE timestamp < ?', (cutoff_iso,))
            status_deleted = cursor.rowcount

            total_deleted = sensor_deleted + status_deleted
            if total_deleted > 0:
                print(f"Cleaned up {total_deleted} old records ({sensor_deleted} sensor, {status_deleted} status)")

    except Exception as e:
        print(f"Error during data cleanup: {e}")


# === API Endpoints ===
# Authentication Endpoints (NFR5)
@app.post("/api/auth/login")
async def login(user: UserLogin):
    """
    User authentication endpoint. Validates credentials and returns JWT token for secure API access.

    Args:
        user: Login credentials

    Returns:
        dict: Access token and token type

    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT username, password_hash FROM users WHERE username = ?',
                (user.username,)
            )
            db_user = cursor.fetchone()

        if not db_user or not verify_password(user.password, db_user[1]):
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


# Sensor Data Endpoints (FR1)
@app.post("/api/sensor-data")
async def receive_sensor_data(data: SensorData):
    """
    FR1: Plant Condition Monitoring - Receive sensor data from NodeMCU,
    processes environmental sensor readings, evaluates plant status,
    and determines watering requirements with weather integration.

    Args:
        data: Environmental sensor readings

    Returns:
        dict: Processing status, watering decision, and plant evaluation
    """
    global last_auto_watering_time
    timestamp = datetime.now().isoformat()

    try:
        # FR5: Store sensor data in database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO sensor_data (temperature, humidity, light_level, timestamp)
                           VALUES (?, ?, ?, ?)
                           ''', (data.temperature, data.humidity, data.light_level, timestamp))

        # Get user-configured thresholds (FR7)
        thresholds = get_settings()

        # Get weather forecast for intelligent watering (FR4)
        weather_info = get_weather_forecast(thresholds["location"])

        # Prepare sensor data for evaluation
        sensor_dict = {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "light_level": data.light_level
        }

        # FR2: Evaluate plant status
        evaluation = evaluate_plant_status(sensor_dict, thresholds, weather_info)

        # FR8: Apply watering cooldown to prevent excessive irrigation
        should_water = evaluation["should_water"]
        now = datetime.now()

        if should_water and last_auto_watering_time:
            if (now - last_auto_watering_time) < AUTO_WATERING_COOLDOWN:
                should_water = False
                print("Auto-watering skipped due to cooldown period")
            else:
                last_auto_watering_time = now
                print("Auto-watering authorized by server")
        elif should_water:
            last_auto_watering_time = now

        # FR5: Store plant status evaluation
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO plant_status (status, recommendations, timestamp)
                           VALUES (?, ?, ?)
                           ''', (evaluation["status"], json.dumps(evaluation["recommendations"]), timestamp))

        print(
            f"Sensor data processed - T:{data.temperature}°C H:{data.humidity}% L:{data.light_level}% Status:{evaluation['status']}")

        return {
            "status": "success",
            "should_water": should_water,
            "weather": weather_info,
            "plant_status": evaluation["status"],
            "timestamp": timestamp
        }

    except Exception as e:
        print(f"Error processing sensor data: {e}")
        raise HTTPException(status_code=500, detail="Failed to process sensor data")


# Device Communication Endpoints (FR8)
@app.get("/api/device-commands")
async def get_device_commands():
    """
    FR8: Send control commands to NodeMCU device
    Provides irrigation commands and settings to the IoT device.

    Returns:
        dict: Current device commands and settings
    """
    global device_commands
    commands = device_commands.copy()        # Create response with current commands
    device_commands["manual_water"] = False  # Reset manual water command after sending
    return commands


@app.post("/api/pump-status")
async def update_pump_status(status: PumpStatusUpdate):
    """
    FR8: Update pump status from Arduino device
    Receives real-time pump operation status for monitoring and logging.

    Args:
        status: Current pump operation state

    Returns:
        dict: Confirmation of status update
    """
    global pump_status

    print(f"Pump status update received: {'ON' if status.is_on else 'OFF'}")

    # Update global pump status with timestamps
    pump_status.update({
        "is_on": status.is_on,
        "last_changed": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat()
    })

    return {
        "status": "success",
        "updated_status": pump_status
    }


@app.get("/api/pump-status")
async def get_pump_status():
    """
    Get current pump operation status

    Returns:
        dict: Current pump status with timestamps
    """
    pump_status["last_updated"] = datetime.now().isoformat()
    return pump_status


# User Interface Endpoints (FR6)

@app.get("/api/current-status")
async def get_current_status():
    """
    FR6: User Query Interface - Get current plant status

    Provides comprehensive current system status including sensor readings,
    plant health evaluation, and system configuration.

    Returns:
        dict: Complete current system status
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get latest sensor readings
            cursor.execute('''
                           SELECT temperature, humidity, light_level, timestamp
                           FROM sensor_data
                           ORDER BY timestamp DESC
                           LIMIT 1
                           ''')
            sensor_row = cursor.fetchone()

            # Get latest plant status evaluation
            cursor.execute('''
                           SELECT status, recommendations, timestamp
                           FROM plant_status
                           ORDER BY timestamp DESC
                           LIMIT 1
                           ''')
            status_row = cursor.fetchone()

        # Handle case when no data available
        if not sensor_row:
            return {
                "temperature": 0.0,
                "humidity": 0.0,
                "light_level": 0,
                "timestamp": datetime.now().isoformat(),
                "status": "No data",
                "recommendations": ["Connect sensors and wait for data"],
                "auto_watering_enabled": device_commands["auto_watering_enabled"],
                "pump_status": pump_status
            }

        # Return comprehensive status
        return {
            "temperature": sensor_row[0],
            "humidity": sensor_row[1],
            "light_level": sensor_row[2],
            "timestamp": sensor_row[3],
            "status": status_row[0] if status_row else "Unknown",
            "recommendations": json.loads(status_row[1]) if status_row and status_row[1] else [],
            "auto_watering_enabled": device_commands["auto_watering_enabled"],
            "pump_status": pump_status
        }

    except Exception as e:
        print(f"Error retrieving current status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system status")


@app.get("/api/historical-data")
async def get_historical_data(hours: int = 24, current_user: str = Depends(get_current_user)):
    """
    FR5 & FR6: Historical data retrieval for trend analysis. Environmental data for dashboard visualization.

    Args:
        hours: Number of hours of historical data to retrieve
        current_user: Authenticated user (from JWT token)

    Returns:
        dict: Historical sensor data array
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_iso = cutoff_time.isoformat()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT temperature, humidity, light_level, timestamp
                           FROM sensor_data
                           WHERE timestamp > ?
                           ORDER BY timestamp ASC
                           ''', (cutoff_iso,))

            data = [
                {
                    "temperature": row[0],
                    "humidity": row[1],
                    "light_level": row[2],
                    "timestamp": row[3]
                }
                for row in cursor.fetchall()
            ]

        print(f"Historical data request by {current_user} - {len(data)} records ({hours}h)")
        return {"data": data}

    except Exception as e:
        print(f"Error retrieving historical data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve historical data")


# Weather Integration Endpoint (FR4)
@app.get("/api/weather")
async def get_weather():
    """
    FR4: Weather forecast information for dashboard display

    Returns:
        dict: Current weather information including rain forecast
    """
    thresholds = get_settings()
    weather_info = get_weather_forecast(thresholds["location"])
    return weather_info


# Manual Control Endpoints (FR8)
@app.post("/api/manual-water")
async def manual_water(current_user: str = Depends(get_current_user)):
    """
    FR8: Manual watering trigger. Allows authenticated users to manually trigger plant watering.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        dict: Command confirmation
    """
    global device_commands

    device_commands["manual_water"] = True
    print(f"Manual watering triggered by user: {current_user}")

    return {
        "status": "success",
        "message": "Manual watering command sent to device"
    }


@app.post("/api/toggle-auto-watering")
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


# Configuration Endpoints (FR7)
@app.get("/api/settings")
async def get_user_settings(current_user: str = Depends(get_current_user)):
    """
    FR7: Get current plant care thresholds

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        dict: Current threshold settings
    """
    return get_settings()


@app.post("/api/settings")
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

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           UPDATE settings
                           SET min_humidity=?,
                               max_temp=?,
                               min_temp=?,
                               min_light=?,
                               max_light=?,
                               location=?
                           WHERE user_id = (SELECT id FROM users WHERE username = ?)
                           ''', (
                               settings.min_humidity, settings.max_temp, settings.min_temp,
                               settings.min_light, settings.max_light, settings.location,
                               current_user
                           ))

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


# System Health Endpoint
@app.get("/api/health")
async def health_check():
    """
    System health and status endpoint

    Returns:
        dict: System health information
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "weather_api": "configured" if WEATHER_API_KEY else "not configured",
        "pump_status": pump_status,
        "auto_watering": device_commands["auto_watering_enabled"]
    }


# === Static Files and Web Interface ===
# Serve static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def dashboard():
    """Serve main dashboard page"""
    return FileResponse('templates/index.html')

@app.get("/login")
async def login_page():
    """Serve login page"""
    return FileResponse('templates/login.html')


# === Application Startup ===
def setup_weather_api():
    """
    FR4: Configure weather API integration

    Prompts for WeatherAPI key or uses environment variable.
    Weather integration is optional - system works without it.
    """
    global WEATHER_API_KEY

    # Try environment variable first
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
    print("🌱 SMART PLANT MONITOR - Backend Server")
    print("=====================================")

    # FR4: Setup weather API integration
    setup_weather_api()

    # FR5: Initialize database if needed
    if not os.path.exists('plant_monitor.db'):
        print("Initializing database...")
        try:
            from database import init_database
            init_database()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Database initialization failed: {e}")
            exit(1)
    else:
        print("Database found and ready")

    # FR5: Cleanup old data
    cleanup_old_data()

    print("\nStarting HTTPS server...")
    print("Dashboard: https://localhost:8000")
    print("NodeMCU endpoint: https://YOUR_IP:8000/api/sensor-data")
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