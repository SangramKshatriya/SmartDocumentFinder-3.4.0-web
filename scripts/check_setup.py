from pathlib import Path
import os
import shutil
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

print("Smart Document Finder — multilingual setup check")
print("=" * 58)
print(f"Python: {sys.version.split()[0]}")
print(f"Language provider: {os.getenv('LANGUAGE_PROVIDER', 'sarvam')}")
database_backend = os.getenv("DATABASE_BACKEND", "").strip().lower() or "auto"
database_url = os.getenv("DATABASE_URL", "").strip()
if database_url.lower().startswith(("postgresql://", "postgres://", "postgresql+")):
    resolved_db = "PostgreSQL"
elif database_backend in {"postgres", "postgresql", "pg"}:
    resolved_db = "PostgreSQL (URL required)"
else:
    resolved_db = "local SQLite activity store"
print(f"Activity database: {resolved_db}")
print(f"DATABASE_URL: {'configured' if database_url else 'not configured'}")
digilocker_token = bool(os.getenv("DIGILOCKER_ACCESS_TOKEN", "").strip())
print(f"DigiLocker issued-document access: {'configured' if digilocker_token else 'not configured (optional)'}")

try:
    import PySide6
    print(f"PySide6: OK ({PySide6.__version__})")
except Exception as exc:
    print(f"PySide6: FAIL ({exc})")

try:
    import requests
    print(f"requests: OK ({requests.__version__})")
except Exception as exc:
    print(f"requests: FAIL ({exc})")

try:
    import sqlalchemy
    print(f"SQLAlchemy: OK ({sqlalchemy.__version__})")
except Exception as exc:
    print(f"SQLAlchemy: FAIL ({exc})")

if resolved_db == "PostgreSQL":
    try:
        import psycopg
        print(f"psycopg: OK ({psycopg.__version__})")
    except Exception as exc:
        print(f"psycopg: FAIL ({exc})")

    if database_url:
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(database_url, pool_pre_ping=True, future=True)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()
            print("PostgreSQL connection: OK")
        except Exception as exc:
            print(f"PostgreSQL connection: FAIL ({exc})")

try:
    import pytesseract
    print(f"Tesseract Python binding: OK")
    print(f"Tesseract executable: {shutil.which('tesseract') or os.getenv('TESSERACT_CMD', 'not on PATH')}")
    try:
        langs = pytesseract.get_languages(config="")
        wanted = os.getenv("OCR_LANGUAGES", "eng+hin").split("+")
        print("Installed OCR languages:", ", ".join(sorted(set(langs).intersection(wanted))) or "none of configured languages")
    except Exception as exc:
        print(f"Tesseract runtime: FAIL ({exc})")
except Exception as exc:
    print(f"pytesseract: FAIL ({exc})")

if os.getenv("LANGUAGE_PROVIDER", "sarvam").lower() == "sarvam":
    print(f"Sarvam key: {'configured' if os.getenv('SARVAM_API_KEY') else 'MISSING'}")
elif os.getenv("LANGUAGE_PROVIDER", "").lower() == "bhashini":
    print(f"BHASHINI key: {'configured' if os.getenv('BHASHINI_API_KEY') else 'MISSING'}")

print("\nNext: run `python app.py` or `run.ps1`.")
