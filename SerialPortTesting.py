import time
import binascii
import serial.tools.list_ports

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

start = '02'
payload_mark = 'FFFFFFFF'
end = '03'

establish_connection = '0001'
connection_answer = '8001'
process_ends = '8002'
retry = '8003'
dukpt_interaction =  '8010'
kek_interaction = '8011'
eft_interaction ='8013'
tmk_interaction = '8014'
kbpk_interaction = '8015'

type_ksn = '6900'
type_sn = '6901'
type_rsa_public_key = '6902'
type_dukpt_ciphertext_data = '6903'
type_dukpt_ciphertext_kcv = '6904'
type_kek_plaintext_data = '6905'
type_kek_kcv = '6906'
type_dukpt_ksn = '6907'
type_dukpt_index = '6908'
type_dukpt_3des_aes = '6910'
type_key_length = '6911'
etf_key = '6909'
eft_kcv = '690A'
eft_index = '690B'

tmk_ciphertext = '6F01'
tmk_kcv = '6F02'
tmk_index = '6F03'

kbpk_key_data = '6F04'
kbpk_kcv = '6F05'
kbpk_index = '6F06'
type_subsequent_data = '6F00'

# make sure we have the Lib
print(serial.__file__)
print(hasattr(serial, "Serial"))

# 获取所有可用串口
ports = serial.tools.list_ports.comports()

# 打印串口信息
for port in ports:
    print(f"Device: {port.device}, Description: {port.description}, Hardware ID: {port.hwid}")

port_name = input("Enter Device name: ")

handshake_ok_bytes = bytes.fromhex('020008FFFFFFFF80013030038A')
handshake_retry_bytes = bytes.fromhex('020008FFFFFFFF800330300388')

send_handshake_data_hex = "020006FFFFFFFF00010304"
# Convert to Bytes
data_bytes = bytes.fromhex(send_handshake_data_hex)
# kek information
kek_tsys = '679BF40E8C1329FD380E83D3A7C157D5'
kek_kcv_tsys = 'B5D6451B9BE94349'
kek_packet_plaintext_hex = '69050020' + kek_tsys + '69060010' + kek_kcv_tsys

bdk_plaintext = '0123456789ABCDEFFEDCBA9876543210'
bkd_kcv_plaintext = '08D7B4FB629D0885'
bdk_cypher = '2E51D99703F78E38E2C04C645C884BB3'
bkd_kcv_cypher = '50D2D8ABE11C67EB'
bdk_ksn = 'FFFF5B467C7DC5E00001'
bdk_index = '06'
non_subsequent_data = '00'


# Serial Port Configuration
ser = serial.Serial(
    port=port_name,
    baudrate=115200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=3
)

# 等待串口稳定
time.sleep(2)

# send handshake (bytes) to TargetPOS
ser.write(data_bytes)
print(f"send: {data_bytes}")

response_bytes = b""
while True:
    chunk = ser.read(1024)  # 每次最多读 1KB
    if not chunk:
        break  # 超时，说明读完了
    response_bytes += chunk
print(f"response: {response_bytes}")
print(f"完整数据: {response_bytes.hex().upper()}")

# 接收来自 TargetPOS 的回显
# response_bytes = ser.readline()
# print(f'response: {response_bytes}')


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
        response = "✅ Success"
    elif handshake_retry_bytes in data:
        response = "❌ Retry"
    else:
        response ="❌ Failed"
    return response

def parse_sn(data: bytes) -> str:
    """
    先将 bytes 转 HEX 字符串，再按照 TLV 解析 SN
    TLV 格式: 69 01 [长度 2字节] [SN数据]
    """
    data_hex = data.hex().upper()  # bytes -> HEX
    # TLV 头部
    head = type_sn
    idx = data_hex.find(head)
    if idx == -1:
        return None

    # 长度字段 1字节或2字节？原 bytes 用 idx+2:idx+4 两字节
    length_hex = data_hex[idx + 4: idx + 8]  # 两字节长度 HEX
    length = int(length_hex, 16)
    print(f"length: {length}")

    # SN 数据段，每字节对应 2 个 HEX 字符
    sn_hex = data_hex[idx + 8: idx + 8 + length]
    print(f"length: {length}, hex: {sn_hex}")

    if len(sn_hex) < length:
        return None

    # 转回 ASCII
    sn_bytes = bytes.fromhex(sn_hex)
    return sn_bytes.decode('ascii')

