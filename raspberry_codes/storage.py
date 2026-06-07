import sqlite3
from datetime import datetime, timedelta

DB_FILE = "carebox.db"
MAX_SLOTS = 20


# ==========================
# Database helpers
# ==========================

def now_text():
    return datetime.now().isoformat(timespec="seconds")


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def init_database():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot INTEGER NOT NULL UNIQUE,
            medicine TEXT NOT NULL,
            dose TEXT NOT NULL,
            type TEXT DEFAULT 'tablet',
            hour INTEGER NOT NULL,
            minute INTEGER NOT NULL,
            time TEXT NOT NULL,
            scheduled_date TEXT DEFAULT '',
            repeat TEXT DEFAULT 'daily',
            instructions TEXT DEFAULT '',
            status TEXT DEFAULT 'planned',
            verified_by_qr INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT DEFAULT '',
            loaded_at TEXT DEFAULT '',
            skipped_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            read_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            caregiver_name TEXT DEFAULT '',
            patient_name TEXT DEFAULT '',
            emergency_phone TEXT DEFAULT '',
            language TEXT DEFAULT 'ar',
            device_id TEXT DEFAULT 'CAREBOX-001'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT DEFAULT '',
            status TEXT DEFAULT 'normal',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings (
            id,
            caregiver_name,
            patient_name,
            emergency_phone,
            language,
            device_id
        )
        VALUES (
            1,
            '',
            '',
            '',
            'ar',
            'CAREBOX-001'
        )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS device_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL UNIQUE,
        platform TEXT DEFAULT 'android',
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


# ==========================
# Schedules
# ==========================

