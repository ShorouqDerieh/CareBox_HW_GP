import serial
import time
import threading
import subprocess
from storage import mark_schedule_status

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

AUDIO_FILE = "reminder.mp3"
AUDIO_DEVICE = "plughw:2,0"


class SerialManager:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.running = False
        self.listener_thread = None
        self.heartbeat_thread = None
        self.reminder_active = False
        self.audio_thread = None
        self.last_status = "INIT"
        self.history = []

        # ✅ جديد: تتبع الجرعة الحالية
        self.current_dispense = None

    def connect(self):
        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)

        self.running = True

        self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listener_thread.start()

        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def send(self, cmd):
        with self.lock:
            self.ser.write((cmd + "\n").encode())

    def listen_loop(self):
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if line:
                        print("Arduino:", line)
                        self.last_status = line
                        self.history.append(line)
                        self.history = self.history[-50:]
                        self.handle_message(line)
            except Exception as e:
                print("Listen error:", e)

            time.sleep(0.05)

    def heartbeat_loop(self):
        while self.running:
            try:
                self.send("PING")
            except Exception as e:
                print("Heartbeat error:", e)

            time.sleep(5)

    def handle_message(self, msg):
        # تشغيل الصوت
        if msg in ["DONE", "Please take medicine..."]:
            self.start_reminder()

        # تم أخذ الجرعة
        elif msg in ["TAKEN", "DOSE_CONFIRMED"]:
            self.stop_reminder()

            if self.current_dispense:
                mark_schedule_status(
                    self.current_dispense["slot"],
                    self.current_dispense["hour"],
                    self.current_dispense["minute"],
                    "taken"
                )
                self.current_dispense = None

        # لم يتم أخذ الجرعة
        elif msg in ["MISSED", "DOSE_NOT_TAKEN"]:
            self.stop_reminder()

            if self.current_dispense:
                mark_schedule_status(
                    self.current_dispense["slot"],
                    self.current_dispense["hour"],
                    self.current_dispense["minute"],
                    "missed"
                )
                self.current_dispense = None

    def play_reminder_loop(self):
        while self.reminder_active:
            try:
                subprocess.run(
                    ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", AUDIO_FILE],
                    check=False
                )
            except Exception as e:
                print("Audio error:", e)

            time.sleep(1)

    def start_reminder(self):
        if not self.reminder_active:
            print(">>> Starting reminder audio")
            self.reminder_active = True
            self.audio_thread = threading.Thread(target=self.play_reminder_loop, daemon=True)
            self.audio_thread.start()

    def stop_reminder(self):
        if self.reminder_active:
            print(">>> Stopping reminder audio")
        self.reminder_active = False
    def sync_schedules(self, schedules):
        self.send("CLEAR")
        time.sleep(0.3)

        for item in schedules:
            self.send(f"ADD {item['hour']} {item['minute']} {item['slot']}")
            time.sleep(0.2)

        self.send("SAVE")
        time.sleep(0.2)

        self.send("LIST")
        time.sleep(0.2)

    def close(self):
        self.running = False
        self.stop_reminder()

        if self.ser:
            self.ser.close()



serial_manager = SerialManager()