import os
import sys
import json

def get_config_path():
    """Get the persistent path for config.json."""
    if getattr(sys, 'frozen', False):
        # Running as bundled executable
        exe_path = os.path.abspath(sys.executable)
        if 'Contents/MacOS' in exe_path:
            # Mac Bundle: go to directory containing .app
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(exe_path))))
        else:
            base_dir = os.path.dirname(exe_path)
    else:
        # Development mode
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    config_dir = os.path.join(base_dir, 'config')
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, 'config.json')
    
    # Initialize config file if it doesn't exist
    if not os.path.exists(config_path):
        default_config = {
            'douban_user_id': '',
            'douban_cookie': '',
            'imdb_user_id': '',
            'imdb_cookie': ''
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
    
    # Also check for old config.py and migrate if needed
    old_config_path = os.path.join(config_dir, 'config.py')
    if os.path.exists(old_config_path) and os.path.getsize(config_path) < 100:
        # Try to migrate from old format
        try:
            migrate_from_old_config(old_config_path, config_path)
        except Exception as e:
            print(f"Could not migrate old config: {e}")
            
    return config_path

def migrate_from_old_config(old_path, new_path):
    """Migrate from old config.py format to new config.json format."""
    import re
    
    with open(old_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    config = {}
    
    # Parse old DOUBAN_CONFIG format
    douban_block = re.search(r"DOUBAN_CONFIG\s*=\s*\{([^}]+)\}", content, re.DOTALL)
    if douban_block:
        douban_content = douban_block.group(1)
        douban_user = re.search(r"'user_id':\s*'([^']*)'", douban_content)
        douban_cookie = re.search(r"'Cookie':\s*'([^']*)'", douban_content)
        if douban_user: config['douban_user_id'] = douban_user.group(1)
        if douban_cookie: config['douban_cookie'] = douban_cookie.group(1)
    
    # Parse old IMDB_CONFIG format
    imdb_block = re.search(r"IMDB_CONFIG\s*=\s*\{([^}]+)\}", content, re.DOTALL)
    if imdb_block:
        imdb_content = imdb_block.group(1)
        imdb_user = re.search(r"'user_id':\s*'([^']*)'", imdb_content)
        imdb_cookie = re.search(r"'Cookie':\s*'([^']*)'", imdb_content)
        if imdb_user: config['imdb_user_id'] = imdb_user.group(1)
        if imdb_cookie: config['imdb_cookie'] = imdb_cookie.group(1)
    
    if config:
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"Migrated config from {old_path} to {new_path}")

CONFIG_PATH = get_config_path()

def read_config():
    """Reads the configuration file and returns a dictionary of values."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing config JSON: {e}")
        return {}

def write_config(new_values):
    """Updates the configuration file with new values.
    
    Merges new_values with existing config, preserving keys not in new_values.
    """
    try:
        # Read existing config
        existing_config = read_config()
        
        # Merge new values into existing config
        existing_config.update(new_values)
        
        # Write back
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error writing config: {e}")
        return False
