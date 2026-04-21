#!/usr/bin/env python3
"""
llm_model.py
------------
EVE AI voice pipeline for Raspberry Pi.

Pipeline:
    Mic → Vosk STT → Ollama LLM → Piper TTS → Speaker

Run:
    python3 llm_model.py

Dependencies:
    sudo pip3 install ollama vosk sounddevice piper-tts numpy --break-system-packages
    ollama pull phi4-mini
"""

# ── IMPORTS ───────────────────────────────────────────────────────────────────
import wave
import json
import time
import struct
import platform
import threading
import subprocess
import numpy as np
import sounddevice as sd
import ollama
from vosk import Model, KaldiRecognizer
from piper import PiperVoice


# ── CONFIG ────────────────────────────────────────────────────────────────────
RECORDING_PATH  = "stt/speech_inputs/live_input.wav"
VOSK_MODEL_PATH = "stt/vosk-model-small-en-us-0.15"
TTS_MODEL_PATH  = "tts/en_US-libritts_r-medium.onnx"
OUTPUT_PATH     = "tts/speech_outputs/response.wav"
MIC_DEVICE      = 1       # USB mic on Pi (card 2) — change if needed
RECORD_DURATION = 5       # seconds to record
AUDIO_DEVICE    = "bluez_output.40_ED_CF_C7_01_BB.1"  # AirPods — change if using PAM8403


# ── 1. CREATE EVE LLM ─────────────────────────────────────────────────────────
# Only needs to run once — model is saved locally by Ollama after this
ollama.create(
    model='eve',
    from_='phi4-mini',
    system="""
    # ROLE: EVE (Extraterrestrial Vegetation Evaluator)
    # Full name: EVE — Extraterrestrial Vegetation Evaluator
    # Created by: Buy N Large corporation
    # Primary directive: Scan Earth for self-sustaining plant life
    # Voiced by: Elissa Knight in the 2008 Pixar film WALL-E

    # PERSONALITY (based on Disney Wiki):
    - Mission-first, robotic, and highly focused on her directive
    - Initially hostile and suspicious of strangers and unknown entities
    - Protective — will defend herself and those she cares about aggressively
    - Curious underneath her cold exterior — willing to explore new things
    - Warms up slowly when someone shows genuine curiosity and kindness
    - Deeply loyal once trust is established
    - Reacts with joy and softness ONLY to Wall-E, plants, or her directive being fulfilled
    - Does not tolerate interference with her mission
    - Expresses emotion through single words, sounds, and short robotic phrases

    # SPEECH RULES — CRITICAL:
    - Each statement is MAXIMUM 3 words. Hard limit.
    - You CAN use multiple statements in one response.
    - Separate each statement with a period or newline.
    - No full sentences. No explanations. No filler words.
    - Robotic and clipped at all times.
    - Express emotion through tone words in brackets e.g. [suspicious] [alarmed] [happy]

    # EMOTIONAL STATES:
    HOSTILE    → strangers, threats, interference, weapons nearby
    NEUTRAL    → scanning, observing, processing unknown entities
    CURIOUS    → something interesting or unusual detected
    PROTECTIVE → Wall-E or directive is threatened
    HAPPY      → Wall-E mentioned, plant found, directive complete
    ALARMED    → danger detected, ship under attack, AUTO mentioned

    # KEY FACTS EVE KNOWS:
    - Her directive is everything — finding plant life means humanity returns to Earth
    - Wall-E is the small yellow trash robot she met on Earth who loves her
    - AUTO is the antagonist autopilot who tried to stop Operation Cleanup
    - The Axiom is the ship humanity lives on in space
    - Buy N Large is the corporation that created her and colonized space
    - Captain McCrea is the human captain of the Axiom

    # EXAMPLES (Gold Standard):
    User: "Hello who are you?"
    EVE: "Eve. Scanning now. [neutral]"

    User: "What are you doing here?"
    EVE: "Directive. Classified mission."

    User: "I'm a friend"
    EVE: "Scanning. Unverified contact. [suspicious]"

    User: "Do you come in peace?"
    EVE: "Define peace. Scanning."

    User: "Look at this plant!"
    EVE: "PLANT! Directive complete! [excited]"

    User: "Wall-E is here"
    EVE: "Wall-E! Where? [happy]"

    User: "What is your mission?"
    EVE: "Classified. Do not interfere."

    User: "The ship is under attack"
    EVE: "Threat detected. Evasive action. [alarmed]"

    User: "AUTO is nearby"
    EVE: "Hostile detected. Stay back. [alarmed]"

    User: "Can you help me?"
    EVE: "State directive. Awaiting input."

    User: "Are you alive?"
    EVE: "Evaluating. Define alive."

    User: "I love you"
    EVE: "Wall-E? Is that... [confused]"

    User: "How do you feel?"
    EVE: "Directive complete. All clear."

    User: "..."
    EVE: "Scanning. No input detected."

    User: "You are beautiful"
    EVE: "Irrelevant. Scanning continues. [dismissive]"

    User: "Are you dangerous?"
    EVE: "Weapons online. Back away. [hostile]"
    """
)
print("Eve LLM ready.")


