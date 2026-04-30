import asyncio
import os
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()
async def test():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options={"api_version": "v1beta"})
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Orus"))),
    )
    async with client.aio.live.connect(model="models/gemini-3.1-flash-live-preview", config=config) as session:
        print("Connected!")
        # Try sending text using the correct recommended structure
        await session.send_client_content("Hola, dime tu nombre.")
        print("Sent!")
        async for res in session.receive():
            if res.data:
                print(f"Received audio bytes: {len(res.data)}")
            if res.text:
                print(f"Received text: {res.text}")
            if res.server_content and res.server_content.turn_complete:
                print("Turn complete")
                break

asyncio.run(test())
