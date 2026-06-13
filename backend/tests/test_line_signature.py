"""LINE webhook 簽章驗證：對的放行、錯的擋下、缺 secret/簽章一律不放行。"""

import base64
import hashlib
import hmac

from app.line.signature import verify_signature

_SECRET = "my-channel-secret"
_BODY = b'{"events":[]}'


def _sign(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_valid_signature_passes():
    assert verify_signature(_SECRET, _BODY, _sign(_SECRET, _BODY)) is True


def test_wrong_secret_fails():
    assert verify_signature(_SECRET, _BODY, _sign("other-secret", _BODY)) is False


def test_tampered_body_fails():
    sig = _sign(_SECRET, _BODY)
    assert verify_signature(_SECRET, b'{"events":[1]}', sig) is False


def test_missing_signature_fails():
    assert verify_signature(_SECRET, _BODY, None) is False


def test_empty_secret_fails():
    # secret 未設定時不放行任何請求（即便對方湊得出某個簽章）
    assert verify_signature("", _BODY, _sign("", _BODY)) is False
