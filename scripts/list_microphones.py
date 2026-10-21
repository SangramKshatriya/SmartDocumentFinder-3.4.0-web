"""List microphone devices visible to SpeechRecognition/PyAudio."""
from __future__ import annotations

import speech_recognition as sr

mics = sr.Microphone.list_microphone_names()
if not mics:
    print("No microphones found.")
else:
    for index, name in enumerate(mics):
        print(f"{index}: {name}")
