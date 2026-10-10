# MIT License
# Copyright (c) 2026 Equipe Camada Física — UTFPR Campo Mourão
#
# metodo2.py — Método 2: FSK (Frequency-Shift Keying) + CRC-8
#
# Quadro:  [ PRÓLOGO (Barker-13) ][ TAMANHO (8 bits) ][ DADOS (N×8 bits) ][ CRC-8 (8 bits) ]
#   - 1 bit = 1 tom de DUR_BIT segundos: FREQ_0 (bit 0) ou FREQ_1 (bit 1)
#   - O prólogo é uma sequência de Barker-13: o receptor o procura no áudio inteiro
#     por correlação para achar o início exato do quadro (sincronismo real).
#   - O TAMANHO permite ao receptor saber quantos caracteres vêm, sem configurar nada.
#   - O CRC-8 protege TAMANHO + DADOS.

import numpy as np
from utils import (SR, silencio, tocar, gravar_ate_silencio, calcular_crc8,
                   byte_para_bits, bits_para_byte)

# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════

FREQ_0   = 1000      # Hz para bit 0
FREQ_1   = 2000      # Hz para bit 1
DUR_BIT  = 0.02      # Segundos por bit (50 bps). Use múltiplo de 1/FREQ_0 e 1/FREQ_1
AMPLITUDE = 0.5

# Barker-13: autocorrelação quase perfeita → sincronismo preciso mesmo com ruído
PROLOGO = [1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1]

AMOSTRAS_BIT = int(SR * DUR_BIT)
_T = np.arange(AMOSTRAS_BIT) / SR
_REF0 = np.exp(-2j * np.pi * FREQ_0 * _T)
_REF1 = np.exp(-2j * np.pi * FREQ_1 * _T)
_SINAL_PROLOGO = np.array([1 if b else -1 for b in PROLOGO])
_ENERGIA_MINIMA = (0.02 * AMOSTRAS_BIT / 2) ** 2    # tom de amplitude 0.02 (limite de "há sinal")
SCORE_MINIMO = 0.6                                  # correlação mínima para aceitar o prólogo

# ══════════════════════════════════════════════════════════
#  TRANSMISSOR
# ══════════════════════════════════════════════════════════

def _tom(freq):
    t = np.arange(AMOSTRAS_BIT) / SR
    return (AMPLITUDE * np.sin(2 * np.pi * freq * t)).astype(np.float32)

def montar_quadro_m2(texto, injetar_erro=False):
    """Texto → lista de bits do quadro FSK. Retorna (bits, crc)."""
    dados = texto.encode('latin-1', errors='replace')
    if not 1 <= len(dados) <= 255:
        raise ValueError("A mensagem deve ter de 1 a 255 caracteres.")
    corpo = bytes([len(dados)]) + dados
    crc = calcular_crc8(corpo)

    bits = list(PROLOGO)
    for byte in corpo:
        bits += byte_para_bits(byte)
    bits += byte_para_bits(crc)

    if injetar_erro:                         # corrompe 1 bit de dados DEPOIS do CRC
        bits[len(PROLOGO) + 8 + 3] ^= 1
    return bits, crc

def gerar_audio_m2(texto, injetar_erro=False):
    bits, _ = montar_quadro_m2(texto, injetar_erro)
    tons = [_tom(FREQ_1 if b else FREQ_0) for b in bits]
    return np.concatenate([silencio(0.3)] + tons + [silencio(0.3)])

def transmitir_m2(texto, injetar_erro=False):
    print(f"\n[M2 FSK TX] Transmitindo: '{texto}'" + ("  (COM ERRO INJETADO)" if injetar_erro else ""))
    bits, crc = montar_quadro_m2(texto, injetar_erro)
    audio = gerar_audio_m2(texto, injetar_erro)
    util = len(texto) * 8
    print(f"  CRC-8: {crc} | Bits no quadro: {len(bits)} | Taxa bruta: {1/DUR_BIT:.0f} bps")
    print(f"  Duração do quadro: {len(bits)*DUR_BIT:.2f}s | Taxa útil (só dados): {util/(len(bits)*DUR_BIT):.1f} bps")
    tocar(audio)
    print("[M2 FSK TX] ✅ Concluído!\n")

# ══════════════════════════════════════════════════════════
#  RECEPTOR
# ══════════════════════════════════════════════════════════

def _janelas(audio, inicio, n_bits):
    """Fatia n_bits janelas de DUR_BIT a partir de `inicio` (completa com zeros se faltar)."""
    total = n_bits * AMOSTRAS_BIT
    seg = audio[inicio:inicio + total]
    if len(seg) < total:
        seg = np.pad(seg, (0, total - len(seg)))
    return seg.reshape(n_bits, AMOSTRAS_BIT)

def _energias(janelas):
    """Energia de cada janela nas frequências FREQ_0 e FREQ_1 (equivale a uma FFT em 2 pontos)."""
    return np.abs(janelas @ _REF0) ** 2, np.abs(janelas @ _REF1) ** 2

