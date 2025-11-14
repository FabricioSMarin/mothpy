import serial
import time

# Serial connection settings
SERIAL_PORT = "COM3"  # Change to your port (e.g., "/dev/ttyUSB0" for Linux/Mac)
BAUD_RATE = 115200

def move_motors():
    """Connect to ESP32 and move motors 1 and 2 by 1000 steps"""
    try:
        # Connect to ESP32
        print(f"Connecting to ESP32 on {SERIAL_PORT}...")
        esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for connection to stabilize
        
        # Verify connection
        esp32.write(b'Hello\n')
        time.sleep(0.5)
        response = esp32.readline().decode().strip()
        if response == "Hi":
            print("Connected to ESP32!")
        else:
            print(f"Warning: Unexpected response: {response}")
        
        # Move motor 1 by 1000 steps (forward)
        print("Moving motor 1 by 1000 steps...")
        command1 = "move:1,F,1000\n"
        esp32.write(command1.encode())
        time.sleep(0.1)
        
        # Move motor 2 by 1000 steps (forward)
        print("Moving motor 2 by 1000 steps...")
        command2 = "move:2,F,1000\n"
        esp32.write(command2.encode())
        time.sleep(0.1)
        
        print("Commands sent successfully!")
        
        # Wait a bit to see any responses
        time.sleep(1)
        while esp32.in_waiting > 0:
            response = esp32.readline().decode().strip()
            if response:
                print(f"ESP32: {response}")
        
        esp32.close()
        print("Connection closed.")
        
    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        print("Make sure the ESP32 is connected and the port is correct.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    move_motors()

