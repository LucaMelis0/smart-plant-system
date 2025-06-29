/**
 * Smart Plant Monitor - NodeMCU ESP8266
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
 * - FR8: Automated and Manual Watering (pump control)
 *
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <DHT.h>

// Hardware pin configuration
#define DHT_PIN D4        // DHT11 temperature/humidity sensor
#define LDR_PIN A0        // LDR photoresistor
#define RELAY_PIN D2      // Relay for water pump control

// Network configuration - Must be updated with your Wi-Fi credentials and server URL
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverURL = "https://YOUR_SERVER_IP:8000";

// Sensor and communication objects
DHT dht(DHT_PIN, DHT11);
WiFiClientSecure client;
HTTPClient http;

// Timing intervals (NFR1: readings at least every 5 minutes)
const unsigned long SENSOR_READ_INTERVAL = 300000;      // 5 minutes (NFR1 requirement)
const unsigned long SERVER_UPDATE_INTERVAL = 300000;    // 5 minutes data transmission
const unsigned long COMMAND_POLL_INTERVAL = 3000;       // 3 seconds for responsive commands
const unsigned long PUMP_DURATION = 10000;              // 10 seconds pump operation

// System state variables
unsigned long lastRead = 0, lastUpdate = 0, lastCommandPoll = 0, pumpStart = 0;
bool pumpActive = false; // Water pump state (FR8)
bool autoWater = false;  // Auto-watering toggle (FR8)

// Sensor data storage
float temperature, humidity;
int lightLevel;

// System initialization: Sets up hardware pins, Wi-Fi connection, and sensors
void setup() {
    Serial.begin(115200);
    Serial.println("Smart Plant Monitor - Initializing...");

    // Configure hardware pins
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, LOW);  // Ensure pump is OFF at startup

    // Initialize DHT11 sensor
    dht.begin();
    delay(2000);  // Allow sensor stabilization

    // Establish Wi-Fi connection
    connectToWiFi();

    // Configure HTTPS client (ignore SSL certificates for development)
    client.setInsecure();

    Serial.println("System ready for plant monitoring");
}

/**
 * Main control loop
 * Handles sensor readings, server communication, and pump control
 * Implements timing-based task scheduling for efficient operation
 */
void loop() {
    unsigned long currentTime = millis();

    // FR8: Stop pump after defined duration
    if (pumpActive && (currentTime - pumpStart >= PUMP_DURATION)) {
        stopPump();
    }

    // FR1: Read sensor data at specified intervals (NFR1: every 5 minutes)
    if (currentTime - lastRead >= SENSOR_READ_INTERVAL) {
        readEnvironmentalSensors();
        lastRead = currentTime;
    }

    // Transmit sensor data to server
    if (currentTime - lastUpdate >= SERVER_UPDATE_INTERVAL) {
        transmitSensorData();
        lastUpdate = currentTime;
    }

    // FR8: Poll for manual watering commands (responsive control)
    if (currentTime - lastCommandPoll >= COMMAND_POLL_INTERVAL) {
        checkWateringCommands();
        lastCommandPoll = currentTime;
    }

    delay(100);  // Small delay after each loop
}

// Establishes Wi-Fi connection with retry mechanism
void connectToWiFi() {
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");

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
 * FR1: Plant Condition Monitoring
 * Reads environmental sensors and processes data
 * Implements light level mapping and error handling
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
 * Transmits sensor data to FastAPI backend
 * Implements FR1 data communication and FR2 status evaluation response
 */
void transmitSensorData() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected - attempting reconnection...");
        WiFi.reconnect();
        return;
    }

    // Prepare HTTPS POST request
    http.begin(client, String(serverURL) + "/api/sensor-data");
    http.addHeader("Content-Type", "application/json");

    // Create JSON payload with sensor data
    String jsonData = createSensorDataJSON();

    Serial.println("Transmitting data to server...");
    int responseCode = http.POST(jsonData);

    // Process server response
    if (responseCode >= 200 && responseCode < 300) {
        String response = http.getString();
        Serial.printf("Server response: %d (Success)\n", responseCode);

        // Parse server recommendations (FR2: Status Evaluation)
        processServerResponse(response);
    } else {
        Serial.printf("Server communication error: %d\n", responseCode);
    }

    http.end();
}

/**
 * Creates JSON payload for sensor data transmission
 * @return Formatted JSON string with current sensor readings
 */
String createSensorDataJSON() {
    return "{\"temperature\":" + String(temperature) +
           ",\"humidity\":" + String(humidity) +
           ",\"light_level\":" + String(lightLevel) +
           ",\"timestamp\":" + String(millis()) + "}";
}

/**
 * FR2: Process server response for plant status evaluation
 * Handles automatic watering decisions based on server analysis
 * @param response JSON response from server containing watering recommendations
 */
void processServerResponse(String response) {
    DynamicJsonDocument doc(256);

    if (!deserializeJson(doc, response)) {
        // FR8: Automatic watering based on server evaluation
        if (doc["should_water"] && autoWater && !pumpActive) {
            activatePump("Automatic watering - server recommendation");
        }

        // Display plant status information
        if (doc.containsKey("plant_status")) {
            Serial.printf("Plant Status: %s\n", doc["plant_status"].as<String>().c_str());
        }
    }
}

/**
 * FR8: Check for manual watering commands from server
 * Polls backend for user-initiated watering requests
 */
void checkWateringCommands() {
    http.begin(client, String(serverURL) + "/api/device-commands");
    int responseCode = http.GET();

    if (responseCode == 200) {
        DynamicJsonDocument doc(128);
        String response = http.getString();

        if (!deserializeJson(doc, response)) {
            // Manual watering command
            if (doc["manual_water"] && !pumpActive) {
                activatePump("Manual watering - user request");
            }

            // Auto-watering toggle
            if (doc.containsKey("auto_watering_enabled")) {
                autoWater = doc["auto_watering_enabled"];
                Serial.printf("Auto-watering: %s\n", autoWater ? "ENABLED" : "DISABLED");
            }
        }
    }

    http.end();
}

/**
 * FR8: Activate water pump for irrigation
 * @param reason Description of why watering was triggered
 */
void activatePump(String reason) {
    Serial.println(reason + " - Activating water pump (RELAY-D2)");

    digitalWrite(RELAY_PIN, HIGH);
    pumpActive = true;
    pumpStart = millis();

    // Notify server of pump activation
    updatePumpStatus(true);
}

// Stop water pump operation
void stopPump() {
    digitalWrite(RELAY_PIN, LOW);
    pumpActive = false;
    Serial.println("Water pump deactivated - safety timeout");

    // Notify server of pump deactivation
    updatePumpStatus(false);
}

/**
 * Update server with current pump status
 * Enables real-time monitoring of irrigation system
 * @param isActive Current pump operation state
 */
void updatePumpStatus(bool isActive) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Cannot update pump status - WiFi not connected");
        return;
    }

    http.begin(client, String(serverURL) + "/api/pump-status");
    http.addHeader("Content-Type", "application/json");

    String jsonStatus = "{\"is_on\":" + String(isActive ? "true" : "false") + "}";
    int responseCode = http.POST(jsonStatus);

    if (responseCode >= 200 && responseCode < 300) {
        Serial.println("Pump status updated on server");
    } else {
        Serial.printf("Failed to update pump status: %d\n", responseCode);
    }

    http.end();
}
