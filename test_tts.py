
import asyncio
from livekit.agents import tts
from livekit.plugins import elevenlabs
import os
from dotenv import load_dotenv
from pathlib import Path

# Load env from backend
backend_env = Path(__file__).parent.parent / "backend" / ".env"
load_dotenv(backend_env)

async def test_elevenlabs():
    api_key = os.getenv("ELEVENLABS_TTS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    model = os.getenv("ELEVENLABS_MODEL")
    
    print(f"Testing ElevenLabs with:")
    print(f"  API Key: {api_key[:5]}...")
    print(f"  Voice ID: {voice_id}")
    print(f"  Model: {model}")
    
    # Try with default auto_mode=True (uses blingfire)
    try:
        plugin = elevenlabs.TTS(api_key=api_key, voice_id=voice_id, model=model)
        print("Successfully created elevenlabs.TTS with auto_mode=True")
        
        # Test sentence tokenization
        from livekit.agents import tts
        tokenizer = tts.SentenceTokenizer.default()
        print(f"Default SentenceTokenizer: {type(tokenizer).__name__}")
        
    except Exception as e:
        print(f"Error creating plugin: {e}")

if __name__ == "__main__":
    asyncio.run(test_elevenlabs())
