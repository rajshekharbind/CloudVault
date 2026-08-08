# CloudVault

CloudVault is a Django-based file storage and sharing application with real-time activity updates using Django Channels.

Quick start (local)
1. Create and activate a virtualenv:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2. Install dependencies:
```powershell
python -m pip install -r requirements.txt
```
3. Run migrations:
```powershell
python manage.py makemigrations
python manage.py migrate
```
4. Start ASGI server (recommended) to enable WebSockets:
```powershell
.\run_asgi.ps1    # uses daphne by default
# or: .\run_asgi.ps1 -Server uvicorn
```
5. Open http://127.0.0.1:8000/ and log in.

Pushing to GitHub (recommended automated commits)
- Use the provided script to create up to 100 professional commits and push them.
```powershell
# Dry run (preview planned commits)
.\scripts\create_commits.ps1 -RemoteUrl "git@github.com:USERNAME/REPO_NAME.git" -MaxCommits 100 -DryRun

# Execute and push
.\scripts\create_commits.ps1 -RemoteUrl "git@github.com:USERNAME/REPO_NAME.git" -MaxCommits 100 -PushAfterCommit
```

CI
- A basic GitHub Actions workflow is included in `.github/workflows/ci.yml` that installs requirements, runs migrations and runs tests.

Notes
- Ensure `.env` or other secret files are never committed. `.gitignore` includes `.env`.
- For production, configure `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, and a production-ready `DATABASES` (Postgres) and `REDIS_URL` for Channels.

License
- Internal/Proprietary (change as needed)
