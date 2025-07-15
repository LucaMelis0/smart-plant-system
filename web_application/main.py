"""
LeaFi - FastAPI Backend Server

This is the core backend server implementing all functional requirements
for the IoT plant monitoring system LeaFi. It provides RESTful APIs for sensor
data collection, plant status evaluation, user management, and automated
irrigation control. It communicates with NodeMCU via MQTT (MQTTs/TLS).
Digital Twin pattern: DigitalPlant class manages virtual representation and logic.
"""

# === Imports ===

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from pymongo import MongoClient
import requests
import uvicorn
import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
import json
import os
import paho.mqtt.client as mqtt
import threading
import time
import smtplib
from email.mime.text import MIMEText
from cryptography.fernet import Fernet

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

SECRET_KEY = hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

WEATHER_API_KEY = None
cached_weather = None
cached_weather_time = None
last_auto_watering_time = None

WEATHER_CACHE_DURATION = timedelta(hours=3)
AUTO_WATERING_COOLDOWN = timedelta(minutes=30)

device_commands = {
    "auto_watering_enabled": False
}

# === MongoDB Setup ===

mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["LeaFi_storage"]

# === FastAPI Application Setup ===

app = FastAPI(
    title="LeaFi",
    description="LeaFi IoT Plant Monitoring System Backend",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:8000", "https://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# === Data Models ===

class UserLogin(BaseModel):
    username: str
    password: str

class UserRegister(BaseModel):
    username: str
    password: str
    email: EmailStr

class SensorData(BaseModel):
    temperature: float = Field(ge=-40, le=80)
    humidity: float = Field(ge=0, le=100)
    light_level: int = Field(ge=0, le=100)
    timestamp: Optional[str] = None

class ThresholdUpdate(BaseModel):
    min_humidity: float = Field(ge=0, le=100)
    max_temp: float = Field(ge=0, le=50)
    min_temp: float = Field(ge=-10, le=40)
    min_light: float = Field(ge=0, le=100)
    max_light: float = Field(ge=0, le=100)
    location: str = Field(default="Cagliari")

class EmailConfig(BaseModel):
    smtp_server: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    sender_email: EmailStr

class PlantAlert(BaseModel):
    email: EmailStr
    subject: str
    message: str

# === Utility: Authentication and Security ===

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token validation failed")

# === Utility: Email Notification ===

def ask_for_smtp_key():
    key = os.environ.get("LEAFI_SMTP_KEY")
    if not key:
        print("LEAFI_SMTP_KEY not found in environment.")
        key = input("Enter the Fernet SMTP encryption key (LEAFI_SMTP_KEY) generated during setup: ").strip()
        if not key:
            print("SMTP key not provided. Cannot start backend.")
            exit(1)
        os.environ["LEAFI_SMTP_KEY"] = key
    return key

def get_email_config():
    cfg = db.config.find_one({"type": "email"})
    if not cfg:
        return None
    key = os.environ.get("LEAFI_SMTP_KEY")
    if not key:
        raise RuntimeError("LEAFI_SMTP_KEY not found in environment")
    fernet = Fernet(key.encode())
    decrypted_password = fernet.decrypt(cfg["smtp_password"].encode()).decode()
    cfg["smtp_password"] = decrypted_password
    return cfg

def send_email_notification(email: EmailStr, subject: str, message: str):
    cfg = get_email_config()
    if not cfg:
        print("[MAIL] No email config found, skipping mail")
        return False
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = cfg["sender_email"]
        msg["To"] = email
        with smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.login(cfg["smtp_username"], cfg["smtp_password"])
            server.sendmail(cfg["sender_email"], [email], msg.as_string())
        print(f"[MAIL] Sent alert email to {email}")
        return True
    except Exception as e:
        print(f"[MAIL] Failed to send email: {e}")
        return False

# === Digital Twin: DigitalPlant ===

class DigitalPlant:
    def __init__(self, db, email_callback=None):
        self.db = db
        self.latest_sensor_data = {}
        self.latest_pump_status = {}
        self.last_auto_watering_time = None
        self.email_callback = email_callback
        self.last_status = None

    def update_sensor_data(self, data: dict):
        self.latest_sensor_data = data
        self.store_sensor_data(data)

    def store_sensor_data(self, data: dict):
        try:
            self.db.sensor_data.insert_one(data)
        except Exception as e:
            print(f"Failed to store sensor data: {e}")

    def get_latest_sensor_data(self):
        if self.latest_sensor_data:
            return self.latest_sensor_data.copy()
        row = self.db.sensor_data.find_one(sort=[("timestamp", -1)])
        if row:
            return {
                "temperature": row["temperature"],
                "humidity": row["humidity"],
                "light_level": row["light_level"],
                "timestamp": row["timestamp"]
            }
        return None

    def update_pump_status(self, data: dict):
        self.latest_pump_status = data

    def get_latest_pump_status(self):
        if self.latest_pump_status:
            return self.latest_pump_status.copy()
        return {"status": "unknown", "timestamp": datetime.now().isoformat()}

    def get_settings(self, user_id=None):
        try:
            q = {"user_id": user_id} if user_id else {}
            settings = self.db.settings.find_one(q, {"_id": 0})
            if settings:
                return settings
        except Exception as e:
            print(f"Error loading settings: {e}")
        return {
            "min_humidity": 30,
            "max_temp": 35,
            "min_temp": 15,
            "min_light": 20,
            "max_light": 80,
            "location": "Cagliari"
        }

    def evaluate_plant_status(self, data: dict, thresholds: dict, weather_info: dict):
        recommendations = []
        should_water = False

        if data["humidity"] < thresholds["min_humidity"]:
            status = "Needs water"
            if weather_info["will_rain"]:
                recommendations.append(
                    f"Plant needs water but rain expected ({weather_info['rain_amount']}mm) - skip watering"
                )
                should_water = False
            else:
                recommendations.append("Plant needs watering - humidity too low")
                should_water = True
        else:
            status = None

        if data["temperature"] > thresholds["max_temp"]:
            recommendations.append(
                f"Temperature too high ({data['temperature']}°C) - move to cooler location"
            )
        elif data["temperature"] < thresholds["min_temp"]:
            recommendations.append(
                f"Temperature too low ({data['temperature']}°C) - move to warmer location"
            )

        if data["light_level"] < thresholds["min_light"]:
            recommendations.append(
                f"Insufficient light ({data['light_level']}%) - move to brighter location"
            )
        elif data["light_level"] > thresholds["max_light"]:
            recommendations.append(
                f"Too much light ({data['light_level']}%) - add shade or relocate"
            )

        if not status:
            if not recommendations:
                status = "Healthy"
            else:
                status = "Change position"

        return {
            "status": status,
            "recommendations": recommendations,
            "should_water": should_water
        }

    def store_plant_status(self, status: str, recommendations: list, timestamp: str):
        try:
            self.db.plant_status.insert_one({
                "status": status,
                "recommendations": recommendations,
                "timestamp": timestamp
            })
        except Exception as e:
            print(f"Failed to store plant status: {e}")

    def process_and_notify(self, data: dict):
        thresholds = self.get_settings()
        weather_info = self.get_weather_forecast(thresholds["location"])
        evaluation = self.evaluate_plant_status(data, thresholds, weather_info)
        now_status = evaluation["status"]
        negative_states = {"Needs water", "Change position", "No data"}

        if self.last_status != now_status and now_status in negative_states:
            user_row = self.db.users.find_one()
            user_email = user_row.get("email") if user_row else None
            username = user_row.get("username", "User") if user_row else "User"
            timestamp = data.get("timestamp")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    time_str = timestamp
            else:
                time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            subject = "[LeaFI] Alert: Your plant needs attention!"
            recommendations = ""
            if evaluation["recommendations"]:
                recommendations = "\n".join(f"- {rec}" for rec in evaluation["recommendations"])
            else:
                recommendations = "- Check your plant conditions."

            message = f"""Hello {username},

LeaFI has detected that your plant requires attention:

- Status: {now_status}
- Time: {time_str}

Recommended actions:
{recommendations}

This email was generated automatically by your LeaFi system.

-- 
LeaFi

(Do not reply to this email)
"""
            if user_email and self.email_callback:
                self.email_callback(user_email, subject, message)
        self.last_status = now_status

        self.store_plant_status(
            now_status,
            evaluation["recommendations"],
            data.get("timestamp", datetime.now().isoformat())
        )

    def get_weather_forecast(self, location):
        global cached_weather, cached_weather_time, WEATHER_API_KEY
        if not WEATHER_API_KEY:
            return {
                "will_rain": False,
                "rain_amount": 0,
                "condition": "API not configured",
                "location": location
            }
        now = datetime.now()
        if (cached_weather and cached_weather_time and
                (now - cached_weather_time) < WEATHER_CACHE_DURATION):
            return cached_weather

        try:
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
                return result
        except Exception as e:
            print(f"Weather API error: {e}")
        return {
            "will_rain": False,
            "rain_amount": 0,
            "condition": "Unknown",
            "location": location
        }

    def can_auto_water(self, evaluation):
        global last_auto_watering_time
        can_water = evaluation["should_water"]
        now = datetime.now()
        if can_water:
            if last_auto_watering_time:
                elapsed = now - last_auto_watering_time
                if elapsed < AUTO_WATERING_COOLDOWN:
                    print("[AUTO] Cooldown in effect, skipping irrigation")
                    can_water = False
            if can_water:
                last_auto_watering_time = now
        return can_water

    def trigger_auto_watering(self, mqtt_client, user_email=None):
        command = {
            "action": "water",
            "reason": "auto"
        }
        mqtt_client.publish(MQTT_TOPICS["command"], json.dumps(command), qos=1)
        print(f"[AUTO] Auto irrigation triggered at {datetime.now().isoformat()}")
        if user_email and self.email_callback:
            self.email_callback(
                user_email,
                "LeaFi - Automatic Watering Performed",
                "Your plant has been automatically watered by the system."
            )

# === DigitalPlant singleton ===

plant = DigitalPlant(db=db, email_callback=send_email_notification)

# === MQTT Client Setup and Handlers ===

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPICS["sensor"], qos=1)
    client.subscribe(MQTT_TOPICS["pump"], qos=1)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"[MQTT] Message received: {topic}\n{payload}")
    try:
        data = json.loads(payload)
    except Exception as e:
        print(f"[MQTT] Error decoding JSON: {e}")
        return

    if topic == MQTT_TOPICS["sensor"]:
        plant.update_sensor_data(data)
        plant.process_and_notify(data)

    elif topic == MQTT_TOPICS["pump"]:
        plant.update_pump_status(data)

