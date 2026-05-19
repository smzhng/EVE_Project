#!/usr/bin/env python3
"""
llm_model.py
------------
EVE AI voice pipeline for Raspberry Pi.

Pipeline:
    Mic (always on) → OpenWakeWord → WebRTC VAD → Vosk STT → Ollama LLM → Piper TTS → Speaker

Run standalone:
    python3 llm_model.py

Run together with eyes + servos + idle:
    sudo python3 main.py

Dependencies:
    sudo pip3 install ollama vosk sounddevice piper-tts numpy openwakeword webrtcvad pyaudio scipy --break-system-packages
    ollama pull phi4-mini
"""

# ── IMPORTS ───────────────────────────────────────────────────────────────────
import os
import re
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
VOSK_MODEL_PATH    = "stt/vosk-model-en-us-0.22-lgraph"
TTS_MODEL_PATH     = "tts/en_US-libritts_r-medium.onnx"
OUTPUT_PATH        = "tts/speech_outputs/response.wav"
AUDIO_DEVICE       = "bluez_output.F4_4E_FD_2B_B4_43.1"  # onn bluetooth speaker
SAMPLE_RATE        = 16000
NATIVE_RATE        = 44100

# ── Wake word config ──────────────────────────────────────────────────────────
WAKE_WORD          = "okay_eve"   # custom trained wake word
WAKE_THRESHOLD     = 0.3
REQUIRED_HITS      = 3
NOISE_GATE         = 0

# ── VAD config ────────────────────────────────────────────────────────────────
VAD_MODE           = 3
VAD_FRAME_MS       = 30
VAD_FRAME_SAMPLES  = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
VAD_NATIVE_SAMPLES = int(NATIVE_RATE * VAD_FRAME_MS / 1000)
VAD_PADDING_MS     = 1000   # ms of silence before cutting off — increased for more time
VAD_MAX_RECORD_S   = 15     # max recording seconds

OWW_CHUNK          = 1280
OWW_NATIVE_CHUNK   = int(NATIVE_RATE * OWW_CHUNK / SAMPLE_RATE)


# ── HELPERS ───────────────────────────────────────────────────────────────────
def resample_to_16k(audio_bytes):
    audio     = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    gcd       = math.gcd(SAMPLE_RATE, NATIVE_RATE)
    up, down  = SAMPLE_RATE // gcd, NATIVE_RATE // gcd
    resampled = resample_poly(audio, up, down).astype(np.int16)
    return resampled

def parse_emotion(llm_response):
    """Extract emotion tag from Eve's response e.g. [suspicious]."""
    match = re.search(r'\[(\w+)\]', llm_response)
    if match:
        return match.group(1).lower()
    return None

def contains_walle(text):
    """Check if Wall-E is mentioned in text."""
    return "wall-e" in text.lower() or "walle" in text.lower()

def parse_gesture(text):
    """Check if user input matches a gesture trigger."""
    text = text.lower()
    if any(w in text for w in ["hello", "hi", "hey", "greetings", "howdy"]):
        return "wave"
    if any(w in text for w in ["thank you", "thanks", "appreciate", "yes", "correct", "exactly", "right"]):
        return "nod"
    if any(w in text for w in ["no", "wrong", "incorrect", "nope"]):
        return "shake"
    if any(w in text for w in ["look", "watch", "see", "show", "what is that", "over there"]):
        return "look_around"
    if any(w in text for w in ["i don't know", "not sure", "maybe", "whatever", "shrug"]):
        return "shrug"
    return None

def contains_music_request(text):
    """Check if user is asking Eve to play music."""
    text = text.lower()
    return any(p in text for p in ["play music", "play a song", "play some music", "dance", "play something", "sing"])

def send_eye_state(eye_queue, state):
    if eye_queue is not None:
        eye_queue.put(state)

def send_servo_state(servo_queue, state):
    if servo_queue is not None:
        servo_queue.put(state)

def send_idle_state(idle_queue, state):
    if idle_queue is not None:
        idle_queue.put(state)


# ── 1. CREATE EVE LLM ─────────────────────────────────────────────────────────
try:
    ollama.show('eve')
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
if WAKE_WORD == "okay_eve":
    oww_model = WakeModel(wakeword_model_paths=["models/okay_eve.onnx"])
else:
    oww_model = WakeModel()
print("Wake word model loaded.")


# ── 4. PIPELINE FUNCTIONS ─────────────────────────────────────────────────────

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


def record_with_vad():
    vad = webrtcvad.Vad(VAD_MODE)
    padding_frames = VAD_PADDING_MS // VAD_FRAME_MS
    ring_buffer    = collections.deque(maxlen=padding_frames)
    triggered      = False
    voiced_frames  = []
    max_frames     = int(VAD_MAX_RECORD_S * 1000 / VAD_FRAME_MS)
    frame_count    = 0

    print("Eve: Listening...")

    with sd.InputStream(samplerate=NATIVE_RATE, channels=1, dtype='int16',
                        device=MIC_DEVICE, blocksize=VAD_NATIVE_SAMPLES) as mic:
        while frame_count < max_frames:
            raw, _       = mic.read(VAD_NATIVE_SAMPLES)
            resampled    = resample_to_16k(raw.tobytes())
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
    import tempfile, os
    voice = PiperVoice.load(TTS_MODEL_PATH)

    tmp_path = output_file_path + ".tmp.wav"
    with wave.open(tmp_path, "wb") as tmp_wav:
        voice.synthesize_wav(LLM_text_response, tmp_wav)

    with wave.open(tmp_path, "rb") as tmp_wav:
        params      = tmp_wav.getparams()
        speech_data = tmp_wav.readframes(tmp_wav.getnframes())
    os.remove(tmp_path)

    silence_frames = int(params.framerate * 1.5)
    silence        = struct.pack('<' + 'h' * silence_frames, *([0] * silence_frames))

    with wave.open(output_file_path, "wb") as wav_file:
        wav_file.setparams(params)
        wav_file.writeframes(silence)
        wav_file.writeframes(speech_data)

    return output_file_path


