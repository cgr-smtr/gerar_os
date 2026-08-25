# Gerador de OS (Python version)

Este repositório contém ferramentas em Python para geração, auditoria e comparação de dados operacionais da rede de ônibus, incluindo programação de Ordens de Serviço (OS) e análise geoespacial de traçados GTFS.

---

## Estrutura do Repositório

```
gerar_os/
├── src/
│   ├── generate_os.py        # Geração de tabelas de programação OS
│   ├── auditoria_app.py      # Auditoria de programação OS (tabelas CSV/Parquet)
│   └── auditoria_gtfs_app.py # Auditoria geoespacial de traçados GTFS
├── legacy/                   # Scripts originais em R (referência histórica)
├── requirements.txt          # Dependências do projeto
└── .gitignore
```

---

## Instalação

Recomenda-se o uso de um ambiente virtual:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Ou com `uv`:

```bash
uv venv
uv pip install -r requirements.txt
```

### Dependências

| Pacote       | Uso                                             |
|--------------|-------------------------------------------------|
| `pandas`     | Manipulação de dados tabulares                  |
| `pyarrow`    | Leitura de arquivos Parquet                     |
| `streamlit`  | Interface web interativa                        |
| `openpyxl`   | Exportação para Excel                           |
| `numpy`      | Cálculos numéricos e fallbacks geoespaciais     |
| `geopandas`  | Operações geoespaciais                          |
| `shapely`    | Geometrias vetoriais (LineString, distâncias)   |
| `pyproj`     | Cálculo geodésico preciso de extensões (WGS84)  |
| `pydeck`     | Visualização de mapas interativos               |

---

## Scripts

### 1. `generate_os.py` — Geração de Tabelas de Programação

Processa os dados de partidas (`partidas.parquet`) e gera as tabelas de programação OS e os Planos Gerais em CSV.

**Executar:**
```bash
python src/generate_os.py
# ou
uv run python src/generate_os.py
```

**Entradas e saídas:**

| Item            | Caminho padrão                                          |
|-----------------|---------------------------------------------------------|
| Entrada         | `C:\R_SMTR\resultados\partidas\partidas.parquet`        |
| Saída (OS)      | `C:\R_SMTR\resultados\arquivos_os\`                     |

**Filtros aplicados automaticamente:**
- `route_type == "700"` (ônibus urbanos)
- Exclusão do consórcio `MOBI-Rio`

> Os caminhos podem ser ajustados no topo do arquivo `src/generate_os.py`.

---

### 2. `auditoria_app.py` — Auditoria de Programação OS

Interface Streamlit para comparar duas versões de tabelas de programação OS (CSV ou Parquet) e identificar mudanças entre quinzenas.

**Executar:**
```bash
streamlit run src/auditoria_app.py
# ou
uv run streamlit run src/auditoria_app.py
```

**Funcionalidades:**
- Upload de duas tabelas (quinzena anterior × atual)
- Detecção automática de separador CSV (`,` ou `;`)
- Exibição de linhas novas, removidas e alteradas
- Exportação do relatório de auditoria

---

### 3. `auditoria_gtfs_app.py` — Auditoria Geoespacial de Traçados GTFS

Interface Streamlit para comparar dois feeds GTFS (`.zip`) e identificar diferenças de traçado por trip/linha, com visualização em mapa interativo.

**Executar:**
```bash
streamlit run src/auditoria_gtfs_app.py
# ou
uv run streamlit run src/auditoria_gtfs_app.py
```

**Funcionalidades:**

| Funcionalidade                        | Descrição                                                                 |
|---------------------------------------|---------------------------------------------------------------------------|
| Upload dual de GTFS                   | Carrega os feeds "Anterior" e "Atual" via sidebar                         |
| Comparação por linha e direção        | Identifica rotas novas, removidas e modificadas                           |
| Cálculo de extensão                   | Comprimento geodésico (WGS84) em metros via `pyproj` (fallback: Haversine)|
| Desvio espacial (Hausdorff)           | Distância máxima entre traçados para classificar grau de mudança          |
| Visualização em mapa                  | Mapa escuro (`pydeck`) com traçado anterior (vermelho) e atual (azul)     |
| Relatório tabular                     | Tabela com extensão anterior, atual e diferença, com formatação BR        |
| Leitura de `agency.txt`               | Exibe nome da agência para contextualização do feed                       |

**Classificação de mudanças:**

| Status            | Critério                                                        |
|-------------------|-----------------------------------------------------------------|
| 🟢 Sem mudança    | Desvio espacial < 50 m                                          |
| 🟡 Mudança leve   | Desvio entre 50 m e 200 m                                       |
| 🔴 Mudança severa | Desvio > 200 m                                                  |
| ➕ Rota nova      | Presente apenas no feed atual                                   |
| ➖ Rota removida  | Presente apenas no feed anterior                                |

**Formatação numérica:** padrão brasileiro (milhar: `.` | decimal: `,`), extensões em metros (`m`).

---

## Licença

Este projeto está licenciado sob a Licença MIT — consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
