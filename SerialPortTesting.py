import constants as constants
import sys
import logging
import time
import binascii
import serial.tools.list_ports

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from binascii import unhexlify, hexlify
from Crypto.Cipher import DES3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# make sure we have the Lib
print(serial.__file__)
print(hasattr(serial, "Serial"))

# 获取所有可用串口
ports = serial.tools.list_ports.comports()

# 打印串口信息
for port in ports:
    print(f"Device: {port.device}, Description: {port.description}, Hardware ID: {port.hwid}")

port_name = input("Enter Device name: ")

handshake_ok_bytes = bytes.fromhex(constants.HANDSHAKE_OK_RESP)
handshake_retry_bytes = bytes.fromhex(constants.HANDSHAKE_RETRY_RESP)


# Convert HEX of handshake command to Bytes
handshake_data_bytes = bytes.fromhex(constants.HANDSHAKE_CMD)
print(f"send {constants.INFO_HANDSHAKE_CMD_BYTES}: {handshake_data_bytes}")

# VARIANT_MASK 是固定的，标准定义，在ANSI X9.24 规范里写死的，处理 IPEK 的时候使用
VARIANT_MASK = bytes.fromhex('C0C0C0C000000000C0C0C0C000000000')


# Serial Port Configuration
try:
    ser = serial.Serial(
        port=port_name,
        baudrate=115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=constants.SERIAL_TIMEOUT,
    )
except serial.SerialException as e:
    logger.error(f"串口打开失败: {e}")
    sys.exit(1)


# 等待串口稳定
time.sleep(2)

# send handshake (bytes) to TargetPOS
ser.write(handshake_data_bytes)


def read_full_response(ser, chunk_size: int = constants.SERIAL_READ_SIZE, timeout_sec: float = constants.SERIAL_TIMEOUT) -> bytes:
    """
    从串口读取完整响应
    :param ser: Serial 对象
    :param chunk_size: 每次读取的字节数
    :param timeout_sec: 超时时间（秒），如果在 timeout_sec 内没有数据就停止
    :return: 接收到的完整字节流
    """
    response_bytes = b""
    start_time = time.time()

    while True:
        chunk = ser.read(chunk_size)
        if chunk:
            response_bytes += chunk
            start_time = time.time()  # 收到数据，重置超时计时
        else:
            # if timeout, break the circle
            if time.time() - start_time >= timeout_sec:
                break

    return response_bytes

def read_full_frame(ser):
    buffer = bytearray()

    while True:
        b = ser.read(1)
        if not b:
            continue  # 超时没数据，继续等待
        buffer += b

        # 检查是否至少读到 STX + Len(2 bytes)
        if len(buffer) >= 3:
            if buffer[0] != 0x02:
                # 不是开头，丢弃
                buffer.pop(0)
                continue

            # 获取长度
            length = (buffer[1] << 8) | buffer[2]

            # 总帧长度 = STX(1) + LEN(2) + Payload(length-1) + ETX(1) + checksum(1)
            total_len = 1 + 2 + length + 1  # len includes ETX? 如果长度只包含 Payload，请改成 length + 1
            if len(buffer) >= total_len + 1:  # +1 因为 checksum
                frame = buffer[:total_len + 1]
                buffer = buffer[total_len + 1:]  # 剩余数据留在 buffer
                return frame


response_bytes = read_full_response(ser)
# response_bytes = b""
# while True:
#     chunk = ser.read(constants.SERIAL_READ_SIZE)  # 每次最多读 1KB
#     if not chunk:
#         break  # 超时，说明读完了
#     response_bytes += chunk
# print(f"response: {response_bytes}")
# print(f"完整数据: {response_bytes.hex().upper()}")
#
# 接收来自 TargetPOS 的回显
# response_bytes = ser.readline()
# print(f'response: {response_bytes}')

# 校验 checksum
def verify_checksum(frame):
    # frame = STX + LEN_H + LEN_L + PAYLOAD + ETX + CHECKSUM
    checksum = frame[-1]
    xor = 0
    for b in frame[1:-1]:  # LEN + PAYLOAD + ETX
        xor ^= b
    return xor == checksum

