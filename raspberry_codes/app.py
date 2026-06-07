from flask import Flask, request, jsonify, render_template, redirect, url_for

from storage import (
    init_database,

    load_schedules,
    add_schedule,
    add_schedule_auto_slot,
    add_schedule_multiple_doses,
    schedules_for_api,
    clear_schedules,
    delete_schedule,

    load_alerts,
    mark_alert_read,
    mark_all_alerts_read,
    add_alert,

    load_history,
    add_history,

    load_settings,
    save_settings,

    load_health_readings,
    add_health_reading,
    save_device_token
)

from tray_manager import tray_manager
from security_manager import security_manager
from refill_manager import refill_manager
from scheduler import scheduler
from push_manager import send_push
app = Flask(__name__)


# ======================
# Helper API responses
# ======================

def api_ok(message="OK", **extra):
    data = {
        "success": True,
        "message": message
    }
    data.update(extra)
    return jsonify(data), 200


def api_error(message="Error", status_code=400, **extra):
    data = {
        "success": False,
        "message": message
    }
    data.update(extra)
    return jsonify(data), status_code


# ======================
# Old Web Dashboard Routes
# ======================

@app.route("/")
def home():
    return render_template(
        "index.html",
        schedules=load_schedules(),
        refill=refill_manager.status(),
        tray_status=tray_manager.last_status,
        security_status=security_manager.last_status,
        tray_history=tray_manager.history[-15:],
        security_history=security_manager.history[-15:]
    )


@app.route("/add", methods=["POST"])
def add():
    slot = int(request.form["slot"])
    medicine = request.form["medicine"].strip()
    dose = request.form["dose"].strip()
    hour = int(request.form["hour"])
    minute = int(request.form["minute"])

    add_schedule(slot, medicine, dose, hour, minute)
    return redirect(url_for("home"))


@app.route("/delete/<int:index>", methods=["POST"])
def delete(index):
    delete_schedule(index)
    return redirect(url_for("home"))


@app.route("/clear", methods=["POST"])
def clear():
    clear_schedules()
    tray_manager.send("CLEAR")
    tray_manager.send("LCD_READY")
    return redirect(url_for("home"))


@app.route("/sync", methods=["POST"])
def sync():
    schedules = load_schedules()
    tray_manager.sync_loaded_schedules(schedules)
    tray_manager.send("LCD_READY")
    return redirect(url_for("home"))


@app.route("/test", methods=["POST"])
def test():
    tray_manager.test()
    return redirect(url_for("home"))


@app.route("/move_slot", methods=["POST"])
def move_slot():
    slot = int(request.form["slot"])
    tray_manager.send(f"LCD_MOVE_SLOT {slot}")
    tray_manager.move_slot(slot)
    return redirect(url_for("home"))


@app.route("/unlock", methods=["POST"])
def unlock():
    security_manager.unlock_lid()
    tray_manager.send("LCD_RFID_OK")
    return redirect(url_for("home"))


@app.route("/lock", methods=["POST"])
def lock():
    security_manager.lock_lid()
    tray_manager.send("LCD_READY")
    return redirect(url_for("home"))


# ======================
# Old Refill Web Routes
# ======================

@app.route("/refill/start", methods=["POST"])
def refill_start():
    refill_manager.start()
    return redirect(url_for("home"))


@app.route("/refill/scan", methods=["POST"])
def refill_scan():
    refill_manager.scan_and_verify()
    return redirect(url_for("home"))


@app.route("/refill/confirm", methods=["POST"])
def refill_confirm():
    refill_manager.confirm_loaded()
    return redirect(url_for("home"))


@app.route("/refill/skip", methods=["POST"])
def refill_skip():
    refill_manager.skip_current()
    return redirect(url_for("home"))


@app.route("/refill/finish", methods=["POST"])
def refill_finish():
    refill_manager.finish()
    return redirect(url_for("home"))


@app.route("/refill/cancel", methods=["POST"])
def refill_cancel():
    refill_manager.cancel()
    return redirect(url_for("home"))


# ======================
# Flutter API: Status
# ======================

