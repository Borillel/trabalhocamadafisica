# MIT License
# Copyright (c) 2026 Equipe Camada Física — UTFPR Campo Mourão
#
# tests/test_canal_simulado.py
# Testes automáticos SEM microfone/alto-falante: o áudio gerado pelo transmissor
# passa por um "canal" simulado (atraso, atenuação, ruído, eco) e é decodificado
# pelo receptor. Execute com:   python -m unittest discover -s tests -v

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import SR, montar_quadro, verificar_paridade, calcular_crc8, silencio
import metodo1
import metodo2


def canal(audio, rng, atraso=1.0, ganho=0.4, ruido=0.01, eco=False):
    """Simula atraso, atenuação, ruído branco e (opcional) reverberação."""
    x = np.concatenate([silencio(atraso), audio * ganho, silencio(1.0)]).astype(np.float64)
    if eco:
        n = int(SR * 0.12)
        resposta = np.zeros(n)
        resposta[0] = 1.0
        resposta += 0.03 * rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * 0.03))
        x = np.convolve(x, resposta)[:len(x)]
    return (x + ruido * rng.standard_normal(len(x))).astype(np.float32)


class TestUtils(unittest.TestCase):
    def test_paridade_exemplos_do_enunciado(self):
        self.assertEqual(montar_quadro('A')[8], 0)            # 01000001 → 2 uns → b9 = 0
        self.assertEqual(montar_quadro('C')[8], 1)            # 01000011 → 3 uns → b9 = 1
        self.assertTrue(verificar_paridade([1, 1, 0, 0, 0, 0, 0, 0, 0]))
        self.assertTrue(verificar_paridade([1, 1, 1, 0, 0, 0, 0, 0, 1]))
        self.assertFalse(verificar_paridade([1, 1, 1, 0, 0, 0, 0, 0, 0]))

    def test_crc8_valor_conhecido(self):
        self.assertEqual(calcular_crc8(b"123456789"), 0xF4)   # valor de referência do CRC-8 (0x07)


class TestMetodo1(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1)

    def _rodar(self, texto, **kw):
        audio = canal(metodo1.gerar_audio_m1(texto), self.rng, **kw)
        return metodo1.decodificar_m1(audio)

    def test_ida_e_volta(self):
        r = self._rodar("Oi!")
        self.assertEqual("".join(c for c, _, _ in r), "Oi!")
        self.assertTrue(all(ok for _, _, ok in r))

    def test_com_ruido_e_eco(self):
        r = self._rodar("Redes", ganho=0.3, ruido=0.02, eco=True)
        self.assertEqual("".join(c for c, _, _ in r), "Redes")

    def test_erro_injetado_e_detectado(self):
        audio = canal(metodo1.gerar_audio_m1("AB", injetar_erro=True), self.rng)
        r = metodo1.decodificar_m1(audio)
        self.assertFalse(r[0][2])                 # 1º caractere: falha
        self.assertTrue(r[1][2])                  # 2º caractere: ok
        self.assertEqual(r[1][0], "B")

    def test_batidas_humanas_com_jitter(self):
        """Simula palmas humanas: intervalos e volumes irregulares."""
        rng = self.rng
        partes = [silencio(0.5)]
        for char in "Ok":
            for bit in montar_quadro(char):
                partes.append(silencio(rng.uniform(0.7, 1.1)))
                partes.append(metodo1._clique() * rng.uniform(0.5, 1.0))
                if bit:
                    partes.append(silencio(rng.uniform(0.18, 0.40)))
                    partes.append(metodo1._clique() * rng.uniform(0.5, 1.0))
        partes.append(silencio(0.5))
        r = metodo1.decodificar_m1(canal(np.concatenate(partes), rng))
        self.assertEqual("".join(c for c, _, _ in r), "Ok")

    def test_silencio_nao_gera_bits(self):
        self.assertEqual(metodo1.decodificar_m1(canal(silencio(3), self.rng)), [])


