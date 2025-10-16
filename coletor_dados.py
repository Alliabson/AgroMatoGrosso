import requests
from bs4 import BeautifulSoup
import pandas as pd

# --- CONFIGURAÇÕES ---
# URL da página que lista as empresas.
# NOTA: Este é um exemplo. O site real pode ter uma estrutura diferente.
# Se este URL não funcionar, teremos que encontrar a página correta no site da AMPA/ABRAPA.
URL_ALVO = "https://ampa.com.br/associados/" 
ARQUIVO_SAIDA = "empresas_agro.csv"

# --- SCRIPT DE WEB SCRAPING ---
print(f"Iniciando a coleta de dados do site: {URL_ALVO}")

try:
    # 1. Faz a requisição para obter o HTML da página
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
    response = requests.get(URL_ALVO, headers=headers, timeout=15)
    response.raise_for_status() # Lança um erro se a requisição falhar

    # 2. Cria um objeto BeautifulSoup para "parsear" (analisar) o HTML
    soup = BeautifulSoup(response.content, 'lxml')

    # 3. Encontra os elementos que contêm as informações das empresas
    # Esta é a parte mais importante e que pode precisar de ajuste.
    # Precisamos "inspecionar" o HTML do site para encontrar as tags e classes corretas.
    # Exemplo: Supondo que cada empresa esteja numa div com a classe 'item-associado'
    # e o nome dentro de uma tag <h2>.
    
    itens_empresas = soup.find_all('div', class_='dados') # ATENÇÃO: Esta classe é um palpite e pode mudar.
    
    if not itens_empresas:
        print("\nAVISO: Nenhuma empresa encontrada com os seletores atuais.")
        print("Isso pode significar que a estrutura do site mudou ou o seletor está incorreto.")
        print("Vamos criar um arquivo de exemplo para que o fluxo continue.")
        # Cria um exemplo caso o scraping falhe, para não quebrar os próximos passos
        dados_exemplo = {
            'Nome': ['Scheffer Agrobusiness (Exemplo)', 'Grupo Bom Futuro (Exemplo)'],
            'Tipo': ['Algodoeira', 'Algodoeira'],
            'Endereço': ['Endereço não coletado', 'Endereço não coletado'],
            'Cidade': ['Sapezal', 'Cuiabá'],
            'Estado': ['MT', 'MT']
        }
        df = pd.DataFrame(dados_exemplo)
    else:
        print(f"Encontrados {len(itens_empresas)} itens de empresas. Processando...")
        lista_empresas = []
        for item in itens_empresas:
            # Extrai o nome da empresa
            nome_tag = item.find('h2', class_='title')
            nome = nome_tag.text.strip() if nome_tag else "Nome não encontrado"
            
            # Extrai a cidade/localização
            cidade_tag = item.find('p') # Supondo que a cidade esteja no primeiro <p>
            local_info = cidade_tag.text.strip() if cidade_tag else "Local não encontrado"
            
            # Simplesmente pegamos a primeira parte da localização como cidade
            cidade = local_info.split('-')[0].strip()

            lista_empresas.append({
                'Nome': nome,
                'Tipo': 'Algodoeira', # Definimos o tipo manualmente
                'Endereço': 'Endereço não coletado via scraping', # Scraping de endereço é mais complexo
                'Cidade': cidade,
                'Estado': 'MT' # Definimos o estado manualmente
            })
        
        df = pd.DataFrame(lista_empresas)

    # 4. Salva os dados em um arquivo CSV
    df.to_csv(ARQUIVO_SAIDA, index=False)
    print(f"\nProcesso finalizado! {len(df)} empresas salvas em '{ARQUIVO_SAIDA}'.")

except requests.exceptions.RequestException as e:
    print(f"\nERRO: Falha ao acessar o site. Verifique sua conexão ou o URL. Detalhes: {e}")
