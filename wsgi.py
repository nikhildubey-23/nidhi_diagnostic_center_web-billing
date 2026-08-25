"""WSGI entry point for Vercel deployment."""
import sys
import os
import traceback

# Ensure the app directory is in the path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app import create_app
    app = create_app()
except Exception:
    traceback.print_exc()
    raise

# For local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
