from database import get_connection, init_db

MISSIONS = [
    (
        "Developpeur Python Backend",
        "Mission de developpement d'API REST avec Flask et Django. "
        "Conception de modeles de donnees PostgreSQL, ecriture de tests unitaires, "
        "integration continue avec Git et Docker. Experience en architecture microservices appreciee.",
    ),
    (
        "Data Scientist",
        "Mission d'analyse de donnees et modelisation predictive. Utilisation de Python, pandas, "
        "scikit-learn et notebooks Jupyter pour construire des modeles de machine learning. "
        "Presentation des resultats aux equipes metier et redaction de rapports.",
    ),
    (
        "Developpeur Frontend React",
        "Mission de developpement d'interfaces utilisateur avec React et TypeScript. "
        "Integration de maquettes Figma, gestion d'etat avec Redux, ecriture de tests "
        "avec Jest et collaboration etroite avec l'equipe design.",
    ),
    (
        "Ingenieur DevOps",
        "Mission de mise en place et maintenance de pipelines CI/CD avec GitLab CI et Jenkins. "
        "Conteneurisation des applications avec Docker et orchestration Kubernetes. "
        "Surveillance de l'infrastructure avec Prometheus et Grafana sur AWS.",
    ),
    (
        "Developpeur Full Stack JavaScript",
        "Mission de developpement d'applications web avec Node.js cote serveur et React cote client. "
        "Conception d'API REST, base de donnees MongoDB, deploiement sur des environnements cloud "
        "et participation aux ceremonies agiles.",
    ),
    (
        "Data Engineer",
        "Mission de construction de pipelines de donnees ETL avec Python, Apache Spark et Airflow. "
        "Modelisation d'entrepots de donnees, optimisation des requetes SQL et mise en place "
        "de flux de traitement de donnees a grande echelle.",
    ),
    (
        "Developpeur Mobile Flutter",
        "Mission de developpement d'applications mobiles multiplateformes avec Flutter et Dart. "
        "Integration d'API REST, gestion de l'authentification, publication sur l'App Store "
        "et le Google Play Store.",
    ),
    (
        "Administrateur Systemes Linux",
        "Mission d'administration de serveurs Linux, gestion des sauvegardes, supervision "
        "et securisation de l'infrastructure. Automatisation des taches avec des scripts Bash "
        "et Ansible, gestion des droits utilisateurs et du reseau.",
    ),
    (
        "Chef de Projet IT / Scrum Master",
        "Mission de pilotage de projets informatiques en methodologie agile Scrum. "
        "Animation des ceremonies (sprint planning, retrospectives), suivi du backlog "
        "avec Jira, coordination entre les equipes techniques et les parties prenantes.",
    ),
    (
        "Developpeur PHP Symfony",
        "Mission de developpement et maintenance d'applications web avec PHP et le framework "
        "Symfony. Conception de bases de donnees MySQL, ecriture de tests avec PHPUnit "
        "et integration de Composer pour la gestion des dependances.",
    ),
]


def seed():
    init_db()
    conn = get_connection()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
        if existing == 0:
            conn.executemany(
                "INSERT INTO missions (title, description) VALUES (?, ?)", MISSIONS
            )
            conn.commit()
            print(f"{len(MISSIONS)} missions inserees.")
        else:
            print("La table missions contient deja des donnees, aucune insertion effectuee.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
