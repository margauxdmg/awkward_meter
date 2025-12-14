import os
import shutil
import wave
import json
import uuid
from typing import Dict
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import openai

from src.pipeline import AwkwardPipeline
from src.analysis import AwkwardnessMeter
from src.utils import Segment
from src.gradium_tts import GradiumTTS

load_dotenv()

app = FastAPI()

# Directories
UPLOAD_DIR = "temp_uploads"
SAMPLES_DIR = "web/static/samples"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SAMPLES_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# Initialize Pipeline
pyannote_key = os.getenv("PYANNOTE_API_KEY")
gradium_key = os.getenv("GRADIUM_API_KEY")

pipeline = AwkwardPipeline(pyannote_key=pyannote_key, gradium_key=gradium_key) 

# Gradium TTS Setup
gradium_tts = GradiumTTS(gradium_key) if gradium_key else None

# OpenAI Setup
openai.api_key = os.getenv("OPENAI_API_KEY")

# Store intermediate results in memory
SESSION_STORE = {}

def extract_speaker_samples(audio_path: str, segments: list, job_id: str):
    """
    Extracts a 3-5 second sample for each speaker from the WAV file.
    """
    wav_path = os.path.join(UPLOAD_DIR, f"{job_id}_converted.wav")
    if not os.path.exists(wav_path):
        os.system(f"afconvert -f WAVE -d LEI16@24000 -c 1 '{audio_path}' '{wav_path}'")

    samples_map = {}
    found_speakers = set(s.speaker for s in segments)
    
    with wave.open(wav_path, 'rb') as source:
        framerate = source.getframerate()
        
        for spk in found_speakers:
            candidates = [s for s in segments if s.speaker == spk and (s.end - s.start) > 2.0]
            if not candidates:
                candidates = [s for s in segments if s.speaker == spk]
            
            if candidates:
                seg = candidates[0]
                start_frame = int(seg.start * framerate)
                duration_frames = int(min(5.0, seg.end - seg.start) * framerate)
                
                source.setpos(start_frame)
                audio_data = source.readframes(duration_frames)
                
                sample_filename = f"{job_id}_{spk}.wav"
                sample_path = os.path.join(SAMPLES_DIR, sample_filename)
                
                with wave.open(sample_path, 'wb') as dest:
                    dest.setnchannels(source.getnchannels())
                    dest.setsampwidth(source.getsampwidth())
                    dest.setframerate(framerate)
                    dest.writeframes(audio_data)
                
                samples_map[spk] = f"/static/samples/{sample_filename}"
    
    if os.path.exists(wav_path):
        os.remove(wav_path)
        
    return samples_map

