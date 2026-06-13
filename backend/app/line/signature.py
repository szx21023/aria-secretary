"""LINE webhook 簽章驗證。

LINE 用 channel secret 對「原始 request body」做 HMAC-SHA256、base64 後放進
X-Line-Signature header。驗證時必須拿「未經解析的 bytes」重算，所以 webhook
端點要先 await request.body() 再交給這裡，不能用已 parse 的 dict 反序列化。
"""

import base64
import hashlib
import hmac


def verify_signature(channel_secret: str, body: bytes, signature: str | None) -> bool:
    """body 的 HMAC-SHA256（base64）是否等於 header 帶來的 signature。

    用 hmac.compare_digest 做定時比較，避免以字串比較洩漏時序資訊。
    secret 未設定或 signature 缺漏一律視為不通過（不放行未簽章請求）。
    """
    if not channel_secret or not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)
