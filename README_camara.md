# Pipeline de Proposições Legislativas — Câmara dos Deputados (2025)

Pipeline de dados que coleta Projetos de Lei apresentados na Câmara dos Deputados em 2025, transforma e valida os dados com Pandas, carrega o histórico no PostgreSQL e grava uma visão derivada (ranking de produtividade legislativa por partido) no MongoDB Atlas.

**Autor:** Cauê Lima


---

## A pergunta que este pipeline responde

> **Qual partido mais apresentou Projetos de Lei na Câmara dos Deputados em 2025 — e qual é o mais produtivo por deputado?**

A distinção importa: partidos com bancadas maiores naturalmente apresentam mais proposições em números absolutos. A média por deputado normaliza esse efeito e revela produtividade real, não apenas tamanho de bancada. As duas métricas convivem no mesmo documento da coleção derivada.

---

## Arquitetura

```
API Dados Abertos          coleta.py            data/raw/
   da Câmara        →      (requests)      →    (JSON + timestamp UTC)
                                                        ↓
                                                  transforma.py
                                                  (Pandas + validação)
                                                        ↓
                                    ┌───────────────────┴──────────────┐
                                    ↓                                  ↓
                          PostgreSQL                          MongoDB Atlas
                     tabela `proposicoes`                 coleção `resumo_partidos`
                    (histórico linha a linha)              (visão derivada/ranking)
```

O diagrama completo em PNG está em `docs/arquitetura.png`.

**Mapeamento nos cinco blocos de uma arquitetura de dados:**

| Bloco | Componente neste projeto |
|---|---|
| Fontes | API de Dados Abertos da Câmara dos Deputados |
| Ingestão | `src/coleta.py` (requests, timeout, retry com backoff, paginação) |
| Armazenamento | `data/raw/` (bruto) · PostgreSQL (tratado) · MongoDB Atlas (derivado) |
| Processamento | `src/transforma.py` (Pandas: normalização, tipagem, validação) |
| Consumo | DBeaver, Atlas Browse Collections |

Este é um pipeline **batch**: roda sob demanda, processa o lote inteiro e encerra. Dados legislativos não exigem latência de segundos — a periodicidade natural é diária ou semanal, o que dispensa a complexidade de streaming.

---

## Estrutura do projeto

```
pipeline-proposicoes-camara-2025/
├── config.py               # credenciais (NÃO versionado — ver .gitignore)
├── .gitignore
├── requirements.txt
├── README.md
├── docs/
│   └── arquitetura.png     # diagrama draw.io
├── src/
│   ├── coleta.py           # E: consulta a API e grava a camada raw
│   ├── transforma.py       # T: achata, tipa e valida com Pandas
│   ├── pipeline.py         # orquestra E + T + L (PostgreSQL)
│   └── carga_mongo.py      # visão derivada: PostgreSQL → Atlas
└── data/
    ├── raw/                # JSON bruto, um arquivo por coleta
    └── tratada/            # CSV processado
```

---

## Fonte de dados

**API de Dados Abertos da Câmara dos Deputados** — `https://dadosabertos.camara.leg.br/api/v2`

Escolhida por três razões: é pública e sem autenticação, devolve JSON bem estruturado com paginação padronizada, e trata de dados legislativos — domínio próximo à minha formação jurídica.

Endpoints utilizados:

| Endpoint | Uso |
|---|---|
| `/deputados` | Lista os 513 deputados da legislatura atual, com partido e UF |
| `/proposicoes?siglaTipo=PL&ano=2025&idDeputadoAutor={id}` | PLs apresentados por um deputado específico |

---

## Decisões de escopo 

Estas decisões delimitam o que o pipeline mede. Sem elas, os números seriam facilmente mal interpretados.

### 1. Somente Projetos de Lei (PL), somente 2025

O filtro é `siglaTipo=PL` e `ano=2025`. Ficam de fora PECs, PLPs, requerimentos, indicações e demais tipos de proposição. O recorte anual fechado garante que uma reexecução futura produza o mesmo universo de dados.

### 2. Somente proposições de autoria de deputados federais

O laço de coleta percorre os **513 deputados** e pergunta, para cada um, quais PLs ele apresentou. A consequência é que proposições de autoria do **Poder Executivo, do Senado Federal, de comissões ou de órgãos** ficam fora do conjunto — corretamente, já que essas autorias não possuem partido e não caberiam no ranking.

**Por que o laço foi invertido:** o endpoint `/proposicoes` não devolve o autor na listagem. Coletar as proposições e depois descobrir o autor de cada uma exigiria uma requisição adicional por proposição — milhares de chamadas. Consultando por deputado, o partido vem por construção: já se sabe de quem se está perguntando. A troca reduz o volume de requisições de milhares para aproximadamente 513.

