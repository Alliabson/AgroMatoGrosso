import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import folium

# --- NOME DO ARQUIVO DE DADOS ---
# Nenhuma alteração necessária aqui. O app continua lendo o mesmo arquivo final.
ARQUIVO_DE_DADOS = "empresas_com_coords.csv"

# ==============================================================================
# PASSO 1: CARREGAR A BASE DE DADOS
# ==============================================================================
@st.cache_data
def carregar_dados(caminho_arquivo):
    """
    Lê os dados de um arquivo CSV e retorna um DataFrame do Pandas.
    """
    try:
        df = pd.read_csv(caminho_arquivo)
        # Remove linhas onde a Latitude ou Longitude não foram encontradas
        df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
        return df
    except FileNotFoundError:
        # Retorna um DataFrame vazio se o arquivo não existir
        return pd.DataFrame()

# ==============================================================================
# PASSO 2: CONFIGURAÇÃO DA INTERFACE DO APLICATIVO
# ==============================================================================
st.set_page_config(page_title="Mapa do Agronegócio Brasileiro", layout="wide")
st.title("🗺️ Mapa Interativo do Agronegócio no Brasil")
st.markdown("Filtre as empresas por tipo na barra lateral para visualizá-las no mapa.")

# Carrega os dados usando a função
df_empresas = carregar_dados(ARQUIVO_DE_DADOS)

# ==============================================================================
# PASSO 3: LÓGICA PRINCIPAL E EXIBIÇÃO
# ==============================================================================
if df_empresas.empty:
    st.error(f"Arquivo de dados '{ARQUIVO_DE_DADOS}' não encontrado ou vazio.")
    st.info("Por favor, execute o script 'coletor_dados.py' e depois 'geocodificar.py' para gerar o arquivo com as coordenadas.")
else:
    # --- FILTRO NA BARRA LATERAL ---
    st.sidebar.header("Filtros")
    tipos_disponiveis = ["Exibir Todas"] + sorted(df_empresas['Tipo'].unique().tolist())
    tipo_selecionado = st.sidebar.selectbox("Selecione o Tipo de Empresa:", tipos_disponiveis)

    # --- LÓGICA DE FILTRAGEM ---
    if tipo_selecionado == "Exibir Todas":
        df_filtrado = df_empresas
    else:
        df_filtrado = df_empresas[df_empresas['Tipo'] == tipo_selecionado]

    # --- EXIBIÇÃO DOS RESULTADOS ---
    if df_filtrado.empty:
        st.warning("Nenhuma empresa encontrada para o tipo selecionado.")
    else:
        st.subheader(f"Exibindo {len(df_filtrado)} empresa(s) do tipo '{tipo_selecionado}'")
        st.dataframe(df_filtrado[['Nome', 'Cidade', 'Estado', 'Endereço']])
        
        st.subheader("Mapa de Localizações")
        map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        mapa = folium.Map(location=map_center, zoom_start=5) # Zoom 5 para uma visão mais ampla do Brasil

        for index, empresa in df_filtrado.iterrows():
            popup_html = f"""
            <b>{empresa.get('Nome', 'N/A')}</b><br><hr>
            <b>Endereço:</b> {empresa.get('Endereço', 'N/A')}<br>
            <b>Cidade:</b> {empresa.get('Cidade', 'N/A')} - {empresa.get('Estado', 'N/A')}<br>
            <b>Tipo:</b> {empresa.get('Tipo', 'N/A')}
            """
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa.get('Nome', 'N/A')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
