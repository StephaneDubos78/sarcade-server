"""Wake-up of the devices (note « Réveil des appareils », 28 Oct 2026)."""
import json

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from sarcade.wakeup import fcm, service, webpush


def _hkdf(salt, ikm, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def test_webpush_body_decrypts_on_the_browser_side():
    ua = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    body = webpush.encrypt(b'{"type":"wake"}', webpush.b64u(ua_pub), webpush.b64u(auth))
    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_pub = body[21:21 + idlen]
    assert rs == 4096 and idlen == 65
    shared = ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
    assert plain == b'{"type":"wake"}\x02'


def test_vapid_header_signed_for_the_push_service_origin():
    key = webpush.load_key(webpush.new_private_key_pem())
    header = webpush.vapid_header("https://fcm.googleapis.com/fcm/send/abc", key, "mailto:x@y.org", now=1_000_000)
    token = header.split("t=")[1].split(",")[0]
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com",
                        options={"verify_exp": False})
    assert claims["sub"] == "mailto:x@y.org"
    assert header.endswith("k=" + webpush.public_key_b64(key))


def test_subscription_checked():
    good = json.dumps({"endpoint": "https://push.example/x", "keys": {"p256dh": "AAAA", "auth": "BBBB"}})
    assert webpush.parse_subscription(good)["endpoint"] == "https://push.example/x"
    with pytest.raises(ValueError):
        webpush.parse_subscription(json.dumps({"endpoint": "http://plain", "keys": {"p256dh": "A", "auth": "B"}}))


def test_signal_has_no_content():
    data = service.signal("ev1", "immediate")
    assert data == {"type": "wake", "kind": "message", "event_id": "ev1", "priority": "immediate"}


def test_targets():
    devices = ["PCO", "TEL-01", "TEL-02"]
    assert service.targets(devices, "PCO", []) == ["TEL-01", "TEL-02"], "broadcast: everyone but the sender"
    assert service.targets(devices, "PCO", ["group:abc"]) == ["TEL-01", "TEL-02"], "group: devices decide"
    assert service.targets(devices, "TEL-01", ["TEL-02"]) == ["TEL-02"], "direct: the recipient only"
    assert service.targets(devices, "TEL-01", ["TEL-02", "group:x"]) == ["PCO", "TEL-02"]


def test_routine_grouped_per_minute():
    service._last_routine.clear()
    assert service.routine_allowed("e", "TEL-01", now=100.0)
    assert not service.routine_allowed("e", "TEL-01", now=130.0)
    assert service.routine_allowed("e", "TEL-02", now=130.0)
    assert service.routine_allowed("e", "TEL-01", now=161.0)
    assert service.is_urgent("immediate") and service.is_urgent("urgent") and not service.is_urgent("routine")


def test_fcm_data_message_and_gone_tokens(monkeypatch, tmp_path):
    msg = fcm.message("tok", {"type": "wake"}, True)
    assert msg["message"]["android"]["priority"] == "high" and "notification" not in msg["message"]
    assert fcm.is_gone(404, "") and fcm.is_gone(400, '{"errorCode":"UNREGISTERED"}') and not fcm.is_gone(500, "")
    monkeypatch.delenv("SARCADE_FCM_SERVICE_ACCOUNT", raising=False)
    assert fcm.load_account() is None
    f = tmp_path / "sa.json"
    f.write_text(json.dumps({"client_email": "a@b", "private_key": "k", "project_id": "p"}))
    monkeypatch.setenv("SARCADE_FCM_SERVICE_ACCOUNT", str(f))
    assert fcm.load_account()["project_id"] == "p"


def test_iphone_gets_a_generic_alert_without_content():
    msg = fcm.message("tok", {"type": "wake", "priority": "immediate", "event_id": "e"}, True, ios=True)["message"]
    aps = msg["apns"]["payload"]["aps"]
    assert aps["alert"] == {"title": "SARCADE : message prioritaire", "body": "Ouvrez SARCADE pour le lire."}
    assert msg["apns"]["headers"]["apns-priority"] == "10"
    assert "apns" not in fcm.message("tok", {"type": "wake"}, True)["message"]
    assert fcm.title({"kind": "test"}) == "SARCADE : réveil reçu"

