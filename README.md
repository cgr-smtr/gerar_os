# Gerarador de OS (Python version)

Este repositório contém a versão em Python das ferramentas de geração e auditoria de Ordem de Serviço (OS) para a rede de ônibus.

## Estrutura do Repositório

- `src/`: Contém os scripts Python.
  - `generate_os.py`: Processa os dados de partidas (`partidas.parquet`) e gera as tabelas de programação OS e os Planos Gerais.
  - `auditoria_app.py`: Interface Streamlit para comparar duas versões de tabelas e auditar mudanças.
- `requirements.txt`: Dependências do projeto.
- `legacy/`: Scripts originais em R (para referência).
- `.gitignore`: Configuração para ignorar arquivos temporários e resultados.

## Instalação

Recomenda-se o uso de um ambiente virtual:

```bash
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows
pip install -r requirements.txt
```

## Como Usar

### 1. Gerar Tabelas de Programação
Para processar os dados de partidas e gerar os arquivos CSV:

```bash
python src/generate_os.py
```
Os resultados serão salvos em `C:\R_SMTR\resultados\arquivos_os\`.

### 2. Auditoria de Mudanças
Para abrir a interface de auditoria:

```bash
streamlit run src/auditoria_app.py
```

## Configurações e Filtros
Os caminhos de entrada e saída podem ser ajustados diretamente no topo do arquivo `src/generate_os.py`.
- **Entrada padrão**: `C:\R_SMTR\resultados\partidas\partidas.parquet`
- **Saída padrão**: `C:\R_SMTR\resultados\arquivos_os\`
- **Filtros aplicados**: O script filtra automaticamente `route_type == "700"` e **exclui** partidas do consórcio `MOBI-Rio`.

## Licença

Este projeto está licenciado sob a Licença MIT - consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