def parse_rsa_public(data: bytes) -> hex:
    """
    先把 bytes 转 HEX 字符串，再在 HEX 字符串里按 TLV 解析 RSA 公钥
    TLV 格式: 69 02 [长度 2字节] [payload]
    """
    # 先转换为 HEX 字符串（方便显示）
    hex_data = data.hex().upper()
    print(f"Full HEX: {hex_data}")
    # TLV 中，头是 "6902"
    head = type_rsa_public_key
    idx = hex_data.find(head)
    if idx == -1:
        return None

    # 长度字段 2字节 -> HEX 字符串 4位
    length_hex = hex_data[idx + 4: idx + 8]  # 两个字节对应 4 个 HEX 字符
    length = int(length_hex, 16)
    print(f"length: {length}")

    # 数据段在 HEX 中，每字节对应两个 HEX 字符
    payload_hex = hex_data[idx + 8: idx + 8 + length]
    print(payload_hex)
    print(len(payload_hex))
    if len(payload_hex) < length:
        # 数据不完整
        return None

    return payload_hex


# frame = read_full_frame(ser)
# print(type(frame))
# print(f"raw frame: {frame.hex()}")
#
# if verify_checksum(frame):
#     print("Checksum OK!")
# else:
#     print("Checksum Error!")


# print(f"Handshake: {is_handshake_ok(response_bytes)}")
# print("SN:", parse_sn(response_bytes))

def rsa_encrypt_hex(pubkey_der_hex: hex, plaintext_hex: hex) -> hex:
    """
    使用 RSA 公钥加密 HEX 字符串数据
    :param pubkey_der_hex: RSA 公钥 DER HEX
    :param plaintext_hex: 待加密数据 HEX
    :return: 密文Key HEX
    """
    # HEX 转 bytes
    pubkey_bytes_1 = bytes.fromhex(pubkey_der_hex)
    print(f"pubkey_bytes1: {pubkey_bytes_1}")

    # 明文密钥是按照字符串本身去加密。所以计算的时候也是按照54字节
    plaintext_bytes_1 = bytes.fromhex(plaintext_hex)
    print(f"plaintext_bytes1: {plaintext_bytes_1}")
    plaintext_bytes_2 = plaintext_hex.encode("utf-8")  # 得到54字节
    print(f"plaintext_bytes2: {plaintext_bytes_2}")

    # 载入 RSA 公钥
    public_key = serialization.load_der_public_key(pubkey_bytes_1)

    # 加密
    ciphertext_bytes = public_key.encrypt(
        plaintext_bytes_2,
        padding.PKCS1v15()
    )

    # 返回 HEX
    return ciphertext_bytes.hex().upper()

sn = parse_sn(response_bytes)
print(f"sn: {sn}")
rsa_public_key_hex = parse_rsa_public(response_bytes)
print(f"RSA Public Key: {rsa_public_key_hex}")

def calc_checksum(frame_hex: str) -> int:
    frame = bytes.fromhex(frame_hex)

    # 参与校验的字节
    data_for_checksum = frame

    checksum = 0
    for b in data_for_checksum:
        checksum ^= b
    return checksum

frame_hex = "013FFFFFFFFF80116901001A504230344439374136303035346902024830820120300D06092A864886F70D01010105000382010D00308201080282010100C1988A7F0E322C248580E5F8F3417C3F50E69977D32D656D4A937ECEB08649889B6B8B6E6581541DB0695D5928E4FC5A60E5BE493BBA82BCA8E5C35418F3DEA3C83831DCB6A29F823903D265A637C51ADFD7E38B6667CD74502D7DC34C2945933746BB0D8E725E3E77C16E7B117BD2B26B5EE375828187390112C0CB3C43BD865C115887A388732DB55BA80EBE330B2EE07BC247BC9AAC60205DB6197414B82068FC06CE70C887DE6038FB2470432DF4463E01EC494C1F6FBC029B8E50827BA9AF49D8380447A306A716341527137733371679D50C8D03DC03E9AA8B043581A212400B7FF225E3BB57B0E217A0B0C1A3EE4D5A89875DDD630DD71355F46EF97302010303"

checksum = bytes([calc_checksum(frame_hex)])

