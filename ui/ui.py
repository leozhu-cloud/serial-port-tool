import threading

import SimulatedHSM.main as hsm_main
import SimulatedHSM.simhsm.serial_utils

import GenerateKey.main as genkey_main

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import sys
import datetime

# 主题色
COLOR_PRIMARY = "#0A192F"       # 深蓝 主色
COLOR_SECONDARY = "#00BCD4"     # 青绿 按钮/高亮
COLOR_BACKGROUND = "#FFFFFF"    # 内容区背景
COLOR_TEXT_PRIMARY = "#FFFFFF"  # 白色文字
COLOR_TEXT_SECONDARY = "#B0BEC5"  # 灰色文字


def make_validator(var, length_label, aes_lengths, des_lengths, alg_var=None, fixed_alg=None):
    """
    通用校验函数工厂
    var: tk.StringVar 绑定的输入变量
    length_label: 显示长度的 Label
    aes_lengths: tuple, AES 合法长度
    des_lengths: tuple, 3DES 合法长度
    alg_var: tk.StringVar 算法选择变量 (AES/3DES)，可选
    fixed_alg: str 固定算法 ("AES"/"3DES")，可选 such as calculate KCV
    """

    def validate(*args):
        text = var.get()

        # 清理非法字符，只保留 0-9A-Fa-f
        cleaned = "".join(c for c in text if c in "0123456789abcdefABCDEF")
        if cleaned != text:
            var.set(cleaned)

        length = len(cleaned)
        length_label.config(text=f"{length} chars")

        # 选择算法来源
        if alg_var is not None:
            alg = alg_var.get()
        elif fixed_alg is not None:
            alg = fixed_alg
        else:
            raise ValueError("必须提供 alg_var 或 fixed_alg 之一")

        # 根据算法选择合法长度
        if alg == "AES":
            valid_lengths = aes_lengths
        else:
            valid_lengths = des_lengths

        if length in valid_lengths:
            length_label.config(fg="green")
        else:
            length_label.config(fg="red")

    return validate



class RedirectText(object):
    """把 print() 重定向到 Text 控件"""
    def __init__(self, text_widget):
        self.output = text_widget

    def write(self, string):
        self.output.insert(tk.END, string)
        self.output.see(tk.END)  # 自动滚动到底部

    def flush(self):
        pass


