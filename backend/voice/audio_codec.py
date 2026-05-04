"""Audio codec helpers used by Twilio media streams."""

from __future__ import annotations

import struct


MULAW_SAMPLE_RATE = 8000
MULAW_CHANNELS = 1


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert mu-law encoded bytes to 16-bit little-endian PCM."""

    mulaw_bias = 33
    pcm_samples: list[int] = []

    for byte in mulaw_bytes:
        mu = ~byte & 0xFF
        sign = mu & 0x80
        exponent = (mu >> 4) & 0x07
        mantissa = mu & 0x0F
        sample = ((mantissa << 3) + mulaw_bias) << exponent
        sample -= mulaw_bias
        if sign:
            sample = -sample
        pcm_samples.append(max(-32768, min(32767, sample)))

    return struct.pack(f"<{len(pcm_samples)}h", *pcm_samples)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit little-endian PCM bytes to mu-law bytes."""

    mulaw_max = 0x1FFF
    mulaw_bias = 33
    samples = struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes)
    mulaw_bytes = bytearray()

    for sample in samples:
        sign = 0x80 if sample < 0 else 0
        sample = min(abs(sample), mulaw_max)
        sample += mulaw_bias

        exponent = 7
        for exp in range(7, -1, -1):
            if sample >= (1 << (exp + 3)):
                exponent = exp
                break

        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        mulaw_bytes.append(mulaw_byte)

    return bytes(mulaw_bytes)


def create_wav_header(
    pcm_data: bytes,
    sample_rate: int = MULAW_SAMPLE_RATE,
    channels: int = MULAW_CHANNELS,
    bits: int = 16,
) -> bytes:
    """Create a WAV header for raw PCM data."""

    data_size = len(pcm_data)
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        data_size + 36,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * channels * bits // 8,
        channels * bits // 8,
        bits,
        b"data",
        data_size,
    )
