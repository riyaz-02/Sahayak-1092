"""Voice stream handler entrypoint.

The concrete Twilio WebSocket implementation remains in `backend.media_stream`
so existing routes and Twilio configuration continue to work.
"""

from backend.media_stream import handle_media_stream

__all__ = ["handle_media_stream"]
