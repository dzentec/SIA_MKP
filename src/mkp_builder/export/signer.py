"""Ed25519 digital signature generation and verification (RFC 8032 / Invariant I13).

100% pure Python implementation with zero native dependencies, ensuring 100% offline
Windows/Linux compatibility without CFFI compilation errors.
"""

from __future__ import annotations

import hashlib
import os

# Field and Curve constants for Ed25519 (RFC 8032)
_B = 256
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _inv(x: int) -> int:
    return pow(x, _Q - 2, _Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_BX = _xrecover(_BY)
_B_POINT = [_BX % _Q, _BY % _Q]


def _edwards(P: list[int], Q: list[int]) -> list[int]:
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _D * x1 * x2 * y1 * y2)
    return [x3 % _Q, y3 % _Q]


def _scalarmult(P: list[int], e: int) -> list[int]:
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _encodeint(y: int) -> bytes:
    bits = [(y >> i) & 1 for i in range(_B)]
    return bytes(sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(_B // 8))


def _encodepoint(P: list[int]) -> bytes:
    x, y = P
    bits = [(y >> i) & 1 for i in range(_B - 1)] + [x & 1]
    return bytes(sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(_B // 8))


def _bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _decodeint(s: bytes) -> int:
    return sum(2**i * _bit(s, i) for i in range(0, _B))


def _decodepoint(s: bytes) -> list[int] | None:
    y = sum(2**i * _bit(s, i) for i in range(0, _B - 1))
    x = _xrecover(y)
    if x & 1 != _bit(s, _B - 1):
        x = _Q - x
    P = [x, y]
    if (y * y - x * x - 1 - _D * x * x * y * y) % _Q != 0:
        return None
    return P


def _h(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _secret_expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("Secret key must be 32 bytes")
    h = _h(secret)
    a = 2**(_B - 2) + sum(2**i * _bit(h, i) for i in range(3, _B - 2))
    RH = bytes(h[i] for i in range(_B // 8, _B // 4))
    return a, RH


def public_key_from_private(private_key_bytes: bytes) -> bytes:
    """Derive 32-byte public key from 32-byte private key."""
    a, _ = _secret_expand(private_key_bytes)
    A = _scalarmult(_B_POINT, a)
    return _encodepoint(A)


def sign(message: bytes, private_key_bytes: bytes) -> bytes:
    """Sign message bytes using 32-byte private key. Returns 64-byte signature."""
    a, RH = _secret_expand(private_key_bytes)
    A = _scalarmult(_B_POINT, a)
    A_bytes = _encodepoint(A)
    r = _decodeint(_h(RH + message))
    R = _scalarmult(_B_POINT, r)
    R_bytes = _encodepoint(R)
    k = _decodeint(_h(R_bytes + A_bytes + message))
    S = (r + k * a) % _L
    return R_bytes + _encodeint(S)


def verify(signature: bytes, message: bytes, public_key_bytes: bytes) -> bool:
    """Verify 64-byte signature on message bytes using 32-byte public key."""
    if len(signature) != 64 or len(public_key_bytes) != 32:
        return False
    R_bytes = signature[:32]
    S_bytes = signature[32:]
    A = _decodepoint(public_key_bytes)
    if A is None:
        return False
    R = _decodepoint(R_bytes)
    if R is None:
        return False
    S = _decodeint(S_bytes)
    if S >= _L:
        return False
    k = _decodeint(_h(R_bytes + public_key_bytes + message))
    SB = _scalarmult(_B_POINT, S)
    RAk = _edwards(R, _scalarmult(A, k))
    return SB[0] == RAk[0] and SB[1] == RAk[1]


# Default development signing key for MKP Service builder
DEFAULT_DEV_PRIVATE_KEY_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
DEFAULT_DEV_PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"


def sign_data_hex(data: bytes, private_key_hex: str = DEFAULT_DEV_PRIVATE_KEY_HEX) -> str:
    """Sign data and return hex-encoded signature."""
    priv_bytes = bytes.fromhex(private_key_hex)
    sig_bytes = sign(data, priv_bytes)
    return sig_bytes.hex()


def verify_data_hex(data: bytes, signature_hex: str, public_key_hex: str = DEFAULT_DEV_PUBLIC_KEY_HEX) -> bool:
    """Verify signature on data with hex-encoded keys."""
    try:
        sig_bytes = bytes.fromhex(signature_hex)
        pub_bytes = bytes.fromhex(public_key_hex)
        return verify(sig_bytes, data, pub_bytes)
    except Exception:
        return False