@app.route("/api/status", methods=["GET"])
def api_status():
    schedules = schedules_for_api()
    refill_status = refill_manager.status()

    lid_status = getattr(security_manager, "lid_lock_status", "locked")

    next_dose = "No dose scheduled"
    if len(schedules) > 0:
        sorted_schedules = sorted(
            schedules,
            key=lambda x: (int(x.get("hour", 0)), int(x.get("minute", 0)))
        )
        first = sorted_schedules[0]
        next_dose = f"{first.get('name', 'Medicine')} at {first.get('time', '--:--')}"

    alerts = load_alerts()
    last_alert = "No alerts"
    if len(alerts) > 0:
        last_alert = alerts[0].get("title", "Alert")

    health_readings = load_health_readings()
    latest_health = "No reading yet"
    if len(health_readings) > 0:
        reading = health_readings[0]
        latest_health = (
            f"{reading.get('type', 'health')}: "
            f"{reading.get('value', '--')} "
            f"{reading.get('unit', '')}"
        )

    return jsonify({
        "online": True,
        "message": "CareBox is running",
        "carebox_status": "ready",
        "next_dose": next_dose,
        "lid_status": lid_status,
        "latest_health": latest_health,
        "last_alert": last_alert,

        "tray_arduino": "connected" if tray_manager.ser else "disconnected",
        "security_arduino": "connected" if security_manager.ser else "disconnected",

        "refill": refill_status,
        "schedules": schedules,
        "tray_status": tray_manager.last_status,
        "security_status": security_manager.last_status,
        "tray_history": tray_manager.history[-20:],
        "security_history": security_manager.history[-20:]
    })


# ======================
# Flutter API: Register / Settings
# ======================

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}

    caregiver_name = str(data.get("caregiver_name", "")).strip()
    patient_name = str(data.get("patient_name", "")).strip()
    emergency_phone = str(data.get("emergency_phone", "")).strip()
    language = str(data.get("language", "ar")).strip()
    device_id = str(data.get("device_id", "CAREBOX-001")).strip()

    if not caregiver_name or not patient_name or not emergency_phone:
        return api_error(
            "Caregiver name, patient name, and emergency phone are required",
            422
        )

    settings = save_settings({
        "caregiver_name": caregiver_name,
        "patient_name": patient_name,
        "emergency_phone": emergency_phone,
        "language": language,
        "device_id": device_id
    })

    add_history(
        event_type="registration",
        message=f"Caregiver {caregiver_name} registered patient {patient_name}.",
        severity="info"
    )

    return api_ok("Registration saved", settings=settings)


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.get_json(silent=True) or {}

    settings = save_settings({
        "caregiver_name": str(data.get("caregiver_name", "")).strip(),
        "patient_name": str(data.get("patient_name", "")).strip(),
        "emergency_phone": str(data.get("emergency_phone", "")).strip(),
        "language": str(data.get("language", "ar")).strip(),
        "device_id": str(data.get("device_id", "CAREBOX-001")).strip()
    })

    add_history(
        event_type="settings_updated",
        message="CareBox settings were updated.",
        severity="info"
    )

    return api_ok("Settings saved", settings=settings)


# ======================
# Flutter API: Schedules
# ======================

@app.route("/api/schedules", methods=["GET"])
def api_get_schedules():
    return jsonify({
        "schedules": schedules_for_api()
    })


@app.route("/api/schedules", methods=["POST"])
def api_add_schedule():
    data = request.get_json(silent=True) or {}

    medicine = str(data.get("name", data.get("medicine", ""))).strip()
    dose = str(data.get("dose", "")).strip()
    medicine_type = str(data.get("type", "tablet")).strip()
    scheduled_date = str(data.get("scheduled_date", "")).strip()
    time_text = str(data.get("time", "")).strip()
    repeat = str(data.get("repeat", "daily")).strip()
    instructions = str(data.get("instructions", "")).strip()

    if not medicine or not dose or not time_text:
        return api_error("Medicine name, amount, and time are required", 422)

    try:
        hour_text, minute_text = time_text.split(":")
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return api_error("Invalid time format. Use HH:MM", 422)

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return api_error("Invalid time value", 422)

    try:
        number_of_doses = int(data.get("number_of_doses", data.get("duration_days", 1)))
    except Exception:
        number_of_doses = 1

    if repeat == "once":
        number_of_doses = 1

    if number_of_doses < 1:
        return api_error("Number of doses must be at least 1", 422)

    if number_of_doses > 20:
        return api_error("Number of doses cannot be more than 20", 422)

    result = add_schedule_multiple_doses(
        medicine=medicine,
        dose=dose,
        hour=hour,
        minute=minute,
        scheduled_date=scheduled_date,
        repeat=repeat,
        number_of_doses=number_of_doses,
        medicine_type=medicine_type,
        instructions=instructions
    )

    if not result["success"]:
        return api_error(result["message"], 400)

    return jsonify(result), 201


