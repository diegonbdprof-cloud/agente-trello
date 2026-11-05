# Agente organizador de tarefas no Trello

Agente em Python (Google ADK + Gemini + py-trello) que organiza as tarefas do dia no board do Trello cujo nome é exatamente **DIO**.

Na primeira mensagem, o agente chama `get_temporal_context` e pergunta as tarefas de hoje já dizendo a data em `America/Sao_Paulo`. Cada tarefa vira um card com nome, descrição e vencimento. Dá para listar os cards, movê-los entre as listas e arquivar um card pelo nome.

## Ferramentas

| Ferramenta | O que faz |
| --- | --- |
| `get_temporal_context` | Data e hora atuais no fuso `America/Sao_Paulo`. |
| `adicionar_tarefa` | Cria um card na lista **A fazer**, com nome, descrição e vencimento. |
| `listar_tarefas` | Lista os cards abertos, todos ou filtrados por status. |
| `mudar_status_tarefa` | Move o card entre **A fazer**, **Em andamento** e **Concluído**. |
| `remover_tarefa` | Arquiva o card com aquele nome. Ele sai das listas abertas e pode ser restaurado em Arquivados no Trello. |

O texto de instrução do agente cita só essas cinco ferramentas.

## Board DIO

1. No Trello, crie um board com o nome exato `DIO` (maiúsculas, sem texto extra).
2. Crie três listas, nesta ordem, com estes nomes:
   - `A fazer`
   - `Em andamento`
   - `Concluído`
3. O agente também reconhece listas chamadas `To Do`, `Doing` ou `Done`, mas o board pedido pelo desafio usa os três nomes em português acima.

Cards novos entram em **A fazer**. Quando você disser o que já fez, ou em que etapa a tarefa está, o agente move o card.

## Chave, segredo e token do Trello

