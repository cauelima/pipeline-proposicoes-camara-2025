# src/transforma.py: etapa T do pipeline
import json, logging
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
TRATADA_DIR = Path("data/tratada")
ANO = 2025

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def raw_mais_recente() -> Path:
    """O ultimo raw pelo carimbo UTC no nome do arquivo."""
    arquivos = sorted(RAW_DIR.glob("proposicoes_*.json"))
    if not arquivos:
        raise SystemExit("nenhum raw: rode src/coleta.py antes")
    return arquivos[-1]


def carregar_raw(caminho: Path) -> dict:
    with open(caminho, encoding="utf-8") as arq:
        return json.load(arq)


def transformar(conteudo: dict, origem: str) -> pd.DataFrame:
    """Achata a lista de proposicoes em DataFrame limpo e tipado."""
    df = pd.DataFrame(conteudo["proposicoes"])

    df = df[["id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao",
             "autor_id", "autor_nome", "autor_partido", "autor_uf"]]

    df = df.rename(columns={
        "id": "id_proposicao",
        "siglaTipo": "tipo",
        "dataApresentacao": "data_apresentacao",
    })

    for coluna in ["id_proposicao", "numero", "ano", "autor_id"]:
        df[coluna] = df[coluna].astype(int)

    df["data_apresentacao"] = pd.to_datetime(df["data_apresentacao"])

    df["arquivo_origem"] = origem
    return df


def validar(df: pd.DataFrame) -> None:
    obrigatorias = ["id_proposicao", "autor_partido", "data_apresentacao"]
    for coluna in obrigatorias:
        if coluna not in df.columns:
            raise ValueError(f"coluna ausente: {coluna}")
        if df[coluna].isnull().any():
            raise ValueError(f"coluna com nulo: {coluna}")

    if (df["ano"] != ANO).any():
        raise ValueError(f"proposicao fora do ano {ANO}: recorte violado")

    logger.info("validacao ok: %d linhas integras", len(df))


if __name__ == "__main__":
    caminho = raw_mais_recente()
    logger.info("processando %s", caminho.name)

    df = transformar(carregar_raw(caminho), origem=caminho.name)
    validar(df)

    TRATADA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRATADA_DIR / "proposicoes.csv", index=False)
    logger.info("tratada gravada (%d linhas)", len(df))