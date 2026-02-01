
import requests
import json

base_url = "http://152.53.128.218:8096"
api_key = "ede4965d80e544c8a363df51e4fb8e6f"
headers = {"X-Emby-Token": api_key}

try:
    print(f"Testing connection to {base_url}...")
    resp = requests.get(f"{base_url}/System/Info", headers=headers, timeout=10)
    print(f"System Info Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"System Info: {resp.json().get('ProductName')} (Version: {resp.json().get('Version')})")
    
    print("\nFetching first 5 items...")
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Movie",
        "Fields": "ProviderIds,ProductionYear,OriginalTitle,Path",
        "Limit": 5
    }
    resp = requests.get(f"{base_url}/Items", headers=headers, params=params, timeout=10)
    print(f"Items Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Total Record Count: {data.get('TotalRecordCount')}")
        items = data.get('Items', [])
        print(f"Returned Items Count: {len(items)}")
        for item in items:
            print(f"- {item.get('Name')} ({item.get('ProductionYear')}): IDs={item.get('ProviderIds')}")
    else:
        print(f"Error Response: {resp.text}")

except Exception as e:
    print(f"Error during test: {e}")
