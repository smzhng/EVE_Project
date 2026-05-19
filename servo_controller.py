#!/usr/bin/env python3
"""
servo_controller.py
-------------------
EVE servo control via PCA9685 16-channel PWM board.

Servo layout:
    Channel 0  → Right arm up/down
    Channel 4  → Arms extend/retract from torso
    Channel 8  → Left arm up/down (mirrored)
    Channel 12 → Head left/right

Arm positions (physical):
    ARM_DOWN   = arms at sides (default when extended)
    ARM_RAISED = arms slightly raised (gentle animations)
    ARM_FRONT  = arms horizontal out front (happy, excited)
    ARM_UP     = arms above head (hostile, alarmed only)

Right arm is offset by -23 degrees due to gear tooth alignment.
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

ARM_DOWN     = 180   # arms at sides — default extended position
ARM_RAISED   = 135   # arms slightly raised — gentle animations
ARM_FRONT    = 90    # arms horizontal out front — happy/excited
ARM_UP       = 0     # arms above head — hostile/alarmed only
EXTEND_IN    = 0
EXTEND_OUT   = 180
HEAD_LEFT    = 20
HEAD_CENTER  = 90
HEAD_RIGHT   = 160

SMOOTH_STEPS     = 20
SMOOTH_DELAY     = 0.02
RIGHT_ARM_OFFSET = -23   # right arm gear is 23 degrees off — brings down to 157
VERBOSE          = False  # set to True to show [Servos] debug messages

DANCE_BPM        = 94
DANCE_BEAT       = 60 / DANCE_BPM        # 0.638s per beat
DANCE_HALF_BEAT  = DANCE_BEAT / 2        # 0.319s

def mirror(angle):
    return 180 - angle

def right(angle):
    """Apply offset to right arm angle to compensate for gear tooth alignment."""
    return max(0, min(180, angle + RIGHT_ARM_OFFSET))


# ── SERVO CONTROLLER ──────────────────────────────────────────────────────────
class ServoController:
    def __init__(self):
        self.kit = ServoKit(channels=16)
        for ch in [CH_RIGHT_ARM, CH_EXTEND, CH_LEFT_ARM, CH_HEAD]:
            self.kit.servo[ch].set_pulse_width_range(PULSE_MIN, PULSE_MAX)

        self.angles = {
            CH_RIGHT_ARM: right(ARM_DOWN),
            CH_EXTEND:    EXTEND_IN,
            CH_LEFT_ARM:  mirror(ARM_DOWN),
            CH_HEAD:      HEAD_CENTER,
        }
        self.arms_extended = False

        self._set(CH_RIGHT_ARM, right(ARM_DOWN))
        self._set(CH_LEFT_ARM,  mirror(ARM_DOWN))
        self._set(CH_EXTEND,    EXTEND_IN)
        self._set(CH_HEAD,      HEAD_CENTER)
        print("Servos initialized.")

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
        t_right = threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, right(arm_angle),  steps, delay))
        t_left  = threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(arm_angle), steps, delay))
        t_right.start(); t_left.start()
        t_right.join();  t_left.join()

    def smooth_move_all(self, arm=None, extend=None, head=None,
                        steps=SMOOTH_STEPS, delay=SMOOTH_DELAY):
        threads = []
        if arm is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, right(arm),  steps, delay)))
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(arm), steps, delay)))
        if extend is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_EXTEND, extend, steps, delay)))
        if head is not None:
            threads.append(threading.Thread(target=self.smooth_move, args=(CH_HEAD, head, steps, delay)))
        for t in threads: t.start()
        for t in threads: t.join()

    # ── MAIN ANIMATIONS ───────────────────────────────────────────────────────

    def wake(self):
        if VERBOSE: print("[Servos] wake")
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=10, delay=0.02)  # face forward first
        self.smooth_move(CH_EXTEND, EXTEND_OUT, steps=25, delay=0.02)
        self.arms_extended = True
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=8, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=8, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=8, delay=0.01)

    def listen(self):
        if VERBOSE: print("[Servos] listen")
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=10, delay=0.02)

    def think(self):
        if VERBOSE: print("[Servos] think")
        self.smooth_move(CH_HEAD, HEAD_LEFT, steps=30, delay=0.03)

    def rest(self):
        if VERBOSE: print("[Servos] rest")
        self.smooth_move_arms(ARM_DOWN, steps=20, delay=0.02)
        self.smooth_move(CH_EXTEND, EXTEND_IN, steps=25, delay=0.02)
        self.arms_extended = False
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=15, delay=0.02)

    def happy(self):
        if VERBOSE: print("[Servos] happy")
        self.smooth_move_arms(ARM_FRONT, steps=15, delay=0.015)
        time.sleep(0.3)
        self.smooth_move_arms(ARM_DOWN, steps=15, delay=0.02)

    def suspicious(self):
        if VERBOSE: print("[Servos] suspicious")
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=12, delay=0.02)
        time.sleep(0.3)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=12, delay=0.02)
        time.sleep(0.3)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=12, delay=0.02)

    def hostile(self):
        if VERBOSE: print("[Servos] hostile")
        self.smooth_move_arms(ARM_UP, steps=8, delay=0.01)
        time.sleep(0.3)
        self.smooth_move_arms(ARM_DOWN, steps=8, delay=0.02)

    def alarmed(self):
        if VERBOSE: print("[Servos] alarmed")
        self.smooth_move_arms(ARM_RAISED, steps=6, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=6, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=6, delay=0.01)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=6, delay=0.01)
        self.smooth_move_arms(ARM_DOWN, steps=10, delay=0.02)

    # ── GESTURE ANIMATIONS ────────────────────────────────────────────────────

    def play_gesture(self, gesture):
        if VERBOSE: print(f"[Servos] gesture: {gesture}")
        if gesture == "wave":
            # wave right arm up and down twice
            self.smooth_move(CH_RIGHT_ARM, right(ARM_FRONT), steps=12, delay=0.02)
            time.sleep(0.15)
            self.smooth_move(CH_RIGHT_ARM, right(ARM_RAISED), steps=8, delay=0.02)
            time.sleep(0.15)
            self.smooth_move(CH_RIGHT_ARM, right(ARM_FRONT), steps=8, delay=0.02)
            time.sleep(0.15)
            self.smooth_move(CH_RIGHT_ARM, right(ARM_RAISED), steps=8, delay=0.02)
            time.sleep(0.15)
            self.smooth_move(CH_RIGHT_ARM, right(ARM_DOWN), steps=12, delay=0.02)
        elif gesture == "nod":
            # head tilt left then back (EVE's version of nodding)
            self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=8, delay=0.02)
            time.sleep(0.2)
            self.smooth_move(CH_HEAD, HEAD_CENTER, steps=8, delay=0.02)
        elif gesture == "shake":
            # head shake no
            self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=6, delay=0.01)
            self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=6, delay=0.01)
            self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=6, delay=0.01)
            self.smooth_move(CH_HEAD, HEAD_CENTER, steps=6, delay=0.01)
        elif gesture == "look_around":
            # curious scan
            self.smooth_move(CH_HEAD, HEAD_LEFT,   steps=20, delay=0.03)
            time.sleep(0.3)
            self.smooth_move(CH_HEAD, HEAD_RIGHT,  steps=20, delay=0.03)
            time.sleep(0.3)
            self.smooth_move(CH_HEAD, HEAD_CENTER, steps=20, delay=0.03)
        elif gesture == "shrug":
            # both arms raise slightly then drop
            self.smooth_move_arms(ARM_RAISED, steps=10, delay=0.02)
            time.sleep(0.3)
            self.smooth_move_arms(ARM_DOWN, steps=10, delay=0.02)

    # ── DANCE ANIMATION ───────────────────────────────────────────────────────

    def dance(self, duration=24.0):
        """Dance to Put On Your Sunday Clothes — 94 BPM, synced head/arm moves."""
        if VERBOSE: print("[Servos] dance start")
        steps_per_beat = 6
        delay_per_beat = DANCE_BEAT / steps_per_beat

        end_time = time.time() + duration
        beat = 0

        while time.time() < end_time:
            phase = beat % 8  # 8-beat cycle

            if phase == 0:
                # head left
                t = threading.Thread(target=self.smooth_move,
                    args=(CH_HEAD, HEAD_LEFT, steps_per_beat, delay_per_beat))
                t.start(); t.join()
            elif phase == 1:
                # right arm up
                t = threading.Thread(target=self.smooth_move,
                    args=(CH_RIGHT_ARM, right(ARM_FRONT), steps_per_beat, delay_per_beat))
                t.start(); t.join()
            elif phase == 2:
                # head right
                t = threading.Thread(target=self.smooth_move,
                    args=(CH_HEAD, HEAD_RIGHT, steps_per_beat, delay_per_beat))
                t.start(); t.join()
            elif phase == 3:
                # left arm up, right arm down
                t1 = threading.Thread(target=self.smooth_move,
                    args=(CH_RIGHT_ARM, right(ARM_DOWN), steps_per_beat, delay_per_beat))
                t2 = threading.Thread(target=self.smooth_move,
                    args=(CH_LEFT_ARM, mirror(ARM_FRONT), steps_per_beat, delay_per_beat))
                t1.start(); t2.start(); t1.join(); t2.join()
            elif phase == 4:
                # head left
                t = threading.Thread(target=self.smooth_move,
                    args=(CH_HEAD, HEAD_LEFT, steps_per_beat, delay_per_beat))
                t.start(); t.join()
            elif phase == 5:
                # both arms front
                self.smooth_move_arms(ARM_FRONT, steps=steps_per_beat, delay=delay_per_beat)
            elif phase == 6:
                # head right
                t = threading.Thread(target=self.smooth_move,
                    args=(CH_HEAD, HEAD_RIGHT, steps_per_beat, delay_per_beat))
                t.start(); t.join()
            elif phase == 7:
                # both arms down
                self.smooth_move_arms(ARM_DOWN, steps=steps_per_beat, delay=delay_per_beat)

            beat += 1

        # return to default
        self.smooth_move_arms(ARM_DOWN, steps=20, delay=0.02)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=15, delay=0.02)
        if VERBOSE: print("[Servos] dance end")

    # ── IDLE ANIMATIONS ───────────────────────────────────────────────────────

    def idle_head_left(self):
        if VERBOSE: print("[Servos] idle head left")
        self.smooth_move(CH_HEAD, HEAD_LEFT, steps=35, delay=0.04)
        time.sleep(8.0)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=35, delay=0.04)

    def idle_head_right(self):
        if VERBOSE: print("[Servos] idle head right")
        self.smooth_move(CH_HEAD, HEAD_RIGHT, steps=35, delay=0.04)
        time.sleep(8.0)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=35, delay=0.04)

    def idle_head_center(self):
        if VERBOSE: print("[Servos] idle head center")
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=35, delay=0.04)

    def idle_arm_wave(self):
        if VERBOSE: print("[Servos] idle arm wave")
        self.smooth_move_arms(ARM_RAISED, steps=40, delay=0.04)
        time.sleep(0.3)
        self.smooth_move_arms(ARM_DOWN, steps=40, delay=0.04)

    def idle_complex(self):
        if VERBOSE: print("[Servos] idle complex")
        self.smooth_move(CH_HEAD, HEAD_LEFT, steps=15, delay=0.03)
        time.sleep(0.3)
        self.smooth_move(CH_HEAD, HEAD_CENTER, steps=10, delay=0.02)
        time.sleep(0.2)
        for _ in range(3):
            t1 = threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, right(ARM_FRONT),  10, 0.02))
            t2 = threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(ARM_DOWN),  10, 0.02))
            t1.start(); t2.start(); t1.join(); t2.join()
            time.sleep(0.1)
            t1 = threading.Thread(target=self.smooth_move, args=(CH_RIGHT_ARM, right(ARM_DOWN),   10, 0.02))
            t2 = threading.Thread(target=self.smooth_move, args=(CH_LEFT_ARM,  mirror(ARM_FRONT), 10, 0.02))
            t1.start(); t2.start(); t1.join(); t2.join()
            time.sleep(0.1)
        self.smooth_move_arms(ARM_DOWN, steps=15, delay=0.02)

    def play_emotion(self, emotion):
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


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main(servo_queue=None):
    sc = ServoController()

    if servo_queue is None:
        print("Running standalone test...")
        time.sleep(1)
        sc.wake()
        time.sleep(1)
        sc.play_gesture("wave")
        time.sleep(1)
        sc.play_gesture("nod")
        time.sleep(1)
        sc.dance(duration=10.0)
        time.sleep(1)
        sc.rest()
        print("Done.")
        return

    print("Servo controller ready.")

    try:
        while True:
            if not servo_queue.empty():
                try:
                    state = servo_queue.get_nowait()
                    if VERBOSE: print(f"[Servos] received: {state}")
                    if state == "wake":               sc.wake()
                    elif state == "listen":           sc.listen()
                    elif state == "think":            sc.think()
                    elif state == "idle":             sc.rest()
                    elif state == "happy":            sc.happy()
                    elif state == "suspicious":       sc.suspicious()
                    elif state == "hostile":          sc.hostile()
                    elif state == "alarmed":          sc.alarmed()
                    elif state == "idle_head_left":   sc.idle_head_left()
                    elif state == "idle_head_right":  sc.idle_head_right()
                    elif state == "idle_head_center": sc.idle_head_center()
                    elif state == "idle_arm_wave":    sc.idle_arm_wave()
                    elif state == "idle_complex":     sc.idle_complex()
                    elif state == "dance":            sc.dance(duration=24.0)
                    elif state.startswith("emotion:"):
                        sc.play_emotion(state.split(":", 1)[1])
                    elif state.startswith("gesture:"):
                        sc.play_gesture(state.split(":", 1)[1])
                except:
                    pass
            else:
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nServos offline.")
        sc.rest()


if __name__ == "__main__":
    main()