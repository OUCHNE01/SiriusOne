# Explication du projet CV Matcher

Ce document explique a quoi sert chaque fichier et chaque partie du code.

## Vue d'ensemble

L'utilisateur depose son CV (PDF ou DOCX) sur une page web. L'application :
1. extrait le texte du CV,
2. le compare au texte de chaque "mission" stockee dans une base de donnees,
3. calcule un score de similarite (0 a 100%) pour chaque mission,
4. affiche les 5 missions les plus proches du profil, avec les mots-cles communs.

```
cv_matcher/
├── app.py            -> serveur Flask (routes web, formulaire, orchestration)
├── matcher.py        -> logique d'extraction de texte + calcul des scores
├── database.py       -> connexion SQLite + lecture des missions
├── seed_db.py        -> script qui remplit la base avec des missions d'exemple
├── requirements.txt  -> liste des librairies Python necessaires
├── missions.db       -> fichier de base de donnees SQLite (crée au démarrage)
├── templates/
│   └── index.html    -> page web (formulaire + resultats)
├── static/
│   └── style.css      -> mise en forme de la page
└── uploads/           -> dossier temporaire ou le CV est ecrit puis supprime
```

---

## 1. `database.py` - la base de donnees

```python
DB_PATH = os.path.join(os.path.dirname(__file__), "missions.db")
```
Definit le chemin du fichier SQLite `missions.db`, place a cote du code (un fichier de base de donnees, pas besoin d'installer un serveur de base de donnees).

```python
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```
Ouvre une connexion à la base. `row_factory = sqlite3.Row` permet d'acceder aux colonnes par leur nom (ex: `row["title"]`) au lieu d'index numeriques.

```python
def init_db():
    ...
    CREATE TABLE IF NOT EXISTS missions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL
    )
```
Crée la table `missions` si elle n'existe pas encore. Chaque mission a un identifiant, un titre et une description.

```python
def get_all_missions():
    rows = conn.execute("SELECT id, title, description FROM missions").fetchall()
    return [dict(row) for row in rows]
```
Recupere toutes les missions de la base et les transforme en liste de dictionnaires Python, ex :
```python
[{"id": 1, "title": "Developpeur Python Backend", "description": "..."}, ...]
```

---

## 2. `seed_db.py` - peupler la base avec des donnees de test

```python
MISSIONS = [
    ("Developpeur Python Backend", "Mission de developpement d'API REST avec Flask..."),
    ("Data Scientist", "Mission d'analyse de donnees..."),
    ...
]
```
Liste de 10 missions d'exemple (titre + description) representatives de profils IT.

```python
def seed():
    init_db()
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
    if existing == 0:
        conn.executemany("INSERT INTO missions (title, description) VALUES (?, ?)", MISSIONS)
        conn.commit()
```
- Cree la table si besoin (`init_db()`).
- Verifie si la table est vide.
- Si oui, insere les 10 missions d'un coup avec `executemany`.
- Si la table contient deja des donnees, ne fait rien (evite les doublons si on relance le script).

C'est un script a part, lance manuellement avec `python seed_db.py`, separe de `app.py` car on n'a besoin de le faire qu'une seule fois (ou quand on veut reinitialiser les donnees).

---

## 3. `matcher.py` - le coeur de l'analyse

### Chargement du modele de langue francais

```python
_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("fr_core_news_sm")
    return _nlp
```
`fr_core_news_sm` est un modele spaCy entraine sur du texte francais. Il sait :
- decouper une phrase en mots (tokenisation),
- ramener chaque mot a sa forme de base / **lemme** (ex: "developpais", "developpeur", "developpement" -> "developper" ou "developpeur"),
- reperer les mots vides ("le", "de", "et"...) appeles **stopwords**.

Le modele est gros et lent a charger : on le charge **une seule fois** (variable globale `_nlp`) et on le reutilise, au lieu de le recharger a chaque requete.

### Extraction du texte du CV

```python
def extract_text_from_pdf(filepath):
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
```
Ouvre le PDF page par page et extrait le texte brut de chaque page avec `pdfplumber`.

```python
def extract_text_from_docx(filepath):
    document = docx.Document(filepath)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
```
Ouvre un fichier Word (.docx) et concatene le texte de tous les paragraphes avec `python-docx`.

```python
def extract_text(filepath):
    if filepath.lower().endswith(".pdf"):
        return extract_text_from_pdf(filepath)
    if filepath.lower().endswith(".docx"):
        return extract_text_from_docx(filepath)
    raise ValueError(...)
```
Fonction "aiguilleur" : regarde l'extension du fichier et appelle la bonne fonction d'extraction.

### Pretraitement du texte (`preprocess`)

```python
def preprocess(text):
    nlp = get_nlp()
    doc = nlp(text.lower())
    tokens = [
        token.lemma_
        for token in doc
        if token.is_alpha and not token.is_stop and len(token) > 1
    ]
    return " ".join(tokens), set(tokens)
```
Etapes :
1. `text.lower()` : tout passe en minuscules.
2. `nlp(text)` : spaCy analyse le texte et le decoupe en "tokens" (mots).
3. Pour chaque token, on garde seulement ceux qui :
   - sont composes de lettres (`is_alpha`, donc pas de chiffres/ponctuation),
   - ne sont pas des mots vides (`not token.is_stop`),
   - font plus d'une lettre (filtre les lettres isolees).
4. `token.lemma_` : on prend la forme **lemmatisee** du mot (ex: "developpais" -> "developper").

Resultat : une chaine de mots-cles nettoyes (`cv_clean`, utilisee pour le calcul de similarite) et un `set` des mots uniques (`cv_tokens`, utilise pour trouver les mots-cles communs).

### Calcul du classement (`rank_missions`)

C'est la fonction appelee par `app.py`. Elle prend le texte du CV et la liste des missions, et renvoie les 5 meilleures.

```python
cv_clean, cv_tokens = preprocess(cv_text)
```
Nettoie le texte du CV.

```python
for mission in missions:
    clean, tokens = preprocess(f"{mission['title']} {mission['description']}")
    mission_cleaned.append(clean)
    mission_tokens_list.append(tokens)
```
Nettoie le titre + la description de chaque mission de la meme facon.

```python
vectorizer = TfidfVectorizer()
tfidf_matrix = vectorizer.fit_transform([cv_clean] + mission_cleaned)
```
**TF-IDF** (Term Frequency - Inverse Document Frequency) transforme chaque texte en un vecteur de nombres :
- un mot frequent dans un texte mais rare dans l'ensemble des textes obtient un poids eleve (il est "caracteristique"),
- un mot qui revient partout (peu informatif) obtient un poids faible.

`fit_transform([cv_clean] + mission_cleaned)` construit ces vecteurs pour le CV **et** toutes les missions **en meme temps**, avec le meme vocabulaire, pour qu'ils soient comparables.

```python
similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
```
- `tfidf_matrix[0:1]` = le vecteur du CV (1ere ligne).
- `tfidf_matrix[1:]` = les vecteurs de toutes les missions (lignes suivantes).
- `cosine_similarity` mesure l'angle entre deux vecteurs : 1 = identiques, 0 = aucun mot en commun pertinent. On obtient un score entre 0 et 1 pour chaque mission.

```python
for mission, similarity, tokens in zip(missions, similarities, mission_tokens_list):
    results.append({
        "id": mission["id"],
        "title": mission["title"],
        "description": mission["description"],
        "score": round(float(similarity) * 100, 1),
        "common_keywords": sorted(cv_tokens & tokens),
    })
```
Pour chaque mission :
- `score` : la similarite convertie en pourcentage (0-100), arrondie a 1 decimale.
- `common_keywords` : intersection (`&`) entre les mots-cles du CV et ceux de la mission -> les mots qu'ils ont en commun.

```python
results.sort(key=lambda r: r["score"], reverse=True)
return results[:top_n]
```
Trie les missions par score decroissant et ne garde que les `top_n` premieres (5 par defaut).

---

## 4. `app.py` - le serveur web Flask

```python
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
init_db()
```
- Cree l'application Flask.
- Definit le dossier `uploads/` ou les fichiers envoyes seront temporairement enregistres (le cree s'il n'existe pas).
- `init_db()` : s'assure que la table `missions` existe des le demarrage du serveur.

```python
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
```
Verifie que le fichier envoye a bien une extension `.pdf` ou `.docx`.

```python
@app.route("/", methods=["GET", "POST"])
def index():
```
Une seule route (`/`) qui gere :
- **GET** : affiche la page vide (formulaire d'upload).
- **POST** : traite le fichier envoye par le formulaire.

Deroulement du POST :
```python
cv_file = request.files.get("cv_file")

if not cv_file or cv_file.filename == "":
    error = "Veuillez selectionner un fichier CV."
elif not allowed_file(cv_file.filename):
    error = "Format de fichier non supporte. Utilisez un PDF ou DOCX."
else:
    ...
```
1. Verifie qu'un fichier a bien ete envoye.
2. Verifie que son extension est autorisee.

```python
filename = secure_filename(cv_file.filename)
filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
cv_file.save(filepath)
```
- `secure_filename` nettoie le nom du fichier (retire les caracteres dangereux, evite qu'un nom de fichier malveillant ecrive en dehors du dossier `uploads/`).
- Le fichier est enregistre temporairement sur le disque (necessaire car `pdfplumber`/`python-docx` lisent un fichier, pas directement les octets en memoire dans ce code).

```python
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
```
- Extrait le texte du CV.
- Si le texte est vide (PDF scanne sans texte par exemple), affiche une erreur.
- Sinon, recupere toutes les missions et calcule le top 5 avec `rank_missions`.
- Le `finally` garantit que le fichier uploade est **toujours supprime** du disque, meme en cas d'erreur (le CV ne reste jamais stocke).

```python
return render_template("index.html", results=results, error=error)
```
Renvoie la page HTML, en lui passant soit les resultats (`results`), soit un message d'erreur (`error`).

```python
if __name__ == "__main__":
    app.run(debug=True)
```
Lance le serveur de developpement Flask. `debug=True` recharge automatiquement le serveur quand le code change, et affiche les erreurs detaillees dans le navigateur.

---

## 5. `templates/index.html` - la page web

C'est un template **Jinja2** (le moteur de templates de Flask). Les balises `{{ ... }}` et `{% ... %}` sont remplacees par Flask au moment de generer la page.

```html
<form method="POST" enctype="multipart/form-data" class="match-form">
    <label for="cv_file">CV (PDF ou DOCX)</label>
    <input type="file" id="cv_file" name="cv_file" accept=".pdf,.docx" required>
    <button type="submit">Analyser</button>
</form>
```
- `enctype="multipart/form-data"` est obligatoire pour pouvoir envoyer un fichier dans un formulaire.
- `name="cv_file"` est le nom utilise cote serveur (`request.files.get("cv_file")`).
- `accept=".pdf,.docx"` filtre les fichiers proposes par le navigateur (mais ne remplace pas la verification cote serveur).

```html
{% if error %}
<div class="alert alert-error">{{ error }}</div>
{% endif %}
```
Affiche le message d'erreur s'il y en a un.

```html
{% if results %}
<div class="result">
    <h2>Top {{ results|length }} missions correspondantes</h2>
    {% for mission in results %}
    <div class="mission-card">
        <h3>{{ mission.title }}</h3>
        <span class="mission-score">{{ mission.score }}%</span>
        <div class="score-bar">
            <div class="score-fill" style="width: {{ mission.score }}%"></div>
        </div>
        <p class="mission-description">{{ mission.description }}</p>
        <ul class="keywords">
            {% for keyword in mission.common_keywords %}
            <li>{{ keyword }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endfor %}
</div>
{% endif %}
```
- `{% for mission in results %}` boucle sur les 5 missions renvoyees par `app.py`.
- Pour chacune : titre, score (en %), une barre de progression (largeur = score), la description, et la liste des mots-cles communs.

---

## 6. `static/style.css` - le style

Fichier CSS classique : couleurs, espacements, arrondis. Points notables :
- `.score-bar` / `.score-fill` : la barre grise est le conteneur, la barre verte (`width: {{ mission.score }}%`) represente visuellement le score.
- `.mission-card` : encadre chaque mission dans un bloc avec une bordure.
- `.keywords li` : transforme chaque mot-cle en "pastille" (badge arrondi).

---

## 7. `requirements.txt` - les dependances

| Librairie | Role |
|---|---|
| `flask` | Le serveur web (routes, formulaires, templates) |
| `pdfplumber` | Lire le texte des fichiers PDF |
| `python-docx` | Lire le texte des fichiers Word (.docx) |
| `scikit-learn` | TF-IDF + similarite cosinus pour calculer les scores |
| `spacy` | Analyse linguistique du francais (lemmatisation, stopwords) |
| `openai` | Present mais non utilise actuellement (reserve pour une future fonctionnalite, ex: explication du score generee par IA) |

Le modele `fr_core_news_sm` n'est pas un paquet PyPI normal, il s'installe a part (voir commentaire dans `requirements.txt`).

---

## Resume du flux complet

1. L'utilisateur ouvre `/` -> `app.py` affiche `index.html` (formulaire vide).
2. L'utilisateur choisit un CV et clique sur "Analyser" -> requete **POST**.
3. `app.py` sauvegarde temporairement le fichier dans `uploads/`.
4. `matcher.extract_text()` lit le PDF ou DOCX et recupere le texte brut.
5. `matcher.rank_missions()` :
   - nettoie/lemmatise le texte du CV et de chaque mission (`preprocess`),
   - vectorise tout avec TF-IDF,
   - calcule la similarite cosinus entre le CV et chaque mission,
   - trie et garde les 5 meilleures.
6. `app.py` supprime le fichier uploade et renvoie `index.html` avec les resultats.
7. `index.html` affiche les 5 missions, leur score et les mots-cles communs.
