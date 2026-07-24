from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_H_PATTERN = re.compile(
    r'var\s+(\w+)\s*=\s*([\'"`])((?:[^\\\'"`]|\\.)+?(?:split|splice|join|reverse|length).*?)\2\s*\.split\(\s*([\'"])([^\'"]+)\4\s*\)',
    re.DOTALL,
)


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


_ALGO_CACHE: dict[str, DecipherAlgorithm] = {}


def parse_decipher_algo(js_code: str) -> DecipherAlgorithm:
    """Parses base.js dynamically using the XOR state-machine solver, falling back to legacy parsing if needed."""
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

        stmt_pattern = re.compile(
            rf"(\w+)\[{var_h}\[{key_var}\^(\d+)\]\]\({buf_var},\s*(?:{key_var}\^(\d+)|(\d+))\)"
        )
        statements = stmt_pattern.findall(block_body)
        if not statements:
            raise ValueError("No transformation helper statements found")

        helper_name = statements[0][0]

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

    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
    ) as e:
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
