# src/carga_mongo.py: do PostgreSQL para o Atlas
import logging, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import create_engine
from pymongo import MongoClient

from config import POSTGRES_URL, MONGO_URL

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ANO = 2025


def resumir(df: pd.DataFrame) -> list[dict]:
    """Deriva um documento-resumo por partido."""
    documentos = []
    for partido, grupo in df.groupby("autor_partido"):
        proposicoes = grupo["id_proposicao"].nunique()
        deputados = grupo["autor_id"].nunique()
        documentos.append({
            "partido": partido,
            "ano": ANO,
            "total_proposicoes": int(proposicoes),
            "total_autorias": int(len(grupo)),
            "deputados_autores": int(deputados),
            "media_por_deputado": round(proposicoes / deputados, 2),
        })
    documentos.sort(key=lambda d: d["total_proposicoes"], reverse=True)
    return documentos


def main() -> None:
    engine = create_engine(POSTGRES_URL)
    df = pd.read_sql("SELECT * FROM proposicoes", engine)
    logger.info("%d linhas lidas do PostgreSQL", len(df))

    documentos = resumir(df)

    cliente = MongoClient(MONGO_URL)
    colecao = cliente["pipeline_camara"]["resumo_partidos"]
    colecao.delete_many({})
    colecao.insert_many(documentos)
    logger.info("resumo gravado: %d documentos", len(documentos))
    cliente.close()


if __name__ == "__main__":
    main()