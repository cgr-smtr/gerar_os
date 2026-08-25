import streamlit as st
import pandas as pd
import numpy as np
import zipfile
import io
import os
from datetime import datetime
import pydeck as pdk

# ============================================================================
# IMPORTS OPCIONAIS GEOESPACIAIS COM FALLBACKS ROBUSTOS
# ============================================================================
try:
    from shapely.geometry import LineString
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    from pyproj import Geod
    geod_calc = Geod(ellps="WGS84")
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    geod_calc = None

# ============================================================================
# FORMATAÇÃO NUMÉRICA PADRÃO BRASIL (Milhar: . | Decimal: ,)
# ============================================================================

def fmt_br(val, decimais=1, sinal=False, unidade=""):
    """
    Formata valores numéricos no padrão brasileiro:
    - Separador de milhar: '.'
    - Separador decimal: ','
    """
    if pd.isna(val) or val is None or val == "":
        return "N/D"
    try:
        val_float = float(val)
        if sinal:
            texto = f"{val_float:+,.{decimais}f}"
        else:
            texto = f"{val_float:,.{decimais}f}"
        # Inverte separadores: , -> X, . -> ,, X -> .
        texto_br = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        if unidade:
            return f"{texto_br} {unidade}".strip()
        return texto_br
    except Exception:
        return str(val)

