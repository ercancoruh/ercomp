"""Background audio via ffplay or bundled ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ercomp.tools import ffmpeg_bin


class AudioPlayer:
    """Play file audio with optional seek / volume / mute."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._helper: subprocess.Popen[bytes] | None = None
        self.path: Path | None = None
        self.volume: float = 1.0
        self.mute: bool = False
        self._start: float = 0.0

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("ffplay") or ffmpeg_bin())

    def play(
        self,
        path: Path,
        *,
        start: float = 0.0,
        volume: float = 1.0,
        mute: bool = False,
    ) -> None:
        self.stop()
        self.path = path
        self.volume = volume
        self.mute = mute
        self._start = max(0.0, start)
        vol = 0.0 if mute else max(0.0, min(2.0, volume))

        ffplay = shutil.which("ffplay")
        if ffplay:
            self._proc = self._popen(
                [
                    ffplay,
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    "-ss",
                    f"{self._start:.3f}",
                    "-af",
                    f"volume={vol}",
                    str(path),
                ]
            )
            return

        ffmpeg = ffmpeg_bin()
        if not ffmpeg:
            return

        base = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{self._start:.3f}",
            "-i",
            str(path),
            "-vn",
            "-af",
            f"volume={vol}",
        ]

        if sys.platform == "darwin":
            sinks: list[list[str]] = [[*base, "-f", "coreaudio", "default"]]
        else:
            sinks = [
                [*base, "-f", "pulse", "ercomp"],
                [*base, "-f", "alsa", "default"],
            ]

        for cmd in sinks:
            proc = self._popen(cmd)
            if proc is not None:
                self._proc = proc
                return

        # Last resort: wav → aplay/paplay/afplay
        player = shutil.which("aplay") or shutil.which("paplay") or shutil.which("afplay")
        if not player:
            return
        try:
            ff = subprocess.Popen(
                [*base, "-f", "wav", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            play_cmd = [player, "-"] if "afplay" not in player else [player, "/dev/stdin"]
            play = subprocess.Popen(
                play_cmd,
                stdin=ff.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ff.stdout:
                ff.stdout.close()
            self._helper = ff
            self._proc = play
        except OSError:
            self.stop()

    @staticmethod
    def _popen(cmd: list[str]) -> subprocess.Popen[bytes] | None:
        try:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return None

    def stop(self) -> None:
        for attr in ("_proc", "_helper"):
            proc = getattr(self, attr)
            if proc is None:
                continue
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
            setattr(self, attr, None)

    def set_mute(self, mute: bool) -> None:
        if self.path is None:
            self.mute = mute
            return
        self.mute = mute
        self.play(self.path, start=self._start, volume=self.volume, mute=mute)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(2.0, volume))
        if self.path is None:
            return
        self.play(self.path, start=self._start, volume=self.volume, mute=self.mute)

    def seek(self, start: float) -> None:
        if self.path is None:
            return
        self.play(self.path, start=start, volume=self.volume, mute=self.mute)