def load_schedules():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM schedules
        ORDER BY scheduled_date ASC, hour ASC, minute ASC, slot ASC
    """).fetchall()
    conn.close()

    schedules = rows_to_dicts(rows)

    for item in schedules:
        item["verified_by_qr"] = bool(item.get("verified_by_qr", 0))

    return schedules

def complete_schedule_and_free_slot(schedule_id: int, final_status: str):
    """
    Marks a dose as completed, saves the result in history,
    then deletes it from schedules so the tray slot becomes available again.

    final_status should be: 'taken' or 'missed'
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT *
        FROM schedules
        WHERE id = ?
    """, (int(schedule_id),)).fetchone()

    if not row:
        conn.close()
        return False

    item = dict(row)

    conn.execute("""
        DELETE FROM schedules
        WHERE id = ?
    """, (int(schedule_id),))

    conn.commit()
    conn.close()

    medicine = item.get("medicine", "medicine")
    slot = item.get("slot")
    time_text = item.get("time", "")
    scheduled_date = item.get("scheduled_date", "")

    if final_status == "taken":
        message = (
            f"Dose taken: {medicine}, slot {slot}, "
            f"date {scheduled_date}, time {time_text}."
        )
        severity = "info"
    else:
        message = (
            f"Dose missed: {medicine}, slot {slot}, "
            f"date {scheduled_date}, time {time_text}."
        )
        severity = "critical"

    add_history(
        event_type=f"dose_{final_status}",
        message=message,
        severity=severity
    )

    return True
def save_schedules(schedules):
    """
    Compatibility function.
    موجودة فقط حتى لو في كود قديم ناداها.
    الأفضل استخدام add/delete/mark functions بدلها.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM schedules")

    for item in schedules:
        hour = int(item.get("hour", 0))
        minute = int(item.get("minute", 0))
        time_text = item.get("time", f"{hour:02d}:{minute:02d}")

        cur.execute("""
            INSERT INTO schedules (
                slot,
                medicine,
                dose,
                type,
                hour,
                minute,
                time,
                scheduled_date,
                repeat,
                instructions,
                status,
                verified_by_qr,
                created_at,
                updated_at,
                loaded_at,
                skipped_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(item.get("slot")),
            item.get("medicine", item.get("name", "")),
            item.get("dose", ""),
            item.get("type", "tablet"),
            hour,
            minute,
            time_text,
            item.get("scheduled_date", ""),
            item.get("repeat", "daily"),
            item.get("instructions", ""),
            item.get("status", "planned"),
            1 if item.get("verified_by_qr") else 0,
            item.get("created_at", now_text()),
            item.get("updated_at", ""),
            item.get("loaded_at", ""),
            item.get("skipped_at", "")
        ))

    conn.commit()
    conn.close()


def get_used_slots():
    conn = get_connection()
    rows = conn.execute("""
        SELECT slot
        FROM schedules
    """).fetchall()
    conn.close()

    return [int(row["slot"]) for row in rows]


def get_available_slots():
    used_slots = set(get_used_slots())
    return [
        slot for slot in range(1, MAX_SLOTS + 1)
        if slot not in used_slots
    ]


def find_next_available_slot():
    available_slots = get_available_slots()

    if len(available_slots) == 0:
        return None

    return available_slots[0]


def add_schedule(slot: int, medicine: str, dose: str, hour: int, minute: int):
    """
    Old web dashboard function.
    المستخدم القديم في صفحة الويب كان يختار slot يدويًا.
    أبقيناها حتى لا نكسر /add في app.py.
    """
    time_text = f"{hour:02d}:{minute:02d}"
    created_at = now_text()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO schedules (
            slot,
            medicine,
            dose,
            type,
            hour,
            minute,
            time,
            scheduled_date,
            repeat,
            instructions,
            status,
            verified_by_qr,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        int(slot),
        medicine,
        dose,
        "tablet",
        int(hour),
        int(minute),
        time_text,
        "",
        "daily",
        "",
        "planned",
        0,
        created_at
    ))

    conn.commit()
    conn.close()

    add_history(
        event_type="schedule_added",
        message=f"Added {medicine} at {time_text} to slot {slot}.",
        severity="info"
    )

    return {
        "slot": slot,
        "medicine": medicine,
        "name": medicine,
        "dose": dose,
        "type": "tablet",
        "hour": hour,
        "minute": minute,
        "time": time_text,
        "scheduled_date": "",
        "repeat": "daily",
        "instructions": "",
        "status": "planned",
        "verified_by_qr": False,
        "created_at": created_at
    }


def add_schedule_auto_slot(
    medicine: str,
    dose: str,
    hour: int,
    minute: int,
    scheduled_date: str = "",
    repeat: str = "daily",
    medicine_type: str = "tablet",
    instructions: str = ""
):
    """
    New Flutter function.
    تطبيق Flutter لا يرسل slot.
    Raspberry Pi يختار أول slot فاضي تلقائيًا.
    """
    slot = find_next_available_slot()

    if slot is None:
        add_alert(
            alert_type="storage_full",
            title="No Available Tray Slots",
            message="CareBox tray is full. No available slot for new medicine.",
            severity="warning"
        )

        return {
            "success": False,
            "message": "No available tray slots",
            "schedule": None
        }

    time_text = f"{hour:02d}:{minute:02d}"
    created_at = now_text()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO schedules (
            slot,
            medicine,
            dose,
            type,
            hour,
            minute,
            time,
            scheduled_date,
            repeat,
            instructions,
            status,
            verified_by_qr,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        int(slot),
        medicine,
        dose,
        medicine_type,
        int(hour),
        int(minute),
        time_text,
        scheduled_date,
        repeat,
        instructions,
        "planned",
        0,
        created_at
    ))

    conn.commit()
    conn.close()

    item = {
        "slot": slot,
        "medicine": medicine,
        "name": medicine,
        "dose": dose,
        "type": medicine_type,
        "hour": hour,
        "minute": minute,
        "time": time_text,
        "scheduled_date": scheduled_date,
        "repeat": repeat,
        "instructions": instructions,
        "status": "planned",
        "verified_by_qr": False,
        "created_at": created_at
    }

    add_history(
        event_type="schedule_added",
        message=f"Added {medicine} at {time_text}. CareBox assigned slot {slot}.",
        severity="info"
    )

    return {
        "success": True,
        "message": "Schedule added successfully",
        "schedule": item
    }



def add_schedule_multiple_doses(
    medicine: str,
    dose: str,
    hour: int,
    minute: int,
    scheduled_date: str = "",
    repeat: str = "daily",
    number_of_doses: int = 1,
    medicine_type: str = "tablet",
    instructions: str = ""
):
    """
    Flutter repeating-dose function.

    Important design:
    - Each physical tray slot represents ONE dose.
    - repeat='once' always creates one dose.
    - repeat='daily' creates number_of_doses rows on consecutive dates.
    - Raspberry stores the full date-based schedule.
    - Arduino only receives today's loaded schedules for backup.
    """
    repeat = (repeat or "daily").lower().strip()

    if repeat == "once":
        number_of_doses = 1

    try:
        number_of_doses = int(number_of_doses)
    except Exception:
        number_of_doses = 1

    if number_of_doses < 1:
        number_of_doses = 1

    if number_of_doses > MAX_SLOTS:
        number_of_doses = MAX_SLOTS

    if scheduled_date:
        try:
            start_date = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
        except Exception:
            return {
                "success": False,
                "message": "Invalid scheduled_date format. Use YYYY-MM-DD",
                "schedules": []
            }
    else:
        start_date = datetime.now().date()
        scheduled_date = start_date.isoformat()

    available_slots = get_available_slots()

    if len(available_slots) < number_of_doses:
        add_alert(
            alert_type="storage_full",
            title="Not Enough Tray Slots",
            message=(
                f"CareBox needs {number_of_doses} available slot(s), "
                f"but only {len(available_slots)} slot(s) are available."
            ),
            severity="warning"
        )

        return {
            "success": False,
            "message": f"Only {len(available_slots)} slot(s) available",
            "schedules": []
        }

    created_items = []

    conn = get_connection()
    cur = conn.cursor()

    try:
        for i in range(number_of_doses):
            slot = available_slots[i]

            if repeat == "daily":
                dose_date = start_date + timedelta(days=i)
            else:
                dose_date = start_date

            dose_date_text = dose_date.isoformat()
            time_text = f"{hour:02d}:{minute:02d}"
            created_at = now_text()

            cur.execute("""
                INSERT INTO schedules (
                    slot,
                    medicine,
                    dose,
                    type,
                    hour,
                    minute,
                    time,
                    scheduled_date,
                    repeat,
                    instructions,
                    status,
                    verified_by_qr,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(slot),
                medicine,
                dose,
                medicine_type,
                int(hour),
                int(minute),
                time_text,
                dose_date_text,
                repeat,
                instructions,
                "planned",
                0,
                created_at
            ))

            created_items.append({
                "id": cur.lastrowid,
                "slot": slot,
                "medicine": medicine,
                "name": medicine,
                "dose": dose,
                "type": medicine_type,
                "hour": hour,
                "minute": minute,
                "time": time_text,
                "scheduled_date": dose_date_text,
                "repeat": repeat,
                "instructions": instructions,
                "status": "planned",
                "verified_by_qr": False,
                "created_at": created_at
            })

        conn.commit()

    except Exception as e:
        conn.rollback()
        conn.close()

        return {
            "success": False,
            "message": f"Could not create schedules: {e}",
            "schedules": []
        }

    conn.close()

    add_history(
        event_type="schedule_added",
        message=(
            f"Added {medicine}: {len(created_items)} dose(s) starting "
            f"{scheduled_date} at {hour:02d}:{minute:02d}."
        ),
        severity="info"
    )

    return {
        "success": True,
        "message": f"{len(created_items)} schedule dose(s) added successfully",
        "schedule": created_items[0] if created_items else None,
        "schedules": created_items,
        "created_count": len(created_items)
    }

