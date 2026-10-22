"""Treino dos modelos de risco (zonas, vias, pontos críticos, série mensal).

Roda offline (`scripts/treinar_risco.py`) e publica os resultados em tabelas
do banco; a API (`app/`) só lê essas tabelas e nunca importa este pacote.
Por isso as dependências pesadas (pandas, scikit-learn, scipy) ficam em
`requirements-ml.txt`, fora do `requirements.txt` da API.
"""
