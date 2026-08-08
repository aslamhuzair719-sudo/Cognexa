"""Simple IMAP connectivity and login tester using app.config values.

Usage: in activated .venv run `python scripts/test_imap.py`.
"""
from __future__ import annotations

import imaplib
import socket
import sys

import os
import sys

# Ensure project root is on sys.path when running as a script
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config


def main() -> int:
    host = config.IMAP_HOST
    port = config.IMAP_PORT
    user = config.IMAP_USERNAME
    pwd = config.IMAP_PASSWORD
    use_ssl = config.IMAP_USE_SSL

    if not host or not user or not pwd:
        print("IMAP settings are missing. Set IMAP_HOST, IMAP_USERNAME, IMAP_PASSWORD in your .env or environment.")
        return 2

    print(f"Testing IMAP connection to {host}:{port} (ssl={use_ssl})")
    try:
        # simple TCP connect test
        with socket.create_connection((host, port), timeout=10):
            print("TCP connection OK")
    except Exception as exc:
        print("TCP connection FAILED:", exc)
        return 3

    try:
        if use_ssl:
            imap = imaplib.IMAP4_SSL(host, port)
        else:
            imap = imaplib.IMAP4(host, port)
    except Exception as exc:
        print("Failed to establish IMAP session:", exc)
        return 4

    try:
        print("Attempting login as", user)
        imap.login(user, pwd)
        print("Login OK")
        imap.logout()
        return 0
    except imaplib.IMAP4.error as exc:
        print("IMAP login failed:", exc)
        return 5


if __name__ == "__main__":
    sys.exit(main())
