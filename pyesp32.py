import serial
import time

# Change to your ESP32's serial port
SERIAL_PORT = '/dev/ttyUSB0'  # Linux or Mac
# SERIAL_PORT = 'COM3'  # Windows
BAUD_RATE = 115200

def send_command(ser, command):
    ser.write((command + '\n').encode())
    response = ser.readline().decode().strip()
    return response

def move_stepper(ser, steps):
    response = send_command(ser, f"MOVE {steps}")
    return response

def set_speed(ser, speed):
    response = send_command(ser, f"SPEED {speed}")
    return response

def set_direction(ser, direction):
    response = send_command(ser, f"DIR {direction}")
    return response

def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for the connection to establish

        while True:
            command = input("Enter command (move <steps> / speed <value> / dir <0 or 1>): ").strip().lower()
            if command.startswith("move"):
                steps = int(command.split()[1])
                response = move_stepper(ser, steps)
                print(response)
            elif command.startswith("speed"):
                speed = int(command.split()[1])
                response = set_speed(ser, speed)
                print(response)
            elif command.startswith("dir"):
                direction = int(command.split()[1])
                response = set_direction(ser, direction)
                print(response)
            else:
                print("Invalid command. Use 'move <steps>', 'speed <value>', or 'dir <0 or 1>'.")

    except serial.SerialException as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("Exiting program.")
    finally:
        if ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()