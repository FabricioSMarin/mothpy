#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

// WiFi Credentials
const char* ssid = "Marinf2.4";
const char* password = "3V@$!VE_Wifi2.4";
//const char* ssid = "auranox";
//const char* password = "C0ndu(tive_Wifi";
WebServer server(80); // Add this line to declare the server instance
Preferences preferences;

#define MOTOR_COUNT 2

// **Stepper Motor Pin Assignments** 30-pin board
// #define STEP_PIN_1 15
// #define DIR_PIN_1  14
// #define ENABLE_PIN_1 13

// #define STEP_PIN_2 16
// #define DIR_PIN_2  17
// #define ENABLE_PIN_2 18

// #define STEP_PIN_3 27
// #define DIR_PIN_3  22
// #define ENABLE_PIN_3 19

#define STEP_PIN_1 5
#define DIR_PIN_1  4
#define ENABLE_PIN_1 19

// #define STEP_PIN_2 17
// #define DIR_PIN_2  16
// #define ENABLE_PIN_2 18

#define STEP_PIN_2 22
#define DIR_PIN_2  21
#define ENABLE_PIN_2 23


volatile bool emergencyStop = false;
//NOTE: nema17 RPM range 100-500 == 600us delay (could have sworn I've gone to 200-300us..)
//Minimum delay, unloaded is 80 us; way faster than the alleged 100-500 as described online. 
//80us = 12500 steps/sec = 3.75k RPM
// **Persistent Data: Backlash, Position, Resolution, Soft Limits**
int backlashSteps[MOTOR_COUNT] = {10, 10}; //steps
int motorVelocities[MOTOR_COUNT] = {1250,1250}; //steps/sec
float motorAccelerations[MOTOR_COUNT] = {1.0,1.0}; //seconds
long motorPositions[MOTOR_COUNT] = {0, 0}; //steps
long softLimitPositive[MOTOR_COUNT] = {1000000, 1000000}; //steps
long softLimitNegative[MOTOR_COUNT] = {-1000000, -1000000}; //steps
int stepsPerUnit[MOTOR_COUNT] = {200, 200}; // Steps per degree/mm
String unitType[MOTOR_COUNT] = {"degrees", "degrees"}; 

