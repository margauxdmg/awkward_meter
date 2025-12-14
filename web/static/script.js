// DOM Elements
const uploadSection = document.getElementById('upload-section');
const loadingScreen = document.getElementById('loading-screen');
const loadingText = document.getElementById('loading-text');
const identitySection = document.getElementById('identity-section');
const reportSection = document.getElementById('report-section');
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnAnalyze = document.getElementById('btn-analyze');

let currentJobId = null;
let currentSpeakers = [];
let speakerIdMap = {}; // Maps Name -> Original ID (e.g. "Margaux" -> "SPEAKER_01")
let globalMainUser = null; // Store the selected main user name

// Drag & Drop
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = '#00f2ff'; });
dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = 'rgba(255,255,255,0.1)'; });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'rgba(255,255,255,0.1)';
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

async function handleFile(file) {
    uploadSection.classList.add('hidden');
    loadingScreen.classList.remove('hidden');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', { method: 'POST', body: formData });
        const data = await response.json();
        
        loadingScreen.classList.add('hidden');
        if (data.error) throw new Error(data.error);

        currentJobId = data.job_id;
        currentSpeakers = data.speakers;
        showIdentityScreen(data.speakers, data.samples);
    } catch (e) {
        alert("Upload Error: " + e.message);
        location.reload();
    }
}

function showIdentityScreen(speakers, samples) {
    identitySection.classList.remove('hidden');
    const grid = document.getElementById('speakers-grid');
    if (!grid) {
        console.error("Critical Error: #speakers-grid element not found in DOM.");
        alert("Interface Error: Please reload the page.");
        return;
    }
    grid.innerHTML = '';

    speakers.forEach((spk, index) => {
        const div = document.createElement('div');
        div.className = 'speaker-card';
        div.innerHTML = `
            <label class="spk-label">IDENTIFY: ${spk}</label>
            <input type="text" class="spk-input" id="name-${spk}" value="${spk}" placeholder="Enter name...">
            
            <div style="margin: 10px 0; display: flex; align-items: center; gap: 8px;">
                <input type="radio" name="main_user" id="me-${spk}" value="${spk}" ${index === 0 ? 'checked' : ''}>
                <label for="me-${spk}" style="font-size: 0.8rem; cursor: pointer; color: var(--accent);">THIS IS ME (Analyze My Performance)</label>
            </div>

            <div class="audio-control" onclick="document.getElementById('audio-${spk}').play()">
                ▶ LISTEN TO SAMPLE
            </div>
            <audio id="audio-${spk}" src="${samples[spk]}"></audio>
        `;
        grid.appendChild(div);
    });
}

btnAnalyze.addEventListener('click', async () => {
    const speakerMap = {};
    speakerIdMap = {}; // Reset
    let mainUserId = null;

    currentSpeakers.forEach(spk => {
        const val = document.getElementById(`name-${spk}`).value || spk;
        speakerMap[spk] = val;
        // Clean key for mapping: lower case
        speakerIdMap[val.toLowerCase().trim()] = spk;
        
        // Check if this is the main user
        if (document.getElementById(`me-${spk}`).checked) {
            mainUserId = val; // We send the RENAMED name as main user
        }
    });

    identitySection.classList.add('hidden');
    loadingScreen.classList.remove('hidden');
    loadingText.innerText = "Running behavioral analysis & AI coaching...";

    const formData = new FormData();
    formData.append('job_id', currentJobId);
    formData.append('speaker_map', JSON.stringify(speakerMap));
    formData.append('main_user_name', mainUserId);
    
    globalMainUser = mainUserId; 

    try {
        const response = await fetch('/analyze', { method: 'POST', body: formData });
        const data = await response.json();
        
        loadingScreen.classList.add('hidden');
        if (data.error) throw new Error(data.error);
        
        showReport(data);
    } catch (e) {
        alert("Analysis Error: " + e.message);
        location.reload();
    }
});

