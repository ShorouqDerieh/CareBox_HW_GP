import json
import os
from datetime import datetime

SCHEDULE_FILE = "schedule.json"


def load_schedules():
    if not os.path.exists(SCHEDULE_FILE):
        return []

    try:
        with open(SCHEDULE_FILE, "r") as f:
            data = json.load(f)
            return data.get("schedules", [])
    except Exception:
        return []


def save_schedules(schedules):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump({"schedules": schedules}, f, indent=2)


def add_schedule(slot: int, medicine: str, dose: str, hour: int, minute: int):
    schedules = load_schedules()

    schedules.append({
        "slot": slot,                 # 1..20 للمستخدم
        "medicine": medicine,
        "dose": dose,
        "hour": hour,
        "minute": minute,
        "status": "planned",          # planned يعني بدها تعبئة
        "verified_by_qr": False,
        "created_at": datetime.now().isoformat(timespec="seconds")
    })

    save_schedules(schedules)


def clear_schedules():
    save_schedules([])


def delete_schedule(index: int):
    schedules = load_schedules()
    if 0 <= index < len(schedules):
        schedules.pop(index)
        save_schedules(schedules)


def mark_schedule_status(slot: int, hour: int, minute: int, status: str):
    schedules = load_schedules()

    for item in schedules:
        if (
            int(item["slot"]) == int(slot)
            and int(item["hour"]) == int(hour)
            and int(item["minute"]) == int(minute)
        ):
            item["status"] = status
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            break

    save_schedules(schedules)


def mark_slot_loaded(slot: int):
    schedules = load_schedules()

    for item in schedules:
        if int(item["slot"]) == int(slot):
            item["status"] = "loaded"
            item["verified_by_qr"] = True
            item["loaded_at"] = datetime.now().isoformat(timespec="seconds")
            break

    save_schedules(schedules)


def mark_slot_skipped(slot: int):
    schedules = load_schedules()

    for item in schedules:
        if int(item["slot"]) == int(slot):
            item["status"] = "skipped"
            item["verified_by_qr"] = False
            item["skipped_at"] = datetime.now().isoformat(timespec="seconds")
            break

    save_schedules(schedules)


def get_refill_queue():
    schedules = load_schedules()

    queue = [
        item for item in schedules
        if item.get("status") in ["planned", "skipped", "needs_refill"]
    ]

    queue.sort(key=lambda x: (int(x["hour"]), int(x["minute"]), int(x["slot"])))
    return queue


def get_loaded_schedules():
    schedules = load_schedules()
    return [item for item in schedules if item.get("status") == "loaded"]


def get_active_dispense_schedules():
    schedules = load_schedules()

    return [
        item for item in schedules
        if item.get("status") in ["loaded", "pending"]
    ]