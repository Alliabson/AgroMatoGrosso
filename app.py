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
st.markdown("Sistema completo para mapeamento do setor algodoeiro")

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
    geolocator = Nominatim(user_agent="algodoeiras_mt_app_v5")
    
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
# WEB SCRAPING ESPECÍFICO PARA CADA PÁGINA
# ==============================================================================

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_cooperativas():
    """
    Web scraping específico para a página de cooperativas
    """
    st.write("🏢 Coletando dados de cooperativas...")
    
    url = "https://ampa.com.br/consulta-cooperativas/"
    lista_cooperativas = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Procura por tabelas na página
        tabelas = soup.find_all('table')
        
        if not tabelas:
            st.warning("❌ Nenhuma tabela encontrada na página de cooperativas")
            return pd.DataFrame()
        
        for tabela in tabelas:
            # Encontra todas as linhas da tabela
            linhas = tabela.find_all('tr')
            
            # Pega o cabeçalho para entender a estrutura
            if len(linhas) > 0:
                cabecalho = [th.get_text(strip=True) for th in linhas[0].find_all(['th', 'td'])]
                st.write(f"📋 Estrutura da tabela: {cabecalho}")
            
            # Processa as linhas de dados (pula o cabeçalho)
            for linha in linhas[1:]:
                celulas = linha.find_all(['td', 'th'])
                if len(celulas) >= 2:  # Pelo menos 2 colunas
                    # Diferentes estruturas possíveis
                    if len(celulas) >= 4:
                        # Estrutura: Fantasia, Cooperativas, Email, Fone
                        fantasia = celulas[0].get_text(strip=True)
                        nome_cooperativa = celulas[1].get_text(strip=True)
                        email = celulas[2].get_text(strip=True) if len(celulas) > 2 else "Não Informado"
                        telefone = celulas[3].get_text(strip=True) if len(celulas) > 3 else "Não Informado"
                        
                        # Prefere o nome da cooperativa, mas usa fantasia se necessário
                        nome_final = nome_cooperativa if nome_cooperativa else fantasia
                        
                    elif len(celulas) == 2:
                        # Estrutura simples: Nome, Telefone
                        nome_final = celulas[0].get_text(strip=True)
                        telefone = celulas[1].get_text(strip=True)
                        email = "Não Informado"
                    
                    else:
                        continue
                    
                    if nome_final and is_pessoa_juridica(nome_final):
                        lista_cooperativas.append({
                            'Nome': nome_final,
                            'Telefone': telefone,
                            'Email': email,
                            'Tipo': 'Cooperativa',
                            'Cidade': 'Mato Grosso',
                            'Estado': 'MT'
                        })
        
        if lista_cooperativas:
            df = pd.DataFrame(lista_cooperativas)
            df = df.drop_duplicates(subset=['Nome'])
            st.success(f"✅ Cooperativas: {len(df)} encontradas")
            return geocodificar_empresas_em_lote(df)
        else:
            st.warning("⚠️ Nenhuma cooperativa encontrada")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Erro ao coletar cooperativas: {str(e)}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=3600)
