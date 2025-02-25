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
}

void processCommand(String command) {
    int motorNum;
    char direction;
    int steps;
    int velocity;
    int accelTime;

    Serial.println("Processing command: " + command); // Debugging

    if (sscanf(command.c_str(), "%d,%c,%d,%d,%d", &motorNum, &direction, &steps, &velocity, &accelTime) == 5) {
        Serial.printf("Parsed command: Motor %d, Direction %c, Steps %d, Velocity %d, Accel %d\n",
                      motorNum, direction, steps, velocity, accelTime);

        if (motorNum >= 1 && motorNum <= MOTOR_COUNT) {
            int motorIndex = motorNum - 1;
            bool newDirection = (direction == 'F' || direction == 'f');

            Serial.printf("Setting Motor %d Direction: %s\n", motorNum, newDirection ? "FORWARD" : "BACKWARD");
            digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);

            // Backlash Compensation
            if (motors[motorIndex].lastDirection != newDirection) {
                Serial.printf("Applying Backlash Compensation: %d steps\n", backlashSteps[motorIndex]);
                moveSteps(motorIndex, backlashSteps[motorIndex], velocity);
                moveSteps(motorIndex, -backlashSteps[motorIndex], velocity);
            }

            Serial.printf("Moving Motor %d: %d steps at velocity %d\n", motorNum, steps, velocity);
            moveSteps(motorIndex, steps, velocity);

            motors[motorIndex].targetSteps = steps;
            motors[motorIndex].currentStep = 0;
            motors[motorIndex].velocity = velocity;
            motors[motorIndex].accelSteps = (steps / 2 < (velocity * accelTime / 1000)) ? steps / 2 : (velocity * accelTime / 1000);
            motors[motorIndex].active = true;
            motors[motorIndex].lastDirection = newDirection;
        }
    } else {
        Serial.println("Invalid Command Format!");
    }
}

void moveSteps(int motorIndex, int steps, int maxSpeed) {
    digitalWrite(motors[motorIndex].enablePin, LOW); // Ensure motor is enabled
    Serial.printf("Motor %d | Steps: %d | Max Speed: %d\n", motorIndex + 1, steps, maxSpeed);

    int accelSteps = motors[motorIndex].accelSteps; // Acceleration step count
    int decelSteps = accelSteps; // Deceleration step count
    int cruiseSteps = steps - (accelSteps + decelSteps); // Remaining steps

    int minDelay = 1000000/maxSpeed;  // Fastest step delay in µs
    int maxDelay = 2000; // Slowest step delay for acceleration start
    int stepDelay = maxDelay; // Start slow

    Serial.printf("Motor %d | Accel: %d | Cruise: %d | Decel: %d\n", motorIndex + 1, accelSteps, cruiseSteps, decelSteps);

    // **Acceleration Phase**
    for (int i = 0; i < accelSteps; i++) {
        stepDelay = maxDelay - ((maxDelay - minDelay) * i / accelSteps); // Decrease delay
        stepOnce(motorIndex, stepDelay);
    }

    // **Cruise Phase (Constant Speed)**
    for (int i = 0; i < cruiseSteps; i++) {
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
    }


    // **Deceleration Phase**
    for (int i = 0; i < decelSteps; i++) {
        stepDelay = minDelay + ((maxDelay - minDelay) * i / decelSteps); // Increase delay
        stepOnce(motorIndex, stepDelay);
    }

    Serial.printf("Motor %d Movement Complete\n", motorIndex + 1);
}

// **Single Step Function (Helper)**
void stepOnce(int motorIndex, int delayTime) {
    Serial.printf("Stepping Motor %d | Delay: %d µs\n", motorIndex + 1, delayTime);
    digitalWrite(motors[motorIndex].stepPin, HIGH);
    delayMicroseconds(delayTime);
    digitalWrite(motors[motorIndex].stepPin, LOW);
    delayMicroseconds(delayTime);
}

