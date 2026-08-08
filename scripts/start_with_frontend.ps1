# Build the frontend and start the backend (Windows PowerShell helper)
# Run this from the repository root with your venv already activated.
# Example: (Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .venv\Scripts\Activate.ps1) ; ./scripts/start_with_frontend.ps1

Write-Host "Starting: build frontend and run backend..."

# Ensure we are in repo root
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Check for Node
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js is not installed or not on PATH. Install Node.js to build the frontend."
    exit 1
}

# Build frontend
Push-Location frontend
if (-not (Test-Path node_modules)) {
    Write-Host "Installing frontend dependencies..."
    npm install
}

Write-Host "Building frontend (production)..."
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend build failed (npm run build returned exit code $LASTEXITCODE)."
    Pop-Location
    exit $LASTEXITCODE
}
Pop-Location

# Start backend (assumes venv/python is active in this shell)
Write-Host "Starting backend (uvicorn) - press Ctrl+C to stop"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
