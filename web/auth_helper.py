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
    
    # Login URLs - use user home pages to capture cookies after login redirect
    # The login page redirects to these pages after successful login
    urls = {
        'douban': 'https://www.douban.com/mine/',  # User home page - redirects to login if not logged in
        'imdb': 'https://www.imdb.com/list/watchlist/'  # Watchlist page - requires login
    }
    
    # Required cookies that indicate successful login
    required_cookies = {
        'douban': ['dbcl2'],  # dbcl2 is the main auth cookie for douban
        'imdb': ['at-main', 'ubid-main']  # Both required for IMDB
    }
    
    url = urls[platform]
    required = required_cookies[platform]

    
    result = {'cookie': None, 'closed': False, 'window': None}
    
    def get_cookies():
        """Get cookies from system storage and check for required auth cookies"""
        parts = []
        found_required = set()
        
        try:
            from Foundation import NSHTTPCookieStorage
            all_cookies = NSHTTPCookieStorage.sharedHTTPCookieStorage().cookies() or []
            for c in all_cookies:
                domain = str(c.domain())
                name = str(c.name())
                value = str(c.value())
                
                # Filter by platform domain
                if platform == 'douban' and 'douban' in domain:
                    parts.append(f"{name}={value}")
                    # Check if this is a required cookie
                    if name.lower() in [r.lower() for r in required]:
                        # Validate cookie value is not empty/placeholder
                        if value and len(value) > 10:
                            found_required.add(name.lower())
                            logging.info(f"Found required cookie: {name} (len={len(value)})")
                            
                elif platform == 'imdb' and ('imdb' in domain or 'amazon' in domain):
                    parts.append(f"{name}={value}")
                    if name.lower() in [r.lower() for r in required]:
                        if value and len(value) > 10:
                            found_required.add(name.lower())
                            logging.info(f"Found required cookie: {name} (len={len(value)})")
                            
        except Exception as e:
            logging.error(f"Cookie read error: {e}")
        
        # Check if ALL required cookies are present
        required_lower = set(r.lower() for r in required)
        all_found = required_lower.issubset(found_required)
        
        return "; ".join(parts), all_found, len(parts)
    
    def close_window():
        """Close the webview window"""
        logging.info("Closing window...")
        try:
            if result.get('window'):
                result['window'].destroy()
            else:
                try:
                    from AppKit import NSApp
                    NSApp.terminate_(None)
                except ImportError:
                    os._exit(0)
        except Exception as e:
            logging.error(f"Window close error: {e}")
            os._exit(0)
    
    def cookie_watcher():
        logging.info("Cookie watcher started")
        time.sleep(2)  # Wait for window to fully load
        
        check_count = 0
        max_checks = 180  # 3 minutes max
        
        while check_count < max_checks and not result['closed']:
            time.sleep(1)
            check_count += 1
            
            cookie_str, all_required_found, cookie_count = get_cookies()
            
            # Log every 10 seconds with more details
            if check_count % 10 == 0:
                logging.info(f"Check #{check_count}: cookies={cookie_count}, auth_valid={all_required_found}")
                # Log first few cookie names for debugging
                if cookie_str:
                    cookie_names = [c.split('=')[0] for c in cookie_str.split('; ')[:5]]
                    logging.info(f"  Sample cookies: {cookie_names}")
            
            if all_required_found and cookie_str:
                logging.info(f"✅ Valid auth cookie captured! len={len(cookie_str)}")
                result['cookie'] = cookie_str
                
                # Save to file
                try:
                    import json
                    with open(result_file, 'w') as f:
                        json.dump({'cookie': cookie_str, 'username': ''}, f)
                    logging.info("Cookie saved to file")
                except Exception as e:
                    logging.error(f"Save error: {e}")
                
                # Close window after short delay
                time.sleep(0.5)
                close_window()
                return
        
        logging.info("Watcher timeout - no valid cookie found")
    
    def on_closing():
        """Called when window is closed"""
        logging.info("Window closing event")
        result['closed'] = True
        
        # Final cookie capture attempt
        if not result['cookie']:
            cookie_str, all_found, _ = get_cookies()
            if cookie_str:
                result['cookie'] = cookie_str
                logging.info(f"Final capture: len={len(cookie_str)}, valid={all_found}")
                try:
                    import json
                    with open(result_file, 'w') as f:
                        json.dump({'cookie': cookie_str, 'username': ''}, f)
                except:
                    pass
    
    def get_js_cookies(window):
        """Get cookies from document.cookie via JavaScript"""
        try:
            js_cookies = window.evaluate_js('document.cookie') or ""
            return js_cookies
        except Exception as e:
            logging.error(f"JS cookie error: {e}")
            return ""
    
    def get_webview_cookies(window):
        """Get cookies directly from webview using pywebview's native API"""
        try:
            if window:
                cookies = window.get_cookies()
                if cookies:
                    # cookies is a list of SimpleCookie objects
                    parts = []
                    has_auth = False
                    for cookie in cookies:
                        for name, morsel in cookie.items():
                            value = morsel.value
                            if value:
                                parts.append(f"{name}={value}")
                                # Check for auth cookies
                                if name.lower() in ['dbcl2', 'at-main', 'ubid-main']:
                                    if len(value) > 10:
                                        has_auth = True
                                        logging.info(f"Found auth cookie via webview API: {name}")
                    cookie_str = "; ".join(parts)
                    logging.info(f"Webview API cookies: {len(parts)} cookies, has_auth={has_auth}")
                    return cookie_str, has_auth
        except Exception as e:
            logging.error(f"Webview cookie error: {e}")
        return "", False
    
    def combine_cookies(native_cookies, js_cookies):
        """Combine cookies from native storage and JavaScript"""
        cookie_dict = {}
        
        # Parse native cookies
        if native_cookies:
            for part in native_cookies.split('; '):
                if '=' in part:
                    name, value = part.split('=', 1)
                    cookie_dict[name] = value
        
        # Parse JS cookies (may have more recent values)
        if js_cookies:
            for part in js_cookies.split('; '):
                if '=' in part:
                    name, value = part.split('=', 1)
                    if name not in cookie_dict or len(value) > len(cookie_dict.get(name, '')):
                        cookie_dict[name] = value
        
        return '; '.join([f"{k}={v}" for k, v in cookie_dict.items()])
    
    class Api:
        """JavaScript API exposed to webview"""
        def __init__(self):
            self.window = None
        
        def force_done(self):
            """Called when user clicks manual complete button or auto-detected login"""
            logging.info("Force done triggered - attempting to capture cookies")
            
            # Wait a moment for cookies to be set
            time.sleep(0.5)
            
            # Try multiple sources to get cookies
            max_retries = 6
            retry_delay = 0.5  # 500ms between retries, total 3 seconds max
            
            for attempt in range(max_retries):
                all_cookies = {}
                has_auth = False
                
                # Source 1: pywebview's native get_cookies() - BEST source, directly from WKWebView
                if self.window:
                    webview_str, wv_has_auth = get_webview_cookies(self.window)
                    if webview_str:
                        for part in webview_str.split('; '):
                            if '=' in part:
                                name, value = part.split('=', 1)
                                all_cookies[name] = value
                        if wv_has_auth:
                            has_auth = True
                
                # Source 2: NSHTTPCookieStorage (may not be synced yet)
                native_str, native_has_auth, _ = get_cookies()
                if native_str:
                    for part in native_str.split('; '):
                        if '=' in part:
                            name, value = part.split('=', 1)
                            if name not in all_cookies:  # Don't override webview cookies
                                all_cookies[name] = value
                    if native_has_auth:
                        has_auth = True
                
                # Source 3: JavaScript document.cookie (limited, HTTPOnly not visible)
                if self.window:
                    js_str = get_js_cookies(self.window)
                    if js_str:
                        for part in js_str.split('; '):
                            if '=' in part:
                                name, value = part.split('=', 1)
                                if name not in all_cookies:
                                    all_cookies[name] = value
                
                combined = "; ".join([f"{k}={v}" for k, v in all_cookies.items()])
                logging.info(f"Attempt {attempt + 1}: {len(all_cookies)} cookies, has_auth={has_auth}")
                
                # Check if we have valid auth cookies
                if has_auth and combined and len(combined) > 100:
                    result['cookie'] = combined
                    try:
                        import json
                        with open(result_file, 'w') as f:
                            json.dump({'cookie': combined, 'username': ''}, f)
                        logging.info(f"✅ Cookie saved successfully after {attempt + 1} attempts ({len(combined)} chars)")
                    except Exception as e:
                        logging.error(f"Save error: {e}")
                    break
                
                # If not found yet, wait and retry
                if attempt < max_retries - 1:
                    logging.info(f"Auth cookie not found yet, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
            
            # If we still don't have cookies, save whatever we got
            if not result.get('cookie') and combined and len(combined) > 20:
                result['cookie'] = combined
                try:
                    import json
                    with open(result_file, 'w') as f:
                        json.dump({'cookie': combined, 'username': ''}, f)
                    logging.info(f"Cookie saved (may be incomplete): {len(combined)} chars")
                except Exception as e:
                    logging.error(f"Save error: {e}")
            
            # Close window
            if self.window:
                self.window.destroy()
    
    api = Api()
    
    logging.info(f"Opening webview for {platform}...")
    
    window = webview.create_window(
        f'CineRecord - 登录 {platform.upper()}',
        url,
        width=900,
        height=750,
        js_api=api
    )
    api.window = window
    result['window'] = window
    
    def inject_complete_button(window):
        """Inject a completion button AND login detection script into the page"""
        time.sleep(2)  # Wait for page to load
        
        try:
            # Inject comprehensive login detection (via URL change) and manual button
            # Note: dbcl2 cookie is HttpOnly so JavaScript cannot read it
            # Instead, we detect login success by checking if URL contains /people/ (user profile)
            window.evaluate_js(f"""
                (function() {{
                    // Check if already injected
                    if (window.cinerecordInjected) return;
                    window.cinerecordInjected = true;
                    
                    console.log('[CineRecord] Login detector injected, platform: {platform}');
                    console.log('[CineRecord] Current URL: ' + window.location.href);
                    
                    // Create manual complete button
                    var btn = document.createElement('div');
                    btn.id = 'cinerecord-complete-btn';
                    btn.style = 'position:fixed;top:0;left:0;width:100%;background:linear-gradient(90deg,#10b981,#059669);color:white;text-align:center;padding:14px;z-index:999999;cursor:pointer;font-weight:bold;font-family:-apple-system,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.3);font-size:14px;';
                    btn.innerHTML = '✅ 登录成功后点这里完成 - Click here after login';
                    btn.onclick = function() {{ 
                        console.log('[CineRecord] Manual complete clicked');
                        window.pywebview.api.force_done(); 
                    }};
                    document.body.appendChild(btn);
                    
                    // Login detection function - check URL patterns
                    function checkLoginSuccess() {{
                        var url = window.location.href;
                        var isLoggedIn = false;
                        
                        // Douban: logged in if URL contains /people/ or /mine/ without redirect to login
                        if ('{platform}' === 'douban') {{
                            // Check if we're on a user page (not login page)
                            isLoggedIn = (url.indexOf('/people/') !== -1) || 
                                        (url.indexOf('/mine/') !== -1 && url.indexOf('passport') === -1);
                            console.log('[CineRecord] Douban URL check: ' + url + ' -> ' + isLoggedIn);
                        }}
                        // IMDB: logged in if URL contains /user/ or watchlist is accessible
                        else if ('{platform}' === 'imdb') {{
                            isLoggedIn = url.indexOf('/user/') !== -1 ||
                                        (url.indexOf('/list/watchlist') !== -1 && url.indexOf('signin') === -1);
                        }}
                        
                        if (isLoggedIn) {{
                            console.log('[CineRecord] Login detected via URL!');
                            btn.style.background = 'linear-gradient(90deg,#22c55e,#16a34a)';
                            btn.innerHTML = '🎉 检测到登录成功！自动保存中...';
                            
                            // Auto-trigger after short delay
                            setTimeout(function() {{
                                window.pywebview.api.force_done();
                            }}, 1500);
                            return true;
                        }}
                        return false;
                    }}
                    
                    // Start polling for login success
                    var checkCount = 0;
                    var maxChecks = 90; // 3 minutes at 2 second intervals
                    
                    var loginInterval = setInterval(function() {{
                        checkCount++;
                        if (checkCount > maxChecks) {{
                            console.log('[CineRecord] Login check timeout');
                            clearInterval(loginInterval);
                            return;
                        }}
                        
                        if (checkLoginSuccess()) {{
                            clearInterval(loginInterval);
                        }}
                    }}, 2000);
                    
                    // Also check immediately in case already logged in
                    setTimeout(checkLoginSuccess, 1000);
                }})();
            """)
            logging.info("Login detector script injected successfully")
        except Exception as e:
            logging.error(f"Inject script error: {e}")
    
    # Track if login was detected
    login_detected = {'value': False}
    
    def on_page_loaded():
        """Called every time a page finishes loading in the webview"""
        if login_detected['value']:
            return  # Already detected, don't process again
            
        logging.info("Page loaded event triggered")
        time.sleep(0.5)  # Brief delay for page to stabilize
        
        try:
            # Get current URL
            current_url = window.get_current_url() or ""
            logging.info(f"Current URL: {current_url}")
            
            # Check if we're on a logged-in page
            is_logged_in = False
            if platform == 'douban':
                # Logged in if URL contains /people/ or /mine/ (not on login page)
                is_logged_in = ('/people/' in current_url) or \
                              ('/mine/' in current_url and 'passport' not in current_url)
            elif platform == 'imdb':
                is_logged_in = ('/user/' in current_url) or \
                              ('/list/watchlist' in current_url and 'signin' not in current_url)
            
            logging.info(f"Login check: is_logged_in={is_logged_in}")
            
            if is_logged_in:
                logging.info("✅ Login detected via URL! Capturing cookies...")
                login_detected['value'] = True
                
                # Wait a moment for cookies to fully set
                time.sleep(1)
                
                # Capture cookies and close
                api.force_done()
                return
            
            # Not logged in yet - inject the manual complete button
            try:
                window.evaluate_js(f"""
                    (function() {{
                        if (document.getElementById('cinerecord-complete-btn')) return;
                        
                        var btn = document.createElement('div');
                        btn.id = 'cinerecord-complete-btn';
                        btn.style = 'position:fixed;top:0;left:0;width:100%;background:linear-gradient(90deg,#10b981,#059669);color:white;text-align:center;padding:14px;z-index:999999;cursor:pointer;font-weight:bold;font-family:-apple-system,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.3);font-size:14px;';
                        btn.innerHTML = '✅ 登录成功后点这里完成 - Click here after login';
                        btn.onclick = function() {{ 
                            window.pywebview.api.force_done(); 
                        }};
                        document.body.appendChild(btn);
                        console.log('[CineRecord] Button injected');
                    }})();
                """)
                logging.info("Manual complete button injected")
            except Exception as e:
                logging.error(f"Button inject error: {e}")
                
        except Exception as e:
            logging.error(f"Page loaded handler error: {e}")
    
    # Register the loaded event handler
    window.events.loaded += on_page_loaded
    
    # Start cookie watcher thread as backup
    watcher_thread = threading.Thread(target=cookie_watcher, daemon=True)
    watcher_thread.start()
    
    # Run webview (blocks until window is closed)
    logging.info("Starting webview...")
    webview.start()
    
    # Window closed
    on_closing()
    logging.info("Webview ended")

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