### 3. Granularidade: proposição × autor

Um PL com coautoria é devolvido pela API uma vez para **cada** coautor. A tabela `proposicoes` preserva essa granularidade — a mesma proposição pode aparecer em mais de uma linha, com autores e partidos diferentes.

Isso não é duplicação de dados: é a representação correta da coautoria. O tratamento acontece na agregação, que distingue duas métricas:

- `total_proposicoes` — usa `nunique()` sobre o id da proposição (conta proposições distintas)
- `total_autorias` — conta as linhas (conta participações em autoria)

### 4. Enriquecimento na coleta

Cada proposição é gravada no raw já acrescida de `autor_id`, `autor_nome`, `autor_partido` e `autor_uf`. Esses campos não são uma transformação do dado devolvido pela API: são **metadados da própria consulta** — o registro de qual pergunta gerou aquele resultado. Sem eles, o raw perderia a informação de autoria, que não é recuperável a partir da resposta isolada.

### 5. A camada tratada é uma foto da última coleta

Diferente de um pipeline de séries temporais (onde cada coleta traz observações novas), aqui uma reexecução devolve **as mesmas proposições**. Por isso, `transform()` processa apenas o **raw mais recente**, e não a soma de todos.

A camada raw continua acumulando o histórico completo de coletas — o que preserva auditoria e permite reprocessamento —, mas a tabela final representa o estado da última execução.

---

## Como rodar do zero

### Pré-requisitos

- Python 3.12+
- PostgreSQL instalado e rodando localmente, com um banco criado
- Conta gratuita no MongoDB Atlas com um cluster M0

### 1. Clonar e preparar o ambiente

```bash
git clone https://github.com/SEU-USUARIO/pipeline-proposicoes-camara-2025.git
cd pipeline-proposicoes-camara-2025

python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
```

### 2. Criar o banco no PostgreSQL

```sql
CREATE DATABASE pipeline_proposicoes_camara;
```

A tabela `proposicoes` é criada automaticamente pelo pipeline — não é necessário rodar DDL.

### 3. Criar o `config.py` na raiz do projeto

Este arquivo **não** está versionado. Crie-o manualmente com o seguinte conteúdo, substituindo pelos seus dados:

```python
POSTGRES_URL = "postgresql+psycopg2://USUARIO:SENHA@localhost:5432/pipeline_proposicoes_camara"
MONGO_URL = "mongodb+srv://USUARIO:SENHA@SEU-CLUSTER.mongodb.net/"
```

### 4. Liberar o IP no MongoDB Atlas

No painel do Atlas: **Network Access → Add IP Address**. Para estudo, `0.0.0.0/0` é aceitável; em produção, jamais.

> **Atenção:** em clusters M0 (gratuitos), um IP não liberado faz a conexão falhar **durante o handshake TLS**, com a mensagem `TLSV1_ALERT_INTERNAL_ERROR`. O erro parece um problema de certificado ou de biblioteca SSL, mas é bloqueio de rede. Esta foi a causa raiz de horas de depuração neste projeto.

### 5. Executar o pipeline

```bash
python src/pipeline.py       # E + T + L → PostgreSQL (~12 minutos)
python src/carga_mongo.py    # visão derivada → MongoDB Atlas (segundos)
```

A coleta completa leva cerca de 12 minutos: são 513 consultas paginadas, com pausa entre tentativas em caso de falha. É comportamento esperado de um pipeline batch, não travamento.

---

## Detalhamento das etapas

### Extract — `src/coleta.py`

Coleta defensiva sobre três garantias:

- **`timeout=15`** em toda requisição: sem timeout, uma API que não responde trava o pipeline indefinidamente.
- **`raise_for_status()`**: erros HTTP (4xx/5xx) viram exceção em vez de passarem despercebidos como resposta vazia.
- **Retry com backoff exponencial**: até 3 tentativas, com espera de 1s, 2s e 4s. Após a terceira falha, o pipeline aborta com `RuntimeError` — falhar em silêncio seria pior do que falhar.

A paginação percorre as páginas sequencialmente e para quando a API devolve uma lista vazia (`if not lote: break`).

O resultado é gravado em `data/raw/proposicoes_<timestamp>.json`, com carimbo UTC no formato `%Y%m%dT%H%M%SZ` — ordenável alfabeticamente e sem ambiguidade de fuso horário.

**A camada raw nunca é editada.** Só se cria e se lê.

### Transform — `src/transforma.py`

