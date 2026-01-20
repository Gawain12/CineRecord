import requests

def test_shortlink(url):
    print(f"\n--- Testing Shortlink: {url} ---")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        # First, try HEAD with redirects allowed (what code does now)
        print("1. Trying HEAD with allow_redirects=True...")
        resp_head = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        print(f"   Status Code: {resp_head.status_code}")
        print(f"   Final URL: {resp_head.url}")
        
        if 'letterboxd.com/film/' in resp_head.url:
            print("   ✅ HEAD method Success!")
        else:
            print("   ❌ HEAD method Failed or didn't redirect to film page.")

        # Second, try GET with redirects allowed (alternative)
        print("\n2. Trying GET with allow_redirects=True...")
        resp_get = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        print(f"   Status Code: {resp_get.status_code}")
        print(f"   Final URL: {resp_get.url}")
        
        if 'letterboxd.com/film/' in resp_get.url:
            print("   ✅ GET method Success!")
        else:
            print("   ❌ GET method Failed.")
            print("   Response text preview:")
            print(resp_get.text[:500])

        # Third, try Manual Redirect handling (no follow) to inspect Location header
        print("\n3. Trying GET with allow_redirects=False (Manual inspection)...")
        resp_manual = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
        print(f"   Status: {resp_manual.status_code}")
        if resp_manual.is_redirect:
            print(f"   Location Header: {resp_manual.headers.get('Location')}")
        else:
            print("   Not a redirect response.")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    urls = [
        "https://boxd.it/6gdusn",  # Invalid format maybe? Usually it's boxd.it/XYZ
        "https://boxd.it/6gduSb",
        "https://boxd.it/6gdtCB" 
    ]
    # Note: user logs showed "https://boxd.it/6gdusn". boxd.it usually has shorter codes but let's trust logs.
    
    for u in urls:
        test_shortlink(u)
