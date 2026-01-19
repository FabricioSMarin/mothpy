#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>  // May be needed for wifi_tx_info_t in newer cores

// Motor pin definitions (ESP32-WROOM-32)
// Motor 1: GPIO16 (step), GPIO17 (direction), GPIO18 (enable)
// Motor 2: GPIO21 (step), GPIO22 (direction), GPIO23 (enable)
// 
// Pin capabilities:
// - GPIO16, 21: Output-capable, support fast toggling for step pulses
//   Suitable for continuous step pulses up to ~50kHz (software) or higher with RMT
// - GPIO17, 22: Output-capable, direction pins (can be set once per direction change)
// - GPIO18, 23: Output-capable, enable pins (active LOW)
// 
// Note: GPIO21/22 are default I2C pins, but safe to use if I2C not needed
//       GPIO18/23 are often used for SPI, but safe if SPI not used
#define STEP_PIN_1 17
#define DIR_PIN_1  16
#define ENABLE_PIN_1 18

#define STEP_PIN_2 22
#define DIR_PIN_2  21
#define ENABLE_PIN_2 23

// Data structure to receive motor commands
typedef struct struct_motor_command {
  int motor1_velocity;  // Steps per second (0 = stop)
  int motor1_direction;  // 1 = forward, -1 = backward, 0 = stop
  int motor2_velocity;  // Steps per second (0 = stop)
  int motor2_direction;  // 1 = forward, -1 = backward, 0 = stop
} struct_motor_command;

struct_motor_command motorCommand;

// Motor state
struct MotorState {
  int current_velocity;
  int current_direction;
  int last_direction;  // Track direction to avoid unnecessary pin toggles
  unsigned long last_step_time;
  unsigned long step_delay_us;  // Calculated from velocity
};

MotorState motor1_state = {0, 0, 0, 0, 0};
MotorState motor2_state = {0, 0, 0, 0, 0};

// Timing
unsigned long last_command_time = 0;
const unsigned long command_timeout = 200;  // Stop motors if no command received for 200ms

// Callback when data is received (updated for ESP32 Arduino core v2.x+)
void OnDataRecv(const esp_now_recv_info_t *recv_info, const uint8_t *incomingData, int len) {
  if (len != sizeof(struct_motor_command)) {
    Serial.println("Received data size mismatch");
    return;
  }
  
  memcpy(&motorCommand, incomingData, sizeof(motorCommand));
  last_command_time = millis();
  
  // Update motor states
  updateMotorState(&motor1_state, motorCommand.motor1_velocity, motorCommand.motor1_direction);
  updateMotorState(&motor2_state, motorCommand.motor2_velocity, motorCommand.motor2_direction);
  
  // Optional: Print received command for debugging
  Serial.print("M1: ");
  Serial.print(motorCommand.motor1_velocity);
  Serial.print(" ");
  Serial.print(motorCommand.motor1_direction);
  Serial.print(" | M2: ");
  Serial.print(motorCommand.motor2_velocity);
  Serial.print(" ");
  Serial.println(motorCommand.motor2_direction);
}

// Callback when data is sent (ESP32 Arduino core v2.x+ with ESP-IDF 5.x)
// Note: Client doesn't send data, but callback is required for ESP-NOW registration
// ESP-IDF 5.x requires wifi_tx_info_t* instead of uint8_t* for the first parameter
void OnDataSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  // Empty - client doesn't send data
  (void)info;
  (void)status;
}