def schedules_for_api():
    schedules = load_schedules()
    result = []

    for item in schedules:
        result.append({
            "id": item.get("id"),
            "slot": item.get("slot"),
            "name": item.get("medicine", "Unknown medicine"),
            "medicine": item.get("medicine", "Unknown medicine"),
            "dose": item.get("dose", ""),
            "type": item.get("type", "tablet"),
            "scheduled_date": item.get("scheduled_date", ""),
            "time": item.get("time", ""),
            "hour": item.get("hour", 0),
            "minute": item.get("minute", 0),
            "repeat": item.get("repeat", "daily"),
            "instructions": item.get("instructions", ""),
            "status": item.get("status", "planned"),
            "verified_by_qr": bool(item.get("verified_by_qr", False)),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", "")
        })

    return result


def clear_schedules():
    conn = get_connection()
    conn.execute("DELETE FROM schedules")
    conn.commit()
    conn.close()

    add_history(
        event_type="schedules_cleared",
        message="All medication schedules were cleared.",
        severity="warning"
    )


def delete_schedule(index: int):
    schedules = load_schedules()

    if 0 <= index < len(schedules):
        item = schedules[index]
        schedule_id = item["id"]

        conn = get_connection()
        conn.execute("""
            DELETE FROM schedules
            WHERE id = ?
        """, (schedule_id,))
        conn.commit()
        conn.close()

        add_history(
            event_type="schedule_deleted",
            message=f"Deleted schedule for {item.get('medicine', 'medicine')}.",
            severity="info"
        )


