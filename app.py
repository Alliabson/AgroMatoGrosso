import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import folium
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
import re

# ==============================================================================
# FUNÇÕES AUXILIARES
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
        'agricultura', 'ranch', 'farm', 'agribusiness'
    ]
    
    nome_lower = nome.lower()
    
    for keyword in keywords:
        if keyword in nome_lower:
            return True
    
    if re.search(r'\b(ltda|s\.a|s/a|eireli|mei|me)\b', nome_lower):
        return True
        
    return False

def geocodificar_empresa(nome, cidade="Mato Grosso", estado="MT"):
    """
    Geocodifica uma empresa individual
    """
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_manual")
    
    try:
        # Tenta diferentes formatos de query
        queries = [
            f"{nome}, {cidade}, {estado}, Brasil",
            f"{nome}, {estado}, Brasil",
            f"{nome}, Brasil",
            f"{cidade}, {estado}, Brasil"  # Fallback
        ]
        
        location = None
        for query in queries:
            try:
                location = geolocator.geocode(query, timeout=10)
                if location:
                    break
            except:
                continue
        
        if location:
            endereco = location.address
            latitude = location.latitude
            longitude = location.longitude
            
            # Extrai cidade do endereço
            address_dict = location.raw.get('address', {})
            cidade_detectada = (address_dict.get('city') or 
                              address_dict.get('town') or 
                              address_dict.get('village') or 
                              address_dict.get('municipality') or 
                              cidade)
            
            return {
                'Nome': nome,
                'Telefone': "Não Informado",
                'Tipo': 'Algodoeira',
                'Cidade': cidade_detectada,
                'Estado': estado,
                'Latitude': latitude,
                'Longitude': longitude,
                'Endereco': endereco,
                'Fonte': 'Manual'
            }
        else:
            st.warning(f"❌ Não foi possível geocodificar: {nome}")
            return None
            
    except Exception as e:
        st.error(f"Erro na geocodificação de {nome}: {e}")
        return None

def geocodificar_multiplas_empresas(df):
    """
    Geocodifica um DataFrame de empresas
    """
    if df.empty:
        return df
        
    st.write("🗺️ Iniciando geocodificação...")
    
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v3")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

    latitudes = []
    longitudes = []
    cidades_detectadas = []
    enderecos = []
    
    progress_bar = st.progress(0)
    total_empresas = len(df)
    status_text = st.empty()

    for index, row in df.iterrows():
        # CORREÇÃO: Garante que o progresso nunca ultrapasse 1.0
        progresso_atual = min((index + 1) / total_empresas, 1.0)
        progress_bar.progress(progresso_atual)
        
        status_text.text(f"📍 Buscando: {row['Nome'][:40]}... ({index + 1}/{total_empresas})")
        
        location = None
        query_attempts = [
            f"{row['Nome']}, Mato Grosso, Brasil",
            "Cuiabá, Mato Grosso, Brasil"
        ]
        
        for query in query_attempts:
            try:
                location = geocode(query)
                if location:
                    break
            except Exception as e:
                continue

        if location:
            latitudes.append(location.latitude)
            longitudes.append(location.longitude)
            enderecos.append(location.address)
            
            address = location.raw.get('address', {})
            cidade = (address.get('city') or 
                     address.get('town') or 
                     address.get('village') or 
                     address.get('municipality') or 
                     "Mato Grosso")
            cidades_detectadas.append(cidade)
        else:
            latitudes.append(None)
            longitudes.append(None)
            enderecos.append("Não Localizado")
            cidades_detectadas.append("Mato Grosso")
        
        time.sleep(1.2)

    df_result = df.copy()
    df_result['Latitude'] = latitudes
    df_result['Longitude'] = longitudes
    df_result['Cidade'] = cidades_detectadas  # CORREÇÃO: Nome da coluna padronizado
    df_result['Endereco'] = enderecos
    df_result['Fonte'] = 'Web Scraping'
    
    df_final = df_result.dropna(subset=['Latitude', 'Longitude']).copy()
    
    status_text.text("✅ Geocodificação finalizada!")
    progress_bar.empty()
    return df_final

# ==============================================================================
# WEB SCRAPING
# ==============================================================================

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_dados_web_scraping():
    """
    Tenta carregar dados via web scraping
    """
    st.write("🌐 Tentando web scraping automático...")
    
    url = "https://ampa.com.br/consulta-associados-ativos/"
    lista_empresas = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Estratégia simplificada: busca por texto que parece nome de empresa
        elementos_texto = soup.find_all(text=True)
        
        empresas_encontradas = set()
        
        for texto in elementos_texto:
            texto_limpo = texto.strip()
            
            if len(texto_limpo) > 5 and is_pessoa_juridica(texto_limpo):
                if texto_limpo not in empresas_encontradas:
                    empresas_encontradas.add(texto_limpo)
                    lista_empresas.append({
                        'Nome': texto_limpo,
                        'Telefone': "Não Informado",
                        'Tipo': 'Algodoeira',
                        'Cidade': 'Mato Grosso',
                        'Estado': 'MT'
                    })
        
        if lista_empresas:
            df = pd.DataFrame(lista_empresas)
            st.success(f"✅ Web scraping: {len(df)} empresas encontradas")
            return geocodificar_multiplas_empresas(df)
        else:
            st.warning("⚠️ Web scraping não encontrou empresas. Use a inserção manual.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Falha no web scraping: {e}")
        return pd.DataFrame()

