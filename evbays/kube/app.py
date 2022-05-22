import os

from flask import Flask
from flask import abort
from flask import json
from flask import jsonify
from flask import make_response
from flask import render_template
from flask import request

DB_FILE = "/tmp/db.json"
app = Flask(__name__)


def _read():
    try:
        with open(DB_FILE, "r") as infile:
            return json.load(infile)
    except FileNotFoundError:
        pass
    return {}


def _save(data):
    tmp_filename = DB_FILE + ".tmp"
    with open(tmp_filename, "w") as outfile:
        json.dump(data, outfile)
    os.rename(tmp_filename, DB_FILE)


@app.route("/")
def top_level():
    return render_template("index.html")


@app.route("/data", methods=["GET"])
def read_bays():
    data = _read()
    return make_response(jsonify(data))


@app.route("/data", methods=["POST"])
def save_bays():
    if not request.json:
        abort(400)

    VALID_KEYS = (
        "text",
        "bays",
        "last-update",
    )

    data = _read()
    for key in VALID_KEYS:
        data[key] = request.json.get(key, data.get(key))
    _save(data)

    return make_response(jsonify(data))