Resumo do que o [guia da DIO](https://github.com/digitalinnovationone/agent-carbon-footprint/blob/main/agents/agent04/readme.md) descreve. O passo a passo com as telas está nesse link. O cadastro do Power-Up fica em [https://trello.com/power-ups/admin/](https://trello.com/power-ups/admin/).

1. Abra o admin de Power-Ups, entre na sua conta e crie um Power-Up (**New**). Nome, workspace, e-mail e autor bastam para usar a API. A URL de iframe pode ficar em branco.
2. Na página do Power-Up, copie a **API key** e o **secret**.
3. No navegador, autorize um token de usuário (troque a key na URL):

   `https://trello.com/1/authorize?expiration=never&name=AppDio&scope=read,write&response_type=token&key=SUA_API_KEY`

4. Clique em **Allow** e copie o token que aparecer na página. Guarde key, secret e token só no seu `.env` local. Não commite esses valores.

O token dessa URL (`response_type=token`) não é um token OAuth 1.0. No py-trello 0.20, passar o argumento `token=` do construtor liga OAuth1 e a chamada é recusada. O helper deste projeto envia a API key e o token de usuário na query string, que é o modo que essa URL de autorização produz. O segredo do Power-Up fica no `.env` para você guardar o que a página do Power-Up mostrou; ele não é enviado em cada requisição e não aparece nas mensagens de erro.

## Chave do Gemini

1. Acesse [Google AI Studio](https://aistudio.google.com/apikey) com uma conta Google.
2. Crie uma API key gratuita.
3. Coloque a key em `GOOGLE_API_KEY` no `.env`.
4. Deixe `GOOGLE_GENAI_USE_VERTEXAI=0` para usar o AI Studio, e não o Vertex AI.

O modelo configurado em `agenttaskmanager/agent.py` é `gemini-2.5-flash`. Se o AI Studio recusar esse nome, troque a string `model` pela versão Flash atual da sua conta.

## Como rodar

É preciso Python 3.10 ou mais recente (`zoneinfo` e o ADK). Na raiz deste repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.exemplo .env
```

No Windows, ative o venv com `.venv\Scripts\activate`. Edite o `.env` e preencha os cinco valores. O arquivo `.env.exemplo` só tem marcadores; o `.env` real está no `.gitignore`.

O `requirements.txt` pede `google-adk`, `py-trello`, `python-dotenv` e `tzdata`. `datetime` e `zoneinfo` já vêm com o Python. O pacote é `python-dotenv` (o pacote chamado só `dotenv` no PyPI é outro projeto e quebra a instalação). `tzdata` fornece o fuso `America/Sao_Paulo` no Windows; no Linux o sistema já costuma ter essa base.

Com o venv ativo e o `.env` preenchido, na raiz do repositório:

```bash
adk web
```

Abra o endereço que o comando mostrar (em geral `http://127.0.0.1:8000`), escolha o agente `agenttaskmanager` e envie uma mensagem, por exemplo `olá`. O agente deve chamar `get_temporal_context` e perguntar as tarefas de hoje, já com a data.

O `.env` fica na raiz, ao lado deste README. O `adk web` procura o arquivo subindo a partir da pasta `agenttaskmanager/`.

## Melhorias

### 1. Vencimento não cai mais no dia anterior

O Trello grava a data de vencimento em UTC e a tela mostra o fuso de quem abre o board. Uma string só com o dia, como `2026-11-05`, é interpretada como meia-noite UTC (`2026-11-05T00:00:00.000Z`). `America/Sao_Paulo` é UTC−3 o ano inteiro desde 2019, então meia-noite UTC é 21:00 do dia 4. O card aparece ontem.

`List.add_card` do py-trello repassa o campo `due` como está para `POST /1/cards`. O agente deixa de mandar a data crua. Data sem horário (e também horário `00:00:00`, inclusive com `Z`) vira meio-dia em `America/Sao_Paulo`, com offset:

`2026-11-05` → `2026-11-05T12:00:00-03:00`

O Trello guarda o instante equivalente, `2026-11-05T15:00:00.000Z`. Esse horário ainda é 5 de novembro em UTC e em São Paulo. O meio-dia foi escolhido em vez da meia-noite local porque, se algum cliente ignorar o offset e ler o relógio como UTC, o dia civil continua o mesmo. Um horário diferente de meia-noite é mantido; se vier sem fuso, vale o relógio de São Paulo. Data com barra no formato brasileiro (`05/11/2026`) também é aceita.

Como testar: peça um card com vencimento num dia conhecido, por exemplo `2026-11-05`. Na resposta da ferramenta, confira o ISO `2026-11-05T12:00:00-03:00`. No card do Trello, o dia do calendário tem de ser 5 de novembro, não 4. A listagem do agente mostra o vencimento já convertido para `America/Sao_Paulo`.

Esta lógica de data foi conferida localmente com `python -m unittest discover -s tests -v`, sem chamar a API do Trello. Não há credencial neste repositório, então o calendário de um board ao vivo não foi verificado daqui.

### 2. Status com acento, sinônimo e espaços

`concluído`, `concluido`, `done`, `to do`, `a fazer`, `em andamento` e `doing` caem no mesmo status, com qualquer capitalização e com espaços repetidos. O acento é removido antes da comparação, e o nome da lista no board passa pelo mesmo tratamento. Por isso `Concluído` no board casa com `concluído` dito no chat. Antes, `mudar_status_tarefa` só tinha a chave `concluido` e respondia status inválido quando a palavra vinha com acento.

Como testar: crie um card, peça para listar `concluído` (com acento) e peça para mover outro card dizendo `concluído`, `DONE` ou `em  andamento`. A ferramenta não deve responder status inválido.

### 3. `remover_tarefa`

A instrução original prometia remover tarefa, mas a lista de tools não tinha essa função. `remover_tarefa` procura o card pelo nome (sem diferenciar maiúsculas nem espaços repetidos) e arquiva com `set_closed(True)`. O card some de `listar_tarefas`. Não é exclusão permanente: dá para restaurar em Arquivados no Trello. Se existir mais de um card com o mesmo nome, só o primeiro é arquivado e a resposta avisa.

Como testar: crie um card, peça para remover pelo nome e liste de novo. Ele não deve aparecer. No Trello, o card fica em itens arquivados.

### 4. Erro em toda ferramenta, sem vazar segredo

`get_temporal_context`, `adicionar_tarefa`, `listar_tarefas`, `mudar_status_tarefa` e `remover_tarefa` estão em `try/except`. A falha volta como texto começando com `Não foi possível concluir a operação.` O texto troca o valor de `GOOGLE_API_KEY`, `TRELLO_API_KEY`, `TRELLO_API_SECRET` e `TRELLO_TOKEN` por `[redigido]` e também limpa `key=`, `token=` e `secret=` se aparecerem numa URL.

Como testar: pare o processo, apague `TRELLO_TOKEN` do `.env`, suba de novo e peça para listar. A resposta deve citar a variável que falta e não deve imprimir a key nem o token que continuam no arquivo. O teste automático `tests/test_logica.py` cobre a redação com um segredo fictício.

### 5. Uma conexão só com o board DIO

`criar_cliente_trello` e `obter_board_dio` concentram o `TrelloClient` e a busca do board aberto de nome exato `DIO`. As ferramentas não repetem mais esse bloco. Listas e cards arquivados ficam de fora (`filter=open`).

### 6. Instrução alinhada às ferramentas

A instruction do `Agent` descreve criar, listar, mover e arquivar, manda abrir a conversa com `get_temporal_context` e a data de hoje, e não promete ação que não tenha ferramenta.

## Teste automático, sem board

Na raiz, com o venv ativo:

```bash
python -m unittest discover -s tests -v
```

Isso cobre o dia do vencimento, as variações de status, a redação de segredo e o cliente Trello sem OAuth1. Não usa rede e não precisa de `.env`.

## Evidência para a entrega

Um print do `adk web` ao lado do board DIO, com um card no dia certo, ajuda na correção. Este repositório não traz print e não afirma que um board real foi usado daqui: não há token no código. Gere o print na sua máquina, depois de preencher o `.env`.
