#!/usr/bin/env python3
"""
main.py
-------
Runs EVE's eye animations and voice pipeline simultaneously.
A shared queue lets the voice pipeline signal eye state changes.

Eye states:
    idle    → normal random blinking
    wake    → eyes snap open wide (wake word detected)
    listen  → eyes stay open (recording speech)
    think   → eyes slightly squinted (LLM processing)

Run:
    sudo python3 main.py

Press Ctrl+C to shut down both processes cleanly.
"""

from multiprocessing import Process, Queue
import signal
import sys


def run_eyes(eye_queue):
    """Runs the eye animation in its own process."""
    import eve_eyes
    eve_eyes.main(eye_queue)


def run_voice(eye_queue):
    """Runs the voice pipeline in its own process."""
    import llm_model
    llm_model.main(eye_queue)


if __name__ == "__main__":
    print("=" * 50)
    print("  EVE ONLINE")
    print("  Eyes + Voice starting simultaneously")
    print("  Press Ctrl+C to shut down")
    print("=" * 50)

    # shared queue — voice sends states, eyes react
    eye_queue = Queue()

    eye_process   = Process(target=run_eyes,  args=(eye_queue,), name="EVE-Eyes")
    voice_process = Process(target=run_voice, args=(eye_queue,), name="EVE-Voice")

    eye_process.start()
    voice_process.start()

    print(f"Eyes process started  (PID {eye_process.pid})")
    print(f"Voice process started (PID {voice_process.pid})")

    def shutdown(sig, frame):
        print("\nShutting down EVE...")
        eye_process.terminate()
        voice_process.terminate()
        eye_process.join()
        voice_process.join()
        print("EVE offline.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    eye_process.join()
    voice_process.join()