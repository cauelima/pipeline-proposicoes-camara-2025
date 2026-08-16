# src/coleta.py: etapa E do pipeline
import json, logging, time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://dadosabertos.camara.leg.br/api/v2"
RAW_DIR = Path("data/raw")
ANO = 2025
TIPO = "PL"

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def buscar_pagina(caminho: str, params: dict) -> list[dict]:
    """Uma requisicao defensiva, com retry e backoff exponencial."""
    for tentativa in range(3):
        try:
            resposta = requests.get(f"{BASE}{caminho}", params=params, timeout=15)
            resposta.raise_for_status()
            return resposta.json()["dados"]
        except requests.exceptions.RequestException as erro:
            espera = 2 ** tentativa
            logger.warning("falha em %s (tentativa %d): %s — aguardando %ds",
                           caminho, tentativa + 1, erro, espera)
            time.sleep(espera)
    raise RuntimeError(f"3 tentativas falharam em {caminho}")


def buscar_tudo(caminho: str, params: dict) -> list[dict]:
    """Percorre todas as paginas ate a API devolver lista vazia."""
    coletados = []
    pagina = 1
    while True:
        lote = buscar_pagina(caminho, {**params, "pagina": pagina, "itens": 100})
        if not lote:
            break
        coletados.extend(lote)
        pagina += 1
    return coletados

def coletar_deputados() -> list[dict]:
    """Os deputados da legislatura atual, com partido e UF."""
    deputados = buscar_tudo("/deputados", {})
    logger.info("%d deputados coletados", len(deputados))
    return deputados


def coletar_proposicoes(deputados: list[dict]) -> list[dict]:
    """Para cada deputado, os PLs que ele apresentou no ano."""
    todas = []
    for i, dep in enumerate(deputados, start=1):
        pls = buscar_tudo("/proposicoes", {
            "siglaTipo": TIPO,
            "ano": ANO,
            "idDeputadoAutor": dep["id"],
        })
        for pl in pls:
            pl["autor_id"] = dep["id"]
            pl["autor_nome"] = dep["nome"]
            pl["autor_partido"] = dep["siglaPartido"]
            pl["autor_uf"] = dep["siglaUf"]
        todas.extend(pls)

        if i % 50 == 0:
            logger.info("%d/%d deputados — %d PLs ate agora",
                        i, len(deputados), len(todas))
    return todas


def salvar_raw(deputados: list[dict], proposicoes: list[dict]) -> Path:
    """Salva a coleta bruta com timestamp UTC no nome."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    caminho = RAW_DIR / f"proposicoes_{carimbo}.json"

    conteudo = {
        "coletado_em": carimbo,
        "ano": ANO,
        "tipo": TIPO,
        "total_deputados": len(deputados),
        "proposicoes": proposicoes,
    }
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
    return caminho


if __name__ == "__main__":
    deputados = coletar_deputados()
    proposicoes = coletar_proposicoes(deputados)
    caminho = salvar_raw(deputados, proposicoes)
    logger.info("raw salvo em %s — %d proposicoes", caminho, len(proposicoes))