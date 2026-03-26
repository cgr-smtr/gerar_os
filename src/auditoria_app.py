import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# ============================================================================
# APP DE AUDITORIA DE OS - VERSÃO STREAMLIT
# ============================================================================

st.set_page_config(page_title="Auditoria de Programação OS", layout="wide")

st.title("Auditoria de Programação OS - Gestão de Rede")

# Sidebar
st.sidebar.header("Arquivos de Entrada")
file_antigo = st.sidebar.file_uploader("Tabela da Quinzena ANTERIOR", type=["csv", "parquet"])
file_novo = st.sidebar.file_uploader("Tabela da Quinzena ATUAL", type=["csv", "parquet"])

processar = st.sidebar.button("Executar Auditoria", type="primary")

def ler_dados(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith('.csv'):
        # Tenta ler as primeiras linhas para detectar o separador
        content = uploaded_file.read(1024).decode('utf-8-sig', errors='ignore')
        uploaded_file.seek(0)
        
        # Detecta se é ; ou ,
        if ';' in content:
            sep = ';'
            dec = ','
        else:
            sep = ','
            dec = ',' # Assume decimal , se o usuário mencionou, mas se for padrão US o pandas resolve
            
        try:
            return pd.read_csv(uploaded_file, sep=sep, decimal=dec, quotechar='"')
        except Exception as e:
            st.error(f"Erro ao ler CSV: {e}")
            return None
    elif uploaded_file.name.endswith('.parquet'):
        return pd.read_parquet(uploaded_file)
    return None

def calc_ivk(df):
    # Procura colunas que contenham Km, Quilometragem ou Extensão (Case-insensitive)
    cols_all_km = [c for c in df.columns if any(x.lower() in c.lower() for x in ["Km", "Quilometragem", "Extensão"])]
    cols_all_partidas = [c for c in df.columns if any(x.lower() in c.lower() for x in ["Partida", "Viagem"])]
    
    # Filtra para evitar dupla contagem: tenta identificar colunas de "Total"
    import re
    faixa_pattern = re.compile(r"(\d{2}:\d{2}-\d{2}:\d{2})|(\d{2}h à \d{2}h)")
    
    cols_totais_km = [c for c in cols_all_km if not faixa_pattern.search(c)]
    cols_totais_partidas = [c for c in cols_all_partidas if not faixa_pattern.search(c)]
    
    # Se não encontrar colunas de total, usa as de faixa (mas nesse caso haverá apenas faixas)
    final_cols_km = cols_totais_km if cols_totais_km else cols_all_km
    final_cols_partidas = cols_totais_partidas if cols_totais_partidas else cols_all_partidas
    
    # Converte para numérico (força erros para NaN)
    df_km = df[final_cols_km].apply(pd.to_numeric, errors='coerce')
    df_part = df[final_cols_partidas].apply(pd.to_numeric, errors='coerce')
    
    km_total = df_km.sum().sum()
    part_total = df_part.sum().sum()
    
    if km_total <= 0:
        return 0
    return part_total / km_total

if processar and file_antigo and file_novo:
    antigo = ler_dados(file_antigo)
    novo = ler_dados(file_novo)
    
    if antigo is not None and novo is not None:
        chaves = ["Serviço", "Vista", "Consórcio", "Sentido"]
        chaves_efetivas = [c for c in chaves if c in antigo.columns]
        
        if not chaves_efetivas:
            st.error(f"Não foi possível encontrar as colunas de identificação {chaves} em um dos arquivos.")
            st.write("Colunas encontradas no arquivo Antigo:", list(antigo.columns))
            st.write("Colunas encontradas no arquivo Novo:", list(novo.columns))
            st.stop()
            
        # IVK
        ivk_antigo = calc_ivk(antigo)
        ivk_atual = calc_ivk(novo)
        
        # Entradas e Saídas
        lin_antigas = antigo[chaves_efetivas].drop_duplicates()
        lin_novas_df = novo[chaves_efetivas].drop_duplicates()
        
        # Novas (linhas em novo que não estão em antigo)
        novas = pd.merge(lin_novas_df, lin_antigas, on=chaves_efetivas, how='left', indicator=True)
        novas = novas[novas['_merge'] == 'left_only'].drop(columns=['_merge'])
        
        # Excluídas (linhas em antigo que não estão em novo)
        excluidas = pd.merge(lin_antigas, lin_novas_df, on=chaves_efetivas, how='left', indicator=True)
        excluidas = excluidas[excluidas['_merge'] == 'left_only'].drop(columns=['_merge'])
        
        # Comparação detalhada (todas as colunas numéricas)
        num_cols = antigo.select_dtypes(include=[np.number]).columns.tolist()
        num_cols = [c for c in num_cols if c not in chaves_efetivas]
        
        antigo_long = antigo.melt(id_vars=chaves_efetivas, value_vars=num_cols, var_name="Campo", value_name="Valor_Anterior")
        novo_long = novo.melt(id_vars=chaves_efetivas, value_vars=num_cols, var_name="Campo", value_name="Valor_Atual")
        
        comparativo = pd.merge(antigo_long, novo_long, on=chaves_efetivas + ["Campo"], how='outer')
        comparativo['Valor_Anterior'] = comparativo['Valor_Anterior'].fillna(0)
        comparativo['Valor_Atual'] = comparativo['Valor_Atual'].fillna(0)
        comparativo['Diferenca'] = (comparativo['Valor_Atual'] - comparativo['Valor_Anterior']).round(3)
        
        comparativo = comparativo[comparativo['Diferenca'] != 0]
        
        # Impactos
        impacto_km = comparativo[comparativo['Campo'].str.contains("Km|Quilometragem|Extensão", case=False)]['Diferenca'].sum()
        impacto_viagens = comparativo[comparativo['Campo'].str.contains("Partida|Viagem", case=False)]['Diferenca'].sum()
        
        # Diagnóstico Tabular
        diag = comparativo.groupby("Serviço", group_keys=False).apply(lambda x: pd.Series({
            "Partida": "X" if any(x['Campo'].str.contains("Partida|Viagem", case=False)) else "",
            "Quilometragem": "X" if any(x['Campo'].str.contains("Km|Quilometragem|Extensão", case=False)) else ""
        }), include_groups=False).reset_index()

        # UI Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["Diferenças Encontradas", "Apenas Partidas", "Apenas Quilometragem", "Resumo de Alterações"])
        
        with tab1:
            st.dataframe(comparativo, width='stretch')
            
        with tab2:
            st.dataframe(comparativo[comparativo['Campo'].str.contains("Partida|Viagem", case=False)], width='stretch')

        with tab3:
            st.dataframe(comparativo[comparativo['Campo'].str.contains("Km|Quilometragem|Extensão", case=False)], width='stretch')
            
        with tab4:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("IVK Anterior", f"{ivk_antigo:.5f}")
                st.metric("IVK Atual", f"{ivk_atual:.5f}")
                var_ivk = ((ivk_atual / ivk_antigo) - 1) * 100 if ivk_antigo > 0 else 0
                st.metric("Variação Eficiência", f"{var_ivk:.2f}%")
            
            with col2:
                st.metric("Variação KM Total", f"{impacto_km:.2f} km")
                st.metric("Variação Viagens", f"{impacto_viagens:.0f}")

            st.markdown("---")
            st.subheader("Novas Linhas")
            st.table(novas)
            
            st.subheader("Linhas Excluídas")
            st.table(excluidas)
            
            st.subheader("Diagnóstico de Alterações")
            st.table(diag)

            # Download
            report = io.StringIO()
            report.write("==================================================\n")
            report.write("       RELATORIO DE AUDITORIA E PRODUTIVIDADE     \n")
            report.write("==================================================\n")
            report.write(f"Analise gerada em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
            report.write(f"IVK Anterior: {ivk_antigo:.5f} | Atual: {ivk_atual:.5f}\n")
            report.write(f"Variacao de Eficiencia: {var_ivk:.2f}%\n")
            report.write("--------------------------------------------------\n\n")
            report.write(f"Variacao KM Total: {impacto_km:.2f} km\n")
            report.write(f"Variacao Viagens: {impacto_viagens:.0f} partidas\n\n")
            report.write(f"Serviços Alterados: {', '.join(comparativo['Serviço'].unique())}\n\n")
            
            st.download_button(
                label="Baixar Relatório Completo",
                data=report.getvalue(),
                file_name=f"Resumo_Auditoria_OS_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
    else:
        st.error("Erro ao ler arquivos. Verifique o formato.")
else:
    st.info("Aguardando upload dos arquivos e clique em 'Executar Auditoria'.")