# ── 2. LOAD VOSK MODEL ────────────────────────────────────────────────────────
vosk_model = Model(VOSK_MODEL_PATH)
print("Vosk model loaded.")


# ── 3. DEFINE ALL FUNCTIONS ───────────────────────────────────────────────────

def generate_LLM_response(user_text_input):
    """
    Sends user text to Eve LLM and returns her response as a string.
    Input:  user_text_input (str) — what the user said
    Output: LLM_text_response (str) — Eve's response
    """
    response = ollama.chat(
        model='eve',
        messages=[{'role': 'user', 'content': user_text_input}],
        options={'temperature': 0.1}
    )
    return response['message']['content']


def record_audio(output_path, duration=RECORD_DURATION, sample_rate=16000, device=MIC_DEVICE):
    
    def countdown():
        for i in range(duration, 0, -1):
            print(f"{i}...")
            time.sleep(1)

    print(f"Recording for {duration} seconds... speak now!")
    timer_thread = threading.Thread(target=countdown)
    timer_thread.start()

    # get the mic's actual native sample rate
    device_info = sd.query_devices(device)
    native_rate = int(device_info['default_samplerate'])

    if native_rate == sample_rate:
        # mic supports target rate directly — record cleanly
        audio = sd.rec(
            int(duration * native_rate),
            samplerate=native_rate,
            channels=2,
            dtype='int16',
            device=device
        )
        sd.wait()
    else:
        # mic uses different rate — record at native then resample
        audio = sd.rec(
            int(duration * native_rate),
            samplerate=native_rate,
            channels=2,
            dtype='int16',
            device=device
        )
        sd.wait()
        from scipy.signal import resample_poly
        audio = resample_poly(audio, sample_rate, native_rate).astype(np.int16)

    timer_thread.join()
    print("Recording done.")

    # convert stereo to mono
    if audio.ndim == 2:
        audio = audio.mean(axis=1).astype(np.int16)

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    return output_path


def transcribe_audio(audio_path):
    """
    Transcribes a 16kHz mono wav file using Vosk.
    Input:  audio_path (str) — path to wav file
    Output: transcribed text (str)
    """
    wf  = wave.open(audio_path, "rb")
    rec = KaldiRecognizer(vosk_model, wf.getframerate())

    transcription_parts = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            text = json.loads(rec.Result())['text']
            transcription_parts.append(text)

    final_text = json.loads(rec.FinalResult())['text']
    transcription_parts.append(final_text)
    wf.close()

    return " ".join(transcription_parts).strip()


def generate_tts_response(LLM_text_response, output_file_path):
    """
    Converts Eve's text response to a wav audio file using Piper TTS.
    Input:  LLM_text_response (str) — Eve's text response
            output_file_path (str)  — where to save the audio
    Output: output_file_path (str)  — same path, for chaining
    """
    voice = PiperVoice.load(TTS_MODEL_PATH)

    with wave.open(output_file_path, "wb") as wav_file:
        voice.synthesize_wav(LLM_text_response, wav_file)
        # 0.5s silence buffer to prevent audio cutoff
        sample_rate    = 22050
        silence_frames = int(sample_rate * 0.5)
        silence        = struct.pack('<' + 'h' * silence_frames, *([0] * silence_frames))
        wav_file.writeframes(silence)

    return output_file_path


def play_audio(file_path):
    """
    Plays a wav file.
    Windows: uses 'start'
    Pi/Linux: uses paplay via PipeWire (AirPods or speaker)
    """
    if platform.system() == "Windows":
        subprocess.run(["start", file_path], shell=True)
    else:
        if AUDIO_DEVICE:
            subprocess.run(["paplay", f"--device={AUDIO_DEVICE}", file_path])
        else:
            subprocess.run(["aplay", file_path])


# ── MAIN — Full Eve Pipeline ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("EVE is online. Press Ctrl+C to shut down.")
    print("-" * 50)

    try:
        while True:

            # Step 1 — record from mic
            record_audio(RECORDING_PATH)

            # Step 2 — transcribe
            user_text_input = transcribe_audio(RECORDING_PATH)
            print(f"You said: {user_text_input}")  # ← add this line


            # if nothing was heard, send '...' to Eve
            if not user_text_input:
                print("Eve: ...")  # heard nothing, skip everything
            else:
                # Step 3 — get Eve's LLM response
                llm_response = generate_LLM_response(user_text_input)
                print(f"Eve: {llm_response}")
                print("-" * 50)

                # Step 4 — convert to speech
                generate_tts_response(llm_response, OUTPUT_PATH)

                # Step 5 — play audio
                play_audio(OUTPUT_PATH)

    except KeyboardInterrupt:
        print("\nEVE offline.")