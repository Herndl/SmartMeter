"""Entry point — kept for backward compatibility with the systemd service.

All logic has been moved into the smartmeter package.
"""

from smartmeter.runner import main

if __name__ == "__main__":
    main()
