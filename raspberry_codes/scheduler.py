import threading
import time
from datetime import datetime

from storage import get_active_dispense_schedules, mark_schedule_status
from tray_manager import tray_manager


class Scheduler:
    def __init__(self):
        self.running = False
        self.thread = None
        self.last_processed_minute = None

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        print("Scheduler started")

    def loop(self):
        while self.running:
            try:
                self.check_due_schedules()
            except Exception as e:
                print("Scheduler error:", e)

            time.sleep(1)

    def check_due_schedules(self):
        now = datetime.now()
        today_text = now.date().isoformat()
        current_hm = (now.hour, now.minute)
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        if self.last_processed_minute == minute_key:
            return

        schedules = get_active_dispense_schedules()
        due_schedules = []

        for item in schedules:
            if item.get("status") != "loaded":
                continue

            scheduled_date = str(item.get("scheduled_date", "") or "").strip()

            if scheduled_date and scheduled_date != today_text:
                continue

            target = (int(item["hour"]), int(item["minute"]))

            if current_hm != target:
                continue

            schedule_item = dict(item)
            schedule_item["id"] = int(item["id"])
            schedule_item["slot"] = int(item["slot"])
            schedule_item["hour"] = int(item["hour"])
            schedule_item["minute"] = int(item["minute"])
            schedule_item["scheduled_date"] = scheduled_date

            due_schedules.append(schedule_item)

        if not due_schedules:
            return

        self.last_processed_minute = minute_key

        print(
            f"Scheduler: found {len(due_schedules)} due dose(s) "
            f"for {today_text} {now.hour:02d}:{now.minute:02d}"
        )

        for item in due_schedules:
            try:
                mark_schedule_status(
                    slot=int(item["slot"]),
                    hour=int(item["hour"]),
                    minute=int(item["minute"]),
                    status="pending",
                )

                print(
                    f"Scheduler: queued slot {item['slot']} "
                    f"for {item['hour']:02d}:{item['minute']:02d}"
                )

            except Exception as e:
                print("Scheduler pending mark error:", e)

        tray_manager.enqueue_due_doses(due_schedules)

    def stop(self):
        self.running = False


scheduler = Scheduler()