from __future__ import annotations

import os
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from gtts import gTTS
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips, vfx
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
VISEME_DIR_DEFAULT = STATIC_DIR / "visemes"
VISEME_DIR_FALLBACK = ROOT.parent / "viseme"  # your current layout: AI/Meditra-avatar/viseme/*.mp4
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


AllowedViseme = Literal[
    "ee",
    "ih",
    "ah",
    "oh",
    "oo",
    "ma",
    "pa",
    "fa",
    "tha",
    "ta",
    "ka",
    "sha",
    "pause",
]

ALL_VISEMES: list[AllowedViseme] = [
    "ee",
    "ih",
    "ah",
    "oh",
    "oo",
    "ma",
    "pa",
    "fa",
    "tha",
    "ta",
    "ka",
    "sha",
    "pause",
]


class GenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class GenerateResponse(BaseModel):
    video_url: str
    download_url: str
    duration_s: float
    segments: int
    visemes: list[str]


app = FastAPI(title="Meditra Avatar Generator")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


def _require_viseme_clips() -> None:
    global VISEME_DIR_DEFAULT
    viseme_dir = _resolve_viseme_dir()
    missing: list[str] = []
    for v in ALL_VISEMES:
        p = viseme_dir / f"{v}.mp4"
        if not p.exists():
            missing.append(p.name)
    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Missing viseme clips in {viseme_dir.as_posix()}: "
                + ", ".join(missing)
                + ". Add these files and retry."
            ),
        )


def _resolve_viseme_dir() -> Path:
    # Prefer app/static/visemes, but also support repo-level AI/Meditra-avatar/viseme/
    # Only use a candidate if it actually contains at least one expected clip.
    if (VISEME_DIR_DEFAULT / "ih.mp4").exists() or (VISEME_DIR_DEFAULT / "ee.mp4").exists():
        return VISEME_DIR_DEFAULT
    return VISEME_DIR_FALLBACK


def _tts_to_mp3(text: str, out_path: Path) -> None:
    """Generate TTS audio with fallback to local TTS if gTTS fails."""
    # Try gTTS first (online)
    try:
        tts = gTTS(text=text)
        tts.save(str(out_path))
        print(f"✅ gTTS generated: {out_path}")
        return
    except Exception as e:
        print(f"⚠️ gTTS failed: {e}")
        
    # Fallback to local TTS
    if PYTTSX3_AVAILABLE:
        try:
            # Initialize pyttsx3 with better error handling
            engine = pyttsx3.init(driverName='sapi5') if os.name == 'nt' else pyttsx3.init()
            
            # Set voice properties for better quality
            voices = engine.getProperty('voices')
            if voices:
                engine.setProperty('voice', voices[0].id)  # Use first available voice
            engine.setProperty('rate', 150)  # Normal speech rate
            
            # Save to temporary wav file first, then convert to mp3
            temp_wav = out_path.with_suffix('.wav')
            engine.save_to_file(text, str(temp_wav))
            engine.runAndWait()
            
            # Wait a moment for file to be written
            import time
            time.sleep(0.5)
            
            # Convert wav to mp3 using moviepy
            if temp_wav.exists() and temp_wav.stat().st_size > 0:
                audio_clip = AudioFileClip(str(temp_wav))
                audio_clip.write_audiofile(str(out_path), codec='mp3')
                audio_clip.close()
                temp_wav.unlink()  # Remove temp file
                print(f"✅ Local TTS generated: {out_path}")
                return
            else:
                print(f"⚠️ Local TTS failed: WAV file not created or empty")
        except Exception as e:
            print(f"⚠️ Local TTS failed: {e}")
            # Try alternative approach
            try:
                # Try without specific driver
                engine = pyttsx3.init()
                temp_wav = out_path.with_suffix('.wav')
                engine.save_to_file(text, str(temp_wav))
                engine.runAndWait()
                time.sleep(0.5)
                
                if temp_wav.exists() and temp_wav.stat().st_size > 0:
                    audio_clip = AudioFileClip(str(temp_wav))
                    audio_clip.write_audiofile(str(out_path), codec='mp3')
                    audio_clip.close()
                    temp_wav.unlink()
                    print(f"✅ Local TTS (fallback) generated: {out_path}")
                    return
            except Exception as e2:
                print(f"⚠️ Local TTS fallback also failed: {e2}")
    
    # Create a silent audio file as last resort
    try:
        # Create 1 second of silence
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        import numpy as np
        
        # Generate 1 second of silence at 44100 Hz
        sample_rate = 44100
        duration = 1.0  # 1 second
        silence = np.zeros((int(sample_rate * duration), 2), dtype=np.float32)
        
        # Create audio clip from silence and save
        def make_frame(t):
            return silence[int(t * sample_rate)] if t < duration else silence[-1]
        
        audio_clip = AudioClip(make_frame, duration=duration)
        audio_clip.fps = sample_rate
        audio_clip.write_audiofile(str(out_path), codec='mp3')
        audio_clip.close()
        print(f"✅ Silent audio generated: {out_path}")
    except Exception as e:
        print(f"❌ All TTS methods failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {e}")


