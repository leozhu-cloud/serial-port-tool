import time
import binascii
import serial.tools.list_ports

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

hex_send_data_hex = "020006FFFFFFFF00010304"
# Convert to Bytes
data_bytes = bytes.fromhex(hex_send_data_hex)

# Serial Port Configuration
ser = serial.Serial(
    port=port_name,
    baudrate=1200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1
)

# 等待串口稳定
time.sleep(2)

# send bytes to TargetPOS
ser.write(data_bytes)
print(f"send: {data_bytes}")

# 接收来自 TargetPOS 的回显
response_bytes = ser.readline()
print(f'response: {response_bytes}')
hex_response = binascii.hexlify(response_bytes).decode().upper()
print(hex_response)

ser.close()

def is_handshake_ok(data: bytes) -> str:
    if handshake_ok_bytes in data:
        response = "✅ Success"
    elif handshake_retry_bytes in data:
        response = "❌ Retry"
    else:
        response ="❌ Failed"
    return response

def parse_sn(data: bytes) -> str:
    idx = data.find(b'\x69\x01')
    if idx == -1:
        return None
    sn = data[idx+4:idx+4+13]  # Sunmi SN is fixed 13 digital number (hex 1a = Decimal 26)
    return sn.decode('ascii')

print(f"Handshake: {is_handshake_ok(response_bytes)}")
print("SN:", parse_sn(response_bytes))