def is_handshake_ok(data: bytes) -> str:
    if handshake_ok_bytes in data:
        response = f"✅ {constants.SUCCESS_RESP}"
    elif handshake_retry_bytes in data:
        response = f"❌ {constants.RETRY_RESP}"
    else:
        response = f"❌ {constants.FAILURE_RESP}"
    return response

def parse_sn(data: bytes) -> str | None:
    """
    先将 bytes 转 HEX 字符串，再按照 TLV 解析 SN
    TLV 格式: 69 01 [长度 2字节] [SN数据]
    """
    try:
        data_hex = data.hex().upper()  # bytes -> HEX
        # TLV 头部
        head = constants.TYPE_SN
        idx = data_hex.find(head)
        if idx == -1:
            return None

        # 长度字段 1字节或2字节？原 bytes 用 idx+2:idx+4 两字节
        length_hex = data_hex[idx + 4: idx + 8]  # 两字节长度 HEX
        length = int(length_hex, 16)
        print(f"{constants.INFO_LENGTH}: {length}")

        # SN 数据段，每字节对应 2 个 HEX 字符
        sn_hex = data_hex[idx + 8: idx + 8 + length]
        print(f"{constants.INFO_LENGTH}: {length}, hex: {sn_hex}")

        if len(sn_hex) < length:
            return None

        # 转回 ASCII
        sn_bytes = bytes.fromhex(sn_hex)
        return sn_bytes.decode('ascii')

    except Exception as e:
        logger.error(f"{constants.ERR_PARSE_SN}: {e}")
        return None

def parse_rsa_public(data: bytes) -> hex:
    """
    先把 bytes 转 HEX 字符串，再在 HEX 字符串里按 TLV 解析 RSA 公钥
    TLV 格式: 69 02 [长度 2字节] [payload]
    """
    try:
        # 先转换为 HEX 字符串（方便显示）
        hex_data = data.hex().upper()
        print(f"Full HEX: {hex_data}")
        # TLV 中，头是 "6902"
        head = constants.TYPE_RSA_PUBLIC_KEY
        idx = hex_data.find(head)
        if idx == -1:
            return None

        # 长度字段 2字节 -> HEX 字符串 4位
        length_hex = hex_data[idx + 4: idx + 8]  # 两个字节对应 4 个 HEX 字符
        length = int(length_hex, 16)
        print(f"{constants.INFO_LENGTH}: {length}")

        # 数据段在 HEX 中，每字节对应两个 HEX 字符
        payload_hex = hex_data[idx + 8: idx + 8 + length]
        logger.debug(f"payload_hex: {payload_hex}")
        logger.debug(len(payload_hex))
        if len(payload_hex) < length:
            # 数据不完整
            return None

        return payload_hex

    except Exception as e:
        logger.error(f"{constants.ERR_PARSE_RSA}: {e}")
        return None


logger.info(f"Handshake: {is_handshake_ok(response_bytes)}")

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
        logger.error(f":{constants.ERR_RSA_KEY_LOAD}: {e}")
        return None

    # 加密
    try:
        ciphertext_bytes = public_key.encrypt(
            plaintext_bytes,
            padding.PKCS1v15()
        )
    except Exception as e:
        logger.error(f"{constants.ERR_RSA_ENC}: {e}")
        return None


    # 返回 HEX
    return ciphertext_bytes.hex().upper()

try:
    sn = parse_sn(response_bytes)
except Exception as e:
    logger.error(f"{constants.ERR_PARSE_SN}: {e}")
    sn = None
logger.info(f"{constants.INFO_SN_RESP}: {sn}")

rsa_public_key_hex = parse_rsa_public(response_bytes)
logger.info(f"{constants.INFO_RSA_PUB_KEY}: {rsa_public_key_hex}")

