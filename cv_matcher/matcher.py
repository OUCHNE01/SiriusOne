import pdfplumber
import docx
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("fr_core_news_sm")
    return _nlp


def extract_text_from_pdf(filepath):
    pages = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
    return "\n".join(pages)


def extract_text_from_docx(filepath):
    document = docx.Document(filepath)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text(filepath):
    lower_path = filepath.lower()
    if lower_path.endswith(".pdf"):
        return extract_text_from_pdf(filepath)
    if lower_path.endswith(".docx"):
        return extract_text_from_docx(filepath)
    raise ValueError("Format de fichier non supporte (PDF ou DOCX uniquement)")


def preprocess(text):
    nlp = get_nlp()
    doc = nlp(text.lower())
    tokens = [
        token.lemma_
        for token in doc
        if token.is_alpha and not token.is_stop and len(token) > 1
    ]
    return " ".join(tokens), set(tokens)


def rank_missions(cv_text, missions, top_n=5):
    cv_clean, cv_tokens = preprocess(cv_text)

    mission_cleaned = []
    mission_tokens_list = []
    for mission in missions:
        clean, tokens = preprocess(f"{mission['title']} {mission['description']}")
        mission_cleaned.append(clean)
        mission_tokens_list.append(tokens)

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([cv_clean] + mission_cleaned)
    similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

    results = []
    for mission, similarity, tokens in zip(missions, similarities, mission_tokens_list):
        results.append({
            "id": mission["id"],
            "title": mission["title"],
            "description": mission["description"],
            "score": round(float(similarity) * 100, 1),
            "common_keywords": sorted(cv_tokens & tokens),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]
