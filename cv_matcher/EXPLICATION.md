# Explication du projet CV Matcher

Ce document explique à quoi sert chaque fichier et chaque partie du code.

## Vue d'ensemble

L'utilisateur dépose son CV (PDF ou DOCX) sur une page web. L'application :
1. extrait le texte du CV,
2. le compare au texte de chaque mission stockée dans une base de données,
3. calcule un score de similarité (0 à 100 %) pour chaque mission,
4. affiche les 5 missions les plus proches du profil, avec les mots-clés communs.

```
cv_matcher/
├── app.py            -> serveur Flask (routes web, formulaire, orchestration)
├── matcher.py        -> logique d'extraction de texte + calcul des scores
├── database.py       -> connexion SQLite + lecture des missions
├── seed_db.py        -> script qui remplit la base avec des missions d'exemple
├── requirements.txt  -> liste des librairies Python nécessaires
├── missions.db       -> fichier de base de données SQLite (créé au démarrage)
├── templates/
│   └── index.html    -> page web (formulaire + résultats)
├── static/
│   └── style.css     -> mise en forme de la page
└── uploads/          -> dossier temporaire où le CV est écrit puis supprimé
```

---

## 1. `database.py` — la base de données

```python
DB_PATH = os.path.join(os.path.dirname(__file__), "missions.db")
```
Définit le chemin du fichier SQLite `missions.db`, placé à côté du code. C'est un fichier de base de données léger : pas besoin d'installer un serveur dédié.

```python
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```
Ouvre une connexion à la base. `row_factory = sqlite3.Row` permet d'accéder aux colonnes par leur nom (ex. : `row["title"]`) au lieu d'indices numériques.

```python
def init_db():
    ...
    CREATE TABLE IF NOT EXISTS missions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL
    )
```
Crée la table `missions` si elle n'existe pas encore. Chaque mission possède un identifiant, un titre et une description.

```python
def get_all_missions():
    rows = conn.execute("SELECT id, title, description FROM missions").fetchall()
    return [dict(row) for row in rows]
```
Récupère toutes les missions de la base et les transforme en liste de dictionnaires Python, par exemple :
```python
[{"id": 1, "title": "Développeur Python Backend", "description": "..."}, ...]
```

---

## 2. `seed_db.py` — peupler la base avec des données de test

```python
MISSIONS = [
    ("Développeur Python Backend", "Mission de développement d'API REST avec Flask..."),
    ("Data Scientist", "Mission d'analyse de données..."),
    ...
]
```
Liste de 10 missions d'exemple (titre + description) représentatives de profils IT.

