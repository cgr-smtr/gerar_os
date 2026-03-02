pacman::p_load(gtfstools, dplyr, data.table, sf, lubridate, gt, stringr, webshot2, purrr, tidyr)

# ============================================================================
# BLOCO 1: LISTA DE PARTIDAS VIA ARQUIVO GTFS
# ============================================================================

# ============================================================================
# CONFIGURAÇÕES INICIAIS
# ============================================================================

# Certifique-se de que o caminho abaixo aponta para o arquivo .zip ou para a pasta descompactada
endereco_gtfs <- "C:/Users/02626810/Downloads/gtfs_rio-de-janeiro_pub.zip"
caminho_fantasmas <- "../../dados/insumos/trip_id_fantasma.txt"
pasta_resultados <- "C:/R_SMTR/projetos/Gerar_OS/Resultados/"

tipo_dia <- c('du', 'dom', 'sab')
`%nin%` <- function(x, table) !(x %in% table)

# Criar pasta de resultados se não existir
if (!dir.exists(pasta_resultados)) dir.create(pasta_resultados, recursive = TRUE)

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

get_pattern <- function(tipo_dia) {
  case_when(
    tipo_dia == "du"  ~ "U",
    tipo_dia == "sab" ~ "S",
    tipo_dia == "dom" ~ "D"
  )
}

filter_gtfs_base <- function(gtfs_path) {
  gtfs <- read_gtfs(gtfs_path)
  
  # Filtrar frescões
  frescoes <- gtfs$routes %>% 
    filter(route_type == '200') %>% 
    pull(route_id)
  
  gtfs <- filter_by_route_id(gtfs, frescoes, keep = FALSE)
  
  return(gtfs)
}

filter_trips_by_day <- function(gtfs, pattern) {
  trips_service_id <- gtfs$trips %>%
    filter(grepl(pattern, service_id)) %>%
    pull(trip_id)
  
  # CORREÇÃO: Pular arquivo de trips fantasmas caso não exista
  if (file.exists(caminho_fantasmas)) {
    trips_fantasma <- fread(caminho_fantasmas) %>% unlist()
    cat("  ✓ Arquivo de trips fantasmas aplicado.\n")
  } else {
    warning(paste("Arquivo não encontrado em:", caminho_fantasmas, "- Pulando filtro de fantasmas."))
    trips_fantasma <- character(0)
  }
  
  trips_desat <- gtfs$trips %>% 
    filter(service_id %like% 'DESAT') %>% 
    pull(trip_id)
  
  gtfs <- gtfs %>% 
    filter_by_trip_id(trips_service_id, keep = TRUE) %>% 
    filter_by_trip_id(trips_desat, keep = FALSE) %>% 
    filter_by_trip_id(trips_fantasma, keep = FALSE)
  
  return(gtfs)
}

process_shapes <- function(gtfs) {
  gtfs$shapes <- as.data.table(gtfs$shapes) %>% 
    group_by(shape_id) %>% 
    arrange(shape_id, shape_pt_sequence)
  
  shapes_sf <- convert_shapes_to_sf(gtfs) %>% 
    st_transform(31983) %>% 
    mutate(extensao = as.integer(st_length(.))) %>% 
    st_drop_geometry()
  
  return(list(gtfs = gtfs, shapes_sf = shapes_sf))
}

calculate_extensions <- function(gtfs, shapes_sf, viagens_freq) {
  trips_manter <- gtfs$trips %>%
    mutate(
      letras = stringr::str_extract(trip_short_name, "[A-Z]+"),
      numero = stringr::str_extract(trip_short_name, "[0-9]+")
    ) %>%
    tidyr::unite(., trip_short_name, letras, numero, na.rm = TRUE, sep = "") %>%
    left_join(select(viagens_freq, trip_id, partidas), by = "trip_id") %>%
    mutate(partidas = if_else(is.na(partidas), 1, partidas)) %>%
    group_by(shape_id) %>%
    mutate(ocorrencias = sum(partidas)) %>%
    ungroup() %>%
    group_by(route_id, direction_id) %>%
    slice_max(ocorrencias, n = 1) %>%
    ungroup() %>%
    distinct(shape_id, trip_short_name, .keep_all = TRUE) %>%
    select(trip_id, trip_short_name, shape_id, direction_id, route_id) %>% 
    left_join(select(shapes_sf, shape_id, extensao), by = "shape_id") %>% 
    group_by(trip_short_name, direction_id, route_id) %>% 
    slice_min(extensao, n = 1) %>%
    ungroup() %>%
    select(trip_short_name, direction_id, route_id, extensao)
  
  return(trips_manter)
}

