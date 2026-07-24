from __future__ import annotations

import re
from dataclasses import dataclass

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([\w-]{11})")

_QUALITY_HEIGHTS = {
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}


@dataclass
class VideoStream:
    """A resolved, directly-downloadable video stream."""

    url: str
    mime_type: str
    ext: str
    quality_label: str
    itag: int
    height: int


def extract_video_id(url: str) -> str | None:
    """Extracts the 11-character YouTube video ID from a URL."""
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def is_youtube_url(url: str) -> bool:
    """Returns True if the URL points at YouTube (watch / short / embed / youtu.be)."""
    u = (url or "").lower()
    return "youtube.com" in u or "youtu.be" in u or "youtube-nocookie.com" in u


def _ext_from_mime(mime_type: str) -> str:
    mt = (mime_type or "").lower()
    if "webm" in mt:
        return "webm"
    if "mp4" in mt or "m4v" in mt:
        return "mp4"
    if "ogg" in mt or "theora" in mt:
        return "ogv"
    if "3gp" in mt:
        return "3gp"
    return "mp4"


def _norm_height(fmt: dict) -> int:
    h = fmt.get("height")
    if isinstance(h, int):
        return h
    ql = fmt.get("qualityLabel", "") or ""
    m = re.search(r"(\d{3,4})p", ql)
    if m:
        return int(m.group(1))
    return 0


def _pick_format(player_response: dict, preferred_quality: str):
    """Pick the best format dict for the requested quality."""
    streaming = player_response.get("streamingData", {})
    formats = streaming.get("formats", [])
    adaptive = streaming.get("adaptiveFormats", [])
    all_fmts = formats + adaptive
    if not all_fmts:
        return None

    norm = []
    for f in all_fmts:
        norm.append(
            {
                "fmt": f,
                "itag": f.get("itag"),
                "mime": f.get("mimeType", ""),
                "height": _norm_height(f),
                "quality_label": f.get("qualityLabel", "") or f.get("quality", ""),
                "has_url": bool(f.get("url")),
                "has_cipher": bool(f.get("signatureCipher") or f.get("cipher")),
                "ext": _ext_from_mime(f.get("mimeType", "")),
            }
        )

    def mp4_first(items):
        mp4 = [n for n in items if n["ext"] == "mp4"]
        return mp4 + [n for n in items if n["ext"] != "mp4"]

    def by_height_desc(items):
        return sorted(items, key=lambda n: n["height"], reverse=True)

    prog = mp4_first([n for n in norm if n["has_url"]])
    any_fmt = mp4_first(norm)

    if preferred_quality == "best":
        for itag in (22, 18):
            for n in prog:
                if n["itag"] == itag:
                    return n
        if prog:
            return by_height_desc(prog)[0]
        return by_height_desc(any_fmt)[0]

    target = _QUALITY_HEIGHTS.get(preferred_quality)
    if not target:
        return _pick_format(player_response, "best")

    le = [n for n in norm if n["height"] and n["height"] <= target]
    if le:
        exact = [n for n in le if n["height"] == target]
        pool = (
            mp4_first(by_height_desc(exact)) if exact else mp4_first(by_height_desc(le))
        )
    else:
        gt = [n for n in norm if n["height"]]
        pool = mp4_first(by_height_desc(gt)) if gt else any_fmt

    prog_pool = [n for n in pool if n["has_url"]]
    return (prog_pool or pool)[0]
