#!/usr/bin/env python3
"""
eve_eyes.py
-----------
Animated eye display for EVE (Wall-E) using two Waveshare 1.5inch RGB OLED modules.
Eye graphics extracted directly from the original ShimmerNZ/EVE-2.0 project
(EveEye.h) — sclera texture + eyelid masks rendered faithfully.

Runs on Raspberry Pi 5 using SPI interface.

Wiring:
    Both displays share: VCC, GND, DIN (MOSI), CLK, DC, RST
    Display 1 CS  →  GPIO 8  (CE0, Pin 24)
    Display 2 CS  →  GPIO 7  (CE1, Pin 26)

Run standalone:
    sudo python3 eve_eyes.py

Run together with voice:
    sudo python3 main.py

Dependencies:
    sudo pip3 install pillow spidev lgpio --break-system-packages

Eye states (sent via queue from llm_model.py):
    closed  → eyes fully shut (startup + inactivity)
    wake    → plays opening animation then switches to idle
    listen  → eyes open, no blinking (recording speech)
    think   → eyes slightly squinted (LLM processing)
    idle    → eyes open with normal blinking, 30s inactivity timer
"""

import time
import numpy as np
import random
import os, re


# ── CONFIG ────────────────────────────────────────────────────────────────────
SCREEN_W  = 128
SCREEN_H  = 128

SCLERA_W = 200
SCLERA_H = 200

EYE_Y_OFFSET = 4

SCLERA_X = (SCLERA_W - SCREEN_W) // 2
SCLERA_Y = (SCLERA_H - SCREEN_H) // 2

PIN_DC  = 25
PIN_RST = 27

BLINK_INTERVAL_MIN  = 3.0
BLINK_INTERVAL_MAX  = 7.0
FRAME_DELAY         = 0.04
INACTIVITY_TIMEOUT  = 30.0   # seconds before eyes close after last interaction

LAPTOP_MODE = os.environ.get('EVE_LAPTOP_MODE') == '1'
if not LAPTOP_MODE:
    import lgpio
    import spidev
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_DC)
    lgpio.gpio_claim_output(h, PIN_RST)
    spi1 = spidev.SpiDev()
    spi1.open(0, 0)
    spi1.max_speed_hz = 40000000
    spi1.mode = 0
    spi2 = spidev.SpiDev()
    spi2.open(0, 1)
    spi2.max_speed_hz = 40000000
    spi2.mode = 0


# ── LOAD EYE DATA FROM EveEye.h ───────────────────────────────────────────────
def load_eye_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    h_file = os.path.join(script_dir, 'EveEye.h')

    if not os.path.exists(h_file):
        raise FileNotFoundError(
            f"EveEye.h not found at {h_file}\n"
            "Please place EveEye.h in the same folder as eve_eyes.py"
        )

    with open(h_file, 'r') as f:
        content = f.read()

    end = content.find('iris[')
    hex16 = re.findall(r'0x([0-9A-Fa-f]{4})', content[:end])
    def rgb565(v):
        v = int(v, 16)
        return ((v >> 11) & 0x1F) << 3, ((v >> 5) & 0x3F) << 2, (v & 0x1F) << 3
    sclera_pixels = [rgb565(h) for h in hex16[:SCLERA_W * SCLERA_H]]
    sclera = np.array(sclera_pixels, dtype=np.uint8).reshape(SCLERA_H, SCLERA_W, 3)

    def extract_uint8_array(content, name):
        idx = content.find(f'const uint8_t {name}[SCREEN_HEIGHT][SCREEN_WIDTH]')
        if idx == -1:
            return None
        bs = content.find('{', idx)
        be = content.find('};', bs)
        vals = re.findall(r'0x([0-9A-Fa-f]{2})', content[bs:be])
        return np.array([int(v, 16) for v in vals[:SCREEN_W * SCREEN_H]],
                        dtype=np.uint8).reshape(SCREEN_H, SCREEN_W)

    upper = extract_uint8_array(content, 'upper')
    lower = extract_uint8_array(content, 'lower')

    print(f"Eye data loaded: sclera {sclera.shape}, upper {upper.shape}, lower {lower.shape}")
    return sclera, upper, lower


