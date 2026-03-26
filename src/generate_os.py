import pandas as pd
import numpy as np
import os
from datetime import datetime

# ============================================================================
# CONFIGURATIONS
# ============================================================================
INPUT_PATH = r"C:\R_SMTR\resultados\partidas\partidas.parquet"
OUTPUT_DIR = r"C:\R_SMTR\resultados\arquivos_os"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIPO_DIA_MAP = {
    "du": "Dia Útil",
    "sab": "Sábado",
    "dom": "Domingo",
    "pf": "Ponto Facultativo"
}

FAIXAS = [
    "00:00-01:00", "01:00-02:00", "02:00-03:00", "03:00-04:00",
    "04:00-05:00", "05:00-06:00", "06:00-09:00", "09:00-12:00",
    "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-22:00",
    "22:00-23:00", "23:00-24:00"
]

FAIXAS_FMT = [
    "00h à 01h", "01h à 02h", "02h à 03h", "03h à 04h",
    "04h à 05h", "05h à 06h", "06h à 09h", "09h à 12h",
    "12h à 15h", "15h à 18h", "18h à 21h", "21h à 22h",
    "22h à 23h", "23h à 24h"
]

FAIXA_MAP = dict(zip(FAIXAS, FAIXAS_FMT))

TIPOS_DIA = ["Dia Útil", "Sábado", "Domingo", "Ponto Facultativo"]

def export_csv_br(df, path):
    """Exports a DataFrame to CSV using ; separator and , for decimals (Brazilian format)."""
    df.to_csv(path, sep=';', decimal=',', index=False, encoding='utf-8-sig')

