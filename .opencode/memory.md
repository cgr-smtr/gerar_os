# Memória de longo prazo — Gerar OS

Registro de decisões, histórico e contexto detalhado. Complementa o `AGENTS.md`.
Preferência: adicionar entradas no topo, datadas.

---

## 2026-08-27 — Criação do banco de memória

- Criados `AGENTS.md` e `.opencode/memory.md`.
- Porta em Python (Streamlit) dos fluxos legados em R de geração de Ordens de
  Serviço e auditoria de programação da rede de ônibus do RJ (SPPO).
- `generate_os.py`: lê partidas do GTFS consolidadas em `partidas.parquet`,
  mapeia tipo de dia (du/sab/dom/pf) e faixas horárias (14 faixas, ex. 06:00-09:00),
  e exporta CSV/Parquet com separador `;`.
- Auditorias são apps Streamlit: comparam quinzenas de OS e feeds GTFS
  (traçado por trip/linha, extensão WGS84 e desvio Hausdorff; classificação
  sem-mudança < 50 m, leve 50-200 m, severa > 200 m).
- Depende de estrutura `C:\R_SMTR\resultados\` para entradas e saídas.
- Existem versões/cópias relacionadas: `gerar_os - Copia` (cópia mais antiga sem
  `auditoria_gtfs_app.py`) e `Gerar_OS_RedeOnibus` (origem em R).
- Sem credenciais registradas aqui.