def carregar_associados_ativos():
    """
    Web scraping específico para a página de associados ativos
    """
    st.write("👥 Coletando dados de associados ativos...")
    
    url = "https://ampa.com.br/consulta-associados-ativos/"
    lista_associados = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Procura por tabelas na página
        tabelas = soup.find_all('table')
        
        if not tabelas:
            st.warning("❌ Nenhuma tabela encontrada na página de associados")
            return pd.DataFrame()
        
        for tabela in tabelas:
            # Encontra todas as linhas da tabela
            linhas = tabela.find_all('tr')
            
            # Processa as linhas de dados
            for linha in linhas:
                celulas = linha.find_all(['td', 'th'])
                if len(celulas) >= 2:  # Pelo menos 2 colunas
                    nome = celulas[0].get_text(strip=True)
                    telefone = celulas[1].get_text(strip=True) if len(celulas) > 1 else "Não Informado"
                    
                    # Pula cabeçalhos e linhas vazias
                    if not nome or nome.lower() in ['associado', 'nome', 'empresa']:
                        continue
                    
                    # Filtra apenas pessoas jurídicas
                    if is_pessoa_juridica(nome):
                        lista_associados.append({
                            'Nome': nome,
                            'Telefone': telefone,
                            'Email': "Não Informado",
                            'Tipo': 'Associado Ativo',
                            'Cidade': 'Mato Grosso',
                            'Estado': 'MT'
                        })
        
        if lista_associados:
            df = pd.DataFrame(lista_associados)
            df = df.drop_duplicates(subset=['Nome'])
            st.success(f"✅ Associados ativos: {len(df)} encontrados")
            return geocodificar_empresas_em_lote(df)
        else:
            st.warning("⚠️ Nenhum associado ativo (PJ) encontrado")
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
                st.session_state.empresas_mapeadas = df_cooperativas
                st.rerun()
            else:
                st.error("❌ Não foi possível coletar cooperativas")

with col2:
    if st.button("👥 Coletar Associados Ativos", type="primary", use_container_width=True):
        with st.spinner('Coletando dados de associados ativos...'):
            df_associados = carregar_associados_ativos()
            if not df_associados.empty:
                st.session_state.empresas_mapeadas = df_associados
                st.rerun()
            else:
                st.error("❌ Não foi possível coletar associados ativos")

# Botão para limpar dados
if st.button("🗑️ Limpar Todos os Dados", use_container_width=True):
    st.session_state.empresas_mapeadas = pd.DataFrame()
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
    
    # Tabela de dados
    st.subheader("📋 Lista de Empresas")
    colunas_para_mostrar = ['Nome', 'Tipo', 'Cidade', 'Telefone']
    if 'Email' in df_filtrado.columns:
        colunas_para_mostrar.append('Email')
    if 'Fonte' in df_filtrado.columns:
        colunas_para_mostrar.append('Fonte')
    
    st.dataframe(
        df_filtrado[colunas_para_mostrar].reset_index(drop=True),
        use_container_width=True,
        height=400
    )
    
    # Mapa
    st.subheader("🗺️ Mapa de Localizações")
    
    # Filtra empresas com coordenadas válidas
    df_mapa = df_filtrado.dropna(subset=['Latitude', 'Longitude']).copy()
    
    if df_mapa.empty:
        st.warning("Nenhuma empresa com coordenadas válidas para exibir no mapa.")
    else:
        # Centro do mapa em Mato Grosso
        map_center = [-12.6819, -56.9211]
        if len(df_mapa) > 0:
            map_center = [df_mapa['Latitude'].mean(), df_mapa['Longitude'].mean()]
        
        mapa = folium.Map(location=map_center, zoom_start=7)

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
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
    
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
    
    1. **Coleta Automática:** Escolha entre cooperativas ou associados ativos
    2. **Inserção Manual:** Adicione empresas específicas manualmente
    3. **Filtros:** Use os filtros para explorar os dados
    4. **Mapa:** Visualize todas as localizações no mapa interativo
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
    
    1. **Coleta Específica por Categoria** - Botões separados para cada tipo
    2. **Inserção Manual Flexível** - Com lista sugerida e campo customizado
    3. **Filtros Avançados** - Por tipo e cidade
    4. **Mapa Colorido** - Cores diferentes para cada tipo de empresa
    5. **Exportação de Dados** - Download em CSV
    
    **📊 Legenda do Mapa:**
    - 🔵 **Azul**: Cooperativas
    - 🟢 **Verde**: Associados Ativos  
    - 🔴 **Vermelho**: Algodoeiras
    - 🟠 **Laranja**: Outros tipos
    
    **💡 Dica:** Comece coletando as cooperativas, depois os associados ativos!
    """)
