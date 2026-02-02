import multiprocessing
import time
import os
import tempfile
import logging
import threading
import sys

# These imports are checked at runtime in the worker process
HAS_WEBVIEW = False
HAS_OBJC = False
HAS_APPKIT = False
webview = None

def login_worker(platform, result_file, log_file):
    """Worker process for handling webview login"""
    global HAS_WEBVIEW, HAS_OBJC, HAS_APPKIT, webview
    
    # Setup logging first
    _stream = sys.stdout or getattr(sys, "__stdout__", None) or sys.stderr or getattr(sys, "__stderr__", None)
    if _stream is None:
        _stream = open(os.devnull, "w")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(_stream)]
    )
    
    logging.info(f"Login worker started for {platform}")
    
    # Import webview in the worker process
    try:
        import webview as wv
        webview = wv
        HAS_WEBVIEW = True
        logging.info("webview module loaded successfully")
    except ImportError as e:
        logging.error(f"Failed to import webview: {e}")
        return
    
    # Import macOS cookie access
    try:
        from Foundation import NSHTTPCookieStorage
        HAS_OBJC = True
        logging.info("Foundation module loaded")
    except ImportError:
        logging.warning("Foundation not available - cookie capture may not work")
    
    try:
        from AppKit import NSApp
        HAS_APPKIT = True
    except ImportError:
        pass
    
    # Login URLs - use direct login pages for more stable loading
    urls = {
        'douban': 'https://accounts.douban.com/passport/login',  # Direct login page
        'imdb': 'https://www.imdb.com/registration/signin'  # Direct login page
    }
    
    # Required cookies that indicate successful login
    required_cookies = {
        'douban': ['dbcl2'],  # dbcl2 is the main auth cookie for douban
        'imdb': ['at-main', 'ubid-main']  # Both required for IMDB
    }
    
    url = urls[platform]
    required = required_cookies[platform]

    
    
    # Track state in a class we can pass around
    class State:
        def __init__(self):
            self.closed = False
            self.cookie = None
            self.window = None
    state = State()
    is_macos = sys.platform == 'darwin'
    
    def get_cookies():
        """Get cookies - uses platform-specific methods for best compatibility"""
        parts = []
        found_required = set()
        
        # Try macOS native method first
        if is_macos and HAS_OBJC:
            try:
                from Foundation import NSHTTPCookieStorage
                all_cookies = NSHTTPCookieStorage.sharedHTTPCookieStorage().cookies() or []
                for c in all_cookies:
                    domain = str(c.domain())
                    name = str(c.name())
                    value = str(c.value())
                    if platform == 'douban' and 'douban' in domain:
                        parts.append(f"{name}={value}")
                        if name.lower() in [r.lower() for r in required]:
                            if len(value) > 10: found_required.add(name.lower())
                    elif platform == 'imdb' and ('imdb' in domain or 'amazon' in domain):
                        parts.append(f"{name}={value}")
                        if name.lower() in [r.lower() for r in required]:
                            if len(value) > 10: found_required.add(name.lower())
            except Exception as e:
                logging.error(f"macOS cookie read error: {e}")
        
        # On Windows (or if macOS failed), use pywebview
        if not parts and state.window:
            try:
                # IMPORTANT: get_cookies() can be unstable on Windows 
                # if called too early or from wrong context.
                # We wrap it extensively.
                cookies = state.window.get_cookies()
                if cookies:
                    for cookie in cookies:
                        if hasattr(cookie, 'items'):
                            for name, morsel in cookie.items():
                                value = morsel.value if hasattr(morsel, 'value') else str(morsel)
                                if value:
                                    parts.append(f"{name}={value}")
                                    if name.lower() in [r.lower() for r in required]:
                                        if len(value) > 10: 
                                            found_required.add(name.lower())
                                            logging.info(f"Found required cookie: {name}")
                        elif isinstance(cookie, dict):
                           for name, value in cookie.items():
                                if value:
                                    parts.append(f"{name}={value}")
                                    if name.lower() in [r.lower() for r in required]:
                                        if len(str(value)) > 10: 
                                            found_required.add(name.lower())
                                            logging.info(f"Found required cookie: {name}")
            except Exception as e:
                logging.error(f"Webview cookie read error: {e}")
        
        required_lower = set(r.lower() for r in required)
        all_found = required_lower.issubset(found_required)
        return "; ".join(parts), all_found, len(parts)

    def save_and_close(cookie_str):
        if not cookie_str: return
        logging.info(f"Saving cookie ({len(cookie_str)} chars)...")
        try:
            import json
            with open(result_file, 'w') as f:
                json.dump({'cookie': cookie_str, 'username': ''}, f)
        except Exception as e:
            logging.error(f"Save error: {e}")
        
        state.closed = True
        time.sleep(0.5)
        if state.window:
            state.window.destroy()
        else:
            os._exit(0)

    def monitor_loop():
        """Monitor URL and Title changes to detect login"""
        time.sleep(3) # Wait for start
        while not state.closed:
            time.sleep(2) # Low frequency polling
            if not state.window: continue
            
            try:
                # 1. Check Window Title (Manual Signal)
                # We inject JS that changes title to "CR_DONE" when button clicked
                # This avoids python->js bridge crashes
                # Note: Pywebview doesn't have get_title(), so we rely on URL mainly
                
                # 2. Check URL
                current_url = state.window.get_current_url() or ""
                is_logged_in = False
                
                if platform == 'douban':
                     is_logged_in = ('/people/' in current_url) or \
                                   ('/mine/' in current_url and 'passport' not in current_url)
                elif platform == 'imdb':
                     is_logged_in = ('/user/' in current_url) or \
                                   ('/list/watchlist' in current_url and 'signin' not in current_url)
                
                # Check for manual signal via URL hash or specific path
                if 'cinerecord_done' in current_url:
                    is_logged_in = True
                    logging.info("Manual done signal detected via URL")

                if is_logged_in:
                    logging.info("Login detected! Capturing cookies...")
                    # Retry getting cookies a few times
                    for i in range(5):
                        c_str, valid, count = get_cookies()
                        if valid:
                            save_and_close(c_str)
                            return
                        time.sleep(1)
                    
                    # If strictly valid not found, save what we have
                    c_str, _, count = get_cookies()
                    if count > 0:
                        save_and_close(c_str)
                        return
                    else:
                        logging.warning("Login detected but no cookies found?")
            except Exception as e:
                logging.error(f"Monitor error: {e}")

    def on_loaded():
        """Inject simple JS to help manual signaling"""
        if state.closed: return
        try:
            # We inject a button that changes URL to a specific anchor
            # This triggers our URL detector in python
            js = f"""
                (function() {{
                    if (document.getElementById('cr_btn')) return;
                    var btn = document.createElement('div');
                    btn.id = 'cr_btn';
                    btn.style = 'position:fixed;top:0;left:0;width:100%;height:40px;line-height:40px;background:#10b981;color:white;text-align:center;z-index:999999;cursor:pointer;font-weight:bold;font-size:14px;';
                    btn.innerHTML = '✅ 登录成功后点此完成 / Click here after login';
                    btn.onclick = function() {{ 
                        window.location.hash = 'cinerecord_done';
                    }};
                    document.body.appendChild(btn);
                }})();
            """
            state.window.evaluate_js(js)
        except:
            pass

    logging.info(f"Opening webview for {platform}...")
    
    # CRITICAL FIX: Do NOT pass js_api=api. This causes recursion crash on Windows.
    window = webview.create_window(
        f'CineRecord - 登录 {platform.upper()}',
        url,
        width=1000,
        height=800
    )
    state.window = window
    
    # Start separate thread for monitoring
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    
    window.events.loaded += on_loaded
    webview.start()
    
    # Cleanup
    state.closed = True
    if not result_file or not os.path.exists(result_file):
        # Last ditch effort
        c_str, _, _ = get_cookies()
        if c_str:
            save_and_close(c_str)

