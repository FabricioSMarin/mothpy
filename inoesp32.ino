#include <AccelStepper.h>

// Define stepper motor connections and interface type
#define dirPin  12
#define stepPin 13

AccelStepper stepper(AccelStepper::DRIVER, stepPin, dirPin);

void setup() {
  Serial.begin(115200);
  stepper.setMaxSpeed(1000); // Set maximum speed value for the stepper
  stepper.setAcceleration(100); // Set acceleration value for the stepper
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    if (command.startsWith("MOVE")) {
      int steps = command.substring(5).toInt();
      stepper.moveTo(steps);
      while (stepper.distanceToGo() != 0) {
        stepper.run();
      }
      Serial.println("DONE");
    } else if (command.startsWith("SPEED")) {
      int speed = command.substring(6).toInt();
      stepper.setMaxSpeed(speed);
      Serial.println("SPEED SET");
    } else if (command.startsWith("DIR")) {
      int dir = command.substring(4).toInt();
      if (dir == 0) {
        stepper.setPinsInverted(true, false, false); // Invert direction pin
      } else {
        stepper.setPinsInverted(false, false, false); // Normal direction
      }
      Serial.println("DIRECTION SET");
    }
  }
}