# ============================================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ============================================================================
st.set_page_config(
    page_title="Auditoria de Traçados GTFS",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# FUNÇÕES DE LEITURA E PROCESSAMENTO GTFS
# ============================================================================

def ler_tabela_gtfs(fonte, nome_arquivo, obrigatorio=True):
    """
    Lê um arquivo .txt do GTFS a partir de um ZipFile ou de um diretório.
    """
    df = None
    try:
        if isinstance(fonte, zipfile.ZipFile):
            candidatos = [f for f in fonte.namelist() if f.endswith(nome_arquivo) or f.endswith(nome_arquivo.lower())]
            if not candidatos:
                if obrigatorio:
                    st.warning(f"Arquivo obrigatório '{nome_arquivo}' não encontrado no ZIP.")
                return None
            with fonte.open(candidatos[0]) as f:
                content = f.read()
                try:
                    df = pd.read_csv(io.BytesIO(content), dtype=str, encoding='utf-8-sig')
                except Exception:
                    df = pd.read_csv(io.BytesIO(content), dtype=str, encoding='latin1')
        elif isinstance(fonte, str) and os.path.exists(fonte):
            caminho_direto = os.path.join(fonte, nome_arquivo)
            if not os.path.exists(caminho_direto):
                arquivos = os.listdir(fonte)
                match = [a for a in arquivos if a.lower() == nome_arquivo.lower()]
                if match:
                    caminho_direto = os.path.join(fonte, match[0])
                else:
                    if obrigatorio:
                        st.warning(f"Arquivo obrigatório '{nome_arquivo}' não encontrado no diretório: {fonte}")
                    return None
            try:
                df = pd.read_csv(caminho_direto, dtype=str, encoding='utf-8-sig')
            except Exception:
                df = pd.read_csv(caminho_direto, dtype=str, encoding='latin1')
        else:
            return None

        if df is not None:
            df.columns = [c.strip() for c in df.columns]
            for col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            return df
    except Exception as e:
        st.error(f"Erro ao processar '{nome_arquivo}': {e}")
        return None

def calcular_extensao_geodesica(lons, lats):
    """
    Calcula a extensão geodésica precisa em metros para uma sequência de coordenadas WGS84.
    """
    if len(lons) < 2:
        return 0.0
    if HAS_PYPROJ and geod_calc is not None:
        try:
            comprimento_metros = geod_calc.line_length(lons, lats)
            return float(comprimento_metros)
        except Exception:
            pass

    # Fallback para Haversine ponto a ponto em metros
    lons_rad = np.radians(lons)
    lats_rad = np.radians(lats)
    dlats = lats_rad[1:] - lats_rad[:-1]
    dlons = lons_rad[1:] - lons_rad[:-1]
    a = np.sin(dlats / 2.0)**2 + np.cos(lats_rad[:-1]) * np.cos(lats_rad[1:]) * np.sin(dlons / 2.0)**2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    total_m = np.sum(6371008.8 * c) # Raio médio da Terra em metros
    return float(total_m)

def mapear_sentido(direction_id, trip_headsign):
    """
    Mapeia o sentido da viagem (Ida, Volta, Circular) com base em direction_id e headsign.
    """
    headsign_str = str(trip_headsign).lower() if trip_headsign else ""
    if "circular" in headsign_str:
        return "Circular"
    
    dir_str = str(direction_id).strip() if direction_id is not None else ""
    if dir_str == "0":
        return "Ida"
    elif dir_str == "1":
        return "Volta"
    elif dir_str != "" and dir_str != "nan":
        return f"Sentido {dir_str}"
    return "Desconhecido"

@st.cache_data(show_spinner=False)
def carregar_e_processar_gtfs(fonte_bytes_ou_path, label_gtfs="GTFS"):
    """
    Carrega tabelas do GTFS (agency, routes, trips, shapes), calcula extensões geodésicas em metros e
    agrupa os itinerários por serviço/linha, sentido e shape_id.
    """
    if isinstance(fonte_bytes_ou_path, bytes):
        zip_obj = zipfile.ZipFile(io.BytesIO(fonte_bytes_ou_path))
        fonte = zip_obj
    else:
        fonte = fonte_bytes_ou_path

    # 1. Leitura de agency.txt
    df_agency = ler_tabela_gtfs(fonte, "agency.txt", obrigatorio=False)
    agency_map = {}
    if df_agency is not None and not df_agency.empty:
        if "agency_id" in df_agency.columns and "agency_name" in df_agency.columns:
            agency_map = dict(zip(df_agency["agency_id"], df_agency["agency_name"]))
        elif "agency_name" in df_agency.columns:
            agency_map["default"] = df_agency["agency_name"].iloc[0]

    # 2. Leitura de routes.txt
    df_routes = ler_tabela_gtfs(fonte, "routes.txt", obrigatorio=True)
    if df_routes is None or df_routes.empty:
        st.error(f"[{label_gtfs}] routes.txt está ausente ou vazio.")
        return None

    # Mapeia agência para routes
    if "agency_id" in df_routes.columns and agency_map:
        df_routes["agency_name"] = df_routes["agency_id"].map(agency_map).fillna("Não Informado")
    elif "agency_name" not in df_routes.columns:
        default_agency = agency_map.get("default", "Não Informado")
        df_routes["agency_name"] = default_agency

    # Identificador do serviço
    if "route_short_name" in df_routes.columns and df_routes["route_short_name"].str.strip().ne("").any():
        df_routes["servico"] = df_routes["route_short_name"].fillna(df_routes["route_id"])
    else:
        df_routes["servico"] = df_routes["route_id"]

    if "route_long_name" not in df_routes.columns:
        df_routes["route_long_name"] = ""

    # 3. Leitura de trips.txt
    df_trips = ler_tabela_gtfs(fonte, "trips.txt", obrigatorio=True)
    if df_trips is None or df_trips.empty:
        st.error(f"[{label_gtfs}] trips.txt está ausente ou vazio.")
        return None

    if "direction_id" not in df_trips.columns:
        df_trips["direction_id"] = "0"
    if "trip_headsign" not in df_trips.columns:
        df_trips["trip_headsign"] = ""
    if "shape_id" not in df_trips.columns:
        st.error(f"[{label_gtfs}] Coluna 'shape_id' não encontrada em trips.txt.")
        return None

    # 4. Leitura de shapes.txt
    df_shapes = ler_tabela_gtfs(fonte, "shapes.txt", obrigatorio=True)
    if df_shapes is None or df_shapes.empty:
        st.error(f"[{label_gtfs}] shapes.txt está ausente ou vazio.")
        return None

    # Validação e conversão das coordenadas de shapes
    try:
        df_shapes["shape_pt_lat"] = pd.to_numeric(df_shapes["shape_pt_lat"], errors="coerce")
        df_shapes["shape_pt_lon"] = pd.to_numeric(df_shapes["shape_pt_lon"], errors="coerce")
        df_shapes["shape_pt_sequence"] = pd.to_numeric(df_shapes["shape_pt_sequence"], errors="coerce").fillna(0).astype(int)
        df_shapes = df_shapes.dropna(subset=["shape_pt_lat", "shape_pt_lon", "shape_id"]).copy()
        df_shapes = df_shapes.sort_values(["shape_id", "shape_pt_sequence"])
    except Exception as e:
        st.error(f"[{label_gtfs}] Erro ao converter coordenadas em shapes.txt: {e}")
        return None

    # Construir geometrias e calcular extensões em metros por shape_id
    shapes_info = {}
    grouped_shapes = df_shapes.groupby("shape_id")
    for shape_id, group in grouped_shapes:
        lons = group["shape_pt_lon"].tolist()
        lats = group["shape_pt_lat"].tolist()
        if len(lons) < 2:
            continue
        coords = list(zip(lons, lats))
        extensao_m = calcular_extensao_geodesica(lons, lats)
        line_geom = LineString(coords) if HAS_SHAPELY else None
        shapes_info[str(shape_id)] = {
            "coords": coords, # [[lon, lat], ...]
            "extensao_m": round(extensao_m, 1),
            "num_pontos": len(coords),
            "geom": line_geom,
            "ponto_inicial": coords[0],
            "ponto_final": coords[-1]
        }

    # Cruzar routes com trips
    trips_com_rotas = pd.merge(
        df_trips[["route_id", "trip_id", "trip_headsign", "direction_id", "shape_id"]],
        df_routes[["route_id", "servico", "route_long_name", "agency_name"]],
        on="route_id",
        how="inner"
    )

    trips_com_rotas["shape_id"] = trips_com_rotas["shape_id"].astype(str)
    trips_com_rotas["sentido"] = trips_com_rotas.apply(
        lambda r: mapear_sentido(r["direction_id"], r["trip_headsign"]), axis=1
    )

    # Identificar frequência de cada shape_id por (serviço, sentido, headsign) para escolher o mais representativo
    resumo_trips = trips_com_rotas.groupby(
        ["servico", "sentido", "trip_headsign", "route_long_name", "agency_name", "shape_id"]
    ).size().reset_index(name="qtd_viagens")

    # Filtra shapes válidos com geometria
    resumo_trips = resumo_trips[resumo_trips["shape_id"].isin(shapes_info.keys())].copy()

    # Ordena para pegar o shape_id mais frequente por serviço + sentido como primário
    resumo_trips = resumo_trips.sort_values(
        ["servico", "sentido", "qtd_viagens"], ascending=[True, True, False]
    )

    # Atribui extensão em metros
    resumo_trips["extensao_m"] = resumo_trips["shape_id"].map(lambda sid: shapes_info[sid]["extensao_m"])

    return {
        "resumo_linhas": resumo_trips,
        "shapes_info": shapes_info,
        "raw_routes": df_routes,
        "raw_agency": df_agency
    }


# ============================================================================
# COMPARAÇÃO GEOMÉTRICA E DE EXTENSÃO ENTRE OS DOIS GTFS
# ============================================================================

def calcular_distancia_maxima_desvio(coords_a, coords_b, geom_a=None, geom_b=None):
    """
    Calcula uma estimativa da distância máxima de afastamento (em metros) entre dois traçados WGS84.
    Funciona tanto com Shapely quanto com Numpy puro.
    """
    if coords_a is None or coords_b is None or len(coords_a) < 2 or len(coords_b) < 2:
        return 999999.0

    if HAS_SHAPELY and geom_a is not None and geom_b is not None:
        try:
            h_dist_deg = geom_a.hausdorff_distance(geom_b)
            return float(h_dist_deg * 111139.0) # Aprox metros por grau
        except Exception:
            pass

    # Fallback de alta precisão em Numpy: distância máxima ponto-a-segmento
    try:
        pts_a = np.array(coords_a) # [[lon, lat], ...]
        pts_b = np.array(coords_b)

        # Amostragem para performance se o shape for muito grande
        if len(pts_a) > 200:
            idx_a = np.linspace(0, len(pts_a) - 1, 200, dtype=int)
            pts_a = pts_a[idx_a]
        if len(pts_b) > 200:
            idx_b = np.linspace(0, len(pts_b) - 1, 200, dtype=int)
            pts_b = pts_b[idx_b]

        diff_lon = pts_a[:, 0:1] - pts_b[:, 0:1].T
        diff_lat = pts_a[:, 1:2] - pts_b[:, 1:2].T
        
        mean_lat = np.radians(np.mean(pts_a[:, 1]))
        dy_m = diff_lat * 111139.0
        dx_m = diff_lon * 111139.0 * np.cos(mean_lat)
        dists_m = np.sqrt(dx_m**2 + dy_m**2)

        min_a_to_b = np.min(dists_m, axis=1)
        min_b_to_a = np.min(dists_m, axis=0)
        h_m = max(np.max(min_a_to_b), np.max(min_b_to_a))
        return float(h_m)
    except Exception:
        return 999999.0

def auditar_gtfs(dados_a, dados_b, tol_metros=25.0, tol_extensao_m=50.0):
    """
    Compara os itinerários do GTFS A (Anterior) com GTFS B (Atual).
    """
    df_a = dados_a["resumo_linhas"].copy()
    df_b = dados_b["resumo_linhas"].copy()

    shapes_a = dados_a["shapes_info"]
    shapes_b = dados_b["shapes_info"]

    chave_cols = ["servico", "sentido"]

    rep_a = df_a.groupby(chave_cols).first().reset_index()
    rep_b = df_b.groupby(chave_cols).first().reset_index()

    rep_a = rep_a.rename(columns={
        "trip_headsign": "vista_a",
        "route_long_name": "vista_completa_a",
        "agency_name": "consorcio_a",
        "shape_id": "shape_id_a",
        "extensao_m": "extensao_m_a",
        "qtd_viagens": "viagens_a"
    })

    rep_b = rep_b.rename(columns={
        "trip_headsign": "vista_b",
        "route_long_name": "vista_completa_b",
        "agency_name": "consorcio_b",
        "shape_id": "shape_id_b",
        "extensao_m": "extensao_m_b",
        "qtd_viagens": "viagens_b"
    })

    comp = pd.merge(rep_a, rep_b, on=chave_cols, how="outer", indicator=True)

    status_list = []
    dif_m_list = []
    var_pct_list = []
    desvio_m_list = []
    consorcio_final = []
    vista_final = []

    for _, row in comp.iterrows():
        merge_type = row["_merge"]
        sid_a = str(row["shape_id_a"]) if pd.notna(row["shape_id_a"]) else None
        sid_b = str(row["shape_id_b"]) if pd.notna(row["shape_id_b"]) else None
        
        ext_a = row["extensao_m_a"] if pd.notna(row["extensao_m_a"]) else 0.0
        ext_b = row["extensao_m_b"] if pd.notna(row["extensao_m_b"]) else 0.0
        
        c_a = row["consorcio_a"] if pd.notna(row["consorcio_a"]) else ""
        c_b = row["consorcio_b"] if pd.notna(row["consorcio_b"]) else ""
        consorcio_final.append(c_b if c_b else c_a)

        v_a = row["vista_b"] if pd.notna(row["vista_b"]) and row["vista_b"] != "" else row.get("vista_a", "")
        vista_final.append(v_a if pd.notna(v_a) else "")

        if merge_type == "left_only":
            status_list.append("Excluída (Apenas no GTFS Anterior)")
            dif_m_list.append(-ext_a)
            var_pct_list.append(-100.0)
            desvio_m_list.append(np.nan)
        elif merge_type == "right_only":
            status_list.append("Nova Linha/Itinerário (Apenas no GTFS Atual)")
            dif_m_list.append(ext_b)
            var_pct_list.append(100.0)
            desvio_m_list.append(np.nan)
        else:
            dif_m = round(ext_b - ext_a, 1)
            dif_m_list.append(dif_m)
            var_pct = round(((ext_b - ext_a) / ext_a * 100.0), 2) if ext_a > 0 else 0.0
            var_pct_list.append(var_pct)

            c_a_pts = shapes_a.get(sid_a, {}).get("coords", []) if sid_a else []
            c_b_pts = shapes_b.get(sid_b, {}).get("coords", []) if sid_b else []
            g_a = shapes_a.get(sid_a, {}).get("geom") if sid_a else None
            g_b = shapes_b.get(sid_b, {}).get("geom") if sid_b else None

            if sid_a == sid_b and c_a_pts == c_b_pts:
                status_list.append("Traçado Idêntico")
                desvio_m_list.append(0.0)
            elif c_a_pts and c_b_pts:
                desvio_metros = calcular_distancia_maxima_desvio(c_a_pts, c_b_pts, g_a, g_b)
                desvio_m_list.append(round(desvio_metros, 1))

                dif_extensao_metros = abs(ext_b - ext_a)

                if desvio_metros <= tol_metros and dif_extensao_metros <= tol_extensao_m:
                    status_list.append("Traçado Sem Alteração Significativa")
                else:
                    status_list.append("Traçado Modificado")
            else:
                status_list.append("Sem Geometria Comparável")
                desvio_m_list.append(np.nan)

    comp["Consórcio"] = consorcio_final
    comp["Vista"] = vista_final
    comp["Status"] = status_list
    comp["Diferença Extensão (m)"] = dif_m_list
    comp["Variação (%)"] = var_pct_list
    comp["Desvio Máximo Aprox (m)"] = desvio_m_list

    comp = comp.rename(columns={
        "servico": "Serviço",
        "sentido": "Sentido",
        "extensao_m_a": "Extensão Anterior (m)",
        "extensao_m_b": "Extensão Atual (m)",
        "shape_id_a": "Shape Anterior",
        "shape_id_b": "Shape Atual"
    })

    colunas_finais = [
        "Serviço", "Vista", "Consórcio", "Sentido", "Status",
        "Extensão Anterior (m)", "Extensão Atual (m)", "Diferença Extensão (m)", "Variação (%)",
        "Desvio Máximo Aprox (m)", "Shape Anterior", "Shape Atual"
    ]
    comp = comp[[c for c in colunas_finais if c in comp.columns]].sort_values(
        by=["Status", "Serviço", "Sentido"]
    )

    return comp


# ============================================================================
# RENDERIZAÇÃO DO MAPA INTERATIVO (PYDECK)
# ============================================================================

def gerar_mapa_comparativo(coords_a, coords_b, servico, sentido, info_a, info_b):
    """
    Renderiza mapa interativo PyDeck sobrepondo traçado anterior (vermelho) e atual (azul/ciano).
    """
    layers = []
    all_lons = []
    all_lats = []

    # Camada do Traçado Anterior (GTFS A)
    if coords_a and len(coords_a) > 1:
        for lon, lat in coords_a:
            all_lons.append(lon)
            all_lats.append(lat)
        path_a_data = [{
            "path": coords_a,
            "name": f"GTFS Anterior (Shape {info_a.get('shape_id', '')})",
            "extensao": fmt_br(info_a.get('extensao_m', 0), 1, False, "m")
        }]
        layer_a = pdk.Layer(
            "PathLayer",
            data=path_a_data,
            get_path="path",
            get_color=[255, 87, 87, 220], # Vermelho / Coral Neon (Base)
            width_scale=20,
            width_min_pixels=3,
            get_width=3,
            pickable=True,
            auto_highlight=True
        )
        layers.append(layer_a)

    # Camada do Traçado Atual (GTFS B)
    if coords_b and len(coords_b) > 1:
        for lon, lat in coords_b:
            all_lons.append(lon)
            all_lats.append(lat)
        path_b_data = [{
            "path": coords_b,
            "name": f"GTFS Atual (Shape {info_b.get('shape_id', '')})",
            "extensao": fmt_br(info_b.get('extensao_m', 0), 1, False, "m")
        }]
        layer_b = pdk.Layer(
            "PathLayer",
            data=path_b_data,
            get_path="path",
            get_color=[0, 210, 255, 240], # Ciano / Azul Neon (Mais Fino no Topo)
            width_scale=20,
            width_min_pixels=1.25,
            get_width=1.25,
            pickable=True,
            auto_highlight=True
        )
        layers.append(layer_b)

    # Marcadores de Início e Fim
    pontos_extremos = []
    if coords_a and len(coords_a) > 0:
        pontos_extremos.append({
            "coord": coords_a[0],
            "tipo": "Início (GTFS Anterior)",
            "cor": [255, 107, 107, 255]
        })
        pontos_extremos.append({
            "coord": coords_a[-1],
            "tipo": "Fim (GTFS Anterior)",
            "cor": [220, 53, 69, 255]
        })
    if coords_b and len(coords_b) > 0:
        pontos_extremos.append({
            "coord": coords_b[0],
            "tipo": "Início (GTFS Atual)",
            "cor": [0, 230, 150, 255]
        })
        pontos_extremos.append({
            "coord": coords_b[-1],
            "tipo": "Fim (GTFS Atual)",
            "cor": [0, 180, 255, 255]
        })

    if pontos_extremos:
        layer_pontos = pdk.Layer(
            "ScatterplotLayer",
            data=pontos_extremos,
            get_position="coord",
            get_color="cor",
            get_radius=35,
            radius_min_pixels=6,
            radius_max_pixels=14,
            pickable=True
        )
        layers.append(layer_pontos)

    # View State
    if all_lons and all_lats:
        center_lon = float(np.mean(all_lons))
        center_lat = float(np.mean(all_lats))
        zoom_level = 12
    else:
        center_lon, center_lat, zoom_level = -43.2096, -22.9035, 11

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom_level,
        pitch=0,
        bearing=0
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="dark",
        tooltip={"html": "<b>{name}</b><br/>Extensão: {extensao}"}
    )
    return deck


