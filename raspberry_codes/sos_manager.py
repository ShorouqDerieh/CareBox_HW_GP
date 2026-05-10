import time
from twilio.rest import Client

ACCOUNT_SID = "AC9794e83c1cbf7f947a7f32796e095e35"
AUTH_TOKEN = "64570b377787a754c51df37e94fdf87e"
TWILIO_FROM_NUMBER = "+17015751020"
CAREGIVER_NUMBER = "+970595143035"

last_call_time = 0
CALL_COOLDOWN_SECONDS = 60


def make_sos_call():
    global last_call_time

    now = time.time()

    # منع تكرار الاتصال خلال دقيقة
    if now - last_call_time < CALL_COOLDOWN_SECONDS:
        print("SOS call skipped: cooldown active")
        return False

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)

        call = client.calls.create(
            to=CAREGIVER_NUMBER,
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
        return True

    except Exception as e:
        print("SOS call failed:", e)
        return False