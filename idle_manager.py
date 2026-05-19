#!/usr/bin/env python3
"""
idle_manager.py
---------------
EVE idle animation manager.

Sound mapping:
    0001.mp3 → power down
    0002.mp3 → power on / wake up
    0003.mp3 → curious/scanning
    0004.mp3 → happy/laugh
    0005.mp3 → mechanical movement (head/arm swing)
    0006.mp3 → complex idle animation (head turn + alternating arms)
    0007.mp3 → startup/boot systems initializing
    0008.mp3 → confused/uncertain
    0009.mp3 → random idle ambient
    0010.mp3 → Wall-E call
    sunday_clothes.mp3 → Put On Your Sunday Clothes (dance song)

Idle states received from voice pipeline (idle_queue):
    "awake"      → start idle animations
    "busy"       → pause idle animations
    "reset"      → reset inactivity timer
    "boot"       → play 0007.mp3 (first wake)
    "wake_sound" → play 0002.mp3 (subsequent wakes)
    "powerdown"  → play 0001.mp3
    "walle"      → play 0010.mp3
    "play_music" → play Put On Your Sunday Clothes
    "emotion:X"  → play matching sound
"""

import time
import random
import subprocess
import os

# ── CONFIG ────────────────────────────────────────────────────────────────────
IDLE_ANIM_MIN     = 5.0
IDLE_ANIM_MAX     = 15.0
POWERDOWN_TIMEOUT = 600.0   # 10 minutes
SOUNDS_DIR        = "sounds"
VERBOSE           = False   # set to True to show [Idle] debug messages

SND_POWERDOWN   = "0001.mp3"
SND_POWERON     = "0002.mp3"
SND_CURIOUS     = "0003.mp3"
SND_HAPPY       = "0004.mp3"
SND_MECHANICAL  = "0005.mp3"
SND_COMPLEX     = "0006.mp3"
SND_BOOT        = "0007.mp3"
SND_CONFUSED    = "0008.mp3"
SND_AMBIENT     = "0009.mp3"
SND_WALLE       = "0010.mp3"
SND_MUSIC       = "Hello Dolly - Put on Your Sunday Clothes.mp3"


def play_sound(filename, block=False):
    path = os.path.join(SOUNDS_DIR, filename)
    if not os.path.exists(path):
        print(f"[Idle] sound not found: {path}")
        return None
    if block:
        subprocess.run(["mpg123", "-q", path])
        return None
    else:
        proc = subprocess.Popen(["mpg123", "-q", path])
        return proc


# ── IDLE MANAGER ──────────────────────────────────────────────────────────────
class IdleManager:
    def __init__(self, idle_queue, eye_queue, servo_queue):
        self.idle_queue   = idle_queue
        self.eye_queue    = eye_queue
        self.servo_queue  = servo_queue
        self.awake        = False
        self.busy         = False
        self.last_active  = None
        self.next_anim    = None
        self.powered_down = False
        print("Idle manager ready.")

    def send_eye(self, state):
        if self.eye_queue is not None:
            self.eye_queue.put(state)

    def send_servo(self, state):
        if self.servo_queue is not None:
            self.servo_queue.put(state)

    def play_idle_animation(self):
        anim = random.choice([
            "head_left", "head_right", "head_center",
            "eye_look", "arm_wave", "complex", "ambient",
        ])
        if VERBOSE: print(f"[Idle] animation: {anim}")

        if anim == "head_left":
            play_sound(SND_MECHANICAL)
            self.send_servo("idle_head_left")
        elif anim == "head_right":
            play_sound(SND_MECHANICAL)
            self.send_servo("idle_head_right")
        elif anim == "head_center":
            self.send_servo("idle_head_center")
        elif anim == "arm_wave":
            play_sound(SND_MECHANICAL)
            self.send_servo("idle_arm_wave")
        elif anim == "eye_look":
            play_sound(SND_CURIOUS)
            self.send_eye("idle_look")
        elif anim == "complex":
            play_sound(SND_COMPLEX)
            self.send_servo("idle_complex")
        elif anim == "ambient":
            play_sound(SND_AMBIENT)

    def trigger_emotion_sound(self, emotion):
        emotion = emotion.lower().strip("[]")
        if emotion in ("happy", "excited"):
            play_sound(SND_HAPPY)
        elif emotion in ("curious",):
            play_sound(SND_CURIOUS)
        elif emotion in ("confused",):
            play_sound(SND_CONFUSED)
        elif emotion in ("neutral",):
            play_sound(SND_CURIOUS)

    def check_queue(self):
        while not self.idle_queue.empty():
            try:
                msg = self.idle_queue.get_nowait()
                if msg == "awake":
                    self.awake        = True
                    self.busy         = False
                    self.powered_down = False
                    self.last_active  = time.time()
                    self.next_anim    = time.time() + random.uniform(IDLE_ANIM_MIN, IDLE_ANIM_MAX)
                    if VERBOSE: print("[Idle] state → awake")
                elif msg == "busy":
                    self.busy = True
                    if VERBOSE: print("[Idle] state → busy")
                elif msg == "reset":
                    self.last_active = time.time()
                    self.busy        = False
                    if VERBOSE: print("[Idle] activity reset")
                elif msg.startswith("emotion:"):
                    emotion = msg.split(":", 1)[1]
                    self.trigger_emotion_sound(emotion)
                elif msg == "walle":
                    play_sound(SND_WALLE)
                elif msg == "powerdown":
                    play_sound(SND_POWERDOWN, block=True)
                elif msg == "boot":
                    play_sound(SND_BOOT, block=True)
                elif msg == "wake_sound":
                    play_sound(SND_POWERON, block=True)
                elif msg == "play_music":
                    # play music and trigger dance animation simultaneously
                    play_sound(SND_MUSIC, block=False)
                    self.send_servo("dance")
                    if VERBOSE: print("[Idle] playing music + dance")
            except:
                pass

    def update(self):
        now = time.time()
        self.check_queue()

        if not self.awake or self.powered_down:
            return

        if self.last_active is not None and (now - self.last_active) > POWERDOWN_TIMEOUT:
            if VERBOSE: print("[Idle] 10 min inactivity → power down")
            play_sound(SND_POWERDOWN)
            self.send_eye("closed")
            self.send_servo("idle")
            self.awake        = False
            self.powered_down = True
            return

        if not self.busy and self.next_anim is not None and now >= self.next_anim:
            self.play_idle_animation()
            self.next_anim = now + random.uniform(IDLE_ANIM_MIN, IDLE_ANIM_MAX)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main(idle_queue=None, eye_queue=None, servo_queue=None):
    manager = IdleManager(idle_queue, eye_queue, servo_queue)
    try:
        while True:
            manager.update()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nIdle manager offline.")


if __name__ == "__main__":
    main()