def _audio_duration_s(audio_path: Path) -> float:
    # Use ffmpeg-backed parsing (works well for mp3 from gTTS).
    clip = AudioFileClip(str(audio_path))
    try:
        return float(clip.duration)
    finally:
        clip.close()


def _detect_silence_segments(audio_path: Path, silence_threshold: float = 0.01, min_silence_duration: float = 0.1) -> list[tuple[float, float]]:
    """Detect silence segments in audio for pause clip insertion."""
    clip = AudioFileClip(str(audio_path))
    try:
        # Get audio samples with error handling
        try:
            audio_array = clip.to_soundarray()
        except Exception:
            # Fallback: return empty silence segments if audio analysis fails
            return []
        
        if len(audio_array.shape) > 1:
            # Convert stereo to mono by averaging channels
            audio_array = np.mean(audio_array, axis=1)
        
        # Calculate RMS energy with smaller frame size for better precision
        frame_size = max(int(clip.fps * 0.02), 1)  # 20ms frames minimum 1 sample
        energies = []
        
        for i in range(0, len(audio_array), frame_size):
            frame = audio_array[i:i+frame_size]
            if len(frame) > 0:
                rms = np.sqrt(np.mean(frame**2))
                energies.append(rms)
        
        if not energies:
            return []
        
        # Detect silence segments
        silence_segments = []
        in_silence = False
        silence_start = 0
        
        for i, energy in enumerate(energies):
            time_point = (i * frame_size) / clip.fps
            # Ensure time_point doesn't exceed clip duration
            time_point = min(time_point, clip.duration)
            is_silent = energy < silence_threshold
            
            if is_silent and not in_silence:
                silence_start = time_point
                in_silence = True
            elif not is_silent and in_silence:
                silence_duration = time_point - silence_start
                if silence_duration >= min_silence_duration:
                    silence_segments.append((silence_start, time_point))
                in_silence = False
        
        # Handle case where audio ends in silence
        if in_silence:
            silence_duration = clip.duration - silence_start
            if silence_duration >= min_silence_duration:
                silence_segments.append((silence_start, clip.duration))
        
        return silence_segments
    finally:
        clip.close()


def _segment_count(duration_s: float) -> int:
    segments = int(duration_s / 0.54)
    return max(6, min(10, segments))


def _random_segment_durations(total_s: float, n: int, jitter: float = 0.2) -> list[float]:
    base = total_s / float(n)
    weights = []
    for _ in range(n):
        w = random.uniform(1.0 - jitter, 1.0 + jitter)
        weights.append(w)
    weights = np.array(weights, dtype=np.float64)
    weights = weights / weights.sum()
    durs = (weights * total_s).tolist()

    # Avoid tiny segments that cause extreme speed changes.
    min_seg = max(0.18, base * 0.55)
    max_seg = base * 1.7
    durs = [float(min(max_seg, max(min_seg, d))) for d in durs]

    # Renormalize after clamping.
    s = sum(durs)
    if s <= 0:
        return [base] * n
    scale = total_s / s
    durs = [d * scale for d in durs]
    return durs


