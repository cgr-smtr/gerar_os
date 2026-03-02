pacotes <- c("tidyverse", "shiny", "DT", "openxlsx", "shinythemes")
instalados <- pacotes %in% installed.packages()

if(any(!instalados)) {
  install.packages(pacotes[!instalados])
}

library(shiny)
library(tidyverse)
library(DT)
library(openxlsx)
library(shinythemes)

# ============================================================================
# APP DE AUDITORIA DE OS - VERSÃO FINAL CORRIGIDA E COMPLETA
# ============================================================================

ui <- fluidPage(
  theme = shinytheme("flatly"),
  titlePanel(title = span("Auditoria de Programação OS - Gestão de Rede", style = "color: #2c3e50;")),
  
  sidebarLayout(
    sidebarPanel(
      wellPanel(
        h4("Arquivos de Entrada"),
        fileInput("file_antigo", "Tabela da Quinzena ANTERIOR", accept = c(".csv", ".rds")),
        fileInput("file_novo", "Tabela da Quinzena ATUAL", accept = c(".csv", ".rds")),
        hr(),
        actionButton("processar", "Executar Auditoria", class = "btn-success btn-block"),
        br(),
        uiOutput("botao_download") 
      )
    ),
    
    mainPanel(
      tabsetPanel(
        tabPanel("Diferenças Encontradas", br(), DTOutput("tabela_detalhada")),
        tabPanel("Apenas Partidas", br(), DTOutput("tabela_partidas")),
        tabPanel("Resumo de Alterações e Impactos", br(), verbatimTextOutput("sumario"))
      )
    )
  )
)

