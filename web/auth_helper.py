import multiprocessing
import time
import os
import tempfile
import webview
import logging
import threading

try:
    from Foundation import NSHTTPCookieStorage
    HAS_OBJC = True
except ImportError:
    HAS_OBJC = False

try:
    from AppKit import NSApp
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False

def login_worker(platform, result_file, log_file):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )
    
    logging.info(f"Started for {platform}")
    
    # Simple login URLs
    urls = {
        'douban': 'https://www.douban.com/mine/',
        'imdb': 'https://www.imdb.com/registration/signin'
    }
    
    indicators = {
        'douban': ['dbcl2'],
        'imdb': ['at-main', 'ubid-main']
    }
    
    url = urls[platform]
    ind = indicators[platform]
    
    result = {'cookie': None, 'closed': False}
    
    def get_cookies():
        parts, found = [], False
        all_domains = set()
        if HAS_OBJC:
            try:
                all_cookies = NSHTTPCookieStorage.sharedHTTPCookieStorage().cookies() or []
                for c in all_cookies:
                    domain = str(c.domain())
                    all_domains.add(domain)
                    n, v = str(c.name()), str(c.value())
                    
                    # For douban: only douban cookies
                    # For imdb: imdb + amazon cookies
                    if platform == 'douban' and 'douban' in domain:
                        parts.append(f"{n}={v}")
                        if any(i.lower() in n.lower() for i in ind):
                            found = True
                    elif platform == 'imdb' and ('imdb' in domain or 'amazon' in domain):
                        parts.append(f"{n}={v}")
                        if any(i.lower() in n.lower() for i in ind):
                            found = True
            except Exception as e:
                logging.error(f"Cookie error: {e}")
        return "; ".join(parts), found, all_domains
    
    def cookie_watcher():
        logging.info("Watcher started")
        time.sleep(3)
        
        for i in range(300):
            if result['closed']:
                return
            
            time.sleep(1)
            cookie_str, found, domains = get_cookies()
            
            if i % 15 == 0:
                cookie_count = cookie_str.count(';') + 1 if cookie_str else 0
                logging.info(f"Check: cookies={cookie_count}, found={found}, domains={len(domains)}")
                if domains and cookie_count == 0:
                    logging.info(f"  Domains: {list(domains)[:5]}...")
            
            if found:
                logging.info(f"Cookie found! len={len(cookie_str)}")
                result['cookie'] = cookie_str
                
                try:
                    import json
                    with open(result_file, 'w') as f:
                        json.dump({'cookie': cookie_str, 'username': ''}, f)
                    logging.info("Saved")
                except Exception as e:
                    logging.error(f"Save error: {e}")
                
                if HAS_APPKIT:
                    NSApp.terminate_(None)
                else:
                    os._exit(0)
                return
        
        logging.info("Timeout")
    
    logging.info("Opening window...")
    
    window = webview.create_window(
        f'CineRecord - Login {platform.upper()}',
        url,
        width=900,
        height=700
    )
    
    threading.Thread(target=cookie_watcher, daemon=True).start()
    
    webview.start()
    
    result['closed'] = True
    logging.info("Webview ended")
    
    if not result['cookie']:
        cookie_str, found, _ = get_cookies()
        result['cookie'] = cookie_str
        if cookie_str:
            logging.info(f"Final capture: len={len(cookie_str)}, found={found}")
    
    try:
        import json
        with open(result_file, 'w') as f:
            json.dump({'cookie': result['cookie'] or '', 'username': ''}, f)
    except:
        pass

def run_login_in_thread(platform, socketio, callback):
    socketio.emit('log', {'message': f'🌐 Opening {platform.upper()} login...', 'type': 'info'})
    
    temp = tempfile.gettempdir()
    ts = int(time.time())
    rf = os.path.join(temp, f'cr_{platform}_{ts}.json')
    lf = os.path.join(temp, f'cr_{platform}_{ts}.log')
    
    p = multiprocessing.Process(target=login_worker, args=(platform, rf, lf))
    p.start()
    
    def monitor():
        p.join(timeout=600)
        if p.is_alive():
            p.terminate()
        
        cookie = None
        try:
            if os.path.exists(rf):
                import json
                with open(rf) as f:
                    d = json.load(f)
                    cookie = d.get('cookie') or None
                os.remove(rf)
        except:
            pass
        
        try:
            os.path.exists(lf) and os.remove(lf)
        except:
            pass
        
        callback(platform, cookie, None)
    
    threading.Thread(target=monitor, daemon=True).start()