@dataclass(frozen=True)
class _VisemeProps:
    openness: float  # 0 closed -> 1 open
    rounding: float  # 0 wide -> 1 rounded
    motion: float  # 0 still -> 1 high motion


_PROPS: dict[AllowedViseme, _VisemeProps] = {
    "pause": _VisemeProps(openness=0.05, rounding=0.2, motion=0.05),
    "ma": _VisemeProps(openness=0.10, rounding=0.2, motion=0.35),
    "pa": _VisemeProps(openness=0.10, rounding=0.2, motion=0.45),
    "fa": _VisemeProps(openness=0.18, rounding=0.25, motion=0.45),
    "tha": _VisemeProps(openness=0.25, rounding=0.25, motion=0.55),
    "ta": _VisemeProps(openness=0.20, rounding=0.25, motion=0.50),
    "ka": _VisemeProps(openness=0.28, rounding=0.30, motion=0.55),
    "sha": _VisemeProps(openness=0.22, rounding=0.55, motion=0.55),
    "ih": _VisemeProps(openness=0.35, rounding=0.25, motion=0.40),  # bridge
    "ee": _VisemeProps(openness=0.25, rounding=0.10, motion=0.55),
    "ah": _VisemeProps(openness=0.85, rounding=0.25, motion=0.65),
    "oh": _VisemeProps(openness=0.55, rounding=0.75, motion=0.55),
    "oo": _VisemeProps(openness=0.25, rounding=0.95, motion=0.55),
}


def _distance(a: AllowedViseme, b: AllowedViseme) -> float:
    pa, pb = _PROPS[a], _PROPS[b]
    return abs(pa.openness - pb.openness) * 1.2 + abs(pa.rounding - pb.rounding) * 1.0


def _is_extreme_jump(a: AllowedViseme, b: AllowedViseme) -> bool:
    # Explicitly avoid the extreme wide<->rounded jump and very open<->very closed.
    if (a == "ee" and b == "oo") or (a == "oo" and b == "ee"):
        return True
    if (a == "ah" and b == "ee") or (a == "ee" and b == "ah"):
        return True
    if (a == "ah" and b == "oo") or (a == "oo" and b == "ah"):
        return True
    return _distance(a, b) > 0.95


def _pick_next(prev: AllowedViseme, rep_count: int) -> AllowedViseme:
    # Use ih as the primary bridge.
    candidates: list[AllowedViseme] = [v for v in ALL_VISEMES if v != prev]

    # Prefer low-motion options occasionally to mimic reduced articulation.
    if random.random() < 0.18:
        candidates = ["pause", "ih", "ma", "ta", "fa"]  # type: ignore[assignment]

    # Score candidates by continuity.
    scored: list[tuple[float, AllowedViseme]] = []
    for v in candidates:
        dist = _distance(prev, v)
        penalty = 2.5 if _is_extreme_jump(prev, v) else 0.0
        score = dist + penalty
        scored.append((score, v))

    scored.sort(key=lambda x: x[0])

    # Keep the best few and sample, to avoid robotic patterns.
    top = scored[: min(6, len(scored))]
    weights = np.linspace(1.0, 0.35, num=len(top), dtype=np.float64)
    weights = weights / weights.sum()
    choice = random.choices([v for _, v in top], weights=weights.tolist(), k=1)[0]

    # If we repeated twice already, force a change.
    if rep_count >= 2:
        if choice == prev:
            return "ih"
    return choice


