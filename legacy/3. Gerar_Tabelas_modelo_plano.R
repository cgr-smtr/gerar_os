library(tidyverse)

# ============================================================================
# BLOCO 3: TABELA PIVOTADA POR SENTIDO E FAIXA HORÁRIA - Modelo Plano Geral
# ============================================================================

# Ler o arquivo RDS já processado (que já contém quilometragem em KM para todos os dias)
tabela_base <- readRDS("C:/R_SMTR/resultados/tabela_programacao_OS.rds")

# Função para processar um tipo de dia específico
processar_tipo_dia <- function(dados, tipo_dia_nome) {
  
  # Definir faixas horárias
  faixas <- c(
    "00:00-01:00", "01:00-02:00", "02:00-03:00", "03:00-04:00",
    "04:00-05:00", "05:00-06:00", "06:00-09:00", "09:00-12:00",
    "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-22:00",
    "22:00-23:00", "23:00-24:00"
  )
  
  # Converter faixas para formato "00h à 01h"
  faixas_formatadas <- c(
    "00h à 01h", "01h à 02h", "02h à 03h", "03h à 04h",
    "04h à 05h", "05h à 06h", "06h à 09h", "09h à 12h",
    "12h à 15h", "15h à 18h", "18h à 21h", "21h à 22h",
    "22h à 23h", "23h à 24h"
  )
  
  # Selecionar colunas base
  colunas_base <- c("Serviço", "Vista", "Consórcio", "Sentido", "Extensão")
  
  # Selecionar colunas do tipo de dia específico
  colunas_tipo <- names(dados)[str_detect(names(dados), tipo_dia_nome)]
  
  tabela_tipo <- dados %>%
    select(all_of(c(colunas_base, colunas_tipo)))
  
  # Criar colunas de extensão por sentido
  extensoes_por_sentido <- dados %>%
    select(Serviço, Vista, Consórcio, Sentido, Extensão) %>%
    group_by(Serviço, Vista, Consórcio, Sentido) %>%
    summarise(Extensão = max(Extensão, na.rm = TRUE), .groups = "drop") %>%
    pivot_wider(
      id_cols = c(Serviço, Vista, Consórcio),
      names_from = Sentido,
      values_from = Extensão,
      names_prefix = "Extensão de "
    )
  
  # Garantir que todas as colunas de extensão existam e substituir NAs
  for (col in c("Extensão de Ida", "Extensão de Volta", "Extensão de Circular")) {
    if (!col %in% names(extensoes_por_sentido)) {
      extensoes_por_sentido[[col]] <- 0
    } else {
      extensoes_por_sentido[[col]] <- replace_na(extensoes_por_sentido[[col]], 0)
    }
  }
  
  # Processar cada linha (serviço/sentido)
  resultado_linhas <- list()
  
  for (i in 1:nrow(tabela_tipo)) {
    linha <- tabela_tipo[i, ]
    servico <- linha$Serviço
    vista <- linha$Vista
    consorcio <- linha$Consórcio
    sentido <- linha$Sentido
    
    # Criar linha de resultado
    nova_linha <- tibble(
      Serviço = servico,
      Vista = vista,
      Consórcio = consorcio
    )
    
    # Adicionar extensões
    ext_servico <- extensoes_por_sentido %>%
      filter(Serviço == servico, Vista == vista, Consórcio == consorcio)
    
    nova_linha$`Extensão de Ida` <- if(nrow(ext_servico) > 0) ext_servico$`Extensão de Ida`[1] else 0
    nova_linha$`Extensão de Volta` <- if(nrow(ext_servico) > 0) ext_servico$`Extensão de Volta`[1] else 0
    nova_linha$`Extensão Circular` <- if(nrow(ext_servico) > 0) ext_servico$`Extensão de Circular`[1] else 0
    
    # Adicionar totais de partidas por sentido
    for (sent in c("Ida", "Volta", "Circular")) {
      col_nome <- paste0("Partidas ", sent, " - ", tipo_dia_nome)
      if (sentido == sent) {
        total_partidas <- 0
        for (j in 1:length(faixas)) {
          col_partida <- paste0("partidas ", faixas[j], " - ", tipo_dia_nome)
          if (col_partida %in% names(linha)) {
            total_partidas <- total_partidas + as.numeric(linha[[col_partida]])
          }
        }
        nova_linha[[col_nome]] <- total_partidas
      } else {
        nova_linha[[col_nome]] <- 0
      }
    }
    
    nova_linha[[paste0("Viagens - ", tipo_dia_nome)]] <- 0
    
    # Quilometragem total (Sem divisão, pois já foi corrigido na base)
    total_km <- 0
    for (j in 1:length(faixas)) {
      col_km <- paste0("quilometragem ", faixas[j], " - ", tipo_dia_nome)
      if (col_km %in% names(linha)) {
        total_km <- total_km + as.numeric(linha[[col_km]])
      }
    }
    nova_linha[[paste0("Quilometragem - ", tipo_dia_nome)]] <- total_km
    
    # Adicionar partidas e quilometragem por faixa horária
    for (j in 1:length(faixas)) {
      faixa <- faixas[j]
      faixa_fmt <- faixas_formatadas[j]
      
      col_partida <- paste0("partidas ", faixa, " - ", tipo_dia_nome)
      col_km <- paste0("quilometragem ", faixa, " - ", tipo_dia_nome)
      
      if (col_partida %in% names(linha) && col_km %in% names(linha)) {
        nova_linha[[paste0("Partidas ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome)]] <- as.numeric(linha[[col_partida]])
        nova_linha[[paste0("Quilometragem ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome)]] <- as.numeric(linha[[col_km]])
      } else {
        nova_linha[[paste0("Partidas ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome)]] <- 0
        nova_linha[[paste0("Quilometragem ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome)]] <- 0
      }
    }
    
    resultado_linhas[[i]] <- nova_linha
  }
  
  # Agregação Final
  resultado_agregado <- bind_rows(resultado_linhas) %>%
    group_by(Serviço, Vista, Consórcio) %>%
    summarise(
      `Extensão de Ida` = first(`Extensão de Ida`),
      `Extensão de Volta` = first(`Extensão de Volta`),
      `Extensão Circular` = first(`Extensão Circular`),
      across(starts_with("Partidas") | starts_with("Quilometragem"), ~sum(.x, na.rm = TRUE)),
      .groups = "drop"
    ) %>%
    mutate(
      !!paste0("Viagens - ", tipo_dia_nome) := 
        ((!!sym(paste0("Partidas Ida - ", tipo_dia_nome)) + 
            !!sym(paste0("Partidas Volta - ", tipo_dia_nome))) / 2) + 
        !!sym(paste0("Partidas Circular - ", tipo_dia_nome))
    )
  
  # Reordenação de colunas
  colunas_base_ordem <- c("Serviço", "Vista", "Consórcio", "Extensão de Ida", "Extensão de Volta", "Extensão Circular")
  colunas_totais <- c(paste0("Partidas Ida - ", tipo_dia_nome), paste0("Partidas Volta - ", tipo_dia_nome), 
                      paste0("Partidas Circular - ", tipo_dia_nome), paste0("Viagens - ", tipo_dia_nome), 
                      paste0("Quilometragem - ", tipo_dia_nome))
  
  colunas_faixas <- c()
  for (j in 1:length(faixas_formatadas)) {
    faixa_fmt <- faixas_formatadas[j]
    for (sentido in c("Ida", "Volta", "Circular")) {
      colunas_faixas <- c(colunas_faixas, 
                          paste0("Partidas ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome),
                          paste0("Quilometragem ", sentido, " ", faixa_fmt, " - ", tipo_dia_nome))
    }
  }
  
  resultado_final <- resultado_agregado %>%
    select(all_of(intersect(c(colunas_base_ordem, colunas_totais, colunas_faixas), names(.))))
  
  return(resultado_final)
}

# Execução do loop de tipos de dia
tipos_dia <- c("Dia Útil", "Sábado", "Domingo", "Ponto Facultativo")

for (tipo in tipos_dia) {
  cat("\nProcessando:", tipo, "...")
  tabela_resultado <- processar_tipo_dia(tabela_base, tipo)
  nome_arquivo <- str_replace_all(tolower(tipo), " ", "_")
  
  # write_csv2 garante o formato BR (decimal com vírgula)
  write_csv2(tabela_resultado, paste0("C:/R_SMTR/resultados/tabela_", nome_arquivo, ".csv"))
  saveRDS(tabela_resultado, paste0("C:/R_SMTR/resultados/tabela_", nome_arquivo, ".rds"))
  cat(" Concluído.")
}

cat("\n\n✓ Processamento concluído com base corrigida!\n")