void updateMotorState(MotorState *state, int velocity, int direction) {
  state->current_velocity = velocity;
  state->current_direction = direction;
  
  // Calculate step delay from velocity
  if (velocity > 0) {
    // delay = 1,000,000 / (2 * velocity) microseconds
    // (2 because each step has HIGH and LOW phases)
    state->step_delay_us = 1000000 / (2 * velocity);
    // Minimum delay for safety (allows up to 50kHz step rate)
    if (state->step_delay_us < 10) {
      state->step_delay_us = 10;
    }
  } else {
    state->step_delay_us = 0;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("ESP-NOW Client (Stepper Motor Controller)");
  
  // Configure motor pins
  pinMode(STEP_PIN_1, OUTPUT);
  pinMode(DIR_PIN_1, OUTPUT);
  pinMode(ENABLE_PIN_1, OUTPUT);
  
  pinMode(STEP_PIN_2, OUTPUT);
  pinMode(DIR_PIN_2, OUTPUT);
  pinMode(ENABLE_PIN_2, OUTPUT);
  
  // Enable motors (active LOW)
  digitalWrite(ENABLE_PIN_1, LOW);
  digitalWrite(ENABLE_PIN_2, LOW);
  
  // Set initial direction
  digitalWrite(DIR_PIN_1, HIGH);
  digitalWrite(DIR_PIN_2, HIGH);
  motor1_state.last_direction = 1;
  motor2_state.last_direction = 1;
  
  // Set device as WiFi Station
  WiFi.mode(WIFI_STA);
  
  // Small delay to ensure WiFi is initialized
  delay(100);
  
  // Print MAC address
  Serial.print("Client MAC Address: ");
  Serial.println(WiFi.macAddress());
  Serial.println("Copy this MAC address to the master device!");
  
  // Initialize ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }
  
  // Register callbacks
  esp_now_register_recv_cb(OnDataRecv);
  esp_now_register_send_cb(OnDataSent);
  
  Serial.println("ESP-NOW initialized. Ready to receive commands.");
  
  // Initialize motor command
  motorCommand.motor1_velocity = 0;
  motorCommand.motor1_direction = 0;
  motorCommand.motor2_velocity = 0;
  motorCommand.motor2_direction = 0;
}

void loop() {
  unsigned long current_time = micros();
  
  // Check for command timeout (stop motors if no command received)
  if (millis() - last_command_time > command_timeout) {
    motor1_state.current_velocity = 0;
    motor2_state.current_velocity = 0;
  }
  
  // Motor 1 stepping
  if (motor1_state.current_velocity > 0 && motor1_state.step_delay_us > 0) {
    unsigned long time_since_last_step = current_time - motor1_state.last_step_time;
    if (time_since_last_step >= motor1_state.step_delay_us) {
      // Set direction only when it changes (more efficient)
      if (motor1_state.last_direction != motor1_state.current_direction) {
        digitalWrite(DIR_PIN_1, (motor1_state.current_direction > 0) ? HIGH : LOW);
        motor1_state.last_direction = motor1_state.current_direction;
        // Small delay after direction change (some drivers need this)
        delayMicroseconds(2);
      }
      
      // Step pulse (GPIO16 - fast toggling capable)
      digitalWrite(STEP_PIN_1, HIGH);
      delayMicroseconds(1);  // Minimum pulse width (most drivers need >0.5µs)
      digitalWrite(STEP_PIN_1, LOW);
      
      motor1_state.last_step_time = micros();  // Use micros() here to get accurate time
    }
  }
  
  // Motor 2 stepping
  if (motor2_state.current_velocity > 0 && motor2_state.step_delay_us > 0) {
    unsigned long time_since_last_step = current_time - motor2_state.last_step_time;
    if (time_since_last_step >= motor2_state.step_delay_us) {
      // Set direction only when it changes (more efficient)
      if (motor2_state.last_direction != motor2_state.current_direction) {
        digitalWrite(DIR_PIN_2, (motor2_state.current_direction > 0) ? HIGH : LOW);
        motor2_state.last_direction = motor2_state.current_direction;
        // Small delay after direction change (some drivers need this)
        delayMicroseconds(2);
      }
      
      // Step pulse (GPIO21 - fast toggling capable)
      digitalWrite(STEP_PIN_2, HIGH);
      delayMicroseconds(1);  // Minimum pulse width (most drivers need >0.5µs)
      digitalWrite(STEP_PIN_2, LOW);
      
      motor2_state.last_step_time = micros();  // Use micros() here to get accurate time
    }
  }
  
  // Small delay to prevent watchdog issues
  delayMicroseconds(10);
}