def _text_to_visemes(text: str) -> list[AllowedViseme]:
    """Convert text to viseme sequence with precise phonetic mapping and smooth transitions."""
    # Enhanced phonetic mapping focusing on visual similarity and timing
    phoneme_to_viseme = {
        # Vowels - primary mouth shapes
        'a': 'ah', 'e': 'ee', 'i': 'ih', 'o': 'oh', 'u': 'oo',
        'A': 'ah', 'E': 'ee', 'I': 'ih', 'O': 'oh', 'U': 'oo',
        
        # Diphthongs and vowel combinations - prioritize visual flow
        'ai': 'ah', 'ay': 'ah', 'ae': 'ah',
        'ea': 'ee', 'ee': 'ee', 'ie': 'ee', 'ei': 'ee',
        'oa': 'oh', 'ow': 'oh', 'ou': 'oh', 'oy': 'oh',
        'oo': 'oo', 'ue': 'oo', 'ui': 'oo',
        
        # Bilabial consonants - similar mouth closure
        'b': 'pa', 'p': 'pa', 'm': 'ma',
        
        # Labiodental consonants - teeth on lip
        'f': 'fa', 'v': 'fa',
        
        # Dental consonants - tongue position
        'th': 'tha', 't': 'ta', 'd': 'ta',
        
        # Velar consonants - back of mouth
        'k': 'ka', 'c': 'ka', 'g': 'ka', 'ng': 'ka',
        
        # Alveolar and postalveolar - tongue behind teeth
        's': 'sha', 'sh': 'sha', 'z': 'sha', 'j': 'sha', 'ch': 'sha',
        
        # Liquids and glides - transitional sounds
        'l': 'ih', 'r': 'ih', 'n': 'ih', 'w': 'oo', 'y': 'ih', 'h': 'ih',
        
        # Common consonant clusters
        'bl': 'pa', 'br': 'pa', 'cl': 'ka', 'cr': 'ka', 'dr': 'ta', 'fl': 'fa',
        'fr': 'fa', 'gl': 'ka', 'gr': 'ka', 'pl': 'pa', 'pr': 'pa', 'sk': 'ka',
        'sl': 'sha', 'sm': 'ma', 'sn': 'ih', 'sp': 'pa', 'st': 'ta', 'sw': 'sha',
        'th': 'tha', 'tr': 'ta', 'tw': 'ta', 'wh': 'oo', 'wr': 'oo',
    }
    
    # Process text word by word for natural timing
    words = text.lower().split()
    viseme_sequence: list[AllowedViseme] = []
    
    for word_idx, word in enumerate(words):
        # Add natural pause between words (not for first word)
        if viseme_sequence and word_idx > 0:
            viseme_sequence.append("pause")
        
        # Enhanced syllable-like breakdown with better timing
        i = 0
        while i < len(word):
            matched = False
            
            # Try longer patterns first for better phonetic accuracy
            for pattern_len in [4, 3, 2, 1]:
                if i + pattern_len <= len(word):
                    chunk = word[i:i+pattern_len]
                    if chunk in phoneme_to_viseme:
                        viseme_sequence.append(phoneme_to_viseme[chunk])  # type: ignore[arg-type]
                        i += pattern_len
                        matched = True
                        break
            
            if not matched:
                # Default to ih for unknown characters (neutral transition)
                viseme_sequence.append("ih")
                i += 1
    
    # Enhanced post-processing for maximum visual continuity
    if not viseme_sequence:
        return ["pause"]
    
    # Apply sophisticated transition logic
    smooth_sequence = _apply_smooth_transitions(viseme_sequence)
    
    # Ensure ending in neutral state
    if smooth_sequence and smooth_sequence[-1] not in ("ee", "ih"):
        smooth_sequence.append("ih")
    
    return smooth_sequence


def _apply_smooth_transitions(visemes: list[AllowedViseme]) -> list[AllowedViseme]:
    """Apply intelligent transition logic using ih/ee as bridges."""
    if len(visemes) <= 1:
        return visemes
    
    smooth_sequence = [visemes[0]]
    
    for i in range(1, len(visemes)):
        prev, curr = smooth_sequence[-1], visemes[i]
        
        # Skip redundant consecutive visemes
        if prev == curr:
            continue
        
        # Insert bridge viseme for extreme jumps
        if _is_extreme_jump(prev, curr):
            # Choose best bridge based on visual similarity
            if curr in ("ah", "oh", "oo") and prev in ("ee", "ih"):
                smooth_sequence.append("ih")  # Neutral transition
            elif curr in ("ee", "ih") and prev in ("ah", "oh", "oo"):
                smooth_sequence.append("ih")  # Neutral transition
            elif prev in ("pa", "ma", "fa") and curr in ("pa", "ma", "fa"):
                # Similar bilabial sounds - minimal transition needed
                pass
            else:
                smooth_sequence.append("ih")  # Default neutral bridge
        
        smooth_sequence.append(curr)
    
    return smooth_sequence