function showReport(data) {
    reportSection.classList.remove('hidden');

    // Score Ring
    const circle = document.getElementById('score-ring');
    if (circle) {
        // Circumference is 100 due to radius ~15.9155
        const circumference = 100;
        const offset = circumference - (data.score / 100) * circumference;
        
        circle.style.strokeDasharray = `${circumference} ${circumference}`;
        circle.style.strokeDashoffset = circumference;
        
        setTimeout(() => { circle.style.strokeDashoffset = offset; }, 100);
    } else console.warn("#score-ring not found");
    
    // Counting animation
    let count = 0;
    const targetScore = Math.round(data.score || 0);
    const scoreValEl = document.getElementById('score-val');
    
    // Reset immediately
    scoreValEl.textContent = "0";

    const interval = setInterval(() => {
        if (count >= targetScore) {
            clearInterval(interval);
            scoreValEl.textContent = targetScore;
        } else {
            count++;
            scoreValEl.textContent = count;
        }
    }, 20);

    document.getElementById('verdict-text').innerText = data.verdict;

    // --- ANALYTICS DASHBOARD ---
    const metrics = data.detailed_metrics;
    const analysis = data.ai_insights.analysis;

    // Helper to safely set text
    const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.innerText = text;
        else console.warn(`Element #${id} not found`);
    };

    // 1. Dominance
    const domChart = document.getElementById('dominance-chart');
    if (domChart) {
        domChart.innerHTML = '<div class="bar-midpoint"></div>';
        const colors = ['#00f2ff', '#ff00d4', '#e1ff00']; // Cyan, Magenta, Yellow
        let i = 0;
        for (const [spk, pct] of Object.entries(metrics.speaking_distribution)) {
            const bar = document.createElement('div');
            bar.className = 'bar-segment';
            bar.style.width = `${pct}%`;
            bar.style.backgroundColor = colors[i % colors.length];
            bar.innerText = `${spk} ${pct}%`;
            domChart.appendChild(bar);
            i++;
        }
    } else console.warn("#dominance-chart not found");
    
    setText('dominance-comment', analysis.dominance || "No analysis available.");

    // 2. Interruptions
    let totalInt = 0;
    if (metrics.interruptions) {
        Object.values(metrics.interruptions).forEach(v => totalInt += v);
    }
    setText('interruptions-val', totalInt);
    setText('interruptions-comment', analysis.interruptions || "No interruptions detected.");

    // 3. Silence
    if (metrics.silence_stats) {
        setText('silence-val', metrics.silence_stats.avg_duration + "s");
    }
    setText('silence-comment', analysis.silence || "Silence analysis unavailable.");

    // 4. Quality (Engagement)
    let totalQuestions = 0;
    let totalWPT = 0;
    let speakerCount = 0;
    
    if (metrics.engagement_stats) {
        if (metrics.engagement_stats.questions_asked) {
            Object.values(metrics.engagement_stats.questions_asked).forEach(v => totalQuestions += v);
        }
        if (metrics.engagement_stats.avg_words_per_turn) {
            Object.values(metrics.engagement_stats.avg_words_per_turn).forEach(v => {
                totalWPT += v;
                speakerCount++;
            });
        }
    }
    const avgWPT = speakerCount ? Math.round(totalWPT / speakerCount) : 0;

    setText('questions-val', totalQuestions);
    setText('wpt-val', avgWPT);
    setText('quality-comment', analysis.quality || "Engagement analysis unavailable.");


    // --- ACTION PLAN / INNER VOICE REWIND ---
    const actionList = document.getElementById('action-plan-list');
    if (actionList) {
        actionList.innerHTML = '';
        if (data.ai_insights.action_plan && Array.isArray(data.ai_insights.action_plan)) {
            data.ai_insights.action_plan.forEach(item => {
                const div = document.createElement('div');
                div.className = 'action-item';
                
                // --- NEW LOGIC: Use separated fields from AI ---
                const displayText = item.display_text || item.text; // Fallback
                const triggerText = item.audio_trigger_text || "";
                const responseText = item.audio_response_text || item.text;
                
                // Determine Speakers for Audio
                // Response Speaker is Main User
                const responseName = globalMainUser ? globalMainUser.toLowerCase().trim() : "";
                const responseId = speakerIdMap[responseName];

                // Trigger Speaker (The OTHER person)
                // If AI gives name, use it. Else find the one that ISN'T the main user.
                let triggerName = item.audio_trigger_speaker ? item.audio_trigger_speaker.toLowerCase().trim() : "";
                let triggerId = speakerIdMap[triggerName];
                
                // Fallback: If we don't know the trigger speaker, pick the first one that isn't the main user
                if (!triggerId && currentSpeakers.length > 1) {
                    const other = currentSpeakers.find(s => s !== responseId);
                    if (other) triggerId = other;
                }

                // Show button if we have Main User ID
                if (responseId) {
                    audioBtn = `<button class="audio-gen-btn" onclick="playCoachAudio(this)">↺ REPLAY THIS MOMENT BETTER</button>`;
                }
                
                div.innerHTML = `
                    <div style="font-size: 0.85rem; color: #888; margin-bottom: 4px; font-style: italic;">
                        ${item.context || "At this moment..."}
                    </div>
                    <div style="margin-bottom:8px; color: #fff; font-size: 1.1rem;">
                        "${displayText}"
                    </div>
                    <div class="action-audio-container" style="border-top:1px solid rgba(255,255,255,0.1); padding-top:8px;">
                        ${audioBtn}
                        <p class="audio-status" style="display:none; font-size:0.8rem; color:#00f2ff; margin-top:5px;">Initializing Inner Voice...</p>
                    </div>
                `;
                
                // Store Data on the Container
                div.dataset.triggerSpeaker = triggerId || "";
                div.dataset.triggerText = triggerText;
                div.dataset.responseSpeaker = responseId || "";
                div.dataset.responseText = responseText;
                
                actionList.appendChild(div);
            });
        } else {
            actionList.innerHTML = '<div class="action-item">No action plan generated.</div>';
        }
    } else console.warn("#action-plan-list not found");


    // --- TIMELINE ---
    const timeline = document.getElementById('timeline');
    if (timeline) {
        timeline.innerHTML = '';

        // Merge moments and transcript
        const allEvents = [];
        if (data.timeline) data.timeline.forEach(t => allEvents.push({...t, type: 'speech'}));
        if (data.pain_points) data.pain_points.forEach(p => allEvents.push({...p, type: 'pain'}));
        allEvents.sort((a, b) => a.start - b.start);

        allEvents.forEach(evt => {
            const row = document.createElement('div');
            
            if (evt.type === 'pain') {
                row.className = 'event-awkward';
                row.innerHTML = `⚠️ ${evt.label}: ${evt.desc} (${Math.round(evt.end - evt.start)}s)`;
            } else {
                // Determine alignment based on speaker index (simple heuristic)
                const isSecondSpeaker = Object.keys(metrics.speaking_distribution).indexOf(evt.speaker) === 1;
                row.className = `event-row ${isSecondSpeaker ? 'right' : 'left'}`;
                
                row.innerHTML = `
                    <div class="event-time">${formatTime(evt.start)}</div>
                    <div class="event-bubble">
                        <strong>${evt.speaker}</strong><br>
                        ${evt.text}
                    </div>
                `;
            }
            timeline.appendChild(row);
        });
    } else console.warn("#timeline not found");
}

