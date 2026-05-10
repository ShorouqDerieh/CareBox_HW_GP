import threading
import subprocess
import time
import os

AUDIO_DEVICE = "plughw:2,0"

REMINDER_AUDIO = "reminder.mp3"
TAKEN_AUDIO = "taken.mp3"
MISSED_AUDIO = "missed.mp3"
SOS_AUDIO = "sos.mp3"


class AudioManager:
    def __init__(self):
        self.reminder_active = False
        self.audio_thread = None

    def play_once(self, audio_file):
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return

        try:
            subprocess.run(
                ["mpg123", "-a", AUDIO_DEVICE, "-f", "65536", audio_file],
                check=False
            )
        except Exception as e:
            print("Audio error:", e)

    def reminder_loop(self):
        while self.reminder_active:
            self.play_once(REMINDER_AUDIO)
            time.sleep(1)

    def start_reminder(self):
        if not self.reminder_active:
            print(">>> Starting reminder audio")
            self.reminder_active = True
            self.audio_thread = threading.Thread(
                target=self.reminder_loop,
                daemon=True
            )
            self.audio_thread.start()

    def stop_reminder(self):
        if self.reminder_active:
            print(">>> Stopping reminder audio")
        self.reminder_active = False

    def play_taken(self):
        self.stop_reminder()
        self.play_once(TAKEN_AUDIO)

    def play_missed(self):
        self.stop_reminder()
        self.play_once(MISSED_AUDIO)

    def play_sos(self):
        self.play_once(SOS_AUDIO)


audio_manager = AudioManager()