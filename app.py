import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import folium
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

# ==============================================================================
# PASSO 1: FUNÇÃO MESTRA PARA COLETAR E PROCESSAR OS DADOS
# ==============================================================================

# O @st.cache_data é a parte mais importante. Ele armazena o resultado desta função.
# Isso significa que o web scraping e a geocodificação (processos lentos)
# só serão executados UMA VEZ. Nas próximas interações, o Streamlit usará os dados em cache.
@st.cache_data
def carregar_e_processar_dados():
    """
    Função unificada que executa o web scraping e a geocodificação.
    Retorna um DataFrame final com todas as informações e coordenadas.
    """
    # --- Parte 1: Web Scraping (lógica do 'coletor_dados.py') ---
    st.write("Iniciando coleta de dados via web scraping...")
    URL_ALVO = "https://ampa.com.br/associados/" 
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(URL_ALVO, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        
        itens_empresas = soup.find_all('div', class_='dados')
        
        if not itens_empresas:
            st.error("Falha no Web Scraping: Não foi possível encontrar a lista de empresas no site. A estrutura pode ter mudado.")
            return pd.DataFrame() # Retorna um DataFrame vazio se a coleta falhar

        lista_empresas = []
        for item in itens_empresas:
            nome_tag = item.find('h2', class_='title')
            nome = nome_tag.text.strip() if nome_tag else None
            cidade_tag = item.find('p')
            local_info = cidade_tag.text.strip() if cidade_tag else ""
            cidade = local_info.split('-')[0].strip()
            
            if nome: # Adiciona apenas se encontrou um nome
                lista_empresas.append({
                    'Nome': nome,
                    'Tipo': 'Algodoeira',
                    'Cidade': cidade,
                    'Estado': 'MT'
                })
        
        df = pd.DataFrame(lista_empresas)
        st.write(f"Coleta concluída: {len(df)} empresas encontradas.")

    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão durante o web scraping: {e}")
        return pd.DataFrame()

    # --- Parte 2: Geocodificação (lógica do 'geocodificar.py') ---
    st.write("Iniciando geocodificação (buscando coordenadas). Isso pode demorar...")
    
    geolocator = Nominatim(user_agent="app_agro_streamlit")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

    latitudes = []
    longitudes = []
    
    # Barra de progresso para a geocodificação
    progress_bar = st.progress(0)
    total_empresas = len(df)

    for index, row in df.iterrows():
        endereco_completo = f"{row['Nome']}, {row['Cidade']}, {row['Estado']}, Brasil"
        location = None
        try:
            location = geocode(endereco_completo)
        except Exception as e:
            st.warning(f"Erro ao buscar coordenadas para {row['Nome']}: {e}")

        if location:
            latitudes.append(location.latitude)
            longitudes.append(location.longitude)
        else:
            latitudes.append(None)
            longitudes.append(None)
        
        # Atualiza a barra de progresso
        progress_bar.progress((index + 1) / total_empresas, text=f"Processando: {row['Nome']}")

    df['Latitude'] = latitudes
    df['Longitude'] = longitudes
    df.dropna(subset=['Latitude', 'Longitude'], inplace=True) # Remove empresas não encontradas no mapa
    st.write("Geocodificação finalizada.")
    
    return df

# ==============================================================================
# PASSO 2: INTERFACE DO APLICATIVO STREAMLIT
# ==============================================================================

st.set_page_config(page_title="Mapa do Agronegócio Brasileiro", layout="wide")
st.title("🗺️ Mapa Interativo do Agronegócio no Brasil")
st.markdown("Os dados são coletados e processados em tempo real. Filtre por tipo na barra lateral.")

# --- Lógica Principal ---
# Mostra uma mensagem de carregamento enquanto a função demorada é executada
with st.spinner('Por favor, aguarde... Coletando e processando dados de toda a base...'):
    df_empresas = carregar_e_processar_dados()

if df_empresas.empty:
    st.error("Não foi possível carregar os dados. Tente recarregar a página.")
else:
    st.success(f"Processo concluído! {len(df_empresas)} empresas foram localizadas e mapeadas.")
    
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
        st.dataframe(df_filtrado[['Nome', 'Cidade', 'Estado']])
        
        st.subheader("Mapa de Localizações")
        map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        mapa = folium.Map(location=map_center, zoom_start=7)

        for index, empresa in df_filtrado.iterrows():
            popup_html = f"""
            <b>{empresa.get('Nome', 'N/A')}</b><br><hr>
            <b>Cidade:</b> {empresa.get('Cidade', 'N/A')} - {empresa.get('Estado', 'N/A')}
            """
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa.get('Nome', 'N/A')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
