import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import folium
from folium.plugins import AntPath
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
import re
import polyline
import os
from datetime import datetime

# ==============================================================================
# CONFIGURAÇÃO INICIAL
# ==============================================================================

st.set_page_config(
    page_title="Mapa das Algodoeiras de MT",
    layout="wide",
    page_icon="🌱"
)

st.title("🌱 Mapa das Algodoeiras e Cooperativas de Mato Grosso")
st.markdown("Sistema completo para mapeamento e visualização interativa do setor algodoeiro.")

# ==============================================================================
# FUNÇÕES AUXILIARES - GEOCODIFICAÇÃO MELHORADA
# ==============================================================================

def is_pessoa_juridica(nome):
    """
    Verifica se um nome provavelmente pertence a uma empresa.
    """
    if not nome or pd.isna(nome):
        return False
        
    keywords = [
        'ltda', 's.a', 's/a', 's.a.', 'eireli', 'mei', 'me', 'empresa',
        'agropecuária', 'agropecuaria', 'agrícola', 'agricola', 
        'fazenda', 'grupo', 'agro', 'produtos', 'investimentos',
        'comércio', 'comercio', 'algodão', 'algodao', 'cotton',
        'industrial', 'exportação', 'exportadora', 'comercial',
        'holding', 'corporation', 'corp', 'inc', 'cooperative',
        'cooperativa', 'agrônoma', 'agronoma', 'sementes',
        'agricultura', 'ranch', 'farm', 'agribusiness',
        'algodoeira', 'agricola', 'agroindustrial', 'cooperativa'
    ]
    
    nome_lower = nome.lower()
    
    for keyword in keywords:
        if keyword in nome_lower:
            return True
    
    if re.search(r'\b(ltda|s\.a|s/a|eireli|mei|me)\b', nome_lower):
        return True
        
    return False

def geocodificar_empresa(nome, cidade="Mato Grosso", estado="MT", tipo="Algodoeira"):
    """
    Geocodifica uma empresa individual com estratégias aprimoradas
    """
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v8")
    
    try:
        # Dicionário de cidades importantes de MT para melhorar a precisão
        cidades_mt_coordenadas = {
            'sinop': (-11.8484, -55.5126),
            'cuiabá': (-15.6010, -56.0974),
            'cuiaba': (-15.6010, -56.0974),
            'rondonópolis': (-16.4676, -54.6378),
            'rondonopolis': (-16.4676, -54.6378),
            'lucas do rio verde': (-13.0678, -55.9125),
            'sorriso': (-12.5425, -55.7211),
            'tangará da serra': (-14.6229, -57.4823),
            'campo verde': (-15.5454, -55.1626),
            'nova mutum': (-13.8234, -56.0731),
            'primavera do leste': (-15.5601, -54.2971),
            'campo novo do parecis': (-13.6747, -57.8931)
        }
        
        # Verifica se o nome da empresa contém referência a cidades
        cidade_detectada = cidade
        for cidade_chave, coords in cidades_mt_coordenadas.items():
            if cidade_chave in nome.lower():
                cidade_detectada = cidade_chave.title()
                break
        
        # Estratégias de busca melhoradas
        queries = [
            f"{nome}, {cidade_detectada}, {estado}, Brasil",
            f"{nome}, {estado}, Brasil",
            f"{tipo} {nome}, {cidade_detectada}, {estado}, Brasil",
            f"{nome} algodão, {cidade_detectada}, {estado}, Brasil",
            f"{cidade_detectada}, {estado}, Brasil"
        ]
        
        location = None
        for query in queries:
            try:
                location = geolocator.geocode(query, timeout=15)
                if location and location.latitude and location.longitude:
                    # Verifica se a localização está em Mato Grosso
                    if -18.0 < location.latitude < -8.0 and -62.0 < location.longitude < -50.0:
                        break
                    else:
                        location = None  # Descarta localizações fora de MT
            except Exception as e:
                continue
        
        if location and location.latitude and location.longitude:
            endereco = location.address
            latitude = location.latitude
            longitude = location.longitude
            
            # Extrai cidade do endereço
            address_dict = location.raw.get('address', {})
            cidade_final = (address_dict.get('city') or 
                           address_dict.get('town') or 
                           address_dict.get('village') or 
                           address_dict.get('municipality') or 
                           address_dict.get('county') or
                           cidade_detectada)
            
            return {
                'Nome': nome,
                'Telefone': "Não Informado",
                'Tipo': tipo,
                'Cidade': cidade_final,
                'Estado': estado,
                'Latitude': latitude,
                'Longitude': longitude,
                'Endereco': endereco,
                'Fonte': 'Manual'
            }
        else:
            # Fallback: usa coordenadas da cidade específica se detectada
            if cidade_detectada.lower() in cidades_mt_coordenadas:
                lat, lon = cidades_mt_coordenadas[cidade_detectada.lower()]
                return {
                    'Nome': nome,
                    'Telefone': "Não Informado", 
                    'Tipo': tipo,
                    'Cidade': cidade_detectada,
                    'Estado': estado,
                    'Latitude': lat,
                    'Longitude': lon,
                    'Endereco': f"Localização aproximada - {cidade_detectada}, {estado}",
                    'Fonte': 'Manual (Cidade Aproximada)'
                }
            else:
                # Fallback geral para Mato Grosso
                return {
                    'Nome': nome,
                    'Telefone': "Não Informado",
                    'Tipo': tipo, 
                    'Cidade': cidade_detectada,
                    'Estado': estado,
                    'Latitude': -12.6819,
                    'Longitude': -56.9211,
                    'Endereco': f"Localização aproximada - {cidade_detectada}, {estado}",
                    'Fonte': 'Manual (Aproximado)'
                }
            
    except Exception as e:
        # Fallback em caso de erro
        return {
            'Nome': nome,
            'Telefone': "Não Informado",
            'Tipo': tipo, 
            'Cidade': cidade,
            'Estado': estado,
            'Latitude': -12.6819,
            'Longitude': -56.9211,
            'Endereco': f"Localização aproximada - {cidade}, {estado}",
            'Fonte': 'Manual (Erro)'
        }

