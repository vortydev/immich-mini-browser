# app.py
from __future__ import annotations
from flask import Flask, render_template

from config import FLASK_PORT, FLASK_HOST, VERSION, ENV_MODE
from app_utils import print_routes
from blueprints import immich_bp

app = Flask(__name__)
app.register_blueprint(immich_bp)

DEV_ENV = ENV_MODE == "dev"


@app.context_processor
def inject_flags():
    flags = {
        "version": VERSION,
    }
    return flags
 
@app.get("/")
def home():
    return render_template("home.html")

def run_app(print_app_routes: bool = False):
    if print_app_routes:
        print_routes(app)

    with app.app_context():
        app.run( 
            host=FLASK_HOST,
            port=FLASK_PORT,
            debug=DEV_ENV,
        )


if __name__ == "__main__":
    try:
        run_app(print_app_routes=False)
    except KeyboardInterrupt:
        print("User aborted the program!")
        exit()
    except Exception as e:
        print(f"Critical error occured: {e}")
        exit(1)