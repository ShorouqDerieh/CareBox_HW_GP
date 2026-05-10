import serial
import time
import threading
import subprocess

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

AUDIO_FILE = "reminder.mp3"
AUDIO_DEVICE = "plughw:2,0"

# متغيرات التحكم بالصوت
reminder_active = False
audio_thread = None


def play_reminder_loop():
    global reminder_active

    while reminder_active:
        try:
            subprocess.run(
                ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", AUDIO_FILE],
                check=False
            )
        except Exception as e:
            print("Audio error:", e)

        # مهلة صغيرة بين كل مرة والثانية
        time.sleep(1)


def start_reminder():
    global reminder_active, audio_thread

    if not reminder_active:
        print(">>> Starting reminder audio loop")
        reminder_active = True
        audio_thread = threading.Thread(target=play_reminder_loop, daemon=True)
        audio_thread.start()


def stop_reminder():
    global reminder_active

    if reminder_active:
        print(">>> Stopping reminder audio loop")
        reminder_active = False


def main():
    print(f"Connecting to Arduino on {SERIAL_PORT} ...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Connected. Listening...")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode(errors="ignore").strip()

                if line:
                    print("Arduino:", line)

                    # بداية التذكير
                    if line == "DONE" or line == "Please take medicine...":
                        start_reminder()

                    # إيقاف التذكير
                    elif line == "TAKEN" or line == "MISSED":
                        stop_reminder()

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        stop_reminder()
        ser.close()
        print("Serial closed.")


if __name__ == "__main__":
    main()