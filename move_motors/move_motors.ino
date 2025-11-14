#define MOTOR_COUNT 2

// Motor pin definitions
#define STEP_PIN_1 16
#define DIR_PIN_1  17
#define ENABLE_PIN_1 18

#define STEP_PIN_2 21
#define DIR_PIN_2  22
#define ENABLE_PIN_2 23

// Motor pin arrays
int stepPins[MOTOR_COUNT] = {STEP_PIN_1, STEP_PIN_2};
int dirPins[MOTOR_COUNT] = {DIR_PIN_1, DIR_PIN_2};
int enablePins[MOTOR_COUNT] = {ENABLE_PIN_1, ENABLE_PIN_2};

// Velocity in steps per second for each motor (default: ~833 steps/sec)
int motorVelocities[MOTOR_COUNT] = {833, 833};
int stepDelays[MOTOR_COUNT] = {600, 600}; // microseconds (calculated from velocity)

void setup() {
  // Setup motor pins as outputs
  for (int i = 0; i < MOTOR_COUNT; i++) {
    pinMode(stepPins[i], OUTPUT);
    pinMode(dirPins[i], OUTPUT);
    pinMode(enablePins[i], OUTPUT);
    digitalWrite(enablePins[i], LOW);  // Enable motors (active LOW)
    digitalWrite(dirPins[i], HIGH);    // Set initial direction
    updateStepDelay(i);  // Calculate initial step delay for each motor
  }

  Serial.begin(115200);
  Serial.println("Stepper test starting...");
  Serial.println("Commands: set_velocity:<motor_index>,<steps_per_second>");
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    int separatorIndex = command.indexOf(':');

    if (separatorIndex != -1) {  // Ensure ":" exists in the string
      String key = command.substring(0, separatorIndex);
      String value = command.substring(separatorIndex + 1);
      key.trim();  // Remove spaces
      value.trim();

      if (key == "set_velocity") {
        int commaIndex = value.indexOf(',');
        if (commaIndex != -1) {  // Ensure there is a comma
          String motor = value.substring(0, commaIndex);
          String velocityStr = value.substring(commaIndex + 1);
          motor.trim();
          velocityStr.trim();

          int motorIndex = motor.toInt();  // Convert to integer
          int newVelocity = velocityStr.toInt();  // Convert to integer
          
          if (motorIndex >= 0 && motorIndex < MOTOR_COUNT) {
            if (newVelocity > 0) {
              motorVelocities[motorIndex] = newVelocity;
              updateStepDelay(motorIndex);
              Serial.print("Motor ");
              Serial.print(motorIndex);
              Serial.print(" velocity set to ");
              Serial.print(motorVelocities[motorIndex]);
              Serial.print(" steps/sec (delay: ");
              Serial.print(stepDelays[motorIndex]);
              Serial.println(" us)");
            } else {
              Serial.println("Error: Velocity must be greater than 0");
            }
          } else {
            Serial.print("Error: Motor index must be between 0 and ");
            Serial.println(MOTOR_COUNT - 1);
          }
        } else {
          Serial.println("Error: Command format is set_velocity:<motor_index>,<steps_per_second>");
        }
      } else {
        Serial.println("Invalid command");
      }
    }
  }
}

// Function to step a specific motor N times
void stepMotor(int motorIndex, int steps) {
  if (motorIndex < 0 || motorIndex >= MOTOR_COUNT) {
    return;  // Invalid motor index
  }
  
  digitalWrite(enablePins[motorIndex], LOW); // Ensure motor is enabled
  
  for (int i = 0; i < steps; i++) {
    digitalWrite(stepPins[motorIndex], HIGH);
    delayMicroseconds(stepDelays[motorIndex]);
    digitalWrite(stepPins[motorIndex], LOW);
    delayMicroseconds(stepDelays[motorIndex]);
  }
}

// Update step delay based on velocity (steps per second) for a specific motor
void updateStepDelay(int motorIndex) {
  if (motorIndex < 0 || motorIndex >= MOTOR_COUNT) {
    return;  // Invalid motor index
  }
  
  // Calculate delay: 1 second = 1,000,000 microseconds
  // For each step, we have HIGH and LOW phases, so total time per step = 2 * delay
  // steps_per_second = 1,000,000 / (2 * delay)
  // delay = 1,000,000 / (2 * steps_per_second)
  stepDelays[motorIndex] = 1000000 / (2 * motorVelocities[motorIndex]);
  
  // Ensure minimum delay (safety limit)
  if (stepDelays[motorIndex] < 10) {
    stepDelays[motorIndex] = 10;
    Serial.print("Warning: Motor ");
    Serial.print(motorIndex);
    Serial.println(" velocity too high, limited to minimum delay");
  }
}

