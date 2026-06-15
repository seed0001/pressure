import sys
import os

# Add root folder to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
import pressure_engine as pe

def test_tts():
    print("Testing Edge TTS default voice...")
    pe.CONFIG["TTS_VOICE"] = "en-IE-EmilyNeural"
    audio_data, mime = server._speak_tts("Hello, this is a test of Emily voice.")
    print(f"Edge TTS Success! Mime: {mime}, Bytes: {len(audio_data)}")
    
    print("\nTesting LuxTTS voice...")
    pe.CONFIG["TTS_VOICE"] = "LuxTTS"
    audio_data, mime = server._speak_tts("Hello there, this is a test of the Lux Text-to-Speech system. We are verifying if the voice cloning generates correctly.")
    print(f"LuxTTS Success! Mime: {mime}, Bytes: {len(audio_data)}")

    print("\nTesting LuxTTS short input fallback to Edge...")
    # This is a very short text, which will fail in LuxTTS and fall back to Edge
    audio_data, mime = server._speak_tts("Yes.")
    print(f"Short input fallback Success! Mime: {mime}, Bytes: {len(audio_data)}")

if __name__ == "__main__":
    test_tts()
