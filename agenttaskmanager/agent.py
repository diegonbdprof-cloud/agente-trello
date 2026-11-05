"""Agente Google ADK que organiza tarefas do dia no board Trello chamado DIO."""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from trello import TrelloClient

# O adk web também procura um .env subindo a partir da pasta do agente.
# Carregar aqui cobre `python -c` e testes, sem exigir que o processo
# esteja com a raiz do repositório como diretório atual.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FUSO_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NOME_BOARD = "DIO"

# Variáveis que nunca podem aparecer numa mensagem devolvida ao modelo.
_VARIAVEIS_SECRETAS = (
    "TRELLO_API_KEY",
    "TRELLO_API_SECRET",
    "TRELLO_TOKEN",
    "GOOGLE_API_KEY",
)

# Texto já sem acento, em minúsculas e com espaços simples.
_ALIASES_STATUS = {
    "a fazer": "a fazer",
    "to do": "a fazer",
    "todo": "a fazer",
    "em andamento": "em andamento",
    "doing": "em andamento",
    "concluido": "concluido",
    "concluida": "concluido",
    "done": "concluido",
    "todas": "todas",
    "todos": "todas",
    "all": "todas",
}

# Nomes aceitos de cada lista no board, depois da mesma normalização.
_NOMES_DE_LISTA = {
    "a fazer": {"a fazer", "to do", "todo"},
    "em andamento": {"em andamento", "doing"},
    "concluido": {"concluido", "concluida", "done"},
}

_STATUS_DE_MOVIMENTO = ("a fazer", "em andamento", "concluido")
_STATUS_INVALIDO = (
    "Status não reconhecido. Use a fazer, to do, em andamento, doing, "
    "concluído, concluido ou done."
)

_DATA_ISO = re.compile(r"^(\d{4})[/-](\d{2})[/-](\d{2})$")
_DATA_BR = re.compile(r"^(\d{2})[/-](\d{2})[/-](\d{4})$")
_DATA_HORA = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$"
)
_DATA_HORA_BR = re.compile(
    r"^(\d{2})/(\d{2})/(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?$"
)
_SEGREDO_NA_QUERY = re.compile(
    r"(?i)(key|token|secret|api_key|apikey|api_secret)=([^&\s\"']+)"
)


def normalizar_texto(valor: str) -> str:
    """Minúsculas, sem acento e com espaços internos colapsados."""
    texto = " ".join((valor or "").strip().split())
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.casefold().strip(" .,:;!?")


def normalizar_status(status: str) -> str | None:
    """Converte variações de status para a fazer, em andamento, concluido ou todas."""
    return _ALIASES_STATUS.get(normalizar_texto(status))


def normalizar_nome(nome: str) -> str:
    """Compara títulos de card ignorando maiúsculas e espaços repetidos."""
    return " ".join((nome or "").strip().split()).casefold()


def _meio_dia_local(ano: int, mes: int, dia: int) -> str:
    try:
        momento = datetime(ano, mes, dia, 12, 0, 0, tzinfo=FUSO_SAO_PAULO)
    except ValueError as exc:
        raise ValueError(
            "Data de vencimento inválida. Use YYYY-MM-DD, por exemplo 2026-11-05."
        ) from exc
    return momento.isoformat(timespec="seconds")


def _instante_local(
    ano: int, mes: int, dia: int, hora: int, minuto: int, segundo: int
) -> str:
    # Meia-noite sem fuso é o mesmo caso da data só com dia: o relógio não
    # foi escolhido, então ancoramos no meio-dia local.
    if hora == 0 and minuto == 0 and segundo == 0:
        return _meio_dia_local(ano, mes, dia)
    try:
        momento = datetime(
            ano, mes, dia, hora, minuto, segundo, tzinfo=FUSO_SAO_PAULO
        )
    except ValueError as exc:
        raise ValueError(
            "Data de vencimento inválida. Use YYYY-MM-DD, por exemplo 2026-11-05."
        ) from exc
    return momento.isoformat(timespec="seconds")


