import os
import time
from twilio.rest import Client

from storage import load_settings

# ==========================
# Twilio configuration
# ==========================
# الأفضل لاحقًا نحطهم في environment variables بدل ما يكونوا مكتوبين بالكود.
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "AC9794e83c1cbf7f947a7f32796e095e35")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "64570b377787a754c51df37e94fdf87e")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+17015751020")

last_call_time = 0
CALL_COOLDOWN_SECONDS = 60


def get_emergency_phone():
    settings = load_settings()
    emergency_phone = str(settings.get("emergency_phone", "")).strip()

    if emergency_phone == "":
        print("SOS call failed: emergency phone is not set in settings")
        return None

    return emergency_phone


def make_sos_call():
    global last_call_time

    now = time.time()

    if now - last_call_time < CALL_COOLDOWN_SECONDS:
        print("SOS call skipped: cooldown active")
        return False

    caregiver_number = get_emergency_phone()

    if caregiver_number is None:
        return False

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)

        call = client.calls.create(
            to=caregiver_number,
            from_=TWILIO_FROM_NUMBER,
            machine_detection="Disable",
            twiml="""
<Response>
    <Say voice="alice" language="en-US">
        Emergency alert from CareBox Plus.
        The patient pressed the SOS button.
        Please check on them immediately.
    </Say>
</Response>
"""
        )

        last_call_time = now
        print("SOS call started:", call.sid)
        print("SOS call sent to:", caregiver_number)
        return True

    except Exception as e:
        print("SOS call failed:", e)
        return False
