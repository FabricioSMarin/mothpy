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
//velocity ranges from 100-12500 steps/sec
// **Persistent Data: Backlash, Position, Resolution, Soft Limits**
int backlashSteps[MOTOR_COUNT] = {5, 3, 4}; //steps
int motorVelocities[MOTOR_COUNT] = {500, 400, 300}; //steps/sec
int motorAccelerations[MOTOR_COUNT] = {300, 200, 100}; //steps
long motorPositions[MOTOR_COUNT] = {0, 0, 0};     //steps
long softLimitPositive[MOTOR_COUNT] = {10000, 10000, 10000};  //steps
long softLimitNegative[MOTOR_COUNT] = {-10000, -10000, -10000}; //steps
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
    float accelTime;

    Serial.println("Processing command: " + command); // Debugging

    if (sscanf(command.c_str(), "%d,%c,%d,%d,%f", &motorNum, &direction, &steps, &velocity, &accelTime) == 5) {
        Serial.printf("Parsed command: Motor %d, Direction %c, Steps %d, Velocity %d, Accel %f\n",
                      motorNum, direction, steps, velocity, accelTime);

        if (motorNum >= 1 && motorNum <= MOTOR_COUNT) {
            int motorIndex = motorNum - 1;
            bool newDirection = (direction == 'F' || direction == 'f');

            digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);

            // Backlash Compensation
            // if (motors[motorIndex].lastDirection != newDirection) {
            //     Serial.printf("Applying Backlash Compensation: %d steps\n", backlashSteps[motorIndex]);
            //     moveSteps(motorIndex, backlashSteps[motorIndex], velocity);
            //     moveSteps(motorIndex, -backlashSteps[motorIndex], velocity);
            // }

            moveSteps(motorIndex, steps, velocity, accelTime);

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

void moveSteps(int motorIndex, int steps, int maxSpeed, float accelTime) {
    digitalWrite(motors[motorIndex].enablePin, LOW); // Ensure motor is enabled
    Serial.printf("Motor %d | Steps: %d | Max Speed: %d\n", motorIndex + 1, steps, maxSpeed);

    // Constants
    const int max_M = steps/2;  // Max upper limit for M
    const double sum_constant = 2000e-6;  // 2000 * 10^-6 aboslute max delay (min speed)
    const float min_value = 1.0/maxSpeed;  // 80 * 10^-6
    // const double min_value = 80e-6;  // 80 * 10^-6 absolute min delay (max speed)
    double R_target = accelTime/2;  // Desired sum target, divide by two because off by factor of 2 somehow
        Serial.print("minDelay d: ");
        Serial.print(min_value*1000000, 10);
        Serial.println(" micro seconds");
    int optimal_M = -1;
    double optimal_t = -1.0;
    double computed_sum = 0.0;

    // Iterate from max_M downwards to find the largest valid M
    for (int M = max_M; M > 0; M--) {
        // Compute sum of i from 0 to M using formula M*(M+1)/2
        double sum_i_part = (M * (M + 1)) / 2.0;
        double sum_constant_part = (M + 1) * sum_constant;

        // Solve for t
        double t_value = (sum_constant_part - R_target) / sum_i_part;

        // Check minimum value constraint
        double min_value_check = sum_constant - M * t_value;

        if (t_value > 0 && min_value_check >= min_value) {
            optimal_M = M;
            optimal_t = t_value;

            // Compute actual sum for verification
            computed_sum = 0.0;
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
        // stepDelay = maxDelay - ((maxDelay - minDelay) * i / accelSteps); // Decrease delay
        stepDelay = maxDelay - i*optimal_t; // Decrease delay
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
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
        // stepDelay = minDelay + ((maxDelay - minDelay) * i / decelSteps); // Increase delay
        stepDelay = minDelay + i*optimal_t; // Increase delay
        digitalWrite(motors[motorIndex].stepPin, HIGH);
        delayMicroseconds(stepDelay);
        digitalWrite(motors[motorIndex].stepPin, LOW);
        delayMicroseconds(stepDelay);
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

