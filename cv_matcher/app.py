import os

from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

from database import get_all_missions, init_db
from matcher import extract_text, rank_missions

ALLOWED_EXTENSIONS = {"pdf", "docx"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET", "POST"])
def index():
    results = None
    error = None

    if request.method == "POST":
        cv_file = request.files.get("cv_file")

        if not cv_file or cv_file.filename == "":
            error = "Veuillez selectionner un fichier CV."
        elif not allowed_file(cv_file.filename):
            error = "Format de fichier non supporte. Utilisez un PDF ou DOCX."
        else:
            filename = secure_filename(cv_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            cv_file.save(filepath)
            try:
                cv_text = extract_text(filepath)
                if not cv_text.strip():
                    error = "Impossible d'extraire le texte du CV."
                else:
                    missions = get_all_missions()
                    if not missions:
                        error = "Aucune mission disponible dans la base de donnees."
                    else:
                        results = rank_missions(cv_text, missions, top_n=5)
            finally:
                os.remove(filepath)

    return render_template("index.html", results=results, error=error)


if __name__ == "__main__":
    app.run(debug=True)
