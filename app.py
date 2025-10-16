import streamlit as st
from streamlit_folium import st_folium
import requests
import pandas as pd
import folium
import json

# --- CONFIGURAÇÕES E FUNÇÃO DE BUSCA (sem alterações) ---

# Endpoint da API Overpass
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tags do OpenStreetMap para a busca
TAGS_DE_BUSCA = {
    '"industrial"': '"textile"',
    '"product"': '"cotton"'
}

# Usamos o @st.cache_data para que o Streamlit armazene os resultados da busca.
# Se o usuário buscar pela mesma cidade de novo, o resultado é instantâneo.
@st.cache_data
def buscar_empresas_osm(cidade):
    """
    Busca por locais em uma cidade usando a Overpass API do OpenStreetMap.
    """
    
    query_parts = ""
    for key, value in TAGS_DE_BUSCA.items():
        query_parts += f"""
        node[{key}={value}](area.searchArea);
        way[{key}={value}](area.searchArea);
        relation[{key}={value}](area.searchArea);
        """

    overpass_query = f"""
    [out:json];
    area[name="{cidade}"]->.searchArea;
    (
      {query_parts}
    );
    out center;
    """
    
    try:
        response = requests.get(OVERPASS_URL, params={'data': overpass_query})
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        # Em vez de imprimir no console, retornamos o erro para a interface
        st.error(f"Erro de conexão com a API: {e}")
        return pd.DataFrame()
    except json.JSONDecodeError:
        st.error(f"Não foi possível decodificar a resposta da API. A cidade pode não ter sido encontrada.")
        return pd.DataFrame()

    empresas_encontradas = []
    for element in data.get('elements', []):
        tags = element.get('tags', {})
        empresa_info = {
            'Nome': tags.get('name', 'Nome não disponível'),
            'Latitude': element.get('lat') or element.get('center', {}).get('lat'),
            'Longitude': element.get('lon') or element.get('center', {}).get('lon'),
            'Tags': str(tags)
        }
        if empresa_info['Latitude'] and empresa_info['Longitude']:
            empresas_encontradas.append(empresa_info)
    
    return pd.DataFrame(empresas_encontradas)

# --- INTERFACE DO APLICATIVO STREAMLIT ---

# Título da página
st.set_page_config(page_title="Buscador de Algodoeiras", layout="wide")
st.title("🗺️ Buscador de Empresas Algodoeiras")
st.markdown("Encontre indústrias do ramo algodoeiro em cidades do Brasil utilizando dados do OpenStreetMap.")

# Campo de texto para o usuário inserir a cidade
cidade_input = st.text_input(
    "Digite o nome da cidade e estado (ex: Sapezal, MT)", 
    "Sapezal, MT" # Valor padrão para facilitar o teste
)

# Botão para iniciar a busca
if st.button("Buscar Empresas"):
    if not cidade_input:
        st.warning("Por favor, digite o nome de uma cidade para iniciar a busca.")
    else:
        # Mostra uma mensagem de "carregando" enquanto a função de busca é executada
        with st.spinner(f"Buscando por empresas em '{cidade_input}'..."):
            df_empresas = buscar_empresas_osm(cidade_input)

        # Após a busca, verifica se encontrou resultados
        if df_empresas.empty:
            st.error("Nenhuma empresa encontrada no OpenStreetMap para esta cidade.")
        else:
            st.success(f"Busca concluída! Encontramos {len(df_empresas)} locais relevantes.")
            
            # Mostra a tabela de dados
            st.subheader("Resultados da Busca")
            st.dataframe(df_empresas[['Nome', 'Tags']])
            
            # Cria e exibe o mapa
            st.subheader("Mapa de Localizações")
            
            # Centraliza o mapa na primeira empresa da lista
            map_center = [df_empresas['Latitude'].iloc[0], df_empresas['Longitude'].iloc[0]]
            mapa = folium.Map(location=map_center, zoom_start=11)
            
            # Adiciona um marcador para cada empresa
            for index, empresa in df_empresas.iterrows():
                popup_html = f"""
                <b>{empresa.get('Nome', 'N/A')}</b><br>
                <hr>
                <b>Tags OSM:</b> {empresa.get('Tags', '{}')}
                """
                folium.Marker(
                    location=[empresa['Latitude'], empresa['Longitude']],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=empresa.get('Nome', 'N/A')
                ).add_to(mapa)
            
            # Renderiza o mapa na tela
            st_folium(mapa, width='100%', height=500)