// **Stepper Motor Struct**
struct StepperMotor {
    int stepPin;
    int dirPin;
    int enablePin;
    int velocity;
    float accelTime;
    int backlash;
    int nlim;
    int plim;
    int position;
    bool active;
    bool lastDirection;  // Stores the last direction (true = forward, false = backward)
};
// **Motor Definitions**
// Define Motors
StepperMotor motors[MOTOR_COUNT] = {
    {STEP_PIN_1, DIR_PIN_1, ENABLE_PIN_1, 5000, 1.0, 0, -1000000, 1000000, 0, false, true},
    {STEP_PIN_2, DIR_PIN_2, ENABLE_PIN_2, 5000, 1.0, 0, -1000000, 1000000, 0, false, true},
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

    <h3>Motor 1 settings</h3>
    <div>
        <div style="font-size: 18px; font-weight: bold; margin: 10px 0;">
            Position: <span id="pos1">0 steps</span>
            <button onclick="setZero(1)">Set Zero</button>
        </div>
        <button onclick="setMotorState(1, 1)">Enable Motor 1</button>
        <button onclick="setMotorState(1, 0)">Disable Motor 1</button><br>
        <label> resolution <input type="number" id="res1" oninput="saveInput(1, 'res')"> 
            <select id="unit1" onchange="saveInput(1, 'unit')">
                <option value="degrees">Degrees</option>
                <option value="mm">Millimeters</option>
            </select>
        </label>
        <button onclick="setResolution(1)">Set</button><br>
        <label> Pos Limit <input type="number" id="posLimit1" oninput="saveInput(1, 'posLimit')"></label>
        <label> Neg Limit <input type="number" id="negLimit1" oninput="saveInput(1, 'negLimit')"></label>
        <button onclick="setSoftLimits(1)">Set</button><br>
        <label> velocity (steps/sec) <input type="number" id="velo1" oninput="saveInput(1, 'velo')"></label>
        <button onclick="setVelocity(1)">Set</button><br>
        <label> acceleration (s) <input type="number" id="accel1" oninput="saveInput(1, 'accel')"></label>
        <button onclick="setAcceleration(1)">Set</button><br>
        <label> backlash (steps) <input type="number" id="backlsh1" oninput="saveInput(1, 'backlsh')"></label>
        <button onclick="setBacklash(1)">Set</button><br>
    </div>

    <h3>Motor 2 settings</h3>
    <div>
        <div style="font-size: 18px; font-weight: bold; margin: 10px 0;">
            Position: <span id="pos2">0 steps</span>
            <button onclick="setZero(2)">Set Zero</button>
        </div>
        <button onclick="setMotorState(2, 1)">Enable Motor 2</button>
        <button onclick="setMotorState(2, 0)">Disable Motor 2</button><br>
        <label> resolution <input type="number" id="res2" oninput="saveInput(2, 'res')"> 
            <select id="unit2" onchange="saveInput(2, 'unit')">
                <option value="degrees">Degrees</option>
                <option value="mm">Millimeters</option>
            </select>
        </label>
        <button onclick="setResolution(2)">Set</button><br>
        <label> Pos Limit <input type="number" id="posLimit2" oninput="saveInput(2, 'posLimit')"></label>
        <label> Neg Limit <input type="number" id="negLimit2" oninput="saveInput(2, 'negLimit')"></label>
        <button onclick="setSoftLimits(2)">Set</button><br>
        <label> velocity (steps/sec) <input type="number" id="velo2" oninput="saveInput(2, 'velo')"></label>
        <button onclick="setVelocity(2)">Set</button><br>
        <label> acceleration (s) <input type="number" id="accel2" oninput="saveInput(2, 'accel')"></label>
        <button onclick="setAcceleration(2)">Set</button><br>
        <label> backlash (steps) <input type="number" id="backlsh2" oninput="saveInput(2, 'backlsh')"></label>
        <button onclick="setBacklash(2)">Set</button><br>
    </div>


    <h3>Move Motors</h3>
    <div>
        <label> <select id="dir1" onchange="saveInput(1, 'dir')">
            <option value="F">Forward</option>
            <option value="B">Backward</option>
        </select> Steps: <input type="number" id="steps1" oninput="saveInput(1, 'steps')">
        <button onclick="moveMotor(1)">Move</button><br>

        <label> <select id="dir2" onchange="saveInput(2, 'dir')">
            <option value="F">Forward</option>
            <option value="B">Backward</option>
        </select> Steps: <input type="number" id="steps2" oninput="saveInput(2, 'steps')">
        <button onclick="moveMotor(2)">Move</button><br>

    </div>


    <h3>Manual Command</h3>
    <div>
        <input type="text" id="cmd" placeholder="move:1,B,2000">
        <button onclick="sendCommand()">Move Motor</button><br>
    </div>

    <h3>Controls</h3>
    <button onclick="emergencyStop()">Emergency Stop</button>

    <script>


        document.addEventListener("DOMContentLoaded", function () {
            [1, 2].forEach(motor => loadInputs(motor)); // Load settings for all motors
            updatePositions(); // Initial position update
            setInterval(updatePositions, 500); // Update positions every 500ms
        });

        function updatePositions() {
            fetch("/get_positions")
                .then(response => response.json())
                .then(data => {
                    data.motors.forEach(motor => {
                        let steps = motor.steps;
                        let resolution = motor.resolution;
                        let unit = motor.unit;
                        let id = motor.id;
                        
                        let displayText = steps + " steps";
                        
                        // If resolution is defined (not zero), calculate and display real position
                        if (resolution && resolution > 0) {
                            let realPos = steps / resolution;
                            displayText = realPos.toFixed(2) + " " + unit + " (" + steps + " steps)";
                        }
                        
                        document.getElementById("pos" + id).textContent = displayText;
                    });
                })
                .catch(error => console.error('Error updating positions:', error));
        }

        function setZero(motor) {
            fetch(`/set_position?motor=${motor}&pos=0`)
                .then(response => response.text())
                .then(data => {
                    updatePositions(); // Update display immediately
                })
                .catch(error => console.error('Error:', error));
        }

        function saveInput(motor, field) {
            let value = document.getElementById(field + motor).value;
            localStorage.setItem(field + motor, value);
        }

        function loadInputs(motor) {
            const fields = ["res", "unit", "posLimit", "negLimit", "velo", "accel", "backlsh", "dir", "steps"];
            fields.forEach(field => {
                let savedValue = localStorage.getItem(field + motor);
                if (savedValue !== null) {
                    let element = document.getElementById(field + motor);
                    if (element) {
                        element.value = savedValue;
                    }
                }
            });
        }

        function setMotorState(motor, state) {
            fetch(`/set_motor_state?motor=${motor}&state=${state}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function setResolution(motor) {
            let res = document.getElementById("res" + motor).value;
            let unit = document.getElementById("unit" + motor).value;
            fetch(`/set_resolution?motor=${motor}&res=${res}&unit=${unit}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function setSoftLimits(motor) {
            let posLimit = document.getElementById("posLimit" + motor).value;
            let negLimit = document.getElementById("negLimit" + motor).value;
            fetch(`/set_soft_limits?motor=${motor}&posLimit=${posLimit}&negLimit=${negLimit}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function setVelocity(motor) {
            let velocity = document.getElementById("velo" + motor).value;
            fetch(`/set_velocity?motor=${motor}&velocity=${velocity}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function setAcceleration(motor) {
            let accel = document.getElementById("accel" + motor).value;
            fetch(`/set_acceleration?motor=${motor}&accel=${accel}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function setBacklash(motor) {
            let backlsh = document.getElementById("backlsh" + motor).value;
            fetch(`/set_backlash?motor=${motor}&backlsh=${backlsh}`)
                .then(response => response.text())
                .then(data => alert(data));
        }

        function emergencyStop() {
            fetch("/emergency_stop");
            alert("Emergency Stop Activated!");
        }

        function moveMotor(motor) {
            let dir = document.getElementById("dir" + motor).value;
            let steps = document.getElementById("steps" + motor).value;
            let velo = document.getElementById("velo" + motor).value;
            let accel = document.getElementById("accel" + motor).value;
            let command = "move:" + motor + "," + dir + "," + steps;            
            fetch("/command?cmd=" + command)
                .catch(error => console.error('Error:', error));
        }

        function sendCommand() {
            let command = document.getElementById("cmd").value;
            fetch("/command?cmd=" + command) 
                .catch(error => console.error('Error:', error));
        }
    </script>
</body>
</html>
)rawliteral";


void setup() {
    Serial.begin(115200);
    delay(1000); // Give serial time to initialize
    Serial.println("\n\nESP32 Stepper Motor Controller Starting...");
    
    preferences.begin("backlash", false);
    for (int i = 0; i < MOTOR_COUNT; i++) {
        motors[i].backlash = preferences.getInt(("motor" + String(i+1)).c_str(), motors[i].backlash);
        motorPositions[i] = preferences.getLong(("motor" + String(i+1) + "_position").c_str(), motorPositions[i]);
        stepsPerUnit[i] = preferences.getFloat(("motor" + String(i+1) + "_res").c_str(), stepsPerUnit[i]);
        unitType[i] = preferences.getString(("motor" + String(i+1) + "_unit").c_str(), unitType[i]);
        Serial.printf("Motor %d: Backlash=%d, Position=%ld, Resolution=%d %s\n", 
                      i+1, motors[i].backlash, motorPositions[i], stepsPerUnit[i], unitType[i].c_str());
    }
    
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) { 
        delay(500); 
        Serial.print(".");
    }
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    
    server.on("/", []() { 
        Serial.println("Serving webpage");
        server.send(200, "text/html", webpage); 
    });
    server.on("/command", []() {
        String cmd = server.arg("cmd");
        Serial.println("Received command: " + cmd);
        processCommand(cmd);
        server.send(200, "text/plain", "Command processed: " + cmd);
    });

    server.on("/emergency_stop", []() {
        emergencyStop = true;
        Serial.println("Emergency stop activated!");
        server.send(200, "text/plain", "Emergency stop activated!");
    });


    server.on("/set_motor_state", []() {
        int motor = server.arg("motor").toInt() - 1;
        bool enableState = server.arg("state").toInt();
        Serial.printf("Setting motor %d state to %s\n", motor + 1, enableState ? "enabled" : "disabled");
        if (motor >= 0 && motor < MOTOR_COUNT) {
            digitalWrite(motors[motor].enablePin, enableState ? LOW : HIGH);
            server.send(200, "text/plain", "Motor " + String(motor + 1) + " " + (enableState ? "enabled" : "disabled"));
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_resolution", []() {
        int motor = server.arg("motor").toInt() - 1;
        float res = server.arg("res").toFloat();
        String unit = server.arg("unit");
        Serial.printf("Setting motor %d resolution to %f %s\n", motor + 1, res, unit.c_str());

        if (motor >= 0 && motor < MOTOR_COUNT) {
            stepsPerUnit[motor] = res;
            unitType[motor] = unit;
            preferences.putFloat(("motor" + String(motor+1) + "_res").c_str(), res);
            preferences.putString(("motor" + String(motor+1) + "_unit").c_str(), unit);
            server.send(200, "text/plain", "Motor " + String(motor + 1) + " resolution set to " + String(res) + " " + unit);
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_soft_limits", []() {
        int motor = server.arg("motor").toInt() - 1;
        long posLimit = server.arg("posLimit").toInt();
        long negLimit = server.arg("negLimit").toInt();
        Serial.printf("Setting motor %d soft limits: pos=%ld, neg=%ld\n", motor + 1, posLimit, negLimit);

        if (motor >= 0 && motor < MOTOR_COUNT) {
            motors[motor].plim = posLimit;
            motors[motor].nlim = negLimit;
            preferences.putLong(("motor" + String(motor+1) + "_soft_pos").c_str(), posLimit);
            preferences.putLong(("motor" + String(motor+1) + "_soft_neg").c_str(), negLimit);
            server.send(200, "text/plain", "Motor " + String(motor + 1) + " soft limits set: pos=" + String(posLimit) + ", neg=" + String(negLimit));
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_backlash", []() {
        int motor = server.arg("motor").toInt() - 1;
        int backlsh = server.arg("backlsh").toInt();
        Serial.printf("Setting motor %d backlash to %d steps\n", motor + 1, backlsh);
        if (motor >= 0 && motor < MOTOR_COUNT) {
            motors[motor].backlash = backlsh;
            preferences.putInt(("motor" + String(motor+1)).c_str(), backlsh);
            server.send(200, "text/plain", "Motor " + String(motor + 1) + " backlash set to " + String(backlsh) + " steps");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_velocity", []() {
        int motor = server.arg("motor").toInt() - 1;
        int velo = server.arg("velocity").toInt();
        Serial.printf("Setting motor %d velocity to %d steps/sec\n", motor + 1, velo);
        if (motor >= 0 && motor < MOTOR_COUNT) {
            motors[motor].velocity = velo;
            preferences.putInt(("motor" + String(motor+1) + "_velo").c_str(), velo);
            server.send(200, "text/plain", "Motor " + String(motor + 1) + " velocity set to " + String(velo) + " steps/sec");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_acceleration", []() {
        int motorIndex = server.arg("motor").toInt() - 1;
        float accel = server.arg("accel").toFloat();
        Serial.printf("Setting motor %d acceleration to %f seconds\n", motorIndex + 1, accel);
        if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
            motors[motorIndex].accelTime = accel;
            preferences.putFloat(("motor" + String(motorIndex+1) + "_accel").c_str(), accel);
            server.send(200, "text/plain", "Motor " + String(motorIndex + 1) + " acceleration set to " + String(accel) + " seconds");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_position", []() {
        int motorIndex = server.arg("motor").toInt() - 1;
        long pos = server.arg("pos").toInt();
        Serial.printf("Setting motor %d position to %ld\n", motorIndex + 1, pos);
        if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
            motorPositions[motorIndex] = pos;
            preferences.putLong(("motor" + String(motorIndex+1) + "_position").c_str(), pos);
            server.send(200, "text/plain", "Motor " + String(motorIndex + 1) + " position set to " + String(pos));
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/get_positions", []() {
        String json = "{\"motors\":[";
        for (int i = 0; i < MOTOR_COUNT; i++) {
            if (i > 0) json += ",";
            json += "{\"id\":" + String(i+1);
            json += ",\"steps\":" + String(motorPositions[i]);
            json += ",\"resolution\":" + String(stepsPerUnit[i]);
            json += ",\"unit\":\"" + unitType[i] + "\"}";
        }
        json += "]}";
        server.send(200, "application/json", json);
    });
    
    server.begin();
    Serial.println("Web server started!");

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
        int separatorIndex = command.indexOf(':');

        if (command=="Hello") {
            Serial.print("Hi");
        }

        if (separatorIndex != -1) {  // Ensure ":" exists in the string
            String key = command.substring(0, separatorIndex);
            String value = command.substring(separatorIndex + 1);
            key.trim();  // Remove spaces
            value.trim();

            if (key == "set_resolution") {
                int commaIndex = value.indexOf(',');
                if (commaIndex != -1) {  // Ensure there is a comma
                    String motor = value.substring(0, commaIndex);
                    String resolution = value.substring(commaIndex + 1);
                    motor.trim();
                    resolution.trim();

                    int motorIndex = motor.toInt();  // Convert to integer
                    int res = resolution.toInt();  // Convert to integer
                    Serial.print("Motor ");
                    Serial.print(motorIndex);
                    Serial.print(" resolution set to ");
                    Serial.println(res);

                    if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
                        stepsPerUnit[motorIndex] = res;
                        // unitType[motor] = unit;
                        preferences.putFloat(("motor" + String(motorIndex+1) + "_res").c_str(), res);
                        // preferences.putString(("motor" + String(motor+1) + "_unit").c_str(), unit);
                    }
                  }

            } else if (key == "set_acceleration") {
                int commaIndex = value.indexOf(',');
                if (commaIndex != -1) {  // Ensure there is a comma
                    String motor = value.substring(0, commaIndex);
                    String acceleration = value.substring(commaIndex + 1);
                    motor.trim();
                    acceleration.trim();

                    int motorIndex = motor.toInt();  // Convert to integer
                    int acc = acceleration.toInt();  // Convert to integer
                    Serial.print("Motor ");
                    Serial.print(motor);
                    Serial.print(" accleration set to ");
                    Serial.println(acc);

                    if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
                        motors[motorIndex].accelTime = acc;
                        // unitType[motor] = unit;
                        preferences.putInt(("motor" + String(motorIndex+1)).c_str(), acc);
                    }
                  }
            } else if (key == "set_backlash") {
                int commaIndex = value.indexOf(',');
                if (commaIndex != -1) {  // Ensure there is a comma
                    String motor = value.substring(0, commaIndex);
                    String backlash = value.substring(commaIndex + 1);
                    motor.trim();
                    backlash.trim();

                    int motorIndex = motor.toInt();  // Convert to integer
                    int bac = backlash.toInt();  // Convert to integer
                    Serial.print("Motor ");
                    Serial.print(motorIndex);
                    Serial.print(" backlash set to ");
                    Serial.println(bac);

                    if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
                        motors[motorIndex].accelTime = bac;
                        // unitType[motor] = unit;
                        preferences.putInt(("motor" + String(motorIndex+1)).c_str(), bac);
                    }
                }
                
            } else if (key == "move") {
                    processCommand(value);
                  
            } else {
                Serial.print("Invalid command");
                
              }
        }       
    }
}

void processCommand(String command) {
    int motorNum;
    char direction;
    int steps;

    Serial.println("Processing command: " + command); // Debugging

    // Strip "move:" prefix if present (for web interface commands)
    if (command.startsWith("move:")) {
        command = command.substring(5); // Remove "move:" prefix
        Serial.println("Stripped prefix, command is now: " + command);
    }

    if (sscanf(command.c_str(), "%d,%c,%d", &motorNum, &direction, &steps) == 3) {
        Serial.printf("Parsed command: Motor %d, Direction %c, Steps %d\n",
                      motorNum, direction, steps);

        if (motorNum >= 1 && motorNum <= MOTOR_COUNT) {
            int motorIndex = motorNum - 1;
            int velo = motors[motorIndex].velocity;
            int bac = motors[motorIndex].backlash;
            float acc = motors[motorIndex].accelTime;
            bool newDirection = (direction == 'F' || direction == 'f');

            // Backlash Compensation - apply when direction changes
            if (motors[motorIndex].lastDirection != newDirection && motors[motorIndex].backlash > 0) {
                Serial.printf("Direction changed - Applying Backlash Compensation: %d steps\n", motors[motorIndex].backlash);
                // Set direction for backlash compensation (in the new direction)
                digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);
                // Move backlash steps in the new direction to take up slack
                // Use a fast speed (higher than normal) and no acceleration for backlash compensation
                int backlashSpeed = velo > 2000 ? velo : 2000; // Use at least 2000 steps/sec for backlash
                moveSteps(motorIndex, motors[motorIndex].backlash, backlashSpeed, 0.0);
                // Update position for backlash compensation
                motorPositions[motorIndex] += newDirection ? motors[motorIndex].backlash : -motors[motorIndex].backlash;
                preferences.putLong(("motor" + String(motorIndex+1) + "_position").c_str(), motorPositions[motorIndex]);
            }

            // Set direction for main movement
            digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);

            moveSteps(motorIndex, steps, velo, acc);
            // Update position for main movement
            motorPositions[motorIndex] += newDirection ? steps : -steps;
            preferences.putLong(("motor" + String(motorIndex+1) + "_position").c_str(), motorPositions[motorIndex]);
            
            motors[motorIndex].active = true;
            motors[motorIndex].lastDirection = newDirection;
        } else {
            Serial.printf("Invalid motor number: %d (must be 1-%d)\n", motorNum, MOTOR_COUNT);
        }
    } else {
        Serial.printf("Invalid Command Format! Expected format: 'motor,direction,steps' or 'move:motor,direction,steps'\n");
        Serial.printf("Received: '%s'\n", command.c_str());
        Serial.printf("Example: '1,B,2000' or 'move:1,B,2000'\n");
    }
}

void moveSteps(int motorIndex, int steps, int maxSpeed, float accelTime) {
    digitalWrite(motors[motorIndex].enablePin, LOW); // Ensure motor is enabled
    Serial.printf("Motor %d | Steps: %d | Max Speed: %d | Accel Time %f\n", motorIndex + 1, steps, maxSpeed, accelTime);

    // If acceleration time is zero, skip acceleration/deceleration and run at max speed
    if (accelTime == 0.0 || accelTime < 0.001) {
        double minDelay = (1.0 / maxSpeed) * 1000000; // Convert to microseconds
        Serial.printf("No acceleration - running at max speed: %f microseconds per step\n", minDelay);
        for (int i = 0; i < steps; i++) {
            digitalWrite(motors[motorIndex].stepPin, HIGH);
            delayMicroseconds(minDelay);
            digitalWrite(motors[motorIndex].stepPin, LOW);
            delayMicroseconds(minDelay);
        }
        Serial.printf("Motor %d Movement Complete\n", motorIndex + 1);
        return;
    }

    // Constants
    const int max_M = steps/2;  // Max upper limit for M
    const double sum_constant = 2000e-6;  // 2000 * 10^-6 aboslute max delay (min speed)
    const float min_value = 1.0/maxSpeed;  // 80 * 10^-6 is absolute min delay (max speed)
    double R_target = accelTime/2;  // Desired sum target, divide by two because off by factor of 2 somehow
        Serial.print("minDelay d: ");
        Serial.print(min_value*1000000, 10);
        Serial.println(" micro seconds");
    int optimal_M = -1;
    double optimal_t = -1.0;
    double computed_sum = 0.0;
    
    for (int M = max_M; M > 0; M--) { // Iterate from max_M downwards to find the largest valid M
        double sum_i_part = (M * (M + 1)) / 2.0; // Compute sum of i from 0 to M using formula M*(M+1)/2
        double sum_constant_part = (M + 1) * sum_constant;
        double t_value = (sum_constant_part - R_target) / sum_i_part; // Solve for t
        double min_value_check = sum_constant - M * t_value; // Check minimum value constraint

        if (t_value > 0 && min_value_check >= min_value) {
            optimal_M = M;
            optimal_t = t_value;
            
            computed_sum = 0.0; // Compute actual sum for verification
            for (int i = 0; i <= M; i++) {
                computed_sum += (sum_constant - i * optimal_t);
            }
            break;  // Stop once a valid M is found
        }
    }

    // Print results
    if (optimal_M != -1) {
        Serial.print("Optimal t: ");
        Serial.print(optimal_t*1000000, 10);
        Serial.println(" micro seconds");

        Serial.print("maxDelay D: ");
        Serial.print(sum_constant*1000000, 10);
        Serial.println(" micro seconds");

        Serial.print("minDelay d: ");
        Serial.print(min_value*1000000, 10);
        Serial.println(" micro seconds");
    } else {
        Serial.println("No valid solution found.");
    }
    optimal_t = optimal_t*1000000;
    double maxDelay = sum_constant*1000000; // Start slow
    double stepDelay = maxDelay;
    int decelSteps = optimal_M;
    int accelSteps = optimal_M;
    int cruiseSteps = steps - (optimal_M + optimal_M); // Remaining steps
    double minDelay = min_value*1000000;
    Serial.printf("Motor %d | Accel: %d | Cruise: %d | Decel: %d | AccelTime: %f\n", motorIndex + 1, accelSteps, cruiseSteps, decelSteps, computed_sum);

    // **Acceleration Phase**
    for (int i = 0; i < accelSteps; i++) {
        stepDelay = maxDelay - i*optimal_t; // Decrease delay
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
    }
    
    for (int i = 0; i < cruiseSteps; i++) { // **Cruise Phase (Constant Speed)**
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
    } 
    
    for (int i = 0; i < decelSteps; i++) { // **Deceleration Phase**
        stepDelay = minDelay + i*optimal_t; // Increase delay
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
    }
    Serial.printf("Motor %d Movement Complete\n", motorIndex + 1);
}
