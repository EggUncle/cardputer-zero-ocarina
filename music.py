"""Streaming harmonic melody estimation and Switch 2 ocarina arrangement."""
from itertools import groupby
import numpy as np
import soundfile as sf

BASE = [(62, "L"), (65, "R"), (69, "A"), (71, "Y"), (74, "X")]
LOW, HIGH = 59, 77
STEP = .020


def transcribe(path, lead_range=(45, 89)):
    """Return (start_ms, end_ms, MIDI pitch) for the prominent melodic line."""
    pitches = np.arange(lead_range[0], lead_range[1] + 1)
    hz = 440 * 2 ** ((pitches - 69) / 12)
    with sf.SoundFile(path) as audio:
        rate = audio.samplerate
        hop = max(1, round(rate * STEP))
        size = 4 * hop
        fft = 1 << (size * 2 - 1).bit_length()
        window = np.hanning(size)
        bins = np.rint(hz[:, None] * np.arange(1, 7) * fft / rate).astype(int)
        bins = np.clip(bins, 1, fft // 2 - 1)
        # Favour the upper melodic voice when bass and melody compete.
        # Penalise overtones of a candidate's subharmonics before applying
        # this preference so an isolated low instrument keeps its octave.
        register_weight = np.clip((hz / 260.0) ** 1.6, .32, 1.08)
        sub_bins = np.clip(np.rint(hz[:, None] / [2, 3] * fft / rate).astype(int), 1, fft//2-1)
        weights = np.array([1, .48, .32, .20, .13, .09])
        transitions = -.08 * np.minimum(abs(pitches[:, None] - pitches), 12)
        transitions -= .35 * (transitions != 0)
        score = np.zeros(len(pitches))
        back, voiced, attacks = [], [], []
        prev_energy = 0
        # Pad both ends so the centre of frame i is at i * hop.
        pending = np.zeros((size // 2, audio.channels), dtype='float32')
        duration_ms = round(1000 * len(audio) / rate)
        frames = (len(audio) + hop - 1) // hop
        while len(back) < frames:
            chunk = audio.read(64 * hop, dtype='float32', always_2d=True)
            if not len(chunk):
                chunk = np.zeros((size, audio.channels), dtype='float32')
            pending = np.concatenate((pending, chunk))
            offset = 0
            while offset + size <= len(pending) and len(back) < frames:
                frame = pending[offset:offset + size]
                offset += hop
                energy = np.mean(frame * frame)
                spectrum = abs(np.fft.rfft(frame * window[:, None], n=fft, axis=0)).mean(axis=1)
                partials = np.maximum.reduce([spectrum[bins + d] for d in (-1, 0, 1)])
                subharmonics = spectrum[sub_bins].max(axis=1)
                # Only suppress harmonics supported by a stronger lower partial.
                overtone = np.maximum(subharmonics - partials[:, 0], 0)
                salience = np.maximum(partials @ weights - .52 * overtone, 0) * register_weight
                peak = max(salience.max(), 1e-9)
                active = energy > 1e-7 and peak > 6 * (np.median(spectrum) + 1e-7)
                voiced.append(active)
                attacks.append(energy > max(prev_energy * 3.0, 2e-7))
                prev_energy = energy
                paths = score[:, None] + transitions
                back.append(paths.argmax(axis=0).astype('uint8'))
                score = paths.max(axis=0) + (salience / peak if active else 0)
                score -= score.max()
            pending = pending[offset:]
    index = int(score.argmax())
    labels = []
    for i in reversed(range(len(back))):
        labels.append(int(pitches[index]) if voiced[i] else None)
        index = int(back[i][index])
    labels.reverse()
    notes = []
    start = 0
    for pitch, group in groupby(labels):
        end = start + sum(1 for _ in group)
        if pitch is not None:
            boundaries = [start]
            for i in range(start + 3, end - 2):
                if attacks[i] and i - boundaries[-1] >= 4:
                    boundaries.append(i)
            for a, b in zip(boundaries, boundaries[1:] + [end]):
                if b - a >= 3:
                    notes.append((round(1000*a*hop/rate), min(round(1000*b*hop/rate), duration_ms), pitch))
        start = end
    if not notes:
        raise ValueError("没有检测到持续的旋律音")
    # A sustained bass can surface for a few frames during a lead articulation.
    # Treat a brief octave-plus drop between nearby, sustained notes as a rest.
    cleaned = []
    for i, (a, b, pitch) in enumerate(notes):
        if 0 < i < len(notes)-1 and b-a <= 80:
            left, right = notes[i-1], notes[i+1]
            if (min(left[2], right[2]) - pitch > 12 and abs(left[2]-right[2]) <= 7
                    and left[1]-left[0] >= 160 and right[1]-right[0] >= 160
                    and a-left[1] <= 40 and right[0]-b <= 40):
                continue
        cleaned.append((a, b, pitch))
    return cleaned


def arrange(notes):
    def cost(shift):
        overflow = sum((b-a)*max(LOW-p-shift, p+shift-HIGH, 0) for a,b,p in notes)
        return overflow, abs(shift) % 12 != 0, abs(shift)
    shift = min(range(-36, 37), key=cost)
    events = []
    folded = 0
    for start, end, pitch in notes:
        target = pitch + shift
        while target < LOW:
            target += 12
        while target > HIGH:
            target -= 12
        folded += target != pitch + shift
        base, button = min(BASE, key=lambda v: abs(v[0] - target))
        delta = target - base
        direction = "UP" if delta > 0 else "DOWN"
        mods = []
        if abs(delta) % 2:
            mods.append("DPAD_" + direction)
        if abs(delta) >= 2:
            mods.append("LSTICK_" + direction)
        events.append((start, end, target, mods, button))
    return events, shift, folded


def write_audition(path, events):
    """Render a small mono WAV with the same note-on and release schedule as play()."""
    rate = 16000
    cursor = 0
    block_size = 4096
    silence = np.zeros(block_size, dtype=np.float32)
    # Open exclusively to protect existing songs or earlier auditions.
    with open(path, "xb") as stream, sf.SoundFile(stream, mode="w", samplerate=rate,
                                                   channels=1, format="WAV", subtype="PCM_16") as out:
        for start, end, target, _, _ in events:
            first = round(start * rate / 1000)
            last = round((end - 25) * rate / 1000)
            while cursor < first:
                count = min(block_size, first - cursor)
                out.write(silence[:count])
                cursor += count
            frequency = 440 * 2 ** ((target - 69) / 12)
            while cursor < last:
                samples = np.arange(cursor, min(cursor + block_size, last))
                age = (samples - first) / rate
                envelope = np.minimum(1, np.minimum(age / .008, (last - samples) / (.008 * rate)))
                out.write(.35 * envelope * np.sin(2 * np.pi * frequency * age))
                cursor += len(samples)