# ==============================================================================
# INTERFACE STREAMLIT
# ==============================================================================

st.set_page_config(
    page_title="Mapa das Algodoeiras de MT", 
    layout="wide",
    page_icon="🌱"
)

st.title("🌱 Mapa das Algodoeiras de Mato Grosso")
st.markdown("Sistema híbrido: web scraping automático + inserção manual")

# Inicializar session state para armazenar empresas
if 'empresas_mapeadas' not in st.session_state:
    st.session_state.empresas_mapeadas = pd.DataFrame()

# ==============================================================================
# SEÇÃO 1: WEB SCRAPING AUTOMÁTICO
# ==============================================================================

st.header("🔍 Coleta Automática")

col1, col2 = st.columns([3, 1])
with col1:
    if st.button("🔄 Tentar Web Scraping Automático", type="primary"):
        with st.spinner('Coletando dados da AMPA...'):
            df_scraping = carregar_dados_web_scraping()
            if not df_scraping.empty:
                st.session_state.empresas_mapeadas = df_scraping
                st.rerun()

with col2:
    if st.button("🗑️ Limpar Dados"):
        st.session_state.empresas_mapeadas = pd.DataFrame()
        st.rerun()

# ==============================================================================
# SEÇÃO 2: INSERÇÃO MANUAL
# ==============================================================================

st.header("✍️ Inserção Manual")

with st.form("form_insercao_manual"):
    col1, col2 = st.columns([3, 1])
    
    with col1:
        nome_empresa = st.text_input(
            "Nome da Empresa:",
            placeholder="Ex: 3ab Produtos Agricolas S.A.",
            help="Digite o nome completo da empresa algodoeira"
        )
    
    with col2:
        cidade_empresa = st.text_input(
            "Cidade (opcional):",
            value="Mato Grosso",
            help="Cidade onde a empresa está localizada"
        )
    
    submitted = st.form_submit_button("📍 Buscar Localização", type="secondary")
    
    if submitted and nome_empresa:
        with st.spinner(f'Buscando localização de {nome_empresa}...'):
            empresa_geocodificada = geocodificar_empresa(nome_empresa, cidade_empresa)
            
            if empresa_geocodificada:
                # Converte para DataFrame para facilitar a manipulação
                nova_empresa_df = pd.DataFrame([empresa_geocodificada])
                
                # Adiciona às empresas existentes
                if st.session_state.empresas_mapeadas.empty:
                    st.session_state.empresas_mapeadas = nova_empresa_df
                else:
                    # Verifica se já existe para evitar duplicatas
                    if nome_empresa not in st.session_state.empresas_mapeadas['Nome'].values:
                        st.session_state.empresas_mapeadas = pd.concat(
                            [st.session_state.empresas_mapeadas, nova_empresa_df], 
                            ignore_index=True
                        )
                    else:
                        st.warning("⚠️ Esta empresa já está na lista!")
                
                st.success(f"✅ {nome_empresa} adicionada ao mapa!")
                st.rerun()

# ==============================================================================
# SEÇÃO 3: VISUALIZAÇÃO DOS DADOS
# ==============================================================================

