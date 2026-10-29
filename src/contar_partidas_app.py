import streamlit as st
import pandas as pd
from datetime import time, datetime
from pathlib import Path

# ============================================================================
# CONTADOR DE PARTIDAS POR FAIXA
# ============================================================================

st.set_page_config(page_title="Contador de Partidas por Faixa", layout="wide")

st.title("Contador de Partidas por Faixa")

RAIZ = Path(__file__).resolve().parent.parent

FAIXAS = [
    "00:00-01:00", "01:00-02:00", "02:00-03:00", "03:00-04:00",
    "04:00-05:00", "05:00-06:00", "06:00-09:00", "09:00-12:00",
    "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-22:00",
    "22:00-23:00", "23:00-24:00"
]


def faixa_de_hora(h):
    minutos = h.hour * 60 + h.minute
    for faixa in FAIXAS:
        ini, fim = faixa.split("-")
        ini_h, ini_m = map(int, ini.split(":"))
        fim_h, fim_m = map(int, fim.split(":"))
        ini_min = ini_h * 60 + ini_m
        fim_min = fim_h * 60 + fim_m
        if fim_min == 24 * 60:
            fim_min = 24 * 60
        if ini_min <= minutos < fim_min:
            return faixa
    return None


def parse_horarios(texto):
    """Extrai horários únicos do texto colado (formato tab-separated Horário\tIntervalo)."""
    horarios = set()
    invalidas = []
    for i, linha in enumerate(texto.strip().splitlines(), start=1):
        linha = linha.strip()
        if not linha:
            continue
        campo = linha.split("\t")[0].strip()
        if not campo or campo.lower() == "horário":
            continue
        try:
            h = time.fromisoformat(campo)
            horarios.add(h)
        except ValueError:
            invalidas.append((i, campo))
    return sorted(horarios), invalidas


def contar_faixas(horarios):
    contagem = {f: 0 for f in FAIXAS}
    for h in horarios:
        f = faixa_de_hora(h)
        if f:
            contagem[f] += 1
    return contagem


def para_hora(v):
    """Converte valor de célula Excel em time."""
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    try:
        return time.fromisoformat(str(v).strip())
    except ValueError:
        return None


def ler_xlsx(caminho):
    """Lê o XLSX detectando o formato pelos cabeçalhos.

    Formatos suportados:
    - Intersul: B4='Horário' (Ida), G4='Horário' (Volta), dados a partir da linha 5
    - Modelo de quadro: B4='Horário' (Ida), E4='Horário 2' (Volta), dados a partir da linha 5
    """
    abas = pd.read_excel(caminho, sheet_name=None, header=None)
    resultado = {}
    for nome, df in abas.items():
        if nome == "Resumo":
            continue

        # Localizar linha de cabeçalho e colunas de horário (Ida e Volta)
        col_ida = col_volta = linha_hdr = None
        for r in range(min(10, len(df))):
            cols_horario = [
                c for c in range(1, min(8, df.shape[1]))
                if str(df.iat[r, c]).strip().lower().startswith("hor")
            ]
            if cols_horario:
                linha_hdr = r
                col_ida = cols_horario[0]
                col_volta = cols_horario[1] if len(cols_horario) > 1 else None
                break
        if col_ida is None:
            continue

        ida, volta = set(), set()
        for _, linha in df.iloc[linha_hdr + 1:].iterrows():
            h = para_hora(linha[col_ida] if len(linha) > col_ida else None)
            if h:
                ida.add(h)
            if col_volta is not None:
                h = para_hora(linha[col_volta] if len(linha) > col_volta else None)
                if h:
                    volta.add(h)
        if ida or volta:
            resultado[nome] = (sorted(ida), sorted(volta))
    return resultado


modo = st.radio("Modo de entrada", ["Arquivo XLSX (raiz do projeto)", "Colar lista"], horizontal=True)

