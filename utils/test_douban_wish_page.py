import json
import requests


def build_headers(cookie, user_agent=None):
    headers = {
        "Cookie": cookie,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://m.douban.com/",
        "User-Agent": user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    return headers


def main():
    try:
        from config.config import DOUBAN_CONFIG
    except Exception as exc:
        print(f"Failed to load config.config: {exc}")
        return

    user_id = DOUBAN_CONFIG.get("user_id")
    cookie = DOUBAN_CONFIG.get("headers", {}).get("Cookie")
    user_agent = DOUBAN_CONFIG.get("headers", {}).get("User-Agent")

    if not user_id or not cookie:
        print("Missing douban user_id or cookie in config.")
        return

    url = f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
    params = {
        "type": "movie",
        "status": "mark",
        "count": 20,
        "start": 0,
        "for_mobile": 1,
    }

    resp = requests.get(url, params=params, headers=build_headers(cookie, user_agent), timeout=30)
    resp.raise_for_status()
    data = resp.json()

    interests = data.get("interests", []) or []
    print(f"total={data.get('total', 0)}, page_count={len(interests)}")

    if interests:
        sample = interests[0]
        subject = sample.get("subject", {}) or {}
        print("sample_keys:", sorted(sample.keys()))
        print("subject_keys:", sorted(subject.keys()))
        print("sample_title:", subject.get("title"))
        print("sample_json:", json.dumps(sample, ensure_ascii=False)[:1000])


if __name__ == "__main__":
    main()
