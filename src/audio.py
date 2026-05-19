import os
import requests
from config import LEMONADE_URL

def generate_speech(text, voice="af_sarah"):
    """
    Generates an audio file from text using the local Lemonade Kokoro TTS model
    and plays it using mpv.
    """
    try:
        print(f"🎙️ Generating speech: '{text}' using voice {voice}...")
        url = f"{LEMONADE_URL}/audio/speech"
        headers = {"Authorization": "Bearer lemonade"}
        data = {
            "model": "kokoro-v1",
            "input": text,
            "voice": voice,
            "response_format": "wav"
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            with open("alert.wav", "wb") as f:
                f.write(response.content)
            print("✅ Audio saved to alert.wav")
            # Triggers local audio playback
            os.system("mpv alert.wav")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"⚠️ TTS request failed: {e}")