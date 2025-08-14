import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import binascii
import time

handshake_ok_bytes = bytes.fromhex('020008FFFFFFFF80013030038A')
handshake_retry_bytes = bytes.fromhex('020008FFFFFFFF800330300388')
hex_send_data_hex = "020006FFFFFFFF00010304"

# --- GUI ---
root = tk.Tk()
root.title("TargetPOS Serial Port Testing")
root.geometry("650x400")

# --- GUI ---
log_text = tk.Text(root, height=15)
log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

# 创建一个总的水平 Frame
frame_top = tk.Frame(root)
frame_top.pack(pady=5, fill=tk.X, padx=10)

# --- 串口选择，左对齐 ---
port_var = tk.StringVar()

frame_device = tk.Frame(frame_top)  # 放在水平 Frame 里
frame_device.pack(pady=5, side=tk.LEFT, padx=10)

tk.Label(frame_device, text="Device:").pack(side=tk.LEFT)
ports_combo = ttk.Combobox(frame_device, textvariable=port_var, state="readonly")
ports_combo.pack(side=tk.LEFT)

# --- 波特率选择，右对齐 ---
baud_var = tk.StringVar(value="115200")
baud_options = [
    1200, 1800, 2400, 4800, 9600, 14400, 19200, 38400, 57600,
    115200, 230400, 460800, 614400, 921600, 1228800, 2457600, 3000000, 6000000
]

frame_baud = tk.Frame(frame_top)  # 放在水平 Frame 里
frame_baud.pack(pady=5, side=tk.RIGHT, padx=10)

tk.Label(frame_baud, text="Baud Rate:").pack(side=tk.LEFT)
baud_combo = ttk.Combobox(frame_baud, textvariable=baud_var, values=baud_options, state="readonly", width=10)
baud_combo.pack(side=tk.LEFT)


# --- 功能函数 ---
def log(msg):
    log_text.insert(tk.END, msg + "\n")
    log_text.see(tk.END)

def refresh_ports():
    ports = serial.tools.list_ports.comports()
    port_names = [port.device for port in ports]
    ports_combo['values'] = port_names
    if port_names:
        port_var.set(port_names[0])

def is_handshake_ok(data: bytes) -> str:
    if handshake_ok_bytes in data:
        return "✅ Success"
    elif handshake_retry_bytes in data:
        return "❌ Retry"
    else:
        return "❌ Failed"

def parse_sn(data: bytes) -> str:
    idx = data.find(b'\x69\x01')
    if idx == -1:
        return None
    sn = data[idx+4:idx+4+13]
    return sn.decode('ascii')

def do_handshake():
    port_name = port_var.get()
    if not port_name:
        messagebox.showwarning("Warning", "Please select a serial port")
        return
    try:
        baudrate = int(baud_var.get())
        ser = serial.Serial(
            port=port_name,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        time.sleep(1)
        data_bytes = bytes.fromhex(hex_send_data_hex)
        ser.write(data_bytes)
        log(f"Sent: {data_bytes.hex().upper()}")
        response_bytes = ser.readline()
        log(f"Received: {response_bytes.hex().upper()}")
        handshake_status = is_handshake_ok(response_bytes)
        sn = parse_sn(response_bytes)
        log(f"Handshake: {handshake_status}")
        log(f"SN: {sn} \n\n")
        ser.close()
    except Exception as e:
        log(f"Error: {e} \n\n")

# --- Buttons ---
frame_buttons = tk.Frame(root)
frame_buttons.pack(pady=5)

tk.Button(frame_buttons, text="Fresh Serial Port", command=refresh_ports).pack(side=tk.LEFT, pady=2)
tk.Button(frame_buttons, text="Send", command=do_handshake).pack(side=tk.LEFT, pady=2)

# 初始刷新串口
refresh_ports()
root.mainloop()