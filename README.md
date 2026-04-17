# EVE Project 🤖
** EVE from Wall-E on Raspberry Pi**

This project transforms a Raspberry Pi into a fully interactive real-life clone of EVE from the movie Wall-E, with personality that matches the iconic character. This project uses a LLM to generate responses to user input and converts phrases into audible speech, while simultaneoulsy displaying face animations.

## ✨ Features

* **Locally Powered Intelligence**: Powered by the phi4-mini LLM from **Ollama** and **Wispr Flow** for speech-to-text. No API fees or cloud data required.
* **Reactive Faces**: The Pi updates the character's face expressions based on its state (Listening, Thinking, Speaking, Idle)
* **Text-to-Speech**: Uses **Piper TTS** for low-latency, high quality voice generation on the Pi.
* **Vision Capable**: Can "see" and respond to the world using a Raspberry Pi Camera Module 3 and the **Moondream** vision module

## Hardware 🛠️
* ** Raspberry Pi 5 4GB RAM**
* USB Microphone & Speaker
* Two Oled Screens
* Raspberry Pi Camera Module 3

## 📁 Project Structure
```text
EVE_Project/
├── tts                        # Speech engine assets
│   └── speech_outputs         # Generated .wav files for EVE's voice
├── .gitignore                 # Tells Git which files to ignore
├── llm_model.ipynb            # Jupyter Notebook for brain & personality training
└── README                     # Project documentation and setup guide
```

---
