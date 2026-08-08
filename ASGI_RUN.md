Running the ASGI server (WebSockets)
====================================

This project uses Django Channels for WebSocket support. The development `runserver` command may not reliably accept WebSocket connections depending on environment. Use an ASGI server instead.

PowerShell helper (recommended):

```
# Default (daphne) on 127.0.0.1:8000
.\run_asgi.ps1

# Use uvicorn instead
.\run_asgi.ps1 -Server uvicorn

# Customize host/port
.\run_asgi.ps1 -Host 0.0.0.0 -Port 9000
```

Manual commands:

```
# Daphne
python -m pip install daphne
daphne -b 127.0.0.1 -p 8000 cloudvault.asgi:application

# Uvicorn
python -m pip install uvicorn
uvicorn cloudvault.asgi:application --host 127.0.0.1 --port 8000 --reload
```

If you are running via Docker, update your container command to run `daphne` or `uvicorn` instead of `manage.py runserver`.
