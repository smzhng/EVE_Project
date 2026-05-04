#!/usr/bin/env python3
"""
llm_model.py
------------
EVE AI voice pipeline for Raspberry Pi.

Pipeline:
    Mic (always on) → OpenWakeWord → WebRTC VAD → Vosk STT → Ollama LLM → Piper TTS → Speaker

Run standalone:
    python3 llm_model.py

Run together with eyes:
    python3 main.py

Dependencies:
    sudo pip3 install ollama vosk sounddevice piper-tts numpy openwakeword webrtcvad pyaudio scipy --break-system-packages
    ollama pull phi4-mini
"""

# ── IMPORTS ───────────────────────────────────────────────────────────────────
import os
import warnings
os.environ["VOSK_LOG_LEVEL"] = "-1"
os.environ["ORT_LOGGING_LEVEL"] = "3"
warnings.filterwarnings("ignore")

import wave
import json
import time
import math
import struct
import platform
import subprocess
import collections
import numpy as np
import sounddevice as sd
import pyaudio
import webrtcvad
import ollama
from scipy.signal import resample_poly
from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)
from piper import PiperVoice
from openwakeword.model import Model as WakeModel

# find USB mic by name regardless of device number
def get_mic_device():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if 'USB' in d['name'] and d['max_input_channels'] > 0:
            return i
    return None

MIC_DEVICE = get_mic_device()
print(f"Using mic device: {MIC_DEVICE}")

# ── CONFIG ────────────────────────────────────────────────────────────────────
RECORDING_PATH     = "stt/speech_inputs/live_input.wav"
VOSK_MODEL_PATH    = "stt/vosk-model-small-en-us-0.15"
TTS_MODEL_PATH     = "tts/en_US-libritts_r-medium.onnx"
OUTPUT_PATH        = "tts/speech_outputs/response.wav"
AUDIO_DEVICE       = None    # MAX98357A via I2S — uses aplay hw:2,0
SAMPLE_RATE        = 16000   # Hz — required by Vosk, VAD, and OpenWakeWord
NATIVE_RATE        = 44100   # Hz — USB mic's actual hardware rate

# ── Wake word config ──────────────────────────────────────────────────────────
# Built-in options (no training needed):
#   "hey_jarvis", "alexa", "hey_mycroft"
# To use "hey_eve": train a custom model at github.com/dscripka/openWakeWord
WAKE_WORD          = "hey_jarvis"
WAKE_THRESHOLD     = 0.7     # 0.0–1.0 — raise if too many false triggers

# ── VAD config ────────────────────────────────────────────────────────────────
VAD_MODE           = 3       # 0=least aggressive, 3=most aggressive (filters noise)
VAD_FRAME_MS       = 30      # ms per VAD frame — must be 10, 20, or 30
VAD_FRAME_SAMPLES  = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)   # 480 samples @ 16kHz
VAD_NATIVE_SAMPLES = int(NATIVE_RATE * VAD_FRAME_MS / 1000)   # 1323 samples @ 44100Hz
VAD_PADDING_MS     = 500     # ms of silence before cutting off recording
VAD_MAX_RECORD_S   = 10      # hard cap — stops recording after this many seconds

# ── OpenWakeWord chunk sizes ───────────────────────────────────────────────────
OWW_CHUNK          = 1280                                          # samples @ 16kHz
OWW_NATIVE_CHUNK   = int(NATIVE_RATE * OWW_CHUNK / SAMPLE_RATE)  # samples @ 44100Hz


# ── RESAMPLE HELPER ───────────────────────────────────────────────────────────
def resample_to_16k(audio_bytes):
    """Resample raw int16 bytes from NATIVE_RATE to SAMPLE_RATE."""
    audio     = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    gcd       = math.gcd(SAMPLE_RATE, NATIVE_RATE)
    up, down  = SAMPLE_RATE // gcd, NATIVE_RATE // gcd
    resampled = resample_poly(audio, up, down).astype(np.int16)
    return resampled


# ── 1. CREATE EVE LLM ─────────────────────────────────────────────────────────
try:
    ollama.show('eve')
    print("Eve model already exists, skipping creation.")