1. Achata a lista de proposições em DataFrame
2. Seleciona apenas as colunas de interesse
3. Renomeia para **snake_case** (`dataApresentacao` → `data_apresentacao`), porque esses nomes virarão colunas no PostgreSQL e SQL com camelCase é fonte de atrito
4. Converte tipos: identificadores para `int`, data para `datetime` (como string, datas não ordenam nem filtram corretamente)
5. Registra `arquivo_origem` em cada linha — rastreabilidade até o raw que a originou

### Validação — `validar()`

O pipeline **para** com erro explícito quando o dado não é confiável:

| Checagem | Motivo |
|---|---|
| Colunas obrigatórias presentes | Estrutura da API pode mudar sem aviso |
| Sem nulos em `id_proposicao`, `autor_partido`, `data_apresentacao` | São as chaves da análise; nulo aqui invalida a agregação |
| Toda proposição com `ano == 2025` | Regra de negócio: se o filtro da coleta falhar, os dados não representam o que este README promete |

Carregar dado ruim silenciosamente produz um relatório errado que só se descobre meses depois. Erro barulhento se conserta.

### Load — `src/pipeline.py`

```python
df.to_sql("proposicoes", engine, if_exists="replace", index=False)
```

**Justificativa do `if_exists="replace"`:** cada execução reconstrói a tabela inteira a partir do raw mais recente. Como o universo de dados é fechado (PLs de 2025), reprocessar produz exatamente o mesmo conjunto — a substituição total garante idempotência sem necessidade de chave primária ou lógica de *upsert*.

`append` foi descartado justamente por violar essa propriedade: duplicaria todas as linhas a cada execução. `fail` (o padrão) impediria qualquer reexecução.

### Visão derivada — `src/carga_mongo.py`

O PostgreSQL, que era o destino do pipeline anterior, torna-se aqui a **fonte**. É assim que camadas se encadeiam.

A coleção `resumo_partidos` guarda um documento por partido:

```json
{
  "partido": "NOVO",
  "ano": 2025,
  "total_proposicoes": 53,
  "total_autorias": 118,
  "deputados_autores": 5,
  "media_por_deputado": 10.6
}
```

Este documento real ilustra bem por que as duas métricas precisam existir: o NOVO participou de **118 autorias**, mas isso corresponde a apenas **53 proposições distintas** — os deputados do partido coassinam intensamente os projetos uns dos outros. Um ranking construído sobre `total_autorias` colocaria o partido numa posição bem diferente da real.

**Por que é uma visão derivada e não uma cópia:** nenhum desses campos existe na tabela. São agregações calculadas — em especial `media_por_deputado`, que responde uma pergunta que a tabela não responde de bate-pronto: *qual partido é mais produtivo, descontando o tamanho da bancada?*

O `delete_many({})` antes do `insert_many` é o equivalente ao `if_exists="replace"` no mundo MongoDB. Sem ele, cada execução duplicaria os documentos — `insert_many` puro é o `append` do Mongo.

Os `int()` e `float()` explícitos são necessários porque o pymongo não serializa tipos NumPy nativamente.

---

## Segurança de credenciais

Nenhuma senha, chave ou string de conexão real está neste repositório.

- `config.py` está listado no `.gitignore` e nunca foi commitado
- O README documenta o formato esperado do arquivo, com placeholders
- A API da Câmara é pública e não exige chave

Três credenciais passaram por este módulo (OpenWeather, PostgreSQL e MongoDB Atlas) e nenhuma foi versionada.

---

## Evidências de execução

### Coleta completa

```
2026-08-16 14:19:54 [INFO] 200/513 deputados — 3580 PLs ate agora
2026-08-16 14:22:51 [INFO] 350/513 deputados — 5493 PLs ate agora
2026-08-16 14:25:41 [INFO] 500/513 deputados — 7079 PLs ate agora
2026-08-16 14:25:59 [INFO] raw salvo em data\raw\proposicoes_20260816T172559Z.json — 7225 proposicoes
```

### Transformação e validação

```
2026-08-16 14:29:24 [INFO] processando proposicoes_20260816T172559Z.json
2026-08-16 14:29:24 [INFO] validacao ok: 7225 linhas integras
2026-08-16 14:29:24 [INFO] tratada gravada (7225 linhas)
```

### Teste de idempotência — duas execuções seguidas

**Execução 1:**

