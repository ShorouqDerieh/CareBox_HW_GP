import os
import firebase_admin
from firebase_admin import credentials, messaging

from storage import load_active_device_tokens

FIREBASE_KEY_FILE = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT",
    "firebase-service-account.json"
)

firebase_ready = False


def init_push():
    global firebase_ready

    if firebase_ready:
        return True

    try:
        if not os.path.exists(FIREBASE_KEY_FILE):
            print("Push disabled: Firebase key file not found:", FIREBASE_KEY_FILE)
            return False

        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_KEY_FILE)
            firebase_admin.initialize_app(cred)

        firebase_ready = True
        print("Push notifications ready")
        return True

    except Exception as e:
        print("Push init error:", e)
        firebase_ready = False
        return False


def send_push(title, body, data=None):
    if data is None:
        data = {}

    if not init_push():
        return False

    tokens = load_active_device_tokens()

    if not tokens:
        print("Push skipped: no active device tokens")
        return False

    success_count = 0

    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=str(title),
                    body=str(body),
                ),
                data={str(k): str(v) for k, v in data.items()},
                token=token,
            )

            response = messaging.send(message)
            print("Push sent:", response)
            success_count += 1

        except Exception as e:
            print("Push send error:", e)

    return success_count > 0