class TestMetodo2(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(2)

    def _rodar(self, texto, **kw):
        return metodo2.decodificar_m2(canal(metodo2.gerar_audio_m2(texto), self.rng, **kw))

    def test_ida_e_volta(self):
        r = self._rodar("Ola Mundo!")
        self.assertTrue(r['ok'])
        self.assertEqual(r['texto'], "Ola Mundo!")

    def test_atraso_variavel(self):
        for atraso in (0.1, 0.77, 2.3):
            r = self._rodar("Teste", atraso=atraso)
            self.assertTrue(r['ok'], f"atraso={atraso}")
            self.assertEqual(r['texto'], "Teste")

    def test_com_ruido_forte(self):
        r = self._rodar("Camada Fisica", ganho=0.3, ruido=0.04)
        self.assertTrue(r['ok'])
        self.assertEqual(r['texto'], "Camada Fisica")

    def test_com_eco(self):
        r = self._rodar("Redes de Computadores", eco=True)
        self.assertTrue(r['ok'])
        self.assertEqual(r['texto'], "Redes de Computadores")

    def test_acentos_latin1(self):
        r = self._rodar("Conexão")
        self.assertTrue(r['ok'])
        self.assertEqual(r['texto'], "Conexão")

    def test_erro_injetado_e_detectado(self):
        audio = canal(metodo2.gerar_audio_m2("Teste", injetar_erro=True), self.rng)
        r = metodo2.decodificar_m2(audio)
        self.assertIsNotNone(r)
        self.assertFalse(r['ok'])

    def test_so_ruido_nao_acha_prologo(self):
        ruido = (0.05 * self.rng.standard_normal(SR * 5)).astype(np.float32)
        self.assertIsNone(metodo2.decodificar_m2(ruido))

    def test_ruido_antes_do_sinal(self):
        """Um estalo antes da mensagem não pode enganar o sincronismo."""
        audio = metodo2.gerar_audio_m2("Sync")
        estalo = np.concatenate([silencio(0.5), metodo1._clique(), silencio(0.8)])
        r = metodo2.decodificar_m2(canal(np.concatenate([estalo, audio]), self.rng))
        self.assertTrue(r['ok'])
        self.assertEqual(r['texto'], "Sync")


class MicrofoneFalso:
    """Substitui sounddevice.InputStream entregando um áudio pré-gerado, bloco a bloco."""
    audio = np.zeros(1, dtype=np.float32)

    def __init__(self, samplerate, channels, dtype, blocksize):
        self.pos = 0
        self.bloco = blocksize

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        trecho = self.audio[self.pos:self.pos + n]
        self.pos += n
        if len(trecho) < n:                      # acabou o áudio: continua o "silêncio"
            trecho = np.pad(trecho, (0, n - len(trecho)))
        return trecho.reshape(-1, 1), False


class TestReceptoresCompletos(unittest.TestCase):
    """Testa receber_m1/receber_m2 inteiros (calibração, disparo, parada por silêncio)."""

    def _receber(self, funcao, audio):
        from unittest import mock
        falso = mock.MagicMock()
        MicrofoneFalso.audio = audio
        falso.InputStream = MicrofoneFalso
        with mock.patch.dict(sys.modules, {"sounddevice": falso}):
            import io
            from contextlib import redirect_stdout
            saida = io.StringIO()
            with redirect_stdout(saida):
                texto = funcao()
        return texto, saida.getvalue()

    def test_receber_m1_completo(self):
        rng = np.random.default_rng(3)
        audio = canal(metodo1.gerar_audio_m1("Oi"), rng, atraso=2.5)
        texto, log = self._receber(metodo1.receber_m1, audio)
        self.assertEqual(texto, "Oi")
        self.assertIn("SUCESSO", log)

    def test_receber_m1_erro_mostra_falha(self):
        rng = np.random.default_rng(4)
        audio = canal(metodo1.gerar_audio_m1("Oi", injetar_erro=True), rng, atraso=2.0)
        texto, log = self._receber(metodo1.receber_m1, audio)
        self.assertIn("FALHA DE TRANSMISSÃO", log)

    def test_receber_m2_completo(self):
        rng = np.random.default_rng(5)
        audio = canal(metodo2.gerar_audio_m2("Redes"), rng, atraso=2.2)
        texto, log = self._receber(metodo2.receber_m2, audio)
        self.assertEqual(texto, "Redes")
        self.assertIn("SUCESSO", log)

    def test_receber_m2_erro_mostra_falha(self):
        rng = np.random.default_rng(6)
        audio = canal(metodo2.gerar_audio_m2("Redes", injetar_erro=True), rng, atraso=2.2)
        texto, log = self._receber(metodo2.receber_m2, audio)
        self.assertIn("FALHA DE TRANSMISSÃO", log)


if __name__ == "__main__":
    unittest.main()
