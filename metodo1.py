# MIT License
# Copyright (c) 2026 Equipe Camada Física — UTFPR Campo Mourão
#
# metodo1.py — Método 1: batidas acústicas + Paridade Par (quadro de 9 bits)
#
# Padrão dos bits (enunciado):
#   Bit 0 = silêncio + 1 batida  + silêncio
#   Bit 1 = silêncio + 2 batidas + silêncio
#
# O receptor NÃO usa relógio fixo: ele detecta cada batida no tempo e agrupa as
# batidas próximas (mesmo bit) separando os grupos pelos silêncios maiores. Assim
# funciona também com batidas humanas (palmas, caneta) de outra equipe.

import numpy as np
from utils import (SR, LIMIAR_MINIMO, BLOCO_ENV, silencio, tocar, envelope,
                   gravar_ate_silencio, montar_quadro, verificar_paridade,
                   bits_para_byte)

# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÕES (ajuste aqui para casar com o vídeo de referência)
# ══════════════════════════════════════════════════════════

CLICK_HZ     = 800     # Frequência do clique (Hz)
CLICK_DUR    = 0.05    # Duração do clique (s)
SILENCIO     = 0.40    # Silêncio antes e depois de cada bit (s)
ENTRE_BATIDAS = 0.30   # Silêncio entre as 2 batidas do bit 1 (s)

LIMITE_GRUPO = 0.60    # Batidas com intervalo (início→início) <= isto são do MESMO bit (s)
FRACAO_PICO  = 0.30    # Limiar de detecção = 30% da batida mais forte
REARME       = 0.08    # Após uma batida, exige 80 ms abaixo do limiar para aceitar outra
RAZAO_SINAL_RUIDO = 5  # A batida mais forte precisa ser >= 5x o ruído de fundo
FIM_SILENCIO = 3.0     # Silêncio que indica fim da mensagem (s)

# ══════════════════════════════════════════════════════════
#  TRANSMISSOR
# ══════════════════════════════════════════════════════════

def _clique():
    """Uma 'batida': seno de 800 Hz com decaimento exponencial (50 ms)."""
    t = np.linspace(0, CLICK_DUR, int(SR * CLICK_DUR))
    return (0.9 * np.sin(2 * np.pi * CLICK_HZ * t) * np.exp(-30 * t)).astype(np.float32)

def gerar_audio_m1(texto, injetar_erro=False):
    """
    Converte texto em áudio de batidas. Cada caractere vira um quadro de 9 bits
    (8 de dados + paridade par). Se `injetar_erro`, inverte 1 bit do primeiro
    caractere DEPOIS de calcular a paridade (simula corrupção no meio físico).
    """
    partes = [silencio(0.5)]
    for n, char in enumerate(texto):
        quadro = montar_quadro(char)
        if injetar_erro and n == 0:
            quadro[3] ^= 1
        for bit in quadro:
            if bit == 0:
                partes += [silencio(SILENCIO), _clique(), silencio(SILENCIO)]
            else:
                partes += [silencio(SILENCIO), _clique(), silencio(ENTRE_BATIDAS),
                           _clique(), silencio(SILENCIO)]
    partes.append(silencio(0.5))
    return np.concatenate(partes)

def transmitir_m1(texto, injetar_erro=False):
    print(f"\n[M1 TX] Transmitindo: '{texto}'" + ("  (COM ERRO INJETADO)" if injetar_erro else ""))
    for n, char in enumerate(texto):
        quadro = montar_quadro(char)
        if injetar_erro and n == 0:
            quadro[3] ^= 1
        print(f"  '{char}' → {''.join(map(str, quadro[:8]))} | paridade: {quadro[8]}")
    audio = gerar_audio_m1(texto, injetar_erro)
    print(f"  Duração: {len(audio)/SR:.1f}s | Bits: {len(texto)*9}")
    tocar(audio)
    print("[M1 TX] ✅ Concluído!\n")

# ══════════════════════════════════════════════════════════
#  RECEPTOR
# ══════════════════════════════════════════════════════════

def detectar_batidas(audio):
    """Retorna os instantes (s) em que começou cada batida."""
    env = envelope(audio)
    if len(env) == 0 or env.max() < LIMIAR_MINIMO:
        return []
    ruido = float(np.median(env))              # batidas são raras: a mediana é o ruído de fundo
    if env.max() < RAZAO_SINAL_RUIDO * ruido:
        return []                              # só ruído, nenhuma batida de verdade
    limiar = max(LIMIAR_MINIMO, FRACAO_PICO * env.max(), 3 * ruido)
    bloco_s = BLOCO_ENV / SR
    blocos_rearme = max(1, int(REARME / bloco_s))

    tempos, armado, abaixo = [], True, 0
    for i, e in enumerate(env):
        if e > limiar:
            if armado:                       # subida: nova batida
                tempos.append(i * bloco_s)
                armado = False
            abaixo = 0
        else:
            abaixo += 1
            if abaixo >= blocos_rearme:      # som terminou de verdade: pode ouvir outra
                armado = True
    return tempos

def agrupar_batidas(tempos):
    """Agrupa batidas próximas. Retorna a quantidade de batidas de cada grupo (= cada bit)."""
    contagens = []
    anterior = None
    for t in tempos:
        if anterior is not None and t - anterior <= LIMITE_GRUPO:
            contagens[-1] += 1
        else:
            contagens.append(1)
        anterior = t
    return contagens

def decodificar_m1(audio):
    """
    Áudio → lista de quadros. Cada item: (caractere, bits, ok).
    1 batida = 0 | 2 batidas = 1 | outro = bit inválido (None).
    """
    contagens = agrupar_batidas(detectar_batidas(audio))
    bits = [0 if c == 1 else 1 if c == 2 else None for c in contagens]
    resultado = []
    for i in range(0, len(bits), 9):
        quadro = bits[i:i + 9]
        ok = len(quadro) == 9 and None not in quadro and verificar_paridade(quadro)
        char = chr(bits_para_byte(quadro[:8])) if ok else '?'
        resultado.append((char, quadro, ok))
    return resultado

def receber_m1():
    print("\n[M1 RX] Receptor de batidas (o nº de caracteres é detectado sozinho)")
    audio = gravar_ate_silencio(silencio_final=FIM_SILENCIO)
    if audio is None:
        print("  ❌ Nenhum som detectado.\n")
        return ""

    quadros = decodificar_m1(audio)
    texto, tudo_ok = "", True
    for n, (char, bits, ok) in enumerate(quadros, 1):
        quadro_str = ''.join('x' if b is None else str(b) for b in bits)
        if ok:
            print(f"  Caractere {n}: ✅ SUCESSO — '{char}' ({quadro_str})")
        else:
            print(f"  Caractere {n}: ❌ FALHA DE TRANSMISSÃO — quadro corrompido ({quadro_str})")
            tudo_ok = False
        texto += char

    print(f"[M1 RX] Mensagem: '{texto}' → " + ("✅ SUCESSO" if tudo_ok and quadros else "❌ FALHA DE TRANSMISSÃO") + "\n")
    return texto
