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

st.title("🌱 Mapa das Algodoeiras e Cooperativas de Mato Grosso")
st.markdown("Sistema completo para mapeamento e visualização interativa do setor algodoeiro.")

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
    Geocodifica uma empresa individual com múltiplas estratégias
    """
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v7")
    
    try:
        # Estratégias de busca melhoradas
        queries = [
            f"{nome}, {cidade}, {estado}, Brasil",
            f"{nome}, {estado}, Brasil", 
            f"{tipo} {nome}, {estado}, Brasil",
            f"{nome} algodão, {estado}, Brasil",
            f"{cidade}, {estado}, Brasil"
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
                'Tipo': tipo,
                'Cidade': cidade_detectada,
                'Estado': estado,
                'Latitude': latitude,
                'Longitude': longitude,
                'Endereco': endereco,
                'Fonte': 'Manual'
            }
        else:
            # Fallback: usa coordenadas aproximadas de Mato Grosso
            return {
                'Nome': nome,
                'Telefone': "Não Informado", 
                'Tipo': tipo,
                'Cidade': cidade,
                'Estado': estado,
                'Latitude': -12.6819,
                'Longitude': -56.9211,
                'Endereco': f"Localização aproximada - {cidade}, {estado}",
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
# WEB SCRAPING ROBUSTO - MÚLTIPLAS ESTRATÉGIAS
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
        # Procura por padrões que parecem dados de cooperativas
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
                
                # Se não encontrou pelo regex, mas a linha parece ser uma cooperativa
                if 'cooperativa' in linha_limpa.lower() and cooperativas_encontradas == 0:
                    # Tenta extrair o nome da cooperativa manualmente
                    partes = linha_limpa.split()
                    nome_coop = ' '.join(partes[:4])  # Pega as primeiras palavras
                    if is_pessoa_juridica(nome_coop):
                        lista_cooperativas.append({
                            'Nome': nome_coop,
                            'Telefone': "Não Informado",
                            'Email': "Não Informado",
                            'Tipo': 'Cooperativa',
                            'Cidade': 'Mato Grosso',
                            'Estado': 'MT'
                        })
                        cooperativas_encontradas += 1
        
        # ESTRATÉGIA 4: Buscar em elementos específicos
        elementos_texto = soup.find_all(['p', 'div', 'span', 'li'])
        for elemento in elementos_texto:
            texto = elemento.get_text(strip=True)
            if 'cooperativa' in texto.lower() and len(texto) > 10 and len(texto) < 100:
                if is_pessoa_juridica(texto):
                    lista_cooperativas.append({
                        'Nome': texto,
                        'Telefone': "Não Informado",
                        'Email': "Não Informado",
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
            st.warning("""
            ⚠️ Nenhuma cooperativa encontrada automaticamente. 
            
            **Possíveis causas:**
            - A estrutura da página mudou
            - Os dados estão em um formato diferente
            - A página requer JavaScript
            
            **Solução:** Use a inserção manual abaixo para adicionar cooperativas específicas.
            """)
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
            
            # Se não tem telefone, mas parece ser um nome de empresa
            elif is_pessoa_juridica(texto):
                lista_associados.append({
                    'Nome': texto,
                    'Telefone': "Não Informado",
                    'Email': "Não Informado",
                    'Tipo': 'Associado Ativo',
                    'Cidade': 'Mato Grosso',
                    'Estado': 'MT'
                })
                associados_encontrados += 1
        
        # ESTRATÉGIA 2: Buscar em todo o texto da página
        texto_completo = soup.get_text()
        linhas = texto_completo.split('\n')
        
        for linha in linhas:
            linha_limpa = linha.strip()
            if len(linha_limpa) > 5 and len(linha_limpa) < 100:
                # Verifica se é um nome de empresa
                if is_pessoa_juridica(linha_limpa) and linha_limpa not in [a['Nome'] for a in lista_associados]:
                    lista_associados.append({
                        'Nome': linha_limpa,
                        'Telefone': "Não Informado",
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
            st.warning("""
            ⚠️ Nenhum associado ativo (PJ) encontrado automaticamente.
            
            **Possíveis causas:**
            - A estrutura da página mudou
            - Os dados estão em formato dinâmico (JavaScript)
            - A lista pode conter principalmente pessoas físicas
            
            **Solução:** Use a inserção manual abaixo para adicionar empresas específicas.
            """)
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
                # Adiciona ao existente em vez de substituir
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
    # Reseta a visualização do mapa
    st.session_state.map_center = [-12.6819, -56.9211]
    st.session_state.map_zoom = 7
    st.rerun()

# ==============================================================================
# SEÇÃO 2: INSERÇÃO MANUAL
# ==============================================================================

st.header("✍️ Inserção Manual")

# Lista de empresas conhecidas para facilitar
empresas_sugeridas = [
    "Algodoeira Reunidas",
    "3ab Produtos Agricolas S.A.",
    "Cooperativa Aliança dos Produtores do Parecis",
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
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        nome_empresa = st.selectbox(
            "Nome da Empresa:",
            options=empresas_sugeridas,
            index=0,
            help="Selecione ou digite o nome da empresa"
        )
        
        nome_custom = st.text_input(
            "Ou digite o nome manualmente:",
            placeholder="Ex: Algodoeira São João",
            help="Digite o nome completo da empresa"
        )
        
        nome_final = nome_custom if nome_custom else nome_empresa
    
    with col2:
        tipo_empresa = st.selectbox(
            "Tipo:",
            options=["Algodoeira", "Cooperativa", "Associado Ativo", "Outro"],
            index=0
        )
    
    with col3:
        cidade_empresa = st.text_input(
            "Cidade:",
            value="Mato Grosso",
            help="Cidade onde a empresa está localizada"
        )
    
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

    # --- NOVA SEÇÃO: MAPA PRIMEIRO ---
    st.subheader("🗺️ Mapa de Localizações")
    
    # Filtra empresas com coordenadas válidas
    df_mapa = df_filtrado.dropna(subset=['Latitude', 'Longitude']).copy()
    
    if df_mapa.empty:
        st.warning("Nenhuma empresa com coordenadas válidas para exibir no mapa com os filtros atuais.")
    else:
        # Usa o centro e zoom do session_state
        mapa = folium.Map(
            location=st.session_state.map_center, 
            zoom_start=st.session_state.map_zoom, 
            tiles="OpenStreetMap" # Tile inicial
        )

        # ADIÇÃO DE NOVAS CAMADAS DE MAPA (TILE LAYERS)
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
        
        # Adiciona o controle de camadas ao mapa
        folium.LayerControl().add_to(mapa)

        st_folium(mapa, width='100%', height=500, returned_objects=[], 
                  center=st.session_state.map_center, zoom=st.session_state.map_zoom)

    # --- NOVA SEÇÃO: LISTA DE EMPRESAS INTERATIVA ---
    st.subheader("📋 Lista de Empresas")

    # Função para atualizar o centro do mapa
    def set_map_center(lat, lon):
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom = 14 # Zoom mais próximo ao focar

    # Cabeçalho da lista
    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
    with col1:
        st.markdown("**Nome**")
    with col2:
        st.markdown("**Tipo**")
    with col3:
        st.markdown("**Cidade**")
    with col4:
        st.markdown("**Ação**")

    # Itera sobre o dataframe filtrado para criar a lista interativa
    for index, row in df_filtrado.reset_index(drop=True).iterrows():
        st.divider()
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
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
                    "Ver no Mapa", 
                    key=f"goto_{index}", 
                    on_click=set_map_center, 
                    args=(row['Latitude'], row['Longitude']),
                    use_container_width=True
                )
    
    st.divider()
    
    # Download
    st.download_button(
        label="📥 Baixar Dados Completos (CSV)",
        data=df_final.to_csv(index=False, encoding='utf-8-sig'),
        file_name="empresas_algodao_mato_grosso.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    st.info("""
    👆 **Para começar:**
    
    1. **Coleta Automática:** Escolha entre cooperativas ou associados ativos.
    2. **Inserção Manual:** Adicione empresas específicas manualmente.
    3. **Filtros:** Use os filtros para explorar os dados.
    4. **Mapa:** Visualize todas as localizações no mapa interativo.
    
    💡 **Dica:** Se a coleta automática não funcionar, use a inserção manual para adicionar empresas específicas.
    """)

# ==============================================================================
# INSTRUÇÕES
# ==============================================================================

with st.expander("📖 Guia de Uso Completo"):
    st.markdown("""
    **🎯 Fontes de Dados:**
    
    - **🏢 Cooperativas:** https://ampa.com.br/consulta-cooperativas/
      - Estrutura: Fantasia, Cooperativas, Email, Fone
      - Exemplo: CAAP, Cooperativa Aliança dos Produtores do Parecis
    
    - **👥 Associados Ativos:** https://ampa.com.br/consulta-associados-ativos/  
      - Estrutura: Associado, Telefone
      - Exemplo: Alexandre Roberto Paludo, (00) 0000-0000
    
    **🔧 Funcionalidades:**
    
    1. **Coleta Específica por Categoria** - Botões separados para cada tipo.
    2. **Inserção Manual Flexível** - Com lista sugerida e campo customizado.
    3. **Filtros Avançados** - Por tipo e cidade.
    4. **Mapa Interativo com Múltiplas Camadas** - Alterne entre visão de rua e satélite.
    5. **Lista Interativa** - Clique em "Ver no Mapa" para focar em uma empresa.
    6. **Exportação de Dados** - Download em CSV.
    
    **📊 Legenda do Mapa:**
    - 🔵 **Azul**: Cooperativas
    - 🟢 **Verde**: Associados Ativos  
    - 🔴 **Vermelho**: Algodoeiras
    - 🟠 **Laranja**: Outros tipos
    
    **🛠️ Solução de Problemas:**
    
    - **Web scraping não funciona?** → Use a inserção manual.
    - **Localização não encontrada?** → Usamos coordenadas aproximadas de MT.
    - **Dados incompletos?** → Combine coleta automática com manual.
    
    💡 **Dica:** Comece coletando as cooperativas, depois os associados ativos!
    """)

# ==============================================================================
# CARREGAMENTO DE DADOS EXTERNOS
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
                    # Filtra apenas PJs
                    df_upload['É_PJ'] = df_upload['Nome'].apply(is_pessoa_juridica)
                    df_pjs = df_upload[df_upload['É_PJ']].copy()
                    
                    if not df_pjs.empty:
                        st.sidebar.write(f"🏢 {len(df_pjs)} empresas são PJs")
                        
                        # Prepara dados para geocodificação
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
                            # Adiciona às empresas existentes
                            if st.session_state.empresas_mapeadas.empty:
                                st.session_state.empresas_mapeadas = df_geocodificado
                            else:
                                # Remove duplicatas
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