# ============================================================================
# INTERFACE STREAMLIT
# ============================================================================

st.title("🗺️ Auditoria de Desenho e Extensão de GTFS")
st.markdown(
    "Ferramenta para identificação visual e quantitativa de diferenças de traçados (`shapes.txt`), "
    "extensões por serviço/sentido e agências (`agency.txt`) entre dois feeds GTFS."
)

# Sidebar para configurações e upload
st.sidebar.header("📁 Fontes de Dados GTFS")

modo_entrada = st.sidebar.radio(
    "Modo de Carregamento:",
    ["Upload de Arquivos .ZIP", "Caminho de Diretório Local"],
    index=0
)

gtfs_a_input = None
gtfs_b_input = None

if modo_entrada == "Upload de Arquivos .ZIP":
    file_a = st.sidebar.file_uploader("GTFS 1: Quinzena ANTERIOR / Referência (.zip)", type=["zip"], key="zip_a")
    file_b = st.sidebar.file_uploader("GTFS 2: Quinzena ATUAL / Novo (.zip)", type=["zip"], key="zip_b")
    if file_a is not None:
        gtfs_a_input = file_a.getvalue()
    if file_b is not None:
        gtfs_b_input = file_b.getvalue()
else:
    path_a = st.sidebar.text_input("Diretório GTFS ANTERIOR / Referência:", "")
    path_b = st.sidebar.text_input("Diretório GTFS ATUAL / Novo:", "")
    if path_a and os.path.exists(path_a):
        gtfs_a_input = path_a
    if path_b and os.path.exists(path_b):
        gtfs_b_input = path_b

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Parâmetros de Auditoria")
tolerancia_metros = st.sidebar.slider(
    "Tolerância de Desvio Geométrico (metros):",
    min_value=5,
    max_value=150,
    value=25,
    step=5,
    help="Distância máxima de afastamento entre pontos para considerar o desenho idêntico/sem alteração significativa."
)

