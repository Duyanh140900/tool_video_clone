"""Decode SnapTik/Tikmate obfuscated JS payload (from community reverse-engineering)."""

from __future__ import annotations

from ast import literal_eval
from re import findall
from typing import Union

_ALPHA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/"


def _search(d: Union[str, list], q: str) -> int:
    try:
        return d.index(q)
    except Exception:
        return -1


def _reduces(function, iterable, initializer=None) -> int:
    it = iter(iterable)
    if initializer is None:
        value = next(it)
    else:
        value = function(initializer, next(it), 0)
    for index, element in enumerate(it, 1):
        value = function(value, element, index)
    return value


def _main(d, e, f):
    g = list(_ALPHA)
    h = g[0:e]
    i = g[0:f]

    def freduce(a, b, c):
        if _search(h, b) != -1:
            a += _search(h, b) * (e**c)
            return a

    j = _reduces(freduce, list(d)[::-1], 0)
    k = ""
    while j > 0:
        k = i[j % f] + k
        j = int((j - (j % f)) / f)
    return int(k) or 0


def decoder(h, u, n, t, e, r="") -> str:
    out = ""
    i = 0
    while i < len(h):
        s = ""
        while h[i] != n[e]:
            s += h[i]
            i += 1
        for j in range(len(n)):
            s = s.replace(n[j], str(j))
        out += chr(_main(s, e, 10) - t)
        i += 1
    return out


def decode_snaptik_payload(text: str) -> str:
    """Extract decoder(...) args from response text and return decoded HTML/JS."""
    matches = findall(r'\(\".*?,.*?,.*?,.*?,.*?.*?\)', text)
    if not matches:
        raise RuntimeError("SnapTik response did not contain decodable payload")
    args = literal_eval(matches[0])
    return decoder(*args)