data = bytes.fromhex(frame_hex)+bytes.fromhex(end)+checksum
print(data.hex().upper())



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
    mark_bytes = bytes.fromhex(payload_mark)
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

def parse_initial_ksn(data: bytes) -> str:
    """
    先将 bytes 转 HEX 字符串，再按照 TLV 解析 SN
    TLV 格式: 69 01 [长度 2字节] [SN数据]
    """
    data_hex = data.hex().upper()  # bytes -> HEX
    # TLV 头部
    head = type_ksn
    idx = data_hex.find(head)
    if idx == -1:
        return None

    # 长度字段 1字节或2字节？原 bytes 用 idx+2:idx+4 两字节
    length_hex = data_hex[idx + 4: idx + 8]  # 两字节长度 HEX
    length = int(length_hex, 16)
    print(f"length: {length}")

    # KSN 数据段，每字节对应 2 个 HEX 字符
    ksn_hex = data_hex[idx + 8: idx + 8 + length]
    print(f"length: {length}, hex: {ksn_hex}")

    if len(ksn_hex) < length:
        return None

    # 返回hex
    return ksn_hex




# KEK Injection
kek_plaintext_data_packet = build_upper_layer_packet(type_kek_plaintext_data, kek_tsys)
kek_plaintext_kcv_packet = build_upper_layer_packet(type_kek_kcv, kek_kcv_tsys)
kek_plaintext_full_packet = kek_plaintext_data_packet + kek_plaintext_kcv_packet
print(f"full_plaintext_kek_data: {kek_plaintext_full_packet}")
print(f"kek_packet_plaintext_hex: {kek_packet_plaintext_hex}")

kek_rsa_encrypt_full_packet = rsa_encrypt_hex(rsa_public_key_hex, kek_plaintext_full_packet)
print(f"kek_rsa_encrypt_full_packet: {kek_rsa_encrypt_full_packet}")

kek_process_full_package = build_lower_layer_packet(kek_rsa_encrypt_full_packet, kek_interaction)
# send KEK response (bytes) to TargetPOS
ser.write(bytes.fromhex(kek_process_full_package))
print(f"send: {kek_process_full_package}")

response_bytes = b""
while True:
    chunk = ser.read(1024)  # 每次最多读 1KB
    if not chunk:
        break  # 超时，说明读完了
    response_bytes += chunk

print(f"kek_完整数据: {response_bytes.hex().upper()}")
initial_ksn = parse_initial_ksn(response_bytes)
print(f"initial_ksn: {initial_ksn}")
# response_bytes = ser.readline()
# print(f'response: {response_bytes}')





# BDK injection

bdk_key_type_packet = build_upper_layer_packet(type_key_length, '313238')
bdk_key_length_packet = build_upper_layer_packet(type_dukpt_3des_aes, '31')
bdk_cipher_data_packet = build_upper_layer_packet(type_dukpt_ciphertext_data, bdk_cypher)
bdk_cipher_kcv_packet = build_upper_layer_packet(type_dukpt_ciphertext_kcv, bkd_kcv_cypher)
bdk_ksn_packet = build_upper_layer_packet(type_dukpt_ksn, bdk_ksn)
bdk_index_packet = type_dukpt_index + '0002' + bdk_index
bdk_subsequent_data = type_subsequent_data + '0002' + non_subsequent_data
dukpt_full_packet = bdk_key_type_packet + bdk_key_length_packet + bdk_cipher_data_packet + bdk_cipher_kcv_packet + bdk_ksn_packet + bdk_index_packet + bdk_subsequent_data
print(f"dukpt_full_packet : {dukpt_full_packet}")
dukpt_rsa_encrypt_full_packet = rsa_encrypt_hex(rsa_public_key_hex, dukpt_full_packet)

dukpt_process_full_package = build_lower_layer_packet(dukpt_rsa_encrypt_full_packet, dukpt_interaction)
# send IPEK response (bytes) to TargetPOS
ser.write(bytes.fromhex(dukpt_process_full_package))
print(f"send: {dukpt_process_full_package}")

response_bytes = b""
while True:
    chunk = ser.read(1024)  # 每次最多读 1KB
    if not chunk:
        break  # 超时，说明读完了
    response_bytes += chunk

print(f"dukpt_完整数据: {response_bytes.hex().upper()}")





# close serial port
ser.close()