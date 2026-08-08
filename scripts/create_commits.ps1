Param(
    [string]$RemoteUrl = "",
    [switch]$PushAfterCommit,
    [int]$MaxCommits = 100,
    [switch]$ForceInit,
    [switch]$DryRun
)

function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Err "git not found in PATH. Install Git and re-run this script."
    exit 1
}

$root = Get-Location
Write-Info "Working in $root"

if ((-not (Test-Path (Join-Path $root '.git'))) -or $ForceInit) {
    Write-Info "Initializing git repository..."
    git init
    git branch -M main
} else {
    Write-Info "Existing git repository detected. Skipping init unless you use -ForceInit."
}

if ($RemoteUrl) {
    Write-Info "Setting remote origin to $RemoteUrl"
    git remote remove origin 2>$null | Out-Null
    git remote add origin $RemoteUrl
}

# helper: ignore patterns
$excludePatterns = @(
    '\.git\\',
    '^media$',
    '^media\\',
    'db.sqlite3$',
    '\\venv\\',
    '\\env\\',
    '\.venv',
    '\.gitignore$',
    '\.env$',
    '\.env\\',
    '\\node_modules\\',
    '\.sqlite3$'
)

Write-Info "Building file list (recursive)..."

# Collect files recursively, exclude patterns
$files = Get-ChildItem -Recurse -File -Force | Where-Object {
    $relative = $_.FullName.Substring($root.Path.Length).TrimStart('\', '/')
    $skip = $false
    foreach ($pat in $excludePatterns) {
        if ($relative -match $pat) { $skip = $true; break }
    }
    -not $skip
} | Sort-Object FullName

if ($files.Count -eq 0) {
    Write-Warn "No candidate files found for committing. Adjust exclusions or run from repository root."
    exit 0
}

Write-Info "Found $($files.Count) files; planning up to $MaxCommits commits."

$plan = @()
$i = 0
foreach ($f in $files) {
    if ($i -ge $MaxCommits) { break }
    $rel = $f.FullName.Substring($root.Path.Length).TrimStart('\', '/')
    # Skip files already ignored by git
    $isIgnored = git check-ignore --quiet -- "$rel"; $ignoredExit = $LASTEXITCODE
    if ($ignoredExit -eq 0) { continue }

    $ext = $f.Extension.ToLower()
    switch ($ext) {
        '.md' { $msg = "docs: add $rel" }
        '.py' { $msg = "feat: add $rel" }
        '.html' { $msg = "feat: add template $rel" }
        '.json' { $msg = "chore: add config $rel" }
        '.yml' { $msg = "chore: add config $rel" }
        default { $msg = "chore: add $rel" }
    }

    $plan += [PSCustomObject]@{ Path = $rel; Message = $msg }
    $i += 1
}

if ($plan.Count -eq 0) { Write-Warn "No files to commit after filtering."; exit 0 }

if ($DryRun) {
    Write-Info "Dry run enabled — showing planned commits (first $($plan.Count))"
    $plan | ForEach-Object { Write-Host "- $($_.Path) -> $($_.Message)" }
    Write-Info "Run with -DryRun:$false to execute commits."
    exit 0
}

$count = 0
foreach ($item in $plan) {
    if ($count -ge $MaxCommits) { break }
    Write-Info "Adding $($item.Path)"
    git add -- "$($item.Path)"
    $status = git diff --cached --name-only
    if ([string]::IsNullOrWhiteSpace($status)) { Write-Warn "No staged changes for $($item.Path), skipping."; continue }

    Write-Info "Committing $($item.Path) -> '$($item.Message)'"
    git commit -m "$($item.Message)"
    if ($LASTEXITCODE -ne 0) { Write-Err "Commit failed for $($item.Path)"; continue }

    $count += 1

    if ($PushAfterCommit) {
        Write-Info "Pushing commit ($count) to origin/main"
        git push origin main
        if ($LASTEXITCODE -ne 0) { Write-Warn "Push failed for commit $count" }
    }
}

Write-Info "Created $count commits (limit $MaxCommits)."
if (-not $PushAfterCommit) { Write-Info "To push all commits to remote, run: git push -u origin main" }
Write-Info "Done. Review the history with: git log --oneline --decorate --graph -n 100"