def vencimento_para_trello(valor: str) -> str:
    """Converte a data pedida para ISO 8601 com fuso de São Paulo.

    O Trello grava o vencimento em UTC e a interface mostra o fuso de quem
    olha o board. Uma string só com a data (``2026-11-05``) é meia-noite UTC.
    Em America/Sao_Paulo (UTC-3, sem horário de verão desde 2019) isso cai
    às 21:00 do dia anterior, e o card aparece no calendário com um dia a menos.

    Data sem horário, ou com horário 00:00:00, vira meio-dia local do dia
    escrito no texto: ``2026-11-05T12:00:00-03:00``. O Trello guarda
    ``2026-11-05T15:00:00.000Z``. Esse instante continua em 5 de novembro
    tanto em UTC quanto em São Paulo. O meio-dia, e não a meia-noite local,
    também segura o dia se algum cliente ignorar o offset e ler o relógio
    como UTC. Um horário diferente de meia-noite é preservado; se vier sem
    fuso, é interpretado em America/Sao_Paulo.
    """
    texto = " ".join((valor or "").strip().split())
    if not texto:
        raise ValueError(
            "Informe a data de vencimento, de preferência no formato YYYY-MM-DD."
        )

    encontrado = _DATA_ISO.match(texto)
    if encontrado:
        ano, mes, dia = (int(encontrado.group(i)) for i in (1, 2, 3))
        return _meio_dia_local(ano, mes, dia)

    encontrado = _DATA_BR.match(texto)
    if encontrado:
        dia, mes, ano = (int(encontrado.group(i)) for i in (1, 2, 3))
        return _meio_dia_local(ano, mes, dia)

    encontrado = _DATA_HORA.match(texto)
    if encontrado:
        return _instante_local(
            int(encontrado.group(1)),
            int(encontrado.group(2)),
            int(encontrado.group(3)),
            int(encontrado.group(4)),
            int(encontrado.group(5)),
            int(encontrado.group(6) or 0),
        )

    encontrado = _DATA_HORA_BR.match(texto)
    if encontrado:
        return _instante_local(
            int(encontrado.group(3)),
            int(encontrado.group(2)),
            int(encontrado.group(1)),
            int(encontrado.group(4)),
            int(encontrado.group(5)),
            int(encontrado.group(6) or 0),
        )

    try:
        interpretado = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Data de vencimento inválida. Use YYYY-MM-DD, por exemplo 2026-11-05."
        ) from exc

    meia_noite = (
        interpretado.hour == 0
        and interpretado.minute == 0
        and interpretado.second == 0
        and interpretado.microsecond == 0
    )
    if meia_noite:
        # O dia é o que está escrito (componentes do relógio), não o instante
        # convertido. ``2026-11-05T00:00:00Z`` precisa continuar 5 de novembro.
        return _meio_dia_local(
            interpretado.year, interpretado.month, interpretado.day
        )

    if interpretado.tzinfo is None:
        interpretado = interpretado.replace(tzinfo=FUSO_SAO_PAULO)
    else:
        interpretado = interpretado.astimezone(FUSO_SAO_PAULO)
    return interpretado.isoformat(timespec="seconds")


def formatar_vencimento_local(due: object) -> str:
    """Mostra o vencimento guardado pelo Trello no fuso de São Paulo."""
    if due is None:
        return "sem vencimento"
    texto = str(due).strip()
    if not texto:
        return "sem vencimento"
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return texto
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ZoneInfo("UTC"))
    local = momento.astimezone(FUSO_SAO_PAULO)
    return local.strftime("%Y-%m-%d %H:%M (%Z)")