def mark_schedule_status(slot: int, hour: int, minute: int, status: str):
    conn = get_connection()
    conn.execute("""
        UPDATE schedules
        SET status = ?,
            updated_at = ?
        WHERE slot = ?
          AND hour = ?
          AND minute = ?
    """, (
        status,
        now_text(),
        int(slot),
        int(hour),
        int(minute)
    ))
    conn.commit()
    conn.close()

    add_history(
        event_type="schedule_status_changed",
        message=f"Slot {slot} status changed to {status}.",
        severity="info"
    )


def mark_slot_loaded(slot: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT *
        FROM schedules
        WHERE slot = ?
    """, (int(slot),)).fetchone()

    conn.execute("""
        UPDATE schedules
        SET status = 'loaded',
            verified_by_qr = 1,
            loaded_at = ?,
            updated_at = ?
        WHERE slot = ?
    """, (
        now_text(),
        now_text(),
        int(slot)
    ))

    conn.commit()
    conn.close()

    medicine = "medicine"
    if row:
        medicine = row["medicine"]

    add_history(
        event_type="slot_loaded",
        message=f"Slot {slot} loaded with {medicine}.",
        severity="info"
    )


def mark_slot_skipped(slot: int):
    conn = get_connection()
    conn.execute("""
        UPDATE schedules
        SET status = 'skipped',
            verified_by_qr = 0,
            skipped_at = ?,
            updated_at = ?
        WHERE slot = ?
    """, (
        now_text(),
        now_text(),
        int(slot)
    ))
    conn.commit()
    conn.close()

    add_alert(
        alert_type="slot_skipped",
        title="Refill Slot Skipped",
        message=f"Slot {slot} was skipped during refill.",
        severity="warning"
    )

    add_history(
        event_type="slot_skipped",
        message=f"Slot {slot} was skipped during refill.",
        severity="warning"
    )


def get_refill_queue():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE status IN ('planned', 'skipped', 'needs_refill')
        ORDER BY scheduled_date ASC, hour ASC, minute ASC, slot ASC
    """).fetchall()
    conn.close()

    queue = rows_to_dicts(rows)

    for item in queue:
        item["verified_by_qr"] = bool(item.get("verified_by_qr", 0))

    return queue


def get_loaded_schedules():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE status = 'loaded'
        ORDER BY scheduled_date ASC, hour ASC, minute ASC, slot ASC
    """).fetchall()
    conn.close()

    return rows_to_dicts(rows)


def get_active_dispense_schedules():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE status = 'loaded'
        ORDER BY scheduled_date ASC, hour ASC, minute ASC, slot ASC
    """).fetchall()
    conn.close()

    return rows_to_dicts(rows)


# ==========================
# Alerts
# ==========================

def load_alerts():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM alerts
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    alerts = rows_to_dicts(rows)

    for item in alerts:
        item["is_read"] = bool(item.get("is_read", 0))

    return alerts


def add_alert(alert_type: str, title: str, message: str, severity: str = "info"):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO alerts (
            type,
            title,
            message,
            severity,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        alert_type,
        title,
        message,
        severity,
        0,
        now_text()
    ))

    alert_id = cur.lastrowid
    conn.commit()
    conn.close()

    add_history(
        event_type=alert_type,
        message=message,
        severity=severity
    )

    return {
        "id": alert_id,
        "type": alert_type,
        "title": title,
        "message": message,
        "severity": severity,
        "is_read": False,
        "created_at": now_text()
    }


