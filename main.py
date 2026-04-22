#!/usr/bin/env python3
"""
main.py
-------
Runs EVE's eye animations and voice pipeline simultaneously
using Python multiprocessing — each runs in its own process.

Run:
    sudo python3 main.py

Press Ctrl+C to shut down both processes cleanly.
"""

from multiprocessing import Process
import signal
import sys


def run_eyes():
    """Runs the eye animation in its own process."""
    import eve_eyes
    eve_eyes.main()


def run_voice():
    """Runs the voice pipeline in its own process."""
    import llm_model
    llm_model.main()


if __name__ == "__main__":
    print("=" * 50)
    print("  EVE ONLINE")
    print("  Eyes + Voice starting simultaneously")
    print("  Press Ctrl+C to shut down")
    print("=" * 50)

    # create both processes
    eye_process   = Process(target=run_eyes,  name="EVE-Eyes")
    voice_process = Process(target=run_voice, name="EVE-Voice")

    # start both
    eye_process.start()
    voice_process.start()

    print(f"Eyes process started  (PID {eye_process.pid})")
    print(f"Voice process started (PID {voice_process.pid})")

    def shutdown(sig, frame):
        """Clean shutdown on Ctrl+C."""
        print("\nShutting down EVE...")
        eye_process.terminate()
        voice_process.terminate()
        eye_process.join()
        voice_process.join()
        print("EVE offline.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # wait for both to finish
    eye_process.join()
    voice_process.join()