```
2026-08-16 16:15:52 [INFO] pipeline iniciado
2026-08-16 16:15:58 [INFO] 513 deputados coletados
2026-08-16 16:20:17 [INFO] 200/513 deputados — 3580 PLs ate agora
2026-08-16 16:26:26 [INFO] 500/513 deputados — 7079 PLs ate agora
2026-08-16 16:26:43 [INFO] raw salvo em data\raw\proposicoes_20260816T192643Z.json — 7225 proposicoes
2026-08-16 16:26:43 [INFO] processando proposicoes_20260816T192643Z.json
2026-08-16 16:26:43 [INFO] validacao ok: 7225 linhas integras
2026-08-16 16:26:43 [INFO] carga concluida: 7225 linhas
2026-08-16 16:26:43 [INFO] pipeline concluido com sucesso
```

**Execução 2, imediatamente em seguida:**

```
2026-08-16 16:27:08 [INFO] pipeline iniciado
2026-08-16 16:27:17 [INFO] 513 deputados coletados
2026-08-16 16:31:23 [INFO] 200/513 deputados — 3580 PLs ate agora
2026-08-16 16:37:39 [INFO] 500/513 deputados — 7079 PLs ate agora
2026-08-16 16:37:55 [INFO] raw salvo em data\raw\proposicoes_20260816T193755Z.json — 7225 proposicoes
2026-08-16 16:37:55 [INFO] processando proposicoes_20260816T193755Z.json
2026-08-16 16:37:55 [INFO] validacao ok: 7225 linhas integras
2026-08-16 16:37:55 [INFO] carga concluida: 7225 linhas
2026-08-16 16:37:55 [INFO] pipeline concluido com sucesso
```

**Resultado:** 7.225 linhas em ambas as execuções. Dois arquivos raw distintos foram gravados — o histórico de coletas é preservado —, mas a tabela final não duplicou um único registro. É a idempotência que o `if_exists="replace"` garante.

### Consulta de verificação

```sql
SELECT autor_partido,
       COUNT(DISTINCT id_proposicao) AS total_proposicoes
FROM proposicoes
GROUP BY autor_partido
ORDER BY total_proposicoes DESC;
```

---

## Resultado

Ranking parcial gerado pela coleção `resumo_partidos` (21 partidos no total):

| Partido | Proposições | Autorias | Deputados autores | Média por deputado |
|---|---|---|---|---|
| PL | 1.213 | 1.583 | 91 | 13,33 |
| REPUBLICANOS | 887 | 903 | 33 | 26,88 |
| PODE | 852 | 860 | 24 | 35,50 |
| PT | 437 | 746 | 60 | 7,28 |
| UNIÃO | 431 | 450 | 42 | 10,26 |

**A leitura que só a visão derivada permite:** o PL lidera em volume absoluto, o que era esperado — é a maior bancada. Mas o PODE, com pouco mais de um quarto dos deputados do PL, apresenta uma média de 35,5 proposições por deputado contra 13,3 do PL. Em produtividade individual, a ordem do ranking se inverte.

Essa é precisamente a pergunta que a tabela do PostgreSQL não responde de bate-pronto e que a agregação no Atlas responde em um documento.

---

## Limitações conhecidas

- **Não mede aprovação.** O endpoint de listagem não devolve a situação da proposição; obtê-la exigiria uma rodada adicional de coleta. Além disso, PLs de 2025 raramente concluíram tramitação — a métrica seria próxima de zero e pouco informativa. Fica como evolução natural do projeto.
- **Partido no momento da coleta.** A filiação partidária vem do endpoint `/deputados`, que reflete a situação atual. Trocas de partido ocorridas após a apresentação do PL não são retroagidas.
- **Coautoria conta para todos os autores.** Em `total_autorias`, um PL com cinco coautores gera cinco registros. `total_proposicoes` corrige isso via `nunique()`, mas a distinção precisa estar clara na leitura do ranking.
- **A média por deputado favorece bancadas muito pequenas.** O partido MISSÃO, com um único deputado autor e 73 proposições, aparece com média 73 — muito acima de qualquer partido grande. A métrica é útil para comparar bancadas de porte semelhante, mas perde sentido nos extremos. Um filtro por número mínimo de deputados, ou o uso da mediana, corrigiria a distorção.
- **Tempo de coleta.** Cerca de 12 minutos por execução completa. Um cache de deputados evitaria recoletá-los a cada rodada.

---

## Tecnologias

| Ferramenta | Papel |
|---|---|
| `requests` | Consumo da API com coleta defensiva |
| `pandas` | Normalização, tipagem e agregação |
| `SQLAlchemy` + `psycopg2` | Conexão e carga no PostgreSQL |
| `pymongo` | Gravação da visão derivada no MongoDB Atlas |
| `logging` | Observabilidade das execuções |
| draw.io | Diagrama de arquitetura |