process_frequency_trips <- function(gtfs, current_tipo_dia) {
  viagens_freq <- gtfs$frequencies %>%
    mutate(
      start_time = as.character(start_time),
      end_time = as.character(end_time)
    ) %>%
    filter(!is.na(start_time), !is.na(end_time),
           start_time != "", end_time != "",
           start_time != "NA", end_time != "NA") %>%
    mutate(
      start_time_char = start_time,
      end_time_char = end_time
    ) %>%
    mutate(
      hora_inicio = as.numeric(substr(start_time_char, 1, 2)),
      hora_fim = as.numeric(substr(end_time_char, 1, 2))
    ) %>%
    mutate(
      start_time_adj = if_else(
        hora_inicio >= 24,
        paste0(sprintf("%02d", hora_inicio - 24), substr(start_time_char, 3, 8)),
        start_time_char
      ),
      end_time_adj = if_else(
        hora_fim >= 24,
        paste0(sprintf("%02d", hora_fim - 24), substr(end_time_char, 3, 8)),
        end_time_char
      )
    ) %>%
    mutate(
      start_time_posix = as.POSIXct(paste(Sys.Date(), start_time_adj), format = "%Y-%m-%d %H:%M:%S"),
      end_time_posix = as.POSIXct(paste(Sys.Date(), end_time_adj), format = "%Y-%m-%d %H:%M:%S")
    ) %>%
    mutate(
      start_time_final = if_else(hora_inicio >= 24, 
                                 start_time_posix + 86400,
                                 start_time_posix),
      end_time_final = if_else(hora_fim >= 24, 
                               end_time_posix + 86400,
                               end_time_posix)
    ) %>%
    select(-c(start_time, end_time, start_time_char, end_time_char, start_time_adj, end_time_adj, start_time_posix, end_time_posix)) %>%
    rename(
      start_time = start_time_final,
      end_time = end_time_final
    ) %>%
    mutate(
      duracao = as.numeric(difftime(end_time, start_time, units = "secs")),
      partidas = as.numeric(duracao / headway_secs)
    ) %>% 
    left_join(select(gtfs$trips, trip_id, trip_short_name, trip_headsign, direction_id, service_id, route_id), by = "trip_id") %>% 
    filter(!(service_id %like% 'DESAT')) %>% 
    mutate(circular = if_else(nchar(trip_headsign) == 0, TRUE, FALSE)) %>% 
    mutate(tipo_dia = substr(service_id, 1, 1))
  
  return(viagens_freq)
}

expand_frequency_trips <- function(viagens_freq) {
  if(nrow(viagens_freq) == 0) return(data.frame())
  
  viagens_freq_a <- viagens_freq %>%
    mutate(seq_start = mapply(seq, from = start_time,
                              to = end_time,
                              by = headway_secs))
  
  viagens_freq_exp <- viagens_freq_a %>%
    slice(rep(row_number(), lengths(seq_start))) %>%
    arrange(trip_id, start_time) %>%
    group_by(trip_id) %>%
    mutate(
      start_time = start_time + (row_number() * headway_secs) - headway_secs,
      end_time = start_time + headway_secs
    ) %>%
    slice(-n()) %>%
    ungroup()
  
  viagens_freq_exp <- viagens_freq_exp %>%
    dplyr::select(trip_id, trip_short_name, trip_headsign, 
                  start_time, direction_id, route_id)
  
  return(viagens_freq_exp)
}

process_regular_trips <- function(gtfs_proc, linhas_freq) {
  viagens_qh_regular <- gtfs_proc$stop_times %>%
    filter(stop_sequence == '0') %>%
    select(trip_id, departure_time) %>%
    left_join(select(gtfs_proc$trips, trip_id, trip_short_name, trip_headsign, direction_id, service_id, route_id), by = "trip_id") %>% 
    filter(trip_short_name %nin% linhas_freq) %>%
    arrange(direction_id, departure_time) %>%
    mutate(
      departure_time_char = as.character(departure_time),
      hora_partida = as.numeric(substr(departure_time_char, 1, 2)),
      departure_time_adj = if_else(
        hora_partida >= 24,
        paste0(sprintf("%02d", hora_partida - 24), substr(departure_time_char, 3, 8)),
        departure_time_char
      ),
      start_time = as.POSIXct(paste(Sys.Date(), departure_time_adj), format = "%Y-%m-%d %H:%M:%S"),
      start_time = if_else(hora_partida >= 24, 
                           start_time + 86400,
                           start_time)
    ) %>%
    select(trip_id, trip_short_name, trip_headsign, 
           direction_id, start_time, route_id)
  
  return(viagens_qh_regular)
}