class ToolApp(tk.Tk):
    VERSION = "v1.3"  # 版本号

    def __init__(self):
        super().__init__()
        self.title("Key Tool")
        self.geometry("900x600")
        self.configure(bg=COLOR_BACKGROUND)

        # 左边导航栏（主色背景，白色文字）
        self.nav_frame = tk.Frame(self, width=200, bg=COLOR_PRIMARY)
        self.nav_frame.pack(side="left", fill="y")

        # 内容区（白色背景）
        self.content_frame = tk.Frame(self, bg=COLOR_BACKGROUND)
        self.content_frame.pack(side="right", expand=True, fill="both")

        # 导航按钮（青绿色高亮）
        self.nav_buttons = {
            "Home": self.show_home,
            "Simulated LKI": self.show_simhsm,
            "Key Operation": self.show_genkey,
        }

        for i, (name, cmd) in enumerate(self.nav_buttons.items()):
            btn = tk.Button(
                self.nav_frame,
                text=name,
                command=cmd,
                font=("Arial", 12, "bold"),  # 字体加粗
                activebackground=COLOR_SECONDARY,
                activeforeground=COLOR_TEXT_PRIMARY,
                anchor="center",  # 水平居中
                relief="flat"
            )
            btn.pack(fill="x", padx=5, pady=5)

        # 固定版本号在导航栏底部居中（灰色文字）
        version_label = tk.Label(self.nav_frame, text=self.VERSION, bg=COLOR_PRIMARY, fg=COLOR_TEXT_SECONDARY)
        version_label.pack(side="bottom", pady=10)

        # 初始化显示 Home 页面
        self.show_home()

    def clear_content(self):
        # 如果有定时器就取消
        if hasattr(self, "update_time_id"):
            self.after_cancel(self.update_time_id)
            del self.update_time_id

        sys.stdout = sys.__stdout__  # 恢复系统默认 stdout

        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def show_home(self):
        self.clear_content()

        # 当前时间标签
        self.time_label = tk.Label(
            self.content_frame,
            text="",
            font=("Arial", 20, "bold"),
            bg=COLOR_BACKGROUND,
            fg=COLOR_PRIMARY
        )
        self.time_label.pack(expand=True)  # 居中显示

        # 显示 Powered by
        footer = tk.Label(
            self.content_frame,
            text="Powered by AlphaZ",
            font=("Arial", 10, "italic"),
            bg=COLOR_BACKGROUND,
            fg=COLOR_TEXT_SECONDARY
        )
        footer.pack(side="bottom", pady=10)

        # 启动定时器更新。 方案1，更干净，页面切换时就停止定时器，不会一直占用资源。方案2 虽然简单，但update_time会一直运行，没必要。
        # self.update_time()
        self.update_time_id = self.after(1000, self.update_time)

    def update_time(self):
        if hasattr(self, "time_label") and self.time_label.winfo_exists():
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.config(text=f"📅 {current_time}")
            # 每 1 秒刷新一次
            # self.after(1000, self.update_time)
            self.update_time_id = self.after(1000, self.update_time)

    # simulated_hsm_butt in navigation column
    def show_simhsm(self):
        self.clear_content()

        tk.Label(self.content_frame, text="Simulated HSM", font=("Arial", 16), bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).pack(pady=10)

        # -------------------------
        # 父容器
        # Serial Port & Baud Rate parallel
        # -------------------------
        serial_baud_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        serial_baud_frame.pack(fill="x", padx=10, pady=5)

        # 刷新串口函数
        def refresh_ports():
            ports = SimulatedHSM.simhsm.serial_utils.get_available_ports()
            if not ports:
                ports = ["No Ports Found"]
            self.port_combo['values'] = ports
            self.port_combo.current(0)

        # Flash Port 按钮
        flash_btn = tk.Button(
            serial_baud_frame,
            text="Flash Port",
            command=refresh_ports,  # 点按钮时刷新串口
            font=("Arial", 12, "bold"),
            bg=COLOR_SECONDARY,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_TEXT_PRIMARY
        )
        flash_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # # 动态获取串口列表
        # available_ports = SimulatedHSM.simhsm.serial_utils.get_available_ports()
        # if not available_ports:
        #     available_ports = ["No Ports Found"]  # 没找到串口的 fallback

        # serial port
        tk.Label(serial_baud_frame, text="Serial Port:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=1, padx=5, pady=5, sticky="we")
        self.port_combo = ttk.Combobox(serial_baud_frame, state="readonly")
        # if available_ports:
        #     self.port_combo.current(0)  # 默认选择第一个可用串口
        # self.port_combo.grid(row=0, column=1, padx=5, pady=5, sticky="we") # "we" 表示水平拉伸

        refresh_ports()  # 初始化时刷新一次
        self.port_combo.grid(row=0, column=2, padx=5, pady=5, sticky="we")

        # 波特率选择
        baud_options = [
            1200, 1800, 2400, 4800, 9600, 14400, 19200, 38400, 57600,
            115200, 230400, 460800, 614400, 921600, 1228800, 2457600, 3000000, 6000000
        ]

        # Baud Rate
        tk.Label(serial_baud_frame, text="Baud Rate:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.baud_combo = ttk.Combobox(serial_baud_frame, values=baud_options, state="readonly", width=8)
        self.baud_combo.set("115200") # 直接设置默认值为 115200
        self.baud_combo.grid(row=0, column=4, padx=5, pady=5, sticky="w") # 不拉伸

        # 调整列权重，让 Combobox 自适应拉伸
        serial_baud_frame.columnconfigure(2, weight=2)
        serial_baud_frame.columnconfigure(4, weight=0)

        # -------------------------
        # 父容器
        # key Type, Key Index, and KSN
        # -------------------------
        key_index_inject_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        key_index_inject_frame.pack(fill="x", padx=10, pady=5)

        # Algorithm Type
        tk.Label(key_index_inject_frame, text="Algorithm Type:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5, pady=5, sticky="we")
        self.alg_var = tk.StringVar()
        self.alg_combo = ttk.Combobox(
            key_index_inject_frame,
            textvariable=self.alg_var,
            values=["AES", "3DES"],
            state="readonly",
            width = 6,
        )
        self.alg_combo.set("3DES")  # 默认值
        self.alg_combo.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # Key Index
        tk.Label(key_index_inject_frame, text="Key Index:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        # Key Index 输入框，允许手动输入，限制为数字，最多2位
        self.index_var = tk.StringVar()
        self.index_entry = ttk.Combobox(
            key_index_inject_frame,
            textvariable=self.index_var,
            state="readonly",
            width=1,
        )
        self.index_entry['state'] = "readonly"
        self.index_entry.grid(row=0, column=3, padx=5, pady=5, sticky="we")

        # Key KSN
        tk.Label(key_index_inject_frame, text="KSN:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=4, padx=5, pady=5,sticky="w")
        # KSN Data 输入框 (只允许10/12字符)
        self.ksn_data_var = tk.StringVar()
        self.ksn_data_entry = tk.Entry(
            key_index_inject_frame,
            textvariable=self.ksn_data_var,
            bg="white",
            fg="black"
        )
        self.ksn_data_entry.grid(row=0, column=5, padx=5, pady=5, sticky="we")

        # 在输入框后显示当前长度
        self.ksn_length_label = tk.Label(
            key_index_inject_frame,
            text="0 chars",
            bg=COLOR_BACKGROUND,
            fg="red"
        )
        self.ksn_length_label.grid(row=0, column=6, padx=5, pady=5, sticky="w")
        ksn_validator = make_validator(
            self.ksn_data_var,
            self.ksn_length_label,
            aes_lengths=(24,),
            des_lengths=(20,),
            alg_var=self.alg_var,
        )
        self.ksn_data_var.trace_add("write", ksn_validator)

        # 列权重，让输入框水平拉伸
        key_index_inject_frame.columnconfigure(1, weight=1)
        key_index_inject_frame.columnconfigure(3, weight=1)
        key_index_inject_frame.columnconfigure(5, weight=1)


        # -------------------------
        # 父容器
        # Key Data, and Key Injection Button
        key_data_inject_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        key_data_inject_frame.pack(fill="x", padx=10, pady=5)

        # Key Information (16, 24, 32)
        tk.Label(key_data_inject_frame, text="Key Data:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        # Key Data 输入框 (只允许32/48/64字符)
        self.key_data_var = tk.StringVar()
        self.key_data_entry = tk.Entry(
            key_data_inject_frame,
            textvariable=self.key_data_var,
            bg="white",
            fg="black"
        )
        self.key_data_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # 在输入框后显示当前长度
        self.key_length_label = tk.Label(
            key_data_inject_frame,
            text="0 chars",
            bg=COLOR_BACKGROUND,
            fg="red"
        )
        self.key_length_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        key_validator = make_validator(
            self.key_data_var,
            self.key_length_label,
            aes_lengths=(32, 48, 64,),
            des_lengths=(32, 48,),
            alg_var=self.alg_var,
        )
        self.key_data_var.trace_add("write", key_validator)

        # Key Injection 按钮
        key_injection_btn = tk.Button(
            key_data_inject_frame,
            text="Key Injection",
            command=self.do_key_injection,
            font=("Arial", 12, "bold"),
            bg=COLOR_SECONDARY,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_TEXT_PRIMARY
        )
        key_injection_btn.grid(row=0, column=3, padx=10, pady=5)

        # 列权重，让输入框水平拉伸
        key_data_inject_frame.columnconfigure(1, weight=1)


        # 根据算法更新 Key Index 的可选值
        def update_key_index(event=None):
            alg = self.alg_var.get()
            if alg == "AES":
                # AES 可选值
                self.index_entry['values'] = [f"{i:02d}" for i in range(10, 20)] + [f"{i:04d}" for i in range(2100, 2200)]
            else:  # 3DES
                self.index_entry['values'] = [f"{i:02d}" for i in range(0, 10)] + [f"{i:04d}" for i in range(1100, 1200)]
            # 默认选第一个
            self.index_entry.set(self.index_entry['values'][0])

        # 绑定算法选择事件
        self.alg_combo.bind("<<ComboboxSelected>>", update_key_index)

        # 初始化 Key Index
        update_key_index()

        # -------------------------
        # 日志输出窗口
        # -------------------------
        log_label = tk.Label(self.content_frame, text="Log Output:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY)
        log_label.pack(anchor="w", padx=10, pady=(20, 0))

        self.log_text = tk.Text(self.content_frame, height=15, bg=COLOR_PRIMARY, fg=COLOR_TEXT_PRIMARY)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        # 绑定 print 输出到 log_text
        sys.stdout = RedirectText(self.log_text)
        print("✅ Simulated HSM initialized.")



    # Simulated HSM 功能函数
    def do_key_injection(self):
        serial_port = self.port_combo.get()
        baud_rate = int(self.baud_combo.get())
        key_alg = self.alg_combo.get()
        key_index = str(self.index_entry.get())
        key_data = str(self.key_data_var.get())
        ksn = str(self.ksn_data_var.get())
        print(f"👉 Sending Key Injection command to {self.port_combo.get()} @ {self.baud_combo.get()} baud", flush=True)

        # ============================
        # 校验 KSN 长度
        # ============================
        if key_alg == "AES":
            valid_ksn_lengths = (24,)
            valid_key_lengths = (32, 48, 64)
        else:  # 3DES
            valid_ksn_lengths = (20,)
            valid_key_lengths = (32, 48)

        if len(ksn) not in valid_ksn_lengths:
            messagebox.showerror("Invalid KSN", f"❌ The input KSN length is {len(ksn)}, but it must be {valid_ksn_lengths} characters.")
            print(f"❌ The input KSN length is {len(ksn)}, but it must be {valid_ksn_lengths} characters.")
            return

        if len(key_data) not in valid_key_lengths:
            messagebox.showerror("Invalid Key Data", f"❌ The input Key Data length is {len(key_data)}, but it must be {valid_key_lengths} characters.")
            print(f"❌ The input Key Data length is {len(key_data)}, but it must be {valid_key_lengths} characters.")
            return

        def worker():
            hsm_main.run_key_injection(serial_port, baud_rate, key_alg, key_index, key_data, ksn)

        threading.Thread(target=worker, daemon=True).start()


    # gen_key_button in the navigation column
    def show_genkey(self):
        self.clear_content()
        tk.Label(self.content_frame, text="Key Operation", font=("Arial", 16), bg=COLOR_BACKGROUND,
                 fg=COLOR_PRIMARY).pack(pady=10)

        # 选择组件数量 (下拉框)
        selection_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        selection_frame.pack(pady=5)

        tk.Label(selection_frame, text="Components:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).pack(side="left")

        self.comp_var = tk.StringVar(value="2")
        comp_combo = ttk.Combobox(
            selection_frame,
            textvariable=self.comp_var,
            values=["2", "3"],
            width=5,
            state="readonly"
        )
        comp_combo.pack(side="left", padx=5)

        # 绑定下拉框选择事件 → 自动刷新 component 输入框
        comp_combo.bind("<<ComboboxSelected>>", self.update_components)

        # Combine Keys 按钮（只做业务逻辑，不刷新输入框）
        tk.Button(
            selection_frame,
            text="Combine",
            command=self.do_combine_keys  # 你自己的逻辑
        ).pack(side="left", padx=10)

        # 放置 component 输入框的容器
        self.components_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        self.components_frame.pack(pady=10, fill="x")

        # 默认显示 2 个输入框
        self.update_components()

        # -------------------------
        # 父容器
        # Key Operation Button such as Encryption Button, Calculate KCV Button
        key_operation_button_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        key_operation_button_frame.pack(fill="x", padx=10, pady=(16,5))

        # Algorithm Type
        tk.Label(key_operation_button_frame, text="Algorithm Type:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.kcv_alg_var = tk.StringVar()
        self.kcv_alg_combo = ttk.Combobox(
            key_operation_button_frame,
            textvariable=self.kcv_alg_var,
            values=["AES", "3DES"],
            state="readonly",
            width=6,
        )
        self.kcv_alg_combo.set("3DES")  # 默认值
        self.kcv_alg_combo.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # Calculate KCV Button
        calculate_kcv_btn = tk.Button(
            key_operation_button_frame,
            text="Calculate KCV",
            command=self.do_calculate_kcv,
            font=("Arial", 12, "bold"),
            bg=COLOR_SECONDARY,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_TEXT_PRIMARY,
            width=10,
        )
        calculate_kcv_btn.grid(row=0, column=2, padx=10, pady=5, sticky="we")

        # Data Encryption Button
        encryption_btn = tk.Button(
            key_operation_button_frame,
            text="Encrypt Data",
            command=self.do_encryption,
            font=("Arial", 12, "bold"),
            bg=COLOR_SECONDARY,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_TEXT_PRIMARY,
            width=10,
        )
        encryption_btn.grid(row=0, column=3, padx=10, pady=5, sticky="we")

        # Data Decryption Button
        decryption_btn = tk.Button(
            key_operation_button_frame,
            text="Decrypt Data",
            command=self.do_decryption,
            font=("Arial", 12, "bold"),
            bg=COLOR_SECONDARY,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_TEXT_PRIMARY,
            width=10,
        )
        decryption_btn.grid(row=0, column=4, padx=10, pady=5, sticky="we")

        key_operation_button_frame.columnconfigure(1, weight=1)
        key_operation_button_frame.columnconfigure(2, weight=1)
        key_operation_button_frame.columnconfigure(3, weight=1)
        key_operation_button_frame.columnconfigure(4, weight=1)

        # -------------------------
        # 父容器
        # Key Information
        key_information_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        key_information_frame.pack(fill="x", padx=10, pady=5)

        # Key Information (16, 24)
        tk.Label(key_information_frame, text="Key:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        # Key 输入框 (只允许32/48/64字符)
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(
            key_information_frame,
            textvariable=self.key_var,
            bg="white",
            fg="black"
        )
        self.key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # 在输入框后显示当前长度
        self.key_length_label = tk.Label(
            key_information_frame,
            text="0 chars",
            bg=COLOR_BACKGROUND,
            fg="red"
        )
        self.key_length_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        key_validator = make_validator(
            self.key_var,
            self.key_length_label,
            aes_lengths=(32, 48, 64,),
            des_lengths=(32, 48,),
            alg_var=self.kcv_alg_var,
        )
        self.key_var.trace_add("write", key_validator)

        key_information_frame.columnconfigure(1, weight=1)

        # -------------------------
        # 父容器
        # Data Information
        data_information_frame = tk.Frame(self.content_frame, bg=COLOR_BACKGROUND)
        data_information_frame.pack(fill="x", padx=10, pady=5)

        # Key Information (16, 24)
        tk.Label(data_information_frame, text="Data:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        # Key Data 输入框 (只允许32/48/64字符)
        self.data_var = tk.StringVar()
        self.data_entry = tk.Entry(
            data_information_frame,
            textvariable=self.data_var,
            bg="white",
            fg="black"
        )
        self.data_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # 在输入框后显示当前长度
        self.data_length_label = tk.Label(
            data_information_frame,
            text="0 chars",
            bg=COLOR_BACKGROUND,
            fg="red"
        )
        self.data_length_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        key_validator = make_validator(
            self.data_var,
            self.data_length_label,
            aes_lengths=(32, 48, 64,),
            des_lengths=(32, 48,),
            alg_var=self.kcv_alg_var,
        )
        self.data_var.trace_add("write", key_validator)

        data_information_frame.columnconfigure(1, weight=1)


        self.log_text = tk.Text(self.content_frame, height=15, bg=COLOR_PRIMARY, fg=COLOR_TEXT_PRIMARY)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        sys.stdout = RedirectText(self.log_text)
        print("🔑 Ready to do key operation.")

    def update_components(self, event=None):
        """根据下拉框选择自动刷新 Component 输入框，并显示长度"""
        for widget in self.components_frame.winfo_children():
            widget.destroy()

        num = int(self.comp_var.get())
        self.key_entries = []
        self.length_labels = []

        # 定义十六进制校验函数
        def validate_hex_input(char):
            return char == "" or all(c in "/0123456789abcdefABCDEF" for c in char)

        vcmd = (self.content_frame.register(validate_hex_input), "%P")

        for i in range(num):
            frame = tk.Frame(self.components_frame, bg=COLOR_BACKGROUND)
            frame.pack(fill="x", pady=3)

            tk.Label(frame, text=f"Component {i+1} Key Data:", bg=COLOR_BACKGROUND, fg=COLOR_PRIMARY).grid(row=0, column=0, padx=5)

            component_var = tk.StringVar()
            entry = tk.Entry(
                frame, width=48,
                textvariable=component_var,
                validate="key",  # 开启实时校验
                validatecommand=vcmd
            )
            entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")

            # 显示长度
            len_label = tk.Label(frame, text="0 chars", bg=COLOR_BACKGROUND, fg="red", width=6)
            len_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")

            # 保存 Entry 和 StringVar 的引用
            self.key_entries.append(entry)

            key_validator = make_validator(
                component_var,
                len_label,
                aes_lengths=(32, 48, 64,),
                des_lengths=(32, 48,),
                fixed_alg="AES",
            )
            component_var.trace_add("write", key_validator)

            # 列权重，让输入框水平拉伸
            frame.columnconfigure(1, weight=1)


    def do_combine_keys(self):
        """点击 Combine Keys 时执行的业务逻辑"""
        print("🔗 Combine Keys button clicked.")
        keys = [e.get().strip() for e in getattr(self, "key_entries", [])]

        # 校验是否为空
        for i, k in enumerate(keys, start=1):
            if not k:
                messagebox.showerror("输入错误", f"Component {i} 为空，请输入 Key Data")
                print(f"❌ Component {i} 为空，请输入 Key Data")
                return
            if len(k) not in (32, 48, 64):
                messagebox.showerror("输入错误", f"Component {i} 长度非法 ({len(k)}), 必须是 32/48/64 个字符")
                print(f"❌ Component {i} 长度非法 ({len(k)})，必须是 32/48/64 个字符")
                return
            # 可选：校验是否为十六进制
            try:
                int(k, 16)
            except ValueError:
                messagebox.showerror("输入错误", f"Component {i} 不是有效的十六进制")
                return

        # 校验长度是否一致
        lengths = [len(k) for k in keys]
        if len(set(lengths)) != 1:
            messagebox.showerror("输入错误", "所有 Component 的长度必须一致")
            print(f"❌ Component {i} 长度非法 ({len(k)})，必须是 32/48/64 个字符")
            return

        # 校验通过，执行真正的 Combine Keys 逻辑
        print(f"🔗 Combining {len(keys)} components...")
        for i, k in enumerate(keys, start=1):
            print(f"Component {i}: {k}")

        def worker():
            genkey_main.run_combine_key(keys)

        threading.Thread(target=worker, daemon=True).start()

    def do_calculate_kcv(self):
        """"点击 Calculate KCV Button 时执行的业务逻辑"""
        print("🔗 Calculate KCV button clicked.")

        key_hex = self.key_var.get()
        algo_type = self.kcv_alg_var.get()

        def worker():
            genkey_main.run_calculate_kcv(key_hex, algo_type)

        threading.Thread(target=worker, daemon=True).start()

    def do_encryption(self):
        """点击 Encryption Button 时执行的业务逻辑"""
        print("🔗 Encrypt the data with the key.")

        algo_type = self.kcv_alg_var.get()
        key_hex = self.key_var.get()
        data_hex = self.data_var.get()

        def worker():
            genkey_main.run_encryption(data_hex, key_hex, algo_type)

        threading.Thread(target=worker, daemon=True).start()

    def do_decryption(self):
        """点击 Decryption Button 时执行的业务逻辑"""
        print("🔗 Decrypt the data with the key.")

        algo_type = self.kcv_alg_var.get()
        key_hex = self.key_var.get()
        data_hex = self.data_var.get()

        def worker():
            genkey_main.run_decryption(data_hex, key_hex, algo_type)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = ToolApp()
    app.mainloop()