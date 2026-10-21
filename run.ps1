$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.venv')) {
    py -3.11 -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py @args
