from __future__ import annotations

import base64
import json
import logging
import re
import urllib.parse

import primp

from services.youtube.cipher_solver import _ALGO_CACHE, parse_decipher_algo
from services.youtube.format_parser import (
    VideoStream,
    _pick_format,
    extract_video_id,
)

logger = logging.getLogger(__name__)


async def resolve_youtube(
    url: str, preferred_quality: str = "best"
) -> VideoStream | None:
    """Resolve a YouTube URL to a direct, playable media stream."""
    video_id = extract_video_id(url)
    if not video_id:
        logger.info("No YouTube video ID found in URL: %s", url)
        return None

    logger.info(
        "Resolving YouTube stream for video ID: %s (quality=%s)",
        video_id,
        preferred_quality,
    )

    api_key = base64.b64decode(
        "QUl6YVN5QU9fRkosU2xxVThRNFNURUhMR0NpbHdfWTlfMTFxY1c4"
    ).decode("utf-8")
    visitor_data = None
    js_url = None
    player_response = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with primp.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            r = await client.get(watch_url, headers=headers, follow_redirects=True)
            if r.status_code == 200:
                html = r.text

                key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
                if key_match:
                    api_key = key_match.group(1)

                visitor_match = re.search(r'"visitorData"\s*:\s*"([^"]+)"', html)
                if visitor_match:
                    visitor_data = visitor_match.group(1)

                js_match = re.search(r'src="([^"]+/base\.js)"', html)
                if not js_match:
                    js_match = re.search(r'"jsUrl"\s*:\s*"([^"]+)"', html)
                if not js_match:
                    js_match = re.search(
                        r"\/s\/player\/[\w-]+\/player_ias.vflset\/[\w-]+\/base\.js",
                        html,
                    )
                    if js_match:
                        js_url = f"https://www.youtube.com{js_match.group(0)}"
                else:
                    js_url = js_match.group(1)
                    if js_url.startswith("//"):
                        js_url = "https:" + js_url
                    elif js_url.startswith("/"):
                        js_url = "https://www.youtube.com" + js_url

                json_match = re.search(
                    r"ytInitialPlayerResponse\s*=\s*({.+?})\s*;", html
                )
                if not json_match:
                    json_match = re.search(
                        r"var\s+ytInitialPlayerResponse\s*=\s*({.+?});", html
                    )
                if json_match:
                    player_response = json.loads(json_match.group(1))
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            logger.warning("Failed to extract details from watch page: %s", e)

        player_url = f"https://www.youtube.com/youtubei/v1/player?key={api_key}"
        payload = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "21.02.35",
                    "androidSdkVersion": 30,
                    "platform": "MOBILE",
                    "osName": "Android",
                    "osVersion": "11",
                }
            },
        }
        if visitor_data:
            payload["context"]["client"]["visitorData"] = visitor_data

        api_headers = {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip",
        }

        try:
            logger.info("Calling InnerTube player API with ANDROID client...")
            res = await client.post(
                player_url, json=payload, headers=api_headers, follow_redirects=True
            )
            if res.status_code == 200:
                player_response = res.json()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            logger.warning("InnerTube ANDROID player request failed: %s", e)

        if not player_response:
            logger.error("No player response available, cannot resolve")
            return None

        playability = player_response.get("playabilityStatus", {})
        if playability.get("status") not in (None, "OK"):
            logger.warning(
                "Playability warning: %s - %s",
                playability.get("status"),
                playability.get("reason"),
            )

        target = _pick_format(player_response, preferred_quality)
        if not target:
            logger.error("No stream format found in player response")
            return None

        fmt = target["fmt"]
        logger.info(
            "Selected format: itag=%s, mime=%s, height=%s",
            target["itag"],
            target["mime"],
            target["height"],
        )

        direct_url = fmt.get("url")
        if direct_url:
            logger.info("Format contains direct URL (no cipher decryption needed)")
            return VideoStream(
                url=direct_url,
                mime_type=target["mime"],
                ext=target["ext"],
                quality_label=target["quality_label"],
                itag=target["itag"],
                height=target["height"],
            )

        cipher = fmt.get("signatureCipher") or fmt.get("cipher")
        if not cipher:
            logger.error("Format has neither url nor signatureCipher")
            return None

        params = urllib.parse.parse_qs(cipher)
        scrambled_sig = params.get("s", [""])[0]
        base_url = params.get("url", [""])[0]
        sig_param = params.get("sp", ["sig"])[0]

        if not scrambled_sig or not base_url:
            logger.error("Failed to parse signatureCipher parameters")
            return None

        if not js_url:
            logger.error("base.js URL is missing, cannot decrypt signature")
            return None

        algo = _ALGO_CACHE.get(js_url)
        if not algo:
            try:
                logger.info(
                    "Downloading base.js to compile decipher algorithm: %s", js_url
                )
                js_res = await client.get(
                    js_url, headers=headers, follow_redirects=True
                )
                if js_res.status_code == 200:
                    algo = parse_decipher_algo(js_res.text)
                    _ALGO_CACHE[js_url] = algo
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
            ) as e:
                logger.error("Failed to compile decipher algorithm from base.js: %s", e)

        if not algo:
            logger.error("Decipher algorithm is None, cannot resolve")
            return None

        logger.info("Deciphering signature cipher...")
        decrypted_sig = algo.run(scrambled_sig)

        parsed_url = urllib.parse.urlparse(base_url)
        query = urllib.parse.parse_qsl(parsed_url.query)
        query.append((sig_param, decrypted_sig))
        if not any(k == "ratebypass" for k, _ in query):
            query.append(("ratebypass", "yes"))

        resolved_url = parsed_url._replace(query=urllib.parse.urlencode(query)).geturl()
        return VideoStream(
            url=resolved_url,
            mime_type=target["mime"],
            ext=target["ext"],
            quality_label=target["quality_label"],
            itag=target["itag"],
            height=target["height"],
        )
