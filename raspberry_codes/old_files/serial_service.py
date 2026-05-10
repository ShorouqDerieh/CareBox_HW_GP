import serial
import time
import subprocess
import threading

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

AUDIO_FILE = "reminder.mp3"
AUDIO_DEVICE = "plughw:2,0"

REMINDER_INTERVAL = 10   # يعيد التذكير كل 10 ثواني
MAX_WAIT_TIME = 60       # أقصى مدة انتظار دقيقة

def open_serial():
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    return ser

def play_audio_once():
    try:
        subprocess.run(
            ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", AUDIO_FILE],
            check=False
        )
    except Exception as e:
        print("Audio error:", e)

def reminder_loop(stop_event):
    while not stop_event.is_set():
        play_audio_once()

        for _ in range(REMINDER_INTERVAL * 10):
            if stop_event.is_set():
                return
            time.sleep(0.1)

def send_command(cmd, read_seconds=5):
    ser = open_serial()
    ser.write((cmd + "\n").encode())
    time.sleep(0.3)

    response_lines = []
    start_time = time.time()

    while time.time() - start_time < read_seconds:
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                response_lines.append(line)
        time.sleep(0.1)

    ser.close()
    return response_lines

def clear_schedules_on_arduino():
    return send_command("CLEAR", read_seconds=3)

def add_schedule_to_arduino(hour, minute):
    return send_command(f"ADD {hour} {minute}", read_seconds=3)

def list_schedules_on_arduino():
    return send_command("LIST", read_seconds=3)

def sync_all_schedules_to_arduino(schedules):
    responses = []

    responses.extend(clear_schedules_on_arduino())
    time.sleep(0.5)

    for item in schedules:
        responses.extend(add_schedule_to_arduino(item["hour"], item["minute"]))
        time.sleep(0.3)

    return responses

def test_rotate():
    ser = open_serial()
    ser.write(b"TEST\n")
    time.sleep(0.3)

    response_lines = []
    start_time = time.time()

    stop_event = threading.Event()
    reminder_thread = None
    reminder_started = False

    while time.time() - start_time < (MAX_WAIT_TIME + 20):
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print("Arduino:", line)
                response_lines.append(line)

                if line == "DONE" and not reminder_started:
                    reminder_started = True
                    reminder_thread = threading.Thread(
                        target=reminder_loop,
                        args=(stop_event,),
                        daemon=True
                    )
                    reminder_thread.start()

                elif line == "TAKEN":
                    stop_event.set()
                    if reminder_thread is not None:
                        reminder_thread.join(timeout=1)
                    ser.close()
                    return response_lines

                elif line == "MISSED":
                    stop_event.set()
                    if reminder_thread is not None:
                        reminder_thread.join(timeout=1)
                    ser.close()
                    return response_lines

        time.sleep(0.1)

    stop_event.set()
    if reminder_thread is not None:
        reminder_thread.join(timeout=1)

    ser.close()
    response_lines.append("TIMEOUT")
    return response_lines