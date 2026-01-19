#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>  // May be needed for wifi_tx_info_t in newer cores

// Joystick pin definitions (XIAO ESP32C6)
// GPIO0 (ADC1_CH0) - Button input (digital, but ADC-capable)
// GPIO1 (ADC1_CH1) - Analog Y-axis (joystick vertical)
// GPIO2 (ADC1_CH2) - Analog X-axis (joystick horizontal)
// All three pins support 12-bit ADC (0-4095 range)
#define BUTTON_PIN 0
#define ANALOG_Y_PIN 1
#define ANALOG_X_PIN 2

// ESP-NOW peer MAC address (update with your client's MAC address)
// Client MAC: CC:DB:A7:9F:63:9C
uint8_t clientMacAddress[] = {0x84, 0x1F, 0xE8, 0x2B, 0x96, 0x38};

// Data structure to send motor commands
typedef struct struct_motor_command {
  int motor1_velocity;  // Steps per second (0 = stop)
  int motor1_direction;  // 1 = forward, -1 = backward, 0 = stop
  int motor2_velocity;  // Steps per second (0 = stop)
  int motor2_direction;  // 1 = forward, -1 = backward, 0 = stop
} struct_motor_command;

struct_motor_command motorCommand;

// Joystick calibration values
int joystick_x_center = 2048;  // ADC center value (12-bit: 0-4095, center ~2048)
int joystick_y_center = 2048;
int joystick_x_max_pos = 2048;  // Maximum positive reach from center
int joystick_x_max_neg = 2048;  // Maximum negative reach from center
int joystick_y_max_pos = 2048;  // Maximum positive reach from center
int joystick_y_max_neg = 2048;  // Maximum negative reach from center
int joystick_deadzone = 50;    // Deadzone to prevent drift
int max_velocity = 50000;        // Maximum steps per second

// Timing
unsigned long lastSendTime = 0;
const unsigned long sendInterval = 50;  // Send commands every 50ms (20Hz)

// Callback when data is sent (ESP32 Arduino core v2.x+ with ESP-IDF 5.x)
// ESP-IDF 5.x requires wifi_tx_info_t* instead of uint8_t* for the first parameter
void OnDataSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  if (status != ESP_NOW_SEND_SUCCESS) {
    Serial.print("Delivery Fail");
  }
  (void)info;  // Suppress unused parameter warning
}

// Callback when data is received (for pairing/acknowledgment) - updated for ESP32 Arduino core v2.x+
void OnDataRecv(const esp_now_recv_info_t *recv_info, const uint8_t *incomingData, int len) {
  const uint8_t *mac_addr = recv_info->src_addr;
  
  Serial.print("Received from: ");
  for (int i = 0; i < 6; i++) {
    Serial.print(mac_addr[i], HEX);
    if (i < 5) Serial.print(":");
  }
  Serial.println();
  
  // If we receive data, we can use the sender's MAC as our client
  memcpy(clientMacAddress, mac_addr, 6);
  Serial.println("Client MAC address updated!");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("ESP-NOW Master (Joystick Controller)");
  
  // Configure joystick pins
  pinMode(BUTTON_PIN, INPUT_PULLUP);  // Button with pullup (GPIO0, ADC-capable)
  // Analog pins (GPIO1, GPIO2) don't need pinMode on ESP32C6 - analogRead() works directly
  // ESP32C6 ADC1 channels: GPIO0-6 are all ADC-capable (12-bit, 0-4095)
  
  // Set device as WiFi Station
  WiFi.mode(WIFI_STA);
  
  // Small delay to ensure WiFi is initialized
  delay(100);
  
  // Print MAC address
  Serial.print("Master MAC Address: ");
  Serial.println(WiFi.macAddress());
  
  // Initialize ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }
  
  // Register callbacks
  esp_now_register_send_cb(OnDataSent);
  esp_now_register_recv_cb(OnDataRecv);
  
  // Add peer (broadcast initially to find client)
  esp_now_peer_info_t peerInfo;
  memcpy(peerInfo.peer_addr, clientMacAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  
  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add peer");
    return;
  }
  
  Serial.println("ESP-NOW initialized. Waiting for client...");
  Serial.println("NOTE: Update clientMacAddress[] in code with client's MAC address");
  Serial.println("      Or use broadcast (0xFF,0xFF,0xFF,0xFF,0xFF,0xFF) if client is in pairing mode");
  
  // Calibrate joystick center (read a few samples)
  long x_sum = 0, y_sum = 0;
  for (int i = 0; i < 100; i++) {
    x_sum += analogRead(ANALOG_X_PIN);
    y_sum += analogRead(ANALOG_Y_PIN);
    delay(10);
  }
  joystick_x_center = x_sum / 100;
  joystick_y_center = y_sum / 100;
  
  // Calculate maximum reach in each direction (based on ADC range 0-4095)
  // Use the smaller of the two directions to ensure symmetric mapping
  joystick_x_max_pos = 4095 - joystick_x_center;  // Max positive reach
  joystick_x_max_neg = joystick_x_center - 0;      // Max negative reach
  joystick_y_max_pos = 4095 - joystick_y_center;  // Max positive reach
  joystick_y_max_neg = joystick_y_center - 0;      // Max negative reach
  
  // Use the smaller maximum to ensure symmetric response
  // This ensures both directions reach the same max velocity
  joystick_x_max_pos = min(joystick_x_max_pos, joystick_x_max_neg);
  joystick_x_max_neg = joystick_x_max_pos;
  joystick_y_max_pos = min(joystick_y_max_pos, joystick_y_max_neg);
  joystick_y_max_neg = joystick_y_max_pos;
  
  Serial.print("Joystick calibrated - X center: ");
  Serial.print(joystick_x_center);
  Serial.print(", Y center: ");
  Serial.println(joystick_y_center);
  Serial.print("X max reach: ±");
  Serial.print(joystick_x_max_pos);
  Serial.print(", Y max reach: ±");
  Serial.println(joystick_y_max_pos);
  
  // Initialize command structure
  motorCommand.motor1_velocity = 0;
  motorCommand.motor1_direction = 0;
  motorCommand.motor2_velocity = 0;
  motorCommand.motor2_direction = 0;
}

