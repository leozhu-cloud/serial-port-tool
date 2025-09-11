import binascii
from binascii import unhexlify, hexlify
from Crypto.Cipher import DES3, AES
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
import logging
import constants

logger = logging.getLogger(__name__)

VARIANT_MASK_3DES = bytes.fromhex('C0C0C0C000000000C0C0C0C000000000')
VARIANT_MASK_AES = bytes.fromhex('00000000000000FF00000000000000FF')


def rsa_encrypt_hex(pubkey_der_hex: hex, plaintext_hex: hex) -> hex:
    """
    使用 RSA 公钥加密 HEX 字符串数据
    :param pubkey_der_hex: RSA 公钥 DER HEX
    :param plaintext_hex: 待加密数据 HEX
    :return: 密文Key HEX
    """
    # HEX 转 bytes
    pubkey_bytes = bytes.fromhex(pubkey_der_hex)
    print(f"pubkey_bytes1: {pubkey_bytes}")

    # 加密“报文 HEX 文本”的版本（推荐用于 TLV 报文）
    # 得到54字节，得到字符串本身的内容，例如69，把 "69110006" 当做字符串加密；而不是HEX，例如 69 -> i，然后去加密
    plaintext_bytes = plaintext_hex.encode("utf-8")
    print(f"plaintext_bytes2: {plaintext_bytes}")

    # 加密“字节密钥”的版本
    # 明文密钥是按照字符串本身去加密。所以计算的时候也是按照54字节，所以为什么下面的做法是错误的，因为变成了HEX
    # plaintext_bytes_1 = bytes.fromhex(plaintext_hex)
    # print(f"plaintext_bytes1: {plaintext_bytes_1}")

    # 载入 RSA 公钥
    try:
        public_key = serialization.load_der_public_key(pubkey_bytes)
    except ValueError as e:
        print(f":{constants.ERR_RSA_KEY_LOAD}: {e}")
        return None

    # 加密
    try:
        ciphertext_bytes = public_key.encrypt(
            plaintext_bytes,
            padding.PKCS1v15()
        )
    except Exception as e:
        print(f"{constants.ERR_RSA_ENC}: {e}")
        return None


    # 返回 HEX
    return ciphertext_bytes.hex().upper()


def derive_ipek_from_bdk(bdk_hex: str, initial_ksn_hex: str, algo: str) -> str:
    """
    派生 IPEK（支持 3DES 或 AES）
    输入:
      bdk_hex: 16/24 bytes (3DES) / 16/24/32 bytes (AES) BDK 的十六进制字符串 (such as '0123456789ABCDEFFEDCBA9876543210')
      ksn_hex: 10 bytes (3DES) / 12 bytes (AES) KSN 的十六进制字符串 (such as 'FFFF9876543210E00008')
      algorithm: "3DES" 或 "AES"
    输出:
      IPEK 的十六进制字符串
    """

    bdk = binascii.unhexlify(bdk_hex)

    ksn = bytearray(binascii.unhexlify(initial_ksn_hex))

    # 清零 KSN 低 21 位（DUKPT 规范）
    ksn_masked = ksn[:]
    ksn_masked[9] = 0x00
    ksn_masked[8] = 0x00
    ksn_masked[7] &= 0xE0

    # 取处理后的前 8 字节作为数据块
    data_block = bytes(ksn_masked[:8])

    if algo.upper() == "3DES":
        if len(ksn) != 10:
            raise ValueError(f"{constants.ERR_KSN_LENGTH}")

        if len(bdk) not in (16, 24):
            raise ValueError(f"{constants.ERR_BDK_3DES_LENGTH}")

        # 3DES-ECB 加密函数（PyCryptodome 会处理 16 字节 2-key 3DES 为 K1|K2|K1）
        def des3_encrypt(block):
            return DES3.new(bdk, DES3.MODE_ECB).encrypt(block)

        # keyA = BDK
        left = des3_encrypt(data_block)

        # keyB = BDK XOR VARIANT_MASK
        key_variant = bytes(a ^ b for a, b in zip(bdk, VARIANT_MASK_3DES))
        right = DES3.new(key_variant, DES3.MODE_ECB).encrypt(data_block)

        ipek = left + right

    elif algo.upper() == "AES":
        if len(ksn) != 12:
            raise ValueError(f"{constants.ERR_KSN_LENGTH}")

        if len(bdk) not in (16, 24, 32):
            raise ValueError(f"{constants.ERR_BDK_AES_LENGTH}")

        # AES-ECB 加密函数
        def aes_encrypt(block, key):
            padded = pad(block, AES.block_size)  # 16 bytes padding
            cipher = AES.new(key, AES.MODE_ECB)
            return cipher.encrypt(padded)

        # 左分支
        left = aes_encrypt(data_block, bdk)

        # 右分支 = BDK XOR VARIANT_MASK
        variant_mask = VARIANT_MASK_AES[:len(bdk)]
        key_variant = bytes(a ^ b for a, b in zip(bdk, variant_mask))
        right = aes_encrypt(data_block, key_variant)

        # XOR 左右，取前 len(left) 字节作为 IPEK
        # 组合方式：扩展/拼接到和 BDK 一致长度
        if len(bdk) == 16:
            ipek = bytes(x ^ y for x, y in zip(left, right))
        elif len(bdk) == 24:
            ipek = (bytes(x ^ y for x, y in zip(left, right)) +
                    bytes(x ^ y for x, y in zip(left[:8], right[:8])))
        elif len(bdk) == 32:
            ipek = (bytes(x ^ y for x, y in zip(left, right)) +
                    bytes(x ^ y for x, y in zip(left, right)))  # 复制一遍

    else:
        raise ValueError("'3DES' and 'AES' are only options")

    return hexlify(ipek).upper().decode()