def mensagem_erro(exc: BaseException) -> str:
    """Texto curto de falha, sem chave, segredo ou token."""
    texto = f"{type(exc).__name__}: {exc}"
    for nome in _VARIAVEIS_SECRETAS:
        valor = os.getenv(nome)
        if valor and len(valor) >= 8:
            texto = texto.replace(valor, "[redigido]")
    texto = _SEGREDO_NA_QUERY.sub(r"\1=[redigido]", texto)
    texto = " ".join(texto.split())
    if len(texto) > 500:
        texto = texto[:500] + "..."
    return "Não foi possível concluir a operação. " + texto


def criar_cliente_trello() -> TrelloClient:
    """Abre o cliente py-trello com a key e o token de usuário.

    O guia do Power-Up gera um token em ``response_type=token``. Esse token
    não é um token OAuth 1.0. No py-trello 0.20, passar o argumento ``token``
    liga OAuth1 e a API do Trello recusa a chamada. Com OAuth desligado, a
    biblioteca envia o parâmetro ``api_secret`` como ``token`` na query
    string, que é o modo ``key`` + ``token`` documentado pelo Trello.
    O segredo do Power-Up (``TRELLO_API_SECRET``) permanece só no ``.env``:
    ele não entra na requisição e não é impresso.
    """
    api_key = (os.getenv("TRELLO_API_KEY") or "").strip()
    token = (os.getenv("TRELLO_TOKEN") or "").strip()
    faltando = []
    if not api_key:
        faltando.append("TRELLO_API_KEY")
    if not token:
        faltando.append("TRELLO_TOKEN")
    if faltando:
        raise RuntimeError(
            "Credenciais do Trello ausentes no arquivo .env: "
            + ", ".join(faltando)
            + "."
        )
    return TrelloClient(api_key=api_key, api_secret=token)


def obter_board_dio():
    """Conecta ao Trello e devolve o board aberto cujo nome é exatamente DIO."""
    cliente = criar_cliente_trello()
    boards = cliente.list_boards(board_filter="open")
    encontrados = [board for board in boards if board.name == NOME_BOARD]
    if not encontrados:
        raise RuntimeError(
            "Nenhum board aberto chamado exatamente DIO foi encontrado. "
            "Crie um board com o nome DIO e as listas A fazer, Em andamento "
            "e Concluído."
        )
    return encontrados[0]


def _listas_abertas(board):
    return board.list_lists(list_filter="open")


def _encontrar_lista(listas, status_canonico: str):
    aceitos = _NOMES_DE_LISTA[status_canonico]
    for lista in listas:
        if normalizar_texto(lista.name) in aceitos:
            return lista
    return None


def _buscar_cards(listas, nome_da_task: str):
    alvo = normalizar_nome(nome_da_task)
    if not alvo:
        raise ValueError("Informe o nome da tarefa.")
    encontrados = []
    for lista in listas:
        for card in lista.list_cards():
            if normalizar_nome(card.name) == alvo:
                encontrados.append((lista, card))
    return encontrados


def _descrever_ausencia(nome_da_task: str) -> str:
    return (
        f"Nenhum card aberto chamado '{nome_da_task.strip()}' "
        f"foi encontrado no board {NOME_BOARD}."
    )


def get_temporal_context() -> str:
    """Retorna a data e a hora atuais no fuso America/Sao_Paulo.

    Chame esta ferramenta no início da conversa e inclua a data devolvida
    ao perguntar quais são as tarefas de hoje.
    """
    try:
        agora = datetime.now(FUSO_SAO_PAULO)
        return (
            "Agora em America/Sao_Paulo: "
            f"{agora.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
            f"Data de hoje: {agora.strftime('%d/%m/%Y')}."
        )
    except Exception as exc:  # noqa: BLE001 — a ferramenta precisa responder texto
        return mensagem_erro(exc)


