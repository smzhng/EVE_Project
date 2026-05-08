#!/usr/bin/env python3
"""
idle_manager.py
---------------
EVE idle animation manager.

Runs as a separate process. When Eve is in the awake/idle state,
randomly triggers eye movements, servo animations, and audio clips
every 5-15 seconds to make Eve feel alive.

When Eve is actively listening or responding, idle animations pause.
After 10 minutes of no interaction, signals eyes and servos to power down.

Idle states received from voice pipeline (idle_queue):
    "awake"  → Eve is active, start idle animations
    "busy"   → Eve is processing/listening, pause idle animations
    "reset"  → reset inactivity timer (interaction detected)

Sounds:
    Place MP3 files in sounds/ folder.
    mpg123 must be installed: sudo apt install mpg123

Run together with everything:
    sudo python3 main.py
"""

import time
import random
import subprocess
import os

# ── CONFIG ────────────────────────────────────────────────────────────────────
IDLE_ANIM_MIN      = 5.0    # minimum seconds between idle animations
IDLE_ANIM_MAX      = 15.0   # maximum seconds between idle animations
SOUND_CHANCE       = 0.3    # 30% chance an idle animation also plays a sound
POWERDOWN_TIMEOUT  = 600.0  # 10 minutes of no interaction → power down

SOUNDS_DIR         = "sounds"


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

        # load available sound files
        self.sounds = []
        if os.path.exists(SOUNDS_DIR):
            self.sounds = sorted([
                os.path.join(SOUNDS_DIR, f)
                for f in os.listdir(SOUNDS_DIR)
                if f.endswith('.mp3') or f.endswith('.wav')
            ])
        print(f"Idle manager ready. {len(self.sounds)} sound files loaded.")

    def send_eye(self, state):
        if self.eye_queue is not None:
            self.eye_queue.put(state)

    def send_servo(self, state):
        if self.servo_queue is not None:
            self.servo_queue.put(state)

    def play_random_sound(self):
        if not self.sounds:
            return
        sound = random.choice(self.sounds)
        print(f"[Idle] playing sound: {os.path.basename(sound)}")
        subprocess.Popen(["mpg123", "-q", sound])  # non-blocking

    def play_idle_animation(self):
        """Pick a random idle animation and optionally play a sound."""
        anim = random.choice([
            "head_left",
            "head_right",
            "head_center",
            "eye_look",
            "arm_wave",
            "combined",
        ])

        print(f"[Idle] animation: {anim}")

        if anim == "head_left":
            self.send_servo("idle_head_left")
        elif anim == "head_right":
            self.send_servo("idle_head_right")
        elif anim == "head_center":
            self.send_servo("idle_head_center")
        elif anim == "arm_wave":
            self.send_servo("idle_arm_wave")
        elif anim == "eye_look":
            self.send_eye("idle_look")
        elif anim == "combined":
            self.send_servo("idle_head_left")
            self.send_eye("idle_look")

        # random chance to also play a sound
        if random.random() < SOUND_CHANCE:
            self.play_random_sound()

    def check_queue(self):
        """Process messages from voice pipeline."""
        while not self.idle_queue.empty():
            try:
                msg = self.idle_queue.get_nowait()
                if msg == "awake":
                    self.awake        = True
                    self.busy         = False
                    self.powered_down = False
                    self.last_active  = time.time()
                    self.next_anim    = time.time() + random.uniform(IDLE_ANIM_MIN, IDLE_ANIM_MAX)
                    print("[Idle] state → awake")
                elif msg == "busy":
                    self.busy = True
                    print("[Idle] state → busy (pausing idle anims)")
                elif msg == "reset":
                    self.last_active = time.time()
                    self.busy        = False
                    print("[Idle] activity reset")
            except:
                pass

    def update(self):
        now = time.time()
        self.check_queue()

        if not self.awake or self.powered_down:
            return

        # 10 minute inactivity → power down
        if self.last_active is not None and (now - self.last_active) > POWERDOWN_TIMEOUT:
            print("[Idle] 10 min inactivity → power down")
            self.send_eye("closed")
            self.send_servo("idle")   # rest/retract
            self.awake        = False
            self.powered_down = True
            return

        # play idle animation on timer
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