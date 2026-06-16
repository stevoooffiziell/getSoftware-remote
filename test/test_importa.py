import sys
print(f"Python Pfad: {sys.executable}")

try:
    import flask_sqlalchemy
    print("? flask_sqlalchemy ist importierbar")
    print(f"  Version: {flask_sqlalchemy.__version__}")
except ImportError as e:
    print(f"? flask_sqlalchemy kann nicht importiert werden: {e}")

try:
    import flask_login
    print("? flask_login ist importierbar")
    print(f"  Version: {flask_login.__version__}")
except ImportError as e:
    print(f"? flask_login kann nicht importiert werden: {e}")

try:
    import flask
    print("? flask ist importierbar")
    print(f"  Version: {flask.__version__}")
except ImportError as e:
    print(f"? flask kann nicht importiert werden: {e}")

# Installationspfade anzeigen
import site
print(f"Site packages: {site.getsitepackages()}")