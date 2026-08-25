"""WSGI entry point for Vercel deployment."""
import sys
import os

# Ensure the app directory is in the path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()

# For local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
