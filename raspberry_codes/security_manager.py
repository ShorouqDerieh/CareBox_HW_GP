import serial
import time
import threading
from sos_manager import make_sos_call
from push_manager import send_push
SECURITY_PORT = "/dev/carebox_security"
BAUD_RATE = 9600


class SecurityManager:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.running = False
        self.last_status = "SECURITY_INIT"
        self.lid_lock_status = "locked"
        self.history = []

        self.rfid_ok_callback = None
        self.rfid_denied_callback = None
        self.sos_callback = None

    def connect(self):
        self.ser = serial.Serial(SECURITY_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)

        self.running = True
        threading.Thread(target=self.listen_loop, daemon=True).start()

        print("Security connected on", SECURITY_PORT)
        self.status()
    def send(self, cmd):
        with self.lock:
            print(">>> SECURITY SEND:", cmd)
            self.ser.write((cmd + "\n").encode())
            self.ser.flush()

    def listen_loop(self):
        while self.running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode(errors="ignore").strip()

                    if line:
                        print("Security:", line)
                        self.last_status = line
                        self.history.append(line)
                        self.history = self.history[-60:]
                        self.handle_message(line)

            except Exception as e:
                print("Security listen error:", e)

            time.sleep(0.05)

    def handle_message(self, msg):
        if msg == "RFID_OK":
            if self.rfid_ok_callback:
                self.rfid_ok_callback()

        elif msg == "RFID_DENIED":
            if self.rfid_denied_callback:
                self.rfid_denied_callback()

            self.led_error()

        elif msg == "SOS":
            print(">>> SOS received from Arduino")

            self.led_sos()

            if self.sos_callback:
                self.sos_callback()

            make_sos_call()

        elif msg == "LID_UNLOCKED":
            self.lid_lock_status = "unlocked"
            self.led_refill()

        elif msg == "LID_LOCKED":
            self.lid_lock_status = "locked"
            self.led_ready()

        elif msg == "AUTO_LOCK":
            self.lid_lock_status = "locked"

        elif msg.startswith("SECURITY_STATUS"):
            if "UNLOCKED" in msg:
                self.lid_lock_status = "unlocked"
            elif "LOCKED" in msg:
                self.lid_lock_status = "locked"

    # ============================
    # Lock commands
    # ============================

    def lock_lid(self):
        self.send("LOCK")

    def unlock_lid(self):
        self.send("UNLOCK")

    def status(self):
        self.send("STATUS")

    # ============================
    # RGB LED commands
    # ============================

    def led_ready(self):
        self.send("LED_GREEN")

    def led_refill(self):
        self.send("LED_BLUE")

    def led_error(self):
        self.send("LED_RED")

    def led_waiting(self):
        self.send("LED_YELLOW")

    def led_sos(self):
        self.send("LED_SOS")

    def led_off(self):
        self.send("LED_OFF")


security_manager = SecurityManager()
