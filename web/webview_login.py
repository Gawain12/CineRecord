#!/usr/bin/env python3
import sys
import time
import threading
import os
import webview

# Use pyobjc to access macOS native cookie storage directly
try:
    from Foundation import NSHTTPCookieStorage
    HAS_OBJC = True
except ImportError:
    HAS_OBJC = False

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    
    platform = sys.argv[1]
    
    login_urls = {
        'douban': 'https://accounts.douban.com/passport/login',
        'imdb': 'https://www.imdb.com/registration/signin'
    }
    
    # Critical indicators for a valid session
    target_indicators = {
        'douban': ['dbcl2'],
        'imdb': ['at-main'] # Essential for IMDb GraphQL API
    }
    
    url = login_urls.get(platform)
    indicators = target_indicators.get(platform, [])
    
    if not url:
        sys.exit(1)

    result = {'cookie': None}
    log_path = 'webview_debug.log'

    def debug_log(msg):
        with open(log_path, 'a') as f: f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def get_all_cookies(window):
        """Cross-platform cookie access."""
        cookie_parts = []
        found_indicator = False
        names_found = []
        
        # 1. macOS Native Path (Most reliable for HTTPOnly)
        if HAS_OBJC and sys.platform == 'darwin':
            try:
                storage = NSHTTPCookieStorage.sharedHTTPCookieStorage()
                cookies = storage.cookies()
                if cookies:
                    for c in cookies:
                        domain = str(c.domain())
                        if platform in domain:
                            n, v = str(c.name()), str(c.value())
                            cookie_parts.append(f"{n}={v}")
                            names_found.append(n)
                            for ind in indicators:
                                if ind.lower() in n.lower():
                                    found_indicator = True
            except Exception as e:
                debug_log(f"MacOS native cookie error: {e}")

        # 2. PyWebView Cross-platform Path (Experimental/Newer versions)
        if not found_indicator:
            try:
                # pywebview >= 4.0 provides get_cookies() on some platforms
                cookies = window.get_cookies()
                for c in cookies:
                    if platform in c.domain:
                        n, v = c.name, c.value
                        cookie_parts.append(f"{n}={v}")
                        names_found.append(n)
                        for ind in indicators:
                            if ind.lower() in n.lower():
                                found_indicator = True
            except:
                pass

        # 3. JS Fallback (Standard)
        if not found_indicator:
            js_cookies = window.evaluate_js('document.cookie') or ""
            if js_cookies:
                for part in js_cookies.split(';'):
                    if '=' in part:
                        n = part.split('=')[0].strip()
                        names_found.append(n)
                        for ind in indicators:
                            if ind.lower() in n.lower():
                                found_indicator = True
                if found_indicator:
                    return js_cookies, True, names_found

        return "; ".join(cookie_parts), found_indicator, names_found

    def check_login(window):
        start_time = time.time()
        while time.time() - start_time < 600:
            time.sleep(2)
            try:
                cookie_str, found, names = get_all_cookies(window)
                
                debug_log(f"Scan -> Names: {names} | Found Indicator: {found}")

                if found:
                    result['cookie'] = cookie_str
                    debug_log(f"✅ SUCCESS: Captured cookies with {names}")
                    window.destroy()
                    return

            except Exception as e:
                debug_log(f"❌ Error: {e}")

    class Api:
        def force_done(self):
            debug_log("🖱️ User Manual Force Done")
            cookie_str, _, _ = get_all_cookies(window)
            js = window.evaluate_js('document.cookie') or ""
            # When forcing, take whatever is more complete
            result['cookie'] = cookie_str if len(cookie_str) > len(js) else js
            window.destroy()

    window = webview.create_window(
        f'CineRecord - {platform.upper()}',
        url,
        width=540, height=720,
        js_api=Api()
    )

    def inject_ui(window):
        time.sleep(4)
        window.evaluate_js("""
            var d = document.createElement('div');
            d.style = 'position:fixed;top:0;left:0;width:100%;background:#10b981;color:white;text-align:center;padding:12px;z-index:999999;cursor:pointer;font-weight:bold;font-family:sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.2);';
            d.innerHTML = '手动完成：如果你已登录到个人主页且窗口未自动关闭，请点这里 [完成同步]';
            d.onclick = function(){ window.pywebview.api.force_done(); };
            document.body.appendChild(d);
        """)

    threading.Thread(target=check_login, args=(window,), daemon=True).start()
    webview.start(inject_ui, window)
    
    if result['cookie']:
        sys.stdout.write(result['cookie'])
        sys.stdout.flush()
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