def mark_alert_read(alert_id: int):
    conn = get_connection()
    conn.execute("""
        UPDATE alerts
        SET is_read = 1,
            read_at = ?
        WHERE id = ?
    """, (
        now_text(),
        int(alert_id)
    ))
    conn.commit()
    conn.close()


def mark_all_alerts_read():
    conn = get_connection()
    conn.execute("""
        UPDATE alerts
        SET is_read = 1,
            read_at = ?
    """, (now_text(),))
    conn.commit()
    conn.close()


# ==========================
# History
# ==========================

def load_history():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM history
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()
    conn.close()

    return rows_to_dicts(rows)


def add_history(event_type: str, message: str, severity: str = "info"):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO history (
            type,
            message,
            severity,
            created_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        event_type,
        message,
        severity,
        now_text()
    ))

    event_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": event_id,
        "type": event_type,
        "message": message,
        "severity": severity,
        "created_at": now_text()
    }


# ==========================
# Settings
# ==========================

def load_settings():
    conn = get_connection()
    row = conn.execute("""
        SELECT *
        FROM settings
        WHERE id = 1
    """).fetchone()
    conn.close()

    if not row:
        return {
            "caregiver_name": "",
            "patient_name": "",
            "emergency_phone": "",
            "language": "ar",
            "device_id": "CAREBOX-001"
        }

    return dict(row)


def save_settings(settings):
    current = load_settings()

    caregiver_name = settings.get("caregiver_name", current.get("caregiver_name", ""))
    patient_name = settings.get("patient_name", current.get("patient_name", ""))
    emergency_phone = settings.get("emergency_phone", current.get("emergency_phone", ""))
    language = settings.get("language", current.get("language", "ar"))
    device_id = settings.get("device_id", current.get("device_id", "CAREBOX-001"))

    conn = get_connection()
    conn.execute("""
        INSERT INTO settings (
            id,
            caregiver_name,
            patient_name,
            emergency_phone,
            language,
            device_id
        )
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            caregiver_name = excluded.caregiver_name,
            patient_name = excluded.patient_name,
            emergency_phone = excluded.emergency_phone,
            language = excluded.language,
            device_id = excluded.device_id
    """, (
        caregiver_name,
        patient_name,
        emergency_phone,
        language,
        device_id
    ))

    conn.commit()
    conn.close()

    return load_settings()

def save_device_token(token: str, platform: str = "android"):
    token = str(token).strip()
    platform = str(platform).strip() or "android"

    if not token:
        return False

    conn = get_connection()

    conn.execute("""
        INSERT INTO device_tokens (
            token,
            platform,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(token) DO UPDATE SET
            platform = excluded.platform,
            is_active = 1,
            updated_at = excluded.updated_at
    """, (
        token,
        platform,
        now_text(),
        now_text()
    ))

    conn.commit()
    conn.close()

    return True


def load_active_device_tokens():
    conn = get_connection()
    rows = conn.execute("""
        SELECT token
        FROM device_tokens
        WHERE is_active = 1
    """).fetchall()
    conn.close()

    return [row["token"] for row in rows]
# ==========================
# Health
# ==========================

def load_health_readings():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM health_readings
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()
    conn.close()

    return rows_to_dicts(rows)


def add_health_reading(reading_type: str, value, unit: str, status: str = "normal"):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO health_readings (
            type,
            value,
            unit,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        reading_type,
        str(value),
        unit,
        status,
        now_text()
    ))

    reading_id = cur.lastrowid
    conn.commit()
    conn.close()

    reading = {
        "id": reading_id,
        "type": reading_type,
        "value": str(value),
        "unit": unit,
        "status": status,
        "created_at": now_text()
    }

    if status in ["warning", "alert", "critical"]:
        add_alert(
            alert_type="abnormal_health",
            title="Abnormal Health Reading",
            message=f"{reading_type} reading is {value} {unit}.",
            severity="critical" if status in ["alert", "critical"] else "warning"
        )

    add_history(
        event_type="health_reading",
        message=f"{reading_type}: {value} {unit} ({status})",
        severity="info" if status == "normal" else status
    )

    return reading
