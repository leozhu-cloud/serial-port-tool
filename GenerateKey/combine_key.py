from binascii import unhexlify, hexlify

def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def combine_key_components(*components_hex: str) -> str:
    if not components_hex:
        raise ValueError("At least one component is required")

    components = [unhexlify(c) for c in components_hex]

    # 确保所有分量长度一致
    length = len(components[0])
    if any(len(c) != length for c in components):
        raise ValueError("All components must have the same length")

    result = components[0]
    for comp in components[1:]:
        result = xor_bytes(result, comp)

    return hexlify(result).decode().upper()

