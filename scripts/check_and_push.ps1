Param(
    [switch]$AutoPush,
    [switch]$AutoCommit,
    [string]$RemoteName = 'origin'
)

function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Err "git not found in PATH. Install Git and re-run this script."
    exit 1
}

$root = Get-Location
Info "Repository root: $root"

if (-not (Test-Path (Join-Path $root '.git'))) {
    Err "No git repository found in $root. Initialize git first."
    exit 1
}

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Info "Current branch: $branch"

try { $remoteUrl = (git remote get-url $RemoteName) } catch { $remoteUrl = '' }
if ($remoteUrl) { Info "Remote '$RemoteName': $remoteUrl" } else { Warn "Remote '$RemoteName' not set." }

Info "Fetching remote references..."
git fetch $RemoteName 2>$null | Out-Null

# Check if .env is tracked
git ls-files --error-unmatch .env >$null 2>&1
if ($LASTEXITCODE -eq 0) {
    Warn ".env is tracked in git (danger). Remove it with: git rm --cached .env && commit && rotate secrets."
    $envTracked = $true
} else { $envTracked = $false }

Info "Checking working tree status..."
$porcelain = git status --porcelain
if ([string]::IsNullOrWhiteSpace($porcelain)) {
    Info "Working tree clean (no unstaged/uncommitted changes)."
} else {
    Write-Host $porcelain
}

$staged = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($staged)) { Info "No staged changes." } else { Info "Staged changes:"; Write-Host $staged }

# Unpushed commits
Info "Checking for unpushed commits (compared to $RemoteName/$branch)..."
try {
    $unpushed = git log --oneline $RemoteName/$branch..HEAD 2>$null
} catch { $unpushed = $null }

if (-not $unpushed) {
    Info "No unpushed commits found (or remote branch missing)."
} else {
    Info "Unpushed commits (newest first):"
    Write-Host $unpushed
}

if (-not [string]::IsNullOrWhiteSpace($porcelain)) {
    if (-not $AutoCommit) {
        Warn "You have uncommitted changes. Commit them first or re-run with -AutoCommit to auto-commit."
        exit 2
    }
    Info "Auto-commit enabled: staging and committing changes (excluding .env)."
    git add -A
    # ensure .env is not accidentally committed
    git reset -- .env 2>$null | Out-Null
    git commit -m "chore: auto-commit remaining local changes before push" || Info "No changes to commit after reset (.env may be present)."

    # recompute unpushed commits
    $unpushed = git log --oneline $RemoteName/$branch..HEAD 2>$null
    if ($unpushed) { Info "After commit, unpushed commits:"; Write-Host $unpushed }
}

if ($unpushed) {
    if ($AutoPush) {
        Info "AutoPush enabled: pushing to $RemoteName/$branch"
        git push $RemoteName $branch
        if ($LASTEXITCODE -ne 0) { Err "Push failed."; exit 3 } else { Info "Push successful." }
    } else {
        Info "No push executed. To push, run this script with -AutoPush or run: git push $RemoteName $branch"
    }
} else {
    Info "Nothing to push."
}

if ($envTracked) {
    Warn "Reminder: .env is tracked. To remove it from the repo:"
    Write-Host "  git rm --cached .env"
    Write-Host "  echo '.env' >> .gitignore"
    Write-Host "  git add .gitignore && git commit -m \"chore: remove .env and ignore it\""
}

Info "Done."
