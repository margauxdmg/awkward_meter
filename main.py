import os
import sys
import json
from dotenv import load_dotenv
from src.analysis import AwkwardnessMeter
from src.utils import Segment
from src.pipeline import AwkwardPipeline
from generate_viz import generate_html_report

# Load environment variables
load_dotenv()

def main():
    print("==========================================")
    print("   THE AWKWARDNESS METER (Prototype)      ")
    print("==========================================")
    
    # Check for keys
    pyannote_key = os.getenv("PYANNOTE_API_KEY")
    gradium_key = os.getenv("GRADIUM_API_KEY")
    
    if not pyannote_key or not gradium_key:
        print("[WARNING] API Keys missing in .env.")
        print("Using Simulation Mode.")
        pipeline = AwkwardPipeline(pyannote_key="", gradium_key="")
    else:
        pipeline = AwkwardPipeline(pyannote_key, gradium_key)

    print("\n[1] Loading Audio Processing Pipeline...")
    
    # Check for input file
    input_dir = "input"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    audio_files = [f for f in os.listdir(input_dir) if f.endswith(('.wav', '.mp3', '.m4a'))] if os.path.exists(input_dir) else []
    
    if audio_files:
        target_file = os.path.join(input_dir, audio_files[0])
        print(f"    Found input file: {target_file}")
        segments = pipeline.run(target_file)
    else:
        print("    No audio file found in input/. Using Simulation Data.")
        segments = pipeline.run("dummy.wav")
    
    print(f"    Loaded {len(segments)} turns.")

    # --- Speaker Identification (Manual Labeling) ---
    speakers = sorted(list(set([s.speaker for s in segments if "SPEAKER" in s.speaker])))
    speaker_map = {}
    
    if speakers:
        print("\n[2] Speaker Identification")
        print("    I found the following speakers. Who are they?")
        print("    (Press Enter to keep default name)")
        
        # In a real interactive terminal, we would use input(). 
        # But here in a non-interactive run, we might skip or simulate.
        # Assuming the user runs this locally in a terminal:
        try:
            for spk in speakers:
                name = input(f"    > Who is {spk}? ")
                if name.strip():
                    speaker_map[spk] = name.strip()
        except EOFError:
            print("    [Non-interactive mode detected, skipping manual labeling]")

    # Apply mapping
    if speaker_map:
        for s in segments:
            if s.speaker in speaker_map:
                s.speaker = speaker_map[s.speaker]
    
    print("\n[3] Analyzing Conversational Dynamics...")
    meter = AwkwardnessMeter()
    report = meter.analyze_conversation(segments)
    
    print("\n================ REPORT ================")
    print(f"GLOBAL SCORE: {report['score']}/100")
    print(f"VERDICT:      {report['label']}")
    print("----------------------------------------")
    print("TIMELINE OF PAIN:")
    for m in report['moments']:
        print(f"[{m.start:.1f}s - {m.end:.1f}s] {m.label}: {m.description}")
    print("========================================\n")
    
    # Save Report to JSON
    output_file = os.path.join(output_dir, "report.json")
    
    json_report = {
        "score": report["score"],
        "label": report["label"],
        "moments": [
            {
                "start": m.start, 
                "end": m.end, 
                "label": m.label, 
                "description": m.description, 
                "severity": m.severity
            } for m in report["moments"]
        ],
        "transcript": [
            {
                "start": s.start,
                "end": s.end,
                "speaker": s.speaker,
                "text": s.text
            } for s in segments
        ]
    }
    
    with open(output_file, "w") as f:
        json.dump(json_report, f, indent=2)
    print(f"Report saved to: {output_file}")
    
    # Generate HTML automatically
    generate_html_report(output_file, os.path.join(output_dir, "report.html"))

if __name__ == "__main__":
    main()