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
        
    # Lista expandida de palavras-chave que indicam ser uma empresa
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
    
    # Verifica palavras-chave
    for keyword in keywords:
        if keyword in nome_lower:
            return True
    
    # Verifica se tem siglas comuns de empresas
    if re.search(r'\b(ltda|s\.a|s/a|eireli|mei|me)\b', nome_lower):
        return True
        
    return False

def extrair_telefone(texto):
    """
    Tenta extrair telefone do texto quando disponível
    """
    if not texto:
        return "Não Informado"
    
    # Padrões comuns de telefone
    padroes_telefone = [
        r'\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4}',  # (XX) XXXXX-XXXX
        r'\d{2}[\s\.-]?\d{4,5}[\s\.-]?\d{4}',    # XX XXXXX XXXX
        r'\(\d{2}\)\s*\d{4,5}-\d{4}',            # (XX) XXXXX-XXXX
    ]
    
    for padrao in padroes_telefone:
        match = re.search(padrao, texto)
        if match:
            return match.group().strip()
    
    return "Não Informado"

def limpar_nome_empresa(nome):
    """
    Remove informações desnecessárias do nome da empresa
    """
    if not nome:
        return nome
    
    # Remove números no início
    nome = re.sub(r'^\d+\s*', '', nome)
    
    # Remove traços e pontos extras
    nome = re.sub(r'\s*-\s*$', '', nome)
    nome = re.sub(r'\s*\.\s*$', '', nome)
    
    return nome.strip()

# ==============================================================================
# FUNÇÃO DE WEB SCRAPING CORRIGIDA
# ==============================================================================

