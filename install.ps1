$ErrorActionPreference = 'Stop'
foreach ($interpreter in @('python', 'python3')) {
    if (Get-Command $interpreter -ErrorAction SilentlyContinue) {
        & $interpreter -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
        if ($LASTEXITCODE -eq 0) {
            & $interpreter (Join-Path $PSScriptRoot 'install.py') @args
            exit $LASTEXITCODE
        }
    }
}
throw 'Python 3.11 or newer was not found.'
