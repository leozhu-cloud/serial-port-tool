import logging
import constants

logger = logging.getLogger(__name__)

def parse_sn(data: bytes) -> str | None:
    try:
        data_hex = data.hex().upper()
        idx = data_hex.find(constants.TYPE_SN)
        if idx == -1:
            return None
        length = int(data_hex[idx + 4: idx + 8], 16)
        sn_hex = data_hex[idx + 8: idx + 8 + length]
        return bytes.fromhex(sn_hex).decode('ascii')
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

def parse_initial_ksn(data: bytes) -> str | None:
    """
    initial KSN is from devices
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