```python
def seed():
    init_db()
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
    if existing == 0:
        conn.executemany("INSERT INTO missions (title, description) VALUES (?, ?)", MISSIONS)
        conn.commit()
```
- Crée la table si nécessaire (`init_db()`).
- Vérifie si la table est vide.
- Si oui, insère les 10 missions d'un coup avec `executemany`.
- Si la table contient déjà des données, ne fait rien (évite les doublons si l'on relance le script).

C'est un script à part, lancé manuellement avec `python seed_db.py`, séparé de `app.py` car on n'a besoin de l'exécuter qu'une seule fois (ou quand on souhaite réinitialiser les données).

---

## 3. `matcher.py` — le cœur de l'analyse

### Chargement du modèle de langue français

```python
_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("fr_core_news_sm")
    return _nlp
```
`fr_core_news_sm` est un modèle spaCy entraîné sur du texte français. Il est capable de :
- découper une phrase en mots (tokenisation),
- ramener chaque mot à sa forme de base, appelée **lemme** (ex. : « développais », « développeur », « développement » → « développer »),
- repérer les mots vides (« le », « de », « et »…), appelés **stopwords**.

Le modèle est volumineux et lent à charger : on le charge **une seule fois** (variable globale `_nlp`) et on le réutilise, au lieu de le recharger à chaque requête.

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
Ouvre un fichier Word (.docx) et concatène le texte de tous les paragraphes avec `python-docx`.

```python
def extract_text(filepath):
    if filepath.lower().endswith(".pdf"):
        return extract_text_from_pdf(filepath)
    if filepath.lower().endswith(".docx"):
        return extract_text_from_docx(filepath)
    raise ValueError(...)
```
Fonction d'aiguillage : examine l'extension du fichier et appelle la bonne fonction d'extraction.

### Prétraitement du texte (`preprocess`)

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
Étapes :
1. `text.lower()` : tout le texte passe en minuscules.
2. `nlp(text)` : spaCy analyse le texte et le découpe en tokens (mots).
3. Pour chaque token, on conserve uniquement ceux qui :
   - sont composés de lettres (`is_alpha`, donc pas de chiffres ni de ponctuation),
   - ne sont pas des mots vides (`not token.is_stop`),
   - font plus d'une lettre (filtre les lettres isolées).
4. `token.lemma_` : on retient la forme **lemmatisée** du mot (ex. : « développais » → « développer »).

Résultat : une chaîne de mots-clés nettoyés (`cv_clean`, utilisée pour le calcul de similarité) et un `set` des mots uniques (`cv_tokens`, utilisé pour trouver les mots-clés communs).

### Calcul du classement (`rank_missions`)

C'est la fonction appelée par `app.py`. Elle prend le texte du CV et la liste des missions, et renvoie les 5 meilleures.

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
Nettoie le titre et la description de chaque mission de la même façon.

```python
vectorizer = TfidfVectorizer()
tfidf_matrix = vectorizer.fit_transform([cv_clean] + mission_cleaned)
```
**TF-IDF** (Term Frequency — Inverse Document Frequency) transforme chaque texte en un vecteur de nombres :
- un mot fréquent dans un texte mais rare dans l'ensemble des textes obtient un poids élevé (il est « caractéristique »),
- un mot qui revient partout (peu informatif) obtient un poids faible.

`fit_transform([cv_clean] + mission_cleaned)` construit ces vecteurs pour le CV **et** toutes les missions **en même temps**, avec le même vocabulaire, pour qu'ils soient comparables.

```python
similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
```
- `tfidf_matrix[0:1]` = le vecteur du CV (première ligne).
- `tfidf_matrix[1:]` = les vecteurs de toutes les missions (lignes suivantes).
- `cosine_similarity` mesure l'angle entre deux vecteurs : 1 = identiques, 0 = aucun mot pertinent en commun. On obtient un score entre 0 et 1 pour chaque mission.

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
- `score` : la similarité convertie en pourcentage (0-100), arrondie à 1 décimale.
- `common_keywords` : intersection (`&`) entre les mots-clés du CV et ceux de la mission → les mots qu'ils ont en commun.

```python
results.sort(key=lambda r: r["score"], reverse=True)
return results[:top_n]
```
Trie les missions par score décroissant et ne conserve que les `top_n` premières (5 par défaut).

---

## 4. `app.py` — le serveur web Flask

```python
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
init_db()
```
- Crée l'application Flask.
- Définit le dossier `uploads/` où les fichiers envoyés seront temporairement enregistrés (le crée s'il n'existe pas).
- `init_db()` : s'assure que la table `missions` existe dès le démarrage du serveur.

```python
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
```
Vérifie que le fichier envoyé possède bien une extension `.pdf` ou `.docx`.

```python
@app.route("/", methods=["GET", "POST"])
def index():
```
Une seule route (`/`) qui gère :
- **GET** : affiche la page vide (formulaire d'upload).
- **POST** : traite le fichier envoyé par le formulaire.

Déroulement du POST :
```python
cv_file = request.files.get("cv_file")

if not cv_file or cv_file.filename == "":
    error = "Veuillez sélectionner un fichier CV."
elif not allowed_file(cv_file.filename):
    error = "Format de fichier non supporté. Utilisez un PDF ou DOCX."
else:
    ...
```
1. Vérifie qu'un fichier a bien été envoyé.
2. Vérifie que son extension est autorisée.

```python
filename = secure_filename(cv_file.filename)
filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
cv_file.save(filepath)
```
- `secure_filename` nettoie le nom du fichier (supprime les caractères dangereux et empêche qu'un nom malveillant écrive en dehors du dossier `uploads/`).
- Le fichier est enregistré temporairement sur le disque (nécessaire car `pdfplumber` et `python-docx` lisent un fichier, pas directement des octets en mémoire dans ce code).

```python
try:
    cv_text = extract_text(filepath)
    if not cv_text.strip():
        error = "Impossible d'extraire le texte du CV."
    else:
        missions = get_all_missions()
        if not missions:
            error = "Aucune mission disponible dans la base de données."
        else:
            results = rank_missions(cv_text, missions, top_n=5)
finally:
    os.remove(filepath)
```
- Extrait le texte du CV.
- Si le texte est vide (PDF scanné sans texte, par exemple), affiche une erreur.
- Sinon, récupère toutes les missions et calcule le top 5 avec `rank_missions`.
- Le bloc `finally` garantit que le fichier uploadé est **toujours supprimé** du disque, même en cas d'erreur (le CV ne reste jamais stocké).

```python
return render_template("index.html", results=results, error=error)
```
Renvoie la page HTML en lui transmettant soit les résultats (`results`), soit un message d'erreur (`error`).

```python
if __name__ == "__main__":
    app.run(debug=True)
```
Lance le serveur de développement Flask. `debug=True` recharge automatiquement le serveur lors d'une modification du code et affiche les erreurs détaillées dans le navigateur.

---

## 5. `templates/index.html` — la page web

C'est un template **Jinja2** (le moteur de templates de Flask). Les balises `{{ ... }}` et `{% ... %}` sont remplacées par Flask au moment de générer la page.

```html
<form method="POST" enctype="multipart/form-data" class="match-form">
    <label for="cv_file">CV (PDF ou DOCX)</label>
    <input type="file" id="cv_file" name="cv_file" accept=".pdf,.docx" required>
    <button type="submit">Analyser</button>
</form>
```
- `enctype="multipart/form-data"` est obligatoire pour pouvoir envoyer un fichier dans un formulaire.
- `name="cv_file"` est le nom utilisé côté serveur (`request.files.get("cv_file")`).
- `accept=".pdf,.docx"` filtre les fichiers proposés par le navigateur (mais ne remplace pas la vérification côté serveur).

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
- `{% for mission in results %}` boucle sur les 5 missions renvoyées par `app.py`.
- Pour chacune : titre, score (en %), une barre de progression (largeur = score), la description et la liste des mots-clés communs.

---

## 6. `static/style.css` — le style

Fichier CSS classique : couleurs, espacements, arrondis. Points notables :
- `.score-bar` / `.score-fill` : la barre grise est le conteneur ; la barre colorée (`width: {{ mission.score }}%`) représente visuellement le score.
- `.mission-card` : encadre chaque mission dans un bloc avec une bordure.
- `.keywords li` : transforme chaque mot-clé en pastille (badge arrondi).

---

## 7. `requirements.txt` — les dépendances

| Librairie | Rôle |
|---|---|
| `flask` | Le serveur web (routes, formulaires, templates) |
| `pdfplumber` | Lire le texte des fichiers PDF |
| `python-docx` | Lire le texte des fichiers Word (.docx) |
| `scikit-learn` | TF-IDF + similarité cosinus pour calculer les scores |
| `spacy` | Analyse linguistique du français (lemmatisation, stopwords) |
| `openai` | Présent mais non utilisé actuellement (réservé pour une fonctionnalité future, ex. : explication du score générée par IA) |

Le modèle `fr_core_news_sm` n'est pas un paquet PyPI standard ; il s'installe séparément (voir le commentaire dans `requirements.txt`).

---

## Résumé du flux complet

1. L'utilisateur ouvre `/` → `app.py` affiche `index.html` (formulaire vide).
2. L'utilisateur choisit un CV et clique sur « Analyser » → requête **POST**.
3. `app.py` sauvegarde temporairement le fichier dans `uploads/`.
4. `matcher.extract_text()` lit le PDF ou DOCX et récupère le texte brut.
5. `matcher.rank_missions()` :
   - nettoie et lemmatise le texte du CV et de chaque mission (`preprocess`),
   - vectorise l'ensemble avec TF-IDF,
   - calcule la similarité cosinus entre le CV et chaque mission,
   - trie et conserve les 5 meilleures.
6. `app.py` supprime le fichier uploadé et renvoie `index.html` avec les résultats.
7. `index.html` affiche les 5 missions, leur score et les mots-clés communs.