def generate_ai_insights(transcript_text: str, detailed_metrics: dict, main_user: str):
    """
    Calls OpenAI to act as a Date Doctor and analyze the 4 key pillars.
    """
    if not openai.api_key:
        return {
            "analysis": {
                "dominance": "AI Offline.",
                "interruptions": "AI Offline.",
                "silence": "AI Offline.",
                "quality": "AI Offline."
            },
            "action_plan": ["Please configure OpenAI API Key."]
        }

    json_template = """
    {
        "analysis": {
            "dominance": "Critique the balance. Address user as YOU. Use strong language if unbalanced (e.g., 'YOU suffocated the conversation').",
            "interruptions": "Critique interruptions. Who was rude?",
            "silence": "Critique the vibe. Was it awkward? Dead air?",
            "quality": "Critique engagement. Did YOU ask real questions or just fake interest?"
        },
        "action_plan": [
            {
                "speaker": "Name of Speaker (likely YOU)", 
                "context": "Briefly describe what happened just before",
                "display_text": "VERY SPECIFIC advice. Don't say 'Ask about her'. Say: 'You should have asked: What kind of movies do you like?'. Give the actual phrasing to use.",
                "audio_trigger_speaker": "Name of the OTHER person who spoke before",
                "audio_trigger_text": "The exact last sentence the OTHER person said",
                "audio_response_text": "The EXACT new sentence YOU should say (just the sentence, no 'You should say')"
            }
        ]
    }
    """

    prompt = f"""
    You are an expert Communication Coach and Date Doctor.
    You are speaking directly to **{main_user}**. 
    Address {main_user} as **"YOU"**. Refer to the other person by their name.
    
    Analyze this conversation based on 4 pillars. BE BRUTALLY HONEST with {main_user}.
    If the date is bad, SAY IT. If YOU ({main_user}) acted like a narcissist, CALL IT OUT.
    
    1. Dominance. >60% for YOU is a RED FLAG. Did YOU suffocate the conversation?
    2. Interruptions. Did YOU cut them off? Or were YOU too passive?
    3. Silence. Was it awkward? Did YOU fail to fill the gaps or did YOU create them?
    4. Response Quality. Did YOU ask real questions or just fake interest? Did YOU give one-word answers?

    FOR THE ACTION PLAN:
    Identify 3 critical moments where {main_user} failed.
    For each moment, script a "Replay":
    1. **Context**: What just happened.
    2. **Display Text**: The COACHING ADVICE. **CRITICAL**: Do NOT be vague. 
       - BAD: "Ask about her interests."
       - GOOD: "You rambled about your job. Stop. Instead, ask: 'What is your favorite travel memory?'"
       - The user needs to know EXACTLY what to change in their behavior.
    3. **Audio Trigger**: The last thing the other person said.
    4. **Audio Response**: The BETTER response {main_user} should have given.
    
    METRICS PROVIDED:
    {json.dumps(detailed_metrics, indent=2)}
    
    TRANSCRIPT START:
    {transcript_text[:3000]}... (truncated)
    
    OUTPUT JSON FORMAT:
    {json_template}
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a helpful, constructive dating coach."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return {
            "analysis": {"dominance": "Error", "interruptions": "Error", "silence": "Error", "quality": "Error"},
            "action_plan": ["AI Analysis Failed."]
        }


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def process_upload(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())[:8]
    file_ext = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}{file_ext}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        print(f"[API] Processing upload {job_id}...")
        segments = pipeline.run(file_path)
        samples = extract_speaker_samples(file_path, segments, job_id)
        SESSION_STORE[job_id] = {
            "file_path": file_path,
            "segments": segments,
            "original_name": file.filename
        }
        speakers = list(samples.keys())
        return JSONResponse({
            "job_id": job_id,
            "speakers": speakers,
            "samples": samples
        })
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/analyze")
async def analyze_with_names(job_id: str = Form(...), speaker_map: str = Form(...), main_user_name: str = Form(None)):
    try:
        session = SESSION_STORE.get(job_id)
        if not session:
            return JSONResponse({"error": "Session expired or not found"}, status_code=404)
            
        segments = session["segments"]
        mapping = json.loads(speaker_map)
        
        # Apply names
        for s in segments:
            if s.speaker in mapping and mapping[s.speaker].strip():
                s.speaker = mapping[s.speaker]
        
        # Determine Main User (default to first speaker if not provided)
        if not main_user_name:
            main_user_name = segments[0].speaker if segments else "User"

        meter = AwkwardnessMeter()
        report = meter.analyze_conversation(segments)
        
        # --- 1. Dominance / Speaking Time ---
        total_duration = segments[-1].end - segments[0].start if segments else 1
        speakers_time = {}
        for s in segments:
            dur = s.end - s.start
            speakers_time[s.speaker] = speakers_time.get(s.speaker, 0) + dur
        
        # Calculate percentages
        speakers_pct = {k: round((v / total_duration) * 100, 1) for k, v in speakers_time.items()}
        
        # --- 2. Interruptions (DEEP DIVE MODE) ---
        interruption_counts = {spk: 0 for spk in speakers_time.keys()}
        for i in range(1, len(segments)):
            prev = segments[i-1]
            curr = segments[i]
            
            # Skip if same speaker
            if curr.speaker == prev.speaker:
                continue
                
            gap = curr.start - prev.end
            
            # Definition of Interruption:
            # 1. Real Overlap: Negative gap
            # 2. Fast Latch: Gap < 0.15s (starts IMMEDIATELY, often perceived as cutting off)
            is_interruption_timing = gap < 0.15
            
            # Filter out backchannels (short "Yeah" < 1s)
            # If the interrupter speaks for less than 1s, it's likely just agreement, not interruption
            curr_duration = curr.end - curr.start
            is_substantial = curr_duration > 1.0 
            
            if is_interruption_timing and is_substantial:
                interruption_counts[curr.speaker] += 1

        # --- 3. Silence Analysis ---
        gaps = [m for m in report['moments'] if "Silence" in m.label]
        avg_gap = sum([m.end - m.start for m in gaps]) / len(gaps) if gaps else 0
        total_silence_duration = sum([m.end - m.start for m in gaps])

        # --- 4. Quality (Filtered Questions & Phrase Length) ---
        question_counts = {spk: 0 for spk in speakers_time.keys()}
        phrase_lengths = {spk: [] for spk in speakers_time.keys()}

        for s in segments:
            # Only count REAL questions (> 3 words) to avoid "C'est ça?" padding
            if '?' in s.text and len(s.text.split()) > 3:
                question_counts[s.speaker] += 1
            
            word_count = len(s.text.split())
            phrase_lengths[s.speaker].append(word_count)

        avg_words_per_turn = {k: round(sum(v)/len(v), 1) if v else 0 for k, v in phrase_lengths.items()}

        # --- 5. AWKWARDNESS SCORE CALCULATION ---
        # Start with the base score from analysis.py (based on gaps/overlaps)
        final_score = report["score"]
        
        # Penalty: Monologue / Dominance
        max_dominance = max(speakers_pct.values()) if speakers_pct else 0
        if max_dominance > 60:
            # Add 2 points for every % above 60
            dominance_penalty = (max_dominance - 60) * 2.5
            final_score += dominance_penalty
            
        # Penalty: Dead Air (Average Silence)
        if avg_gap > 2.5:
            # Add 10 points for every second above 2.5s
            silence_penalty = (avg_gap - 2.5) * 15
            final_score += silence_penalty
            
        # Penalty: Interruptions
        total_interruptions = sum(interruption_counts.values())
        final_score += total_interruptions * 5
        
        # Cap at 100
        final_score = min(100, int(final_score))
        report["score"] = final_score
        
        # Update Verdict Label based on new score
        if final_score < 20: report["label"] = "Smooth Vibes ✨"
        elif final_score < 40: report["label"] = "Slightly Frictioned 😬"
        elif final_score < 70: report["label"] = "AWKWARD 🚩"
        else: report["label"] = "HOSTAGE SITUATION 🚨"
        
        # --- Prepare Data for AI ---
        transcript_text = "\n".join([f"{s.speaker}: {s.text}" for s in segments])
        
        detailed_metrics = {
            "score": report["score"],
            "duration_total": round(total_duration, 1),
            "speaking_distribution": speakers_pct,
            "interruptions": interruption_counts,
            "silence_stats": {
                "count": len(gaps),
                "avg_duration": round(avg_gap, 2),
                "total_duration": round(total_silence_duration, 1)
            },
            "engagement_stats": {
                "questions_asked": question_counts,
                "avg_words_per_turn": avg_words_per_turn
            }
        }
        
        pain_points_json = [
            {
                "start": m.start,
                "end": m.end,
                "label": m.label,
                "desc": m.description,
                "severity": m.severity
            } for m in report['moments']
        ]
        
        # Call Date Doctor AI with Main User context
        ai_insights = generate_ai_insights(transcript_text, detailed_metrics, main_user_name)

        final_response = {
            "score": report["score"],
            "verdict": report["label"],
            "detailed_metrics": detailed_metrics,
            "ai_insights": ai_insights,
            "timeline": [
                {
                    "start": s.start,
                    "end": s.end,
                    "speaker": s.speaker,
                    "text": s.text,
                    "type": "speech"
                } for s in segments
            ],
            "pain_points": pain_points_json
        }
        
        return JSONResponse(content=final_response)

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

import hashlib

@app.post("/generate_coach_audio")
async def generate_coach_audio(
    job_id: str = Form(...), 
    trigger_speaker: str = Form(...), 
    trigger_text: str = Form(...),
    response_speaker: str = Form(...),
    response_text: str = Form(...)
):
    if not gradium_tts:
        return JSONResponse({"error": "Gradium API Key not configured"}, status_code=500)
    
    async def generate_single_clip(spk_name, text):
        # Find sample (assuming spk_name is the ID like SPEAKER_00)
        sample_path = os.path.join(SAMPLES_DIR, f"{job_id}_{spk_name}.wav")
        if not os.path.exists(sample_path):
            print(f"Sample not found for {spk_name} at {sample_path}")
            return None
        
        # Clone
        voice_uid = gradium_tts.clone_voice(sample_path, spk_name)
        if not voice_uid: return None
        
        # Generate
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        output_filename = f"coach_{job_id}_{spk_name}_{text_hash}.wav"
        output_path = os.path.join(SAMPLES_DIR, output_filename)
        
        # Generate
        success = await gradium_tts.generate_audio_async(text, voice_uid, output_path)
        return f"/static/samples/{output_filename}" if success else None

    # Generate both clips concurrently
    # Note: Trigger speaker and Response speaker are passed as IDs (SPEAKER_00) from frontend
    
    print(f"Generating audio sequence. Trigger: {trigger_speaker} says '{trigger_text}'. Response: {response_speaker} says '{response_text}'")
    
    url_trigger = await generate_single_clip(trigger_speaker, trigger_text)
    url_response = await generate_single_clip(response_speaker, response_text)
    
    if url_trigger and url_response:
        return JSONResponse({
            "playlist": [url_trigger, url_response]
        })
    elif url_response:
        # Fallback if trigger fails
        return JSONResponse({
            "playlist": [url_response]
        })
    else:
        return JSONResponse({"error": "TTS Generation failed"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
