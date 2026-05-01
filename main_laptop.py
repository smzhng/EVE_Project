#!/usr/bin/env python3
"""
main_laptop.py
--------------
Laptop version of EVE — runs voice pipeline with eye preview window.
Run: python3 main_laptop.py
"""
import os
os.environ['EVE_LAPTOP_MODE'] = '1'  # set before import

import eve_eyes

import tkinter as tk
from PIL import ImageTk, Image
import numpy as np
import threading
import time
import random

# ── EYE PREVIEW WINDOW ────────────────────────────────────────────────────────
SCALE = 4
FRAME_DELAY = eve_eyes.FRAME_DELAY
SCREEN_W    = eve_eyes.SCREEN_W
SCREEN_H    = eve_eyes.SCREEN_H
EYE_Y_OFFSET = eve_eyes.EYE_Y_OFFSET

class EyeWindow:
    def __init__(self, sclera, upper, lower):
        self.sclera = sclera
        self.upper  = upper
        self.lower  = lower
        self.eyes   = eve_eyes.EveEyes(sclera, upper, lower)

        self.root = tk.Tk()
        self.root.title("EVE Eyes")
        self.root.configure(bg='black')

        W = SCREEN_W * SCALE
        H = SCREEN_H * SCALE
        self.canvas = tk.Canvas(self.root, width=W*2+20, height=H,
                                bg='black', highlightthickness=0)
        self.canvas.pack()
        self.left_img  = self.canvas.create_image(0,      0, anchor='nw')
        self.right_img = self.canvas.create_image(W+20,   0, anchor='nw')

        self.root.bind('<space>', lambda e: self.eyes.set_combat_mode(not self.eyes.combat_mode))
        self.root.after(0, self.loop)

    def loop(self):
        now = time.time()

        # blink state machine (same as EveEyes.update but without show())
        if self.eyes.blink_state == 0 and now >= self.eyes.next_blink:
            self.eyes.blink_state = 1
            self.eyes.blink_start = now
            self.eyes.blink_dur   = random.uniform(0.036, 0.072)
            self.eyes.orig_dur    = self.eyes.blink_dur

        uT = 0
        lT = 0

        if self.eyes.blink_state > 0:
            elapsed = now - self.eyes.blink_start
            s = min(1.0, elapsed / self.eyes.blink_dur)
            s_int = int(s * 255)
            if self.eyes.blink_state == 2:
                s_int = 1 + s_int
            else:
                s_int = 256 - s_int
            uT = (0 * s_int + 254 * (257 - s_int)) // 256
            lT = (0 * s_int + 254 * (257 - s_int)) // 256

            if elapsed >= self.eyes.blink_dur:
                if self.eyes.blink_state == 1:
                    self.eyes.blink_state = 2
                    self.eyes.blink_start = now
                    self.eyes.blink_dur  *= 2
                else:
                    self.eyes.blink_state = 0
                    self.eyes.next_blink  = now + self.eyes.orig_dur * 3 + random.uniform(0, 4)

        frame_left  = eve_eyes.render_eye(self.sclera, self.upper, self.lower,
                                          uT, lT, self.eyes.combat_mode,
                                          y_offset=-EYE_Y_OFFSET, flip_v=True)
        frame_right = eve_eyes.render_eye(self.sclera, self.upper, self.lower,
                                          uT, lT, self.eyes.combat_mode,
                                          y_offset=-EYE_Y_OFFSET, flip_v=False)
        frame_right = frame_right[:, ::-1, :]

        left_pil  = Image.fromarray(frame_left).resize(
            (SCREEN_W*SCALE, SCREEN_H*SCALE), Image.NEAREST)
        right_pil = Image.fromarray(frame_right).resize(
            (SCREEN_W*SCALE, SCREEN_H*SCALE), Image.NEAREST)

        self.left_tk  = ImageTk.PhotoImage(left_pil)
        self.right_tk = ImageTk.PhotoImage(right_pil)
        self.canvas.itemconfig(self.left_img,  image=self.left_tk)
        self.canvas.itemconfig(self.right_img, image=self.right_tk)

        self.root.after(int(FRAME_DELAY * 1000), self.loop)

    def run(self):
        self.root.mainloop()


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading eye data...")
    sclera, upper, lower = eve_eyes.load_eye_data()

    # start voice pipeline in background thread
    import llm_model
    voice_thread = threading.Thread(target=llm_model.main, daemon=True)
    voice_thread.start()
    print("Voice pipeline started in background.")

    # run eye window on main thread (tkinter requires main thread)
    print("Starting eye preview. SPACE = toggle combat mode. Close window to quit.")
    window = EyeWindow(sclera, upper, lower)
    window.run()