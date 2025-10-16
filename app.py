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
# CONFIGURAÇÃO INICIAL
# ==============================================================================

st.set_page_config(
    page_title="Mapa das Algodoeiras de MT", 
    layout="wide",
    page_icon="🌱"
)

st.title("🌱 Mapa das Algodoeiras de Mato Grosso")
st.markdown("Sistema híbrido: web scraping automático + inserção manual")

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
        'agricultura', 'ranch', 'farm', 'agribusiness',
        'algodoeira', 'agricola', 'agroindustrial'
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
    Geocodifica uma empresa individual com múltiplas estratégias
    """
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v4")
    
    try:
        # Estratégias de busca melhoradas
        queries = [
            f"{nome}, {cidade}, {estado}, Brasil",
            f"{nome}, {estado}, Brasil", 
            f"Algodoeira {nome}, {estado}, Brasil",
            f"{nome} algodão, {estado}, Brasil",
            f"{nome} cotton, {estado}, Brasil",
            f"{cidade}, {estado}, Brasil"  # Fallback para a cidade
        ]
        
        location = None
        for query in queries:
            try:
                location = geolocator.geocode(query, timeout=15)
                if location and location.latitude and location.longitude:
                    break
            except Exception as e:
                continue
        
        if location and location.latitude and location.longitude:
            endereco = location.address
            latitude = location.latitude
            longitude = location.longitude
            
            # Extrai cidade do endereço
            address_dict = location.raw.get('address', {})
            cidade_detectada = (address_dict.get('city') or 
                              address_dict.get('town') or 
                              address_dict.get('village') or 
                              address_dict.get('municipality') or 
                              address_dict.get('county') or
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
            # Fallback: usa coordenadas aproximadas de Mato Grosso
            st.warning(f"⚠️ Usando localização aproximada para: {nome}")
            return {
                'Nome': nome,
                'Telefone': "Não Informado", 
                'Tipo': 'Algodoeira',
                'Cidade': cidade,
                'Estado': estado,
                'Latitude': -12.6819,  # Coordenadas aproximadas de MT
                'Longitude': -56.9211,
                'Endereco': f"Localização aproximada - {cidade}, {estado}",
                'Fonte': 'Manual (Aproximado)'
            }
            
    except Exception as e:
        st.error(f"❌ Erro na geocodificação de {nome}: {e}")
        # Fallback em caso de erro
        return {
            'Nome': nome,
            'Telefone': "Não Informado",
            'Tipo': 'Algodoeira', 
            'Cidade': cidade,
            'Estado': estado,
            'Latitude': -12.6819,
            'Longitude': -56.9211,
            'Endereco': f"Localização aproximada - {cidade}, {estado}",
            'Fonte': 'Manual (Erro)'
        }

# ==============================================================================
# WEB SCRAPING MELHORADO
# ==============================================================================

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_dados_web_scraping():
    """
    Web scraping melhorado para o site da AMPA
    """
    st.write("🌐 Iniciando web scraping da AMPA...")
    
    url = "https://ampa.com.br/consulta-associados-ativos/"
    lista_empresas = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Estratégia 1: Busca por elementos com texto que parecem nomes de empresas
        elementos_potenciais = soup.find_all(['div', 'p', 'li', 'span', 'strong', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        empresas_encontradas = set()
        
        for elemento in elementos_potenciais:
            texto = elemento.get_text(strip=True)
            
            # Filtra textos muito curtos ou que são claramente não-nomes
            if (len(texto) < 4 or 
                len(texto) > 100 or
                texto.lower() in ['associado', 'nome', 'empresa', 'telefone', 'endereço', 'consulta', 'ativos'] or
                texto.isdigit() or
                '©' in texto or
                'copyright' in texto.lower()):
                continue
            
            # Verifica se é pessoa jurídica
            if is_pessoa_juridica(texto):
                if texto not in empresas_encontradas:
                    empresas_encontradas.add(texto)
                    lista_empresas.append({
                        'Nome': texto,
                        'Telefone': "Não Informado",
                        'Tipo': 'Algodoeira',
                        'Cidade': 'Mato Grosso',
                        'Estado': 'MT'
                    })
        
        # Estratégia 2: Busca por padrões comuns em nomes de empresas
        texto_completo = soup.get_text()
        linhas = texto_completo.split('\n')
        
        for linha in linhas:
            linha_limpa = linha.strip()
            if (len(linha_limpa) > 4 and 
                len(linha_limpa) < 100 and
                is_pessoa_juridica(linha_limpa) and
                linha_limpa not in empresas_encontradas):
                
                empresas_encontradas.add(linha_limpa)
                lista_empresas.append({
                    'Nome': linha_limpa,
                    'Telefone': "Não Informado", 
                    'Tipo': 'Algodoeira',
                    'Cidade': 'Mato Grosso',
                    'Estado': 'MT'
                })
        
        if lista_empresas:
            df = pd.DataFrame(lista_empresas)
            df = df.drop_duplicates(subset=['Nome'])
            st.success(f"✅ Web scraping: {len(df)} empresas encontradas")
            
            # Geocodificação em lote
            return geocodificar_empresas_em_lote(df)
        else:
            st.warning("⚠️ Nenhuma empresa encontrada via web scraping. O site pode ter mudado.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Erro no web scraping: {str(e)}")
        return pd.DataFrame()

def geocodificar_empresas_em_lote(df):
    """
    Geocodifica empresas em lote com fallbacks
    """
    if df.empty:
        return df
        
    st.write("🗺️ Geocodificando empresas...")
    
    geolocator = Nominatim(user_agent="algodoeiras_mt_batch_v1")
    
    resultados = []
    total_empresas = len(df)
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for index, row in df.iterrows():
        progresso = min((index + 1) / total_empresas, 1.0)
        progress_bar.progress(progresso)
        status_text.text(f"Processando: {row['Nome'][:30]}... ({index + 1}/{total_empresas})")
        
        # Geocodifica cada empresa
        empresa_geocodificada = geocodificar_empresa(row['Nome'])
        if empresa_geocodificada:
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

# ==============================================================================
# SEÇÃO 1: WEB SCRAPING AUTOMÁTICO
# ==============================================================================

st.header("🔍 Coleta Automática")

col1, col2 = st.columns([3, 1])
with col1:
    if st.button("🔄 Executar Web Scraping", type="primary", use_container_width=True):
        with st.spinner('Coletando e processando dados da AMPA...'):
            df_scraping = carregar_dados_web_scraping()
            if not df_scraping.empty:
                st.session_state.empresas_mapeadas = df_scraping
                st.rerun()
            else:
                st.error("❌ Web scraping não retornou dados. Use a inserção manual abaixo.")

with col2:
    if st.button("🗑️ Limpar Dados", use_container_width=True):
        st.session_state.empresas_mapeadas = pd.DataFrame()
        st.rerun()

# ==============================================================================
# SEÇÃO 2: INSERÇÃO MANUAL MELHORADA
# ==============================================================================

st.header("✍️ Inserção Manual")

# Lista de empresas conhecidas para facilitar
empresas_sugeridas = [
    "Algodoeira Reunidas",
    "3ab Produtos Agricolas S.A.",
    "Amaggi Agro",
    "Bom Futuro Agro",
    "Scheffer Agro",
    "Agropecuária Maggi",
    "SLC Agrícola",
    "Brasil Agro",
    "Agro Santa Rosa",
    "Cotton Brasil"
]

with st.form("form_insercao_manual"):
    col1, col2 = st.columns([2, 1])
    
    with col1:
        nome_empresa = st.selectbox(
            "Nome da Empresa:",
            options=empresas_sugeridas,
            index=0,
            help="Selecione ou digite o nome da empresa algodoeira"
        )
        
        # Campo para digitar manualmente
        nome_custom = st.text_input(
            "Ou digite o nome manualmente:",
            placeholder="Ex: Algodoeira São João",
            help="Digite o nome completo da empresa"
        )
        
        # Usa o nome customizado se fornecido
        nome_final = nome_custom if nome_custom else nome_empresa
    
    with col2:
        cidade_empresa = st.text_input(
            "Cidade:",
            value="Mato Grosso",
            help="Cidade onde a empresa está localizada"
        )
    
    submitted = st.form_submit_button("📍 Buscar e Adicionar ao Mapa", type="secondary", use_container_width=True)
    
    if submitted and nome_final:
        with st.spinner(f'Buscando localização de {nome_final}...'):
            empresa_geocodificada = geocodificar_empresa(nome_final, cidade_empresa)
            
            if empresa_geocodificada:
                nova_empresa_df = pd.DataFrame([empresa_geocodificada])
                
                if st.session_state.empresas_mapeadas.empty:
                    st.session_state.empresas_mapeadas = nova_empresa_df
                else:
                    # Evita duplicatas
                    nomes_existentes = st.session_state.empresas_mapeadas['Nome'].values
                    if nome_final not in nomes_existentes:
                        st.session_state.empresas_mapeadas = pd.concat(
                            [st.session_state.empresas_mapeadas, nova_empresa_df], 
                            ignore_index=True
                        )
                        st.success(f"✅ {nome_final} adicionada ao mapa!")
                    else:
                        st.warning("⚠️ Esta empresa já está na lista!")
                
                st.rerun()

# ==============================================================================
# SEÇÃO 3: VISUALIZAÇÃO DOS DADOS
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
        if 'Fonte' in df_final.columns:
            web_count = len(df_final[df_final['Fonte'] == 'Web Scraping'])
        else:
            web_count = 0
        st.metric("Web Scraping", web_count)
    
    with col4:
        if 'Fonte' in df_final.columns:
            manual_count = len(df_final[df_final['Fonte'].str.contains('Manual')])
        else:
            manual_count = len(df_final)
        st.metric("Manuais", manual_count)
    
    # Tabela de dados
    st.subheader("📋 Lista de Empresas")
    colunas_para_mostrar = ['Nome', 'Cidade', 'Fonte']
    if 'Endereco' in df_final.columns:
        colunas_para_mostrar.append('Endereco')
    
    st.dataframe(
        df_final[colunas_para_mostrar].reset_index(drop=True),
        use_container_width=True,
        height=400
    )
    
    # Mapa
    st.subheader("🗺️ Mapa de Localizações")
    
    # Filtra empresas com coordenadas válidas
    df_mapa = df_final.dropna(subset=['Latitude', 'Longitude']).copy()
    
    if df_mapa.empty:
        st.warning("Nenhuma empresa com coordenadas válidas para exibir no mapa.")
    else:
        # Centro do mapa em Mato Grosso
        map_center = [-12.6819, -56.9211]
        if len(df_mapa) > 0:
            map_center = [df_mapa['Latitude'].mean(), df_mapa['Longitude'].mean()]
        
        mapa = folium.Map(location=map_center, zoom_start=7)

        for index, empresa in df_mapa.iterrows():
            # Define cor baseada na fonte
            if 'Manual' in str(empresa.get('Fonte', '')):
                cor = 'blue'
                icone = 'user'
            else:
                cor = 'green' 
                icone = 'industry'
            
            popup_html = f"""
            <div style="min-width: 250px">
                <h4>{empresa['Nome']}</h4>
                <hr>
                <b>📍 Cidade:</b> {empresa.get('Cidade', 'Não informada')}<br>
                <b>🏢 Tipo:</b> {empresa.get('Tipo', 'Algodoeira')}<br>
                <b>🔍 Fonte:</b> {empresa.get('Fonte', 'Manual')}<br>
                <b>🎯 Endereço:</b> {empresa.get('Endereco', 'Localização aproximada')}
            </div>
            """
            
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa['Nome'],
                icon=folium.Icon(color=cor, icon=icone, prefix='fa')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
    
    # Download
    st.download_button(
        label="📥 Baixar Dados Completos (CSV)",
        data=df_final.to_csv(index=False, encoding='utf-8-sig'),
        file_name="algodoeiras_mato_grosso.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    st.info("""
    👆 **Para começar:**
    
    1. **Clique em 'Executar Web Scraping'** para tentar coleta automática
    2. **Se não funcionar**, use a seção de inserção manual abaixo
    3. **Selecione uma empresa** da lista ou **digite o nome** manualmente
    4. **Clique em 'Buscar e Adicionar ao Mapa'**
    """)

# ==============================================================================
# INSTRUÇÕES
# ==============================================================================

with st.expander("📖 Guia de Uso"):
    st.markdown("""
    **🎯 Como usar este aplicativo:**
    
    **1. Web Scraping Automático** (Primeira tentativa)
    - Clique em "Executar Web Scraping"
    - O sistema tenta coletar dados do site da AMPA
    - Se funcionar, você terá uma base de empresas
    
    **2. Inserção Manual** (Quando o scraping falha)
    - Selecione uma empresa da lista sugerida
    - Ou digite o nome manualmente no campo abaixo
    - Clique em "Buscar e Adicionar ao Mapa"
    - O sistema sempre retorna uma localização (exata ou aproximada)
    
    **🔧 Solução de Problemas:**
    
    - **Web scraping retorna poucas empresas?** → Use a inserção manual
    - **Geocodificação não encontra localização?** → Usamos coordenadas aproximadas de MT
    - **Empresa não está na lista?** → Digite manualmente no campo customizado
    
    **📊 Sobre os dados:**
    - Marcadores **verdes** = Web scraping
    - Marcadores **azuis** = Inserção manual
    - Localizações são sempre fornecidas (exatas ou aproximadas)
    """)
