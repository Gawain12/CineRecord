import base64
import hashlib
import json
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class CookieCloudError(Exception):
    """Raised when CookieCloud sync or parsing fails."""


PLATFORM_DOMAIN_KEYWORDS = {
    'douban': ('douban.com',),
    'imdb': ('imdb.com', 'amazon.com'),
}

PLATFORM_COOKIE_RULES = {
    'douban': {
        'allowed_names': ('dbcl2', 'ck', 'ap_v', 'bid', 'push_noty_num', 'push_doumail_num'),
        'required_names': ('dbcl2',),
    },
    'imdb': {
        'allowed_names': ('ubid-main', 'at-main', 'sess-at-main', 'session-id', 'session-id-time', 'session-token', 'x-main', 'csm-hit', 'uu', 'lc-main'),
        'required_names': ('ubid-main', 'at-main', 'session-token'),
    },
}


def _normalize_host(host: str) -> str:
    host = str(host or '').strip()
    if not host:
        raise CookieCloudError('CookieCloud 地址不能为空')
    if not host.startswith(('http://', 'https://')):
        host = f'http://{host}'
    return host.rstrip('/')


def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16) -> Tuple[bytes, bytes]:
    """OpenSSL-compatible EVP_BytesToKey derivation used by CryptoJS AES."""
    output = b''
    prev = b''
    while len(output) < key_len + iv_len:
        prev = hashlib.md5(prev + password + salt).digest()
        output += prev
    return output[:key_len], output[key_len:key_len + iv_len]


def _decrypt_cookiecloud_blob(uuid: str, password: str, encrypted: str) -> Dict[str, Any]:
    try:
        raw = base64.b64decode(encrypted)
    except Exception as exc:
        raise CookieCloudError(f'CookieCloud 密文不是有效的 Base64: {exc}') from exc

    if len(raw) < 16 or raw[:8] != b'Salted__':
        raise CookieCloudError('CookieCloud 返回的密文格式不正确')

    salt = raw[8:16]
    ciphertext = raw[16:]
    passphrase = hashlib.md5(f'{uuid}-{password}'.encode('utf-8')).hexdigest()[:16].encode('utf-8')
    key, iv = _evp_bytes_to_key(passphrase, salt)

    try:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as exc:
        raise CookieCloudError(f'CookieCloud 解密失败，请检查 UUID/密码是否正确: {exc}') from exc


