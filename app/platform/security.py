import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',',':'))
def secret(): return secrets.token_urlsafe(32)
def password_hash(value):
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${derived}'
def password_ok(value, encoded):
    try:
        _, iterations, salt, expected = encoded.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError): return False

class Vault:
    def __init__(self, key):
        self.key = key
        self.aes = AESGCM(key)
    def seal(self, value):
        nonce = os.urandom(12)
        return base64.urlsafe_b64encode(nonce + self.aes.encrypt(nonce, value.encode(), b'ajo-v1')).decode()
    def open(self, value):
        raw = base64.urlsafe_b64decode(value)
        return self.aes.decrypt(raw[:12], raw[12:], b'ajo-v1').decode()
    def fingerprint(self, value):
        return hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()

def totp(secret_value, counter=None):
    counter = int(time.time()//30) if counter is None else counter
    key = base64.b32decode(secret_value)
    raw = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = raw[-1] & 15
    return str((struct.unpack('>I', raw[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)

def verify_totp(secret_value, code, last_counter=-1):
    for counter in [int(time.time()//30)-1, int(time.time()//30), int(time.time()//30)+1]:
        if counter > last_counter and hmac.compare_digest(totp(secret_value,counter), str(code)):
            return counter
    return None