@app.route("/api/sync", methods=["POST"])
def api_sync():
    schedules = load_schedules()
    tray_manager.sync_loaded_schedules(schedules)
    tray_manager.send("LCD_READY")

    add_history(
        event_type="sync",
        message="Loaded schedules were synced to CareBox tray.",
        severity="info"
    )

    return api_ok("Schedules synced to CareBox device")


# ======================
# Flutter API: Refill
# ======================

def refill_status_for_api():
    status = refill_manager.status()
    current_item = status.get("current_item") or {}

    schedules = load_schedules()
    loaded_count = len([x for x in schedules if x.get("status") == "loaded"])
    skipped_count = len([x for x in schedules if x.get("status") == "skipped"])

    step = "idle"

    if status.get("active"):
        step = "active"

    if status.get("active") and not status.get("authorized"):
        step = "waiting_rfid"

    if status.get("active") and status.get("authorized") and current_item:
        step = "waiting_qr"

    if status.get("qr_verified"):
        step = "qr_verified"

    return {
        "active": status.get("active", False),
        "authorized": status.get("authorized", False),
        "status": step,
        "rfid_authorized": "Authorized" if status.get("authorized") else "Waiting",
        "current_slot": current_item.get("slot", "--"),
        "expected_medicine": current_item.get("medicine", "No medicine selected"),
        "qr_status": "Verified" if status.get("qr_verified") else "Waiting",
        "loaded_count": loaded_count,
        "skipped_count": skipped_count,
        "total_slots": 20,
        "message": status.get("message", "Idle"),
        "raw": status
    }


@app.route("/api/refill/status", methods=["GET"])
def api_refill_status():
    return jsonify(refill_status_for_api())


@app.route("/api/refill/start", methods=["POST"])
def api_refill_start():
    refill_manager.start()

    add_history(
        event_type="refill_started",
        message="Refill process started.",
        severity="info"
    )

    return jsonify(refill_status_for_api())


@app.route("/api/refill/scan_qr", methods=["POST"])
def api_refill_scan_qr():
    refill_manager.scan_and_verify()

    status = refill_manager.status()

    if status.get("qr_verified"):
        add_history(
            event_type="qr_verified",
            message="Medicine QR was verified successfully.",
            severity="info"
        )
    else:
        add_alert(
            alert_type="wrong_qr",
            title="QR Verification Failed",
            message=status.get("message", "Wrong or unreadable QR code."),
            severity="warning"
        )

    return jsonify(refill_status_for_api())


@app.route("/api/refill/confirm", methods=["POST"])
def api_refill_confirm():
    refill_manager.confirm_loaded()
    return jsonify(refill_status_for_api())


@app.route("/api/refill/skip", methods=["POST"])
def api_refill_skip():
    refill_manager.skip_current()
    return jsonify(refill_status_for_api())


@app.route("/api/refill/finish", methods=["POST"])
def api_refill_finish():
    refill_manager.finish()

    add_history(
        event_type="refill_finished",
        message="Refill process finished.",
        severity="info"
    )

    return jsonify(refill_status_for_api())


@app.route("/api/refill/cancel", methods=["POST"])
def api_refill_cancel():
    refill_manager.cancel()

    add_history(
        event_type="refill_cancelled",
        message="Refill process cancelled.",
        severity="warning"
    )

    return jsonify(refill_status_for_api())


# ======================
# Flutter API: Alerts
# ======================

@app.route("/api/alerts", methods=["GET"])
def api_alerts():
    return jsonify({
        "alerts": load_alerts()
    })


@app.route("/api/alerts/<int:alert_id>/read", methods=["POST"])
def api_alert_read(alert_id):
    mark_alert_read(alert_id)
    return api_ok("Alert marked as read", alert_id=alert_id)


@app.route("/api/alerts/read-all", methods=["POST"])
def api_alerts_read_all():
    mark_all_alerts_read()
    return api_ok("All alerts marked as read")