consolidate_trips <- function(viagens_freq_exp, viagens_qh_regular, current_tipo_dia, gtfs, extensoes) {
  viagens_completo <- bind_rows(viagens_freq_exp, viagens_qh_regular) %>%
    select(-c(trip_id)) %>%
    mutate(departure_time = paste(sprintf("%02d", if_else(lubridate::day(start_time) != lubridate::day(Sys.Date()),
                                                          as.integer(lubridate::hour(start_time)) + 24,
                                                          lubridate::hour(start_time))), 
                                  sprintf("%02d", lubridate::minute(start_time)),
                                  sprintf("%02d", lubridate::second(start_time)), sep = ':')) %>%
    arrange(trip_short_name, direction_id, start_time) %>%
    mutate(tipo_dia = current_tipo_dia) %>%
    left_join(select(gtfs$routes, route_id, route_long_name, route_type, agency_id), by = "route_id") %>%
    left_join(select(gtfs$agency, agency_id, agency_name), by = "agency_id") %>%
    left_join(extensoes, by = c("trip_short_name", "direction_id", "route_id")) %>%
    mutate(
      hora = lubridate::hour(start_time),
      faixa = case_when(
        hora < 1 ~ "00:00-01:00",
        hora < 2 ~ "01:00-02:00",
        hora < 3 ~ "02:00-03:00",
        hora < 4 ~ "03:00-04:00",
        hora < 5 ~ "04:00-05:00",
        hora < 6 ~ "05:00-06:00",
        hora < 9 ~ "06:00-09:00",
        hora < 12 ~ "09:00-12:00",
        hora < 15 ~ "12:00-15:00",
        hora < 18 ~ "15:00-18:00",
        hora < 21 ~ "18:00-21:00",
        hora < 22 ~ "21:00-22:00",
        hora < 23 ~ "22:00-23:00",
        hora < 24 ~ "23:00-24:00",
        TRUE ~ "24:00+"
      )
    ) %>%
    select(trip_short_name, route_long_name, trip_headsign, direction_id, departure_time, faixa, 
           agency_name, extensao, route_type, tipo_dia)
  
  return(viagens_completo)
}

calculate_operation_hours <- function(viagens_completo) {
  horario_operacao <- viagens_completo %>%
    arrange(trip_short_name, departure_time) %>%
    group_by(trip_short_name) %>%
    reframe(
      hora_inicio = first(departure_time),
      hora_ultima_partida = last(departure_time)
    )
  
  return(horario_operacao)
}

calculate_planned_departures <- function(viagens_completo) {
  planejado_final <- viagens_completo %>%
    group_by(trip_short_name, direction_id) %>%
    reframe(partidas_planejadas = n())
  
  return(planejado_final)
}

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

cat("\n==========================================================\n")
cat("INICIANDO PROCESSAMENTO\n")
cat("==========================================================\n\n")

x <- data.frame()

cat("ETAPA 1: Lendo GTFS base...\n")
gtfs_base <- filter_gtfs_base(endereco_gtfs)

# Nota: O trace() é interativo. Se rodar em script automático, pode dar erro.
# cat("ETAPA 2: Configurando trace...\n")
# trace(frequencies_to_stop_times, edit = TRUE)

for(current_tipo_dia in tipo_dia) {
  
  cat("\n==========================================================\n")
  cat("PROCESSANDO TIPO DE DIA:", toupper(current_tipo_dia), "\n")
  cat("==========================================================\n\n")
  
  pattern <- get_pattern(current_tipo_dia)
  gtfs_filtered <- filter_trips_by_day(gtfs_base, pattern)
  
  shapes_result <- process_shapes(gtfs_filtered)
  gtfs_processed <- shapes_result$gtfs
  shapes_sf <- shapes_result$shapes_sf
  
  cat("PASSO 5: Convertendo frequencies para stop_times...\n")
  gtfs_proc <- gtfstools::frequencies_to_stop_times(gtfs_processed)
  
  viagens_freq <- process_frequency_trips(gtfs_processed, current_tipo_dia)
  extensoes <- calculate_extensions(gtfs_proc, shapes_sf, viagens_freq)
  viagens_freq_exp <- expand_frequency_trips(viagens_freq)
  linhas_freq <- unique(viagens_freq_exp$trip_short_name)
  
  viagens_qh_regular <- process_regular_trips(gtfs_proc, linhas_freq)
  viagens_completo <- consolidate_trips(viagens_freq_exp, viagens_qh_regular, current_tipo_dia, gtfs_processed, extensoes)
  
  # Salvar resultados parciais
  fwrite(viagens_completo, paste0(pasta_resultados, "partidas_", current_tipo_dia, "_test.csv"))
  
  x <- rbind(x, viagens_completo)
  cat("\n✓ TIPO DE DIA", toupper(current_tipo_dia), "CONCLUÍDO.\n")
}

# FINALIZAÇÃO
fwrite(x, paste0(pasta_resultados, "partidas.csv"))
saveRDS(x, "C:/R_SMTR/resultados/partidas.rds")
cat("\n==========================================================\n")
cat("PROCESSAMENTO COMPLETO FINALIZADO!\n")
cat("==========================================================\n")
