# Memória de longo prazo — Gerar OS

Registro de decisões, histórico e contexto detalhado. Complementa o `AGENTS.md`.
Preferência: adicionar entradas no topo, datadas.

---

## 2026-10-20 — PF sintético: ignorar `tipo_dia == "pf"` do input e garantir inteiros

- Problema: `tabela_ponto_facultativo.csv` saiu com 3.006 valores x,5 nas
  colunas de partidas (e `Viagens` fracionado).
- Causa: o input novo `partidas_2026-10-02Q.parquet` já traz 40.528 partidas
  reais com `tipo_dia == "pf"`. O `generate_os.py` concatenava esse PF real com
  o sintético (62% do DU) e o `pivot_table` (aggfunc padrão `'mean'`) fazia a
  média das duas fontes na mesma chave (ex.: DU=6 → sintético 4 e real 6 → média 5).
- Correção em `src/generate_os.py` (lógica de cálculo sintético mantida):
  1. logo após o `groupby`, filtra `tipo_dia_completo != "Ponto Facultativo"`
     (descarta o PF real; só o sintético é fonte de PF);
  2. `aggfunc='sum'` nos dois `pivot_table` (defesa contra médias);
  3. cast `.round().astype(int)` nas colunas de partidas de `tabela_os` e de
     cada Plano Geral (o `np.where` deixava a coluna em float).
- Verificado após rodar `python src/generate_os.py`: 0 valores não inteiros nas
  5 saídas; razão PF/DU ≈ 0,62 arredondada; noturnos SN permanecem iguais ao DU.
- Decisão do usuário: `generate_os.py` = sempre PF sintético (ignora pf real);
  `generate_os_pf_input.py` = sempre PF real do input (inalterado).

## 2026-10-16 — Clone sem cálculo de Ponto Facultativo

- Motivo: o upstream passará a entregar as partidas de PF no próprio
  `partidas` (`tipo_dia == "pf"`), dispensando a estimativa de 62%.
- Criado `src/generate_os_pf_input.py` (cópia de `generate_os.py`, original
  intacto) com duas diferenças: removido o bloco de geração de PF
  (`resumo_completo = resumo`) e `OUTPUT_DIR` = `C:\R_SMTR\resultados\arquivos_os_pf\`
  para não sobrescrever saídas do original.
- Verificado com parquet temporário contendo `pf`: 863 linhas de PF no input →
  863 partidas PF na tabela OS e no Plano Geral (sem fator 0.62, sem duplicação);
  tabela de Dia Útil sem colunas PF. Se o input não tiver `pf`, o Plano Geral
  de PF é pulado com `AVISO` (comportamento já existente).
- Obs.: o input atual (`partidas_2026-10-01Q.parquet`) ainda não contém `pf`
  (apenas du/sab/dom).

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