# ── DISPLAY DRIVER ────────────────────────────────────────────────────────────
def reset_display():
    lgpio.gpio_write(h, PIN_RST, 1); time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 0); time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 1); time.sleep(0.1)

def send_command(spi, cmd):
    lgpio.gpio_write(h, PIN_DC, 0)
    spi.writebytes([cmd])

def send_data(spi, data):
    lgpio.gpio_write(h, PIN_DC, 1)
    chunk = 4096
    for i in range(0, len(data), chunk):
        spi.writebytes(data[i:i+chunk])

def init_display(spi):
    send_command(spi, 0xFD); send_data(spi, [0x12])
    send_command(spi, 0xFD); send_data(spi, [0xB1])
    send_command(spi, 0xAE)
    send_command(spi, 0xB3); send_data(spi, [0xF1])
    send_command(spi, 0xCA); send_data(spi, [0x7F])
    send_command(spi, 0xA0); send_data(spi, [0x74])
    send_command(spi, 0x15); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0x75); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0xA1); send_data(spi, [0x00])
    send_command(spi, 0xA2); send_data(spi, [0x00])
    send_command(spi, 0xB5); send_data(spi, [0x00])
    send_command(spi, 0xAB); send_data(spi, [0x01])
    send_command(spi, 0xB1); send_data(spi, [0x32])
    send_command(spi, 0xBE); send_data(spi, [0x05])
    send_command(spi, 0xA6)
    send_command(spi, 0xC1); send_data(spi, [0xC8, 0x80, 0xC8])
    send_command(spi, 0xC7); send_data(spi, [0x0F])
    send_command(spi, 0xB4); send_data(spi, [0xA0, 0xB5, 0x55])
    send_command(spi, 0xB6); send_data(spi, [0x01])
    send_command(spi, 0xAF)

def show(spi, img):
    if LAPTOP_MODE:
        return
    send_command(spi, 0x15); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0x75); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0x5C)
    r = img[:,:,0].astype(np.uint16)
    g = img[:,:,1].astype(np.uint16)
    b = img[:,:,2].astype(np.uint16)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    high = (rgb565 >> 8).astype(np.uint8).flatten().tolist()
    low  = (rgb565 & 0xFF).astype(np.uint8).flatten().tolist()
    data = [val for pair in zip(high, low) for val in pair]
    send_data(spi, data)


# ── EYE RENDERER ──────────────────────────────────────────────────────────────
def render_eye(sclera, upper, lower, uT, lT, combat_mode=False, y_offset=0, flip_v=False):
    sclera_crop = sclera[SCLERA_Y:SCLERA_Y+SCREEN_H, SCLERA_X:SCLERA_X+SCREEN_W].copy()

    if flip_v:
        sclera_crop = sclera_crop[::-1, :, :]

    if y_offset != 0:
        upper = np.roll(upper, y_offset, axis=0)
        lower = np.roll(lower, y_offset, axis=0)

    eyelid_mask = (upper <= uT) | (lower <= lT)
    result = sclera_crop.copy()
    result[eyelid_mask] = [0, 0, 0]

    if combat_mode:
        b_dominant = (result[:,:,2] > result[:,:,0]) & (result[:,:,2] > 50)
        r_ch = result[:,:,2].copy()
        result[b_dominant, 0] = r_ch[b_dominant]
        result[b_dominant, 2] = 0
        result[b_dominant, 1] = (result[b_dominant,1] * 0.3).astype(np.uint8)

    return result


