#!/usr/bin/env python3
"""
eve_eyes.py
-----------
Animated eye display for EVE (Wall-E) using two Waveshare 1.5inch RGB OLED modules.
Runs on Raspberry Pi 5 using SPI interface.

Wiring:
    Both displays share: VCC, GND, DIN (MOSI), CLK, DC, RST
    Display 1 CS  →  GPIO 8  (CE0, Pin 24)
    Display 2 CS  →  GPIO 7  (CE1, Pin 26)

Run standalone:
    sudo python3 eve_eyes.py

Run together with voice:
    sudo python3 main.py

Install dependencies:
    sudo pip3 install pillow spidev lgpio --break-system-packages
"""

import time
import math
import random
import lgpio
import spidev
from PIL import Image, ImageDraw

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCREEN_WIDTH  = 128
SCREEN_HEIGHT = 128

# GPIO pin numbers (BCM)
PIN_DC  = 25
PIN_RST = 27

# Eye colors
COLOR_BG            = (0,   0,   0  )   # black background
COLOR_EYE_NORMAL    = (0,   180, 255)   # Eve's signature blue
COLOR_EYE_GLOW      = (100, 220, 255)   # brighter center glow
COLOR_EYE_COMBAT    = (255, 30,  30 )   # red for combat mode
COLOR_EYE_GLOW_COMBAT = (255, 120, 120) # red glow

# Eye shape (oval dimensions)
EYE_W = 90   # eye width
EYE_CX = SCREEN_WIDTH  // 2   # center x
EYE_CY = SCREEN_HEIGHT // 2   # center y

# Animation settings
BLINK_INTERVAL_MIN = 3.0   # seconds between blinks (min)
BLINK_INTERVAL_MAX = 7.0   # seconds between blinks (max)
BLINK_SPEED        = 0.04  # seconds per blink frame
PULSE_SPEED        = 0.05  # glow pulse speed

# ── SPI + GPIO SETUP ──────────────────────────────────────────────────────────
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, PIN_DC)
lgpio.gpio_claim_output(h, PIN_RST)

spi1 = spidev.SpiDev()
spi1.open(0, 0)   # display 1 — CE0
spi1.max_speed_hz = 40000000
spi1.mode = 0

spi2 = spidev.SpiDev()
spi2.open(0, 1)   # display 2 — CE1
spi2.max_speed_hz = 40000000
spi2.mode = 0


# ── DISPLAY DRIVER ────────────────────────────────────────────────────────────
def reset_display():
    """Hardware reset both displays simultaneously."""
    lgpio.gpio_write(h, PIN_RST, 1); time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 0); time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 1); time.sleep(0.1)

def send_command(spi, cmd):
    """Send a command byte to a display."""
    lgpio.gpio_write(h, PIN_DC, 0)
    spi.writebytes([cmd])


def send_data(spi, data):
    """Send data bytes to a display."""
    lgpio.gpio_write(h, PIN_DC, 1)
    chunk = 4096
    for i in range(0, len(data), chunk):
        spi.writebytes(data[i:i+chunk])


def init_display(spi):
    """Initialize SSD1351 OLED display."""
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
    send_command(spi, 0x15); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0x75); send_data(spi, [0x00, 0x7F])
    send_command(spi, 0x5C)
    pixels = list(img.getdata())
    data = []
    for r, g, b in pixels:
        rgb = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        data += [(rgb >> 8) & 0xFF, rgb & 0xFF]
    send_data(spi, data)

def show_both(img):
    show(spi1, img)
    show(spi2, img)