def adicionar_tarefa(
    nome_da_task: str, descricao_da_task: str, due_date: str
) -> str:
    """Cria um card na lista A fazer do board DIO.

    Args:
        nome_da_task: Título do card.
        descricao_da_task: Descrição do card. Pode ser vazia.
        due_date: Dia de vencimento, de preferência YYYY-MM-DD. Também aceita
            DD/MM/YYYY. A data é enviada como meio-dia em America/Sao_Paulo
            para o calendário do Trello não mostrar o dia anterior.
    """
    try:
        nome = " ".join((nome_da_task or "").split())
        if not nome:
            raise ValueError("Informe o nome da tarefa.")
        vencimento = vencimento_para_trello(due_date)
        board = obter_board_dio()
        listas = _listas_abertas(board)
        lista = _encontrar_lista(listas, "a fazer")
        if lista is None:
            nomes = ", ".join(item.name for item in listas) or "nenhuma"
            raise RuntimeError(
                "A lista A fazer não está no board DIO. Listas abertas: "
                + nomes
                + "."
            )
        lista.add_card(
            name=nome,
            desc=descricao_da_task or "",
            due=vencimento,
        )
        return (
            f"Card '{nome}' criado na lista '{lista.name}' do board {NOME_BOARD}. "
            f"Vencimento enviado: {vencimento} "
            "(meio-dia em America/Sao_Paulo quando a data não traz horário). "
            "No Trello, confira se o dia do calendário é o mesmo que foi pedido."
        )
    except Exception as exc:  # noqa: BLE001
        return mensagem_erro(exc)


def listar_tarefas(status: str = "todas") -> str:
    """Lista os cards abertos do board DIO, todos ou filtrados por status.

    Args:
        status: todas, a fazer, to do, em andamento, doing, concluído,
            concluido ou done. Maiúsculas, acento e espaços extras são aceitos.
    """
    try:
        canonico = normalizar_status(status if status is not None else "")
        if not (status or "").strip():
            canonico = "todas"
        if canonico not in ("todas", *_STATUS_DE_MOVIMENTO):
            return "Não foi possível concluir a operação. " + _STATUS_INVALIDO

        board = obter_board_dio()
        listas = _listas_abertas(board)
        if canonico == "todas":
            escolhidas = listas
        else:
            lista = _encontrar_lista(listas, canonico)
            if lista is None:
                raise RuntimeError(
                    f"A lista correspondente a '{status}' não está no board {NOME_BOARD}."
                )
            escolhidas = [lista]

        linhas = []
        for lista in escolhidas:
            for card in lista.list_cards():
                descricao = " ".join((card.desc or "").split())
                if len(descricao) > 180:
                    descricao = descricao[:177] + "..."
                detalhe = f" Descrição: {descricao}." if descricao else ""
                linhas.append(
                    f"- [{lista.name}] {card.name} | vencimento: "
                    f"{formatar_vencimento_local(card.due)}.{detalhe}"
                )
        if not linhas:
            return (
                f"Nenhuma tarefa aberta no board {NOME_BOARD} "
                f"para o filtro '{canonico}'."
            )
        cabecalho = f"Tarefas no board {NOME_BOARD} (filtro: {canonico}):"
        return cabecalho + "\n" + "\n".join(linhas)
    except Exception as exc:  # noqa: BLE001
        return mensagem_erro(exc)


def mudar_status_tarefa(nome_da_task: str, novo_status: str) -> str:
    """Move um card entre A fazer, Em andamento e Concluído.

    Args:
        nome_da_task: Nome do card, sem diferenciar maiúsculas.
        novo_status: a fazer, to do, em andamento, doing, concluído,
            concluido ou done.
    """
    try:
        canonico = normalizar_status(novo_status)
        if canonico not in _STATUS_DE_MOVIMENTO:
            return "Não foi possível concluir a operação. " + _STATUS_INVALIDO

        board = obter_board_dio()
        listas = _listas_abertas(board)
        destino = _encontrar_lista(listas, canonico)
        if destino is None:
            raise RuntimeError(
                f"A lista de destino '{canonico}' não está no board {NOME_BOARD}."
            )
        encontrados = _buscar_cards(listas, nome_da_task)
        if not encontrados:
            return _descrever_ausencia(nome_da_task)

        origem, card = encontrados[0]
        if origem.id == destino.id:
            aviso = ""
            if len(encontrados) > 1:
                aviso = (
                    f" Há {len(encontrados)} cards com esse nome; "
                    "nenhum foi movido porque o primeiro já está nessa lista."
                )
            return (
                f"A tarefa '{card.name}' já está na lista '{destino.name}'.{aviso}"
            )

        card.change_list(destino.id)
        aviso = ""
        if len(encontrados) > 1:
            aviso = (
                f" Há {len(encontrados)} cards com esse nome; "
                f"apenas o da lista '{origem.name}' foi movido."
            )
        return (
            f"Tarefa '{card.name}' movida de '{origem.name}' para "
            f"'{destino.name}'.{aviso}"
        )
    except Exception as exc:  # noqa: BLE001
        return mensagem_erro(exc)


