import time
import serial
import logging
import serial.tools.list_ports
import constants

logger = logging.getLogger(__name__)


handshake_ok_bytes = bytes.fromhex(constants.HANDSHAKE_OK_RESP)
handshake_retry_bytes = bytes.fromhex(constants.HANDSHAKE_RETRY_RESP)


def get_available_ports() -> list[str]:
    """
    获取系统所有可用串口列表
    返回 ["COM1", "COM2", "/dev/ttyUSB0", ...]
    """
    ports = serial.tools.list_ports.comports()
    port_list = []
    for port in ports:
        # 打印信息，可选
        print(f"Device: {port.device}, Description: {port.description}, Hardware ID: {port.hwid}")
        port_list.append(port.device)
    return port_list

def open_serial(port_name: str, baud_rate: int) -> serial.Serial:
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=constants.SERIAL_TIMEOUT,
        )
        time.sleep(2)  # 等待稳定
        return ser
    except serial.SerialException as e:
        logger.error(f"串口打开失败: {e}")
        raise

def read_full_response(ser: serial.Serial, chunk_size: int = constants.SERIAL_READ_SIZE, timeout_sec: float = constants.SERIAL_TIMEOUT) -> bytes:
    response_bytes = b""
    start_time = time.time()
    while True:
        chunk = ser.read(chunk_size)
        if chunk:
            response_bytes += chunk
            start_time = time.time()
        else:
            if time.time() - start_time >= timeout_sec:
                break
    return response_bytes

def is_handshake_ok(data: bytes) -> bool:
    """
    判断从POS返回的握手结果
    """
    if handshake_ok_bytes in data:
        print(f"Handshake: ✅ {constants.SUCCESS_RESP}", flush=True)
        response = True
    elif handshake_retry_bytes in data:
        print(f"Handshake: ❌ {constants.RETRY_RESP}\n", flush=True)
        response = False
    else:
        print(f"Handshake: ❌ {constants.FAILURE_RESP}\n", flush=True)
        response = False
    return response
