# src/pipeline.py: o pipeline completo
import logging, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import create_engine

from coleta import coletar_deputados, coletar_proposicoes, salvar_raw
from transforma import raw_mais_recente, carregar_raw, transformar, validar
from config import POSTGRES_URL

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NOME_TABELA = "proposicoes"


def extract() -> None:
    """E: coleta os deputados e os PLs de cada um."""
    deputados = coletar_deputados()
    proposicoes = coletar_proposicoes(deputados)
    caminho = salvar_raw(deputados, proposicoes)
    logger.info("raw salvo em %s — %d proposicoes", caminho, len(proposicoes))


def transform() -> pd.DataFrame:
    """T: processa o raw mais recente."""
    caminho = raw_mais_recente()
    logger.info("processando %s", caminho.name)
    df = transformar(carregar_raw(caminho), origem=caminho.name)
    validar(df)
    return df


def load(df: pd.DataFrame) -> None:
    """L: grava a foto inteira. replace = reexecutavel sem medo."""
    engine = create_engine(POSTGRES_URL)
    df.to_sql(NOME_TABELA, engine, if_exists="replace", index=False)

    total = pd.read_sql(
        f"SELECT COUNT(*) AS n FROM {NOME_TABELA}", engine)["n"][0]
    logger.info("carga concluida: %d linhas", total)


def main() -> None:
    logger.info("pipeline iniciado")
    extract()
    df = transform()
    load(df)
    logger.info("pipeline concluido com sucesso")


if __name__ == "__main__":
    main()