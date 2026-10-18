"""
本地凭据加解密：使用 Fernet 对称加密，密钥本地保存。
说明：这是桌面工具，密钥保存在 data/.secret.key，
         与数据库同目录，提供"防肉眼直接看到明文"的能力；
         若机器被他人完全控制，仍应自行保管好 data 目录。
"""
import os
from cryptography.fernet import Fernet, InvalidToken

from config import KEY_PATH


def _load_or_create_key() -> bytes:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_PATH, "wb") as f:
        f.write(key)
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(plain_text: str) -> str:
    if plain_text is None or plain_text == "":
        return ""
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("ascii")


def decrypt(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        return _fernet.decrypt(cipher_text.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""