void loop() {
  // Read joystick values
  int x_raw = analogRead(ANALOG_X_PIN);
  int y_raw = analogRead(ANALOG_Y_PIN);
  bool button_pressed = !digitalRead(BUTTON_PIN);  // Inverted because of pullup
  
  // Calculate offsets from center
  int x_offset = x_raw - joystick_x_center;
  int y_offset = y_raw - joystick_y_center;
  
  // Apply deadzone
  if (abs(x_offset) < joystick_deadzone) {
    x_offset = 0;
  }
  if (abs(y_offset) < joystick_deadzone) {
    y_offset = 0;
  }
  
  // Map joystick to motor commands
  // Y-axis controls Motor 1 (Alt)
  // X-axis controls Motor 2 (Azi)
  
  // Motor 1 (Y-axis): Positive Y = forward, Negative Y = backward
  if (y_offset != 0) {
    // Use symmetric mapping based on actual maximum reach
    int max_reach = (y_offset > 0) ? joystick_y_max_pos : joystick_y_max_neg;
    motorCommand.motor1_velocity = map(abs(y_offset), joystick_deadzone, max_reach, 0, max_velocity);
    motorCommand.motor1_velocity = constrain(motorCommand.motor1_velocity, 0, max_velocity);
    motorCommand.motor1_direction = (y_offset > 0) ? 1 : -1;
  } else {
    motorCommand.motor1_velocity = 0;
    motorCommand.motor1_direction = 0;
  }
  
  // Motor 2 (X-axis): Positive X = forward, Negative X = backward
  if (x_offset != 0) {
    // Use symmetric mapping based on actual maximum reach
    int max_reach = (x_offset > 0) ? joystick_x_max_pos : joystick_x_max_neg;
    motorCommand.motor2_velocity = map(abs(x_offset), joystick_deadzone, max_reach, 0, max_velocity/20);
    motorCommand.motor2_velocity = constrain(motorCommand.motor2_velocity, 0, max_velocity/20);
    motorCommand.motor2_direction = (x_offset > 0) ? 1 : -1;
  } else {
    motorCommand.motor2_velocity = 0;
    motorCommand.motor2_direction = 0;
  }
  
  // Button is placeholder (does nothing for now)
  if (button_pressed) {
    // Future: Add button functionality here
  }
  
  // Send commands at regular intervals
  unsigned long currentTime = millis();
  if (currentTime - lastSendTime >= sendInterval) {
    lastSendTime = currentTime;
    
    // Send motor command
    esp_err_t result = esp_now_send(clientMacAddress, (uint8_t *)&motorCommand, sizeof(motorCommand));
    
    if (result == ESP_OK) {
      // Optional: Print status for debugging (comment out for production)
      Serial.print("M1: ");
      Serial.print(motorCommand.motor1_velocity);
      Serial.print(" ");
      Serial.print(motorCommand.motor1_direction);
      Serial.print(" | M2: ");
      Serial.print(motorCommand.motor2_velocity);
      Serial.print(" ");
      Serial.println(motorCommand.motor2_direction);
    } else {
      Serial.println("Error sending data");
    }
  }
  
  delay(10);  // Small delay to prevent watchdog issues
}

