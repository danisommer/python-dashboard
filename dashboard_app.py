import re
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from system_info import SystemInfo
import queue
import threading

cycle_time = 1000  # milissegundos
cycle_time_graphs = 500  # milissegundos
cycle_time_processes = 2000  # milissegundos
last_selected_process = None
processes_thread = 5
last_thread_num = 0

class DashboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System Dashboard")
        self.root.geometry("1200x590")
        self.root.resizable(True, True)
        self.root.minsize(800, 590)

        self.cpu_usage_history = []
        self.mem_usage_history = []
        self.swap_usage_history = []
        self.disk_usage_history = []
        self.network_receive_history = []
        self.network_transmit_history = []
        self.cpu_core_lines = []
        self.max_history_length = 50

        self.sys_info = SystemInfo()
        self.num_cores = len(self.sys_info.get_cpu_usage_per_core())
        self.cpu_core_usage_histories = [[] for _ in range(self.num_cores)]

        self.label_vars = {}
        self.labels = {}
        self.executor = ThreadPoolExecutor(max_workers=len(self.sys_info.fields) + processes_thread)

        self.result_queue = queue.Queue()

        self.setup_widgets()

        self.process_window = None

        self.initialize_cpu_core_histories()
        self.initialize_memory_histories()
        self.initialize_network_histories()
        self.initialize_disk_histories()
        self.root.after(100, self.process_queue)
        
    #funcoes de inicializacao de historicos dos graficos
    def initialize_cpu_core_histories(self):
        core_usages = self.sys_info.get_cpu_usage_per_core()
        for core_index, usage in enumerate(core_usages):
            # inicializa o historico de uso de cada nucleo com zeros
            self.cpu_core_usage_histories[core_index] = [0] * self.max_history_length
    def initialize_memory_histories(self):
        mem_usage = self.sys_info.get_memory_usage()
        swap_usage = self.sys_info.get_swap_usage()
        self.mem_usage_history = [mem_usage] * self.max_history_length
        self.swap_usage_history = [swap_usage] * self.max_history_length
    def initialize_network_histories(self):
        receive_rate = self.sys_info.get_network_receive_rate()
        transmit_rate = self.sys_info.get_network_transmit_rate()
        self.network_receive_history = [receive_rate] * self.max_history_length
        self.network_transmit_history = [transmit_rate] * self.max_history_length
    def initialize_disk_histories(self):
        disk_usage = self.sys_info.get_used_disk()
        self.disk_usage_history = [disk_usage] * self.max_history_length

    def setup_widgets(self): 
        # configuracao principal da grade
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        # quadro para conteudo
        info_frame = tk.Frame(self.root, bg="lightgray")
        info_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        info_frame.grid_rowconfigure(0, weight=1)
        info_frame.grid_columnconfigure(0, weight=1)

        # rotulos para informacoes do sistema
        for i, field in enumerate(self.sys_info.fields.keys()):
            frame = tk.Frame(info_frame, bg="white", padx=10, pady=5)
            frame.grid(row=i, column=0, sticky="ew", pady=3)
            frame.grid_columnconfigure(0, weight=1)
            self.label_vars[field] = tk.StringVar()
            label = tk.Label(frame, textvariable=self.label_vars[field], font=("Arial", 12), anchor="center", bg="white")
            label.pack(fill="x", padx=5)
            self.labels[field] = label
            # agendar atualizacoes
            self.update_field(field)

        # botao para mostrar processos
        self.process_button = tk.Button(self.root, text="Show Processes", command=self.show_processes)
        self.process_button.grid(row=1, column=0, pady=10, padx=10, sticky="ew")

        # graficos de cpu e memoria
        self.cpu_memory_frame = tk.Frame(self.root)
        self.cpu_memory_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=10, pady=10)
        self.cpu_memory_frame.grid_rowconfigure(0, weight=1)
        self.cpu_memory_frame.grid_columnconfigure(0, weight=1)

        self.setup_graphs()

    def setup_graphs(self):
        # criar figura para graficos
        self.fig, ((self.cpu_ax, self.mem_ax), (self.net_ax, self.disk_ax)) = plt.subplots(2, 2, figsize=(12, 8))
        self.fig.tight_layout(pad=2.0)

        # canvas para exibir graficos
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.cpu_memory_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # inicializar objetos de linha
        self.mem_line, = self.mem_ax.plot([], [], color="salmon", label="Memory Usage")
        self.swap_line, = self.mem_ax.plot([], [], color="blue", label="Swap Usage")
        self.net_receive_line, = self.net_ax.plot([], [], color="lightgreen", label="Download")
        self.net_transmit_line, = self.net_ax.plot([], [], color="orange", label="Upload")
        self.disk_line, = self.disk_ax.plot([], [], color="purple", label="Disk Usage")

        self.cpu_ax.set_ylim(0, 100)
        self.cpu_ax.set_title("CPU Usage (MHz)")
        self.cpu_ax.set_xticks([])

        self.mem_ax.set_ylim(0, 100)
        self.mem_ax.set_title("Memory and Swap Usage (%)")
        self.mem_ax.set_xticks([])
        self.mem_ax.legend()

        self.net_ax.set_title("Network Usage (KB/s)")
        self.net_ax.set_xticks([])
        self.net_ax.legend()

        self.disk_ax.set_title("Disk Usage (%)")
        self.disk_ax.set_ylim(0, 100)
        self.disk_ax.set_xticks([])
        self.disk_ax.legend()

        for core in range(self.num_cores):
            line, = self.cpu_ax.plot([], [], label=f"Core {core + 1}")
            self.cpu_core_lines.append(line)

        self.cpu_ax.legend()

        # agendar atualizacoes dos graficos
        self.root.after(cycle_time, self.update_cpu_graph)
        self.root.after(cycle_time, self.update_memory_graph)
        self.root.after(cycle_time, self.update_network_graph)
        self.root.after(cycle_time, self.update_disk_graph)
        
    def update_field(self, field):
        # computacao pesada em uma thread separada
        def worker():
            value = self.sys_info.get_info(field)
            self.result_queue.put(('field', field, value))
        threading.Thread(target=worker).start()
        self.root.after(cycle_time, self.update_field, field)

    def process_queue(self):
        while not self.result_queue.empty():
            item = self.result_queue.get()
            if item[0] == 'field':
                field, value = item[1], item[2]
                self.label_vars[field].set(f"{field}:\n{value}")
            elif item[0] == 'cpu':
                core_usages = item[1]
                for core_index, usage in enumerate(core_usages):
                    self.cpu_core_usage_histories[core_index].append(usage)
                    if len(self.cpu_core_usage_histories[core_index]) > self.max_history_length:
                        self.cpu_core_usage_histories[core_index].pop(0)
                self.refresh_cpu_graph()
            elif item[0] == 'memory':
                mem_usage, swap_usage = item[1], item[2]
                self.mem_usage_history.append(mem_usage)
                self.swap_usage_history.append(swap_usage)
                if len(self.mem_usage_history) > self.max_history_length:
                    self.mem_usage_history.pop(0)
                if len(self.swap_usage_history) > self.max_history_length:
                    self.swap_usage_history.pop(0)
                self.refresh_memory_graph()
            elif item[0] == 'network':
                receive_rate, transmit_rate = item[1], item[2]
                self.network_receive_history.append(receive_rate)
                self.network_transmit_history.append(transmit_rate)
                if len(self.network_receive_history) > self.max_history_length:
                    self.network_receive_history.pop(0)
                if len(self.network_transmit_history) > self.max_history_length:
                    self.network_transmit_history.pop(0)
                self.refresh_network_graph()
            elif item[0] == 'disk':
                disk_usage = item[1]
                if not hasattr(self, 'disk_usage_history'):
                    self.disk_usage_history = []
                self.disk_usage_history.append(disk_usage)
                self.disk_usage_history = self.disk_usage_history[-self.max_history_length:]
                self.refresh_disk_graph()
            elif item[0] == 'processes_update':
                        processes = item[1]
                        self.refresh_process_list(processes)
        self.root.after(100, self.process_queue)

    # funcoes de atualizacao e refresh do grafico de cpu
    def update_cpu_graph(self):
        def worker():
            core_usages = self.sys_info.get_cpu_usage_per_core()
            self.result_queue.put(('cpu', core_usages))
        threading.Thread(target=worker).start()
        self.root.after(cycle_time_graphs, self.update_cpu_graph)
    def refresh_cpu_graph(self):
        xdata = range(len(self.cpu_core_usage_histories[0]))
        for core_index, line in enumerate(self.cpu_core_lines):
            ydata = self.cpu_core_usage_histories[core_index]
            # calcular a media usando os ultimos 10 valores
            avg_ydata = [sum(ydata[max(0, i - 9):i + 1]) / min(10, i + 1) for i in range(len(ydata))]            
            line.set_data(xdata[-len(avg_ydata):], avg_ydata)
        self.cpu_ax.set_xlim(0, self.max_history_length)
        self.cpu_ax.set_ylim(0, max(max(core_data) for core_data in self.cpu_core_usage_histories) * 1.1)
        self.canvas.draw_idle()

    # funcoes de atualizacao e refresh dos graficos de memoria
    def update_memory_graph(self):
        # computacao pesada em uma thread separada
        def worker():
            mem_usage = self.sys_info.get_memory_usage()
            swap_usage = self.sys_info.get_swap_usage()
            self.result_queue.put(('memory', mem_usage, swap_usage))
        threading.Thread(target=worker).start()
        self.root.after(cycle_time_graphs, self.update_memory_graph)
    def refresh_memory_graph(self):
        xdata = range(len(self.mem_usage_history))
        self.mem_line.set_data(xdata, self.mem_usage_history)
        self.swap_line.set_data(xdata, self.swap_usage_history)
        self.mem_ax.set_xlim(0, self.max_history_length)
        self.canvas.draw_idle()

    # funcoes de atualizacao e refresh dos graficos de rede
    def update_network_graph(self):
        # computacao pesada em uma thread separada
        def worker():
            receive_rate = self.sys_info.get_network_receive_rate()
            transmit_rate = self.sys_info.get_network_transmit_rate()
            self.result_queue.put(('network', receive_rate, transmit_rate))
        threading.Thread(target=worker).start()
        self.root.after(cycle_time_graphs, self.update_network_graph)
    def refresh_network_graph(self):
        xdata = range(len(self.network_receive_history))
        self.net_receive_line.set_data(xdata, self.network_receive_history)
        self.net_transmit_line.set_data(xdata, self.network_transmit_history)
        self.net_ax.set_xlim(0, self.max_history_length)
        max_rate = max(max(self.network_receive_history), max(self.network_transmit_history)) * 1.1
        if max_rate == 0:
            max_rate = 1  # definir um limite minimo para y
        self.net_ax.set_ylim(0, max_rate)
        self.canvas.draw_idle()

    # funcoes de atualizacao e refresh do grafico de disco
    def update_disk_graph(self):
        # computacao pesada em uma thread separada
        def worker():
            used_disk = self.sys_info.get_used_disk()
            free_disk = self.sys_info.get_free_disk()
            total_disk = used_disk + free_disk
            disk_usage = (used_disk / total_disk) * 100 if total_disk > 0 else 0
            self.result_queue.put(('disk', disk_usage))
        threading.Thread(target=worker).start()
        self.root.after(cycle_time_graphs, self.update_disk_graph)
    def refresh_disk_graph(self):
        xdata = range(len(self.disk_usage_history))
        self.disk_line.set_data(xdata, self.disk_usage_history)
        self.disk_ax.set_xlim(0, self.max_history_length)
        self.canvas.draw_idle()

    def show_processes(self):
        if self.process_window is not None and tk.Toplevel.winfo_exists(self.process_window):
            self.process_window.deiconify()
            return

        self.process_window = tk.Toplevel(self.root)
        self.process_window.title("Process List")
        self.process_window.geometry("800x400")
        self.process_window.resizable(True, True)

        self.process_window.grid_rowconfigure(0, weight=1)
        self.process_window.grid_columnconfigure(0, weight=1)
        
        columns = ("PID", "Name", "State", "Threads", "Virtual Memory", "Physical Memory") 
        self.process_tree = ttk.Treeview(self.process_window, columns=columns, show="headings")
        
        column_widths = {"PID": 60, "Name": 200, "State": 80, "Threads": 60, "Virtual Memory": 100, "Physical Memory": 100}
        for col in columns:
            self.process_tree.heading(col, text=col, command=lambda _col=col: self.sort_processes(_col))
            self.process_tree.column(col, anchor="center", minwidth=column_widths[col], width=column_widths[col], stretch=True)
        
        self.process_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self.process_window, orient="vertical", command=self.process_tree.yview)
        self.process_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.process_window.grid_rowconfigure(0, weight=1)
        self.process_window.grid_columnconfigure(0, weight=1)
        self.process_window.grid_columnconfigure(1, weight=0)

        self.process_window.protocol("WM_DELETE_WINDOW", self.close_process_window)

        self.process_window_running = True
        self.update_processes()  # comeca a atualizar a lista

        self.sort_column = None
        self.sort_reverse = False
            
    def sort_processes(self, col, invert_sort=True):
        if col != self.sort_column:  # se clicou em uma coluna diferente, ordena normalmente
            self.sort_reverse = False
            self.sort_column = col
        elif invert_sort:  # apenas inverte a ordem se clicou na mesma coluna
            self.sort_reverse = not self.sort_reverse

        # extrai os dados da coluna para ordenar
        data = []
        for child in self.process_tree.get_children(''):
            val = self.process_tree.set(child, col)
            
            #converte para o tipo correto para ordenacao
            if col in ["PID", "Threads"]:
                val = int(val)
            elif col in ["Virtual Memory", "Physical Memory"]:  
                try:
                    val = float(val.replace(" KB", ""))
                except ValueError:
                    val = 0
            
            data.append((val, child))
        
        # ordena os dados
        data.sort(key=lambda x: x[0], reverse=self.sort_reverse)
        
        # reorganiza as linhas na arvore
        for index, (val, child) in enumerate(data):
            self.process_tree.move(child, '', index)

    def close_process_window(self):
        self.process_window_running = False
        self.process_window.destroy()

    def update_processes(self):
        def worker():
            processes_info = self.sys_info.get_processes_info()
            self.result_queue.put(('processes_update', processes_info))
        threading.Thread(target=worker).start()
        if self.process_window_running:
            self.root.after(cycle_time_processes, self.update_processes)  

    def refresh_process_list(self, processes):
        global last_selected_process

        if not hasattr(self, 'process_tree') or not self.process_tree.winfo_exists():
            return

        # salve a posicao vertical do scrollbar
        treeview_yview = self.process_tree.yview()

        # salve o ultimo processo selecionado
        selected_item = self.process_tree.selection()
        if selected_item:
            last_selected_process = self.process_tree.item(selected_item[0], 'values')[0]

        # limpa a lista de processos
        for item in self.process_tree.get_children():
            self.process_tree.delete(item)

        #insere os novos processos
        lines = processes.strip().split('\n')
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 6:
                pid = parts[0]
                name = parts[1]
                state = parts[2]
                threads = parts[3]
                vsize = f"{parts[4]} KB" if parts[4] else "0 KB"
                rss = f"{parts[5]} KB" if parts[5] else "0 KB"
                self.process_tree.insert("", "end", values=(pid, name, state, threads, vsize, rss))

        # reseleciona o ultimo processo selecionado
        if last_selected_process:
            for item in self.process_tree.get_children():
                if self.process_tree.item(item, 'values')[0] == last_selected_process:
                    self.process_tree.selection_set(item)
                    self.process_tree.see(item)
                    break

        # reordena a lista de processos
        if self.sort_column:
            self.sort_processes(self.sort_column, invert_sort=False)

        # restaura a posicao vertical do scrollbar
        self.process_tree.yview_moveto(treeview_yview[0])

    def stop(self):
        self.executor.shutdown(wait=False)
        self.root.quit()