def _pontuar(audio, inicio):
    """
    Compara o áudio, a partir de `inicio`, com o prólogo esperado.
    Retorna (score, ganho1, ganho0): score ≈ 1 = prólogo perfeito; os ganhos são a
    energia média que cada tom teve no prólogo (calibração do canal: o eco pode
    atenuar um tom bem mais que o outro).
    """
    e0, e1 = _energias(_janelas(audio, inicio, len(PROLOGO)))
    uns, zeros = _SINAL_PROLOGO > 0, _SINAL_PROLOGO < 0
    ganho1, ganho0 = e1[uns].mean(), e0[zeros].mean()           # tom certo, janelas certas
    vaza1, vaza0 = e1[zeros].mean(), e0[uns].mean()             # tom errado (vazamento)
    if min(ganho1, ganho0) < _ENERGIA_MINIMA:
        return -1.0, ganho1, ganho0                              # quase silêncio
    if e1[uns].min() < 0.25 * ganho1 or e0[zeros].min() < 0.25 * ganho0:
        return -1.0, ganho1, ganho0                              # alguma janela está vazia
    contraste1 = (ganho1 - vaza1) / (ganho1 + vaza1)
    contraste0 = (ganho0 - vaza0) / (ganho0 + vaza0)
    return float((contraste1 + contraste0) / 2), ganho1, ganho0

def _achar_inicio(audio):
    """
    Procura o prólogo no áudio todo: busca grossa + refinamento.
    Retorna (inicio, score, ganho1, ganho0); inicio=None se não encontrar.
    """
    ultimo = len(audio) - len(PROLOGO) * AMOSTRAS_BIT
    if ultimo <= 0:
        return None, -1.0, 0.0, 0.0
    passo = max(1, AMOSTRAS_BIT // 4)
    melhor, melhor_score = 0, -2.0
    for i in range(0, ultimo, passo):
        s = _pontuar(audio, i)[0]
        if s > melhor_score:
            melhor, melhor_score = i, s
    for i in range(max(0, melhor - passo), min(ultimo, melhor + passo) + 1, 8):
        s = _pontuar(audio, i)[0]
        if s > melhor_score:
            melhor, melhor_score = i, s
    score, ganho1, ganho0 = _pontuar(audio, melhor)
    if score < SCORE_MINIMO:
        return None, score, ganho1, ganho0
    return melhor, score, ganho1, ganho0

def _decidir_bits(audio, inicio, n_bits, ganho1=1.0, ganho0=1.0):
    """Bit = 1 se o tom FREQ_1 (relativo ao seu ganho no prólogo) vence o tom FREQ_0."""
    e0, e1 = _energias(_janelas(audio, inicio, n_bits))
    return [int(b) for b in (e1 / ganho1 > e0 / ganho0)]

def decodificar_m2(audio):
    """
    Áudio → dict com: texto, ok (CRC confere), crc_rx, crc_calc, bits, duracao.
    Retorna None se o prólogo não for encontrado.
    """
    inicio, score, g1, g0 = _achar_inicio(audio)
    if inicio is None:
        return None

    n_cab = len(PROLOGO) + 8
    tamanho = bits_para_byte(_decidir_bits(audio, inicio, n_cab, g1, g0)[len(PROLOGO):])
    total = n_cab + tamanho * 8 + 8
    if tamanho == 0 or inicio + total * AMOSTRAS_BIT > len(audio) + AMOSTRAS_BIT:
        return {'texto': '', 'ok': False, 'crc_rx': None, 'crc_calc': None,
                'bits': n_cab, 'duracao': 0.0, 'motivo': 'quadro incompleto ou tamanho inválido'}

    bits = _decidir_bits(audio, inicio, total, g1, g0)
    corpo_bits = bits[len(PROLOGO):total - 8]
    corpo = bytes(bits_para_byte(corpo_bits[i:i + 8]) for i in range(0, len(corpo_bits), 8))
    crc_rx = bits_para_byte(bits[total - 8:])
    crc_calc = calcular_crc8(corpo)
    return {'texto': corpo[1:].decode('latin-1', errors='replace'),
            'ok': crc_rx == crc_calc, 'crc_rx': crc_rx, 'crc_calc': crc_calc,
            'bits': total, 'duracao': total * DUR_BIT, 'motivo': ''}

def receber_m2():
    print("\n[M2 FSK RX] Receptor FSK (o nº de caracteres vem no cabeçalho do quadro)")
    audio = gravar_ate_silencio(silencio_final=0.5)
    if audio is None:
        print("  ❌ Nenhum som detectado.\n")
        return ""

    r = decodificar_m2(audio)
    if r is None:
        print("  ❌ FALHA DE TRANSMISSÃO — prólogo de sincronismo não encontrado.\n")
        return ""
    if r['ok']:
        util = len(r['texto']) * 8
        print(f"  ✅ SUCESSO — '{r['texto']}' (CRC OK: {r['crc_rx']})")
        print(f"  Taxa bruta: {1/DUR_BIT:.0f} bps | Taxa útil: {util/r['duracao']:.1f} bps ({r['bits']} bits em {r['duracao']:.2f}s)\n")
    else:
        detalhe = r['motivo'] or f"CRC recebido {r['crc_rx']} ≠ calculado {r['crc_calc']}"
        print(f"  ❌ FALHA DE TRANSMISSÃO — dados corrompidos! '{r['texto']}' ({detalhe})\n")
    return r['texto']
