# MIT License
# Copyright (c) 2026 Equipe Camada Física — UTFPR Campo Mourão
#
# utils.py
# Funções auxiliares: Paridade Par, CRC-8 e utilitários de áudio (compartilhados
# pelo Método 1 e pelo Método 2).

import numpy as np

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES DE ÁUDIO COMPARTILHADAS
# ─────────────────────────────────────────────

SR = 44100                        # Taxa de amostragem (Hz)
BLOCO_ENV = int(SR * 0.005)       # Bloco de 5 ms usado para calcular o envelope
LIMIAR_MINIMO = 0.03              # Amplitude mínima (0 a 1) para considerar que "há som"

# ─────────────────────────────────────────────
#  PARIDADE PAR (Método 1)
# ─────────────────────────────────────────────

def calcular_paridade(bits: list) -> int:
    """Retorna 0 se a soma dos bits for par, 1 se for ímpar."""
    return sum(bits) % 2

def montar_quadro(char: str) -> list:
    """Converte um caractere em quadro de 9 bits com paridade par."""
    bits = [int(b) for b in format(ord(char), '08b')]
    return bits + [calcular_paridade(bits)]

def verificar_paridade(quadro: list) -> bool:
    """Verifica se o quadro de 9 bits está íntegro."""
    return calcular_paridade(quadro[:8]) == quadro[8]

# ─────────────────────────────────────────────
#  CRC-8 (Método 2)
# ─────────────────────────────────────────────

def calcular_crc8(dados: bytes) -> int:
    """Calcula o CRC-8 (polinômio 0x07) de um conjunto de bytes."""
    crc = 0
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) if (crc & 0x80) else (crc << 1)
        crc &= 0xFF
    return crc

def verificar_crc8(dados: bytes, crc_recebido: int) -> bool:
    """Retorna True se o CRC bate com os dados."""
    return calcular_crc8(dados) == crc_recebido

# ─────────────────────────────────────────────
#  CONVERSÕES BITS <-> BYTES
# ─────────────────────────────────────────────

def byte_para_bits(valor: int) -> list:
    """Converte um inteiro (0-255) em lista de 8 bits (MSB primeiro)."""
    return [int(b) for b in format(valor, '08b')]

def bits_para_byte(bits: list) -> int:
    """Converte uma lista de bits (MSB primeiro) em inteiro."""
    return int(''.join(map(str, bits)), 2)

# ─────────────────────────────────────────────
#  ÁUDIO: GERAÇÃO, REPRODUÇÃO E CAPTURA
# ─────────────────────────────────────────────

def silencio(dur: float) -> np.ndarray:
    """Gera `dur` segundos de silêncio."""
    return np.zeros(int(SR * dur), dtype=np.float32)

def tocar(audio: np.ndarray):
    """Toca o áudio no alto-falante e espera terminar."""
    import sounddevice as sd
    sd.play(audio, SR)
    sd.wait()

def envelope(audio: np.ndarray, bloco: int = BLOCO_ENV) -> np.ndarray:
    """Envelope de amplitude: maior |amostra| de cada bloco de 5 ms."""
    n = len(audio) // bloco
    return np.abs(audio[:n * bloco]).reshape(n, bloco).max(axis=1)

def gravar_ate_silencio(silencio_final: float, espera_max: float = 60.0,
                        duracao_max: float = 120.0, ganho_limiar: float = 4.0):
    """
    Grava do microfone sem precisar saber a duração de antemão:
      1. calibra o ruído ambiente (1 s de silêncio);
      2. espera o primeiro som acima do limiar;
      3. continua gravando até `silencio_final` segundos sem som.
    Retorna o áudio capturado (com 0,3 s de folga antes do 1º som) ou None se
    nada foi ouvido dentro de `espera_max` segundos.
    """
    import sounddevice as sd
    from collections import deque

    bloco = int(SR * 0.05)                      # blocos de 50 ms
    pre = deque(maxlen=6)                       # guarda os últimos 0,3 s antes do som
    gravado = []
    iniciou = False
    blocos_quietos = 0
    total = 0

    with sd.InputStream(samplerate=SR, channels=1, dtype='float32', blocksize=bloco) as fluxo:
        print("  Calibrando ruído ambiente (fique em silêncio por 1 s)...")
        calib = np.concatenate([fluxo.read(bloco)[0][:, 0] for _ in range(20)])
        limiar = max(LIMIAR_MINIMO, ganho_limiar * float(np.abs(calib).max()))
        print(f"  Ouvindo... (limiar de disparo: {limiar:.3f}) — pode transmitir agora!")

        while True:
            dados = fluxo.read(bloco)[0][:, 0]
            total += 1
            forte = float(np.abs(dados).max()) > limiar
            if not iniciou:
                pre.append(dados)
                if forte:
                    iniciou = True
                    gravado = list(pre)
                elif total * 0.05 > espera_max:
                    return None
            else:
                gravado.append(dados)
                blocos_quietos = 0 if forte else blocos_quietos + 1
                if blocos_quietos * 0.05 >= silencio_final or len(gravado) * 0.05 >= duracao_max:
                    break
    return np.concatenate(gravado)
