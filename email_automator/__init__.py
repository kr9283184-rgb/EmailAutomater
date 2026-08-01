from flask import Flask

from .routes import api


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.register_blueprint(api)
    return app