@st.cache_data(show_spinner=False, ttl=3600)  # Cache por 1 hora
def carregar_e_processar_dados():
    """
    Função corrigida para a nova estrutura do site da AMPA
    """
    st.write("🌐 Iniciando coleta de dados do site da AMPA...")
    
    url = "https://ampa.com.br/consulta-associados-ativos/"
    lista_empresas = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Procura por conteúdo principal - estratégias alternativas
        conteudo_selectores = [
            '.entry-content',
            '.post-content', 
            '.content',
            'main',
            'article',
            '.container',
            '#content'
        ]
        
        conteudo = None
        for seletor in conteudo_selectores:
            conteudo = soup.select_one(seletor)
            if conteudo:
                break
        
        # Se não encontrar pelos seletores, usa o body
        if not conteudo:
            conteudo = soup.find('body')
        
        # Encontra todos os elementos de texto que podem ser nomes
        # Procura por elementos que contenham nomes (h1, h2, h3, h4, h5, h6, p, div, li, strong)
        elementos_texto = conteudo.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'li', 'strong', 'span'])
        
        empresas_coletadas = 0
        pessoas_fisicas = 0
        
        for elemento in elementos_texto:
            texto = elemento.get_text(strip=True)
            
            # Pula elementos muito curtos ou que são claramente não-nomes
            if len(texto) < 3 or texto.lower() in ['associado', 'nome', 'empresa', 'telefone', 'endereço']:
                continue
            
            # Pula números isolados
            if texto.isdigit():
                continue
                
            # Limpa o nome
            nome_limpo = limpar_nome_empresa(texto)
            
            if not nome_limpo:
                continue
            
            # APLICA O FUNIL: Processa apenas se for uma pessoa jurídica
            if is_pessoa_juridica(nome_limpo):
                lista_empresas.append({
                    'Nome': nome_limpo,
                    'Telefone': "Não Informado",  # O site não mostra telefones
                    'Tipo': 'Algodoeira',
                    'Cidade': 'Mato Grosso',
                    'Estado': 'MT'
                })
                empresas_coletadas += 1
            else:
                pessoas_fisicas += 1
        
        st.write(f"📊 Análise concluída: {empresas_coletadas} empresas e {pessoas_fisicas} pessoas físicas encontradas")
        
        if not lista_empresas:
            st.error("❌ Nenhuma empresa foi encontrada. A estrutura do site pode ter mudado.")
            st.info("""
            **Sugestões:**
            1. Verifique manualmente o site: https://ampa.com.br/consulta-associados-ativos/
            2. A estrutura pode ser diferente do esperado
            3. Tente ajustar as palavras-chave na função de filtro
            """)
            return pd.DataFrame()
            
        df = pd.DataFrame(lista_empresas)
        st.success(f"✅ Coleta concluída: {len(df)} empresas encontradas.")
        
        # --- Geocodificação ---
        if len(df) > 0:
            st.write("🗺️ Iniciando geocodificação...")
            
            geolocator = Nominatim(user_agent="algodoeiras_mt_app_v2")
            geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

            latitudes = []
            longitudes = []
            cidades_detectadas = []
            enderecos = []
            
            progress_bar = st.progress(0)
            total_empresas = len(df)
            status_text = st.empty()

            for index, row in df.iterrows():
                status_text.text(f"📍 Buscando: {row['Nome'][:40]}...")
                
                location = None
                query_attempts = [
                    f"{row['Nome']}, Mato Grosso, Brasil",
                    "Cuiabá, Mato Grosso, Brasil"  # Fallback
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
                    
                    # Extrai cidade do endereço
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
                
                progress_bar.progress((index + 1) / total_empresas)
                time.sleep(1.2)  # Respeita o rate limiting

            df['Latitude'] = latitudes
            df['Longitude'] = longitudes
            df['Cidade_Detectada'] = cidades_detectadas
            df['Endereco'] = enderecos
            
            # Remove empresas sem coordenadas
            df_final = df.dropna(subset=['Latitude', 'Longitude']).copy()
            
            status_text.text("✅ Geocodificação finalizada!")
            st.success(f"🗺️ {len(df_final)} empresas geocodificadas com sucesso.")
            
            return df_final
        
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Erro de conexão: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
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
st.markdown("""
**Fonte:** [AMPA - Associação Mato-grossense dos Produtores de Algodão](https://ampa.com.br/consulta-associados-ativos/)

Dados coletados automaticamente do site da AMPA.
""")

# Barra lateral
st.sidebar.header("🎛️ Filtros")
st.sidebar.info("""
Este app coleta a lista de associados da AMPA e filtra apenas empresas (pessoas jurídicas) relacionadas ao algodão.
""")

# Carregamento dos dados
with st.spinner('🔄 Coletando dados da AMPA...'):
    df_empresas = carregar_e_processar_dados()

if df_empresas.empty:
    st.error("Não foi possível carregar os dados. Tente novamente ou verifique a conexão.")
    
    # Botão para tentar novamente
    if st.button("🔄 Tentar Novamente"):
        st.cache_data.clear()
        st.rerun()
else:
    st.success(f"✅ **{len(df_empresas)}** algodoeiras encontradas!")
    
    # Filtros
    cidades = ["Exibir Todas"] + sorted(df_empresas['Cidade_Detectada'].unique().tolist())
    cidade_selecionada = st.sidebar.selectbox("Filtrar por Cidade:", cidades)

    if cidade_selecionada == "Exibir Todas":
        df_filtrado = df_empresas
    else:
        df_filtrado = df_empresas[df_empresas['Cidade_Detectada'] == cidade_selecionada]

    # Estatísticas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Empresas no Mapa", len(df_filtrado))
    with col2:
        st.metric("Cidades", df_filtrado['Cidade_Detectada'].nunique())
    with col3:
        st.metric("Taxa de Sucesso", f"{(len(df_filtrado)/len(df_empresas))*100:.1f}%")

    if df_filtrado.empty:
        st.warning("Nenhuma empresa encontrada para o filtro selecionado.")
    else:
        # Tabela
        st.subheader("📋 Lista de Algodoeiras")
        st.dataframe(
            df_filtrado[['Nome', 'Cidade_Detectada', 'Estado']].reset_index(drop=True),
            use_container_width=True,
            height=400
        )
        
        # Mapa
        st.subheader("🗺️ Mapa de Localizações")
        
        # Centraliza em Mato Grosso
        map_center = [-12.6819, -56.9211]
        if len(df_filtrado) > 0:
            map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        
        mapa = folium.Map(location=map_center, zoom_start=7)

        for index, empresa in df_filtrado.iterrows():
            popup_html = f"""
            <div style="min-width: 200px">
                <h4>{empresa['Nome']}</h4>
                <hr>
                <b>📍 Cidade:</b> {empresa['Cidade_Detectada']}<br>
                <b>🏢 Tipo:</b> {empresa['Tipo']}<br>
                <b>📞 Telefone:</b> {empresa['Telefone']}
            </div>
            """
            
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa['Nome'],
                icon=folium.Icon(color='green', icon='industry', prefix='fa')
            ).add_to(mapa)
        
        st_folium(mapa, width='100%', height=500, returned_objects=[])
        
        # Download
        st.download_button(
            label="📥 Baixar Dados Completos",
            data=df_filtrado.to_csv(index=False, encoding='utf-8-sig'),
            file_name="algodoeiras_mt.csv",
            mime="text/csv"
        )
