import sys
import os

from SimulatedHSM.simhsm import crypto_utils
from GenerateKey import combine_key

# 把上一级目录加入搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import constants

def run_combine_key(components_hex):
    combined_kek = combine_key.combine_key_components(*components_hex)
    print(f"combined_kek: {combined_kek}")

    kek_kcv = crypto_utils.calculate_kcv(combined_kek, constants.KEY_3DES)[:6]
    print(f"kek_kcv: {kek_kcv}\n")

def run_calculate_kcv(key_hex, algo_type):
    kcv = crypto_utils.calculate_kcv(key_hex, algo_type)[:6]
    print(f"kek_kcv: {kcv}\n")

def run_encryption(data_hex, kek_hex, algo):
    cipher_key = crypto_utils.key_encryption_from_kek(data_hex, kek_hex, algo, False, False)
    print(f"cipher_key: {cipher_key}\n")
    print(f'encrypted data: {cipher_key}\n')

def run_decryption(data_hex, kek_hex, algo):
    decode_data = crypto_utils.data_decryption_from_kek(data_hex, kek_hex, algo, False)
    print(f'decrypted data: {decode_data}\n')

if __name__ == "__main__":
    # for testing: hardcode for some information such as component1 and component2
    run_combine_key([constants.COMP1, constants.COMP2])
    print('\n')
    run_calculate_kcv(constants.KEK_TSYS, constants.KEY_3DES)
    print('\n')
    run_encryption(constants.BDK_PLAIN, constants.KEK_NAB, constants.KEY_AES)
    print('\n')
    run_decryption(constants.BDK_PLAIN, constants.KEK_TSYS, constants.KEY_AES)
    print('\n')