# ── EYE DRAWING ───────────────────────────────────────────────────────────────
def draw_eye(blink_amount=1.0, combat_mode=False, pulse=1.0):
    """
    Draw Eve's eye on a PIL image.

    blink_amount: 1.0 = fully open, 0.0 = fully closed
    combat_mode:  False = blue, True = red
    pulse:        0.0 to 1.0, controls glow brightness

    Returns a PIL Image ready to send to display.
    """
    img  = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # pick colors based on mode
    if combat_mode:
        core_color = (255, 255, 200)
        mid_color  = (255, 80,  40 )
        glow_color = (180, 20,  10 )
    else:
        core_color = (200, 240, 255)
        mid_color  = (40,  160, 255)
        glow_color = (0,   60,  180)

    def pulse_color(c):
        return tuple(int(x * (0.7 + 0.3 * pulse)) for x in c)

    core_color = pulse_color(core_color)
    mid_color  = pulse_color(mid_color)
    glow_color = pulse_color(glow_color)

    EYE_H = max(1, int(blink_amount * 100))
    cx    = SCREEN_WIDTH  // 2
    cy    = SCREEN_HEIGHT // 2

    # draw outer glow layers (larger ovals getting dimmer outward)
    for i in range(6, 0, -1):
        alpha_factor = i / 6.0 * 0.25
        g = tuple(int(x * alpha_factor) for x in glow_color)
        w = EYE_W + i * 5
        h_val = max(1, EYE_H + i * 3)
        draw.ellipse([cx - w//2, cy - h_val//2, cx + w//2, cy + h_val//2], fill=g)

    # main eye body
    draw.ellipse([cx - EYE_W//2, cy - EYE_H//2,
                  cx + EYE_W//2, cy + EYE_H//2], fill=mid_color)

    # bright inner core
    core_w = int(EYE_W * 0.75)
    core_h = max(1, int(EYE_H * 0.35))
    draw.ellipse([cx - core_w//2, cy - core_h//2,
                  cx + core_w//2, cy + core_h//2], fill=core_color)

    # white hotspot
    hot_w = int(EYE_W * 0.3)
    hot_h = max(1, int(EYE_H * 0.15))
    draw.ellipse([cx - hot_w//2, cy - hot_h//2,
                  cx + hot_w//2, cy + hot_h//2], fill=(255, 255, 255))

    return img

# ── ANIMATION STATES ──────────────────────────────────────────────────────────
class EveEyes:
    def __init__(self):
        self.combat_mode     = False
        self.pulse           = 0.0
        self.pulse_dir       = 1
        self.blink_amount    = 1.0
        self.is_blinking     = False
        self.blink_phase     = 0   # 0=closing 1=opening
        self.next_blink_time = time.time() + random.uniform(
            BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX
        )

    def set_combat_mode(self, active):
        """Switch between normal blue and combat red."""
        self.combat_mode = active
        print(f"Eve eyes: {'COMBAT MODE' if active else 'normal mode'}")

    def update(self):
        """Update animation state and push frame to displays."""

        # ── pulse glow ────────────────────────────────────────────────────────
        self.pulse += PULSE_SPEED * self.pulse_dir
        if self.pulse >= 1.0:
            self.pulse = 1.0; self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse = 0.0
            self.pulse_dir = 1

        # ── blink logic ───────────────────────────────────────────────────────
        now = time.time()
        if not self.is_blinking and now >= self.next_blink_time:
            self.is_blinking = True
            self.blink_phase = 0   # start closing

        if self.is_blinking:
            if self.blink_phase == 0:
                # closing
                self.blink_amount -= 0.2
                if self.blink_amount <= 0.0:
                    self.blink_amount = 0.0
                    self.blink_phase  = 1
            else:
                # opening
                self.blink_amount += 0.2
                if self.blink_amount >= 1.0:
                    self.blink_amount    = 1.0
                    self.is_blinking     = False
                    self.next_blink_time = now + random.uniform(
                        BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX
                    )

        # ── draw and send frame ───────────────────────────────────────────────
        img = draw_eye(
            blink_amount=self.blink_amount,
            combat_mode=self.combat_mode,
            pulse=self.pulse
        )
        show_both(img)
        time.sleep(BLINK_SPEED)


# ── STARTUP ANIMATION ─────────────────────────────────────────────────────────
def startup_animation():
    """
    Eve's boot sequence — eye opens from a thin line to full size.
    """
    print("EVE boot sequence...")

    # fade in from black
    for i in range(0, 11):
        pulse = i / 10.0
        img   = draw_eye(blink_amount=pulse, combat_mode=False, pulse=pulse)
        show_both(img)
        time.sleep(0.06)

    # quick double blink
    for _ in range(2):
        for amount in [1.0, 0.0, 1.0]:
            img = draw_eye(blink_amount=amount, combat_mode=False, pulse=1.0)
            show_both(img)
            time.sleep(0.08)

    print("EVE eyes online.")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("Initializing displays...")
    reset_display()
    init_display(spi1)
    init_display(spi2)
    print("Displays initialized.")

    # run startup animation
    startup_animation()

    # create eye controller
    eyes = EveEyes()

    print("Running. Press Ctrl+C to stop.")

    try:
        while True:
            eyes.update()

    except KeyboardInterrupt:
        print("\nShutting down...")
        # clear both displays to black on exit
        black = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
        show_both(black)
        spi1.close()
        spi2.close()
        lgpio.gpiochip_close(h)
        print("EVE eyes offline.")

# ── RUN STANDALONE ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()