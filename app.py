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
    Esta é a nossa função "funil".
    """
    if not nome or pd.isna(nome):
        return False
        
    # Lista de palavras-chave que indicam ser uma empresa
    keywords = ['ltda', 's.a', 's/a', 'agropecuária', 'agrícola', 
                'fazenda', 'grupo', 'agro', 'produtos', 'investimentos',
                'comércio', 'agricola', 'algodão', 'algodao', 'cotton',
                'industrial', 'exportação', 'exportadora', 'comercial']
    
    nome_lower = nome.lower()
    for keyword in keywords:
        if keyword in nome_lower:
            return True
    return False

def extrair_cidade_do_nome(nome):
    """
    Tenta extrair a cidade do nome da empresa quando disponível
    """
    padroes_cidade = [
        r'\- ([A-Za-z\s]+)$',  # Padrão "Empresa - Cidade"
        r'\- ([A-Za-z\s]+) \-', # Padrão "Empresa - Cidade -"
        r'([A-Za-z\s]+) \- MT$' # Padrão "Cidade - MT"
    ]
    
    for padrao in padroes_cidade:
        match = re.search(padrao, nome)
        if match:
            return match.group(1).strip()
    
    return "Não Informada"

# ==============================================================================
# FUNÇÃO MESTRA PARA COLETAR E PROCESSAR OS DADOS
# ==============================================================================

@st.cache_data(show_spinner=False)
def carregar_e_processar_dados():
    """
    Função unificada que executa o web scraping de tabelas (com paginação) 
    e a geocodificação, filtrando apenas por pessoas jurídicas.
    """
    # --- Parte 1: Web Scraping de Tabela com Paginação ---
    st.write("🌐 Iniciando coleta de dados via web scraping...")
    
    url_base = "https://ampa.com.br/consulta-associados-ativos/"
    lista_empresas = []
    pagina_num = 1
    max_paginas = 20  # Limite de segurança

    while pagina_num <= max_paginas:
        st.write(f"📄 Coletando dados da página {pagina_num}...")
        
        # Constrói a URL da página atual
        if pagina_num == 1:
            url_atual = url_base
        else:
            url_atual = f"{url_base}page/{pagina_num}/"
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url_atual, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Verifica se a página existe
            if response.status_code == 404 and pagina_num > 1:
                st.write("✅ Todas as páginas foram coletadas.")
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Procura por tabelas - método mais flexível
            tabelas = soup.find_all('table')
            
            if not tabelas:
                if pagina_num == 1:
                    st.error("❌ Não foi possível encontrar tabelas na página. A estrutura do site pode ter mudado.")
                    st.info("💡 Dica: Verifique se o site https://ampa.com.br/consulta-associados-ativos/ está acessível e contém a lista de associados.")
                break

            empresas_encontradas_pagina = 0
            
            for tabela in tabelas:
                # Itera sobre todas as linhas da tabela
                for linha in tabela.find_all('tr'):
                    celulas = linha.find_all(['td', 'th'])
                    if len(celulas) >= 2:  # Pelo menos 2 colunas
                        nome = celulas[0].get_text(strip=True)
                        
                        # Pula cabeçalhos e linhas vazias
                        if not nome or nome.lower() in ['nome', 'empresa', 'associado']:
                            continue
                            
                        telefone = celulas[1].get_text(strip=True) if len(celulas) > 1 else "Não Informado"
                        
                        # APLICA O FUNIL: Processa apenas se for uma pessoa jurídica
                        if is_pessoa_juridica(nome):
                            cidade = extrair_cidade_do_nome(nome)
                            
                            lista_empresas.append({
                                'Nome': nome,
                                'Telefone': telefone,
                                'Tipo': 'Algodoeira',
                                'Cidade': cidade,
                                'Estado': 'MT'
                            })
                            empresas_encontradas_pagina += 1

            st.write(f"✅ {empresas_encontradas_pagina} empresas encontradas na página {pagina_num}")
            
            # Verifica se há próxima página
            next_button = soup.find('a', class_='next')
            if not next_button:
                # Alternativa: procura por numeração de página
                pagination = soup.find('div', class_=['pagination', 'nav-links'])
                if not pagination:
                    st.write("✅ Última página alcançada.")
                    break
            
            pagina_num += 1
            time.sleep(2)  # Respeitoso com o servidor

        except requests.exceptions.RequestException as e:
            st.error(f"❌ Erro de conexão na página {pagina_num}: {e}")
            break
        except Exception as e:
            st.error(f"❌ Erro inesperado na página {pagina_num}: {e}")
            break

    if not lista_empresas:
        st.error("❌ Nenhuma empresa (Pessoa Jurídica) foi coletada.")
        st.info("""
        **Possíveis soluções:**
        1. Verifique se o site https://ampa.com.br/consulta-associados-ativos/ está online
        2. A estrutura do site pode ter mudado
        3. Tente ajustar as palavras-chave na função `is_pessoa_juridica`
        """)
        return pd.DataFrame()
        
    df = pd.DataFrame(lista_empresas)
    st.success(f"📊 Coleta concluída: {len(df)} empresas (PJs) encontradas em {pagina_num-1} páginas.")

    # --- Parte 2: Geocodificação ---
    if len(df) > 0:
        st.write("🗺️ Iniciando geocodificação. Este processo pode ser lento...")
        
        # Filtra empresas únicas para evitar geocodificação duplicada
        df_unique = df.drop_duplicates(subset=['Nome']).copy()
        
        geolocator = Nominatim(user_agent="algodoeiras_mt_app")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)

        latitudes = []
        longitudes = []
        cidades_corrigidas = []
        enderecos_completos = []
        
        progress_bar = st.progress(0)
        total_empresas = len(df_unique)
        status_text = st.empty()

        for index, row in df_unique.iterrows():
            status_text.text(f"📍 Geocodificando: {row['Nome'][:50]}...")
            
            location = None
            query_attempts = [
                f"{row['Nome']}, Mato Grosso, Brasil",
                f"{row['Cidade']}, Mato Grosso, Brasil",
                "Cuiabá, Mato Grosso, Brasil"  # Fallback para capital
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
                enderecos_completos.append(location.address)
                
                # Tenta extrair a cidade do resultado
                address = location.raw.get('address', {})
                cidade = (address.get('city') or 
                         address.get('town') or 
                         address.get('village') or 
                         address.get('municipality') or 
                         row['Cidade'])
                cidades_corrigidas.append(cidade)
            else:
                latitudes.append(None)
                longitudes.append(None)
                enderecos_completos.append("Não Localizado")
                cidades_corrigidas.append(row['Cidade'])
            
            progress_bar.progress((index + 1) / total_empresas)

        df_unique['Latitude'] = latitudes
        df_unique['Longitude'] = longitudes
        df_unique['Cidade_Geocodificada'] = cidades_corrigidas
        df_unique['Endereco'] = enderecos_completos
        
        # Remove empresas que não foram geocodificadas
        df_final = df_unique.dropna(subset=['Latitude', 'Longitude']).copy()
        
        status_text.text("✅ Geocodificação finalizada!")
        st.success(f"🗺️ {len(df_final)} empresas foram geocodificadas com sucesso.")
        
        return df_final
    else:
        return pd.DataFrame()

# ==============================================================================
# INTERFACE DO APLICATIVO STREAMLIT
# ==============================================================================

st.set_page_config(
    page_title="Mapa das Algodoeiras de MT", 
    layout="wide",
    page_icon="🌱"
)

st.title("🌱 Mapa das Algodoeiras de Mato Grosso")
st.markdown("""
**Fonte dos dados:** [AMPA - Associação Mato-grossense dos Produtores de Algodão](https://ampa.com.br/consulta-associados-ativos/)

Os dados são coletados e processados em tempo real através de web scraping.
""")

# Barra lateral com informações
st.sidebar.header("ℹ️ Sobre o App")
st.sidebar.info("""
Este aplicativo coleta dados de algodoeiras associadas à AMPA e as exibe em um mapa interativo.

**Funcionalidades:**
- Web scraping automático do site da AMPA
- Filtro inteligente para pessoas jurídicas
- Geocodificação para obter coordenadas
- Visualização em mapa interativo
""")

st.sidebar.header("🎛️ Filtros")

# Carregamento dos dados
with st.spinner('🔄 Por favor, aguarde... Coletando e processando dados...'):
    df_empresas = carregar_e_processar_dados()

if df_empresas.empty:
    st.error("Não foi possível carregar os dados. Tente recarregar a página ou verificar a conexão com o site da AMPA.")
else:
    st.success(f"✅ Processo concluído! **{len(df_empresas)}** algodoeiras foram localizadas e mapeadas.")
    
    # Filtros
    cidades_disponiveis = ["Exibir Todas"] + sorted(df_empresas['Cidade_Geocodificada'].unique().tolist())
    cidade_selecionada = st.sidebar.selectbox("Filtrar por Cidade:", cidades_disponiveis)

    if cidade_selecionada == "Exibir Todas":
        df_filtrado = df_empresas
    else:
        df_filtrado = df_empresas[df_empresas['Cidade_Geocodificada'] == cidade_selecionada]

    # Estatísticas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Empresas", len(df_filtrado))
    with col2:
        st.metric("Cidades Encontradas", df_filtrado['Cidade_Geocodificada'].nunique())
    with col3:
        st.metric("Tipo", "Algodoeiras")

    if df_filtrado.empty:
        st.warning("Nenhuma empresa encontrada para o filtro selecionado.")
    else:
        # Tabela de dados
        st.subheader("📋 Lista de Algodoeiras")
        st.dataframe(
            df_filtrado[['Nome', 'Telefone', 'Cidade_Geocodificada', 'Estado']].reset_index(drop=True),
            use_container_width=True
        )
        
        # Mapa
        st.subheader("🗺️ Mapa de Localizações")
        
        # Centraliza o mapa em Mato Grosso
        map_center = [-12.6819, -56.9211]  # Coordenadas aproximadas de MT
        if len(df_filtrado) > 0:
            map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
        
        mapa = folium.Map(location=map_center, zoom_start=7)

        # Adiciona marcadores
        for index, empresa in df_filtrado.iterrows():
            popup_html = f"""
            <div style="min-width: 250px">
                <h4>{empresa['Nome']}</h4>
                <hr>
                <b>📍 Cidade:</b> {empresa['Cidade_Geocodificada']}<br>
                <b>📞 Telefone:</b> {empresa['Telefone']}<br>
                <b>🏢 Tipo:</b> {empresa['Tipo']}<br>
                <b>🎯 Endereço:</b> {empresa.get('Endereco', 'Não disponível')}
            </div>
            """
            
            folium.Marker(
                location=[empresa['Latitude'], empresa['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=empresa['Nome'],
                icon=folium.Icon(color='green', icon='leaf', prefix='fa')
            ).add_to(mapa)
        
        # Exibe o mapa
        st_folium(mapa, width='100%', height=600, returned_objects=[])
        
        # Botão de download
        st.download_button(
            label="📥 Baixar Dados em CSV",
            data=df_filtrado.to_csv(index=False, encoding='utf-8-sig'),
            file_name="algodoeiras_mato_grosso.csv",
            mime="text/csv"
        )
