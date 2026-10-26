#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <math.h>

// Debug output (set to 0 to save ~50KB of program space)
#define DEBUG_SERIAL 0

// WiFi Credentials
//const char* ssid = "Marinf2.4";
//const char* password = "3V@$!VE_Wifi2.4";
const char* ssid = "auranox";
const char* password = "C0ndu(tive_Wifi";
WebServer server(80); // Add this line to declare the server instance
Preferences preferences;

#define MOTOR_COUNT 3

// **Stepper Motor Pin Assignments** 30-pin board win nuk
//LR
#define STEP_PIN_2 18
#define DIR_PIN_2  19
#define ENABLE_PIN_2 17
//NF
#define STEP_PIN_3 22
#define DIR_PIN_3  23
#define ENABLE_PIN_3 21
//UD
#define STEP_PIN_1 5
#define DIR_PIN_1  16
#define ENABLE_PIN_1 4




// #define STEP_PIN_1 17
// #define DIR_PIN_1  16
// #define ENABLE_PIN_1 18

// #define STEP_PIN_2 17
// #define DIR_PIN_2  16
// #define ENABLE_PIN_2 18

// #define STEP_PIN_2 22
// #define DIR_PIN_2  21
// #define ENABLE_PIN_2 23


volatile bool emergencyStop = false;
String pendingCommand = "";
bool commandQueued = false;
bool motorBusy = false;
//NOTE: nema17 RPM range 100-500 == 600us delay (could have sworn I've gone to 200-300us..)
//Minimum delay, unloaded is 80 us; way faster than the alleged 100-500 as described online. 
//80us = 12500 steps/sec = 3.75k RPM

// **Persistent Data: Position, Resolution**
// Resolution = motor steps per 1 output-shaft revolution (informational).
// Example: 200 * 19.02 * 32 = 121728. D-pad commands are raw motor steps.
long motorPositions[MOTOR_COUNT] = {0, 0, 0}; // motor steps
float stepsPerUnit[MOTOR_COUNT] = {121728, 121728, 200}; // steps per output rev
String unitType[MOTOR_COUNT] = {"steps", "steps", "steps"}; 

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
    {STEP_PIN_1, DIR_PIN_1, ENABLE_PIN_1, 15000, 0.1, 0, -1000000, 1000000, 0, false, true},
    {STEP_PIN_2, DIR_PIN_2, ENABLE_PIN_2, 15000, 0.1, 0, -1000000, 1000000, 0, false, true},
    {STEP_PIN_3, DIR_PIN_3, ENABLE_PIN_3, 15000, 0.1, 0, -1000000, 1000000, 0, false, true},
};

