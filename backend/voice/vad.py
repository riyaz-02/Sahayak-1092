"""Voice activity detection helpers."""

from __future__ import annotations

import struct

from backend.voice.audio_codec import mulaw_to_pcm16


def normalized_energy_from_mulaw(audio_chunk: bytes) -> float:
    """Return normalized RMS energy for a mu-law audio chunk."""

    if not audio_chunk:
        return 0.0
    pcm_chunk = mulaw_to_pcm16(audio_chunk)
    if not pcm_chunk:
        return 0.0
    samples = struct.unpack(f"<{len(pcm_chunk) // 2}h", pcm_chunk)
    if not samples:
        return 0.0
    rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
    return rms / 32768.0
