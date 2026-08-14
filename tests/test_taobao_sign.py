# -*- coding: utf-8 -*-
import hashlib
import hmac

from crawlers.taobao_client import TaobaoClient


def _client(sign_method="md5"):
    c = TaobaoClient.__new__(TaobaoClient)
    c.app_key = "123456"
    c.app_secret = "test-secret"
    c.sign_method = sign_method
    return c


def test_md5_sign_vector():
    c = _client("md5")
    params = {"method": "taobao.tbk.dg.material.optional.upgrade", "q": "耳机", "page_size": "20"}
    got = c._sign(params)
    raw = "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = hashlib.md5(("test-secret" + raw + "test-secret").encode("utf-8")).hexdigest().upper()
    assert got == expected
    assert len(got) == 32


def test_hmac_sha256_sign():
    c = _client("hmac-sha256")
    params = {"a": "1", "b": "2"}
    got = c._sign(params)
    raw = "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = hmac.new(b"test-secret", raw.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    assert got == expected
