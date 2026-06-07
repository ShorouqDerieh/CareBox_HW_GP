import serial
import time
import threading
import subprocess
import os
from datetime import datetime

from push_manager import send_push
from storage import (
    add_health_reading,
    add_alert,
    add_history,
    mark_schedule_status,
    complete_schedule_and_free_slot,
    load_settings,
)

TRAY_PORT = "/dev/carebox_tray"
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

        # Current dose + queue support for multiple doses at the same time
        self.current_dispense = None
        self.dispense_queue = []
        self.dispensing_active = False

        # Avoid mixing PING with CLEAR/ADD/SAVE during Arduino backup sync
        self.syncing = False

        self.reminder_active = False
        self.audio_thread = None

        self.keypad_callback = None

        self.last_time_sync = 0

    def connect(self):
        self.ser = serial.Serial(TRAY_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)

        self.running = True
        threading.Thread(target=self.listen_loop, daemon=True).start()
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        threading.Thread(target=self.sync_time_periodically, daemon=True).start()

        print("Tray connected on", TRAY_PORT)

        # Send Raspberry Pi time to Arduino/RTC on startup
        time.sleep(1)
        self.sync_time_to_arduino()

    def send(self, cmd):
        with self.lock:
            print(">>> TRAY SEND:", cmd)
            if not self.ser:
                print("Tray serial not connected")
                return False
            self.ser.write((cmd + "\n").encode())
            self.ser.flush()
            return True

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

    # ============================
    # RTC sync from Raspberry Pi to Arduino
    # ============================
    def sync_time_to_arduino(self):
        now = datetime.now()
        cmd = f"SET_TIME {now.year} {now.month} {now.day} {now.hour} {now.minute} {now.second}"

        print(">>> Syncing Arduino RTC:", cmd)

        try:
            self.syncing = True
            ok = self.send(cmd)
            if ok:
                self.last_time_sync = time.time()
            time.sleep(0.3)
        except Exception as e:
            print("RTC sync error:", e)
        finally:
            self.syncing = False

    def sync_time_periodically(self):
        # Re-sync every 6 hours while the backend is running.
        while self.running:
            try:
                if time.time() - self.last_time_sync >= 6 * 60 * 60:
                    self.sync_time_to_arduino()
            except Exception as e:
                print("Periodic RTC sync error:", e)

            time.sleep(60)

    # ============================
    # Dose completion + queue
    # ============================
    def _complete_current_dispense(self, final_status):
        if not self.current_dispense:
            print(f">>> Ignoring {final_status}: no active dispense")
            self.dispensing_active = False
            self.stop_reminder()
            return False
        completed = False

        if self.current_dispense:
            schedule_id = self.current_dispense.get("id")

            try:
                if schedule_id:
                    complete_schedule_and_free_slot(
                        schedule_id=int(schedule_id),
                        final_status=final_status,
                    )
                    completed = True
                else:
                    mark_schedule_status(
                        slot=int(self.current_dispense["slot"]),
                        hour=int(self.current_dispense["hour"]),
                        minute=int(self.current_dispense["minute"]),
                        status=final_status,
                    )
                    completed = True
            except TypeError:
                # Compatibility with older storage.py versions that accepted
                # complete_schedule_and_free_slot(slot, hour, minute, final_status)
                complete_schedule_and_free_slot(
                    int(self.current_dispense["slot"]),
                    int(self.current_dispense["hour"]),
                    int(self.current_dispense["minute"]),
                    final_status,
                )
                completed = True
            except Exception as e:
                print("Complete current dispense error:", e)

        self.current_dispense = None
        self.dispensing_active = False

        # Refresh Arduino backup schedules after taken/missed so completed doses
        # are not kept in Arduino EEPROM backup.
        self.refresh_arduino_schedules()

        # Continue with the next due dose, if multiple doses had same time.
        self.start_next_queued_dose()

        return completed

    def enqueue_due_doses(self, due_schedules):
        if not due_schedules:
            return

        existing_ids = set()

        for item in self.dispense_queue:
            if isinstance(item, dict):
                existing_ids.add(item.get("id"))

        if self.current_dispense:
            existing_ids.add(self.current_dispense.get("id"))

        added_count = 0

        for item in due_schedules:
            if not item:
                continue

            schedule_id = item.get("id")

            if schedule_id in existing_ids:
                continue

            self.dispense_queue.append(item)
            existing_ids.add(schedule_id)
            added_count += 1

        print(f">>> Added {added_count} due dose(s) to queue")
        self.start_next_queued_dose()

    def start_next_queued_dose(self):
        if self.dispensing_active or self.current_dispense:
            return

        if not self.dispense_queue:
            return

        item = self.dispense_queue.pop(0)
        self.current_dispense = item
        self.dispensing_active = True

        try:
            display_slot = int(item["slot"])
            medicine_name = (
                item.get("medicine_name")
                or item.get("name")
                or item.get("medicine")
                or "Medicine"
            )
            hour = int(item.get("hour", 0))
            minute = int(item.get("minute", 0))

            print(
                f">>> Starting queued dose: {medicine_name} "
                f"slot {display_slot} at {hour:02d}:{minute:02d}"
            )

            self.dispense_slot(display_slot)

        except Exception as e:
            print("Queued dose start error:", e)
            self.current_dispense = None
            self.dispensing_active = False
            self.start_next_queued_dose()

    def handle_message(self, msg):
        # ============================
        # Health readings from Arduino
        # Expected examples:
        # HEALTH_TEMP 37.2
        # HEALTH_HEART 82
        # HEALTH_SPO2 97
        # ============================
        if msg.startswith("HEALTH_TEMP"):
            self.handle_temperature_message(msg)
            return

        elif msg.startswith("HEALTH_HEART"):
            self.handle_heart_message(msg)
            return

        elif msg.startswith("HEALTH_SPO2"):
            self.handle_spo2_message(msg)
            return

        # ============================
        # RTC/backup status messages
        # ============================
        if msg in ["RTC_TIME_SET", "BACKUP_MODE_ON", "PRIMARY_MODE_ON", "MODE BACKUP", "MODE PRIMARY"]:
            print(">>> Arduino status:", msg)
            return

        # ============================
        # Audio reminder messages
        # ============================
        if msg == "Please take medicine...":
            self.start_reminder()

        elif msg == "DOSE_CONFIRMED":
            self.stop_reminder()
            self._complete_current_dispense("taken")

        elif msg == "DOSE_NOT_TAKEN":
            self.stop_reminder()

            self._send_push_safe(
                title="Missed Dose",
                body="The patient did not take the medicine on time.",
                data={"type": "missed_dose", "severity": "critical"},
            )

            self._complete_current_dispense("missed")

            add_alert(
                alert_type="missed_dose",
                title="Missed Dose",
                message="The patient did not take the medicine on time.",
                severity="critical",
            )

        # Ignore legacy result words so one physical dose cannot be completed twice.
        elif msg in ["TAKEN", "MISSED"]:
            print(">>> Ignoring legacy dose result:", msg)
            return

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
                "KEY_HEALTH_MENU",
                "KEY_HEALTH_CHECK",
                "KEY_STATUS",
            ]

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
            elif msg == "KEY_HEALTH_MENU":
                print(">>> Keypad requested: HEALTH MENU")
            elif msg == "KEY_HEALTH_CHECK":
                print(">>> Keypad requested: HEALTH CHECK")
            elif msg == "KEY_STATUS":
                print(">>> Keypad requested: STATUS")

            if self.keypad_callback:
                self.keypad_callback(msg)

    # ============================
    # Health parsing functions
    # ============================
    def handle_temperature_message(self, msg):
        try:
            parts = msg.split()
            value = float(parts[1])

            status = "normal"
            if value >= 38.0:
                status = "warning"
            if value >= 39.0:
                status = "critical"

            add_health_reading(
                reading_type="temp",
                value=value,
                unit="C",
                status=status,
            )

            print(f">>> Temperature saved: {value} C ({status})")

        except Exception as e:
            print("Temperature parse error:", e)

    def handle_heart_message(self, msg):
        try:
            parts = msg.split()
            value = int(float(parts[1]))

            status = "normal"
            if value < 50 or value > 120:
                status = "warning"
            if value < 40 or value > 140:
                status = "critical"

            add_health_reading(
                reading_type="heart",
                value=value,
                unit="bpm",
                status=status,
            )

            print(f">>> Heart reading saved: {value} bpm ({status})")

        except Exception as e:
            print("Heart parse error:", e)

    def handle_spo2_message(self, msg):
        try:
            parts = msg.split()
            value = int(float(parts[1]))

            status = "normal"
            if value < 94:
                status = "warning"
            if value < 90:
                status = "critical"

            add_health_reading(
                reading_type="spo2",
                value=value,
                unit="%",
                status=status,
            )

            print(f">>> SpO2 reading saved: {value}% ({status})")

        except Exception as e:
            print("SpO2 parse error:", e)

    def heartbeat_loop(self):
        while self.running:
            try:
                # Do not send PING while a dose is being dispensed.
                # Some Arduino versions may misread serial commands during dispensing.
                if self.current_dispense or self.dispensing_active or self.reminder_active:
                    time.sleep(1)
                    continue

                self.send("PING")

            except Exception as e:
                print("Tray heartbeat error:", e)

            time.sleep(5)

    def get_language(self):
        try:
            settings = load_settings()
            language = str(settings.get("language", "ar")).strip().lower()

            if language not in ["ar", "en"]:
                language = "ar"

            return language
        except Exception as e:
            print("Language load error:", e)
            return "ar"

    def get_audio_file(self, event_name):
        language = self.get_language()

        audio_files = {
            "reminder": {
                "ar": "audio/reminder_ar.mp3",
                "en": "audio/reminder_en.mp3",
            },
            "missed": {
                "ar": "audio/missed_ar.mp3",
                "en": "audio/missed_en.mp3",
            },
            "sos": {
                "ar": "sos_ar.mp3",
                "en": "sos_en.mp3",
            },
            "refill": {
                "ar": "audio/refill_ar.mp3",
                "en": "audio/refill_en.mp3",
            },
        }

        return audio_files.get(event_name, audio_files["reminder"]).get(language)

    def play_audio_once(self, audio_file):
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return False

        try:
            subprocess.Popen(
                ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", audio_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print("Audio error:", e)
            return False

    def play_qr_wrong_sound(self):
        self.play_audio_once("wrong.mp3")

    def play_sos_sound(self):
        audio_file = self.get_audio_file("sos")
        self.play_audio_once(audio_file)

    def play_reminder_loop(self):
        while self.reminder_active:
            audio_file = self.get_audio_file("reminder")

            if not os.path.exists(audio_file):
                print(f"Audio file not found: {audio_file}")
                self.reminder_active = False
                return

            try:
                subprocess.run(
                    ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", audio_file],
                    check=False,
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
                daemon=True,
            )
            self.audio_thread.start()

    def stop_reminder(self):
        if self.reminder_active:
            print(">>> Stopping reminder audio")

        self.reminder_active = False

        try:
            subprocess.run(
                ["pkill", "-f", "mpg123"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print("Stop audio error:", e)

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

    def _send_push_safe(self, title, body, data=None):
        try:
            send_push(title=title, body=body, data=data or {})
        except Exception as e:
            print("Push send error:", e)

    def refresh_arduino_schedules(self):
        """
        Re-send the remaining loaded schedules to Arduino backup after a dose
        is completed. This keeps backup EEPROM aligned with Raspberry state.
        """
        try:
            from storage import load_schedules

            schedules = load_schedules()
            self.sync_loaded_schedules(schedules)
        except Exception as e:
            print("Auto sync after dose error:", e)
            try:
                self.send("LCD_READY")
            except Exception:
                pass

    def sync_loaded_schedules(self, schedules):
        """
        Demo-safe mode:
        Raspberry Pi is the only scheduler.
        Clear Arduino RAM + EEPROM backup schedules.
        """
        try:
            print(">>> DEMO SAFE: clearing Arduino RAM and EEPROM backup schedules")
            self.send("CLEAR")
            time.sleep(0.5)

            # Important: persist empty schedule list to EEPROM
            self.send("SAVE")
            time.sleep(0.5)

            self.send("LIST")
            time.sleep(0.5)

            self.send("LCD_READY")
            time.sleep(0.3)

        except Exception as e:
            print("Arduino schedule clear error:", e)
tray_manager = TrayManager()
