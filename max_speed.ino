#define STEP_PIN 15
#define DIR_PIN 14
#define ENABLE_PIN 13

#define STEPS_PER_REV 200  // Adjust according to your stepper motor specs
#define STEP_DELAY 80    // Microseconds between steps (adjust for speed)

void setup() {
    pinMode(STEP_PIN, OUTPUT);
    pinMode(DIR_PIN, OUTPUT);
    pinMode(ENABLE_PIN, OUTPUT);

    digitalWrite(ENABLE_PIN, LOW);  // Enable the driver (active LOW)
    Serial.begin(115200);
}

void loop() {
    // Move Forward
    digitalWrite(DIR_PIN, HIGH);
    Serial.println("Moving Forward");
    moveStepper(STEPS_PER_REV*100);

    delay(1000);  // Wait before changing direction

    // Move Backward
    digitalWrite(DIR_PIN, LOW);
    Serial.println("Moving Backward");
    moveStepper(STEPS_PER_REV*100);

    delay(2000);  // Pause before next cycle
}

void moveStepper(int steps) {
    for (int i = 0; i < steps; i++) {
        digitalWrite(STEP_PIN, HIGH);
        delayMicroseconds(STEP_DELAY);
        digitalWrite(STEP_PIN, LOW);
        delayMicroseconds(STEP_DELAY);
    }
}