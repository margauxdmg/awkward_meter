import os
import time
import requests
import json
from typing import List, Dict, Any
from .utils import Segment

class PyannoteService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.pyannote.ai/v1"

    def _upload_file(self, file_path: str) -> str:
        """Uploads file to Pyannote via signed URL and returns the media key"""
        object_key = f"upload-{int(time.time())}"
        target_url = f"media://{object_key}"
        print(f"[Pyannote] Requesting upload URL for: {target_url}")
        
        # 1. Get Signed URL
        resp = requests.post(
            f"{self.base_url}/media/input",
            json={"url": target_url},
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        )
        
        if resp.status_code not in [200, 201]:
            raise Exception(f"Failed to get upload URL ({resp.status_code}): {resp.text}")
            
        presigned_url = resp.json()["url"]
        
        # 2. Upload File
        print(f"[Pyannote] Uploading {file_path}...")
        with open(file_path, "rb") as f:
            upload_resp = requests.put(
                presigned_url, 
                data=f,
                headers={"Content-Type": "application/octet-stream"}
            )
            if upload_resp.status_code != 200:
                raise Exception(f"Upload failed: {upload_resp.status_code}")
                
        return f"media://{object_key}"

    def _wait_for_job(self, job_id: str) -> Dict:
        """Polls for job completion"""
        print(f"[Pyannote] Waiting for job {job_id}...")
        while True:
            resp = requests.get(
                f"{self.base_url}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            data = resp.json()
            status = data["status"]
            
            if status == "succeeded":
                return data["output"]
            elif status in ["failed", "canceled"]:
                raise Exception(f"Job failed with status: {status}")
                
            time.sleep(2) # Poll every 2s

    def diarize(self, audio_path: str) -> List[Segment]:
        if not self.api_key:
             print("[Pyannote] No API Key provided.")
             return []

        try:
            # 1. Upload
            media_url = self._upload_file(audio_path)
            
            # 2. Start Job with TRANSCRIPTION enabled
            print("[Pyannote] Starting Diarization + Transcription job...")
            job_resp = requests.post(
                f"{self.base_url}/diarize",
                json={
                    "url": media_url,
                    "transcription": True # Key feature: Pyannote handles everything
                },
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            )
            
            if job_resp.status_code != 200:
                print(f"[Pyannote] Job creation failed: {job_resp.text}")
                return []
                
            job_id = job_resp.json()["jobId"]
            
            # 3. Wait for result
            result = self._wait_for_job(job_id)
            
            # 4. Parse Result
            # Look for transcription data
            segments = []
            
            if "turnLevelTranscription" in result:
                transcripts = result["turnLevelTranscription"]
                print(f"[Pyannote] Success! Found {len(transcripts)} transcribed turns.")
                
                for t in transcripts:
                    segments.append(Segment(
                        start=t["start"],
                        end=t["end"],
                        speaker=t["speaker"],
                        text=t["text"].strip(),
                        is_question=t["text"].strip().endswith('?')
                    ))
            
            elif "diarization" in result:
                print("[Pyannote] Warning: Transcription missing, falling back to diarization only.")
                for d in result["diarization"]:
                    segments.append(Segment(
                        start=d["start"],
                        end=d["end"],
                        speaker=d["speaker"],
                        text="[Unintelligible]",
                        is_question=False
                    ))
            
            return segments
            
        except Exception as e:
            print(f"[Pyannote] Error: {e}")
            return []

class AwkwardPipeline:
    def __init__(self, pyannote_key: str, gradium_key: str = None):
        self.service = PyannoteService(pyannote_key)
    
    def run(self, audio_path: str) -> List[Segment]:
        print(f"Starting analysis pipeline for: {audio_path}")
        if not os.path.exists(audio_path):
             print(f"[Error] File not found: {audio_path}")
             return []

        # Simple synchronous call
        return self.service.diarize(audio_path)
