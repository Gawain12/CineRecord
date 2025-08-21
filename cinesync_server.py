# cinesync_server.py
import sys
import os

# Add the 'web' directory to the Python path to ensure all imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'web')))

def main():
    """
    This is the main entry point for the shiv executable.
    It imports and runs the Flask application from web/app.py.
    """
    from app import app, socketio
    from gevent.pywsgi import WSGIServer
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:8000")

    print("🚀 CineRecord Hub is starting...")
    
    # We need to wrap the Flask app with the SocketIO middleware
    # and then serve it with the gevent WSGI server.
    http_server = WSGIServer(('127.0.0.1', 8000), app)
    
    Timer(1, open_browser).start()
    
    print("✅ Server is running at http://127.0.0.1:8000")
    
    # The SocketIO object needs to be attached to the server to handle websockets
    socketio.init_app(app)
    socketio.server = http_server
    
    http_server.serve_forever()

if __name__ == '__main__':
    main()
