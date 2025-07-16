/**
 * LeaFi - NodeMCU ESP8266 (MQTT with QoS 1)
 *
 * This IoT system monitors plant environmental conditions and enables
 * remote plant care through automated and manual watering controls.
 *
 * Hardware Components:
 * - NodeMCU ESP8266: Wi-Fi connectivity and main controller
 * - Arduino UNO: 5V power supply for sensors and actuators
 * - DHT11 (D4): Temperature and humidity sensor
 * - LDR KY-018 (A0): Light level detection sensor
 * - 5V Water Pump + Relay (D2): Automated irrigation system
 *
 * Functional Requirements Implemented:
 * - FR1: Plant Condition Monitoring (sensors)
 * - FR8: Automated Watering (pump control)
 * - FR9: Remote Command Watering (pump control)
 */

#include <ESP8266WiFi.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <time.h> // For NTP time

// Hardware pin configuration
#define DHT_PIN D4        // DHT11 temperature/humidity sensor
#define LDR_PIN A0        // LDR photoresistor
#define RELAY_PIN D2      // Relay for water pump control

// Network configuration - Must be updated with your Wi-Fi credentials
const char* ssid = "YOUR-WIFI-SSID";
const char* password = "YOUR-WIFI-PASSWORD";

// MQTT broker configuration (public broker, MQTTs)
const char* mqtt_server = "broker.mqttdashboard.com";
const uint16_t mqtt_port = 8883;
const char* topic_sensor = "LeaFi/sensor_data";
const char* topic_command = "LeaFi/commands";
const char* topic_pump = "LeaFi/pump_status";

// Sensor and MQTT objects
DHT dht(DHT_PIN, DHT11);
WiFiClientSecure net;              // For MQTTs (TLS)
MQTTClient mqttClient(512);        // 256dpi/arduino-mqtt

// Timing intervals (NFR1: readings at least every 5 minutes)
const unsigned long SENSOR_READ_INTERVAL = 300000;   // 5 minutes
const unsigned long PUMP_DURATION = 10000;           // 10 seconds pump operation

// System state variables
unsigned long lastRead = 0;
unsigned long pumpStart = 0;
bool pumpActive = false;

// Sensor data storage
float temperature, humidity;
int lightLevel;

// NTP (Network Time Protocol) config for simple ISO8601 timestamp
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 7200;      // Italy summer time (UTC+2)
const int daylightOffset_sec = 0;     // No extra daylight offset

// Function declarations
void connectToWiFi();
void connectToMQTT();
void messageReceived(String &topic, String &payload);
void readEnvironmentalSensors();
void publishSensorData();
void activatePump(const char* reason, const char* trigger);
void stopPump();
void publishPumpStatus(const char* status);
void getISO8601Timestamp(char* buffer, size_t bufferSize);

/**
 * System initialization: Sets up hardware pins, Wi-Fi connection, and sensors.
 */
void setup() {
    Serial.begin(115200);
    Serial.println("LeaFi - Initializing...");

    // Configure hardware pins
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, LOW);  // Ensure pump is OFF at startup

    // Initialize DHT11 sensor
    dht.begin();
    delay(2000);  // Allow sensor stabilization

    // Accept all certificates (for demo/public broker)
    net.setInsecure();

    // Establish Wi-Fi connection
    connectToWiFi();

    // Setup NTP for time sync (for ISO8601 timestamps)
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.print("Waiting for NTP time sync");
    struct tm timeinfo;
    while (!getLocalTime(&timeinfo)) {
        Serial.print(".");
        delay(500);
    }
    Serial.println("\nNTP time synchronized!");

    // Setup MQTT client (256dpi/arduino-mqtt)
    mqttClient.begin(mqtt_server, mqtt_port, net);
    mqttClient.onMessage(messageReceived);

    // Connect MQTT
    connectToMQTT();

    Serial.println("System ready for plant monitoring");
}

/**
 * Main control loop.
 * Handles sensor readings, MQTT communication, and pump control.
 * Implements timing-based task scheduling for efficient operation.
 */
void loop() {
    // Maintain Wi-Fi connection
    if (WiFi.status() != WL_CONNECTED) {
        connectToWiFi();
    }

    // Maintain MQTT connection
    if (!mqttClient.connected()) {
        connectToMQTT();
    }
    mqttClient.loop();

    unsigned long currentTime = millis();

    // FR8: Stop pump after defined duration
    if (pumpActive && (currentTime - pumpStart >= PUMP_DURATION)) {
        stopPump();
    }

    // FR1: Read and publish sensor data at specified intervals
    if (currentTime - lastRead >= SENSOR_READ_INTERVAL) {
        readEnvironmentalSensors();
        publishSensorData();
        lastRead = currentTime;
    }

    delay(100);  // Small delay after each loop for stability
}

/**
 * Establishes Wi-Fi connection with retry mechanism.
 */
void connectToWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.printf("Connecting to WiFi SSID: %s", ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("WiFi connected successfully");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
}

/**
 * Establishes MQTT connection with retry mechanism.
 * Subscribes to command topic for remote control.
 */
