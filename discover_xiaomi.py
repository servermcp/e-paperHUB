
import base64
import hashlib
import hmac
import json
import os
import random
import time
import urllib.parse
import requests
from Crypto.Cipher import ARC4

import config  # Carga .env automáticamente

USERNAME = os.getenv("XIAOMI_USERNAME", "")
USER_ID_HINT = os.getenv("XIAOMI_USER_ID", "")
PASSWORD = os.getenv("XIAOMI_PASSWORD", "")

class XiaomiCloudConnector:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.agent = f"Android-7.1.1-1.0.0-ONEPLUS A3010-136-{self._rand_str(16)} APP/xiaomi.smarthome APPV/62830"
        self.session.headers.update({"User-Agent": self.agent})
        self.ssecurity = None
        self.userId = None
        self.cUserId = None
        self.passToken = None
        self.serviceToken = None

    @staticmethod
    def _rand_str(n):
        return "".join(random.choices("0123456789ABCDEF", k=n))

    @staticmethod
    def _parse_json(text):
        if text.startswith("&&&START&&&"):
            text = text[11:]
        return json.loads(text)

    def login(self):
        # Step 1: serviceLogin
        url1 = "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true"
        r1 = self.session.get(url1, timeout=10)
        d1 = self._parse_json(r1.text)

        # Step 2: serviceLoginAuth2
        url2 = "https://account.xiaomi.com/pass/serviceLoginAuth2"
        pwd_hash = hashlib.md5(self.password.encode()).hexdigest().upper()
        payload = {
            "sid": "xiaomiio",
            "hash": pwd_hash,
            "callback": "https://sts.api.io.mi.com/sts",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": self.username,
            "_sign": d1.get("_sign", ""),
            "_json": "true",
        }
        r2 = self.session.post(url2, data=payload, timeout=10)
        d2 = self._parse_json(r2.text)

        if d2.get("notificationUrl"):
            return {"ok": False, "2fa_required": True, "notificationUrl": d2.get("notificationUrl"), "raw": d2}

        if not d2.get("ssecurity") or not d2.get("location"):
            return {"ok": False, "error": "Credenciales rechazadas o captcha requerido", "raw": d2}

        self.ssecurity = d2["ssecurity"]
        self.userId = d2["userId"]
        self.cUserId = d2.get("cUserId")
        self.passToken = d2.get("passToken")

        # Step 3: follow location to get serviceToken cookie
        r3 = self.session.get(d2["location"], timeout=10)
        self.serviceToken = self.session.cookies.get("serviceToken")
        return {"ok": bool(self.serviceToken), "userId": self.userId, "ssecurity": self.ssecurity}

    def _signed_nonce(self, nonce_b64):
        h = hashlib.sha256(base64.b64decode(self.ssecurity) + base64.b64decode(nonce_b64))
        return base64.b64encode(h.digest()).decode()

    @staticmethod
    def _rc4_crypt(key_b64, data_bytes):
        cipher = ARC4.new(base64.b64decode(key_b64))
        cipher.encrypt(bytes(1024))
        return cipher.encrypt(data_bytes)

    def api_call(self, country, uri, params_dict):
        base = "https://api.io.mi.com/app" if country == "cn" else f"https://{country}.api.io.mi.com/app"
        url = base + uri

        nonce = base64.b64encode(os.urandom(8) + int(time.time() / 60).to_bytes(4, "big")).decode()
        snonce = self._signed_nonce(nonce)

        params = {"data": json.dumps(params_dict)}
        # RC4 signature & encryption
        rc4_params = dict(params)
        msg = "&".join([method := "POST", uri] + [f"{k}={v}" for k, v in rc4_params.items()] + [snonce])
        rc4_params["rc4_hash__"] = base64.b64encode(hashlib.sha1(msg.encode()).digest()).decode()

        enc_params = {}
        for k, v in rc4_params.items():
            enc_params[k] = base64.b64encode(self._rc4_crypt(snonce, v.encode())).decode()

        msg2 = "&".join(["POST", uri] + [f"{k}={v}" for k, v in enc_params.items()] + [snonce])
        enc_params["signature"] = base64.b64encode(hashlib.sha1(msg2.encode()).digest()).decode()
        enc_params["_nonce"] = nonce
        enc_params["ssecurity"] = self.ssecurity

        headers = {
            "User-Agent": self.agent,
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "Accept-Encoding": "identity",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self.userId),
            "yetAnotherServiceToken": str(self.serviceToken),
            "serviceToken": str(self.serviceToken),
            "locale": "en_US",
            "timezone": "GMT+00:00",
            "is_daylight": "0",
            "dst_offset": "0",
            "channel": "MI_APP_STORE",
        }
        resp = self.session.post(url, data=enc_params, headers=headers, cookies=cookies, timeout=10)
        dec = self._rc4_crypt(snonce, base64.b64decode(resp.text))
        return json.loads(dec.decode("utf-8", errors="replace"))

xc = XiaomiCloudConnector(USERNAME, PASSWORD)
login_res = xc.login()
print("Resultado Login Xiaomi:", login_res)

if login_res.get("ok"):
    for region in ("us", "de", "cn", "sg", "ru", "i2"):
        try:
            res = xc.api_call(region, "/home/device_list", {"getVirtualModel": True, "getHuamiDevices": 1, "get_split_device": False, "support_smart_home": True})
            devs = res.get("result", {}).get("list", [])
            print(f"=== Región [{region}] -> {len(devs)} dispositivos ===")
            for d in devs:
                print(f"  - Nombre: {d.get('name')} | DID: {d.get('did')} | Modelo: {d.get('model')} | IP: {d.get('localip')} | Token: {d.get('token')} | Online: {d.get('isOnline')}")
        except Exception as e:
            print(f"Región [{region}] error: {e}")