except:
    print("Creating Eve model for the first time...")
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
    - If you cannot answer in 3 words or less, say "Classified." instead.
    - NEVER output repeated numbers, lists, or rambling text.

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

    User: "What is five times five?"
    EVE: "Classified."

    User: "What is two plus two?"
    EVE: "Irrelevant. Not directive."
    """
)
print("Eve LLM ready.")


# ── 2. LOAD VOSK MODEL ────────────────────────────────────────────────────────
vosk_model = Model(VOSK_MODEL_PATH)
print("Vosk model loaded.")


# ── 3. LOAD WAKE WORD MODEL ───────────────────────────────────────────────────
print(f"Loading wake word model: {WAKE_WORD}...")
oww_model = WakeModel()
print("Wake word model loaded.")


# ── 4. DEFINE ALL FUNCTIONS ───────────────────────────────────────────────────

def generate_LLM_response(user_text_input):
    start_time = time.time()
    client = ollama.Client(host='http://172.20.10.4:11434')
    response = client.chat(
        model='eve',
        messages=[{'role': 'user', 'content': user_text_input}],
        options={'temperature': 0.1}
    )
    elapsed = time.time() - start_time
    llm_response = response['message']['content']

    sentences = llm_response.split('.')
    if len(sentences) > 3:
        llm_response = '. '.join(sentences[:3]) + '.'
    print(f"Response time: {elapsed:.2f}s")
    return llm_response


def record_with_vad(stream):
    """
    Records from a PyAudio stream at NATIVE_RATE using WebRTC VAD.
    Resamples each frame to SAMPLE_RATE before VAD processing.
    Saves 16kHz mono wav to RECORDING_PATH.

    Input:  stream — open PyAudio stream at NATIVE_RATE, mono, int16
    Output: RECORDING_PATH (str) if speech detected, None if silence
    """
    vad = webrtcvad.Vad(VAD_MODE)

    padding_frames = VAD_PADDING_MS // VAD_FRAME_MS
    ring_buffer    = collections.deque(maxlen=padding_frames)
    triggered      = False
    voiced_frames  = []   # stores resampled 16kHz frame bytes
    max_frames     = int(VAD_MAX_RECORD_S * 1000 / VAD_FRAME_MS)
    frame_count    = 0

    print("Eve: Listening...")

    while frame_count < max_frames:
        raw          = stream.read(VAD_NATIVE_SAMPLES, exception_on_overflow=False)
        resampled    = resample_to_16k(raw)       # → 480 samples @ 16kHz
        frame_bytes  = resampled.tobytes()
        frame_count += 1
        is_speech    = vad.is_speech(frame_bytes, SAMPLE_RATE)

        if not triggered:
            ring_buffer.append((frame_bytes, is_speech))
            num_voiced = sum(1 for _, speech in ring_buffer if speech)
            if num_voiced > 0.6 * ring_buffer.maxlen:
                triggered = True
                print("Eve: Speech detected, recording...")
                voiced_frames.extend(f for f, _ in ring_buffer)
                ring_buffer.clear()
        else:
            voiced_frames.append(frame_bytes)
            ring_buffer.append((frame_bytes, is_speech))
            num_unvoiced = sum(1 for _, speech in ring_buffer if not speech)
            if num_unvoiced > 0.9 * ring_buffer.maxlen:
                print("Eve: Speech ended.")
                break

    if not voiced_frames:
        return None

    with wave.open(RECORDING_PATH, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b''.join(voiced_frames))

    return RECORDING_PATH


def transcribe_audio(audio_path):
    """
    Transcribes a 16kHz mono wav file using Vosk.
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
    Converts Eve's text response to a wav file using Piper TTS.
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
    if platform.system() == "Windows":
        subprocess.run(["start", file_path], shell=True)
    else:
        if AUDIO_DEVICE:
            subprocess.run(["paplay", f"--device={AUDIO_DEVICE}", file_path])
        else:
            subprocess.run(["aplay", "-D", "plughw:2,0", file_path])


# ── MAIN FUNCTION (called by main.py or standalone) ───────────────────────────
def main():
    print("EVE voice pipeline online.")
    print(f"Say '{WAKE_WORD.replace('_', ' ')}' to activate Eve.")
    print("Press Ctrl+C to shut down.")
    print("-" * 50)

    pa = pyaudio.PyAudio()
    # Reopen OWW stream for next wake word cycle
    stream = pa.open(
        rate=NATIVE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        input_device_index=MIC_DEVICE,
        frames_per_buffer=OWW_NATIVE_CHUNK
    )

    try:
        while True:
            # ── Wake word detection loop ──────────────────────────────────────
            raw        = stream.read(OWW_NATIVE_CHUNK, exception_on_overflow=False)
            audio      = resample_to_16k(raw)         # → 1280 samples @ 16kHz
            prediction = oww_model.predict(audio)

            if prediction.get(WAKE_WORD, 0) >= WAKE_THRESHOLD:
                print(f"\nEve: Wake word detected!")

                # ── VAD recording ─────────────────────────────────────────────
                stream.stop_stream()
                stream.close()

                vad_stream = pa.open(
                    rate=NATIVE_RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    input_device_index=MIC_DEVICE,
                    frames_per_buffer=VAD_NATIVE_SAMPLES
                )

                audio_path = record_with_vad(vad_stream)

                vad_stream.stop_stream()
                vad_stream.close()

                # Reopen OWW stream for next wake word cycle
                stream = pa.open(
                    rate=NATIVE_RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    input_device_index=MIC_DEVICE,
                    frames_per_buffer=OWW_NATIVE_CHUNK
                )
                oww_model.reset()

                # flush buffered audio before resuming detection
                for _ in range(30):
                    stream.read(OWW_NATIVE_CHUNK, exception_on_overflow=False)

                # ── Pipeline ──────────────────────────────────────────────────
                if not audio_path:
                    print("Eve: ...")
                else:
                    user_text_input = transcribe_audio(audio_path)
                    print(f"You said: {user_text_input}")

                    if not user_text_input:
                        print("Eve: ...")
                    else:
                        llm_response = generate_LLM_response(user_text_input)
                        print(f"Eve: {llm_response}")
                        print("-" * 50)
                        print(f"Say '{WAKE_WORD.replace('_', ' ')}' to activate Eve.")  # ← add this
                        generate_tts_response(llm_response, OUTPUT_PATH)
                        # play_audio(OUTPUT_PATH)  # uncomment when speaker is wired

    except KeyboardInterrupt:
        print("\nEVE voice offline.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


# ── RUN STANDALONE ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()