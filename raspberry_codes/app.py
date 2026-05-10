from flask import Flask, request, jsonify, render_template, redirect, url_for

from storage import (
    load_schedules,
    add_schedule,
    clear_schedules,
    delete_schedule,
    mark_schedule_status
)
from tray_manager import tray_manager
from security_manager import security_manager
from refill_manager import refill_manager
from scheduler import scheduler

app = Flask(__name__)


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
    return redirect(url_for("home"))


@app.route("/sync", methods=["POST"])
def sync():
    schedules = load_schedules()
    tray_manager.sync_loaded_schedules(schedules)
    return redirect(url_for("home"))


@app.route("/test", methods=["POST"])
def test():
    tray_manager.test()
    return redirect(url_for("home"))


@app.route("/move_slot", methods=["POST"])
def move_slot():
    slot = int(request.form["slot"])
    tray_manager.move_slot(slot)
    return redirect(url_for("home"))


@app.route("/unlock", methods=["POST"])
def unlock():
    security_manager.unlock_lid()
    return redirect(url_for("home"))


@app.route("/lock", methods=["POST"])
def lock():
    security_manager.lock_lid()
    return redirect(url_for("home"))


# ======================
# Refill routes
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


@app.route("/api/status")
def api_status():
    return jsonify({
        "schedules": load_schedules(),
        "refill": refill_manager.status(),
        "tray_status": tray_manager.last_status,
        "security_status": security_manager.last_status,
        "tray_history": tray_manager.history[-20:],
        "security_history": security_manager.history[-20:]
    })


# ======================
# Callbacks
# ======================

def on_rfid_ok():
    print(">>> CALLBACK: RFID OK")
    refill_manager.on_rfid_ok()


def on_rfid_denied():
    print(">>> CALLBACK: RFID DENIED")
    refill_manager.on_rfid_denied()


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

    elif msg == "KEY_HEALTH_CHECK":
        print(">>> HEALTH CHECK requested")
        # لاحقًا نربط حساس الحرارة والقلب هنا

    elif msg == "KEY_STATUS":
        print(">>> STATUS requested from keypad")
        print(">>> Refill status:", refill_manager.status())


if __name__ == "__main__":
    tray_manager.connect()
    security_manager.connect()

    security_manager.rfid_ok_callback = on_rfid_ok
    security_manager.rfid_denied_callback = on_rfid_denied

    # Keypad events from Arduino 1 / tray_manager
    tray_manager.keypad_callback = on_keypad_event

    scheduler.start()

    app.run(host="0.0.0.0", port=5000, debug=False)