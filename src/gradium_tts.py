import os
import json
import requests
import asyncio
import websockets
import base64

class GradiumTTS:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Adjust base URL if needed (EU vs US). Using EU as default based on doc example.
        self.base_url = "https://eu.api.gradium.ai/api" 
        # CORRECTION: Added /speech/ segment based on documentation
        self.ws_url = "wss://eu.api.gradium.ai/api/speech/tts"

    def clone_voice(self, audio_path: str, name: str) -> str:
        """
        Uploads a sample to clone a voice and returns the Voice UID.
        """
        url = f"{self.base_url}/voices/"
        
        try:
            with open(audio_path, 'rb') as f:
                files = {
                    'audio_file': (os.path.basename(audio_path), f, 'audio/wav')
                }
                data = {
                    'name': f"Clone-{name}",
                    'input_format': 'wav'
                }
                headers = {
                    'x-api-key': self.api_key
                }
                
                print(f"[Gradium] Cloning voice for {name}...")
                response = requests.post(url, headers=headers, files=files, data=data)
                
                if response.status_code in [200, 201]:
                    res_json = response.json()
                    uid = res_json.get('uid')
                    print(f"[Gradium] Voice created: {uid}")
                    return uid
                else:
                    print(f"[Gradium] Error cloning voice: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"[Gradium] Exception: {e}")
            return None

    async def generate_audio_async(self, text: str, voice_uid: str, output_path: str):
        """
        Connects to WebSocket, sends text, receives audio chunks, and saves to WAV.
        """
        try:
            extra_headers = {"x-api-key": self.api_key}
            
            async with websockets.connect(self.ws_url, additional_headers=extra_headers) as ws:
                # 1. Setup Message
                setup_msg = {
                    "type": "setup",
                    "model_name": "default",
                    "voice_id": voice_uid,
                    "output_format": "wav"
                }
                await ws.send(json.dumps(setup_msg))
                
                # Wait for 'ready'
                while True:
                    resp = await ws.recv()
                    data = json.loads(resp)
                    if data.get("type") == "ready":
                        print("[Gradium] WebSocket Ready.")
                        break
                    if data.get("type") == "error":
                        print(f"[Gradium] Setup Error: {data}")
                        return False, data
                
                # 2. Send Text
                text_msg = {
                    "type": "text",
                    "text": text
                }
                await ws.send(json.dumps(text_msg))
                
                # 3. Send End of Stream (to signal we are done sending text)
                eos_msg = {"type": "end_of_stream"}
                await ws.send(json.dumps(eos_msg))
                
                # 4. Receive Audio
                audio_chunks = []
                
                while True:
                    resp = await ws.recv()
                    data = json.loads(resp)
                    msg_type = data.get("type")
                    
                    if msg_type == "audio":
                        # Base64 decode
                        audio_bytes = base64.b64decode(data["audio"])
                        audio_chunks.append(audio_bytes)
                    
                    elif msg_type == "end_of_stream":
                        print("[Gradium] Stream finished.")
                        break
                        
                    elif msg_type == "error":
                        print(f"[Gradium] Stream Error: {data}")
                        return False, data
                
                # 5. Save to file
                if audio_chunks:
                    with open(output_path, "wb") as f:
                        for chunk in audio_chunks:
                            f.write(chunk)
                    print(f"[Gradium] Audio saved to {output_path}")
                    return True, None
                else:
                    print("[Gradium] No audio received.")
                    return False, {"type": "error", "message": "No audio received from TTS stream"}
                    
        except Exception as e:
            print(f"[Gradium] WebSocket Exception: {e}")
            return False, {"type": "exception", "message": str(e)}