def _insert_silence_pauses(base_visemes: list[AllowedViseme], silence_segments: list[tuple[float, float]], total_duration: float) -> list[AllowedViseme]:
    """Insert pause clips at detected silence locations for seamless continuity."""
    if not silence_segments:
        return base_visemes
    
    # Calculate approximate timing for each viseme
    base_duration_per_viseme = total_duration / len(base_visemes) if base_visemes else 0.54
    
    enhanced_visemes = []
    viseme_idx = 0
    current_time = 0.0
    
    for silence_start, silence_end in silence_segments:
        # Add visemes that occur before this silence
        while viseme_idx < len(base_visemes) and current_time < silence_start:
            enhanced_visemes.append(base_visemes[viseme_idx])
            current_time += base_duration_per_viseme
            viseme_idx += 1
        
        # Insert pause clip for silence duration
        silence_duration = silence_end - silence_start
        if silence_duration >= 0.1:  # Only insert pause for significant silence
            enhanced_visemes.append("pause")
            current_time += silence_duration
    
    # Add remaining visemes after last silence
    while viseme_idx < len(base_visemes):
        enhanced_visemes.append(base_visemes[viseme_idx])
        viseme_idx += 1
    
    return enhanced_visemes if enhanced_visemes else base_visemes


def _calculate_precise_durations(visemes: list[AllowedViseme], total_duration: float, silence_segments: list[tuple[float, float]]) -> list[float]:
    """Calculate precise segment durations matching audio timing."""
    if not visemes:
        return []
    
    # Count pause visemes for special handling
    pause_count = visemes.count("pause")
    active_visemes = len(visemes) - pause_count
    
    if active_visemes == 0:
        # All pauses - distribute evenly
        return [total_duration / len(visemes)] * len(visemes)
    
    # Calculate total silence duration with error handling
    total_silence = sum(end - start for start, end in silence_segments) if silence_segments else 0
    
    # Calculate duration for active visemes and pauses
    active_duration = max(total_duration - total_silence, 0.1)  # Ensure positive
    pause_duration = total_silence / pause_count if pause_count > 0 else 0.1
    active_duration_per_viseme = active_duration / active_visemes if active_visemes > 0 else 0.54
    
    durations = []
    for viseme in visemes:
        if viseme == "pause":
            # Use actual detected silence duration or fallback
            durations.append(max(pause_duration, 0.1))
        else:
            # Add slight variation for natural timing
            jitter = random.uniform(0.9, 1.1)
            durations.append(max(active_duration_per_viseme * jitter, 0.1))
    
    # Normalize to ensure exact total duration
    current_total = sum(durations)
    if current_total > 0:
        scale_factor = total_duration / current_total
        durations = [d * scale_factor for d in durations]
    
    return durations


def generate_viseme_sequence(n: int) -> list[AllowedViseme]:
    seq: list[AllowedViseme] = []
    prev: AllowedViseme = random.choice(["ih", "ee", "ma", "ta", "pause"])
    rep = 1

    for _ in range(n):
        if not seq:
            seq.append(prev)
            continue
        nxt = _pick_next(prev, rep)

        # Bridge extreme jumps with ih.
        if _is_extreme_jump(prev, nxt) and prev != "ih":
            nxt = "ih"

        if nxt == prev:
            rep += 1
            if rep > 2:
                nxt = "ih"
                rep = 1
        else:
            rep = 1

        seq.append(nxt)
        prev = nxt

    # Ensure we end with ee or ih.
    if seq and seq[-1] not in ("ee", "ih"):
        seq[-1] = "ih" if seq[-1] != "ih" else "ee"
    return seq


