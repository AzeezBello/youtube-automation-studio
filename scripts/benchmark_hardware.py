#!/usr/bin/env python3
"""Run local hardware probe and recommend a YouTube Automation Studio resource profile."""

from __future__ import annotations

import json
from dataclasses import asdict

from youtube_studio.config.hardware import HardwareProbe


def main() -> None:
    report = HardwareProbe().run()
    payload = asdict(report)
    payload["recommended_profile"] = report.recommended_profile.value
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
