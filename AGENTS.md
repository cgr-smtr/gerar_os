# AGENTS.md — Memória de sessão (Gerar OS)

Arquivo auto-carregado em toda sessão. Mantenha atualizado e conciso.
Para histórico detalhado, ver `.opencode/memory.md`.

## Projeto
Geração, auditoria e comparação de dados operacionais da rede de ônibus do RJ:
programação de Ordens de Serviço (OS) e análise geoespacial de traçados GTFS.
Python + Streamlit (pandas, pyarrow, geopandas, shapely, pyproj, pydeck).

## Estrutura
- `src/generate_os.py`: gera as tabelas de programação OS e Planos Gerais (CSV)
  a partir de `partidas.parquet` (filtra `route_type == "700"`, exclui MOBI-Rio).
- `src/auditoria_app.py`: Streamlit — compara duas versões de tabelas OS
  (CSV/Parquet) e reporta linhas novas/adicionadas/alteradas.
- `src/auditoria_gtfs_app.py`: Streamlit — compara dois feeds GTFS (.zip),
  mede extensão geodésica (pyproj/Haversine) e desvio Hausdorff, mapa pydeck.
- `legacy/`: scripts R originais (referência histórica).

## Convenções
- Código/docs em português; CSV BR (`;` e vírgula decimal, encoding utf-8-sig).
- Entradas padrão em `C:\R_SMTR\resultados\partidas\partidas.parquet`; saídas em
  `C:\R_SMTR\resultados\arquivos_os\` (ajustáveis no topo dos scripts).
- Executar OS: `python src/generate_os.py`. Auditorias: `streamlit run src/<app>.py`.

## Memória: como usar
- Sessão começa: ler `AGENTS.md` (já carregado) e, se pedido, `.opencode/memory.md`.
- Ao terminar tarefa relevante: atualizar `AGENTS.md` (estado atual) e
  `.opencode/memory.md` (histórico) antes de encerrar.
- NUNCA registrar segredos/credenciais nestes arquivos.