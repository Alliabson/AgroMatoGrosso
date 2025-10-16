import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

# --- CONFIGURAÇÕES ---
ARQUIVO_ENTRADA = "empresas_agro.csv"
ARQUIVO_SAIDA = "empresas_com_coords.csv"

# --- SCRIPT PRINCIPAL ---
print(f"Iniciando processo de geocodificação do arquivo '{ARQUIVO_ENTRADA}'...")

try:
    # Lê o arquivo CSV que você criou
    df = pd.read_csv(ARQUIVO_ENTRADA)
except FileNotFoundError:
    print(f"\nERRO: O arquivo '{ARQUIVO_ENTRADA}' não foi encontrado.")
    print("Por favor, execute o script 'coletor_dados.py' primeiro.")
    exit()

# Inicializa o geocodificador do OpenStreetMap
geolocator = Nominatim(user_agent="app_agro_geocoder")
# RateLimiter garante que não faremos mais de 1 requisição por segundo, respeitando os limites de uso
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# Listas para armazenar os resultados
latitudes = []
longitudes = []

print("\nIniciando a busca por coordenadas. Isso pode levar alguns minutos...")
# Itera sobre cada linha do DataFrame
for index, row in df.iterrows():
    # Cria uma string de endereço completa para a busca
    # Usa a coluna 'Endereço' se existir, caso contrário, usa Cidade e Estado
    if 'Endereço' in row and pd.notna(row['Endereço']) and "não coletado" not in row['Endereço']:
        endereco_completo = f"{row['Endereço']}, {row['Cidade']}, {row['Estado']}, Brasil"
    else:
        endereco_completo = f"{row['Nome']}, {row['Cidade']}, {row['Estado']}, Brasil"

    
    print(f"  -> Buscando: {endereco_completo}")
    
    location = None
    try:
        # Tenta encontrar a localização
        location = geocode(endereco_completo)
        time.sleep(1) # Pausa adicional para segurança
    except Exception as e:
        print(f"    -> Erro ao processar o endereço: {e}")

    # Verifica se encontrou um local
    if location:
        latitudes.append(location.latitude)
        longitudes.append(location.longitude)
        print(f"    -> Sucesso! Coordenadas encontradas: ({location.latitude}, {location.longitude})")
    else:
        latitudes.append(None) # Adiciona None se não encontrar
        longitudes.append(None)
        print("    -> AVISO: Coordenadas não encontradas para este endereço.")

# Adiciona as novas colunas ao DataFrame
df['Latitude'] = latitudes
df['Longitude'] = longitudes

# Salva o novo DataFrame em um novo arquivo CSV
df.to_csv(ARQUIVO_SAIDA, index=False)

print(f"\nProcesso finalizado! Os dados com as coordenadas foram salvos em '{ARQUIVO_SAIDA}'.")
print("Agora você pode executar o aplicativo Streamlit ('streamlit run app.py').")