# ==============================================================================
# SISTEMA DE ROTEAMENTO
# ==============================================================================

def calcular_rota(origem_lat, origem_lon, destino_lat, destino_lon, metodo='carro'):
    """
    Calcula rota entre dois pontos usando OpenRouteService API
    """
    try:
        # Usando OpenRouteService (gratuito, requer API key)
        # Você pode obter uma API key gratuita em: https://openrouteservice.org/
        api_key = st.secrets.get("OPENROUTE_API_KEY", "5b3ce3597851110001cf6248eac86a1a4c704c65b1a9b1b1f6c5a8a4")
        
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        
        headers = {
            'Accept': 'application/json, application/geo+json, application/gpx+json, img/png; charset=utf-8',
            'Authorization': api_key,
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        body = {
            "coordinates": [
                [origem_lon, origem_lat],
                [destino_lon, destino_lat]
            ],
            "instructions": "false",
            "preference": "recommended"
        }
        
        response = requests.post(url, json=body, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'routes' in data and len(data['routes']) > 0:
                route = data['routes'][0]
                geometry = route['geometry']
                
                # Decodifica a geometria polyline
                coordinates = polyline.decode(geometry, 5)
                
                # Converte para formato [lat, lon]
                route_coordinates = [[lat, lon] for lat, lon in coordinates]
                
                # Calcula distância e duração
                distance_km = route['summary']['distance'] / 1000
                duration_min = route['summary']['duration'] / 60
                
                return {
                    'rota_coordenadas': route_coordinates,
                    'distancia_km': round(distance_km, 1),
                    'duracao_min': round(duration_min, 1),
                    'sucesso': True
                }
        
        # Fallback: linha reta se a API falhar
        return {
            'rota_coordenadas': [[origem_lat, origem_lon], [destino_lat, destino_lon]],
            'distancia_km': calcular_distancia_reta(origem_lat, origem_lon, destino_lat, destino_lon),
            'duracao_min': calcular_distancia_reta(origem_lat, origem_lon, destino_lat, destino_lon) * 1.5,
            'sucesso': False,
            'observacao': 'Rota aproximada (linha reta)'
        }
        
    except Exception as e:
        st.error(f"Erro ao calcular rota: {str(e)}")
        # Fallback para linha reta
        return {
            'rota_coordenadas': [[origem_lat, origem_lon], [destino_lat, destino_lon]],
            'distancia_km': calcular_distancia_reta(origem_lat, origem_lon, destino_lat, destino_lon),
            'duracao_min': calcular_distancia_reta(origem_lat, origem_lon, destino_lat, destino_lon) * 1.5,
            'sucesso': False,
            'observacao': 'Rota aproximada (erro na API)'
        }

def calcular_distancia_reta(lat1, lon1, lat2, lon2):
    """
    Calcula distância em linha reta entre dois pontos (fórmula de Haversine)
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Raio da Terra em km
    
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return round(R * c, 1)

def geocodificar_endereco(endereco):
    """
    Geocodifica um endereço para coordenadas
    """
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v8")
    
    try:
        location = geolocator.geocode(f"{endereco}, Mato Grosso, Brasil", timeout=15)
        if location:
            return {
                'endereco': location.address,
                'latitude': location.latitude,
                'longitude': location.longitude,
                'sucesso': True
            }
        else:
            return {
                'sucesso': False,
                'erro': 'Endereço não encontrado'
            }
    except Exception as e:
        return {
            'sucesso': False,
            'erro': str(e)
        }

# ==============================================================================
# WEB SCRAPING (mantido igual)
# ==============================================================================

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_cooperativas():
    """
    Web scraping robusto para cooperativas com múltiplas estratégias
    """
    st.write("🏢 Coletando dados de cooperativas...")
    
    url = "https://ampa.com.br/consulta-cooperativas/"
    lista_cooperativas = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ESTRATÉGIA 1: Buscar por tabelas tradicionais
        tabelas = soup.find_all('table')
        st.write(f"🔍 Encontradas {len(tabelas)} tabelas na página")
        
        # ESTRATÉGIA 2: Buscar por divs que podem conter tabelas
        divs_com_tabelas = soup.find_all('div', class_=re.compile(r'table|wrapper|content', re.I))
        st.write(f"🔍 Encontrados {len(divs_com_tabelas)} divs que podem conter tabelas")
        
        # ESTRATÉGIA 3: Buscar diretamente por dados estruturados
        texto_completo = soup.get_text()
        linhas = texto_completo.split('\n')
        
        st.write("📝 Analisando conteúdo da página...")
        
        # Padrões para identificar cooperativas
        padroes_cooperativas = [
            r'([A-Z][A-Za-z\s&]+)\s+([A-Z][A-Za-z\s]+Cooperativa[A-Za-z\s]+)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s+(\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4})',
            r'([A-Z][A-Za-z\s&]+)\s+([A-Z][A-Za-z\s]+)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s+(\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4})',
        ]
        
        cooperativas_encontradas = 0
        
        for linha in linhas:
            linha_limpa = linha.strip()
            
            # Pula linhas muito curtas ou claramente não-dados
            if len(linha_limpa) < 10 or len(linha_limpa) > 200:
                continue
                
            # Verifica se parece ser uma linha de dados de cooperativa
            if any(palavra in linha_limpa.lower() for palavra in ['cooperativa', 'caap', 'email', '@', '(', ')']):
                # Tenta extrair dados usando regex
                for padrao in padroes_cooperativas:
                    matches = re.findall(padrao, linha_limpa)
                    if matches:
                        for match in matches:
                            if len(match) >= 2:
                                fantasia = match[0].strip()
                                nome_cooperativa = match[1].strip()
                                email = match[2] if len(match) > 2 else "Não Informado"
                                telefone = match[3] if len(match) > 3 else "Não Informado"
                                
                                # Prefere o nome completo da cooperativa
                                nome_final = nome_cooperativa if 'cooperativa' in nome_cooperativa.lower() else fantasia
                                
                                if nome_final and is_pessoa_juridica(nome_final):
                                    lista_cooperativas.append({
                                        'Nome': nome_final,
                                        'Telefone': telefone,
                                        'Email': email,
                                        'Tipo': 'Cooperativa',
                                        'Cidade': 'Mato Grosso',
                                        'Estado': 'MT'
                                    })
                                    cooperativas_encontradas += 1
        
        st.write(f"📊 Total de cooperativas identificadas: {cooperativas_encontradas}")
        
        if lista_cooperativas:
            df = pd.DataFrame(lista_cooperativas)
            df = df.drop_duplicates(subset=['Nome'])
            st.success(f"✅ Cooperativas: {len(df)} encontradas")
            return geocodificar_empresas_em_lote(df)
        else:
            st.warning("Nenhuma cooperativa encontrada automaticamente.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Erro ao coletar cooperativas: {str(e)}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_associados_ativos():
    """
    Web scraping robusto para associados ativos com múltiplas estratégias
    """
    st.write("👥 Coletando dados de associados ativos...")
    
    url = "https://ampa.com.br/consulta-associados-ativos/"
    lista_associados = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ESTRATÉGIA 1: Buscar por qualquer elemento que possa conter dados
        elementos_potenciais = soup.find_all(['div', 'p', 'span', 'li', 'td', 'tr'])
        
        st.write(f"🔍 Analisando {len(elementos_potenciais)} elementos na página...")
        
        associados_encontrados = 0
        padrao_telefone = r'\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4}'
        
        for elemento in elementos_potenciais:
            texto = elemento.get_text(strip=True)
            
            # Filtra elementos muito curtos ou muito longos
            if len(texto) < 5 or len(texto) > 100:
                continue
                
            # Pula elementos que são claramente não-nomes
            if texto.lower() in ['associado', 'telefone', 'nome', 'empresa', 'endereço']:
                continue
                
            # Verifica se tem formato de telefone (indicando que pode ser uma linha de dados)
            tem_telefone = re.search(padrao_telefone, texto)
            
            # Se tem telefone, provavelmente é uma linha de dados
            if tem_telefone:
                # Tenta extrair o nome (tudo antes do telefone)
                partes = texto.split(tem_telefone.group())
                if partes and partes[0].strip():
                    nome = partes[0].strip()
                    telefone = tem_telefone.group()
                    
                    if is_pessoa_juridica(nome):
                        lista_associados.append({
                            'Nome': nome,
                            'Telefone': telefone,
                            'Email': "Não Informado",
                            'Tipo': 'Associado Ativo',
                            'Cidade': 'Mato Grosso',
                            'Estado': 'MT'
                        })
                        associados_encontrados += 1
        
        st.write(f"📊 Total de associados identificados: {associados_encontrados}")
        
        if lista_associados:
            df = pd.DataFrame(lista_associados)
            df = df.drop_duplicates(subset=['Nome'])
            st.success(f"✅ Associados ativos: {len(df)} encontrados")
            return geocodificar_empresas_em_lote(df)
        else:
            st.warning("Nenhum associado ativo (PJ) encontrado automaticamente.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Erro ao coletar associados ativos: {str(e)}")
        return pd.DataFrame()

def geocodificar_empresas_em_lote(df):
    """
    Geocodifica empresas em lote
    """
    if df.empty:
        return df
        
    st.write("🗺️ Geocodificando empresas...")
    
    resultados = []
    total_empresas = len(df)
    
    if total_empresas == 0:
        return pd.DataFrame()
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for index, row in df.iterrows():
        progresso = min((index + 1) / total_empresas, 1.0)
        progress_bar.progress(progresso)
        status_text.text(f"Processando: {row['Nome'][:30]}... ({index + 1}/{total_empresas})")
        
        # Geocodifica cada empresa
        empresa_geocodificada = geocodificar_empresa(
            row['Nome'], 
            row.get('Cidade', 'Mato Grosso'),
            row.get('Estado', 'MT'),
            row.get('Tipo', 'Algodoeira')
        )
        
        if empresa_geocodificada:
            # Mantém os dados originais
            empresa_geocodificada['Telefone'] = row.get('Telefone', 'Não Informado')
            empresa_geocodificada['Email'] = row.get('Email', 'Não Informado')
            empresa_geocodificada['Tipo'] = row.get('Tipo', 'Algodoeira')
            empresa_geocodificada['Fonte'] = 'Web Scraping'
            resultados.append(empresa_geocodificada)
        
        time.sleep(1)  # Respeita rate limiting
    
    progress_bar.empty()
    status_text.text("✅ Geocodificação concluída!")
    
    if resultados:
        return pd.DataFrame(resultados)
    else:
        return pd.DataFrame()

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================

# Inicializar session state
if 'empresas_mapeadas' not in st.session_state:
    st.session_state.empresas_mapeadas = pd.DataFrame()
if 'map_center' not in st.session_state:
    st.session_state.map_center = [-12.6819, -56.9211]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 7
if 'rota_atual' not in st.session_state:
    st.session_state.rota_atual = None
if 'origem_rota' not in st.session_state:
    st.session_state.origem_rota = None

# ==============================================================================
# SEÇÃO 1: WEB SCRAPING ESPECÍFICO
# ==============================================================================

st.header("🔍 Coleta Automática por Categoria")

col1, col2 = st.columns(2)

with col1:
    if st.button("🏢 Coletar Cooperativas", type="primary", use_container_width=True):
        with st.spinner('Coletando dados de cooperativas...'):
            df_cooperativas = carregar_cooperativas()
            if not df_cooperativas.empty:
                if st.session_state.empresas_mapeadas.empty:
                    st.session_state.empresas_mapeadas = df_cooperativas
                else:
                    st.session_state.empresas_mapeadas = pd.concat([
                        st.session_state.empresas_mapeadas, 
                        df_cooperativas
                    ], ignore_index=True).drop_duplicates(subset=['Nome'])
                st.rerun()

with col2:
    if st.button("👥 Coletar Associados Ativos", type="primary", use_container_width=True):
        with st.spinner('Coletando dados de associados ativos...'):
            df_associados = carregar_associados_ativos()
            if not df_associados.empty:
                if st.session_state.empresas_mapeadas.empty:
                    st.session_state.empresas_mapeadas = df_associados
                else:
                    st.session_state.empresas_mapeadas = pd.concat([
                        st.session_state.empresas_mapeadas, 
                        df_associados
                    ], ignore_index=True).drop_duplicates(subset=['Nome'])
                st.rerun()

# Botão para limpar dados
if st.button("🗑️ Limpar Todos os Dados", use_container_width=True):
    st.session_state.empresas_mapeadas = pd.DataFrame()
    st.session_state.rota_atual = None
    st.session_state.origem_rota = None
    st.session_state.map_center = [-12.6819, -56.9211]
    st.session_state.map_zoom = 7
    st.rerun()

# ==============================================================================
# SEÇÃO 2: INSERÇÃO MANUAL MELHORADA
# ==============================================================================

st.header("✍️ Inserção Manual")

# Lista de empresas conhecidas para facilitar
empresas_sugeridas = [
    "Algodoeira Reunidas Sinop",
    "3ab Produtos Agricolas S.A. Sinop",
    "Cooperativa Aliança dos Produtores do Parecis",
    "Amaggi Agro Sapezal",
    "Bom Futuro Agro Campo Novo do Parecis",
    "Scheffer Agro Lucas do Rio Verde",
    "Agropecuária Maggi Sapezal",
    "SLC Agrícola Mato Grosso",
    "Brasil Agro Rondonópolis",
    "Agro Santa Rosa Nova Mutum",
    "Cotton Brasil Sorriso"
]

with st.form("form_insercao_manual"):
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        nome_empresa = st.selectbox(
            "Nome da Empresa:",
            options=empresas_sugeridas,
            index=0,
            help="Selecione uma empresa sugerida ou digite manualmente"
        )
        
        nome_custom = st.text_input(
            "Ou digite o nome manualmente:",
            placeholder="Ex: Algodoeira São João Sinop",
            help="💡 Dica: Inclua a cidade no nome para melhor precisão"
        )
        
        nome_final = nome_custom if nome_custom else nome_empresa
    
    with col2:
        tipo_empresa = st.selectbox(
            "Tipo:",
            options=["Algodoeira", "Cooperativa", "Associado Ativo", "Outro"],
            index=0
        )
    
    with col3:
        cidades_mt = [
            "Sinop", "Cuiabá", "Rondonópolis", "Lucas do Rio Verde", "Sorriso",
            "Tangará da Serra", "Campo Verde", "Nova Mutum", "Primavera do Leste",
            "Campo Novo do Parecis", "Sapezal", "Outra"
        ]
        cidade_empresa = st.selectbox("Cidade:", cidades_mt)
        
        if cidade_empresa == "Outra":
            cidade_empresa = st.text_input("Digite a cidade:")
    
    submitted = st.form_submit_button("📍 Buscar e Adicionar ao Mapa", type="secondary", use_container_width=True)
    
    if submitted and nome_final:
        with st.spinner(f'Buscando localização de {nome_final}...'):
            empresa_geocodificada = geocodificar_empresa(
                nome_final, 
                cidade_empresa, 
                "MT", 
                tipo_empresa
            )
            
            if empresa_geocodificada:
                nova_empresa_df = pd.DataFrame([empresa_geocodificada])
                
                if st.session_state.empresas_mapeadas.empty:
                    st.session_state.empresas_mapeadas = nova_empresa_df
                else:
                    nomes_existentes = st.session_state.empresas_mapeadas['Nome'].values
                    if nome_final not in nomes_existentes:
                        st.session_state.empresas_mapeadas = pd.concat(
                            [st.session_state.empresas_mapeadas, nova_empresa_df], 
                            ignore_index=True
                        )
                        st.success(f"✅ {nome_final} adicionada ao mapa!")
                        
                        # Foca no mapa na nova localização
                        st.session_state.map_center = [empresa_geocodificada['Latitude'], empresa_geocodificada['Longitude']]
                        st.session_state.map_zoom = 12
                    else:
                        st.warning("⚠️ Esta empresa já está na lista!")
                
                st.rerun()

# ==============================================================================
# SEÇÃO 3: SISTEMA DE ROTEAMENTO
# ==============================================================================

st.header("🗺️ Sistema de Roteamento")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📍 Definir Origem")
    
    metodo_origem = st.radio(
        "Como definir a origem:",
        ["Usar Minha Localização Atual", "Digitar Endereço", "Selecionar do Mapa"],
        horizontal=True
    )
    
    origem_lat = None
    origem_lon = None
    origem_nome = "Minha Localização"
    
    if metodo_origem == "Usar Minha Localização Atual":
        # Nota: Streamlit não tem acesso direto à geolocalização do usuário
        st.info("💡 Para usar sua localização atual, você precisará permitir o acesso à localização no navegador.")
        
        col_loc1, col_loc2 = st.columns(2)
        with col_loc1:
            origem_lat = st.number_input("Latitude:", value=-12.6819, format="%.6f")
        with col_loc2:
            origem_lon = st.number_input("Longitude:", value=-56.9211, format="%.6f")
            
        origem_nome = f"Localização ({origem_lat:.4f}, {origem_lon:.4f})"
        
    elif metodo_origem == "Digitar Endereço":
        endereco_origem = st.text_input(
            "Digite seu endereço:",
            placeholder="Ex: Avenida das Torres, 1000, Sinop, MT",
            help="Inclua cidade e estado para melhor precisão"
        )
        
        if endereco_origem:
            if st.button("📍 Buscar Endereço", key="buscar_origem"):
                with st.spinner('Buscando endereço...'):
                    resultado = geocodificar_endereco(endereco_origem)
                    if resultado['sucesso']:
                        origem_lat = resultado['latitude']
                        origem_lon = resultado['longitude']
                        origem_nome = resultado['endereco']
                        st.success("✅ Endereço encontrado!")
                        
                        # Atualiza os campos
                        st.session_state.origem_lat = origem_lat
                        st.session_state.origem_lon = origem_lon
                        st.session_state.origem_nome = origem_nome
                    else:
                        st.error("❌ Endereço não encontrado. Tente ser mais específico.")
        
        # Usa valores da session state se disponíveis
        if 'origem_lat' in st.session_state:
            origem_lat = st.session_state.origem_lat
            origem_lon = st.session_state.origem_lon
            origem_nome = st.session_state.origem_nome

    elif metodo_origem == "Selecionar do Mapa":
        st.info("💡 Clique em 'Ver no Mapa' na lista de empresas abaixo para selecionar como origem")

with col2:
    st.subheader("🎯 Destino")
    
    if not st.session_state.empresas_mapeadas.empty:
        empresas_opcoes = st.session_state.empresas_mapeadas['Nome'].tolist()
        destino_selecionado = st.selectbox("Selecionar empresa destino:", empresas_opcoes)
        
        if destino_selecionado:
            empresa_destino = st.session_state.empresas_mapeadas[
                st.session_state.empresas_mapeadas['Nome'] == destino_selecionado
            ].iloc[0]
            
            destino_lat = empresa_destino['Latitude']
            destino_lon = empresa_destino['Longitude']
            destino_nome = empresa_destino['Nome']
            
            st.write(f"**Destino:** {destino_nome}")
            st.write(f"📍 {empresa_destino.get('Cidade', 'Cidade não informada')}")

# Botão para calcular rota
if st.button("🚗 Calcular Rota", type="primary", use_container_width=True):
    if origem_lat and origem_lon and 'destino_lat' in locals():
        with st.spinner('Calculando melhor rota...'):
            rota = calcular_rota(origem_lat, origem_lon, destino_lat, destino_lon)
            
            if rota:
                st.session_state.rota_atual = rota
                st.session_state.origem_rota = {
                    'nome': origem_nome,
                    'lat': origem_lat,
                    'lon': origem_lon
                }
                st.session_state.destino_rota = {
                    'nome': destino_nome,
                    'lat': destino_lat,
                    'lon': destino_lon
                }
                
                st.success(f"✅ Rota calculada: {rota['distancia_km']} km • {rota['duracao_min']} min")
                
                if not rota['sucesso']:
                    st.warning("⚠️ " + rota.get('observacao', 'Rota aproximada'))
    else:
        st.error("❌ Por favor, defina tanto a origem quanto o destino")

# Exibir informações da rota atual
if st.session_state.rota_atual:
    rota = st.session_state.rota_atual
    origem = st.session_state.origem_rota
    destino = st.session_state.destino_rota
    
    st.subheader("📋 Detalhes da Rota")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Distância Total", f"{rota['distancia_km']} km")
    
    with col2:
        st.metric("Tempo Estimado", f"{rota['duracao_min']} min")
    
    with col3:
        st.metric("Velocidade Média", f"{rota['distancia_km'] / (rota['duracao_min'] / 60):.1f} km/h")
    
    st.write(f"**Origem:** {origem['nome']}")
    st.write(f"**Destino:** {destino['nome']}")
    
    if st.button("🗑️ Limpar Rota", use_container_width=True):
        st.session_state.rota_atual = None
        st.session_state.origem_rota = None
        st.session_state.destino_rota = None
        st.rerun()

# ==============================================================================
# SEÇÃO 4: VISUALIZAÇÃO DOS DADOS E MAPA
# ==============================================================================

if not st.session_state.empresas_mapeadas.empty:
    st.header("📊 Dados Coletados")
    
    df_final = st.session_state.empresas_mapeadas
    
    # Estatísticas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Empresas", len(df_final))
    
    with col2:
        cidades_count = df_final['Cidade'].nunique() if 'Cidade' in df_final.columns else 1
        st.metric("Cidades", cidades_count)
    
    with col3:
        if 'Tipo' in df_final.columns:
            tipos_count = df_final['Tipo'].nunique()
        else:
            tipos_count = 1
        st.metric("Tipos Diferentes", tipos_count)
    
    with col4:
        if 'Fonte' in df_final.columns:
            web_count = len(df_final[df_final['Fonte'] == 'Web Scraping'])
        else:
            web_count = 0
        st.metric("Coleta Automática", web_count)
    
    # Filtros
    st.subheader("🎛️ Filtros")
    col1, col2 = st.columns(2)
    
    with col1:
        if 'Tipo' in df_final.columns and not df_final.empty:
            tipos = ["Exibir Todos"] + sorted(df_final['Tipo'].unique().tolist())
        else:
            tipos = ["Exibir Todos"]
        tipo_selecionado = st.selectbox("Filtrar por Tipo:", tipos)
    
    with col2:
        if 'Cidade' in df_final.columns and not df_final.empty:
            cidades = ["Exibir Todas"] + sorted(df_final['Cidade'].unique().tolist())
        else:
            cidades = ["Exibir Todas"]
        cidade_selecionada = st.selectbox("Filtrar por Cidade:", cidades)
    
    # Aplica filtros
    df_filtrado = df_final.copy()
    
    if tipo_selecionado != "Exibir Todos" and 'Tipo' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Tipo'] == tipo_selecionado]
    
    if cidade_selecionada != "Exibir Todas" and 'Cidade' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Cidade'] == cidade_selecionada]

    # MAPA INTERATIVO
    st.subheader("🗺️ Mapa de Localizações")
    
    # Filtra empresas com coordenadas válidas
    df_mapa = df_filtrado.dropna(subset=['Latitude', 'Longitude']).copy()
    
    if df_mapa.empty:
        st.warning("Nenhuma empresa com coordenadas válidas para exibir no mapa com os filtros atuais.")
    else:
        # Cria mapa
        mapa = folium.Map(
            location=st.session_state.map_center, 
            zoom_start=st.session_state.map_zoom, 
            tiles="OpenStreetMap"
        )

        # Adiciona camadas de mapa
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satélite (Esri)',
            overlay=False,
            control=True
        ).add_to(mapa)

        folium.TileLayer(
            tiles='CartoDB positron',
            attr='CartoDB',
            name='Minimalista (CartoDB)',
            overlay=False,
            control=True
        ).add_to(mapa)

        # Cores por tipo de empresa
        cores = {
            'Cooperativa': 'blue',
            'Associado Ativo': 'green',
            'Algodoeira': 'red',
            'Outro': 'orange'
        }

        # Adiciona marcadores das empresas
        for index, empresa in df_mapa.iterrows():
            tipo = empresa.get('Tipo', 'Algodoeira')
            cor = cores.get(tipo, 'gray')
            
            popup_html = f"""
            <div style="min-width: 250px">
                <h4>{empresa['Nome']}</h4>
                <hr>
                <b>🏢 Tipo:</b> {tipo}<br>
                <b>📍 Cidade:</b> {empresa.get('Cidade', 'Não informada')}<br>
                <b>📞 Telefone:</b> {empresa.get('Telefone', 'Não Informado')}<br>
                <b>📧 Email:</b> {empresa.get('Email', 'Não Informado')}<br>
                <b>🔍 Fonte:</b> {empresa.get('Fonte', 'Manual')}<br>
                <b>🎯 Endereço:</b> {empresa.get('Endereco', 'Localização aproximada')}
            </div>
            """
            
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{empresa['Nome']} ({tipo})",
                icon=folium.Icon(color=cor, icon='industry', prefix='fa')
            ).add_to(mapa)

        # Adiciona rota se existir
        if st.session_state.rota_atual:
            rota = st.session_state.rota_atual
            origem = st.session_state.origem_rota
            destino = st.session_state.destino_rota
            
            # Adiciona marcadores de origem e destino
            folium.Marker(
                location=[origem['lat'], origem['lon']],
                popup=f"<b>Origem:</b> {origem['nome']}",
                tooltip="Origem da Rota",
                icon=folium.Icon(color='green', icon='home', prefix='fa')
            ).add_to(mapa)
            
            folium.Marker(
                location=[destino['lat'], destino['lon']],
                popup=f"<b>Destino:</b> {destino['nome']}",
                tooltip="Destino da Rota",
                icon=folium.Icon(color='red', icon='flag', prefix='fa')
            ).add_to(mapa)
            
            # Adiciona a rota
            if len(rota['rota_coordenadas']) > 1:
                AntPath(
                    rota['rota_coordenadas'],
                    color='blue',
                    weight=6,
                    opacity=0.7,
                    dash_array=[10, 20],
                    tooltip=f"Rota: {rota['distancia_km']} km, {rota['duracao_min']} min"
                ).add_to(mapa)
                
                # Adiciona também uma linha sólida por baixo
                folium.PolyLine(
                    rota['rota_coordenadas'],
                    color='blue',
                    weight=3,
                    opacity=0.9,
                    tooltip=f"Rota para {destino['nome']}"
                ).add_to(mapa)
        
        folium.LayerControl().add_to(mapa)

        # Exibe o mapa
        st_folium(mapa, width='100%', height=500, returned_objects=[])

    # LISTA DE EMPRESAS INTERATIVA
    st.subheader("📋 Lista de Empresas")

    # Função para atualizar o centro do mapa e definir como origem
    def set_map_center(lat, lon, nome):
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom = 14
        
        # Se o usuário quiser usar esta empresa como origem
        if st.session_state.get('definir_como_origem', False):
            st.session_state.origem_rota = {
                'nome': nome,
                'lat': lat,
                'lon': lon
            }
            st.session_state.origem_lat = lat
            st.session_state.origem_lon = lon
            st.session_state.origem_nome = nome
            st.success(f"✅ {nome} definida como origem da rota!")

    # Checkbox para definir como origem ao clicar
    definir_como_origem = st.checkbox(
        "Definir como origem ao clicar em 'Ver no Mapa'", 
        value=st.session_state.get('definir_como_origem', False)
    )
    st.session_state.definir_como_origem = definir_como_origem

    # Cabeçalho da lista
    col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
    with col1:
        st.markdown("**Nome**")
    with col2:
        st.markdown("**Tipo**")
    with col3:
        st.markdown("**Cidade**")
    with col4:
        st.markdown("**Ação**")
    with col5:
        st.markdown("**Rota**")

    # Itera sobre o dataframe filtrado
    for index, row in df_filtrado.reset_index(drop=True).iterrows():
        st.divider()
        col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
        with col1:
            st.write(row.get('Nome', 'N/A'))
        with col2:
            st.write(row.get('Tipo', 'N/A'))
        with col3:
            st.write(row.get('Cidade', 'N/A'))
        with col4:
            # Botão para focar no mapa
            if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
                st.button(
                    "🗺️ Ver Mapa", 
                    key=f"goto_{index}", 
                    on_click=set_map_center, 
                    args=(row['Latitude'], row['Longitude'], row['Nome']),
                    use_container_width=True
                )
        with col5:
            # Botão para calcular rota até esta empresa
            if (pd.notna(row['Latitude']) and pd.notna(row['Longitude']) and 
                st.session_state.get('origem_rota')):
                st.button(
                    "🚗 Rota", 
                    key=f"route_{index}", 
                    on_click=lambda lat=row['Latitude'], lon=row['Longitude'], nome=row['Nome']: 
                        st.session_state.update({
                            'destino_lat': lat,
                            'destino_lon': lon,
                            'destino_nome': nome
                        }),
                    use_container_width=True
                )
    
    st.divider()
    
    # Download
    st.download_button(
        label="📥 Baixar Dados Completos (CSV)",
        data=df_final.to_csv(index=False, encoding='utf-8-sig'),
        file_name=f"empresas_algodao_mt_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    st.info("""
    👆 **Para começar:**
    
    1. **Coleta Automática:** Escolha entre cooperativas ou associados ativos.
    2. **Inserção Manual:** Adicione empresas específicas manualmente.
    3. **Sistema de Rotas:** Defina sua origem e calcule rotas para as empresas.
    4. **Mapa Interativo:** Visualize todas as localizações e rotas.
    
    💡 **Dica:** Inclua o nome da cidade ao adicionar empresas manualmente para melhor precisão!
    """)

# ==============================================================================
# CARREGAMENTO DE DADOS EXTERNOS (mantido igual)
# ==============================================================================

st.sidebar.header("📤 Carregar Dados Externos")

uploaded_file = st.sidebar.file_uploader(
    "Carregar lista de empresas (CSV):",
    type=['csv'],
    help="CSV deve ter coluna 'Nome' com os nomes das empresas"
)

if uploaded_file is not None:
    try:
        df_upload = pd.read_csv(uploaded_file)
        if 'Nome' in df_upload.columns:
            st.sidebar.success(f"📊 {len(df_upload)} empresas carregadas")
            
            if st.sidebar.button("🗺️ Geocodificar Empresas do Arquivo"):
                with st.spinner('Processando empresas do arquivo...'):
                    df_upload['É_PJ'] = df_upload['Nome'].apply(is_pessoa_juridica)
                    df_pjs = df_upload[df_upload['É_PJ']].copy()
                    
                    if not df_pjs.empty:
                        st.sidebar.write(f"🏢 {len(df_pjs)} empresas são PJs")
                        
                        df_para_geocodificar = pd.DataFrame({
                            'Nome': df_pjs['Nome'],
                            'Telefone': df_pjs.get('Telefone', 'Não Informado'),
                            'Email': df_pjs.get('Email', 'Não Informado'),
                            'Tipo': df_pjs.get('Tipo', 'Algodoeira'),
                            'Cidade': 'Mato Grosso',
                            'Estado': 'MT'
                        })
                        
                        df_geocodificado = geocodificar_empresas_em_lote(df_para_geocodificar)
                        
                        if not df_geocodificado.empty:
                            if st.session_state.empresas_mapeadas.empty:
                                st.session_state.empresas_mapeadas = df_geocodificado
                            else:
                                nomes_existentes = set(st.session_state.empresas_mapeadas['Nome'].values)
                                df_novas = df_geocodificado[~df_geocodificado['Nome'].isin(nomes_existentes)]
                                
                                if not df_novas.empty:
                                    st.session_state.empresas_mapeadas = pd.concat(
                                        [st.session_state.empresas_mapeadas, df_novas], 
                                        ignore_index=True
                                    )
                                    st.sidebar.success(f"✅ {len(df_novas)} novas empresas adicionadas!")
                                else:
                                    st.sidebar.info("ℹ️ Todas as empresas do arquivo já estão mapeadas")
                            
                            st.rerun()
                    else:
                        st.sidebar.warning("ℹ️ Nenhuma pessoa jurídica encontrada no arquivo")
        else:
            st.sidebar.error("❌ Arquivo deve ter coluna 'Nome'")
            
    except Exception as e:
        st.sidebar.error(f"❌ Erro ao processar arquivo: {e}")

# ==============================================================================
# INSTRUÇÕES
# ==============================================================================

with st.expander("📖 Guia de Uso Completo"):
    st.markdown("""
    **🎯 Sistema de Rotas:**
    
    1. **Defina sua Origem:**
       - 📍 **Usar Minha Localização:** Digite suas coordenadas
       - 🏠 **Digitar Endereço:** Busque por endereço completo
       - 🗺️ **Selecionar do Mapa:** Clique em "Ver no Mapa" + marque "Definir como origem"
    
    2. **Selecione o Destino:** Escolha uma empresa da lista
    
    3. **Calcule a Rota:** Clique em "Calcular Rota"
    
    **🗺️ Geocodificação Melhorada:**
    
    - Agora detectamos automaticamente cidades nos nomes das empresas
    - Inclua a cidade no nome para melhor precisão: "Algodoeira São João Sinop"
    - Coordenadas aprimoradas para cidades principais de MT
    
    **🔧 Funcionalidades:**
    
    - 🚗 **Sistema de Rotas** com cálculo de distância e tempo
    - 🗺️ **Mapa Interativo** com múltiplas camadas
    - 📍 **Geocodificação Inteligente** com fallback para cidades
    - 📊 **Filtros Avançados** por tipo e cidade
    - 📥 **Exportação de Dados** em CSV
    
    **💡 Dicas:**
    
    - Para máxima precisão, inclua a cidade no nome da empresa
    - Use o filtro "Definir como origem" para rápido planejamento de rotas
    - A rota em azul no mapa mostra o trajeto calculado
    - Use a camada de satélite para ver a região em detalhes
    """)
