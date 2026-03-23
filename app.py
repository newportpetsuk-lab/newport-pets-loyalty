from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "TEST VERSION 12345"
