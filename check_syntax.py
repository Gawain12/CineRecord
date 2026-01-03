
try:
    from web.logic import normalize_movie, get_unified_diff
    print("Syntax check passed: normalize_movie and get_unified_diff are importable.")
except ImportError as e:
    print(f"ImportError: {e}")
except SyntaxError as e:
    print(f"SyntaxError: {e}")
except Exception as e:
    print(f"Error: {e}")
