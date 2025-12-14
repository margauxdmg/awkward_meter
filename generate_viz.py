import json
import os

def generate_html_report(json_path="output/report.json", html_path="output/report.html"):
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, "r") as f:
        data = json.load(f)

    score = data["score"]
    label = data["label"]
    moments = data["moments"]
    transcript = data["transcript"]

    # Simple Color Logic
    score_color = "#4CAF50" # Green
    if score > 40: score_color = "#FF9800" # Orange
    if score > 70: score_color = "#F44336" # Red

    # Build HTML Content
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Awkwardness Report</title>
        <style>
            body {{ font-family: 'Helvetica Neue', sans-serif; background: #f4f4f9; color: #333; margin: 0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
            h1 {{ text-align: center; color: #444; margin-bottom: 10px; }}
            .score-box {{ text-align: center; margin: 30px 0; }}
            .score-val {{ font-size: 80px; font-weight: bold; color: {score_color}; }}
            .score-label {{ font-size: 24px; color: #666; margin-top: -10px; display: block; }}
            
            .timeline {{ position: relative; margin-top: 50px; border-left: 2px solid #ddd; padding-left: 20px; }}
            .event {{ margin-bottom: 25px; position: relative; }}
            .event::before {{ content: ''; position: absolute; left: -26px; top: 5px; width: 10px; height: 10px; border-radius: 50%; background: #ddd; }}
            
            .speaker-tag {{ font-size: 12px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-bottom: 4px; display: block; }}
            .bubble {{ background: #f0f0f5; padding: 12px 18px; border-radius: 18px; display: inline-block; max-width: 80%; line-height: 1.5; }}
            .bubble.SPEAKER_00 {{ background: #e3f2fd; color: #0d47a1; }}
            .bubble.SPEAKER_01 {{ background: #fce4ec; color: #880e4f; }}
            
            .awkward-moment {{ border-left: 4px solid #F44336; background: #ffebee; padding: 15px; margin: 20px 0; border-radius: 4px; }}
            .awkward-label {{ color: #D32F2F; font-weight: bold; display: block; margin-bottom: 5px; }}
            .time-stamp {{ font-size: 11px; color: #aaa; margin-left: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>The Awkwardness Meter</h1>
            
            <div class="score-box">
                <div class="score-val">{score}/100</div>
                <span class="score-label">{label}</span>
            </div>

            <h3>Conversation Log</h3>
            <div class="timeline">
    """

    # We want to interleave Transcript and Awkward Moments chronologically
    # Combine both lists and sort by start time
    
    events = []
    for t in transcript:
        events.append({"type": "speech", "data": t, "time": t["start"]})
    for m in moments:
        events.append({"type": "awkward", "data": m, "time": m["start"]})
        
    events.sort(key=lambda x: x["time"])

    for event in events:
        if event["type"] == "speech":
            s = event["data"]
            speaker_cls = s['speaker'] if s['speaker'] in ['SPEAKER_00', 'SPEAKER_01'] else 'unknown'
            html_content += f"""
                <div class="event">
                    <span class="speaker-tag">{s['speaker']} <span class="time-stamp">{s['start']:.1f}s</span></span>
                    <div class="bubble {speaker_cls}">{s['text']}</div>
                </div>
            """
        else:
            m = event["data"]
            html_content += f"""
                <div class="awkward-moment">
                    <span class="awkward-label">⚠️ {m['label']} ({m['start']:.1f}s - {m['end']:.1f}s)</span>
                    {m['description']}
                </div>
            """

    html_content += """
            </div>
        </div>
    </body>
    </html>
    """

    with open(html_path, "w") as f:
        f.write(html_content)
    
    print(f"HTML Report generated at: {html_path}")

if __name__ == "__main__":
    generate_html_report()

