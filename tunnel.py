"""
tunnel.py  –  starts Flask + ngrok tunnel simultaneously
Gives you a public URL for mobile access from anywhere.

Requires: pip install pyngrok
Free ngrok account: https://ngrok.com (grab your authtoken)
"""

import os
import sys
import threading
import time

def start_flask():
    os.system("python app.py")

def start_ngrok(token: str):
    try:
        from pyngrok import ngrok, conf
        conf.get_default().auth_token = token
        tunnel = ngrok.connect(5000, "http")
        print("\n" + "="*50)
        print(f"  PUBLIC URL: {tunnel.public_url}")
        print(f"  Bookmark this on your phone ↑")
        print("="*50 + "\n")
    except ImportError:
        print("Run: pip install pyngrok")
        sys.exit(1)
    except Exception as e:
        print(f"ngrok error: {e}")
        print("Get free token at https://ngrok.com")

if __name__ == "__main__":
    token = os.getenv("NGROK_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not token:
        print("Usage: python tunnel.py YOUR_NGROK_TOKEN")
        print("Get free token at https://ngrok.com/signup")
        sys.exit(1)

    # Start ngrok first, then Flask
    t = threading.Thread(target=start_ngrok, args=(token,), daemon=True)
    t.start()
    time.sleep(2)  # let ngrok connect
    start_flask()