def play_audio(file_path):
    if platform.system() == "Windows":
        subprocess.run(["start", file_path], shell=True)
    else:
        if AUDIO_DEVICE:
            subprocess.run(["paplay", f"--device={AUDIO_DEVICE}", file_path])
        else:
            subprocess.run(["aplay", "-D", "plughw:2,0", file_path])


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main(eye_queue=None, servo_queue=None, idle_queue=None, llm_queue=None):
    print("EVE voice pipeline online.")
    print(f"Say '{WAKE_WORD.replace('_', ' ')}' to activate Eve.")
    print("Press Ctrl+C to shut down.")
    print("-" * 50)

    pa            = pyaudio.PyAudio()
    stream        = pa.open(
        rate=NATIVE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        input_device_index=MIC_DEVICE,
        frames_per_buffer=OWW_NATIVE_CHUNK
    )
    trigger_count = 0
    eve_awake     = False

    try:
        while True:
            # check for powerdown signal from eye process
            if llm_queue is not None and not llm_queue.empty():
                try:
                    msg = llm_queue.get_nowait()
                    if msg == "powerdown":
                        eve_awake = False
                except:
                    pass
            raw   = stream.read(OWW_NATIVE_CHUNK, exception_on_overflow=False)
            audio = resample_to_16k(raw)

            if NOISE_GATE > 0 and np.abs(audio).mean() < NOISE_GATE:
                trigger_count = 0
            else:
                prediction = oww_model.predict(audio)
                score      = prediction.get(WAKE_WORD, 0)
                if score >= WAKE_THRESHOLD:
                    trigger_count += 1
                    print(f"[OWW] score={score:.3f} hit={trigger_count}/{REQUIRED_HITS}")
                else:
                    if score > 0.1:
                        print(f"[OWW] score={score:.3f} (below threshold)")
                    trigger_count = 0

            if trigger_count >= REQUIRED_HITS:
                trigger_count = 0
                print(f"\nEve: Wake word detected!")

                # ── Boot sound plays on first wake ────────────────────────────
                if not eve_awake:
                    send_idle_state(idle_queue, "boot")
                    eve_awake = True
                else:
                    send_idle_state(idle_queue, "wake_sound")

                # ── Wake — eyes open, arms extend ─────────────────────────────
                send_eye_state(eye_queue, "wake")
                send_servo_state(servo_queue, "wake")
                send_idle_state(idle_queue, "awake")

                stream.stop_stream()
                stream.close()

                # ── Listen ────────────────────────────────────────────────────
                send_eye_state(eye_queue, "listen")
                send_servo_state(servo_queue, "listen")
                send_idle_state(idle_queue, "busy")

                audio_path = record_with_vad()

                if not audio_path:
                    print("Eve: ...")
                    send_eye_state(eye_queue, "idle")
                    send_idle_state(idle_queue, "reset")
                else:
                    user_text_input = transcribe_audio(audio_path)
                    print(f"You said: {user_text_input}")

                    if not user_text_input:
                        print("Eve: ...")
                        send_eye_state(eye_queue, "idle")
                        send_idle_state(idle_queue, "reset")
                    else:
                        # ── Think ─────────────────────────────────────────────
                        send_eye_state(eye_queue, "think")
                        send_servo_state(servo_queue, "think")
                        send_idle_state(idle_queue, "busy")

                        llm_response = generate_LLM_response(user_text_input)
                        print(f"Eve: {llm_response}")
                        tts_response = re.sub(r'\[.*?\]', '', llm_response).strip()

                        # ── Wall-E sound ──────────────────────────────────────
                        if contains_walle(user_text_input) or contains_walle(llm_response):
                            send_idle_state(idle_queue, "walle")

                        # ── Emotion animation + sound ─────────────────────────
                        emotion = parse_emotion(llm_response)
                        if emotion:
                            send_servo_state(servo_queue, f"emotion:{emotion}")
                            send_idle_state(idle_queue, f"emotion:{emotion}")

                        generate_tts_response(tts_response, OUTPUT_PATH)
                        play_audio(OUTPUT_PATH)

                        # back to idle — arms stay extended, idle anims resume
                        send_eye_state(eye_queue, "idle")
                        send_idle_state(idle_queue, "reset")

                # ── Reopen OWW stream ─────────────────────────────────────────
                stream = pa.open(
                    rate=NATIVE_RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    input_device_index=MIC_DEVICE,
                    frames_per_buffer=OWW_NATIVE_CHUNK
                )
                oww_model.reset()
                trigger_count = 0
                print("-" * 50)
                print(f"Say '{WAKE_WORD.replace('_', ' ')}' to activate Eve.")

    except KeyboardInterrupt:
        print("\nEVE voice offline.")
        send_idle_state(idle_queue, "powerdown")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()