def _request_cookiecloud_payload(host: str, uuid: str, password: str, timeout: int = 15) -> Dict[str, Any]:
    url = f'{_normalize_host(host)}/get/{uuid}'
    try:
        response = requests.get(url, params={'password': password}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise CookieCloudError(f'CookieCloud 请求失败: {exc}') from exc
    except ValueError as exc:
        raise CookieCloudError(f'CookieCloud 返回的不是有效 JSON: {exc}') from exc

    if isinstance(data, dict):
        if isinstance(data.get('cookie_data'), (dict, list)):
            return data
        payload = data.get('data')
        if isinstance(payload, dict) and isinstance(payload.get('cookie_data'), (dict, list)):
            return payload
        encrypted = data.get('encrypted')
        if encrypted:
            return _decrypt_cookiecloud_blob(uuid, password, encrypted)

    raise CookieCloudError('CookieCloud 返回中未找到可用的 Cookie 数据')


def _iter_cookie_records(cookie_data: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(cookie_data, dict):
        for source_domain, items in cookie_data.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        yield source_domain, item
            elif isinstance(items, dict):
                for name, value in items.items():
                    yield source_domain, {'name': name, 'value': value, 'domain': source_domain}
    elif isinstance(cookie_data, list):
        for item in cookie_data:
            if isinstance(item, dict):
                yield str(item.get('domain') or ''), item


def _cookie_names_from_header(cookie_header: str) -> List[str]:
    names = []
    for part in str(cookie_header or '').split(';'):
        if '=' not in part:
            continue
        names.append(part.split('=', 1)[0].strip())
    return names


def _build_cookie_header(cookie_data: Any, domain_keywords: Tuple[str, ...], allowed_names: Optional[Tuple[str, ...]] = None) -> Tuple[str, int]:
    cookies = OrderedDict()
    matched = 0
    allowed = {name.lower() for name in allowed_names} if allowed_names else None

    for source_domain, item in _iter_cookie_records(cookie_data):
        name = str(item.get('name') or '').strip()
        value = item.get('value')
        if not name or value is None:
            continue

        domain = str(item.get('domain') or source_domain or '').lower().lstrip('.')
        if domain_keywords and not any(keyword in domain for keyword in domain_keywords):
            continue
        if allowed is not None and name.lower() not in allowed:
            continue

        matched += 1
        if name in cookies:
            del cookies[name]
        cookies[name] = str(value)

    header = '; '.join(f'{name}={value}' for name, value in cookies.items())
    return header, matched


def import_platform_cookies(host: str, uuid: str, password: str) -> Dict[str, Any]:
    uuid = str(uuid or '').strip()
    password = str(password or '')

    if not uuid:
        raise CookieCloudError('CookieCloud UUID 不能为空')
    if not password:
        raise CookieCloudError('CookieCloud 密码不能为空')

    payload = _request_cookiecloud_payload(host, uuid, password)
    cookie_data = payload.get('cookie_data')
    if not cookie_data:
        raise CookieCloudError('CookieCloud 返回中没有 cookie_data')

    results: Dict[str, Any] = {
        'cookie_data': cookie_data,
        'douban_cookie': '',
        'douban_count': 0,
        'imdb_cookie': '',
        'imdb_count': 0,
    }

    for platform, keywords in PLATFORM_DOMAIN_KEYWORDS.items():
        rules = PLATFORM_COOKIE_RULES.get(platform, {})
        header, count = _build_cookie_header(cookie_data, keywords, rules.get('allowed_names'))
        names = _cookie_names_from_header(header)
        required = tuple(rules.get('required_names') or ())
        results[f'{platform}_cookie'] = header
        results[f'{platform}_count'] = count
        results[f'{platform}_cookie_names'] = names
        results[f'{platform}_missing_required'] = [
            required_name for required_name in required
            if required_name not in names
        ]

    return results


def validate_platform_cookie(platform: str, cookie_header: str, user_id: str = '') -> Dict[str, Any]:
    names = _cookie_names_from_header(cookie_header)
    rules = PLATFORM_COOKIE_RULES.get(platform, {})
    missing_required = [
        name for name in tuple(rules.get('required_names') or ())
        if name not in names
    ]
    if missing_required:
        return {
            'success': False,
            'reason': f"missing required cookies: {', '.join(missing_required)}",
            'cookie_names': names,
        }

    headers = {
        'Cookie': cookie_header,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        if platform == 'douban':
            resp = requests.get('https://www.douban.com/mine/', headers=headers, timeout=12, allow_redirects=True)
            final_url = resp.url or ''
            success = ('/people/' in final_url) and ('passport/login' not in final_url)
            return {
                'success': success,
                'reason': '' if success else f'not logged in, final_url={final_url}',
                'cookie_names': names,
            }

        if platform == 'imdb':
            payload = {
                'operationName': 'userRatings',
                'variables': {'first': 1, 'after': None},
                'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': 'ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a'}}
            }
            resp = requests.post('https://api.graphql.imdb.com/', json=payload, headers=headers, timeout=15)
            data = resp.json() if resp.status_code == 200 else {}
            total = data.get('data', {}).get('userRatings', {}).get('total')
            success = resp.status_code == 200 and total is not None
            return {
                'success': success,
                'reason': '' if success else f'graphql status={resp.status_code}',
                'cookie_names': names,
                'ratings_total': total,
                'user_id': user_id,
            }
    except Exception as exc:
        return {
            'success': False,
            'reason': str(exc),
            'cookie_names': names,
        }

    return {
        'success': False,
        'reason': f'unsupported platform: {platform}',
        'cookie_names': names,
    }