def calc_checksum(frame_hex: str) -> int:
    frame = bytes.fromhex(frame_hex)

    # 参与校验的字节
    data_for_checksum = frame

    checksum = 0
    for b in data_for_checksum:
        checksum ^= b
    return checksum

# frame_hex = "013FFFFFFFFF80116901001A504230344439374136303035346902024830820120300D06092A864886F70D01010105000382010D00308201080282010100C1988A7F0E322C248580E5F8F3417C3F50E69977D32D656D4A937ECEB08649889B6B8B6E6581541DB0695D5928E4FC5A60E5BE493BBA82BCA8E5C35418F3DEA3C83831DCB6A29F823903D265A637C51ADFD7E38B6667CD74502D7DC34C2945933746BB0D8E725E3E77C16E7B117BD2B26B5EE375828187390112C0CB3C43BD865C115887A388732DB55BA80EBE330B2EE07BC247BC9AAC60205DB6197414B82068FC06CE70C887DE6038FB2470432DF4463E01EC494C1F6FBC029B8E50827BA9AF49D8380447A306A716341527137733371679D50C8D03DC03E9AA8B043581A212400B7FF225E3BB57B0E217A0B0C1A3EE4D5A89875DDD630DD71355F46EF97302010303"
#
# checksum = bytes([calc_checksum(frame_hex)])
#
# data = bytes.fromhex(frame_hex)+bytes.fromhex(end)+checksum
# print(data.hex().upper())



def build_upper_layer_packet(type_hex: hex, data_hex: hex) -> hex:
    """
    构建上层包（第一个包））
    type_hex: 2字节 HEX
    data_hex: n字节 HEX
    return: 完整报文 (type+length+data)
    """
    # 转为 bytes
    data_bytes = bytes.fromhex(data_hex)
    # 按字符算：计算packet data 的 length
    length = len(data_hex)
    # length 换算成 hex
    length_bytes = length.to_bytes(2, 'big')  # 2字节大端
    # 获取完整包文的bytes
    packet = bytes.fromhex(type_hex) + length_bytes + data_bytes
    return packet.hex().upper()

def build_lower_layer_packet(packet_hex: hex, command_hex: hex) -> hex:
    """
    构建下层包（第二个包）
    packet_hex: 上层包作为 Payload
    mark_hex, command_hex: 固定字段
    返回完整报文（含 Head, Len, Mark, Command, Payload, End, Checksum）
    """

    # 转为 bytes
    head = b'\x02'
    mark_bytes = bytes.fromhex(constants.PAYLOAD_MARK)
    command_bytes = bytes.fromhex(command_hex)
    payload_bytes = bytes.fromhex(packet_hex)  # 上层包作为Packet
    end = b'\x03'

    # 按字节算：Len = payload_len + Mark(4)+Command(2)+End(1)
    length = len(payload_bytes) + len(mark_bytes) + len(command_bytes)
    len_bytes = length.to_bytes(2, 'big')

    # 构建完整报文(不含Checksum)
    frame_without_checksum = head + len_bytes + mark_bytes + command_bytes + payload_bytes + end

    # 计算Checksum
    data_for_checksum = len_bytes + mark_bytes + command_bytes + payload_bytes + end
    checksum = 0
    for b in data_for_checksum:
        checksum ^= b

    full_frame = frame_without_checksum + bytes([checksum])
    return full_frame.hex().upper()

def parse_initial_ksn(data: bytes) -> str | None:
    """
    先将 bytes 转 HEX 字符串，再按照 TLV 解析 SN
    TLV 格式: 69 01 [长度 2字节] [SN数据]
    """
    try:
        data_hex = data.hex().upper()  # bytes -> HEX
        # TLV 头部
        head = constants.TYPE_KSN
        idx = data_hex.find(head)
        if idx == -1:
            return None

        # 长度字段 1字节或2字节？原 bytes 用 idx+2:idx+4 两字节
        length_hex = data_hex[idx + 4: idx + 8]  # 两字节长度 HEX
        length = int(length_hex, 16)
        print(f"{constants.INFO_LENGTH}: {length}")

        # KSN 数据段，每字节对应 2 个 HEX 字符
        ksn_hex = data_hex[idx + 8: idx + 8 + length]
        print(f"{constants.INFO_LENGTH}: {length}, hex: {ksn_hex}")

        if len(ksn_hex) < length:
            return None

        # 返回hex
        return ksn_hex

    except Exception as e:
        logger.error(f"{constants.ERR_PARSE_KSN}: {e}")
        return None

