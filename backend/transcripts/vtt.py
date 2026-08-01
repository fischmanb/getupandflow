"""Minimal WEBVTT parser for Zoom transcript files.

Zoom emits one cue per utterance, with the speaker inline as ``Name: text`` (or
occasionally a ``<v Name>text</v>`` voice tag). We need two things from it: a
speaker-tagged plain-text rendering for the grading engine, and the true
duration (the end timestamp of the last cue). No third-party dependency — the
format is small and stable enough to parse directly.
"""

import re

# HH:MM:SS.mmm or MM:SS.mmm on either side of the cue-timing arrow.
_CUE_TIMING = re.compile(
    r"(?P<start>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(?P<end>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})"
)
_VOICE_TAG = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.DOTALL)
# Any remaining inline markup (e.g. <c>, <i>) is dropped from plain text.
_ANY_TAG = re.compile(r"<[^>]+>")


def _timestamp_to_seconds(stamp):
    stamp = stamp.replace(",", ".")
    parts = stamp.split(":")
    parts = [float(p) for p in parts]
    seconds = 0.0
    for value in parts:
        seconds = seconds * 60 + value
    return seconds


def parse(vtt_text):
    """Return (plain_text, duration_seconds) from raw VTT.

    plain_text is one ``Speaker: utterance`` line per cue (blank speaker when a
    cue carries none), consecutive same-speaker lines preserved as-is.
    duration_seconds is the integer end time of the last timed cue (0 if none).
    """
    if isinstance(vtt_text, bytes):
        vtt_text = vtt_text.decode("utf-8-sig", errors="replace")

    lines = vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    utterances = []
    last_end = 0.0
    i = 0
    while i < len(lines):
        line = lines[i]
        timing = _CUE_TIMING.search(line)
        if not timing:
            i += 1
            continue
        last_end = max(last_end, _timestamp_to_seconds(timing.group("end")))
        # Cue payload is the following non-blank lines until the next blank line.
        i += 1
        payload_lines = []
        while i < len(lines) and lines[i].strip():
            payload_lines.append(lines[i].strip())
            i += 1
        text = " ".join(payload_lines).strip()
        if text:
            utterances.append(_render_cue(text))

    return "\n".join(utterances), int(last_end)


def _render_cue(text):
    voice = _VOICE_TAG.search(text)
    if voice:
        speaker = voice.group(1).strip()
        body = _ANY_TAG.sub("", voice.group(2)).strip()
        return f"{speaker}: {body}" if body else speaker
    # Strip any other markup, keep Zoom's inline "Name: text" as written.
    return _ANY_TAG.sub("", text).strip()
