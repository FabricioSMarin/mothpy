#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

// WiFi Credentials
//const char* ssid = "Marinf2.4";
//const char* password = "3V@$!VE_Wifi2.4";
const char* ssid = "auranox";
const char* password = "C0ndu(tive_Wifi";
WebServer server(80); // Add this line to declare the server instance
Preferences preferences;

#define MOTOR_COUNT 3

// **Stepper Motor Pin Assignments**
#define STEP_PIN_1 15
#define DIR_PIN_1  14
#define ENABLE_PIN_1 13

#define STEP_PIN_2 16
#define DIR_PIN_2  17
#define ENABLE_PIN_2 18

#define STEP_PIN_3 27
#define DIR_PIN_3  22
#define ENABLE_PIN_3 19

volatile bool emergencyStop = false;
volatile bool paused = false;

// **Persistent Data: Backlash, Position, Resolution, Soft Limits**
int backlashSteps[MOTOR_COUNT] = {5, 3, 4};
int motorVelocities[MOTOR_COUNT] = {500, 400, 300};
int motorAccelerations[MOTOR_COUNT] = {300, 200, 100};
long motorPositions[MOTOR_COUNT] = {0, 0, 0};
long softLimitPositive[MOTOR_COUNT] = {10000, 10000, 10000};
long softLimitNegative[MOTOR_COUNT] = {-10000, -10000, -10000};
float stepsPerUnit[MOTOR_COUNT] = {200.0, 200.0, 200.0}; // Steps per rev
String unitType[MOTOR_COUNT] = {"degrees", "degrees", "degrees"};


// **Stepper Motor Struct**
struct StepperMotor {
    int stepPin;
    int dirPin;
    int enablePin;
    int targetSteps;
    int currentStep;
    int stepDelay;
    int velocity;
    int accelSteps;
    bool active;
    bool lastDirection;  // Stores the last direction (true = forward, false = backward)
};
// **Motor Definitions**
// Define Motors
StepperMotor motors[MOTOR_COUNT] = {
    {STEP_PIN_1, DIR_PIN_1, ENABLE_PIN_1, 0, 0, 0, 0, 0, false, true},
    {STEP_PIN_2, DIR_PIN_2, ENABLE_PIN_2, 0, 0, 0, 0, 0, false, true},
    {STEP_PIN_3, DIR_PIN_3, ENABLE_PIN_3, 0, 0, 0, 0, 0, false, true}
};

// **Web Interface**
const char webpage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Stepper Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { text-align: center; font-family: Arial; }
        button, input, select { padding: 10px; margin: 5px; font-size: 16px; }
    </style>
</head>
<body>
    <h2>Stepper Motor Control</h2>

    <h3>Manual Command</h3>
    <div>
        <input type="text" id="cmd" placeholder="1,B,2000,500,300">
        <button onclick="sendCommand()">Move Motor</button><br>
    </div>

    <script>
        function sendCommand() {
            let command = document.getElementById("cmd").value;
            fetch("/command?cmd=" + command) 
                .then(response => response.text()) 
                .then(data => alert(data)) // Show confirmation message
                .catch(error => console.error('Error:', error));
        }
    </script>
</body>
</html>
)rawliteral";



void setup() {
    Serial.begin(115200);
    
    preferences.begin("backlash", false);
    for (int i = 0; i < MOTOR_COUNT; i++) {
        backlashSteps[i] = preferences.getInt(("motor" + String(i+1)).c_str(), backlashSteps[i]);
    }
    
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) { delay(500); }
    
    server.on("/", []() { server.send(200, "text/html", webpage); });

    server.on("/command", []() {
        String cmd = server.arg("cmd");
        processCommand(cmd);
        server.send(200, "text/plain", "Command Received: " + cmd);
    });

    server.begin();

    // Configure motor pins
    for (int i = 0; i < MOTOR_COUNT; i++) {
        pinMode(motors[i].stepPin, OUTPUT);
        pinMode(motors[i].dirPin, OUTPUT);
        pinMode(motors[i].enablePin, OUTPUT);
        digitalWrite(motors[i].enablePin, LOW);  // Enable motors
    }
}

void loop() {
    server.handleClient();
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        processCommand(command);
    }
    moveMotorsSynchronously();
}


// Process Commands from Serial or Web
void processCommand(String command) {
    int motorNum;
    char direction;
    int steps;
    int velocity;
    int accelTime;

    if (sscanf(command.c_str(), "%d,%c,%d,%d,%d", &motorNum, &direction, &steps, &velocity, &accelTime) == 5) {
        if (motorNum >= 1 && motorNum <= MOTOR_COUNT) {
            int motorIndex = motorNum - 1;
            bool newDirection = (direction == 'F' || direction == 'f');

            if (motors[motorIndex].lastDirection != newDirection) {
                // Apply backlash compensation
                Serial.printf("Backlash Compensation: Motor %d moving extra %d steps.\n", motorNum, backlashSteps[motorIndex]);
                digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);
                moveSteps(motorIndex, backlashSteps[motorIndex], 500);
                moveSteps(motorIndex, -backlashSteps[motorIndex], 500);
            }

            digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);
            motors[motorIndex].targetSteps = steps;
            motors[motorIndex].currentStep = 0;
            motors[motorIndex].velocity = velocity;
            motors[motorIndex].accelSteps = (steps / 2 < (velocity * accelTime / 1000)) ? steps / 2 : (velocity * accelTime / 1000);
            motors[motorIndex].active = true;
            motors[motorIndex].lastDirection = newDirection;
        }
    }
}

// Move Specific Steps
void moveSteps(int motorIndex, int steps, int delayTime) {
    digitalWrite(motors[motorIndex].enablePin, LOW);
    for (int i = 0; i < abs(steps); i++) {
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(delayTime);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(delayTime);
    }
    moveMotorsSynchronously();
}

// Synchronized Motion Control (Same as before)
void moveMotorsSynchronously() {
    for (int i = 0; i < MOTOR_COUNT; i++) {
        if (motors[i].active && motors[i].currentStep < motors[i].targetSteps) {
            digitalWrite(motors[i].stepPin, HIGH);
            delayMicroseconds(500);
            digitalWrite(motors[i].stepPin, LOW);
            motors[i].currentStep++;

            if (motors[i].currentStep >= motors[i].targetSteps) {
                motors[i].active = false;
            }
        }
    }
}

