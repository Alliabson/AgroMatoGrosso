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
# FUNÇÕES AUXILIARES
# ==============================================================================

def is_pessoa_juridica(nome):
    """
    Verifica se um nome provavelmente pertence a uma empresa.
    Esta é a nossa função "funil".
    """
    # Lista de palavras-chave que indicam ser uma empresa. Você pode adicionar mais!
    keywords = ['ltda', 's.a', 's/a', 'agropecuária', 'agrícola', 
                'fazenda', 'grupo', 'agro', 'produtos', 'investimentos']
    
    nome_lower = nome.lower()
    for keyword in keywords:
        if keyword in nome_lower:
            return True
    return False

# ==============================================================================
# FUNÇÃO MESTRA PARA COLETAR E PROCESSAR OS DADOS
# ==============================================================================

@st.cache_data
def carregar_e_processar_dados():
    """
    Função unificada que executa o web scraping de tabelas (com paginação) 
    e a geocodificação, filtrando apenas por pessoas jurídicas.
    """
    # --- Parte 1: Web Scraping de Tabela com Paginação ---
    st.write("Iniciando coleta de dados via web scraping...")
    
    url_base = "https://ampa.com.br/consulta-associados-ativos/"
    url_atual = url_base
    lista_empresas = []
    pagina_num = 1

    while url_atual:
        st.write(f"Coletando dados da página {pagina_num}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
            response = requests.get(url_atual, headers=headers, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            
            # ATUALIZAÇÃO CRÍTICA: Encontra a tabela no HTML
            tabela = soup.find('table')
            
            if not tabela:
                if pagina_num == 1:
                    st.error("Falha no Web Scraping: Não foi possível encontrar a <table> na página.")
                break # Sai do loop se não encontrar a tabela

            # Itera sobre todas as linhas <tr> da tabela, pulando o cabeçalho ([1:])
            for linha in tabela.find_all('tr')[1:]:
                celulas = linha.find_all('td')
                if len(celulas) == 2: # Garante que a linha tem as duas colunas
                    nome = celulas[0].text.strip()
                    telefone = celulas[1].text.strip()

                    # APLICA O FUNIL: Processa apenas se for uma pessoa jurídica
                    if is_pessoa_juridica(nome):
                        lista_empresas.append({
                            'Nome': nome,
                            'Telefone': telefone,
                            'Tipo': 'Algodoeira',
                            'Cidade': 'Não Informada', # O novo layout não informa a cidade
                            'Estado': 'MT'
                        })
            
            link_proxima_pagina = soup.find('a', class_='next')
            if link_proxima_pagina and 'href' in link_proxima_pagina.attrs:
                url_atual = link_proxima_pagina['href']
                pagina_num += 1
                time.sleep(1)
            else:
                url_atual = None

        except requests.exceptions.RequestException as e:
            st.error(f"Erro de conexão na página {pagina_num}: {e}")
            url_atual = None

    if not lista_empresas:
        st.error("Nenhuma empresa (Pessoa Jurídica) foi coletada. Verifique os seletores e a função de filtro.")
        return pd.DataFrame()
        
    df = pd.DataFrame(lista_empresas)
    st.write(f"Coleta concluída: {len(df)} empresas (PJs) encontradas em {pagina_num-1} páginas.")

    # --- Parte 2: Geocodificação ---
    st.write("Iniciando geocodificação. Este processo pode ser lento...")
    geolocator = Nominatim(user_agent="app_agro_streamlit")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

    latitudes = []
    longitudes = []
    cidades_encontradas = []
    progress_bar = st.progress(0)
    total_empresas = len(df)

    for index, row in df.iterrows():
        # Buscamos por "Nome da Empresa, Mato Grosso", já que não temos mais a cidade
        query = f"{row['Nome']}, Mato Grosso, Brasil"
        location = None
        try:
            location = geocode(query)
        except Exception as e:
            st.warning(f"Erro ao buscar coordenadas para {row['Nome']}: {e}")

        if location and location.raw.get('address'):
            latitudes.append(location.latitude)
            longitudes.append(location.longitude)
            # Tenta extrair a cidade do resultado da geocodificação
            address = location.raw['address']
            cidade = address.get('city') or address.get('town') or address.get('village') or "Cidade Desconhecida"
            cidades_encontradas.append(cidade)
        else:
            latitudes.append(None)
            longitudes.append(None)
            cidades_encontradas.append("Não Localizada")
        
        progress_bar.progress((index + 1) / total_empresas, text=f"Processando: {row['Nome']}")

    df['Latitude'] = latitudes
    df['Longitude'] = longitudes
    df['Cidade'] = cidades_encontradas # Atualiza a coluna de cidade com o que foi encontrado
    df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
    st.write("Geocodificação finalizada.")
    
    return df

# ==============================================================================
# INTERFACE DO APLICATIVO STREAMLIT (Sem alterações na lógica principal)
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
        # ATUALIZAÇÃO: Adicionamos a coluna Telefone e a nova Cidade na tabela
        st.dataframe(df_filtrado[['Nome', 'Telefone', 'Cidade', 'Estado']])
        
        st.subheader("Mapa de Localizações")
        map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        mapa = folium.Map(location=map_center, zoom_start=7)

        for index, empresa in df_filtrado.iterrows():
            popup_html = f"<b>{empresa.get('Nome', 'N/A')}</b><br><hr><b>Cidade:</b> {empresa.get('Cidade', 'N/A')}<br><b>Telefone:</b> {empresa.get('Telefone', 'N/A')}"
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa.get('Nome', 'N/A')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