def start_mqtt():
    client = mqtt.Client()
    if MQTT_TLS:
        client.tls_set()
        client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client

mqtt_client = start_mqtt()

def auto_watering_loop():
    CHECK_INTERVAL_SECONDS = 300  # 5 min
    while True:
        try:
            if device_commands.get("auto_watering_enabled"):
                data = plant.get_latest_sensor_data()
                if data:
                    user_row = db.users.find_one()
                    user_email = user_row.get("email") if user_row else None
                    thresholds = plant.get_settings()
                    weather_info = plant.get_weather_forecast(thresholds["location"])
                    evaluation = plant.evaluate_plant_status(data, thresholds, weather_info)
                    if plant.can_auto_water(evaluation):
                        plant.trigger_auto_watering(mqtt_client, user_email=user_email)
        except Exception as e:
            print(f"[AUTO] Error in auto-watering loop: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)

threading.Thread(target=auto_watering_loop, daemon=True).start()

# === API Endpoints ===

@app.post("/LeaFi/auth/login")
async def login(user: UserLogin):
    db_user = db.users.find_one({"username": user.username})
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    access_token = create_access_token(data={"sub": user.username})
    print(f"User authenticated: {user.username}")
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@app.post("/LeaFi/auth/register")
async def register(user: UserRegister):
    if db.users.find_one({"username": user.username}) or db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Username or email already exists")
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.users.insert_one({
        "username": user.username,
        "password_hash": password_hash,
        "email": user.email,
        "created_at": datetime.now()
    })
    db.settings.insert_one({
        "user_id": user.username,
        "min_humidity": 30,
        "max_temp": 35,
        "min_temp": 15,
        "min_light": 20,
        "max_light": 80,
        "location": "Cagliari"
    })
    return {"status": "success", "message": "User registered successfully"}

@app.post("/LeaFi/config/email")
async def set_email_config(config: EmailConfig, current_user: str = Depends(get_current_user)):
    db.config.update_one(
        {"type": "email"},
        {"$set": dict(config, type="email")},
        upsert=True
    )
    return {"status": "success", "message": "Email configuration updated"}

@app.get("/LeaFi/current-status")
async def get_current_status():
    data = plant.get_latest_sensor_data()
    pump = plant.get_latest_pump_status()
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
    thresholds = plant.get_settings()
    weather_info = plant.get_weather_forecast(thresholds["location"])
    evaluation = plant.evaluate_plant_status(data, thresholds, weather_info)
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

@app.get("/LeaFi/historical-data")
async def get_historical_data(hours: int = 24, current_user: str = Depends(get_current_user)):
    cutoff_time = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    data = list(db.sensor_data.find(
        {"timestamp": {"$gt": cutoff_iso}},
        {"_id": 0, "temperature": 1, "humidity": 1, "light_level": 1, "timestamp": 1}
    ).sort("timestamp", 1))
    print(f"Historical data request by {current_user} - {len(data)} records ({hours}h)")
    return {"data": data}

@app.get("/LeaFi/weather")
async def get_weather():
    settings = plant.get_settings()
    return plant.get_weather_forecast(settings["location"])

@app.post("/LeaFi/manual-water")
async def manual_water(current_user: str = Depends(get_current_user)):
    global last_auto_watering_time
    command = {
        "action": "water",
        "reason": "manual"
    }
    mqtt_client.publish(MQTT_TOPICS["command"], json.dumps(command), qos=1)
    last_auto_watering_time = datetime.now()
    print(f"[MQTT] Manual watering triggered by user: {current_user}")
    return {
        "status": "success",
        "message": "Manual watering command sent to device"
    }

@app.post("/LeaFi/toggle-auto-watering")
async def toggle_auto_watering(current_user: str = Depends(get_current_user)):
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
    return plant.get_settings(user_id=current_user)

@app.post("/LeaFi/settings")
async def update_settings(settings: ThresholdUpdate, current_user: str = Depends(get_current_user)):
    global cached_weather_time, cached_weather
    try:
        old_settings = plant.get_settings(user_id=current_user)
        update_result = db.settings.update_one(
            {"user_id": current_user},
            {"$set": settings.dict()}
        )
        if update_result.matched_count == 0:
            db.settings.insert_one(dict(settings, user_id=current_user))
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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "weather_api": "configured" if WEATHER_API_KEY else "not configured",
        "auto_watering": device_commands["auto_watering_enabled"]
    }

# === Static Files and Web Interface ===

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def dashboard():
    return FileResponse('templates/index.html')

@app.get("/login")
async def login_page():
    return FileResponse('templates/login.html')

# === Application Startup and Weather API Configuration ===

def setup_weather_api():
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

# === Server Entrypoint ===

if __name__ == "__main__":
    print("🌱 LeaFi - Backend Server")
    print("=====================================")
    # Ensure Fernet SMTP key is set
    ask_for_smtp_key()
    setup_weather_api()
    print("\nStarting HTTPS server...")
    print("Dashboard: https://localhost:8000")
    print("LeaFi MQTT endpoint (cloud): broker.mqttdashboard.com")
    print("Press Ctrl+C to stop server\n")
    try:
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