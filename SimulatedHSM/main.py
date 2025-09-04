import sys
import os

import logging
import time
from os import WCONTINUED

sys.path.append(os.path.dirname(__file__))  # 把 SimulatedHSM 目录加到 sys.path
from SimulatedHSM.simhsm import constants, build_packet_utils, serial_utils, parser, crypto_utils

def run_key_injection(port_name: str, baud_rate: int, key_algo: str, bdk_idx: str, bdk_data: str, ksn: str):
    logger = logging.getLogger(__name__)

    # Convert HEX of handshake command to Bytes
    handshake_data_bytes = bytes.fromhex(constants.HANDSHAKE_CMD)
    print(f"send {constants.INFO_HANDSHAKE_CMD_BYTES}: {handshake_data_bytes}")

    ser = serial_utils.open_serial(port_name, baud_rate)
    time.sleep(2)

    ser.write(handshake_data_bytes)
    response_bytes = serial_utils.read_full_response(ser)

    if not serial_utils.is_handshake_ok(response_bytes):
        return

    try:
        sn = parser.parse_sn(response_bytes)
    except Exception as e:
        logger.error(f"{constants.ERR_PARSE_SN}: {e}")
        sn = None
    print(f"{constants.INFO_SN_RESP}: {sn}", flush=True)

    rsa_pub_key_hex = parser.parse_rsa_public(response_bytes)
    print(f"{constants.INFO_RSA_PUB_KEY}: {rsa_pub_key_hex}", flush=True)

    """
    Start KEK Injection
    """

    kek_kcv = crypto_utils.calculate_kcv(constants.KEK_TSYS, constants.KEY_3DES)

    # build upper layer plaintext KEK packet
    kek_plaintext_data_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_KEK_PLAIN, constants.KEK_TSYS)
    kek_plaintext_kcv_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_KEK_KCV, kek_kcv)
    kek_plaintext_full_packet = kek_plaintext_data_packet + kek_plaintext_kcv_packet
    print(f"full_plaintext_kek_data: {kek_plaintext_full_packet}")
    # encrypt plaintext KEK
    kek_rsa_encrypt_full_packet = crypto_utils.rsa_encrypt_hex(rsa_pub_key_hex, kek_plaintext_full_packet)
    print(f"kek_rsa_encrypt_full_packet: {kek_rsa_encrypt_full_packet}")
    # build lower layer cipher KEK message
    kek_lower_layer_full_message = build_packet_utils.build_lower_layer_packet(kek_rsa_encrypt_full_packet, constants.CMD_KEK_INTERACTION)
    # send KEK response (bytes) to TargetPOS
    ser.write(bytes.fromhex(kek_lower_layer_full_message))
    print(f"Send {constants.INFO_KEK_FULL_LOWER_MESSAGE}: {kek_lower_layer_full_message}")
    # response after KEK injection
    response_bytes = serial_utils.read_full_response(ser)
    print(f"{constants.RESP} - after KEK Injection: {response_bytes.hex().upper()}")

    initial_ksn = parser.parse_initial_ksn(response_bytes)
    logger.info(f"{constants.INFO_INIT_KSN_RESP}: {initial_ksn}")

    """
    Start DUKPT Injection
    """
    # calculate key length in bits; then change to Hex
    bdk_length_string = str(int((len(bdk_data) / 2) * 8))
    bdk_length_hex = bdk_length_string.encode('utf-8').hex()
    print(f"bdk_length_hex: {bdk_length_hex}")

    # calculate IPEK from BDK
    ipek_plaintext = crypto_utils.derive_ipek_from_bdk(bdk_data, ksn, key_algo)
    print(f"{constants.INFO_IPEK_PLAIN}: {ipek_plaintext}")
    # calculate KCV for IPEK
    ipek_kcv_plaintext = crypto_utils.calculate_kcv(ipek_plaintext, key_algo)

    print(f"SN: {sn}; RSA Pub Key: {rsa_pub_key_hex}; KSN: {ksn}; Plaintext IPEK: {ipek_plaintext}; Plaintext KCV: {ipek_kcv_plaintext}")

    # Encrypt IPEK and KCV
    if key_algo == constants.KEY_3DES:
        key_type = '31'
        ipek_cipher = crypto_utils.key_encryption_from_kek(ipek_plaintext, constants.KEK_TSYS, key_algo, False)
        dukpt_ksn_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_KSN, ksn)
    elif key_algo == constants.KEY_AES:
        key_type = '32'
        ipek_cipher = crypto_utils.key_encryption_from_kek(ipek_plaintext, '0' * 32, key_algo, False)
        print(f"ipek_cipher: {ipek_cipher}")
        dukpt_ksn_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_KSN, ksn)
    else:
        raise ValueError("Unsupported algorithm: choose 3DES / AES")

    ipek_kcv_cipher = crypto_utils.key_encryption_from_kek(ipek_kcv_plaintext, constants.KEK_TSYS, key_algo, True)

    # build DUKPT_IPEK each packet
    dukpt_key_type_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_KEY_LENGTH, bdk_length_hex)

    dukpt_key_length_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_3DES_AES, key_type)

    dukpt_cipher_data_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_CIPHER, ipek_cipher)
    dukpt_cipher_kcv_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_KCV_CIPHER, ipek_kcv_cipher)

    bdk_index_packet = build_packet_utils.build_upper_layer_packet(constants.TYPE_DUKPT_IDX, bdk_idx)
    subsequent_data = build_packet_utils.build_upper_layer_packet(constants.TYPE_SUBSEQ_DATA, constants.NO_SUBSEQ)

    # Build higher layer packet for dukpt with plaintext
    dukpt_full_packet = dukpt_key_type_packet + dukpt_key_length_packet + dukpt_cipher_data_packet + dukpt_cipher_kcv_packet + dukpt_ksn_packet + bdk_index_packet + subsequent_data
    print(f"{constants.INFO_DUKPT_HIGHER_PACKET} : {dukpt_full_packet}")

    #Encrypted dukpt packet with RSA public key
    dukpt_rsa_encrypt_full_packet = crypto_utils.rsa_encrypt_hex(rsa_pub_key_hex, dukpt_full_packet)
    print('rsa_pub_key_hex: ', rsa_pub_key_hex)
    print('Leo-3: ', dukpt_rsa_encrypt_full_packet)
    dukpt_low_layer_full_package = build_packet_utils.build_lower_layer_packet(dukpt_rsa_encrypt_full_packet, constants.CMD_DUKPT_INTERACTION)
    print(f"Send {constants.INFO_DUKPT_FULL_LOWER_MESSAGE}: {dukpt_low_layer_full_package}")

    # send DUKPT response (bytes) to TargetPOS
    ser.write(bytes.fromhex(dukpt_low_layer_full_package))

    response_bytes = serial_utils.read_full_response(ser)
    print(f"{constants.RESP}: {response_bytes.hex().upper()}")

    # close serial port
    ser.close()

    print("✅ Key Injection successful.\n")


if __name__ == "__main__":
    # for testing: hardcode for some information such as bdk data, key type
    run_key_injection("/dev/cu.usbserial-10", 115200, '3DES','1112', constants.BDK_PLAIN, constants.BDK_3DES_KSN)  # 默认串口/波特率