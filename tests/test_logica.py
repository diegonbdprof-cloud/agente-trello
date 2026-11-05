"""Testes sem rede: vencimento, status, redação de segredos e cliente Trello."""

import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from agenttaskmanager.agent import (
    criar_cliente_trello,
    formatar_vencimento_local,
    mensagem_erro,
    normalizar_status,
    vencimento_para_trello,
)

FUSO = ZoneInfo("America/Sao_Paulo")


class VencimentoTeste(unittest.TestCase):
    def test_data_somente_dia_vira_meio_dia_em_sao_paulo(self):
        iso = vencimento_para_trello("2026-11-05")
        self.assertEqual(iso, "2026-11-05T12:00:00-03:00")
        momento = datetime.fromisoformat(iso)
        self.assertEqual(momento.utcoffset(), FUSO.utcoffset(momento))
        self.assertEqual(momento.year, 2026)
        self.assertEqual(momento.month, 11)
        self.assertEqual(momento.day, 5)
        self.assertEqual(momento.hour, 12)
        # Meio-dia local é 15:00 UTC: o dia civil continua 5 nos dois fusos.
        utc = momento.astimezone(ZoneInfo("UTC"))
        self.assertEqual(utc.day, 5)
        self.assertEqual(utc.hour, 15)

    def test_meia_noite_utc_nao_volta_o_dia(self):
        iso = vencimento_para_trello("2026-11-05T00:00:00.000Z")
        momento = datetime.fromisoformat(iso)
        self.assertEqual(momento.astimezone(FUSO).date().isoformat(), "2026-11-05")
        self.assertEqual(momento.hour, 12)

    def test_barra_brasileira_e_espacos(self):
        iso = vencimento_para_trello("  05/11/2026  ")
        self.assertTrue(iso.startswith("2026-11-05T12:00:00"))

    def test_horario_explicito_e_preservado(self):
        iso = vencimento_para_trello("2026-11-05 15:30")
        momento = datetime.fromisoformat(iso)
        self.assertEqual(momento.hour, 15)
        self.assertEqual(momento.minute, 30)
        self.assertEqual(momento.day, 5)

    def test_data_invalida(self):
        with self.assertRaises(ValueError):
            vencimento_para_trello("2026-02-31")
        with self.assertRaises(ValueError):
            vencimento_para_trello("amanha")

    def test_exibicao_de_utc_no_fuso_local(self):
        # O que o Trello devolveria depois de gravar o meio-dia local.
        texto = formatar_vencimento_local("2026-11-05T15:00:00.000Z")
        self.assertIn("2026-11-05 12:00", texto)


class StatusTeste(unittest.TestCase):
    def test_variacoes_pedidas(self):
        casos = {
            "concluído": "concluido",
            "concluido": "concluido",
            "DONE": "concluido",
            "  to   do ": "a fazer",
            "A Fazer": "a fazer",
            "em andamento": "em andamento",
            "Em  Andamento": "em andamento",
            "Doing": "em andamento",
            "todas": "todas",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_status(entrada), esperado)

    def test_status_desconhecido(self):
        self.assertIsNone(normalizar_status("arquivado"))
        self.assertIsNone(normalizar_status("   "))


class ErroEClienteTeste(unittest.TestCase):
    def test_mensagem_nao_vaza_segredo_do_ambiente(self):
        nome = "TRELLO_TOKEN"
        anterior = os.environ.get(nome)
        segredo = "token-super-secreto-987654"
        os.environ[nome] = segredo
        try:
            texto = mensagem_erro(
                RuntimeError(f"falha em https://api.trello.com/?token={segredo}")
            )
        finally:
            if anterior is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = anterior
        self.assertNotIn(segredo, texto)
        self.assertIn("[redigido]", texto)
        self.assertTrue(texto.startswith("Não foi possível concluir a operação."))

    def test_mensagem_redige_query_mesmo_sem_env(self):
        texto = mensagem_erro(
            RuntimeError("url?key=abc123456789&token=zzz987654321 fim")
        )
        self.assertNotIn("abc123456789", texto)
        self.assertNotIn("zzz987654321", texto)

    def test_cliente_nao_liga_oauth1(self):
        anteriores = {
            nome: os.environ.get(nome)
            for nome in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_API_SECRET")
        }
        os.environ["TRELLO_API_KEY"] = "key-de-teste"
        os.environ["TRELLO_TOKEN"] = "token-de-usuario"
        os.environ["TRELLO_API_SECRET"] = "segredo-do-power-up"
        try:
            cliente = criar_cliente_trello()
        finally:
            for nome, valor in anteriores.items():
                if valor is None:
                    os.environ.pop(nome, None)
                else:
                    os.environ[nome] = valor
        self.assertIsNone(cliente.oauth)
        self.assertEqual(cliente.api_key, "key-de-teste")
        # O token de usuário ocupa o campo que o py-trello manda como ?token=
        self.assertEqual(cliente.api_secret, "token-de-usuario")
        self.assertNotEqual(cliente.api_secret, "segredo-do-power-up")

    def test_cliente_sem_credencial_nao_revela_valor(self):
        anteriores = {
            nome: os.environ.get(nome)
            for nome in ("TRELLO_API_KEY", "TRELLO_TOKEN")
        }
        os.environ["TRELLO_API_KEY"] = ""
        os.environ["TRELLO_TOKEN"] = "token-que-nao-pode-vazar-123"
        try:
            with self.assertRaises(RuntimeError) as contexto:
                criar_cliente_trello()
        finally:
            for nome, valor in anteriores.items():
                if valor is None:
                    os.environ.pop(nome, None)
                else:
                    os.environ[nome] = valor
        self.assertNotIn("token-que-nao-pode-vazar-123", str(contexto.exception))
        self.assertIn("TRELLO_API_KEY", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
