#!/usr/bin/env python3
"""
main.py
-------
Runs EVE's eye animations, voice pipeline, and servo controller simultaneously.
Two shared queues let the voice pipeline signal eye and servo state changes.

Run:
    sudo python3 main.py

Press Ctrl+C to shut down all processes cleanly.
"""

from multiprocessing import Process, Queue
import signal
import sys


def run_eyes(eye_queue):
    import eve_eyes
    eve_eyes.main(eye_queue)


def run_voice(eye_queue, servo_queue):
    import llm_model
    llm_model.main(eye_queue, servo_queue)


def run_servos(servo_queue):
    import servo_controller
    servo_controller.main(servo_queue)


if __name__ == "__main__":
    print("=" * 50)
    print("  EVE ONLINE")
    print("  Eyes + Voice + Servos starting")
    print("  Press Ctrl+C to shut down")
    print("=" * 50)

    eye_queue   = Queue()
    servo_queue = Queue()

    eye_process   = Process(target=run_eyes,   args=(eye_queue,),          name="EVE-Eyes")
    voice_process = Process(target=run_voice,  args=(eye_queue, servo_queue), name="EVE-Voice")
    servo_process = Process(target=run_servos, args=(servo_queue,),         name="EVE-Servos")

    eye_process.start()
    voice_process.start()
    servo_process.start()

    print(f"Eyes process started   (PID {eye_process.pid})")
    print(f"Voice process started  (PID {voice_process.pid})")
    print(f"Servo process started  (PID {servo_process.pid})")

    def shutdown(sig, frame):
        print("\nShutting down EVE...")
        eye_process.terminate()
        voice_process.terminate()
        servo_process.terminate()
        eye_process.join()
        voice_process.join()
        servo_process.join()
        print("EVE offline.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    eye_process.join()
    voice_process.join()
    servo_process.join()