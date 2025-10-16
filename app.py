import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import folium

# ==============================================================================
# PASSO 1: NOSSA BASE DE DADOS
# ==============================================================================
# Esta função cria e retorna nossa lista de empresas.
# No futuro, você pode modificar esta função para ler dados de um arquivo Excel.
# O decorador @st.cache_data garante que os dados sejam carregados apenas uma vez.
@st.cache_data
def carregar_dados():
    """
    Cria e retorna um DataFrame do Pandas com os dados das empresas.
    As coordenadas de Latitude e Longitude são essenciais para o mapa.
    """
    dados_empresas = [
        {"Nome": "Algodoeira XXX de Sapezal", "Tipo": "Algodoeira", "Cidade": "Sapezal", "Estado": "MT", "Latitude": -13.5415, "Longitude": -58.8596},
        {"Nome": "Pluma Agroavícola Ltda", "Tipo": "Algodoeira", "Cidade": "Sapezal", "Estado": "MT", "Latitude": -13.5580, "Longitude": -58.8475},
        {"Nome": "Grão Forte Armazéns", "Tipo": "Armazém de Grãos", "Cidade": "Sapezal", "Estado": "MT", "Latitude": -13.5299, "Longitude": -58.8683},
        {"Nome": "Cooperativa Agroindustrial Parecis", "Tipo": "Algodoeira", "Cidade": "Campo Novo do Parecis", "Estado": "MT", "Latitude": -13.6751, "Longitude": -57.8864},
        {"Nome": "Sementes Girassol", "Tipo": "Produtor de Sementes", "Cidade": "Campo Novo do Parecis", "Estado": "MT", "Latitude": -13.6645, "Longitude": -57.8912},
        {"Nome": "Agroindustrial GGF", "Tipo": "Algodoeira", "Cidade": "Sorriso", "Estado": "MT", "Latitude": -12.5447, "Longitude": -55.7175},
        {"Nome": "Cargill Armazéns Gerais", "Tipo": "Armazém de Grãos", "Cidade": "Sorriso", "Estado": "MT", "Latitude": -12.5591, "Longitude": -55.7288},
        {"Nome": "Gigante Têxtil S.A.", "Tipo": "Algodoeira", "Cidade": "Rondonópolis", "Estado": "MT", "Latitude": -16.4700, "Longitude": -54.6355}
    ]
    # Converte a lista de dicionários em um DataFrame do Pandas
    return pd.DataFrame(dados_empresas)

# ==============================================================================
# PASSO 2: CONFIGURAÇÃO DA INTERFACE DO APLICATIVO
# ==============================================================================

# Define o título da página e o layout (wide ocupa a largura inteira da tela)
st.set_page_config(page_title="Mapa do Agronegócio", layout="wide")

# Título principal da aplicação
st.title("🗺️ Mapa Interativo do Agronegócio")

# Texto descritivo
st.markdown("Selecione o tipo de empresa na barra lateral para visualizar no mapa.")

# Carrega os dados usando a função que criamos
df_empresas = carregar_dados()

# ==============================================================================
# PASSO 3: CRIAÇÃO DO FILTRO NA BARRA LATERAL
# ==============================================================================

# Adiciona um cabeçalho à barra lateral
st.sidebar.header("Filtros")

# Pega os valores únicos da coluna 'Tipo' para criar as opções do filtro
# A função sorted() coloca as opções em ordem alfabética
# Adicionamos "Exibir Todas" para dar ao usuário a opção de limpar o filtro
tipos_disponiveis = ["Exibir Todas"] + sorted(df_empresas['Tipo'].unique().tolist())

# Cria o componente de menu suspenso (selectbox)
tipo_selecionado = st.sidebar.selectbox(
    "Selecione o Tipo de Empresa:",
    tipos_disponiveis
)

# ==============================================================================
# PASSO 4: LÓGICA DE FILTRAGEM E EXIBIÇÃO DOS DADOS
# ==============================================================================

# Filtra o DataFrame com base na seleção do usuário
if tipo_selecionado == "Exibir Todas":
    # Se "Exibir Todas" for selecionado, o DataFrame filtrado é igual ao original
    df_filtrado = df_empresas
else:
    # Caso contrário, filtra o DataFrame para manter apenas as linhas onde 'Tipo' é igual ao selecionado
    df_filtrado = df_empresas[df_empresas['Tipo'] == tipo_selecionado]

# Verifica se o DataFrame filtrado contém algum dado
if df_filtrado.empty:
    st.warning("Nenhuma empresa encontrada para o tipo selecionado.")
else:
    # Exibe um subtítulo com a contagem de resultados
    st.subheader(f"Exibindo {len(df_filtrado)} empresa(s) do tipo '{tipo_selecionado}'")
    
    # Mostra uma tabela com os dados filtrados. Selecionamos apenas algumas colunas para exibir.
    st.dataframe(df_filtrado[['Nome', 'Cidade', 'Estado']])
    
    # Adiciona um subtítulo para a seção do mapa
    st.subheader("Mapa de Localizações")
    
    # Calcula o centro do mapa com base na média das coordenadas dos pontos filtrados
    map_center = [df_filtrado['Latitude'].mean(), df_filtrado['Longitude'].mean()]
    
    # Cria o objeto do mapa Folium. O zoom_start define o nível de zoom inicial.
    mapa = folium.Map(location=map_center, zoom_start=7)
    
    # Itera sobre cada linha do DataFrame filtrado para adicionar um marcador no mapa
    for index, empresa in df_filtrado.iterrows():
        # Cria o texto que aparecerá na janela popup ao clicar no marcador
        popup_html = f"""
        <b>{empresa.get('Nome', 'N/A')}</b><br>
        <hr>
        <b>Cidade:</b> {empresa.get('Cidade', 'N/A')}<br>
        <b>Tipo:</b> {empresa.get('Tipo', 'N/A')}
        """
        
        # Adiciona o marcador ao mapa
        folium.Marker(
            location=[empresa['Latitude'], empresa['Longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=empresa.get('Nome', 'N/A') # Texto que aparece ao passar o mouse
        ).add_to(mapa)
    
    # Renderiza o mapa Folium dentro do aplicativo Streamlit
    st_folium(mapa, width='100%', height=500, returned_objects=[])
