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
int motorVelocities[MOTOR_COUNT] = {500,400,300};
int motorAccelerations[MOTOR_COUNT] = {300,200,100};
long motorPositions[MOTOR_COUNT] = {0, 0, 0};
long softLimitPositive[MOTOR_COUNT] = {10000, 10000, 10000};
long softLimitNegative[MOTOR_COUNT] = {-10000, -10000, -10000};
float stepsPerUnit[MOTOR_COUNT] = {200.0, 200.0, 200.0}; // Steps per degree/mm
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


//TODO: change MOVE MOTOR function to sendCommand example below
//   <button onclick="sendCommand('1,B,2000,500,300')">Move Motor 1 Backward</button><br>
//    <button onclick="sendCommand('2,F,1500,700,400')">Move Motor 2 Forward</button>

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
        <button onclick="setMotorState(1, 1)">Enable Motor 1</button>
        <button onclick="setMotorState(1, 0)">Disable Motor 1</button><br>
        <label> resolution <input type="number" id="res1"> <select id="unit1">
            <option value="degrees">Degrees</option>
            <option value="mm">Millimeters</option>
        </select></label>
        <button onclick="setResolution(1)">Set</button><br>
        <label> Pos Limit <input type="number" id="posLimit1"></label>
        <label> Neg Limit <input type="number" id="negLimit1"></label>
        <button onclick="setSoftLimits(1)">Set</button><br>
        <label> velocity (steps/sec) <input type="number" id="velo1"></label>
        <button onclick="setVelocity(1)">Set</button><br>
        <label> acceleration (ms) <input type="number" id="accel1"></label>
        <button onclick="setAcceleration(1)">Set</button><br>
        <label> backlash (steps) <input type="number" id="backlsh1"></label>
        <button onclick="setBacklash(1)">Set</button><br>
    </div>


    <h3>Motor 2 settings</h3>
        <button onclick="setMotorState(2, 1)">Enable Motor 2</button>
        <button onclick="setMotorState(2, 0)">Disable Motor 2</button><br>
        <label> resolution <input type="number" id="res2"> <select id="unit2">
            <option value="degrees">Degrees</option>
            <option value="mm">Millimeters</option>
        </select></label>
        <button onclick="setResolution(2)">Set</button><br>
        <label> Pos Limit <input type="number" id="posLimit2"></label>
        <label> Neg Limit <input type="number" id="negLimit2"></label>
        <button onclick="setSoftLimits(2)">Set</button><br>
        <label> velocity (steps/sec) <input type="number" id="velo2"></label>
        <button onclick="setVelocity(2)">Set</button><br>
        <label> acceleration (ms) <input type="number" id="accel2"></label>
        <button onclick="setAcceleration(2)">Set</button><br>
        <label> backlash (steps) <input type="number" id="backlsh2"></label>
        <button onclick="setBacklash(2)">Set</button><br>
    </div>


    <h3>Motor 3 settings</h3>
        <button onclick="setMotorState(3, 1)">Enable Motor 3</button>
        <button onclick="setMotorState(3, 0)">Disable Motor 3</button><br>
        <label> resolution <input type="number" id="res3"> <select id="unit3">
            <option value="degrees">Degrees</option>
            <option value="mm">Millimeters</option>
        </select></label>
        <button onclick="setResolution(3)">Set</button><br>
        <label> Pos Limit <input type="number" id="posLimit3"></label>
        <label> Neg Limit <input type="number" id="negLimit3"></label>
        <button onclick="setSoftLimits(3)">Set</button><br>
        <label> velocity (steps/sec) <input type="number" id="velo3"></label>
        <button onclick="setVelocity(3)">Set</button><br>
        <label> acceleration (ms) <input type="number" id="accel3"></label>
        <button onclick="setAcceleration(3)">Set</button><br>
        <label> backlash (steps) <input type="number" id="backlsh3"></label>
        <button onclick="setBacklash(3)">Set</button><br>
    </div>


    <h3>Move Motors</h3>
    <div>
        <label> <select id="dir1">
            <option value="F">Forward</option>
            <option value="B">Backward</option>
        </select> Steps: <input type="number" id="steps1">
        <button onclick="moveMotor(1)">Move</button><br>

        <label> <select id="dir2">
            <option value="F">Forward</option>
            <option value="B">Backward</option>
        </select> Steps: <input type="number" id="steps2">
        <button onclick="moveMotor(2)">Move</button><br>

        <label> <select id="dir3">
            <option value="F">Forward</option>
            <option value="B">Backward</option>
        </select> Steps: <input type="number" id="steps3">
        <button onclick="moveMotor(3)">Move</button><br>
    </div>

    <h3>Manual Command</h3>
    <div>
        <input type="text" id="cmd" placeholder="1,B,2000,500,300">
        <button onclick="sendCommand()">Move Motor</button><br>
    </div>

    <h3>Controls</h3>
    <button onclick="emergencyStop()">Emergency Stop</button>
    <button onclick="togglePause()">Pause/Resume</button>

    <h3>Real-Time Positions</h3>
    <div id="positions"></div>

    <script>
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

        function togglePause() {
            fetch("/pause")
                .then(response => response.text())
                .then(data => alert(data));
        }

        function moveMotor(motor) {
            let dir = document.getElementById("dir" + motor).value;
            let steps = document.getElementById("steps" + motor).value;
            let velo = document.getElementById("velo" + motor).value;
            let accel = document.getElementById("accel" + motor).value;
            let command = "${motor},${dir},${steps},${velo},${accel}";
            fetch("/command?cmd=" + command);
        }

        function sendCommand() {
            let command = document.getElementById("cmd").value;
            fetch("/command?cmd=" + command) 
                .then(response => response.text()) 
                .then(data => alert(data)) // Show confirmation message
                .catch(error => console.error('Error:', error));
        }

        // Update motor positions every second
        setInterval(() => {
            fetch("/get_positions")
                .then(res => res.text())
                .then(data => document.getElementById("positions").innerHTML = data);
        }, 1000);
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

    server.on("/emergency_stop", []() {
        emergencyStop = true;
        server.send(200, "text/plain", "Emergency stop activated!");
    });

    server.on("/pause", []() {
        paused = !paused;
        server.send(200, "text/plain", paused ? "Motors paused!" : "Motors resumed!");
    });

    server.on("/set_motor_state", []() {
        int motor = server.arg("motor").toInt() - 1;
        bool enableState = server.arg("state").toInt();
        if (motor >= 0 && motor < MOTOR_COUNT) {
            digitalWrite(motors[motor].enablePin, enableState ? LOW : HIGH);
            server.send(200, "text/plain", enableState ? "Motor enabled" : "Motor disabled");
        }
    });

    server.on("/set_resolution", []() {
        int motor = server.arg("motor").toInt() - 1;
        float res = server.arg("res").toFloat();
        String unit = server.arg("unit");

        if (motor >= 0 && motor < MOTOR_COUNT) {
            stepsPerUnit[motor] = res;
            unitType[motor] = unit;
            preferences.putFloat(("motor" + String(motor+1) + "_res").c_str(), res);
            preferences.putString(("motor" + String(motor+1) + "_unit").c_str(), unit);
            server.send(200, "text/plain", "Resolution updated.");
        }
    });

    server.on("/set_soft_limits", []() {
        int motor = server.arg("motor").toInt() - 1;
        long posLimit = server.arg("posLimit").toInt();
        long negLimit = server.arg("negLimit").toInt();

        if (motor >= 0 && motor < MOTOR_COUNT) {
            softLimitPositive[motor] = posLimit;
            softLimitNegative[motor] = negLimit;
            preferences.putLong(("motor" + String(motor+1) + "_soft_pos").c_str(), posLimit);
            preferences.putLong(("motor" + String(motor+1) + "_soft_neg").c_str(), negLimit);
            server.send(200, "text/plain", "Soft limits updated.");
        }
    });

    server.on("/set_backlash", []() {
        int motor = server.arg("motor").toInt() - 1;
        int backlsh = server.arg("backlsh").toInt();
        if (motor >= 0 && motor < MOTOR_COUNT) {
            backlashSteps[motor] = backlsh;
            preferences.putInt(("motor" + String(motor+1)).c_str(), backlsh);
            server.send(200, "text/plain", "Backlash updated.");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_velocity", []() {
        int motor = server.arg("motor").toInt() - 1;
        int velo = server.arg("velo").toInt();
        if (motor >= 0 && motor < MOTOR_COUNT) {
            motorVelocities[motor] = velo;
            preferences.putInt(("motor" + String(motor+1)).c_str(), velo);
            server.send(200, "text/plain", "velocity updated.");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_acceleration", []() {
        int motor = server.arg("motor").toInt() - 1;
        int accel = server.arg("accel").toInt();
        if (motor >= 0 && motor < MOTOR_COUNT) {
            motorAccelerations[motor] = accel;
            preferences.putInt(("motor" + String(motor+1)).c_str(), accel);
            server.send(200, "text/plain", "acceleration updated.");
        } else {
            server.send(400, "text/plain", "Invalid motor number.");
        }
    });

    server.on("/set_position", []() {
        int motor = server.arg("motor").toInt() - 1;
        long pos = server.arg("pos").toInt();
        if (motor >= 0 && motor < MOTOR_COUNT) {
            motorPositions[motor] = pos;
            preferences.putLong(("motor" + String(motor+1) + "_position").c_str(), pos);
            server.send(200, "text/plain", "Position updated.");
        }
    });

    server.on("/get_positions", []() {
        String positions = "";
        for (int i = 0; i < MOTOR_COUNT; i++) {
            positions += "Motor " + String(i+1) + ": " + String(motorPositions[i]) + " steps<br>";
        }
        server.send(200, "text/html", positions);
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
        stepOnce(motorIndex, minDelay);
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
