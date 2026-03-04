# TriLab TREINAMENTO

Aplicacao Streamlit para treinos de forca voltados a corredores, com camada SaaS para cadastro, trial, planos e assinaturas.

## Como rodar localmente

1. Tenha Python 3.11+ com as dependencias do projeto instaladas.
2. Na raiz do projeto, execute:

```powershell
streamlit run app.py
```

3. O banco SQLite sera criado e atualizado automaticamente em `dados/usuarios.db`.

## Banco de dados

- A conexao central fica em `core/banco.py`.
- `garantir_colunas_e_tabelas()` roda na inicializacao do app e cria:
  - `usuarios`
  - `treinador_atleta`
  - `convites_treinador_link`
  - `treinos_gerados`
  - `treinos_realizados`
  - `recuperacao_senha`
  - `preferencias_substituicao_exercicio`
  - `planos`
  - `assinaturas`
- A tabela `planos` recebe seed automatica:
  - `atleta_mensal` por R$ 49.90
  - `treinador_mensal` por R$ 149.90 com limite de 30 atletas

## Estrutura principal

- `app.py`: pagina principal, login/cadastro, home publica, controle de acesso e roteamento interno das areas protegidas.
- `core/`: regras de negocio (usuarios, banco, financeiro, treinos, cronograma, auth e telas internas).
- `pages/`: paginas publicas e financeiras do multipage Streamlit.
- `legal/`: documentos em Markdown de Termos de Uso e Politica de Privacidade.
- `dados/`: banco SQLite e arquivos de dados.

## Paginas

- Publicas:
  - Home (`app.py`)
  - `pages/planos.py`
  - `pages/faq.py`
  - `pages/contato.py`
  - `pages/termos.py`
  - `pages/privacidade.py`
- SaaS:
  - `pages/minha_assinatura.py`
  - `pages/pagamento_manual.py`

## Cadastro e LGPD

- O cadastro exige aceite obrigatorio de:
  - Termos de Uso
  - Politica de Privacidade
- Os aceites sao salvos em `usuarios`:
  - `aceitou_termos`
  - `aceitou_privacidade`
  - `data_consentimento`

## Trial e bloqueio

- Todo novo usuario recebe automaticamente um trial de 7 dias.
- Enquanto a assinatura estiver em `trial` ou `ativa`, o acesso as areas do atleta/treinador permanece liberado.
- Quando o trial expira sem assinatura ativa, o usuario e bloqueado das areas internas e ve a tela de "Assinatura necessaria".
- A pagina `pages/minha_assinatura.py` inclui um botao de teste para simular expiracao.

## Assinatura manual (MVP)

- O fluxo atual nao integra gateway real.
- `pages/pagamento_manual.py` simula a compra e ativa a assinatura manualmente para testes.
- `pages/minha_assinatura.py` permite visualizar status, historico e cancelar a renovacao automatica.

## Preparacao para Asaas

- O arquivo `core/pagamentos_gateway.py` concentra a interface do gateway.
- Hoje ele usa implementacao `manual`.
- No futuro, a integracao com Asaas deve entrar nesse modulo via API e webhook, preservando o restante da camada financeira.