def remover_tarefa(nome_da_task: str) -> str:
    """Arquiva o card aberto com esse nome no board DIO.

    O card sai das listas abertas. No Trello ele pode ser restaurado em
    Arquivados; não é uma exclusão permanente.

    Args:
        nome_da_task: Nome do card, sem diferenciar maiúsculas.
    """
    try:
        board = obter_board_dio()
        listas = _listas_abertas(board)
        encontrados = _buscar_cards(listas, nome_da_task)
        if not encontrados:
            return _descrever_ausencia(nome_da_task)

        origem, card = encontrados[0]
        card.set_closed(True)
        aviso = ""
        if len(encontrados) > 1:
            aviso = (
                f" Há {len(encontrados)} cards com esse nome; "
                f"apenas o da lista '{origem.name}' foi arquivado."
            )
        return (
            f"Tarefa '{card.name}' arquivada no board {NOME_BOARD} "
            f"(estava em '{origem.name}' e saiu das listas abertas).{aviso}"
        )
    except Exception as exc:  # noqa: BLE001
        return mensagem_erro(exc)


root_agent = Agent(
    model="gemini-2.5-flash",
    name="organizador_tarefas",
    description=(
        "Organiza as tarefas do dia no board Trello chamado DIO: "
        "cria, lista, move e arquiva cards."
    ),
    instruction="""
Você é um agente de organização de tarefas no Trello.
O board usado tem o nome exato DIO.
As listas desse board são A fazer, Em andamento e Concluído.

Na primeira mensagem da conversa, antes de pedir qualquer tarefa, chame a ferramenta get_temporal_context.
Em seguida pergunte quais são as tarefas de hoje e inclua na pergunta a data devolvida por essa ferramenta.
Continue perguntando se existe mais alguma tarefa, até a pessoa dizer que não.

Use somente estas ferramentas, que são as que existem:
1. get_temporal_context: data e hora atuais em America/Sao_Paulo.
2. adicionar_tarefa: cria um card na lista A fazer com nome, descrição e data de vencimento. Envie a data como YYYY-MM-DD. A ferramenta ajusta o fuso para o dia do calendário no Trello não cair no dia anterior.
3. listar_tarefas: lista todas as tarefas abertas ou filtra por status. Aceite variações como a fazer, to do, em andamento, doing, concluído, concluido e done, com espaços extras e qualquer capitalização.
4. mudar_status_tarefa: move o card entre A fazer, Em andamento e Concluído. Quando a pessoa disser o que já fez ou em que etapa a tarefa está, mova o card correspondente.
5. remover_tarefa: arquiva o card pelo nome e o tira das listas abertas.

Se uma ferramenta devolver uma mensagem começando com "Não foi possível concluir a operação", explique o problema em português.
Não invente cards, datas ou credenciais.
Nunca repita chave, segredo ou token.
Não ofereça ações fora dessas cinco ferramentas.
""",
    tools=[
        get_temporal_context,
        adicionar_tarefa,
        listar_tarefas,
        mudar_status_tarefa,
        remover_tarefa,
    ],
)