def main():
    print(f"Lendo dados de: {INPUT_PATH}")
    if not os.path.exists(INPUT_PATH):
        print(f"ERRO: Arquivo {INPUT_PATH} não encontrado.")
        return

    df = pd.read_parquet(INPUT_PATH)

    # Filtrar apenas route_type = '700' (GTFS as string) e excluir MOBI-Rio
    # Garantir que não há espaços em branco
    df['route_type'] = df['route_type'].astype(str).str.strip()
    df['agency_name'] = df['agency_name'].astype(str).str.strip()
    
    df = df[(df['route_type'] == '700') & (df['agency_name'] != "MOBI-Rio")].copy()

    # Mapear tipos de dia
    df['tipo_dia_completo'] = df['tipo_dia'].map(TIPO_DIA_MAP).fillna(df['tipo_dia'])

    # Agrupar e contar partidas
    resumo = df.groupby([
        'trip_short_name', 'trip_headsign', 'route_long_name', 
        'agency_name', 'direction_id', 'tipo_dia_completo', 'faixa', 'extensao'
    ]).size().reset_index(name='partidas')

    # Calcular quilometragem
    resumo['quilometragem'] = resumo['partidas'] * (resumo['extensao'] / 1000)

    # --- Geração de Ponto Facultativo baseado em Dia Útil ---
    pf = resumo[resumo['tipo_dia_completo'] == "Dia Útil"].copy()
    pf['eh_noturno'] = pf['trip_short_name'].str.startswith("SN")
    pf['partidas'] = np.where(pf['eh_noturno'], pf['partidas'], (pf['partidas'] * 0.62).round())
    pf['quilometragem'] = pf['partidas'] * (pf['extensao'] / 1000)
    pf['tipo_dia_completo'] = "Ponto Facultativo"
    pf = pf.drop(columns=['eh_noturno'])

    # Combinar
    resumo_completo = pd.concat([resumo, pf], ignore_index=True)

    # Preparar nomes das colunas para pivot
    resumo_completo['col_partidas'] = "partidas " + resumo_completo['faixa'] + " - " + resumo_completo['tipo_dia_completo']
    resumo_completo['col_km'] = "quilometragem " + resumo_completo['faixa'] + " - " + resumo_completo['tipo_dia_completo']

    # --- PASSO 2: Gerar Tabela Programação OS ---
    id_cols = ['trip_short_name', 'trip_headsign', 'route_long_name', 'agency_name', 'direction_id', 'extensao']
    
    partidas_pivot = resumo_completo.pivot_table(
        index=id_cols, columns='col_partidas', values='partidas', fill_value=0
    ).reset_index()

    km_pivot = resumo_completo.pivot_table(
        index=id_cols, columns='col_km', values='quilometragem', fill_value=0
    ).reset_index()

    tabela_final = pd.merge(partidas_pivot, km_pivot, on=id_cols)

    # Sentido
    def get_sentido(row):
        headsign = str(row['trip_headsign']).lower()
        if 'circular' in headsign:
            return "Circular"
        # direction_id pode vir como string ou int do Parquet
        dir_id = str(row['direction_id'])
        if dir_id == '0':
            return "Ida"
        if dir_id == '1':
            return "Volta"
        return dir_id

    tabela_final['Sentido'] = tabela_final.apply(get_sentido, axis=1)

    # Ordenar colunas
    colunas_ordenadas = ["trip_short_name", "route_long_name", "agency_name", "Sentido", "extensao"]
    for tipo in TIPOS_DIA:
        for faixa in FAIXAS:
            col_part = f"partidas {faixa} - {tipo}"
            col_km = f"quilometragem {faixa} - {tipo}"
            if col_part in tabela_final.columns:
                colunas_ordenadas.extend([col_part, col_km])

    tabela_os = tabela_final[colunas_ordenadas].copy()
    tabela_os = tabela_os.rename(columns={
        "trip_short_name": "Serviço",
        "route_long_name": "Vista",
        "agency_name": "Consórcio",
        "extensao": "Extensão"
    })
    tabela_os = tabela_os.sort_values(["Serviço", "Sentido"])

    # Exportar Tabela OS Base
    os_csv_path = os.path.join(OUTPUT_DIR, "tabela_programacao_OS.csv")
    export_csv_br(tabela_os, os_csv_path)
    print(f"Exportado: {os_csv_path}")

    # --- PASSO 3: Gerar Tabelas Modelo Plano Geral (por tipo de dia) ---
    for tipo in TIPOS_DIA:
        print(f"Processando Plano Geral: {tipo}...")
        
        # Filtro colunas do dia
        cols_base = ["Serviço", "Vista", "Consórcio", "Sentido", "Extensão"]
        cols_dia = [c for c in tabela_os.columns if tipo in c]
        
        if not cols_dia:
            print(f"AVISO: Nenhuma coluna encontrada para o dia '{tipo}'. Pulando.")
            continue
            
        df_tipo = tabela_os[cols_base + cols_dia].copy()
        
        if df_tipo.empty:
            print(f"AVISO: Dados vazios para o dia '{tipo}'. Pulando.")
            continue

        # Calcular extensões por sentido (max por serviço/consorcio)
        extensoes = df_tipo.pivot_table(
            index=["Serviço", "Vista", "Consórcio"],
            columns="Sentido",
            values="Extensão",
            aggfunc="max",
            fill_value=0
        ).reset_index()

        for s in ["Ida", "Volta", "Circular"]:
            col_name = f"Extensão de {s}" if s != "Circular" else "Extensão Circular"
            if s in extensoes.columns:
                extensoes[col_name] = extensoes[s]
            else:
                extensoes[col_name] = 0
            # Remover coluna original do pivot se redundante
            if s in extensoes.columns and s not in ["Serviço", "Vista", "Consórcio"]:
                extensoes = extensoes.drop(columns=[s])
        
        ext_cols = ["Serviço", "Vista", "Consórcio", "Extensão de Ida", "Extensão de Volta", "Extensão Circular"]
        ext_cols = [c for c in ext_cols if c in extensoes.columns]
        extensoes = extensoes[ext_cols]

        # Criar colunas de partidas por faixa formatada
        # E somar totais por linha
        part_cols = [c for c in cols_dia if "partidas" in c]
        km_cols = [c for c in cols_dia if "quilometragem" in c]

        df_tipo[f"Partidas - {tipo}"] = df_tipo[part_cols].sum(axis=1)
        df_tipo[f"Quilometragem - {tipo}"] = df_tipo[km_cols].sum(axis=1)

        # Re-pivotar para ter colunas por sentido e faixa
        pivoted_rows = []
        # Agrupar com dropna=False para garantir que não perdemos nada
        groups = df_tipo.groupby(["Serviço", "Vista", "Consórcio"], dropna=False)
        
        for (serv, vista, cons), group in groups:
            row_data = {"Serviço": serv, "Vista": vista, "Consórcio": cons}
            
            # Totais por sentido
            for s in ["Ida", "Volta", "Circular"]:
                s_group = group[group['Sentido'] == s]
                row_data[f"Partidas {s} - {tipo}"] = s_group[f"Partidas - {tipo}"].sum()
            
            # Quilometragem Total do Serviço
            row_data[f"Quilometragem - {tipo}"] = group[f"Quilometragem - {tipo}"].sum()

            # Viagens
            p_ida = row_data.get(f"Partidas Ida - {tipo}", 0)
            p_volta = row_data.get(f"Partidas Volta - {tipo}", 0)
            p_circ = row_data.get(f"Partidas Circular - {tipo}", 0)
            row_data[f"Viagens - {tipo}"] = (p_ida + p_volta) / 2 + p_circ

            # Faixas Horárias
            for f_orig, f_fmt in FAIXA_MAP.items():
                for s in ["Ida", "Volta", "Circular"]:
                    s_group = group[group['Sentido'] == s]
                    p_col = f"partidas {f_orig} - {tipo}"
                    k_col = f"quilometragem {f_orig} - {tipo}"
                    
                    p_val = s_group[p_col].sum() if p_col in s_group.columns else 0
                    k_val = s_group[k_col].sum() if k_col in s_group.columns else 0
                    
                    row_data[f"Partidas {s} {f_fmt} - {tipo}"] = p_val
                    row_data[f"Quilometragem {s} {f_fmt} - {tipo}"] = k_val
            
            pivoted_rows.append(row_data)

        if not pivoted_rows:
            print(f"AVISO: Nenhuma linha processada para o dia '{tipo}'.")
            continue

        # Criar DF final do dia
        df_final_tipo = pd.DataFrame(pivoted_rows)
        
        # Merge with extensions
        # Garantir que as chaves de merge são do mesmo tipo (string)
        for col in ["Serviço", "Vista", "Consórcio"]:
            extensoes[col] = extensoes[col].astype(str)
            df_final_tipo[col] = df_final_tipo[col].astype(str)

        df_final_tipo = pd.merge(extensoes, df_final_tipo, on=["Serviço", "Vista", "Consórcio"])

        # Ordenação final de colunas do Plano Geral
        col_ordem = ["Serviço", "Vista", "Consórcio", "Extensão de Ida", "Extensão de Volta", "Extensão Circular"]
        col_ordem += [f"Partidas Ida - {tipo}", f"Partidas Volta - {tipo}", f"Partidas Circular - {tipo}", f"Viagens - {tipo}", f"Quilometragem - {tipo}"]
        
        for f_fmt in FAIXAS_FMT:
            for s in ["Ida", "Volta", "Circular"]:
                col_ordem.append(f"Partidas {s} {f_fmt} - {tipo}")
                col_ordem.append(f"Quilometragem {s} {f_fmt} - {tipo}")

        available_cols = [c for c in col_ordem if c in df_final_tipo.columns]
        df_final_tipo = df_final_tipo[available_cols]

        # Exportar
        nome_arquivo = f"tabela_{tipo.lower().replace(' ', '_')}.csv"
        path_arquivo = os.path.join(OUTPUT_DIR, nome_arquivo)
        export_csv_br(df_final_tipo, path_arquivo)
        print(f"Exportado: {path_arquivo}")

    print("\nProcessamento concluído com sucesso!")

if __name__ == "__main__":
    main()