@app.route("/api/device-token", methods=["POST"])
def api_device_token():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    platform = str(data.get("platform", "android")).strip()

    if not token:
        return api_error("Device token is required", 422)

    saved = save_device_token(token, platform)

    if not saved:
        return api_error("Could not save device token", 400)

    return api_ok("Device token saved")

# ======================
# Flutter API: History
# ======================

@app.route("/api/history", methods=["GET"])
def api_history():
    return jsonify({
        "history": load_history()
    })


# ======================
# Flutter API: Health
# ======================

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "message": "Health readings come from CareBox sensors.",
        "readings": load_health_readings()
    })


@app.route("/api/health/temp", methods=["POST"])
def api_health_temp():
    tray_manager.send("TEMP_CHECK")

    add_history(
        event_type="health_requested",
        message="Temperature check requested.",
        severity="info"
    )

    return api_ok("Temperature check requested")


@app.route("/api/health/heart", methods=["POST"])
def api_health_heart():
    tray_manager.send("HEART_CHECK")

    add_history(
        event_type="health_requested",
        message="Heart check requested.",
        severity="info"
    )

    return api_ok("Heart check requested")


@app.route("/api/health/mock", methods=["GET", "POST"])
def api_health_mock():
    reading_type = request.args.get("type", "temp")
    value = request.args.get("value", "37.0")
    unit = request.args.get("unit", "C")
    status = request.args.get("status", "normal")

    reading = add_health_reading(
        reading_type=reading_type,
        value=value,
        unit=unit,
        status=status
    )

    return api_ok("Mock health reading added", reading=reading)


# ======================
# Callbacks from Arduino managers
# ======================

def on_rfid_ok():
    print(">>> CALLBACK: RFID OK")

    add_history(
        event_type="rfid_ok",
        message="Caregiver RFID authorized.",
        severity="info"
    )

    refill_manager.on_rfid_ok()


def on_rfid_denied():
    print(">>> CALLBACK: RFID DENIED")

    add_alert(
        alert_type="rfid_denied",
        title="RFID Access Denied",
        message="Unauthorized RFID card tried to access CareBox.",
        severity="warning"
    )

    refill_manager.on_rfid_denied()


def on_sos():
    print(">>> CALLBACK: SOS")
    tray_manager.send("LCD_SOS")
    tray_manager.play_sos_sound()
    add_alert(
        alert_type="sos",
        title="SOS Emergency",
        message="The patient pressed the SOS button.",
        severity="critical"
    )

    add_history(
        event_type="sos",
        message="SOS button was pressed.",
        severity="critical"
    )
    send_push(
        title="SOS Emergency",
        body="The patient pressed the SOS button.",
        data={
            "type": "sos",
            "severity": "critical"
        }
    )


def on_keypad_event(msg):
    print(">>> CALLBACK: KEYPAD", msg)

    if msg == "KEY_START_REFILL":
        refill_manager.start()

    elif msg == "KEY_SCAN_QR":
        refill_manager.scan_and_verify()

    elif msg == "KEY_CONFIRM_LOADED":
        refill_manager.confirm_loaded()

    elif msg == "KEY_SKIP_SLOT":
        refill_manager.skip_current()

    elif msg == "KEY_FINISH_REFILL":
        if refill_manager.active:
            refill_manager.finish()
        else:
            print(">>> FINISH ignored: refill is not active")
            tray_manager.send("LCD_READY")

    elif msg == "KEY_HEALTH_MENU":
        print(">>> HEALTH MENU handled by Arduino")

    elif msg == "KEY_HEALTH_CHECK":
        print(">>> HEALTH CHECK requested")

        add_history(
            event_type="health_requested",
            message="Health check requested from keypad.",
            severity="info"
        )

    elif msg == "KEY_STATUS":
        print(">>> STATUS requested from keypad")
        print(">>> Refill status:", refill_manager.status())


# ======================
# App entry point
# ======================

if __name__ == "__main__":
    init_database()

    tray_manager.connect()
    security_manager.connect()

    security_manager.rfid_ok_callback = on_rfid_ok
    security_manager.rfid_denied_callback = on_rfid_denied
    security_manager.sos_callback = on_sos

    tray_manager.keypad_callback = on_keypad_event

    scheduler.start()

    tray_manager.send("LCD_READY")
    security_manager.led_ready()

    app.run(host="0.0.0.0", port=5000, debug=False)
