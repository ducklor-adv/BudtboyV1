#!/usr/bin/env python3
"""
BudtBoy Application Entry Point

This is the main entry point for running the BudtBoy application locally.

Usage:
    python run.py

Environment variables can be set in .env file (copy from .env.example)
"""
import os
import sys
from app import create_app
from dotenv import load_dotenv

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Load environment variables
load_dotenv()

# Get configuration from environment
config_name = os.environ.get('FLASK_ENV', 'development')

# Create Flask application
app = create_app(config_name)

if __name__ == '__main__':
    # Get host and port from environment
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'

    print("=" * 60)
    print("🌿 BudtBoy Application Starting... ")
    print("=" * 60)
    print(f"Environment: {config_name}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Debug: {debug}")
    print(f"Database: {app.config['DATABASE_PATH']}")
    print("=" * 60)
    print(f"\n🚀 Application running at: http://{host}:{port}")
    print("Press CTRL+C to quit\n")

    # Run the application
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=debug
    )
