import importlib
import sys
import types

_CONFIG_MODULE = f"{__name__}.config"

try:
    importlib.import_module(_CONFIG_MODULE)
except ModuleNotFoundError as exc:
    if exc.name != _CONFIG_MODULE:
        raise

    try:
        from web.config_helper import read_config
        config_data = read_config() or {}
    except Exception:
        config_data = {}

    douban_user_id = config_data.get("douban_user_id", "")
    douban_cookie = config_data.get("douban_cookie", "")
    imdb_user_id = config_data.get("imdb_user_id", "")
    imdb_cookie = config_data.get("imdb_cookie", "")

    fallback = types.ModuleType(_CONFIG_MODULE)
    fallback.DOUBAN_CONFIG = {
        "user_id": douban_user_id,
        "user": douban_user_id,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://m.douban.com/",
            "Cookie": douban_cookie,
        },
    }
    fallback.IMDB_CONFIG = {
        "user_id": imdb_user_id,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": imdb_cookie,
        },
    }
    fallback.FILE_PATHS = {"output_csv": "web/{}_movie_list.csv"}

    sys.modules[_CONFIG_MODULE] = fallback
    setattr(sys.modules[__name__], "config", fallback)
