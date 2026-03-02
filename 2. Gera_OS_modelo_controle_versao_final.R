library(tidyverse)

# ============================================================================
# BLOCO 2: TABELA PIVOTADA POR SENTIDO E FAIXA HORÁRIA - Modelo OS
# ============================================================================

# Ler o arquivo RDS
viagens <- readRDS("C:/R_SMTR/resultados/partidas.rds")

# Filtrar apenas route_type = 700 (linhas regulares)
viagens <- viagens %>%
  filter(route_type == 700)

# Converter tipo_dia para nomes completos
viagens <- viagens %>%
  mutate(
    tipo_dia_completo = case_when(
      tipo_dia == "du" ~ "Dia Útil",
      tipo_dia == "sab" ~ "Sábado",
      tipo_dia == "dom" ~ "Domingo",
      tipo_dia == "pf" ~ "Ponto Facultativo",
      TRUE ~ tipo_dia
    )
  )

# Definir todas as combinações possíveis de faixas e tipos de dia
faixas <- c(
  "00:00-01:00", "01:00-02:00", "02:00-03:00", "03:00-04:00",
  "04:00-05:00", "05:00-06:00", "06:00-09:00", "09:00-12:00",
  "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-22:00",
  "22:00-23:00", "23:00-24:00"
)

tipos_dia <- c("Dia Útil", "Sábado", "Domingo", "Ponto Facultativo")

# Contar partidas e calcular quilometragem por combinação
resumo <- viagens %>%
  group_by(trip_short_name, trip_headsign, route_long_name, agency_name, direction_id, tipo_dia_completo, faixa, extensao) %>%
  summarise(partidas = n(), .groups = "drop") %>%
  mutate(
    quilometragem = partidas * (extensao/1000),
    col_partidas = paste0("partidas ", faixa, " - ", tipo_dia_completo),
    col_km = paste0("quilometragem ", faixa, " - ", tipo_dia_completo)
  )

# Criar dados de Ponto Facultativo baseado em Dia Útil
ponto_facultativo <- resumo %>%
  filter(tipo_dia_completo == "Dia Útil") %>%
  mutate(
    # Identificar se é serviço noturno (começa com SN)
    eh_noturno = str_starts(trip_short_name, "SN"),
    # Aplicar regra: SN mantém 100%, outros 62%
    partidas = if_else(eh_noturno, partidas, round(partidas * 0.62)),
    # AJUSTE: Dividindo por 1000 para converter metros em quilômetros
    quilometragem = partidas * (extensao / 1000), 
    tipo_dia_completo = "Ponto Facultativo",
    col_partidas = paste0("partidas ", faixa, " - Ponto Facultativo"),
    col_km = paste0("quilometragem ", faixa, " - Ponto Facultativo")
  ) %>%
  select(-eh_noturno)

# Combinar resumo original com ponto facultativo
resumo_completo <- bind_rows(resumo, ponto_facultativo)

# Pivotar partidas
partidas_pivot <- resumo_completo %>%
  select(trip_short_name, trip_headsign, route_long_name, agency_name, direction_id, extensao, col_partidas, partidas) %>%
  pivot_wider(
    id_cols = c(trip_short_name, trip_headsign, route_long_name, agency_name, direction_id, extensao),
    names_from = col_partidas,
    values_from = partidas,
    values_fill = 0
  )

# Pivotar quilometragem
km_pivot <- resumo_completo %>%
  select(trip_short_name, trip_headsign, route_long_name, agency_name, direction_id, extensao, col_km, quilometragem) %>%
  pivot_wider(
    id_cols = c(trip_short_name, trip_headsign, route_long_name, agency_name, direction_id, extensao),
    names_from = col_km,
    values_from = quilometragem,
    values_fill = 0
  )

# Juntar as duas tabelas
tabela_final <- partidas_pivot %>%
  left_join(km_pivot, by = c("trip_short_name", "trip_headsign", "route_long_name", "agency_name", "direction_id", "extensao"))

# Criar Sentido
tabela_final <- tabela_final %>%
  mutate(
    Sentido = case_when(
      str_detect(tolower(trip_headsign), "circular") ~ "Circular",
      direction_id == 0 ~ "Ida",
      direction_id == 1 ~ "Volta",
      TRUE ~ as.character(direction_id)
    )
  )

# Criar lista ordenada de colunas
colunas_ordenadas <- c("trip_short_name", "route_long_name", "agency_name", "Sentido", "extensao")

for (tipo in tipos_dia) {
  for (faixa in faixas) {
    col_part <- paste0("partidas ", faixa, " - ", tipo)
    col_km <- paste0("quilometragem ", faixa, " - ", tipo)
    
    if (col_part %in% names(tabela_final)) {
      colunas_ordenadas <- c(colunas_ordenadas, col_part, col_km)
    }
  }
}

# Selecionar e renomear
tabela_pivotada <- tabela_final %>%
  select(all_of(colunas_ordenadas)) %>%
  rename(
    Serviço = trip_short_name,
    Vista = route_long_name,
    Consórcio = agency_name,
    Extensão = extensao
  ) %>%
  arrange(Serviço, Sentido)

# Exportar (write_csv2 usa ; como separador e , como decimal)
write_csv2(tabela_pivotada, "C:/R_SMTR/resultados/tabela_programacao_OS.csv")
saveRDS(tabela_pivotada, "C:/R_SMTR/resultados/tabela_programacao_OS.rds")

cat("Processamento concluído.")