if modo.startswith("Arquivo"):
    arquivos = sorted(RAIZ.glob("*.xlsx"))
    if not arquivos:
        st.warning(f"Nenhum .xlsx encontrado em {RAIZ}")
        st.stop()
    nomes = [a.name for a in arquivos]
    escolhido = st.selectbox("Arquivo XLSX", nomes)
    caminho = RAIZ / escolhido
    processar = st.button("Contar partidas", type="primary")

    if processar:
        abas = ler_xlsx(caminho)
        if not abas:
            st.warning("Nenhuma aba com horários encontrada.")
            st.stop()

        dfs = []
        for nome, (ida, volta) in abas.items():
            c_ida = contar_faixas(ida)
            c_volta = contar_faixas(volta)
            for f in FAIXAS:
                dfs.append({
                    "Aba": nome, "Direção": "Ida", "Faixa": f, "Partidas": c_ida[f],
                })
                dfs.append({
                    "Aba": nome, "Direção": "Volta", "Faixa": f, "Partidas": c_volta[f],
                })
        detalhe = pd.DataFrame(dfs)

        # Resumo por aba x direção
        resumo_aba = detalhe.groupby(["Aba", "Direção"])["Partidas"].sum().unstack(fill_value=0)
        if "Ida" not in resumo_aba.columns:
            resumo_aba["Ida"] = 0
        if "Volta" not in resumo_aba.columns:
            resumo_aba["Volta"] = 0
        resumo_aba["Total"] = resumo_aba["Ida"] + resumo_aba["Volta"]

        st.subheader("Total por aba")
        st.dataframe(resumo_aba[["Ida", "Volta", "Total"]], use_container_width=True)

        # Pivot: faixas por aba/direção
        st.subheader("Partidas por faixa")
        pivot = detalhe.pivot_table(
            index=["Aba", "Direção"], columns="Faixa", values="Partidas",
            fill_value=0, aggfunc="sum",
        )[FAIXAS]
        st.dataframe(pivot, use_container_width=True)

        # Consolidado geral
        st.subheader("Consolidado (todas as abas)")
        linhas = []
        for f in FAIXAS:
            i = int(detalhe[(detalhe["Direção"] == "Ida") & (detalhe["Faixa"] == f)]["Partidas"].sum())
            v = int(detalhe[(detalhe["Direção"] == "Volta") & (detalhe["Faixa"] == f)]["Partidas"].sum())
            linhas.append({"Faixa": f, "Ida": i, "Volta": v, "Total": i + v})
        df_conc = pd.DataFrame(linhas)
        st.dataframe(df_conc, hide_index=True, use_container_width=True)
        st.metric("Total geral", int(df_conc["Total"].sum()))

        csv = df_conc.to_csv(sep=";", decimal=",", index=False, encoding="utf-8-sig")
        csv_det = detalhe.to_csv(sep=";", decimal=",", index=False, encoding="utf-8-sig")
        st.download_button("Baixar consolidado CSV (BR)", data=csv,
                           file_name="partidas_por_faixa.csv", mime="text/csv")
        st.download_button("Baixar detalhe CSV (BR)", data=csv_det,
                           file_name="partidas_por_faixa_detalhe.csv", mime="text/csv")

else:
    texto = st.text_area(
        "Cole a lista de partidas (coluna Horário; Intervalo é ignorado):",
        height=300,
        placeholder="Horário\tIntervalo\n05:30:00\t--\n06:00:00\t00:30:00\n...",
    )

    processar = st.button("Contar partidas", type="primary")

    if processar:
        if not texto.strip():
            st.warning("Cole a lista de horários antes de contar.")
            st.stop()

        horarios, invalidas = parse_horarios(texto)

        if invalidas:
            st.error(
                "Linhas com horário inválido (ignoradas): "
                + ", ".join(f"linha {i}: '{c}'" for i, c in invalidas)
            )

        if not horarios:
            st.warning("Nenhum horário válido encontrado.")
            st.stop()

        contagem = contar_faixas(horarios)

        df = pd.DataFrame({
            "Faixa": FAIXAS,
            "Partidas": [contagem[f] for f in FAIXAS],
        })

        total = df["Partidas"].sum()
        st.subheader(f"Total geral: {total} partidas ({len(horarios)} horários distintos)")
        st.dataframe(df, hide_index=True, use_container_width=True)

        csv = df.to_csv(sep=";", decimal=",", index=False, encoding="utf-8-sig")
        st.download_button(
            "Baixar CSV (BR)",
            data=csv,
            file_name="partidas_por_faixa.csv",
            mime="text/csv",
        )
