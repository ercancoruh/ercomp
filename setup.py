"""setuptools install hook — download portable mpv on Windows after install."""

from __future__ import annotations

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


def _maybe_fetch_mpv() -> None:
    try:
        from ercomp.mpv_vendor import install_mpv_for_package

        install_mpv_for_package()
    except Exception as e:  # noqa: BLE001
        print(f"note: mpv auto-download skipped ({e})")


class PostInstall(install):
    def run(self) -> None:
        install.run(self)
        _maybe_fetch_mpv()


class PostDevelop(develop):
    def run(self) -> None:
        develop.run(self)
        _maybe_fetch_mpv()


setup(
    cmdclass={
        "install": PostInstall,
        "develop": PostDevelop,
    },
)
