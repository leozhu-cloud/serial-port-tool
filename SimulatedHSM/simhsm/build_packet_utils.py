from binascii import unhexlify, hexlify
from . import constants

def build_upper_layer_packet(type_hex: str, data_hex: str) -> str:
    """
    构建上层包（第一个包））
    type_hex: 2字节 HEX
    data_hex: n字节 HEX
    return: 完整报文 (type+length+data)
    """
    # 转为 bytes
    data_bytes = unhexlify(data_hex)
    # 按字符算：计算packet data 的 length
    length = len(data_hex)
    # length 换算成 hex
    length_bytes = length.to_bytes(2, 'big') # 2字节大端
    packet = bytes.fromhex(type_hex) + length_bytes + data_bytes
    return hexlify(packet).upper().decode()

def build_lower_layer_packet(packet_hex: str, command_hex: str) -> str:
    head = b'\x02'
    mark_bytes = unhexlify(constants.PAYLOAD_MARK)
    command_bytes = unhexlify(command_hex)
    payload_bytes = unhexlify(packet_hex)
    end = b'\x03'
    length = len(payload_bytes) + len(mark_bytes) + len(command_bytes)
    len_bytes = length.to_bytes(2, 'big')
    frame_without_checksum = head + len_bytes + mark_bytes + command_bytes + payload_bytes + end
    checksum = 0
    for b in len_bytes + mark_bytes + command_bytes + payload_bytes + end:
        checksum ^= b
    return hexlify(frame_without_checksum + bytes([checksum])).upper().decode()