def derive_ipek_from_bdk(bdk_hex: str, initial_ksn_hex: str) -> str:
    """
    输入:
      bdk_hex: 16 bytes BDK 的十六进制字符串 (such as '0123...3210')
      ksn_hex: 10 bytes KSN 的十六进制字符串 (such as 'FFFF9876543210E00008')
    输出:
      32字节 IPEK 的十六进制字符串
    """

    bdk = binascii.unhexlify(bdk_hex)
    if len(bdk) not in (16, 24):
        raise ValueError(f"{constants.ERR_BDK_LENGTH}")

    ksn = bytearray(binascii.unhexlify(initial_ksn_hex))
    if len(ksn) != 10:
        raise ValueError(f"{constants.ERR_KSN_LENGTH}")

    # 清零 KSN 低 21 位（DUKPT 规范）
    ksn_masked = ksn[:]
    ksn_masked[9] = 0x00
    ksn_masked[8] = 0x00
    ksn_masked[7] &= 0xE0

    # 取处理后的前 8 字节作为数据块
    data_block = bytes(ksn_masked[:8])

    # 3DES-ECB 加密函数（PyCryptodome 会处理 16 字节 2-key 3DES 为 K1|K2|K1）
    def tdes_encrypt(key: bytes, block: bytes) -> bytes:
        return DES3.new(key, DES3.MODE_ECB).encrypt(block)

    # keyA = BDK
    left = tdes_encrypt(bdk, data_block)

    # keyB = BDK XOR VARIANT_MASK
    key_variant = bytes(a ^ b for a, b in zip(bdk, VARIANT_MASK))
    right = tdes_encrypt(key_variant, data_block)

    ipek = left + right
    return hexlify(ipek).upper().decode()

def key_encryption_from_kek(key_hex: str, kek_hex: str) -> str:
    key = unhexlify(key_hex)
    kek = unhexlify(kek_hex)

    # KEK must be 16 or 24 bytes
    if len(kek) == 16:
        kek = kek + kek[:8]  # 扩展成 K1-K2-K1 模式的 24字节
    elif len(kek) != 24:
        raise ValueError("KEK must be 16 or 24 bytes.")

    if len(key) % 8 != 0:
        raise ValueError("BDK must be a multiple of 8 bytes.")

    cipher = DES3.new(kek, DES3.MODE_ECB)

    encrypted = b''
    for i in range(0, len(key), 8):
        block = key[i:i + 8]
        encrypted += cipher.encrypt(block)

    return hexlify(encrypted).decode().upper()

def calculate_kcv(key_hex: str) -> str:
    key = unhexlify(key_hex)

    # 补齐成三重 DES 密钥：K1-K2-K1
    if len(key) == 16:
        key += key[:8]  # 双长补成三段式 K1-K2-K1
    elif len(key) != 24:
        raise ValueError("GenerateKey must be either 16 or 24 bytes (32 or 48 hex characters)")

    cipher = DES3.new(key, DES3.MODE_ECB)
    zero_block = b'\x00' * 8
    encrypted = cipher.encrypt(zero_block)

    # KCV = 前 8 个字节（16 hex 字符）
    kcv = hexlify(encrypted[:8]).decode().upper()
    return kcv


kek_kcv = calculate_kcv(constants.KEK_TSYS)
# KEK Injection
kek_plaintext_data_packet = build_upper_layer_packet(constants.TYPE_KEK_PLAIN, constants.KEK_TSYS)
kek_plaintext_kcv_packet = build_upper_layer_packet(constants.TYPE_KEK_KCV, kek_kcv)
kek_plaintext_full_packet = kek_plaintext_data_packet + kek_plaintext_kcv_packet
logger.debug(f"full_plaintext_kek_data: {kek_plaintext_full_packet}")

