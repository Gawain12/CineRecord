import requests
import re
import time

def test_fetch(url):
    print(f"\n--- Testing URL: {url} ---")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://letterboxd.com/"
    }
    
    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=10)
        elapsed = time.time() - start_time
        
        print(f"Status Code: {response.status_code}")
        print(f"Time: {elapsed:.2f}s")
        
        if response.status_code != 200:
            print("FAILED: Status code is not 200")
            print(response.text[:500])
            return

        text = response.text
        print(f"Content Length: {len(text)} chars")
        
        # Check for IMDb links
        print("Searching for IMDb patterns...")
        
        imdb_patterns = [
            r'imdb\.com/title/(tt\d+)',
            r'href="[^"]*imdb\.com/title/(tt\d+)[^"]*"',
            r'data-track-action="IMDb".*?href="([^"]+)"',
            r'href="([^"]+)".*?data-track-action="IMDb"',
        ]
        
        found_id = None
        for i, pattern in enumerate(imdb_patterns):
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                print(f"  [Match Pattern {i+1}]: {match.group(0)[:100]}...")
                # Extract ID
                val = match.group(1)
                if 'imdb.com' in val:
                    id_match = re.search(r'title/(tt\d+)', val)
                    if id_match:
                        val = id_match.group(1)
                found_id = val
                break
        
        if found_id:
            print(f"✅ SUCCESS: Found IMDb ID: {found_id}")
        else:
            print("❌ FAILED: No IMDb ID found.")
            # Dump some HTML context to see what's wrong
            tmdb_idx = text.find('themoviedb.org')
            imdb_idx = text.find('imdb.com')
            print(f"  'imdb.com' found at index: {imdb_idx}")
            if imdb_idx != -1:
                start = max(0, imdb_idx - 100)
                end = min(len(text), imdb_idx + 100)
                print(f"  Context around 'imdb.com':\n  {text[start:end]}")
            else:
                # Check for buttons
                track_idx = text.find('data-track-action="IMDb"')
                print(f"  'data-track-action=\"IMDb\"' found at index: {track_idx}")
                if track_idx != -1:
                    start = max(0, track_idx - 100)
                    end = min(len(text), track_idx + 100)
                    print(f"  Context around track action:\n  {text[start:end]}")

    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    # Test cases
    urls = [
        "https://letterboxd.com/film/inception/",
        "https://letterboxd.com/film/parasite-2019/", 
        "https://letterboxd.com/film/everything-everywhere-all-at-once/"
    ]
    
    for url in urls:
        test_fetch(url)
        time.sleep(1)