void connectToMQTT() {
    // Generate unique client ID
    String clientId = "LeaFiClient-" + String(ESP.getChipId(), HEX);

    while (!mqttClient.connected()) {
        Serial.print("Connecting to MQTT broker...");
        if (mqttClient.connect(clientId.c_str())) {
            Serial.println("connected");
            mqttClient.subscribe(topic_command, 1);  // Subscribe to command topic, QoS 1
            Serial.printf("Subscribed to: %s (QoS 1)\n", topic_command);
        } else {
            Serial.print("failed, state=");
            Serial.print(mqttClient.lastError());
            Serial.println(" - retrying in 5 seconds");
            delay(5000);
        }
    }
}

/**
 * MQTT message callback function.
 * Handles incoming commands for automated/manual watering via JSON.
 */
void messageReceived(String &topic, String &payload) {
    Serial.printf("Message arrived on topic: %s\n", topic.c_str());
    Serial.println(payload);

    // Parse JSON command
    StaticJsonDocument<128> doc;
    DeserializationError error = deserializeJson(doc, payload);
    if (error) {
        Serial.print("JSON parse error in command: ");
        Serial.println(error.c_str());
        return;
    }

    // Check for watering command
    if (topic == topic_command) {
        const char* action = doc["action"];
        const char* reason = doc["reason"];
        if (action && String(action) == "water" && !pumpActive) {
            activatePump(reason ? reason : "MQTT command", reason ? reason : "unknown");
        }
    }
}

/**
 * FR1: Plant Condition Monitoring.
 * Reads environmental sensors (DHT11, LDR) and processes data.
 * Implements light level mapping and error handling.
 */
void readEnvironmentalSensors() {
    // Read temperature and humidity from DHT11
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();

    // Validate DHT11 readings with retry mechanism
    if (isnan(temperature) || isnan(humidity)) {
        Serial.println("DHT11 read error - retrying...");
        delay(100);
        temperature = dht.readTemperature();
        humidity = dht.readHumidity();
    }

    // Process valid sensor data
    if (!isnan(temperature) && !isnan(humidity)) {
        // Convert LDR reading to percentage (0-100%)
        // Lower values = brighter light, so invert the scale
        int rawLDR = analogRead(LDR_PIN);
        lightLevel = constrain(map(rawLDR, 200, 900, 100, 0), 0, 100);

        // Log sensor readings for debugging
        Serial.println("=== Sensor Readings ===");
        Serial.printf("Temperature: %.1f°C (DHT11-D4)\n", temperature);
        Serial.printf("Humidity: %.1f%% (DHT11-D4)\n", humidity);
        Serial.printf("Light Level: %d%% (LDR-A0)\n", lightLevel);
    } else {
        Serial.println("Failed to read valid sensor data");
    }
}

/**
 * FR1: Publish sensor data to MQTT broker (QoS 1).
 * Sends temperature, humidity, and light level readings as JSON.
 */
void publishSensorData() {
    if (!mqttClient.connected()) return;

    char isoTimestamp[25];
    getISO8601Timestamp(isoTimestamp, sizeof(isoTimestamp));

    char payload[192];
    snprintf(payload, sizeof(payload),
        "{\"temperature\":%.2f,\"humidity\":%.2f,\"light_level\":%d,\"timestamp\":\"%s\"}",
        temperature, humidity, lightLevel, isoTimestamp);

    // Publish with QoS 1, retained = false
    bool ok = mqttClient.publish(topic_sensor, payload, false, 1);
    Serial.printf("Published sensor data to %s: %s [%s]\n", topic_sensor, payload, ok ? "OK" : "FAIL");
}

/**
 * FR8/FR9: Activate water pump for irrigation upon command.
 * @param reason  Description of why watering was triggered
 * @param trigger Source of command (automatic/manual)
 */
void activatePump(const char* reason, const char* trigger) {
    Serial.printf("Pump activation requested - Reason: %s | Trigger: %s\n", reason, trigger);
    digitalWrite(RELAY_PIN, HIGH);
    pumpActive = true;
    pumpStart = millis();

    // Notify server of pump activation
    publishPumpStatus("on");
}

/**
 * Stops water pump operation after defined duration.
 */
void stopPump() {
    digitalWrite(RELAY_PIN, LOW);
    pumpActive = false;
    Serial.println("Water pump deactivated (timeout)");

    // Notify server of pump deactivation
    publishPumpStatus("off");
}

/**
 * Publish current pump status to MQTT broker (QoS 1).
 * Enables real-time monitoring of irrigation system.
 * @param status "on" or "off"
 */
void publishPumpStatus(const char* status) {
    if (!mqttClient.connected()) return;

    char isoTimestamp[25];
    getISO8601Timestamp(isoTimestamp, sizeof(isoTimestamp));

    char payload[96];
    snprintf(payload, sizeof(payload),
        "{\"status\":\"%s\",\"timestamp\":\"%s\"}", status, isoTimestamp);

    mqttClient.publish(topic_pump, payload, false, 1);
    Serial.printf("Published pump status to %s: %s\n", topic_pump, payload);
}

/**
 * Get ISO 8601 timestamp as string.
 * Very simple, just uses current time from NTP.
 */
void getISO8601Timestamp(char* buffer, size_t bufferSize) {
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
        strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%S", &timeinfo);
    } else {
        strncpy(buffer, "1970-01-01T00:00:00", bufferSize);
    }
}