# ── EYE CONTROLLER ────────────────────────────────────────────────────────────
class EveEyes:
    def __init__(self, sclera, upper, lower):
        self.sclera      = sclera
        self.upper       = upper
        self.lower       = lower
        self.combat_mode = False
        self.blink_state = 0
        self.blink_start = 0
        self.blink_dur   = 0
        self.next_blink  = time.time() + random.uniform(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX)
        self.state       = "closed"   # start closed, open on first wake word
        self.last_active = None       # timestamp of last interaction

    def set_state(self, state):
        """Called when voice pipeline sends a new eye state."""
        self.state = state
        if state in ("wake", "listen", "think", "idle"):
            self.last_active = time.time()
        if state == "wake":
            self.blink_state = 0
            print("[Eyes] state → wake")
        elif state == "listen":
            self.blink_state = 0
            print("[Eyes] state → listen")
        elif state == "think":
            self.blink_state = 0
            print("[Eyes] state → think")
        elif state == "idle":
            self.next_blink = time.time() + random.uniform(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX)
            print("[Eyes] state → idle")
        elif state == "closed":
            self.blink_state = 0
            print("[Eyes] state → closed")

    def _show_frame(self, uT, lT):
        """Render and display one frame."""
        # left display is flipped — swap upper/lower so animation appears symmetric
        frame_left  = render_eye(self.sclera, self.upper, self.lower, lT, uT, self.combat_mode, y_offset=-EYE_Y_OFFSET, flip_v=True)
        frame_right = render_eye(self.sclera, self.upper, self.lower, uT, lT, self.combat_mode, y_offset=-EYE_Y_OFFSET, flip_v=False)
        show(spi1, frame_left)
        show(spi2, frame_right[:, ::-1, :])

    def _play_open_animation(self):
        """Eyes open from closed — fade in then double blink."""
        # fade open
        for i in range(11):
            uT = int((1.0 - i / 10.0) * 254)
            self._show_frame(uT, 0)
            time.sleep(0.06)

        # double blink
        for _ in range(2):
            for uT in [0, 254, 0]:
                self._show_frame(uT, 0)
                time.sleep(0.08)

    def update(self, eye_queue=None):
        now = time.time()

        # check for new state — only read one per frame
        if eye_queue is not None and not eye_queue.empty():
            try:
                new_state = eye_queue.get_nowait()
                self.set_state(new_state)
            except:
                pass

        # inactivity timeout — close eyes after 30s of idle
        if self.state == "idle" and self.last_active is not None:
            if now - self.last_active > INACTIVITY_TIMEOUT:
                print("[Eyes] inactivity timeout → closed")
                self.state = "closed"
                self.blink_state = 0

        # ── State rendering ───────────────────────────────────────────────────
        if self.state == "closed":
            # eyes fully shut
            self._show_frame(254, 254)
            time.sleep(FRAME_DELAY)

        elif self.state == "wake":
            # play opening animation then go to idle
            self._play_open_animation()
            self.state = "idle"
            self.last_active = time.time()
            self.next_blink  = time.time() + random.uniform(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX)

        elif self.state == "listen":
            # eyes open, attentive
            self._show_frame(0, 0)
            time.sleep(FRAME_DELAY)

        elif self.state == "think":
            # eyes slightly squinted
            self._show_frame(40, 40)
            time.sleep(FRAME_DELAY)

        else:
            # idle — normal blinking
            uT = 0
            lT = 0

            if self.blink_state == 0 and now >= self.next_blink:
                self.blink_state = 1
                self.blink_start = now
                self.blink_dur   = random.uniform(0.036, 0.072)
                self.orig_dur    = self.blink_dur

            if self.blink_state > 0:
                elapsed = now - self.blink_start
                s       = min(1.0, elapsed / self.blink_dur)
                s_int   = int(s * 255)

                if self.blink_state == 2:
                    s_int = 1 + s_int
                else:
                    s_int = 256 - s_int

                uT = (0 * s_int + 254 * (257 - s_int)) // 256
                lT = uT

                if elapsed >= self.blink_dur:
                    if self.blink_state == 1:
                        self.blink_state = 2
                        self.blink_start = now
                        self.blink_dur  *= 2
                    else:
                        self.blink_state = 0
                        self.next_blink  = now + self.orig_dur * 3 + random.uniform(0, 4)

            self._show_frame(uT, lT)
            time.sleep(FRAME_DELAY)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main(eye_queue=None):
    print("Loading eye data from EveEye.h...")
    sclera, upper, lower = load_eye_data()

    if not LAPTOP_MODE:
        print("Initializing displays...")
        reset_display()
        init_display(spi1)
        init_display(spi2)
        print("Displays initialized.")

    eyes = EveEyes(sclera, upper, lower)
    print("EVE eyes online. Waiting for wake word...")

    try:
        while True:
            eyes.update(eye_queue)

    except KeyboardInterrupt:
        print("\nShutting down eyes...")
        black = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
        if not LAPTOP_MODE:
            show(spi1, black)
            show(spi2, black)
            spi1.close()
            spi2.close()
            lgpio.gpiochip_close(h)
        print("EVE eyes offline.")


# ── RUN STANDALONE ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()