if not st.session_state.empresas_mapeadas.empty:
    st.header("📊 Dados e Mapa")
    
    df_final = st.session_state.empresas_mapeadas
    
    # CORREÇÃO: Verifica se as colunas existem antes de acessá-las
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Empresas", len(df_final))
    
    with col2:
        # Verifica se a coluna Cidade existe
        if 'Cidade' in df_final.columns:
            cidades_count = df_final['Cidade'].nunique()
        else:
            cidades_count = 0
        st.metric("Cidades", cidades_count)
    
    with col3:
        if 'Fonte' in df_final.columns:
            web_scraping_count = len(df_final[df_final['Fonte'] == 'Web Scraping'])
        else:
            web_scraping_count = 0
        st.metric("Web Scraping", web_scraping_count)
    
    with col4:
        if 'Fonte' in df_final.columns:
            manual_count = len(df_final[df_final['Fonte'] == 'Manual'])
        else:
            manual_count = len(df_final)
        st.metric("Manuais", manual_count)
    
    # Filtros
    st.subheader("🎛️ Filtros")
    col1, col2 = st.columns(2)
    
    with col1:
        # CORREÇÃO: Verifica se a coluna existe
        if 'Cidade' in df_final.columns and not df_final.empty:
            cidades = ["Exibir Todas"] + sorted(df_final['Cidade'].unique().tolist())
        else:
            cidades = ["Exibir Todas"]
        cidade_selecionada = st.selectbox("Filtrar por Cidade:", cidades)
    
    with col2:
        # CORREÇÃO: Verifica se a coluna existe
        if 'Fonte' in df_final.columns and not df_final.empty:
            fontes = ["Exibir Todas"] + sorted(df_final['Fonte'].unique().tolist())
        else:
            fontes = ["Exibir Todas"]
        fonte_selecionada = st.selectbox("Filtrar por Fonte:", fontes)
    
    # Aplica filtros
    df_filtrado = df_final.copy()
    
    if cidade_selecionada != "Exibir Todas" and 'Cidade' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Cidade'] == cidade_selecionada]
    
    if fonte_selecionada != "Exibir Todas" and 'Fonte' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Fonte'] == fonte_selecionada]
    
    # Tabela - CORREÇÃO: Usa colunas que existem
    st.subheader("📋 Empresas Mapeadas")
    
    # Define quais colunas mostrar (apenas as que existem)
    colunas_para_mostrar = ['Nome']
    if 'Cidade' in df_filtrado.columns:
        colunas_para_mostrar.append('Cidade')
    if 'Fonte' in df_filtrado.columns:
        colunas_para_mostrar.append('Fonte')
    if 'Endereco' in df_filtrado.columns:
        colunas_para_mostrar.append('Endereco')
    
    st.dataframe(
        df_filtrado[colunas_para_mostrar].reset_index(drop=True),
        use_container_width=True,
        height=300
    )
    
    # Mapa - CORREÇÃO: Verifica se há dados após filtragem
    st.subheader("🗺️ Mapa de Localizações")
    
    if df_filtrado.empty:
        st.warning("Nenhuma empresa encontrada com os filtros aplicados.")
    else:
        # Verifica se as colunas de coordenadas existem
        if 'Latitude' not in df_filtrado.columns or 'Longitude' not in df_filtrado.columns:
            st.error("Dados de localização não disponíveis.")
        else:
            # Remove linhas com coordenadas inválidas
            df_mapa = df_filtrado.dropna(subset=['Latitude', 'Longitude']).copy()
            
            if df_mapa.empty:
                st.warning("Nenhuma empresa com coordenadas válidas após filtragem.")
            else:
                map_center = [-12.6819, -56.9211]  # Centro de MT
                if len(df_mapa) > 0:
                    map_center = [df_mapa['Latitude'].mean(), df_mapa['Longitude'].mean()]
                
                mapa = folium.Map(location=map_center, zoom_start=7)

                for index, empresa in df_mapa.iterrows():
                    # Define cor baseada na fonte
                    cor = 'blue' if empresa.get('Fonte') == 'Manual' else 'green'
                    
                    popup_html = f"""
                    <div style="min-width: 250px">
                        <h4>{empresa['Nome']}</h4>
                        <hr>
                        <b>📍 Cidade:</b> {empresa.get('Cidade', 'Não informada')}<br>
                        <b>🏢 Tipo:</b> {empresa.get('Tipo', 'Algodoeira')}<br>
                        <b>📞 Telefone:</b> {empresa.get('Telefone', 'Não Informado')}<br>
                        <b>🔍 Fonte:</b> {empresa.get('Fonte', 'Manual')}<br>
                        <b>🎯 Endereço:</b> {empresa.get('Endereco', 'Não disponível')}
                    </div>
                    """
                    
                    folium.Marker(
                        location=[empresa['Latitude'], empresa['Longitude']],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=f"{empresa['Nome']} ({empresa.get('Fonte', 'Manual')})",
                        icon=folium.Icon(color=cor, icon='industry', prefix='fa')
                    ).add_to(mapa)
                
                st_folium(mapa, width='100%', height=500, returned_objects=[])
    
    # Download - CORREÇÃO: Botão só aparece se houver dados
    if not df_final.empty:
        st.download_button(
            label="📥 Baixar Dados Completos",
            data=df_final.to_csv(index=False, encoding='utf-8-sig'),
            file_name="algodoeiras_mt_completo.csv",
            mime="text/csv"
        )

else:
    st.info("👆 Use as opções acima para adicionar empresas ao mapa")

# ==============================================================================
# INSTRUÇÕES
# ==============================================================================

with st.expander("📖 Como usar este aplicativo"):
    st.markdown("""
    **1. Web Scraping Automático** (Recomendado primeiro)
    - Clique em "Tentar Web Scraping Automático"
    - O sistema tenta coletar dados do site da AMPA
    - Se funcionar, você terá uma base inicial de empresas
    
    **2. Inserção Manual** (Quando o scraping falha)
    - Digite o nome exato da empresa
    - Clique em "Buscar Localização"
    - O sistema geocodifica e adiciona ao mapa
    
    **Dicas:**
    - Use nomes completos das empresas para melhor geocodificação
    - Empresas com 'LTDA', 'S.A.' são detectadas automaticamente
    - Marcadores azuis = inserção manual | Marcadores verdes = web scraping
    - Se encontrar erros, use a inserção manual para adicionar empresas específicas
    """)
