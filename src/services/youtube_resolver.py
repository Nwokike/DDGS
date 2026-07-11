"""YouTube stream resolver — resolves a watch URL to a direct, playable media URL.

Ported from akili-app's production resolver: fetches the watch page + InnerTube
ANDROID player API and falls back to signature deciphering via base.js.
HTTP fetching uses ``primp`` (already a dependency) so no new packages are needed.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass

import primp

logger = logging.getLogger(__name__)

# --- Patterns for extraction ---
_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([\w-]{11})")
_H_PATTERN = re.compile(
    r'var\s+(\w+)\s*=\s*([\'"`])((?:[^\\\'"`]|\\.)+?(?:split|splice|join|reverse|length).*?)\2\s*\.split\(\s*([\'"])([^\'"]+)\4\s*\)',
    re.DOTALL,
)

# --- Decipher execution primitives ---


def _splice(buffer: list, n: int) -> list:
    return buffer[n:]


def _reverse(buffer: list, _n: int) -> list:
    buffer.reverse()
    return buffer


def _swap(buffer: list, n: int) -> list:
    idx = n % len(buffer)
    buffer[0], buffer[idx] = buffer[idx], buffer[0]
    return buffer


_DISPATCH_TABLE = {
    "splice": _splice,
    "reverse": _reverse,
    "swap": _swap,
}


class Operation:
    def __init__(self, action: str, arg: int):
        self.action = action
        self.arg = arg


class DecipherAlgorithm:
    def __init__(self, steps: list[Operation]):
        self._steps = steps

    def run(self, signature: str) -> str:
        buffer = list(signature)
        for op in self._steps:
            fn = _DISPATCH_TABLE.get(op.action)
            if fn is None:
                raise ValueError(f"Unsupported action '{op.action}'")
            buffer = fn(buffer, op.arg)
        return "".join(buffer)


# Cache for the compiled DecipherAlgorithm based on player base.js URL
_ALGO_CACHE: dict[str, DecipherAlgorithm] = {}


def parse_decipher_algo(js_code: str) -> DecipherAlgorithm:
    """Parses base.js dynamically using the XOR state-machine solver, falling back to legacy parsing if needed."""
    # 1. H-table extraction
    m = _H_PATTERN.search(js_code)
    if not m:
        logger.info("H-table not found, trying legacy parser...")
        return parse_legacy_algo(js_code)

    var_h, raw_h, delim_h = m.group(1), m.group(3), m.group(5)
    dec_h = bytes(raw_h, "utf-8").decode("unicode_escape")
    h_table = dec_h.split(delim_h)

    fwd_h = dict(enumerate(h_table))
    rev_h = {v: i for i, v in fwd_h.items()}

    try:
        # 2. Challenge block split initialization match
        # e.g., var t=x[c[S^589]](c[S^597]);
        chall_init_pattern = re.compile(
            rf"var\s+(\w+)\s*=\s*(\w+)\[{var_h}\[(\w+)\^(\d+)\]\]\({var_h}\[\w+\^\d+\]\);"
        )
        init_match = chall_init_pattern.search(js_code)
        if not init_match:
            raise ValueError("Split init statement not found")

        buf_var, sig_var, key_var, xor_val = (
            init_match.group(1),
            init_match.group(2),
            init_match.group(3),
            int(init_match.group(4)),
        )

        split_idx = rev_h.get("split")
        if split_idx is None:
            raise ValueError("'split' not in H-table")
        key_val = split_idx ^ xor_val

        join_idx = rev_h.get("join")
        if join_idx is None:
            raise ValueError("'join' not in H-table")
        join_xor = key_val ^ join_idx

        block_pattern = re.compile(
            rf"var\s+{buf_var}\s*=\s*{sig_var}\[{var_h}\[{key_var}\^{xor_val}\]\]\({var_h}\[\w+\^\w+\]\);"
            rf"(.*?)"
            rf"\w+={buf_var}\[{var_h}\[{key_var}\^{join_xor}\]\]\({var_h}\[\w+\^\w+\]\)",
            re.DOTALL,
        )
        block_match = block_pattern.search(js_code)
        if not block_match:
            raise ValueError("Could not extract challenge block body")

        block_body = block_match.group(1)

        # 3. Statements match
        # Group 1: helper object name (Nx)
        # Group 2: method name XOR value
        # Group 3: arg XOR value (if of form S^X)
        # Group 4: arg literal value (if of form X)
        stmt_pattern = re.compile(
            rf"(\w+)\[{var_h}\[{key_var}\^(\d+)\]\]\({buf_var},\s*(?:{key_var}\^(\d+)|(\d+))\)"
        )
        statements = stmt_pattern.findall(block_body)
        if not statements:
            raise ValueError("No transformation helper statements found")

        helper_name = statements[0][0]

        # 4. Helper object definition match
        helper_def_pattern = re.compile(
            rf"(?:var|const|let)\s+{helper_name}\s*=\s*\{{(.*?)\}};", re.DOTALL
        )
        def_match = helper_def_pattern.search(js_code)
        if not def_match:
            helper_def_pattern = re.compile(
                rf"{helper_name}\s*=\s*\{{(.*?)\}}", re.DOTALL
            )
            def_match = helper_def_pattern.search(js_code)

        if not def_match:
            raise ValueError(f"Definition of helper {helper_name} not found")

        def_body = def_match.group(1)

        helper_fn_pattern = re.compile(
            r"(\w+)\s*:\s*function\s*\(([^)]*)\)\s*\{(.*?)\}", re.DOTALL
        )
        helpers = {}

        rev_idx_str = f"[{rev_h.get('reverse')}]"
        splice_idx_str = f"[{rev_h.get('splice')}]"

        for name, _args, body in helper_fn_pattern.findall(def_body):
            body_clean = body.replace(" ", "").replace("\n", "")
            if "reverse" in body_clean or rev_idx_str in body_clean:
                action = "reverse"
            elif "splice" in body_clean or splice_idx_str in body_clean:
                action = "splice"
            elif "[0]=" in body_clean or "varx=R[0];R[0]=R[" in body_clean:
                action = "swap"
            else:
                if "0,K" in body_clean or "0,1" in body_clean:
                    action = "splice"
                elif "reverse" in body_clean:
                    action = "reverse"
                else:
                    action = "swap"
            helpers[name] = action

        # 5. Extract operations
        ops = []
        for helper_obj, method_xor, arg_xor, arg_literal in statements:
            if helper_obj != helper_name:
                continue
            method_idx = key_val ^ int(method_xor)
            method_name = fwd_h.get(method_idx)
            action = helpers.get(method_name)
            if not action:
                raise ValueError(f"Could not resolve method {method_name}")

            arg_val = key_val ^ int(arg_xor) if arg_xor else int(arg_literal)

            ops.append(Operation(action, arg_val))

        logger.info("Successfully parsed base.js dynamically using XOR solver!")
        return DecipherAlgorithm(ops)

    except Exception as e:
        logger.warning("XOR solver parsing failed (%s), trying legacy parser...", e)
        return parse_legacy_algo(js_code)


def parse_legacy_algo(js_code: str) -> DecipherAlgorithm:
    SPLICE_RE = re.compile(r"(\w+):function\(\w+,\w+\){\w+\.splice\(0,\w+\)}")
    REVERSE_RE = re.compile(r"(\w+):function\(\w+\){\w+\.reverse\(\)}")
    SWAP_RE = re.compile(
        r"(\w+):function\(\w+,\w+\){var \w+=\w+\[0\];\w+\[0\]=\w+\[\w+%\w+\.length\];\w+\[\w+%\w+\.length\]=\w+}"
    )
    CHALL_RE = re.compile(
        r'function\(\w+\){\w+=\w+\.split\(""\);((?:\w+\.\w+\(\w+,\d+\);)*)return \w+\.join\(""\)\};',
        re.DOTALL,
    )
    CODE_RE = re.compile(r"\w+\.(\w+)\(\w+,(\d+)\);")

    chall_match = CHALL_RE.search(js_code)
    if not chall_match:
        raise ValueError("Legacy CHALL pattern not found")

    chall_body = chall_match.group(1)
    helpers = {}
    for label, rgx in (
        ("splice", SPLICE_RE),
        ("reverse", REVERSE_RE),
        ("swap", SWAP_RE),
    ):
        m = rgx.search(js_code)
        if m:
            helpers[m.group(1)] = label

    ops = []
    for name, param in CODE_RE.findall(chall_body):
        action = helpers.get(name)
        if not action:
            raise ValueError(f"Unknown helper name: {name}")
        ops.append(Operation(action, int(param)))

    logger.info("Successfully parsed base.js using legacy solver!")
    return DecipherAlgorithm(ops)


# --- Resolving and Fetching ---


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


_QUALITY_HEIGHTS = {
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}


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
    """Pick the best format dict for the requested quality.

    Returns a normalized dict (see ``_normalize``) or None.
    """
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


async def resolve_youtube(
    url: str, preferred_quality: str = "best"
) -> VideoStream | None:
    """Resolve a YouTube URL to a direct, playable media stream.

    Uses the InnerTube ANDROID client context (returns unthrottled links) and
    falls back to signature deciphering when a format ships a ``signatureCipher``.
    Returns ``None`` if resolution is not possible (caller should fall back).
    """
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
        except Exception as e:
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
        except Exception as e:
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
            except Exception as e:
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