def _build_video(
    *,
    visemes: list[AllowedViseme],
    segment_durations_s: list[float],
    audio_path: Path,
    output_path: Path,
) -> None:
    viseme_dir = _resolve_viseme_dir()
    audio_clip = AudioFileClip(str(audio_path))
    total_s = float(audio_clip.duration)

    # Create enhanced sequence with pause clips for base layer effect
    enhanced_visemes = []
    enhanced_durations = []
    
    for i, (v, target_s) in enumerate(zip(visemes, segment_durations_s, strict=True)):
        # Add pause clips between visemes for continuous base layer
        if i > 0 and v != "pause":
            enhanced_visemes.append("pause")
            enhanced_durations.append(0.05)
        
        enhanced_visemes.append(v)
        enhanced_durations.append(target_s)
    
    # Ensure ending with pause clip
    if enhanced_visemes and enhanced_visemes[-1] != "pause":
        enhanced_visemes.append("pause")
        enhanced_durations.append(0.1)

    # Build clips with dynamic speed adjustment
    clips = []
    crossfade_s = 0.03

    for i, (v, target_s) in enumerate(zip(enhanced_visemes, enhanced_durations, strict=True)):
        clip_path = viseme_dir / f"{v}.mp4"
        clip = VideoFileClip(str(clip_path), audio=False)

        # Dynamic speed adjustment for precise phoneme timing
        src_s = float(clip.duration)
        if src_s <= 0.001:
            clip.close()
            continue

        target_s = max(target_s, 0.08)  # Increase minimum duration for slower transitions
        
        # Apply overall slowdown factor for more natural speech timing
        overall_slowdown = 0.09  # 0.75x overall slowdown for more natural motion
        adjusted_target_s = target_s / overall_slowdown
        
        factor = src_s / adjusted_target_s
        
        # Allow slower playback for better timing alignment
        # More conservative range to ensure natural-looking speech
        factor = max(0.3, min(factor, 3.0))
        
        # Apply additional slowdown for non-pause visemes
        if v != "pause":
            factor *= 0.85  # Additional 15% slowdown for visemes
        
        clip = vfx.MultiplySpeed(factor=factor).apply(clip)

        # Add crossfade for smooth transitions
        if i > 0:
            clip = vfx.CrossFadeIn(crossfade_s).apply(clip)
        clips.append(clip)

    # Concatenate with pause clips ensuring continuous base layer
    final = concatenate_videoclips(clips, method="compose", padding=-crossfade_s)
    final = final.with_audio(audio_clip)
    final = final.with_duration(total_s)

    # Render final video
    final.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset=os.environ.get("MED_AVATAR_X264_PRESET", "medium"),
        threads=4,
        logger=None,
    )

    # Clean up resources
    for c in clips:
        c.close()
    final.close()
    audio_clip.close()


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    # Uvicorn reload won't pick up edits without --reload, so make sure
    # we resolve viseme dir at request time, after any file drops.
    _require_viseme_clips()

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    job_id = uuid.uuid4().hex
    audio_path = OUTPUTS_DIR / f"{job_id}.mp3"
    video_path = OUTPUTS_DIR / f"{job_id}.mp4"

    try:
        _tts_to_mp3(text, audio_path)
        duration_s = _audio_duration_s(audio_path)

        if duration_s < 0.25:
            raise HTTPException(status_code=400, detail="Generated audio is too short.")

        # Generate base viseme sequence from text
        base_visemes = _text_to_visemes(text)
        
        # Simplified approach: ensure no blank video at end by adding pause if needed
        visemes = base_visemes
        
        # Calculate segment durations to match audio length precisely
        segments = len(visemes)
        if segments == 0:
            raise HTTPException(status_code=400, detail="Failed to generate viseme sequence.")
        
        # Use simple duration calculation with pause filler in _build_video
        seg_durs = _random_segment_durations(duration_s, segments, jitter=0.1)

        _build_video(
            visemes=visemes,
            segment_durations_s=seg_durs,
            audio_path=audio_path,
            output_path=video_path,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate video: {e}") from e

    url = f"/outputs/{video_path.name}"
    return GenerateResponse(
        video_url=url,
        download_url=url,
        duration_s=float(duration_s),
        segments=int(segments),
        visemes=[str(v) for v in visemes],
    )


@app.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    p = (OUTPUTS_DIR / filename).resolve()
    if OUTPUTS_DIR not in p.parents or not p.exists():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(str(p), filename=p.name, media_type="video/mp4")