async function playCoachAudio(btn) {
    const container = btn.parentElement.parentElement; // div.action-item
    const status = container.querySelector('.audio-status');
    
    const triggerId = container.dataset.triggerSpeaker;
    const triggerText = container.dataset.triggerText;
    const responseId = container.dataset.responseSpeaker;
    const responseText = container.dataset.responseText;

    if (!responseId) {
        alert("Error: Main user identity lost.");
        return;
    }

    btn.disabled = true;
    btn.style.opacity = "0.5";
    status.style.display = 'block';
    status.innerText = `Synthesizing Replay (Dual Voice)...`;
    
    const formData = new FormData();
    formData.append('job_id', currentJobId);
    formData.append('trigger_speaker', triggerId);
    formData.append('trigger_text', triggerText);
    formData.append('response_speaker', responseId);
    formData.append('response_text', responseText);
    
    try {
        const response = await fetch('/generate_coach_audio', { method: 'POST', body: formData });
        const data = await response.json();
        
        if (data.error) throw new Error(data.error);
        if (!data.playlist || data.playlist.length === 0) throw new Error("No audio generated.");
        
        status.innerText = "▶ Playing Replay...";
        
        // Play Sequence
        let i = 0;
        const playNext = () => {
            if (i >= data.playlist.length) {
                btn.disabled = false;
                btn.style.opacity = "1";
                status.style.display = 'none';
                return;
            }
            const audio = new Audio(data.playlist[i]);
            audio.onended = () => {
                i++;
                playNext();
            };
            audio.onerror = (e) => {
                console.error("Audio playback error", e);
                i++;
                playNext();
            };
            audio.play();
        };
        
        playNext();
        
    } catch (e) {
        alert("Audio Gen Error: " + e.message);
        btn.disabled = false;
        btn.style.opacity = "1";
        status.innerText = "Error: " + e.message;
    }
}

function formatTime(seconds) {
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
}
