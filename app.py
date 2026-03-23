from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template(
        "welcome.html",
        forename="Test",
        customer_id="NP00001"
    )
