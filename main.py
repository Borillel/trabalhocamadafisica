# MIT License
# Copyright (c) 2026 Equipe Camada Física — UTFPR Campo Mourão
#
# main.py — Software de Comunicação pela Camada Física (menu principal)
# Disciplina: Redes de Computadores | UTFPR Campo Mourão
#
# Métodos implementados:
#   Método 1 (metodo1.py): Batidas acústicas + Paridade Par (9 bits)
#   Método 2 (metodo2.py): FSK (Frequency-Shift Keying) + CRC-8

from utils import montar_quadro, verificar_paridade
from metodo1 import transmitir_m1, receber_m1
from metodo2 import transmitir_m2, receber_m2, montar_quadro_m2
from utils import calcular_crc8, verificar_crc8

# ══════════════════════════════════════════════════════════
#  SIMULAÇÃO DE FALHA (sem áudio)
# ══════════════════════════════════════════════════════════

def simular_falha():
    """Inverte 1 bit e mostra que a paridade (M1) e o CRC-8 (M2) detectam a corrupção."""
    char = input("  Caractere para simular falha: ") or "A"
    char = char[0]

    print("\n  — Método 1 (Paridade Par) —")
    quadro = montar_quadro(char)
    corrompido = quadro[:]
    corrompido[3] ^= 1
    print(f"  Original:   {''.join(map(str, quadro))}  → OK: {verificar_paridade(quadro)}")
    print(f"  Corrompido: {''.join(map(str, corrompido))} → OK: {verificar_paridade(corrompido)}")
    if not verificar_paridade(corrompido):
        print("  → ❌ FALHA DE TRANSMISSÃO detectada!")

    print("\n  — Método 2 (CRC-8) —")
    dados = char.encode('latin-1', errors='replace')
    crc = calcular_crc8(dados)
    dados_corrompidos = bytes([dados[0] ^ 0b00001000])
    print(f"  Original:   dados={dados.hex()} CRC={crc:#04x} → OK: {verificar_crc8(dados, crc)}")
    print(f"  Corrompido: dados={dados_corrompidos.hex()} CRC={crc:#04x} → OK: {verificar_crc8(dados_corrompidos, crc)}")
    if not verificar_crc8(dados_corrompidos, crc):
        print("  → ❌ FALHA DE TRANSMISSÃO detectada!\n")

# ══════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════

def _texto():
    texto = input("  Texto: ")
    # O quadro tem 8 bits por caractere: caracteres fora do Latin-1 viram '?'
    return texto.encode('latin-1', errors='replace').decode('latin-1')

def main():
    print("\n" + "=" * 50)
    print("  SOFTWARE CAMADA FÍSICA | UTFPR Campo Mourão")
    print("=" * 50)
    opcoes = {
        "1": ("Método 1 — TRANSMITIR (Batidas)",              lambda: transmitir_m1(_texto())),
        "2": ("Método 1 — RECEBER   (Batidas)",               receber_m1),
        "3": ("Método 2 — TRANSMITIR (FSK)",                  lambda: transmitir_m2(_texto())),
        "4": ("Método 2 — RECEBER   (FSK)",                   receber_m2),
        "5": ("Simular FALHA de transmissão (offline)",       simular_falha),
        "6": ("Método 1 — TRANSMITIR com ERRO injetado",      lambda: transmitir_m1(_texto(), injetar_erro=True)),
        "7": ("Método 2 — TRANSMITIR com ERRO injetado",      lambda: transmitir_m2(_texto(), injetar_erro=True)),
        "0": ("Sair", None),
    }
    while True:
        print("\n  Escolha:")
        for k, (desc, _) in opcoes.items():
            print(f"  [{k}] {desc}")
        op = input("\n  Opção: ").strip()
        if op == "0":
            print("  Até mais!\n")
            break
        elif op in opcoes:
            opcoes[op][1]()
        else:
            print("  Opção inválida.")

if __name__ == "__main__":
    main()
