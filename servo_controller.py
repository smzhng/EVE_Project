#!/usr/bin/env python3
"""
servo_controller.py
-------------------
EVE servo control via PCA9685 16-channel PWM board.

Servo layout:
    Channel 0  → Left arm up/down
    Channel 4  → Arms extend/retract from torso
    Channel 8  → Right arm up/down
    Channel 12 → Head left/right

Positions:
    Arms:    0 = down,   180 = up
    Extend:  0 = in,     90  = out
    Head:    0 = left,   90  = center,  180 = right

Run standalone:
    python3 servo_controller.py

Run together with eyes + voice:
    sudo python3 main.py

Dependencies:
    pip install adafruit-circuitpython-servokit --break-system-packages
"""

import time
import threading
from adafruit_servokit import ServoKit

# ── CONFIG ────────────────────────────────────────────────────────────────────
CH_LEFT_ARM  = 0
CH_EXTEND    = 4
CH_RIGHT_ARM = 8
CH_HEAD      = 12

PULSE_MIN    = 500
PULSE_MAX    = 2500

# Named positions
ARM_DOWN     = 10
ARM_UP       = 170
ARM_HALF     = 90
EXTEND_IN    = 10
EXTEND_OUT   = 90
HEAD_LEFT    = 20
HEAD_CENTER  = 90
HEAD_RIGHT   = 160

# Smooth movement
SMOOTH_STEPS = 20
SMOOTH_DELAY = 0.02   # seconds between steps


# ── SERVO CONTROLLER ──────────────────────────────────────────────────────────
class ServoController:
    def __init__(self):
        self.kit = ServoKit(channels=16)
        for ch in [CH_LEFT_ARM, CH_EXTEND, CH_RIGHT_ARM, CH_HEAD]:
            self.kit.servo[ch].set_pulse_width_range(PULSE_MIN, PULSE_MAX)

        # track current angles
        self.angles = {
            CH_LEFT_ARM:  ARM_DOWN,
            CH_EXTEND:    EXTEND_IN,
            CH_RIGHT_ARM: ARM_DOWN,
            CH_HEAD:      HEAD_CENTER,
        }

        # move to default positions on startup
        self._set_all(
            left=ARM_DOWN,
            right=ARM_DOWN,
            extend=EXTEND_IN,
            head=HEAD_CENTER
        )
        print("Servos initialized.")

    def _set(self, channel, angle):
        """Instantly set a servo to an angle."""
        angle = max(0, min(180, angle))
        self.kit.servo[channel].angle = angle
        self.angles[channel] = angle

    def _set_all(self, left, right, extend, head):
        """Instantly set all servos."""
        self._set(CH_LEFT_ARM,  left)
        self._set(CH_RIGHT_ARM, right)
        self._set(CH_EXTEND,    extend)
        self._set(CH_HEAD,      head)

    def smooth_move(self, channel, target, steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        """Smoothly move a servo from current position to target angle."""
        start = self.angles[channel]
        target = max(0, min(180, target))
        for i in range(1, steps + 1):
            angle = int(start + (target - start) * i / steps)
            self._set(channel, angle)
            time.sleep(delay)

    def smooth_move_all(self, left=None, right=None, extend=None, head=None,
                        steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        """Smoothly move multiple servos simultaneously using threads."""
        threads = []
        if left   is not None: threads.append(threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  left,   steps, delay)))
        if right  is not None: threads.append(threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, right,  steps, delay)))
        if extend is not None: threads.append(threading.Thread(target=self.smooth_move, args=(CH_EXTEND,    extend, steps, delay)))
        if head   is not None: threads.append(threading.Thread(target=self.smooth_move, args=(CH_HEAD,      head,   steps, delay)))
        for t in threads: t.start()
        for t in threads: t.join()

    # ── PRESET ANIMATIONS ─────────────────────────────────────────────────────

    def idle(self):
        """Default resting position."""
        self.smooth_move_all(left=ARM_DOWN, right=ARM_DOWN, extend=EXTEND_IN, head=HEAD_CENTER)

    def alert(self):
        """Wake word detected — head snaps to center, arms slightly raised."""
        self.smooth_move_all(left=ARM_HALF, right=ARM_HALF, extend=EXTEND_IN, head=HEAD_CENTER, steps=10, delay=0.01)

    def happy(self):
        """Wall-E mentioned or plant found — arms raise and extend."""
        self.smooth_move_all(left=ARM_UP, right=ARM_UP, extend=EXTEND_OUT, head=HEAD_CENTER)
        time.sleep(0.5)
        self.smooth_move_all(left=ARM_DOWN, right=ARM_DOWN, extend=EXTEND_IN, head=HEAD_CENTER)

    def suspicious(self):
        """Scanning unknown entity — head tilts left, arms stay down."""
        self.smooth_move_all(head=HEAD_LEFT)
        time.sleep(0.5)
        self.smooth_move_all(head=HEAD_RIGHT)
        time.sleep(0.5)
        self.smooth_move_all(head=HEAD_CENTER)

    def hostile(self):
        """Threat detected — arms extend out aggressively."""
        self.smooth_move_all(left=ARM_HALF, right=ARM_HALF, extend=EXTEND_OUT, head=HEAD_CENTER, steps=8, delay=0.01)
        time.sleep(0.3)
        self.smooth_move_all(left=ARM_UP, right=ARM_UP, steps=8, delay=0.01)

    def alarmed(self):
        """Danger detected — quick head scan."""
        self.smooth_move_all(head=HEAD_LEFT, steps=8, delay=0.01)
        time.sleep(0.2)
        self.smooth_move_all(head=HEAD_RIGHT, steps=8, delay=0.01)
        time.sleep(0.2)
        self.smooth_move_all(head=HEAD_CENTER, steps=8, delay=0.01)

    def thinking(self):
        """LLM processing — slow head tilt."""
        self.smooth_move_all(head=HEAD_LEFT, steps=30, delay=0.03)

    def idle_wander(self):
        """Idle animation — slow random head movement."""
        import random
        target = random.choice([HEAD_LEFT, HEAD_CENTER, HEAD_RIGHT])
        self.smooth_move_all(head=target, steps=40, delay=0.04)

    def play_animation(self, emotion):
        """
        Play animation based on emotion tag from LLM response.
        Called from llm_model.py after parsing Eve's response.
        """
        emotion = emotion.lower().strip("[]")
        if emotion in ("happy", "excited"):
            self.happy()
        elif emotion in ("suspicious", "neutral"):
            self.suspicious()
        elif emotion in ("hostile",):
            self.hostile()
        elif emotion in ("alarmed",):
            self.alarmed()
        else:
            self.idle()


# ── STANDALONE TEST ───────────────────────────────────────────────────────────
def main():
    print("EVE servo test — running all animations...")
    sc = ServoController()
    time.sleep(1)

    print("Alert...")
    sc.alert()
    time.sleep(1)

    print("Happy...")
    sc.happy()
    time.sleep(1)

    print("Suspicious...")
    sc.suspicious()
    time.sleep(1)

    print("Hostile...")
    sc.hostile()
    time.sleep(1)

    print("Alarmed...")
    sc.alarmed()
    time.sleep(1)

    print("Idle...")
    sc.idle()
    print("Done.")


if __name__ == "__main__":
    main()
