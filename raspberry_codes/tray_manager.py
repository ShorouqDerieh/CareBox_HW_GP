import serial
import time
import threading
import subprocess
import os

TRAY_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

AUDIO_DEVICE = "plughw:2,0"
REMINDER_AUDIO = "reminder.mp3"


class TrayManager:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.running = False
        self.last_status = "TRAY_INIT"
        self.history = []
        self.current_dispense = None

        self.reminder_active = False
        self.audio_thread = None

        # Raspberry/App will attach this callback from app.py
        self.keypad_callback = None

    def connect(self):
        self.ser = serial.Serial(TRAY_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)

        self.running = True
        threading.Thread(target=self.listen_loop, daemon=True).start()
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()

        print("Tray connected on", TRAY_PORT)

    def send(self, cmd):
        with self.lock:
            print(">>> TRAY SEND:", cmd)
            self.ser.write((cmd + "\n").encode())
            self.ser.flush()

    def listen_loop(self):
        while self.running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode(errors="ignore").strip()

                    if line:
                        print("Tray:", line)
                        self.last_status = line
                        self.history.append(line)
                        self.history = self.history[-60:]

                        self.handle_message(line)

            except Exception as e:
                print("Tray listen error:", e)

            time.sleep(0.05)

    def handle_message(self, msg):
        # ============================
        # Audio reminder messages
        # ============================
        if msg == "Please take medicine...":
            self.start_reminder()

        elif msg in ["TAKEN", "DOSE_CONFIRMED", "MISSED", "DOSE_NOT_TAKEN"]:
            self.stop_reminder()

        # ============================
        # Keypad messages from Arduino 1
        # ============================
        elif msg.startswith("KEY_"):
            print(">>> Keypad event:", msg)

            valid_keypad_commands = [
                "KEY_START_REFILL",
                "KEY_SCAN_QR",
                "KEY_CONFIRM_LOADED",
                "KEY_SKIP_SLOT",
                "KEY_FINISH_REFILL",
                "KEY_HEALTH_CHECK",
                "KEY_STATUS",
            ]

            # Ignore raw key messages like KEY_A, KEY_B, KEY_#, KEY_*
            # Use only meaningful command messages.
            if msg not in valid_keypad_commands:
                return

            if msg == "KEY_START_REFILL":
                print(">>> Keypad requested: START REFILL")

            elif msg == "KEY_SCAN_QR":
                print(">>> Keypad requested: SCAN QR")

            elif msg == "KEY_CONFIRM_LOADED":
                print(">>> Keypad requested: CONFIRM LOADED")

            elif msg == "KEY_SKIP_SLOT":
                print(">>> Keypad requested: SKIP SLOT")

            elif msg == "KEY_FINISH_REFILL":
                print(">>> Keypad requested: FINISH REFILL")

            elif msg == "KEY_HEALTH_CHECK":
                print(">>> Keypad requested: HEALTH CHECK")

            elif msg == "KEY_STATUS":
                print(">>> Keypad requested: STATUS")

            if self.keypad_callback:
                self.keypad_callback(msg)

    def heartbeat_loop(self):
        while self.running:
            try:
                self.send("PING")
            except Exception as e:
                print("Tray heartbeat error:", e)

            time.sleep(5)

    def play_reminder_loop(self):
        while self.reminder_active:
            if not os.path.exists(REMINDER_AUDIO):
                print(f"Audio file not found: {REMINDER_AUDIO}")
                self.reminder_active = False
                return

            try:
                subprocess.run(
                    ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", REMINDER_AUDIO],
                    check=False
                )
            except Exception as e:
                print("Audio error:", e)

            time.sleep(1)

    def start_reminder(self):
        if not self.reminder_active:
            print(">>> Starting reminder audio")
            self.reminder_active = True
            self.audio_thread = threading.Thread(
                target=self.play_reminder_loop,
                daemon=True
            )
            self.audio_thread.start()

    def stop_reminder(self):
        if self.reminder_active:
            print(">>> Stopping reminder audio")
        self.reminder_active = False

    def move_slot(self, display_slot):
        arduino_slot = int(display_slot) - 1
        self.send(f"MOVE_SLOT {arduino_slot}")

    def dispense_slot(self, display_slot):
        arduino_slot = int(display_slot) - 1
        self.send(f"DISPENSE_SLOT {arduino_slot}")

    def test(self):
        self.send("TEST")

    def clear(self):
        self.send("CLEAR")

    def sync_loaded_schedules(self, schedules):
        self.send("CLEAR")
        time.sleep(1)

        for item in schedules:
            if item.get("status") == "loaded":
                arduino_slot = int(item["slot"]) - 1
                self.send(f"ADD {item['hour']} {item['minute']} {arduino_slot}")
                time.sleep(1)

        self.send("SAVE")
        time.sleep(1)

        self.send("LIST")
        time.sleep(1)


tray_manager = TrayManager()