tolerancia_extensao = st.sidebar.slider(
    "Tolerância de Extensão (metros):",
    min_value=10,
    max_value=200,
    value=50,
    step=10,
    help="Diferença de comprimento para alertar alteração de extensão."
)

executar_btn = st.sidebar.button("🚀 Executar Auditoria GTFS", type="primary")

if (executar_btn or "resultado_auditoria" in st.session_state) and gtfs_a_input and gtfs_b_input:
    if executar_btn:
        with st.spinner("Carregando e processando GTFS Anterior..."):
            dados_a = carregar_e_processar_gtfs(gtfs_a_input, label_gtfs="GTFS Anterior")
        with st.spinner("Carregando e processando GTFS Atual..."):
            dados_b = carregar_e_processar_gtfs(gtfs_b_input, label_gtfs="GTFS Atual")

        if dados_a is not None and dados_b is not None:
            with st.spinner("Comparando traçados e calculando extensões geodésicas..."):
                tabela_comp = auditar_gtfs(dados_a, dados_b, tol_metros=tolerancia_metros, tol_extensao_m=tolerancia_extensao)
                st.session_state["dados_a"] = dados_a
                st.session_state["dados_b"] = dados_b
                st.session_state["resultado_auditoria"] = tabela_comp
        else:
            st.error("Não foi possível processar um ou ambos os feeds GTFS. Verifique se os arquivos obrigatórios estão presentes.")
            st.stop()

    dados_a = st.session_state.get("dados_a")
    dados_b = st.session_state.get("dados_b")
    resultado = st.session_state.get("resultado_auditoria")

    if resultado is not None and not resultado.empty:
        # ====================================================================
        # CARDS DE RESUMO (KPIs)
        # ====================================================================
        total_itinerarios = len(resultado)
        modificados = len(resultado[resultado["Status"] == "Traçado Modificado"])
        identicos = len(resultado[resultado["Status"].str.contains("Idêntico|Sem Alteração", case=False)])
        novos = len(resultado[resultado["Status"].str.contains("Nova Linha", case=False)])
        excluidos = len(resultado[resultado["Status"].str.contains("Excluída", case=False)])

        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total de Itinerários", total_itinerarios)
        kpi2.metric("Traçados Modificados ⚠️", modificados, delta=f"{(modificados/total_itinerarios*100):.1f}%".replace(".", ",") if total_itinerarios > 0 else "0%")
        kpi3.metric("Sem Alteração de Traçado ✅", identicos)
        kpi4.metric("Novos Itinerários 🆕", novos)
        kpi5.metric("Itinerários Excluídos ❌", excluidos)

        st.markdown("---")

        # ====================================================================
        # SELEÇÃO E VISUALIZAÇÃO NO MAPA
        # ====================================================================
        st.subheader("📍 Comparador Visual de Traçados no Mapa")

        col_filtro1, col_filtro2, col_filtro3 = st.columns([2, 1, 1])
        with col_filtro1:
            servicos_disponiveis = sorted(resultado["Serviço"].unique().tolist())
            servico_selecionado = st.selectbox(
                "Selecione o Serviço / Linha:",
                options=servicos_disponiveis,
                index=0
            )

        subset_servico = resultado[resultado["Serviço"] == servico_selecionado]
        sentidos_disponiveis = subset_servico["Sentido"].unique().tolist()

        with col_filtro2:
            sentido_selecionado = st.selectbox(
                "Selecione o Sentido:",
                options=sentidos_disponiveis,
                index=0
            )

        linha_info = subset_servico[subset_servico["Sentido"] == sentido_selecionado].iloc[0]

        with col_filtro3:
            status_cor = "orange" if "Modificado" in linha_info["Status"] else ("green" if "Idêntico" in linha_info["Status"] else "blue")
            st.markdown(f"**Status do Desenho:**")
            st.markdown(f":{status_cor}[**{linha_info['Status']}**]")

        # Detalhes da Linha Selecionada
        card_col1, card_col2, card_col3, card_col4, card_col5 = st.columns(5)
        ext_ant = linha_info.get("Extensão Anterior (m)", 0.0)
        ext_atu = linha_info.get("Extensão Atual (m)", 0.0)
        dif_ext = linha_info.get("Diferença Extensão (m)", 0.0)
        var_pct = linha_info.get("Variação (%)", 0.0)
        desvio_m = linha_info.get("Desvio Máximo Aprox (m)", np.nan)

        card_col1.metric("Extensão GTFS Anterior", fmt_br(ext_ant, 1, False, "m") if pd.notna(ext_ant) and ext_ant > 0 else "N/D")
        card_col2.metric("Extensão GTFS Atual", fmt_br(ext_atu, 1, False, "m") if pd.notna(ext_atu) and ext_atu > 0 else "N/D")
        card_col3.metric("Diferença de Extensão", fmt_br(dif_ext, 1, True, "m"), delta=fmt_br(var_pct, 2, True, "%"))
        card_col4.metric("Desvio Máx. Estimado", fmt_br(desvio_m, 1, False, "m") if pd.notna(desvio_m) else "N/D")
        card_col5.metric("Consórcio / Agência", str(linha_info.get("Consórcio", "N/D")))

        # Obter geometrias para o mapa
        shape_a_id = str(linha_info.get("Shape Anterior", ""))
        shape_b_id = str(linha_info.get("Shape Atual", ""))

        shape_a_dict = dados_a["shapes_info"].get(shape_a_id, {})
        shape_b_dict = dados_b["shapes_info"].get(shape_b_id, {})

        coords_a = shape_a_dict.get("coords", [])
        coords_b = shape_b_dict.get("coords", [])

        # Legenda Visual do Mapa (Estilo Dark / Neon)
        st.markdown(
            f"""
            <div style="display: flex; gap: 24px; align-items: center; margin-bottom: 10px; background: rgba(25, 28, 36, 0.9); padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.12); width: fit-content;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 20px; height: 6px; background-color: #FF5757; border-radius: 3px; box-shadow: 0 0 6px #FF5757;"></span>
                    <span style="font-size: 13.5px; font-weight: 600; color: #FAFAFA;">GTFS Anterior (Shape: {shape_a_id})</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 20px; height: 6px; background-color: #00D2FF; border-radius: 3px; box-shadow: 0 0 6px #00D2FF;"></span>
                    <span style="font-size: 13.5px; font-weight: 600; color: #FAFAFA;">GTFS Atual (Shape: {shape_b_id})</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        deck_mapa = gerar_mapa_comparativo(
            coords_a, coords_b,
            servico_selecionado, sentido_selecionado,
            {"shape_id": shape_a_id, "extensao_m": ext_ant},
            {"shape_id": shape_b_id, "extensao_m": ext_atu}
        )
        st.pydeck_chart(deck_mapa, use_container_width=True)

        st.markdown("---")

        # ====================================================================
        # TABELA DE AUDITORIA E RELATÓRIO
        # ====================================================================
        st.subheader("📋 Tabela Completa de Auditoria de Traçados e Extensões")

        filtro_status = st.multiselect(
            "Filtrar por Status:",
            options=sorted(resultado["Status"].unique().tolist()),
            default=sorted(resultado["Status"].unique().tolist())
        )

        filtro_consorcio = st.multiselect(
            "Filtrar por Consórcio / Agência:",
            options=sorted(resultado["Consórcio"].dropna().unique().tolist()),
            default=sorted(resultado["Consórcio"].dropna().unique().tolist())
        )

        resultado_filtrado = resultado[
            (resultado["Status"].isin(filtro_status)) &
            (resultado["Consórcio"].isin(filtro_consorcio))
        ].copy()

        # Criar versão formatada no padrão PT-BR para exibição
        resultado_display = resultado_filtrado.copy()
        resultado_display["Extensão Anterior (m)"] = resultado_display["Extensão Anterior (m)"].apply(lambda x: fmt_br(x, 1, False, "") if pd.notna(x) and x > 0 else "-")
        resultado_display["Extensão Atual (m)"] = resultado_display["Extensão Atual (m)"].apply(lambda x: fmt_br(x, 1, False, "") if pd.notna(x) and x > 0 else "-")
        resultado_display["Diferença Extensão (m)"] = resultado_display["Diferença Extensão (m)"].apply(lambda x: fmt_br(x, 1, True, "") if pd.notna(x) else "-")
        resultado_display["Variação (%)"] = resultado_display["Variação (%)"].apply(lambda x: fmt_br(x, 2, True, "%") if pd.notna(x) else "-")
        resultado_display["Desvio Máximo Aprox (m)"] = resultado_display["Desvio Máximo Aprox (m)"].apply(lambda x: fmt_br(x, 1, False, "") if pd.notna(x) else "-")

        st.dataframe(
            resultado_display,
            use_container_width=True,
            hide_index=True
        )

        # Download do Relatório (CSV formatado para Excel em português: sep=';', dec=',')
        csv_buffer = io.StringIO()
        resultado.to_csv(csv_buffer, sep=";", decimal=",", index=False, encoding="utf-8-sig")

        st.sidebar.markdown("---")
        st.sidebar.download_button(
            label="📥 Baixar Tabela de Auditoria (CSV)",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=f"Auditoria_GTFS_Diferencas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
else:
    st.info("👈 Por favor, carregue os dois arquivos GTFS (.zip ou diretórios) na barra lateral e clique em **Executar Auditoria GTFS**.")