server <- function(input, output, session) {
  
  ler_dados <- function(input_file) {
    req(input_file)
    ext <- tools::file_ext(input_file$name)
    if (ext == "rds") return(readRDS(input_file$datapath))
    if (ext == "csv") return(read_csv2(input_file$datapath))
  }
  
  resumo_stats <- reactiveValues(
    novas = NULL, excluidas = NULL, alteradas_limpo = NULL, alteradas_diag_df = NULL,
    impacto_km = 0, impacto_viagens = 0, IVK_antigo = 0, IVK_atual = 0
  )
  
  # Reactive que processa os dados e retorna o dataframe de diferenças
  dados_auditados <- eventReactive(input$processar, {
    antigo <- ler_dados(input$file_antigo)
    novo <- ler_dados(input$file_novo)
    
    chaves <- c("Serviço", "Vista", "Consórcio", "Sentido")
    chaves_efetivas <- intersect(chaves, names(antigo))
    
    # Cálculos de IVK
    calc_IVK <- function(df) {
      km_total <- sum(df %>% select(matches("Km|Quilometragem|Extensão")) %>% select(where(is.numeric)), na.rm = TRUE)
      part_total <- sum(df %>% select(matches("Partida|Viagem")) %>% select(where(is.numeric)), na.rm = TRUE)
      if(km_total <= 0) return(0)
      return(part_total / km_total)
    }
    resumo_stats$IVK_antigo <- calc_IVK(antigo)
    resumo_stats$IVK_atual <- calc_IVK(novo)
    
    # Entradas e Saídas (Item 3)
    lin_antigas <- antigo %>% select(all_of(chaves_efetivas)) %>% distinct()
    lin_novas_df <- novo %>% select(all_of(chaves_efetivas)) %>% distinct()
    resumo_stats$novas <- anti_join(lin_novas_df, lin_antigas, by = chaves_efetivas)
    resumo_stats$excluidas <- anti_join(lin_antigas, lin_novas_df, by = chaves_efetivas)
    
    # Comparação detalhada
    antigo_long <- antigo %>% pivot_longer(cols = where(is.numeric), names_to = "Campo", values_to = "Valor_Anterior")
    novo_long <- novo %>% pivot_longer(cols = where(is.numeric), names_to = "Campo", values_to = "Valor_Atual")
    
    comparativo <- full_join(antigo_long, novo_long, by = c(chaves_efetivas, "Campo")) %>%
      mutate(Valor_Anterior = replace_na(Valor_Anterior, 0), 
             Valor_Atual = replace_na(Valor_Atual, 0),
             Diferenca = round(Valor_Atual - Valor_Anterior, 3)) %>%
      filter(Diferenca != 0)
    
    # Item 4 (Lista Simples)
    resumo_stats$alteradas_limpo <- sort(unique(comparativo$Serviço))
    
    # Item 5 (Diagnóstico Tabular)
    resumo_stats$alteradas_diag_df <- comparativo %>%
      group_by(Serviço) %>%
      summarise(
        Partida = if_else(any(grepl("Partida|Viagem", Campo, ignore.case = TRUE)), "X", ""),
        Quilometragem = if_else(any(grepl("Km|Quilometragem|Extensão", Campo, ignore.case = TRUE)), "X", "")
      ) %>%
      arrange(Serviço)
    
    resumo_stats$impacto_km <- sum(comparativo$Diferenca[grepl("Km|Quilometragem|Extensão", comparativo$Campo, ignore.case = TRUE)])
    resumo_stats$impacto_viagens <- sum(comparativo$Diferenca[grepl("Partida|Viagem", comparativo$Campo, ignore.case = TRUE)])
    
    return(comparativo)
  })
  
  # Função auxiliar para gerar o texto dos itens 1 a 4 (usada na tela e no download)
  gerar_texto_1_ao_4 <- function() {
    req(dados_auditados())
    con <- textConnection("resumo_txt", "w")
    cat("==================================================\n", file = con)
    cat("       RELATORIO DE AUDITORIA E PRODUTIVIDADE     \n", file = con)
    cat("==================================================\n", file = con)
    cat("Analise gerada em:", format(Sys.time(), "%d/%m/%Y %H:%M"), "\n\n", file = con)
    
    cat("[1] METRICAS DE PRODUTIVIDADE (IVK)\n", file = con)
    cat("IVK Anterior (Partidas/Km): ", round(resumo_stats$IVK_antigo, 5), " | Atual: ", round(resumo_stats$IVK_atual, 5), "\n", file = con)
    var_IVK <- ((resumo_stats$IVK_atual/resumo_stats$IVK_antigo)-1)*100
    cat("Variacao de Eficiencia: ", round(var_IVK, 2), "%\n", file = con)
    cat("--------------------------------------------------\n\n", file = con)
    
    cat("[2] IMPACTO BRUTO NA REDE\n", file = con)
    cat("Variacao KM Total: ", resumo_stats$impacto_km, " km\n", file = con)
    cat("Variacao Viagens:  ", resumo_stats$impacto_viagens, " partidas\n\n", file = con)
    
    cat("[3] EXTRATO DE LINHAS (ENTRADAS/SAIDAS)\n", file = con)
    cat("Novas:", nrow(resumo_stats$novas), "\n", file = con)
    if(nrow(resumo_stats$novas) > 0) {
      msg_novas <- capture.output(print(as.data.frame(resumo_stats$novas), row.names = FALSE))
      cat(paste(msg_novas, collapse = "\n"), "\n", file = con)
    }
    cat("\nExcluidas:", nrow(resumo_stats$excluidas), "\n", file = con)
    if(nrow(resumo_stats$excluidas) > 0) {
      msg_exc <- capture.output(print(as.data.frame(resumo_stats$excluidas), row.names = FALSE))
      cat(paste(msg_exc, collapse = "\n"), "\n", file = con)
    }
    
    cat("\n[4] LISTA DE SERVICOS ALTERADOS (REFERENCIA)\n", file = con)
    servicos_limpo <- resumo_stats$alteradas_limpo
    if(length(servicos_limpo) > 0) {
      grupos_limpo <- split(servicos_limpo, ceiling(seq_along(servicos_limpo)/20))
      lapply(grupos_limpo, function(g) { cat(paste(g, collapse = ", "), ",\n", file = con) })
    }
    res <- textConnectionValue(con); close(con); return(res)
  }
  
  # Renderização das tabelas de Diferenças (Voltando a funcionar)
  output$tabela_detalhada <- renderDT({
    req(dados_auditados())
    datatable(dados_auditados(), filter = 'top', options = list(pageLength = 10, scrollX = TRUE), rownames = FALSE)
  })
  
  output$tabela_partidas <- renderDT({
    req(dados_auditados())
    df_partidas <- dados_auditados() %>% filter(grepl("Partida|Viagem", Campo, ignore.case = TRUE))
    datatable(df_partidas, filter = 'top', options = list(pageLength = 10, scrollX = TRUE), rownames = FALSE)
  })
  
  # Renderização do Resumo na tela
  output$sumario <- renderPrint({ 
    cat(gerar_texto_1_ao_4(), sep = "\n") 
    cat("\n[5] DIAGNOSTICO TABULAR DE ALTERACOES\n")
    print(as.data.frame(resumo_stats$alteradas_diag_df), row.names = FALSE)
  })
  
  # Lógica de Download
  output$botao_download <- renderUI({ 
    req(dados_auditados())
    downloadButton("downloadResumo", "Baixar Resumo (.csv)", class = "btn-primary btn-block") 
  })
  
  output$downloadResumo <- downloadHandler(
    filename = function() { paste0("Resumo_Auditoria_OS_", format(Sys.time(), "%Y%m%d"), ".csv") },
    content = function(file) {
      # 1. Escreve os itens 1 a 4 discriminados
      writeLines(gerar_texto_1_ao_4(), file)
      
      # 2. Adiciona o título do Item 5
      # Usamos uma conexão temporária para garantir que o append não apague o texto anterior
      cat("\n[5] DIAGNOSTICO TABULAR DE ALTERACOES\n", file = file, append = TRUE)
      
      # 3. Escreve a tabela do Item 5 com colunas reais (;)
      write.table(resumo_stats$alteradas_diag_df, file, append = TRUE, sep = ";", row.names = FALSE, quote = FALSE)
    }
  )
}

shinyApp(ui, server)