kek_rsa_encrypt_full_packet = rsa_encrypt_hex(rsa_public_key_hex, kek_plaintext_full_packet)
logger.info(f"kek_rsa_encrypt_full_packet: {kek_rsa_encrypt_full_packet}")

kek_lower_layer_full_message = build_lower_layer_packet(kek_rsa_encrypt_full_packet, constants.CMD_KEK_INTERACTION)
# send KEK response (bytes) to TargetPOS
ser.write(bytes.fromhex(kek_lower_layer_full_message))
logger.info(f"Send {constants.INFO_KEK_FULL_LOWER_MESSAGE}: {kek_lower_layer_full_message}")

response_bytes = read_full_response(ser)
logger.info(f"{constants.RESP}: {response_bytes.hex().upper()}")

initial_ksn = parse_initial_ksn(response_bytes)
logger.info(f"{constants.INFO_INIT_KSN_RESP}: {initial_ksn}")

# calculate key length in bits; then change to Hex
bdk_length_string = str(int((len(constants.BDK_PLAIN) / 2) * 8))
bdk_length_hex = bdk_length_string.encode('utf-8').hex()
print(f"bdk_length_hex: {bdk_length_hex}")
# calculate IPEK
ipek_plaintext = derive_ipek_from_bdk(constants.BDK_PLAIN, initial_ksn)
logger.info(f"{constants.INFO_IPEK_PLAIN}: {ipek_plaintext}")

ipek_kcv_plaintext = calculate_kcv(ipek_plaintext)
ipek_cipher = key_encryption_from_kek(ipek_plaintext, constants.KEK_TSYS)
ipek_kcv_cipher = key_encryption_from_kek(ipek_kcv_plaintext, constants.KEK_TSYS)
# DUKPT injection
dukpt_key_type_packet = build_upper_layer_packet(constants.TYPE_KEY_LENGTH, bdk_length_hex)
dukpt_key_length_packet = build_upper_layer_packet(constants.TYPE_DUKPT_3DES_AES, '31')
dukpt_cipher_data_packet = build_upper_layer_packet(constants.TYPE_DUKPT_CIPHER, ipek_cipher)
dukpt_cipher_kcv_packet = build_upper_layer_packet(constants.TYPE_DUKPT_KCV_CIPHER, ipek_kcv_cipher)
dukpt_ksn_packet = build_upper_layer_packet(constants.TYPE_DUKPT_KSN, constants.BDK_3DES_KSN)
bdk_index_packet = build_upper_layer_packet(constants.TYPE_DUKPT_IDX, constants.BDK_IDX)
subsequent_data = build_upper_layer_packet(constants.TYPE_SUBSEQ_DATA, constants.NO_SUBSEQ)

# Build higher layer packet for dukpt with plaintext
dukpt_full_packet = dukpt_key_type_packet + dukpt_key_length_packet + dukpt_cipher_data_packet + dukpt_cipher_kcv_packet + dukpt_ksn_packet + bdk_index_packet + subsequent_data
logger.info(f"{constants.INFO_DUKPT_HIGHER_PACKET} : {dukpt_full_packet}")

#Encrypted dukpt packet with RSA public key
dukpt_rsa_encrypt_full_packet = rsa_encrypt_hex(rsa_public_key_hex, dukpt_full_packet)

dukpt_low_layer_full_package = build_lower_layer_packet(dukpt_rsa_encrypt_full_packet, constants.CMD_DUKPT_INTERACTION)
logger.info(f"Send {constants.INFO_DUKPT_FULL_LOWER_MESSAGE}: {dukpt_low_layer_full_package}")

# send DUKPT response (bytes) to TargetPOS
ser.write(bytes.fromhex(dukpt_low_layer_full_package))

response_bytes = read_full_response(ser)
logger.info(f"{constants.RESP}: {response_bytes.hex().upper()}")


# close serial port
ser.close()