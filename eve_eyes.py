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
EYE_H = 55   # eye height
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
    lgpio.gpio_write(h, PIN_RST, 1)
    time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 0)
    time.sleep(0.1)
    lgpio.gpio_write(h, PIN_RST, 1)
    time.sleep(0.1)


def send_command(spi, cmd):
    """Send a command byte to a display."""
    lgpio.gpio_write(h, PIN_DC, 0)
    spi.writebytes([cmd])


def send_data(spi, data):
    """Send data bytes to a display."""
    lgpio.gpio_write(h, PIN_DC, 1)
    if isinstance(data, int):
        spi.writebytes([data])
    else:
        # send in chunks to avoid SPI buffer overflow
        chunk_size = 4096
        for i in range(0, len(data), chunk_size):
            spi.writebytes(data[i:i + chunk_size])


def init_display(spi):
    """Initialize SSD1351 OLED display."""
    send_command(spi, 0xFD)  # command lock
    send_data(spi, 0x12)
    send_command(spi, 0xFD)
    send_data(spi, 0xB1)
    send_command(spi, 0xAE)  # display off
    send_command(spi, 0xB3)  # clock divider
    send_data(spi, 0xF1)
    send_command(spi, 0xCA)  # mux ratio
    send_data(spi, 0x7F)
    send_command(spi, 0xA0)  # remap and color depth
    send_data(spi, 0x74)
    send_command(spi, 0x15)  # set column
    send_data(spi, 0x00)
    send_data(spi, 0x7F)
    send_command(spi, 0x75)  # set row
    send_data(spi, 0x00)
    send_data(spi, 0x7F)
    send_command(spi, 0xA1)  # start line
    send_data(spi, 0x00)
    send_command(spi, 0xA2)  # display offset
    send_data(spi, 0x00)
    send_command(spi, 0xB5)  # GPIO
    send_data(spi, 0x00)
    send_command(spi, 0xAB)  # function select
    send_data(spi, 0x01)
    send_command(spi, 0xB1)  # precharge
    send_data(spi, 0x32)
    send_command(spi, 0xBE)  # VCOMH voltage
    send_data(spi, 0x05)
    send_command(spi, 0xA6)  # normal display
    send_command(spi, 0xC1)  # contrast RGB
    send_data(spi, 0xC8)
    send_data(spi, 0x80)
    send_data(spi, 0xC8)
    send_command(spi, 0xC7)  # master contrast
    send_data(spi, 0x0F)
    send_command(spi, 0xB4)  # set VSL
    send_data(spi, 0xA0)
    send_data(spi, 0xB5)
    send_data(spi, 0x55)
    send_command(spi, 0xB6)  # precharge 2
    send_data(spi, 0x01)
    send_command(spi, 0xAF)  # display on


def image_to_bytes(img):
    """Convert PIL image to 16-bit RGB565 byte list for SSD1351."""
    pixels = list(img.getdata())
    data = []
    for r, g, b in pixels:
        # convert RGB888 to RGB565
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        data.append((rgb565 >> 8) & 0xFF)
        data.append(rgb565 & 0xFF)
    return data


def show_image(spi, img):
    """Send a PIL image to the display."""
    send_command(spi, 0x15)   # set column address
    send_data(spi, 0x00)
    send_data(spi, 0x7F)
    send_command(spi, 0x75)   # set row address
    send_data(spi, 0x00)
    send_data(spi, 0x7F)
    send_command(spi, 0x5C)   # write RAM
    data = image_to_bytes(img)
    send_data(spi, data)


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
        inner_color = COLOR_EYE_GLOW_COMBAT
        outer_color = COLOR_EYE_COMBAT
    else:
        inner_color = COLOR_EYE_GLOW
        outer_color = COLOR_EYE_NORMAL

    # apply pulse brightness
    outer_color = tuple(int(c * (0.6 + 0.4 * pulse)) for c in outer_color)
    inner_color = tuple(int(c * (0.7 + 0.3 * pulse)) for c in inner_color)

    # apply blink — squish eye vertically
    blink_h = max(2, int(EYE_H * blink_amount))

    # draw outer glow layers (larger ovals getting dimmer outward)
    for i in range(4, 0, -1):
        glow_factor = i / 4.0 * 0.3
        glow_color  = tuple(int(c * glow_factor) for c in outer_color)
        glow_w = EYE_W + i * 6
        glow_h = blink_h + i * 4
        draw.ellipse([
            EYE_CX - glow_w // 2,
            EYE_CY - glow_h // 2,
            EYE_CX + glow_w // 2,
            EYE_CY + glow_h // 2
        ], fill=glow_color)

    # draw main eye oval
    draw.ellipse([
        EYE_CX - EYE_W // 2,
        EYE_CY - blink_h // 2,
        EYE_CX + EYE_W // 2,
        EYE_CY + blink_h // 2
    ], fill=outer_color)

    # draw bright inner highlight (smaller oval in center)
    inner_w = int(EYE_W * 0.55)
    inner_h = int(blink_h * 0.55)
    draw.ellipse([
        EYE_CX - inner_w // 2,
        EYE_CY - inner_h // 2,
        EYE_CX + inner_w // 2,
        EYE_CY + inner_h // 2
    ], fill=inner_color)

    return img


def send_to_both(img):
    """Send the same image to both displays simultaneously."""
    show_image(spi1, img)
    show_image(spi2, img)


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
            self.pulse     = 1.0
            self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse     = 0.0
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
        send_to_both(img)
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
        send_to_both(img)
        time.sleep(0.06)

    # quick double blink
    for _ in range(2):
        for amount in [1.0, 0.0, 1.0]:
            img = draw_eye(blink_amount=amount, combat_mode=False, pulse=1.0)
            send_to_both(img)
            time.sleep(0.08)

    print("EVE online.")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
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
    print("Type 'c' + Enter to toggle combat mode (in another terminal).")

    try:
        while True:
            eyes.update()

    except KeyboardInterrupt:
        print("\nShutting down...")
        # clear both displays to black on exit
        black = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
        send_to_both(black)
        spi1.close()
        spi2.close()
        lgpio.gpiochip_close(h)
        print("EVE eyes offline.")