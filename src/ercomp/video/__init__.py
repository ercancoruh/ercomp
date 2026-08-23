"""Video playback package."""

from ercomp.video.decode import VideoError, probe
from ercomp.video.player import play_video, video_info

__all__ = ["VideoError", "play_video", "probe", "video_info"]
