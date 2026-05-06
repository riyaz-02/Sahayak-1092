"""Audio codec helpers used by Twilio media streams."""

from __future__ import annotations

import audioop
import struct


MULAW_SAMPLE_RATE = 8000
MULAW_CHANNELS = 1


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert mu-law encoded bytes to 16-bit little-endian PCM (G.711).

    Uses audioop.ulaw2lin for standards-compliant ITU-T G.711 decoding.
    """
    # audioop.ulaw2lin returns big-endian PCM; convert to little-endian
    pcm_be = audioop.ulaw2lin(mulaw_bytes, 2)
    # audioop on most platforms already returns native (little-endian on x86)
    return pcm_be


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit little-endian PCM bytes to mu-law bytes (G.711).

    Uses audioop.lin2ulaw for standards-compliant ITU-T G.711 encoding.
    The previous custom encoder was missing the 16-bit -> 14-bit right-shift
    (>> 2) before the 0x1FFF clip, causing hard clipping of the top 75% of
    the PCM dynamic range and severe crackling in Twilio playback.
    """
    return audioop.lin2ulaw(pcm_bytes, 2)


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