def key_encryption_from_kek(key_hex: str, kek_hex: str, algo: str, kcv: bool, pkcs7: bool) -> str:
    key = unhexlify(key_hex)
    kek = unhexlify(kek_hex)
    algo = algo.upper()

    if algo == "3DES" or kcv is True:
        # KEK must be 16 or 24 bytes
        if len(kek) == 16:
            kek = kek + kek[:8]  # 扩展成 K1-K2-K1 模式的 24字节
        elif len(kek) != 24:
            raise ValueError("KEK must be 16 or 24 bytes.")

        if len(key) % 8 != 0:
            raise ValueError("GenerateKey must be a multiple of 8 bytes for 3DES.")

        cipher = DES3.new(kek, DES3.MODE_ECB)

        encrypted = b''
        for i in range(0, len(key), 8):
            block = key[i:i + 8]
            encrypted += cipher.encrypt(block)

    elif algo == "AES":
        # KEK 必须是 16/24/32 字节
        if len(kek) not in (16, 24, 32):
            raise ValueError("AES KEK must be 16, 24, or 32 bytes.")

        cipher = AES.new(kek, AES.MODE_ECB)

        if pkcs7 is True:
            # ===== 🔑 PKCS5Padding 实际上等价于 PKCS7Padding，块大小 16 =====
            # only for SUNMI TargetPOS Key injection. If encrypted regular data, it can use Zeropadding
            padded_key = pad(key, AES.block_size, style="pkcs7")

            if len(padded_key) % 16 != 0:
                raise ValueError("GenerateKey must be a multiple of 16 bytes for AES.")

            encrypted = cipher.encrypt(padded_key)
            print(f"encrypted data with PKCS7Padding: {hexlify(encrypted).decode().upper()}")

        else:
            # ===== Zero Padding 处理 =====
            block_size = AES.block_size  # 16
            remainder = len(key) % block_size
            if remainder != 0:
                padded_key = key + b"\x00" * (block_size - remainder)
            else:
                padded_key = key

        encrypted = cipher.encrypt(padded_key)
        print(f"encrypted data with zero padding: {hexlify(encrypted).decode().upper()}")

    else:
        raise ValueError("Unsupported algorithm, choose '3DES' or 'AES'")

    return hexlify(encrypted).decode().upper()

def data_decryption_from_kek(cipher_hex: str, kek_hex: str, algo: str, pkcs7: bool) -> str:
    cipher_bytes = unhexlify(cipher_hex)
    kek_bytes = unhexlify(kek_hex)
    algo = algo.upper()

    if algo == "3DES":
        # KEK 扩展成 24 字节 (K1-K2-K1) 如果是 16 字节
        if len(kek_bytes) == 16:
            kek_bytes = kek_bytes + kek_bytes[:8]
        elif len(kek_bytes) != 24:
            raise ValueError("KEK must be 16 or 24 bytes for 3DES")
        cipher = DES3.new(kek_bytes, DES3.MODE_ECB)
        decrypted = cipher.decrypt(cipher_bytes)

    elif algo == "AES":
        if len(kek_bytes) not in (16, 24, 32):
            raise ValueError("KEK must be 16, 24, or 32 bytes for AES")
        cipher = AES.new(kek_bytes, AES.MODE_ECB)
        decrypted_padded = cipher.decrypt(cipher_bytes)

        if pkcs7 is True:
            # ===== 🔑 PKCS5Padding 实际上等价于 PKCS7Padding，块大小 16 =====
            decrypted = unpad(decrypted_padded, AES.block_size, style='pkcs7')
            print(f"decrypted data with pkcs7: {hexlify(decrypted).decode().upper()}")
        else:
            # ===== Zero Padding 处理 =====
            decrypted = decrypted_padded.rstrip(b'\x00')
            print(f"decrypted data with zero padding: {hexlify(decrypted).decode().upper()}")

    else:
        raise ValueError("Unsupported algorithm")

    return hexlify(decrypted).decode().upper()


def calculate_kcv(key_hex: str, algo: str) -> str:
    key = unhexlify(key_hex)

    if algo.upper() == constants.KEY_3DES:
        # 补齐成三重 DES 密钥：K1-K2-K1
        if len(key) == 16:
            key += key[:8]  # 双长补成三段式 K1-K2-K1
        elif len(key) != 24:
            raise ValueError("GenerateKey must be either 16 or 24 bytes (32 or 48 hex characters)")

        try:
            cipher = DES3.new(key, DES3.MODE_ECB)
        except Exception as e:
            print(e)

        zero_block = b'\x00' * 8

        encrypted = cipher.encrypt(zero_block)
        # KCV = 前 8 个字节（16 hex 字符）
        kcv = hexlify(encrypted[:8]).decode().upper()

    elif algo.upper() == constants.KEY_AES:
        if len(key) not in (16, 24, 32):  # AES-128 / AES-192 / AES-256
            raise ValueError("AES key must be 16, 24, or 32 bytes (32/48/64 hex characters)")
        cipher = AES.new(key, AES.MODE_ECB)
        zero_block = b'\x00' * 16  # AES block = 16 bytes

        encrypted = cipher.encrypt(zero_block)
        # KCV = 前 16 个字节（32 hex 字符）
        kcv = hexlify(encrypted[:16]).decode().upper()

    else:
        raise ValueError("Unsupported algorithm: choose / 3DES / AES")

    return kcv