// **Enhanced Web Interface with Keyboard & Gamepad Support**
const char webpage[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<title>ESP32 Motor Control</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:Arial;text-align:center;background:#2b2b2b;color:#fff;margin:20px}
.container{max-width:800px;margin:0 auto}
.pos-display{font-size:24px;margin:20px;padding:15px;background:#3b3b3b;border-radius:8px}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}
button{padding:12px 20px;font-size:16px;cursor:pointer;background:#4CAF50;color:#fff;border:none;border-radius:5px;margin:5px}
button:hover{background:#45a049}
button:active{background:#3d8b40}
input{padding:10px;font-size:16px;width:200px;background:#3b3b3b;color:#fff;border:1px solid #555;border-radius:5px}
.status{padding:10px;margin:10px;background:#3b3b3b;border-radius:5px;font-size:14px}
.gamepad-status{color:#4CAF50}
.keyboard-help{font-size:12px;color:#888;margin:10px}
</style></head>
<body>
<div class="container">
<h2>ESP32 Motor Control</h2>
<div class="status">
<span id="gamepad-status">No gamepad detected</span><br>
<span class="keyboard-help">Keyboard: Arrows + [ ] | Gamepad: D-pad + L1/R1</span>
</div>
<div class="pos-display">
Motor 1: <span id="p1">0</span> steps <button onclick="z(1)">Zero</button><br>
Motor 2: <span id="p2">0</span> steps <button onclick="z(2)">Zero</button>
</div>
<div class="controls">
<div>
<h3>Step Control</h3>
Steps: <input id="steps" type="number" value="100"><br>
<button onclick="move(1,'F')">Motor 1 Up</button>
<button onclick="move(1,'B')">Motor 1 Down</button><br>
<button onclick="move(2,'F')">Motor 2 Left</button>
<button onclick="move(2,'B')">Motor 2 Right</button>
</div>
<div>
<h3>Quick Command</h3>
<input id="c" placeholder="move:1,F,100"><br>
<button onclick="sendCmd()">Send Command</button>
</div>
</div>
</div>
<script>
let gamepadIndex=-1;
let pendingRequest=false; // Track if command is in progress
let dpadState={up:false,down:false,left:false,right:false}; // Track D-pad button states
let shoulderState={l1:false,r1:false}; // Track shoulder buttons for step adjustment

// Update positions
setInterval(()=>{
fetch('/get_positions').then(r=>r.json()).then(d=>{
d.motors.forEach(m=>{const el=document.getElementById('p'+m.id);if(el)el.textContent=m.steps})
})},500);

// Keyboard controls (up/down reversed for inverted mount)
document.addEventListener('keydown',e=>{
const s=parseInt(document.getElementById('steps').value)||100;
if(e.key==='ArrowUp'){e.preventDefault();move(1,'B',s)}
if(e.key==='ArrowDown'){e.preventDefault();move(1,'F',s)}
if(e.key==='ArrowLeft'){e.preventDefault();move(2,'F',s)}
if(e.key==='ArrowRight'){e.preventDefault();move(2,'B',s)}
if(e.key===']'){e.preventDefault();adjustSteps(100)}
if(e.key==='['){e.preventDefault();adjustSteps(-100)}
});

// Gamepad detection
window.addEventListener('gamepadconnected',e=>{
gamepadIndex=e.gamepad.index;
document.getElementById('gamepad-status').innerHTML='Gamepad connected: '+e.gamepad.id;
console.log('Gamepad connected:',e.gamepad);
});

window.addEventListener('gamepaddisconnected',e=>{
gamepadIndex=-1;
document.getElementById('gamepad-status').innerHTML='No gamepad detected';
});

// Gamepad polling - D-pad and shoulder buttons
function pollGamepad(){
if(gamepadIndex>=0){
const gp=navigator.getGamepads()[gamepadIndex];
if(gp){
// Shoulder buttons - adjust step size
if(gp.buttons[4].pressed&&!shoulderState.l1){
shoulderState.l1=true;
adjustSteps(-100);
}else if(!gp.buttons[4].pressed)shoulderState.l1=false;
if(gp.buttons[5].pressed&&!shoulderState.r1){
shoulderState.r1=true;
adjustSteps(100);
}else if(!gp.buttons[5].pressed)shoulderState.r1=false;
// D-pad buttons - single press only (up/down reversed for inverted mount)
const dpadSteps=parseInt(document.getElementById('steps').value)||100;
if(gp.buttons[12].pressed&&!dpadState.up){dpadState.up=true;move(1,'B',dpadSteps);}
else if(!gp.buttons[12].pressed)dpadState.up=false;
if(gp.buttons[13].pressed&&!dpadState.down){dpadState.down=true;move(1,'F',dpadSteps);}
else if(!gp.buttons[13].pressed)dpadState.down=false;
if(gp.buttons[14].pressed&&!dpadState.left){dpadState.left=true;move(2,'F',dpadSteps);}
else if(!gp.buttons[14].pressed)dpadState.left=false;
if(gp.buttons[15].pressed&&!dpadState.right){dpadState.right=true;move(2,'B',dpadSteps);}
else if(!gp.buttons[15].pressed)dpadState.right=false;
}
}
requestAnimationFrame(pollGamepad);
}
pollGamepad();

function adjustSteps(delta){
const input=document.getElementById('steps');
let current=parseInt(input.value)||100;
current=Math.max(1,current+delta); // Minimum 1 step
input.value=current;
console.log('Steps adjusted to:',current);
}

function move(m,d,s){
s=s||parseInt(document.getElementById('steps').value)||100;
pendingRequest=true;
fetch('/command?cmd=move:'+m+','+d+','+s)
.then(()=>pendingRequest=false)
.catch(e=>{console.error(e);pendingRequest=false;});
}

function z(m){fetch('/set_position?motor='+m+'&pos=0')}
function sendCmd(){fetch('/command?cmd='+document.getElementById('c').value)}
</script>
</body></html>
)rawliteral";


void setup() {
    Serial.begin(115200);
    Serial.setTimeout(50);  // keep readStringUntil from blocking too long
    delay(1000);
    Serial.println("\nESP32 Motor Controller");
    
    preferences.begin("backlash", false);
    for (int i = 0; i < MOTOR_COUNT; i++) {
        motors[i].backlash = preferences.getInt(("motor" + String(i+1)).c_str(), motors[i].backlash);
        motors[i].velocity = preferences.getInt(("motor" + String(i+1) + "_velo").c_str(), motors[i].velocity);
        motors[i].accelTime = preferences.getFloat(("motor" + String(i+1) + "_accel").c_str(), motors[i].accelTime);
        motorPositions[i] = preferences.getLong(("motor" + String(i+1) + "_position").c_str(), motorPositions[i]);
        stepsPerUnit[i] = preferences.getFloat(("motor" + String(i+1) + "_res").c_str(), stepsPerUnit[i]);
        unitType[i] = preferences.getString(("motor" + String(i+1) + "_unit").c_str(), unitType[i]);
        Serial.printf("Motor %d: vel=%d steps/s accel=%.3fs res=%.2f backlash=%d\n",
                      i + 1, motors[i].velocity, motors[i].accelTime, stepsPerUnit[i], motors[i].backlash);
    }
    
    // Configure motor pins; leave drivers disabled (no holding current) until a move
    for (int i = 0; i < MOTOR_COUNT; i++) {
        pinMode(motors[i].stepPin, OUTPUT);
        pinMode(motors[i].dirPin, OUTPUT);
        pinMode(motors[i].enablePin, OUTPUT);
        digitalWrite(motors[i].enablePin, HIGH);  // HIGH = disabled on A4988/DRV8825
    }

    // WiFi is optional — never block forever (USB serial is primary control path)
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    unsigned long wifiStart = millis();
    const unsigned long WIFI_TIMEOUT_MS = 8000;
    while (WiFi.status() != WL_CONNECTED && (millis() - wifiStart) < WIFI_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
        Serial.println("Web interface ready (USB serial also active)");

        server.on("/", []() {
            Serial.println("Serving webpage");
            server.send(200, "text/html", webpage);
        });
        server.on("/command", []() {
            String cmd = server.arg("cmd");
            Serial.println("Received command: " + cmd);
            pendingCommand = cmd;
            commandQueued = true;
            server.send(200, "text/plain", "OK: " + cmd);
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
    } else {
        Serial.println("WiFi unavailable — continuing with USB serial only");
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
    }

    Serial.println("READY");  // handshake token for host apps
    Serial.println("Ready for USB serial motor commands.");
}


void handleSerialLine(String command) {
    command.trim();
    if (command.length() == 0) return;

    if (command.equalsIgnoreCase("Hello") || command.equalsIgnoreCase("hello")) {
        Serial.println("Hi");
        return;
    }

    int separatorIndex = command.indexOf(':');
    if (separatorIndex < 0) {
        Serial.println("Invalid command (expected key:value)");
        return;
    }

    String key = command.substring(0, separatorIndex);
    String value = command.substring(separatorIndex + 1);
    key.trim();
    value.trim();

    if (key == "set_resolution") {
        int commaIndex = value.indexOf(',');
        if (commaIndex != -1) {
            int motorIndex = value.substring(0, commaIndex).toInt() - 1;  // 1-based from host
            float res = value.substring(commaIndex + 1).toFloat();
            if (motorIndex >= 0 && motorIndex < MOTOR_COUNT && res > 0) {
                stepsPerUnit[motorIndex] = res;
                preferences.putFloat(("motor" + String(motorIndex + 1) + "_res").c_str(), res);
                Serial.printf("Motor %d resolution set to %.2f\n", motorIndex + 1, res);
            }
        }
    } else if (key == "set_velocity") {
        int commaIndex = value.indexOf(',');
        if (commaIndex != -1) {
            int motorIndex = value.substring(0, commaIndex).toInt() - 1;
            int velo = value.substring(commaIndex + 1).toInt();
            if (motorIndex >= 0 && motorIndex < MOTOR_COUNT && velo > 0) {
                motors[motorIndex].velocity = velo;
                preferences.putInt(("motor" + String(motorIndex + 1) + "_velo").c_str(), velo);
                Serial.printf("Motor %d velocity set to %d steps/sec\n", motorIndex + 1, velo);
            }
        }
    } else if (key == "set_acceleration") {
        int commaIndex = value.indexOf(',');
        if (commaIndex != -1) {
            int motorIndex = value.substring(0, commaIndex).toInt() - 1;
            float acc = value.substring(commaIndex + 1).toFloat();
            if (motorIndex >= 0 && motorIndex < MOTOR_COUNT && acc >= 0) {
                motors[motorIndex].accelTime = acc;
                preferences.putFloat(("motor" + String(motorIndex + 1) + "_accel").c_str(), acc);
                Serial.printf("Motor %d acceleration set to %.3f s\n", motorIndex + 1, acc);
            }
        }
    } else if (key == "set_backlash") {
        int commaIndex = value.indexOf(',');
        if (commaIndex != -1) {
            int motorIndex = value.substring(0, commaIndex).toInt() - 1;
            int bac = value.substring(commaIndex + 1).toInt();
            if (motorIndex >= 0 && motorIndex < MOTOR_COUNT && bac >= 0) {
                motors[motorIndex].backlash = bac;
                preferences.putInt(("motor" + String(motorIndex + 1)).c_str(), bac);
                Serial.printf("Motor %d backlash set to %d steps\n", motorIndex + 1, bac);
            }
        }
    } else if (key == "move") {
        // Queue move so loop() can keep reading serial
        pendingCommand = value;
        commandQueued = true;
        Serial.println("Queued move: " + value);
    } else {
        Serial.println("Invalid command: " + key);
    }
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        server.handleClient();
    }

    // Prefer serial handling before moves so buttons stay responsive
    while (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        handleSerialLine(command);
    }

    if (commandQueued && !motorBusy) {
        commandQueued = false;
        motorBusy = true;
        processCommand(pendingCommand);
        motorBusy = false;
    }
}

void setMotorEnabled(int motorIndex, bool enabled) {
    // A4988 / DRV8825: ENABLE is active-LOW
    digitalWrite(motors[motorIndex].enablePin, enabled ? LOW : HIGH);
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

            if (steps < 1) steps = 1;
            float res = stepsPerUnit[motorIndex];
            if (res > 0.0f) {
                Serial.printf("%d steps = %.6f output rev (res=%.2f steps/rev)\n",
                              steps, (double)steps / res, res);
            }

            Serial.printf("Using vel=%d steps/s accel=%.3fs backlash=%d\n", velo, acc, bac);

            // Power coils only for this move, then release holding current
            setMotorEnabled(motorIndex, true);
            delayMicroseconds(100);  // brief driver settle

            // Backlash Compensation - apply when direction changes
            if (motors[motorIndex].lastDirection != newDirection && motors[motorIndex].backlash > 0) {
                Serial.printf("Direction changed - Applying Backlash Compensation: %d steps\n", motors[motorIndex].backlash);
                digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);
                int backlashSpeed = velo > 2000 ? velo : 2000;
                moveSteps(motorIndex, motors[motorIndex].backlash, backlashSpeed, 0.0);
                motorPositions[motorIndex] += newDirection ? motors[motorIndex].backlash : -motors[motorIndex].backlash;
                preferences.putLong(("motor" + String(motorIndex+1) + "_position").c_str(), motorPositions[motorIndex]);
            }

            digitalWrite(motors[motorIndex].dirPin, newDirection ? HIGH : LOW);
            moveSteps(motorIndex, steps, velo, acc);
            motorPositions[motorIndex] += newDirection ? steps : -steps;
            preferences.putLong(("motor" + String(motorIndex+1) + "_position").c_str(), motorPositions[motorIndex]);

            setMotorEnabled(motorIndex, false);
            motors[motorIndex].active = false;
            motors[motorIndex].lastDirection = newDirection;
            Serial.printf("Motor %d disabled (no holding current)\n", motorIndex + 1);
        } else {
            Serial.printf("Invalid motor number: %d (must be 1-%d)\n", motorNum, MOTOR_COUNT);
        }
    } else {
        Serial.printf("Invalid Command Format! Expected format: 'motor,direction,steps' or 'move:motor,direction,steps'\n");
        Serial.printf("Received: '%s'\n", command.c_str());
        Serial.printf("Example: '1,B,2000' or 'move:1,B,2000'\n");
    }
}

void pulseStep(int motorIndex, unsigned long halfDelayUs) {
    if (halfDelayUs < 2) halfDelayUs = 2;
    digitalWrite(motors[motorIndex].stepPin, HIGH);
    delayMicroseconds(halfDelayUs);
    digitalWrite(motors[motorIndex].stepPin, LOW);
    delayMicroseconds(halfDelayUs);
}

void serviceHttp() {
    if (WiFi.status() == WL_CONNECTED) {
        server.handleClient();
    }
    // Drain serial while stepping so settings/commands stay responsive
    while (Serial.available()) {
        handleSerialLine(Serial.readStringUntil('\n'));
    }
}

void moveConstantSpeed(int motorIndex, int steps, int maxSpeed) {
    if (maxSpeed < 1) maxSpeed = 1;
    // Two delays per step, so half-period = 1e6 / (2 * steps/sec)
    unsigned long halfDelay = 1000000UL / (2UL * (unsigned long)maxSpeed);
    if (halfDelay < 2) halfDelay = 2;
    Serial.printf("Constant speed: %d steps/s (half-delay %lu us)\n", maxSpeed, halfDelay);
    for (int i = 0; i < steps; i++) {
        if (emergencyStop) break;
        pulseStep(motorIndex, halfDelay);
        if ((i & 15) == 0) serviceHttp();
    }
}

void moveSteps(int motorIndex, int steps, int maxSpeed, float accelTime) {
    // Caller is responsible for enable/disable around the full move sequence
    Serial.printf("Motor %d | Steps: %d | Max Speed: %d | Accel Time %f\n", motorIndex + 1, steps, maxSpeed, accelTime);

    if (steps <= 0) return;
    if (maxSpeed < 1) maxSpeed = 1;

    // If acceleration time is zero, skip acceleration/deceleration and run at max speed
    if (accelTime == 0.0 || accelTime < 0.001) {
        moveConstantSpeed(motorIndex, steps, maxSpeed);
        return;
    }

    // Constants
    const int max_M = steps/2;  // Max upper limit for M
    const double sum_constant = 2000e-6;  // 2000 * 10^-6 aboslute max delay (min speed)
    const float min_value = 1.0 / (2.0 * maxSpeed);  // half-period so full step = 1/maxSpeed
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

    if (optimal_M < 1) {
        Serial.println("Accel profile invalid for this step count/speed; using constant velocity");
        moveConstantSpeed(motorIndex, steps, maxSpeed);
        return;
    }

    optimal_t = optimal_t*1000000;
    double maxDelay = sum_constant*1000000; // Start slow
    double stepDelay = maxDelay;
    int decelSteps = optimal_M;
    int accelSteps = optimal_M;
    int cruiseSteps = steps - (optimal_M + optimal_M); // Remaining steps
    double minDelay = min_value*1000000;
    if (minDelay < 2) minDelay = 2;

    // **Acceleration Phase**
    for (int i = 0; i < accelSteps; i++) {
        if (emergencyStop) return;
        stepDelay = maxDelay - i*optimal_t; // Decrease delay
        if (stepDelay < minDelay) stepDelay = minDelay;
        pulseStep(motorIndex, (unsigned long)stepDelay);
        if ((i & 15) == 0) serviceHttp();
    }
    
    for (int i = 0; i < cruiseSteps; i++) { // **Cruise Phase (Constant Speed)**
        if (emergencyStop) return;
        pulseStep(motorIndex, (unsigned long)minDelay);
        if ((i & 15) == 0) serviceHttp();
    } 
    
    for (int i = 0; i < decelSteps; i++) { // **Deceleration Phase**
        if (emergencyStop) return;
        stepDelay = minDelay + i*optimal_t; // Increase delay
        pulseStep(motorIndex, (unsigned long)stepDelay);
        if ((i & 15) == 0) serviceHttp();
    }
}

