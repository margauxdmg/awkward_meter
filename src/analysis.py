from typing import List, Dict
from .utils import Segment, AwkwardMoment

class AwkwardnessMeter:
    def __init__(self):
        # Explicit thresholds for explainability - STRICTER FOR DATING CONTEXT
        self.TH_SILENCE_AWKWARD = 1.5  # Seconds (was 2.5)
        self.TH_SILENCE_PAINFUL = 3.0  # Seconds (was 4.0)
        self.TH_OVERLAP_BAD = 0.2      # Seconds (was 1.0)
        self.TH_LATENCY_QUESTION = 1.0

    def analyze_conversation(self, segments: List[Segment]) -> dict:
        """
        Input: Chronological list of speech segments (aligned text + time).
        Output: Score and Timeline.
        """
        moments = []
        
        # 1. Scan for temporal friction (Gaps & Overlaps)
        for i in range(len(segments) - 1):
            current = segments[i]
            next_seg = segments[i+1]
            
            # Calculate Gap (can be negative if overlapping)
            gap = next_seg.start - current.end
            
            # CHECK: Dead Air
            if gap > self.TH_SILENCE_AWKWARD:
                reason = "Awkward Silence"
                severity = 0.6
                desc = f"Uncomfortable pause of {gap:.1f}s."
                
                # Escalation: Is it after a question?
                if current.is_question:
                    reason = "Left Hanging (Vent)"
                    severity = 1.0 # MAX SEVERITY
                    desc = f"Question left hanging for {gap:.1f}s."
                elif gap > self.TH_SILENCE_PAINFUL:
                    reason = "Painful Silence"
                    severity = 0.9
                    desc = f"Painfully long silence of {gap:.1f}s."
                
                moments.append(AwkwardMoment(current.end, next_seg.start, severity, reason, desc))

            # CHECK: Bad Overlap
            # If gap is negative, they are talking over each other
            elif gap < -self.TH_OVERLAP_BAD:
                overlap_dur = abs(gap)
                # Ignore very short overlaps if they are just backchannels (e.g. "Yeah")
                # checking length of text is a proxy
                if len(next_seg.text.split()) > 1: 
                    moments.append(AwkwardMoment(
                        next_seg.start, 
                        current.end, 
                        0.7, 
                        "Interruption", 
                        f"Speech overlap of {overlap_dur:.1f}s."
                    ))

        # 2. Global Aggregation
        total_awkward_time = sum([(m.end - m.start) * m.severity for m in moments])
        total_duration = segments[-1].end - segments[0].start if segments else 1
        
        # Score Logic: 100 - (Flow Integrity)
        # We want the score to spike easily if there are multiple bad moments.
        # Ratio of weighted awkward time to total time.
        # If 5% of the call is weighted awkward, that's already bad in a date.
        awkward_ratio = total_awkward_time / total_duration
        
        # Logarithmic-ish curve: small amount of awkwardness = high impact
        base_score = (awkward_ratio / 0.05) * 50 
        
        global_score = min(100, base_score)
        if moments and global_score < 20: global_score = 20 # Minimum score if issues detected
        
        return {
            "score": int(global_score),
            "label": self._get_qualitative_label(global_score),
            "moments": moments
        }

    def _get_qualitative_label(self, score):
        if score < 20: return "Smooth / In-Sync"
        if score < 50: return "Slightly Frictioned"
        if score < 80: return "Awkward"
        return "Excruciating"

