#!/usr/bin/env python3
"""
servo_controller.py
-------------------
EVE servo control via PCA9685 16-channel PWM board.

Servo layout:
    Channel 0  → Right arm up/down
    Channel 4  → Arms extend/retract from torso
    Channel 8  → Left arm up/down (mirrored — moves opposite to right)
    Channel 12 → Head left/right

Positions:
    Arms:    0 = down,   180 = up
    Extend:  0 = in,     180 = out (full extension)
    Head:    0 = left,   90  = center,  180 = right

Note: Left arm (ch 8) is physically flipped so its angles are inverted.
      RIGHT arm 0° = down → LEFT arm 180° = down
      RIGHT arm 180° = up → LEFT arm 0° = up

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
CH_RIGHT_ARM = 0
CH_EXTEND    = 4
CH_LEFT_ARM  = 8
CH_HEAD      = 12

PULSE_MIN    = 500
PULSE_MAX    = 2500

# Named positions — right arm reference
ARM_DOWN     = 0
ARM_UP       = 180
ARM_HALF     = 90
EXTEND_IN    = 0
EXTEND_OUT   = 180
HEAD_LEFT    = 20
HEAD_CENTER  = 90
HEAD_RIGHT   = 160

# Left arm is mirrored — invert its angles
def mirror(angle):
    """Invert angle for the flipped left arm servo."""
    return 180 - angle

SMOOTH_STEPS = 20
SMOOTH_DELAY = 0.02


# ── SERVO CONTROLLER ──────────────────────────────────────────────────────────
class ServoController:
    def __init__(self):
        self.kit = ServoKit(channels=16)
        for ch in [CH_RIGHT_ARM, CH_EXTEND, CH_LEFT_ARM, CH_HEAD]:
            self.kit.servo[ch].set_pulse_width_range(PULSE_MIN, PULSE_MAX)

        self.angles = {
            CH_RIGHT_ARM: ARM_DOWN,
            CH_EXTEND:    EXTEND_IN,
            CH_LEFT_ARM:  mirror(ARM_DOWN),
            CH_HEAD:      HEAD_CENTER,
        }
        self.arms_extended = False

        # start in rest position
        self._set(CH_RIGHT_ARM, ARM_DOWN)
        self._set(CH_LEFT_ARM,  mirror(ARM_DOWN))
        self._set(CH_EXTEND,    EXTEND_IN)
        self._set(CH_HEAD,      HEAD_CENTER)
        print("Servos initialized — arms retracted, head center.")

    def _set(self, channel, angle):
        angle = max(0, min(180, angle))
        self.kit.servo[channel].angle = angle
        self.angles[channel] = angle

    def smooth_move(self, channel, target, steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        start  = self.angles[channel]
        target = max(0, min(180, target))
        for i in range(1, steps + 1):
            angle = int(start + (target - start) * i / steps)
            self._set(channel, angle)
            time.sleep(delay)

    def smooth_move_arms(self, arm_angle, steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        """Move both arms simultaneously — left arm is mirrored automatically."""
        t_right = threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, arm_angle,         steps, delay))
        t_left  = threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(arm_angle), steps, delay))
        t_right.start()
        t_left.start()
        t_right.join()
        t_left.join()

    def smooth_move_all(self, arm=None, extend=None, head=None,
                        steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        """Smoothly move multiple servos simultaneously."""
        threads = []
        if arm    is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, arm,           steps, delay)))
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(arm),   steps, delay)))
        if extend is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_EXTEND,    extend,        steps, delay)))
        if head   is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_HEAD,      head,          steps, delay)))
        for t in threads: t.start()
        for t in threads: t.join()

    # ── ANIMATIONS ────────────────────────────────────────────────────────────

    def wake(self):
        """Wake word detected — extend arms then head shake, raise arms."""
        print("[Servos] wake sequence")
        self.smooth_move(CH_EXTEND, EXTEND_OUT, steps=25, delay=0.02)
        self.arms_extended = True
        # head wake shake
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=8, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=8, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=8, delay=0.01)
        # raise arms to half
        self.smooth_move_arms(ARM_HALF, steps=15, delay=0.02)

    def listen(self):
        """Listening — head center, arms stay where they are."""
        print("[Servos] listen")
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=10, delay=0.02)

    def think(self):
        """Processing — slow head tilt."""
        print("[Servos] think")
        self.smooth_move(CH_HEAD, HEAD_LEFT, steps=30, delay=0.03)

    def rest(self):
        """Rest mode — lower arms, retract, head center."""
        print("[Servos] rest")
        self.smooth_move_arms(ARM_DOWN, steps=20, delay=0.02)
        self.smooth_move(CH_EXTEND, EXTEND_IN, steps=25, delay=0.02)
        self.arms_extended = False
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=15, delay=0.02)

    def happy(self):
        """Wall-E or plant — arms raise fully."""
        print("[Servos] happy")
        self.smooth_move_arms(ARM_UP, steps=15, delay=0.015)
        time.sleep(0.3)
        self.smooth_move_arms(ARM_HALF, steps=15, delay=0.02)

    def suspicious(self):
        """Unknown entity — head scan."""
        print("[Servos] suspicious")
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=12, delay=0.02)
        time.sleep(0.3)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=12, delay=0.02)
        time.sleep(0.3)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=12, delay=0.02)

    def hostile(self):
        """Threat — arms raise aggressively."""
        print("[Servos] hostile")
        self.smooth_move_arms(ARM_UP, steps=8, delay=0.01)

    def alarmed(self):
        """Danger — fast head scan."""
        print("[Servos] alarmed")
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=6, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=6, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=6, delay=0.01)

    def play_emotion(self, emotion):
        """Play animation based on emotion tag from LLM response."""
        emotion = emotion.lower().strip("[]")
        if emotion in ("happy", "excited"):
            self.happy()
        elif emotion in ("suspicious", "neutral"):
            self.suspicious()
        elif emotion in ("hostile",):
            self.hostile()
        elif emotion in ("alarmed",):
            self.alarmed()
        elif emotion in ("confused", "curious"):
            self.suspicious()
        else:
            self.smooth_move(CH_HEAD, HEAD_CENTER, steps=15, delay=0.02)


# ── MAIN (queue listener) ─────────────────────────────────────────────────────
def main(servo_queue=None):
    sc = ServoController()

    if servo_queue is None:
        print("Running standalone animation test...")
        time.sleep(1)
        sc.wake()
        time.sleep(1)
        sc.happy()
        time.sleep(1)
        sc.suspicious()
        time.sleep(1)
        sc.hostile()
        time.sleep(1)
        sc.alarmed()
        time.sleep(1)
        sc.rest()
        print("Done.")
        return

    print("Servo controller ready, listening for states...")

    try:
        while True:
            if not servo_queue.empty():
                try:
                    state = servo_queue.get_nowait()
                    print(f"[Servos] received: {state}")
                    if state == "wake":
                        sc.wake()
                    elif state == "listen":
                        sc.listen()
                    elif state == "think":
                        sc.think()
                    elif state == "idle":
                        sc.rest()
                    elif state == "happy":
                        sc.happy()
                    elif state == "suspicious":
                        sc.suspicious()
                    elif state == "hostile":
                        sc.hostile()
                    elif state == "alarmed":
                        sc.alarmed()
                    elif state.startswith("emotion:"):
                        emotion = state.split(":", 1)[1]
                        sc.play_emotion(emotion)
                except:
                    pass
            else:
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nServos offline.")
        sc.rest()


if __name__ == "__main__":
    main()