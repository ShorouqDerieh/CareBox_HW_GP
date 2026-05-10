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

        if len(self.queue) == 0:
            self.message = "No planned doses to refill"
        else:
            self.message = "Waiting for RFID"

        return self.status()

    def on_rfid_ok(self):
        if not self.active:
            self.message = "RFID OK received, but refill is not active"
            return

        self.authorized = True
        self.message = "RFID authorized"
        self.move_next()

    def on_rfid_denied(self):
        if self.active:
            self.message = "RFID denied"

    def move_next(self):
        if not self.active:
            self.message = "Refill is not active"
            return None

        if not self.authorized:
            self.message = "Waiting for RFID authorization"
            return None

        self.current_index += 1
        self.qr_verified = False
        self.last_qr = None

        if self.current_index >= len(self.queue):
            self.current_item = None
            self.message = "All refill items completed"
            return None

        self.current_item = self.queue[self.current_index]
        slot = int(self.current_item["slot"])

        self.message = f"Moving to slot {slot}"
        tray_manager.move_slot(slot)

        return self.current_item

    def scan_and_verify(self):
        if not self.current_item:
            self.message = "No current item"
            return self.status()

        result = scan_qr_once()
        self.last_qr = result

        if not result.get("success"):
            self.qr_verified = False
            self.message = result.get("error", "QR scan failed")
            return self.status()

        scanned_data = result.get("data", {})
        scanned_name = str(scanned_data.get("name", "")).strip().lower()
        expected_name = str(self.current_item.get("medicine", "")).strip().lower()

        if scanned_name == expected_name:
            self.qr_verified = True
            self.message = "QR verified"
        else:
            self.qr_verified = False
            self.message = f"Wrong medicine: expected {self.current_item.get('medicine')}, scanned {scanned_data.get('name')}"

        return self.status()

    def confirm_loaded(self):
        if not self.current_item:
            self.message = "No current item to confirm"
            return self.status()

        if not self.qr_verified:
            self.message = "Cannot confirm: QR not verified"
            return self.status()

        slot = int(self.current_item["slot"])
        mark_slot_loaded(slot)

        self.message = f"Slot {slot} loaded"
        self.move_next()

        return self.status()

    def skip_current(self):
        if not self.current_item:
            self.message = "No current item to skip"
            return self.status()

        slot = int(self.current_item["slot"])
        mark_slot_skipped(slot)

        self.message = f"Slot {slot} skipped"
        self.move_next()

        return self.status()

    def finish(self):
        loaded = get_loaded_schedules()

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

        return self.status()

    def cancel(self):
        security_manager.lock_lid()

        self.active = False
        self.authorized = False
        self.current_item = None
        self.qr_verified = False
        self.message = "Refill cancelled. Lid locked."

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


refill_manager = RefillManager()