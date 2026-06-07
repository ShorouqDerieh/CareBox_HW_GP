import time

from storage import (
    get_refill_queue,
    mark_slot_loaded,
    mark_slot_skipped,
    get_loaded_schedules
)
from tray_manager import tray_manager
from security_manager import security_manager
from qr_scanner import scan_qr_once


class RefillManager:
    def __init__(self):
        self.active = False
        self.authorized = False
        self.queue = []
        self.current_index = -1
        self.current_item = None
        self.qr_verified = False
        self.last_qr = None
        self.message = "Idle"

    def start(self):
        self.active = True
        self.authorized = False
        self.queue = get_refill_queue()
        self.current_index = -1
        self.current_item = None
        self.qr_verified = False
        self.last_qr = None

        print(">>> REFILL START")
        tray_manager.send("LCD_REFILL_START")

        if len(self.queue) == 0:
            self.message = "No planned doses to refill"
            print(">>> No planned doses to refill")
            tray_manager.send("LCD_READY")
        else:
            self.message = "Waiting for RFID"
            print(">>> Waiting for RFID")
            time.sleep(0.5)
            tray_manager.send("LCD_WAIT_RFID")

        return self.status()

    def on_rfid_ok(self):
        if not self.active:
            self.message = "RFID OK received, but refill is not active"
            print(">>> RFID OK ignored: refill is not active")
            return self.status()

        self.authorized = True
        self.message = "RFID authorized"

        print(">>> RFID authorized")
        tray_manager.send("LCD_RFID_OK")

        time.sleep(1)
        self.move_next()

        return self.status()

    def on_rfid_denied(self):
        if self.active:
            self.message = "RFID denied"
            print(">>> RFID denied")
            tray_manager.send("LCD_RFID_DENIED")

        return self.status()

    def move_next(self):
        if not self.active:
            self.message = "Refill is not active"
            print(">>> move_next blocked: refill is not active")
            return None

        if not self.authorized:
            self.message = "Waiting for RFID authorization"
            print(">>> move_next blocked: waiting for RFID")
            tray_manager.send("LCD_WAIT_RFID")
            return None

        self.current_index += 1
        self.qr_verified = False
        self.last_qr = None

        if self.current_index >= len(self.queue):
            self.current_item = None
            self.message = "All refill items completed"
            print(">>> All refill items completed")
            tray_manager.send("LCD_REFILL_FINISH")
            return None

        self.current_item = self.queue[self.current_index]
        slot = int(self.current_item["slot"])

        self.message = f"Moving to slot {slot}"
        print(f">>> Moving to refill slot {slot}")

        tray_manager.send(f"LCD_MOVE_SLOT {slot}")
        time.sleep(0.3)

        tray_manager.move_slot(slot)

        # نعطي فرصة بسيطة للرسالة والحركة تبدأ، ثم نعرض شاشة التعبئة
        time.sleep(1)
        medicine = str(self.current_item.get("medicine", "Medicine")).strip()
        medicine = medicine[:16]
        tray_manager.send(f"LCD_FILL_SLOT {slot} {medicine}")
        return self.current_item

    def scan_and_verify(self):
        print(">>> scan_and_verify() called")

        if not self.current_item:
            self.message = "No current item"
            print(">>> QR scan blocked: no current item")
            tray_manager.send("LCD_QR_REQUIRED")
            return self.status()

        print(">>> Opening camera for QR scan...")
        tray_manager.send("LCD_QR_SCAN")

        result = scan_qr_once()
        self.last_qr = result

        if not result.get("success"):
            self.qr_verified = False
            self.message = result.get("error", "QR scan failed")
            print(">>> QR scan failed:", self.message)
            tray_manager.send("LCD_CAMERA_ERROR")
            return self.status()

        scanned_data = result.get("data", {})
        scanned_name = str(scanned_data.get("name", "")).strip().lower()
        expected_name = str(self.current_item.get("medicine", "")).strip().lower()

        print(">>> Expected medicine:", expected_name)
        print(">>> Scanned medicine:", scanned_name)

        if scanned_name == expected_name:
            self.qr_verified = True
            self.message = "QR verified"
            print(">>> QR verified")
            tray_manager.send("LCD_QR_OK")
        else:
            self.qr_verified = False
            self.message = (
                f"Wrong medicine: expected "
                f"{self.current_item.get('medicine')}, "
                f"scanned {scanned_data.get('name')}"
            )
            print(">>> Wrong medicine")
            tray_manager.send("LCD_QR_WRONG")
            tray_manager.play_qr_wrong_sound()
        return self.status()

    def confirm_loaded(self):
        if not self.current_item:
            self.message = "No current item to confirm"
            print(">>> Confirm blocked: no current item")
            tray_manager.send("LCD_QR_REQUIRED")
            return self.status()

        if not self.qr_verified:
            self.message = "Cannot confirm: QR not verified"
            print(">>> Confirm blocked: QR not verified")
            tray_manager.send("LCD_QR_REQUIRED")
            return self.status()

        slot = int(self.current_item["slot"])
        mark_slot_loaded(slot)

        self.message = f"Slot {slot} loaded"
        print(f">>> Slot {slot} loaded")

        tray_manager.send("LCD_SLOT_LOADED")
        time.sleep(1)

        self.move_next()

        return self.status()

    def skip_current(self):
        if not self.current_item:
            self.message = "No current item to skip"
            print(">>> Skip blocked: no current item")
            return self.status()

        slot = int(self.current_item["slot"])
        mark_slot_skipped(slot)

        self.message = f"Slot {slot} skipped"
        print(f">>> Slot {slot} skipped")

        tray_manager.send("LCD_SLOT_SKIPPED")
        time.sleep(1)

        self.move_next()

        return self.status()

    def finish(self):
        loaded = get_loaded_schedules()

        print(">>> Finishing refill")
        tray_manager.send("LCD_REFILL_FINISH")

        security_manager.lock_lid()
        tray_manager.sync_loaded_schedules(loaded)

        self.active = False
        self.authorized = False
        self.queue = []
        self.current_index = -1
        self.current_item = None
        self.qr_verified = False
        self.last_qr = None
        self.message = f"Refill finished. Synced {len(loaded)} loaded doses."

        print(">>> Refill finished:", self.message)
        tray_manager.send("LCD_REFILL_DONE")

        return self.status()

    def cancel(self):
        print(">>> Refill cancelled")

        security_manager.lock_lid()

        self.active = False
        self.authorized = False
        self.current_item = None
        self.qr_verified = False
        self.message = "Refill cancelled. Lid locked."

        tray_manager.send("LCD_READY")

        return self.status()

    def status(self):
        return {
            "active": self.active,
            "authorized": self.authorized,
            "queue_count": len(self.queue),
            "current_index": self.current_index,
            "current_item": self.current_item,
            "qr_verified": self.qr_verified,
            "last_qr": self.last_qr,
            "message": self.message
        }
    def play_audio_once(self, audio_file):
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return False

        try:
            subprocess.Popen(
                ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", audio_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception as e:
            print("Audio error:", e)
            return False

    def play_qr_wrong_sound(self):
        self.play_audio_once("audio/qr_wrong.mp3")


refill_manager = RefillManager()
