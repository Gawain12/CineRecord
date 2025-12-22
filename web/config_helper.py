import re
import os
import sys

def get_config_path():
    """Get the persistent path for config.py."""
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
    config_path = os.path.join(config_dir, 'config.py')
    
    # Initialize config file if it doesn't exist
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("DOUBAN_CONFIG = {'user_id': '', 'Cookie': ''}\nIMDB_CONFIG = {'user_id': '', 'Cookie': ''}\n")
            
    return config_path

CONFIG_PATH = get_config_path()

def read_config():
    """Reads the configuration file and returns a dictionary of values."""
    config = {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # More specific regex to avoid cross-talk
        douban_block = re.search(r"DOUBAN_CONFIG\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        imdb_block = re.search(r"IMDB_CONFIG\s*=\s*\{([^}]+)\}", content, re.DOTALL)

        if douban_block:
            douban_content = douban_block.group(1)
            douban_user = re.search(r"'user_id':\s*'([^']*)'", douban_content)
            douban_cookie = re.search(r"'Cookie':\s*'([^']*)'", douban_content)
            if douban_user: config['douban_user_id'] = douban_user.group(1)
            if douban_cookie: config['douban_cookie'] = douban_cookie.group(1)

        if imdb_block:
            imdb_content = imdb_block.group(1)
            imdb_user_id = re.search(r"'user_id':\s*'([^']*)'", imdb_content)
            imdb_cookie = re.search(r"'Cookie':\s*'([^']*)'", imdb_content)
            if imdb_user_id: config['imdb_user_id'] = imdb_user_id.group(1)
            if imdb_cookie: config['imdb_cookie'] = imdb_cookie.group(1)
            
    except FileNotFoundError:
        pass # Will return empty dict
    return config

def write_config(new_values):
    """Updates the configuration file with new values."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        # Update within DOUBAN_CONFIG block
        if 'douban_user_id' in new_values or 'douban_cookie' in new_values:
            def replace_douban(m):
                block = m.group(1)
                if 'douban_user_id' in new_values:
                    block = re.sub(r"('user_id':\s*')([^']*)'", f"\\1{new_values['douban_user_id']}'", block)
                if 'douban_cookie' in new_values:
                    block = re.sub(r"('Cookie':\s*')([^']*)'", f"\\1{new_values['douban_cookie']}'", block)
                return f"DOUBAN_CONFIG = {{{block}}}"
            content = re.sub(r"DOUBAN_CONFIG\s*=\s*\{([^}]+)\}", replace_douban, content, flags=re.DOTALL)

        # Update within IMDB_CONFIG block
        if 'imdb_user_id' in new_values or 'imdb_cookie' in new_values:
            def replace_imdb(m):
                block = m.group(1)
                if 'imdb_user_id' in new_values:
                    block = re.sub(r"('user_id':\s*')([^']*)'", f"\\1{new_values['imdb_user_id']}'", block)
                if 'imdb_cookie' in new_values:
                    block = re.sub(r"('Cookie':\s*')([^']*)'", f"\\1{new_values['imdb_cookie']}'", block)
                return f"IMDB_CONFIG = {{{block}}}"
            content = re.sub(r"IMDB_CONFIG\s*=\s*\{([^}]+)\}", replace_imdb, content, flags=re.DOTALL)

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing config: {e}")
        return False