def run_login_in_thread(platform, socketio, callback):
    socketio.emit('log', {'message': f'🌐 正在打开 {platform.upper()} 登录窗口...', 'type': 'info'})
    
    temp = tempfile.gettempdir()
    ts = int(time.time())
    rf = os.path.join(temp, f'cr_{platform}_{ts}.json')
    lf = os.path.join(temp, f'cr_{platform}_{ts}.log')
    
    logging.info(f"Starting login process for {platform}")
    logging.info(f"Result file: {rf}")
    logging.info(f"Log file: {lf}")
    
    p = multiprocessing.Process(target=login_worker, args=(platform, rf, lf))
    p.start()
    
    def monitor():
        p.join(timeout=300)  # 5 min timeout
        if p.is_alive():
            logging.warning(f"Login process timed out for {platform}")
            p.terminate()
        
        # Read log file for debugging
        try:
            if os.path.exists(lf):
                with open(lf, 'r') as f:
                    log_content = f.read()
                    if log_content:
                        logging.info(f"Login process log:\n{log_content}")
        except Exception as e:
            logging.error(f"Error reading log file: {e}")
        
        cookie = None
        try:
            if os.path.exists(rf):
                import json
                with open(rf) as f:
                    d = json.load(f)
                    cookie = d.get('cookie') or None
                logging.info(f"Cookie file found, cookie length: {len(cookie) if cookie else 0}")
                os.remove(rf)
            else:
                logging.warning(f"No cookie result file found at {rf}")
        except Exception as e:
            logging.error(f"Error reading cookie file: {e}")
        
        # Clean up log file
        try:
            if os.path.exists(lf):
                os.remove(lf)
        except:
            pass
        
        # Validate cookie has minimum length
        if cookie and len(cookie) < 50:
            logging.warning(f"Cookie too short ({len(cookie)}), treating as invalid")
            socketio.emit('log', {'message': f'❌ 登录失败：Cookie无效', 'type': 'error'})
            cookie = None
        elif cookie:
            socketio.emit('log', {'message': f'✅ {platform.upper()} 登录成功', 'type': 'success'})
        else:
            socketio.emit('log', {'message': f'❌ {platform.upper()} 登录失败或已取消', 'type': 'error'})
        
        callback(platform, cookie, None)
    
    threading.Thread(target=monitor, daemon=True).start()
