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

@st.cache_data
def carregar_e_processar_dados():
    """
    Função unificada que executa o web scraping (com paginação) e a geocodificação.
    """
    # --- Parte 1: Web Scraping com Lógica de Paginação ---
    st.write("Iniciando coleta de dados via web scraping...")
    
    # URL inicial (página 1)
    url_base = "https://ampa.com.br/consulta-associados-ativos/"
    url_atual = url_base
    lista_empresas = []
    pagina_num = 1

    # Loop para percorrer todas as páginas
    while url_atual:
        st.write(f"Coletando dados da página {pagina_num}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
            response = requests.get(url_atual, headers=headers, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            
            # ATUALIZAÇÃO: O seletor correto para cada associado no novo site
            itens_empresas = soup.find_all('div', class_='associado-item')
            
            if not itens_empresas and pagina_num == 1:
                st.error("Falha no Web Scraping: Não foi possível encontrar a lista de empresas no site com o seletor atual. A estrutura pode ter mudado.")
                return pd.DataFrame()

            for item in itens_empresas:
                # Extrai o nome da empresa
                nome_tag = item.find('h3')
                nome = nome_tag.text.strip() if nome_tag else None
                
                # Extrai a cidade e telefone (estão juntos no mesmo <p>)
                info_tag = item.find('p')
                info_texto = info_tag.text.strip() if info_tag else ""
                
                # Separa a cidade do resto da informação
                partes = info_texto.split('–')
                cidade = partes[0].strip() if partes else ""

                if nome:
                    lista_empresas.append({
                        'Nome': nome,
                        'Tipo': 'Algodoeira',
                        'Cidade': cidade,
                        'Estado': 'MT' # Assumimos MT pois é o site da AMPA
                    })
            
            # Procura pelo link da PRÓXIMA página
            link_proxima_pagina = soup.find('a', class_='next')
            
            if link_proxima_pagina and 'href' in link_proxima_pagina.attrs:
                url_atual = link_proxima_pagina['href']
                pagina_num += 1
                time.sleep(1) # Pequena pausa para ser gentil com o servidor
            else:
                url_atual = None # Fim das páginas, encerra o loop

        except requests.exceptions.RequestException as e:
            st.error(f"Erro de conexão na página {pagina_num}: {e}")
            url_atual = None # Encerra o loop em caso de erro

    if not lista_empresas:
        st.error("Nenhuma empresa foi coletada. Verifique os seletores do scraping.")
        return pd.DataFrame()
        
    df = pd.DataFrame(lista_empresas)
    st.write(f"Coleta concluída: {len(df)} empresas encontradas em {pagina_num-1} páginas.")

    # --- Parte 2: Geocodificação ---
    st.write("Iniciando geocodificação (buscando coordenadas). Isso pode demorar...")
    geolocator = Nominatim(user_agent="app_agro_streamlit")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

    latitudes = []
    longitudes = []
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
        
        progress_bar.progress((index + 1) / total_empresas, text=f"Processando: {row['Nome']}")

    df['Latitude'] = latitudes
    df['Longitude'] = longitudes
    df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
    st.write("Geocodificação finalizada.")
    
    return df

# ==============================================================================
# PASSO 2: INTERFACE DO APLICATIVO STREAMLIT (Sem alterações)
# ==============================================================================

st.set_page_config(page_title="Mapa do Agronegócio Brasileiro", layout="wide")
st.title("🗺️ Mapa Interativo do Agronegócio no Brasil")
st.markdown("Os dados são coletados e processados em tempo real. Filtre por tipo na barra lateral.")

with st.spinner('Por favor, aguarde... Coletando e processando dados de todas as páginas...'):
    df_empresas = carregar_e_processar_dados()

if df_empresas.empty:
    st.error("Não foi possível carregar os dados. Tente recarregar a página.")
else:
    st.success(f"Processo concluído! {len(df_empresas)} empresas foram localizadas e mapeadas.")
    
    st.sidebar.header("Filtros")
    tipos_disponiveis = ["Exibir Todas"] + sorted(df_empresas['Tipo'].unique().tolist())
    tipo_selecionado = st.sidebar.selectbox("Selecione o Tipo de Empresa:", tipos_disponiveis)

    if tipo_selecionado == "Exibir Todas":
        df_filtrado = df_empresas
    else:
        df_filtrado = df_empresas[df_empresas['Tipo'] == tipo_selecionado]

    if df_filtrado.empty:
        st.warning("Nenhuma empresa encontrada para o tipo selecionado.")
    else:
        st.subheader(f"Exibindo {len(df_filtrado)} empresa(s) do tipo '{tipo_selecionado}'")
        st.dataframe(df_filtrado[['Nome', 'Cidade', 'Estado']])
        
        st.subheader("Mapa de Localizações")
        map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        mapa = folium.Map(location=map_center, zoom_start=7)

        for index, empresa in df_filtrado.iterrows():
            popup_html = f"<b>{empresa.get('Nome', 'N/A')}</b><br><hr><b>Cidade:</b> {empresa.get('Cidade', 'N/A')} - {empresa.get('Estado', 'N/A')}"
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa.get('Nome', 'N/A')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
