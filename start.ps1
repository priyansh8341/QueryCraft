$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    & '.venv/Scripts/python.exe' -m pip install -r requirements.txt
}
if (!(Test-Path -LiteralPath 'web/dist/index.html')) {
    throw 'Build the frontend first: cd web; corepack pnpm install; corepack pnpm build. See README.md.'
}
& '.venv/Scripts/python.exe' -m uvicorn server:app --host 127.0.0.1 --port 8040
