#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

#define MOTOR_COUNT 3

// **Stepper Motor Pin Assignments**
#define STEP_PIN_1 26
#define DIR_PIN_1  32
#define ENABLE_PIN_1 14

#define STEP_PIN_2 25
#define DIR_PIN_2  33
#define ENABLE_PIN_2 21

#define STEP_PIN_3 27
#define DIR_PIN_3  22
#define ENABLE_PIN_3 19

volatile bool emergencyStop = false;
volatile bool paused = false;

// **Persistent Data: Backlash, Position, Resolution, Soft Limits**
int backlashSteps[MOTOR_COUNT] = {5, 3, 4};
long motorPositions[MOTOR_COUNT] = {0, 0, 0};
long softLimitPositive[MOTOR_COUNT] = {10000, 10000, 10000};
long softLimitNegative[MOTOR_COUNT] = {-10000, -10000, -10000};
float stepsPerUnit[MOTOR_COUNT] = {200.0, 200.0, 200.0}; // Steps per degree/mm
String unitType[MOTOR_COUNT] = {"degrees", "degrees", "degrees"};

Preferences preferences;

// **Stepper Motor Struct**
struct StepperMotor {
    int stepPin;
    int dirPin;
    int enablePin;
    bool lastDirection;
};

// **Motor Definitions**
StepperMotor motors[MOTOR_COUNT] = {
    {STEP_PIN_1, DIR_PIN_1, ENABLE_PIN_1, true},
    {STEP_PIN_2, DIR_PIN_2, ENABLE_PIN_2, true},
    {STEP_PIN_3, DIR_PIN_3, ENABLE_PIN_3, true}
};

void setup() {
    Serial.begin(115200);
    preferences.begin("motor_settings", false);

    for (int i = 0; i < MOTOR_COUNT; i++) {
        pinMode(motors[i].stepPin, OUTPUT);
        pinMode(motors[i].dirPin, OUTPUT);
        pinMode(motors[i].enablePin, OUTPUT);
        digitalWrite(motors[i].enablePin, LOW);

        stepsPerUnit[i] = preferences.getFloat(("motor" + String(i+1) + "_res").c_str(), stepsPerUnit[i]);
        unitType[i] = preferences.getString(("motor" + String(i+1) + "_unit").c_str(), unitType[i]);
        backlashSteps[i] = preferences.getInt(("motor" + String(i+1) + "_backlash").c_str(), backlashSteps[i]);
        motorPositions[i] = preferences.getLong(("motor" + String(i+1) + "_position").c_str(), motorPositions[i]);
        softLimitPositive[i] = preferences.getLong(("motor" + String(i+1) + "_soft_pos").c_str(), softLimitPositive[i]);
        softLimitNegative[i] = preferences.getLong(("motor" + String(i+1) + "_soft_neg").c_str(), softLimitNegative[i]);
    }

    WiFi.begin("Your_SSID", "Your_PASSWORD");
    while (WiFi.status() != WL_CONNECTED) { delay(500); }

    serverSetup();
}

void loop() {
    server.handleClient();
}

// **Server Setup**
void serverSetup() {
    server.on("/", []() { server.send(200, "text/html", webpage); });

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

    server.on("/move_motor", []() {
        int motor = server.arg("motor").toInt() - 1;
        char direction = server.arg("dir").charAt(0);
        int steps = server.arg("steps").toInt();

        if (motor >= 0 && motor < MOTOR_COUNT) {
            long newPosition = motorPositions[motor] + (direction == 'F' ? steps : -steps);

            if (newPosition > softLimitPositive[motor] || newPosition < softLimitNegative[motor]) {
                server.send(400, "text/plain", "Move blocked: Out of limits.");
                return;
            }

            if ((direction == 'F' && motors[motor].lastDirection == false) ||
                (direction == 'B' && motors[motor].lastDirection == true)) {
                newPosition += (direction == 'F' ? backlashSteps[motor] : -backlashSteps[motor]);
            }

            motorPositions[motor] = newPosition;
            preferences.putLong(("motor" + String(motor+1) + "_position").c_str(), motorPositions[motor]);

            motors[motor].lastDirection = (direction == 'F');
            executeMove(motor, direction, steps);
            server.send(200, "text/plain", "Move executed.");
        }
    });

    server.begin();
}

// **Execute Motor Movement**
void executeMove(int motor, char direction, int steps) {
    digitalWrite(motors[motor].dirPin, direction == 'F' ? HIGH : LOW);
    for (int i = 0; i < steps; i++) {
        digitalWrite(motors[motor].stepPin, HIGH);
        delayMicroseconds(500);
        digitalWrite(motors[motor].stepPin, LOW);
        delayMicroseconds(500);
    }
}

// **HTML Web Interface**
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

    <h3>Set Motor Resolution & Units</h3>
    <label>Motor 1: <input type="number" id="res1"> Steps per <select id="unit1">
        <option value="degrees">Degrees</option>
        <option value="mm">Millimeters</option>
        <option value="revolutions">Revolutions</option>
    </select></label>
    <button onclick="setResolution(1)">Set</button><br>

    <h3>Move Motor</h3>
    <label>Motor 1: Direction <select id="dir1"><option value="F">Forward</option><option value="B">Backward</option></select></label>
    <input type="number" id="steps1" placeholder="Steps">
    <button onclick="moveMotor(1)">Move</button><br>

    <h3>Real-Time Positions</h3>
    <div id="positions"></div>

    <script>
        function setResolution(motor) {
            let res = document.getElementById("res" + motor).value;
            let unit = document.getElementById("unit" + motor).value;
            fetch(`/set_resolution?motor=${motor}&res=${res}&unit=${unit}`);
        }

        function moveMotor(motor) {
            let dir = document.getElementById("dir" + motor).value;
            let steps = document.getElementById("steps" + motor).value;
            fetch(`/move_motor?motor=${motor}&dir=${dir}&steps=${steps}`);
        }

        setInterval(() => fetch("/get_positions").then(res => res.text()).then(data => document.getElementById("positions").innerHTML = data), 1000);
    </script>
</body>
</html>
)rawliteral";