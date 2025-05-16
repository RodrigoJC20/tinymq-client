#!/usr/bin/env python3
"""
TinyMQ Client GUI

Interfaz gráfica simplificada y organizada para el cliente TinyMQ.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog  # Añadido simpledialog
import threading
import time
from datetime import datetime
import re

from tinymq import Client, DataAcquisitionService, Database

class TinyMQGUI:
    """Interfaz gráfica simplificada para el cliente TinyMQ."""

    def __init__(self, root):
        self.root = root
        self.root.title("TinyMQ Client")
        self.root.geometry("900x600")
        self.db = Database()
        self.das = None
        self.client = None
        self.running = True

        self.configure_style()
        self.create_widgets()
        self.start_das()

        self.update_thread = threading.Thread(target=self.update_data_loop, daemon=True)
        self.update_thread.start()

    def configure_style(self):
        style = ttk.Style()
        style.configure('TButton', font=('Helvetica', 10))
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('Header.TLabel', font=('Helvetica', 12, 'bold'))

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Binding para detectar cuando se cambia de pestaña
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.create_dashboard_tab()
        self.create_sensors_tab()
        self.create_topics_tab()
        self.create_subscriptions_tab()

        # Barra de estado
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = ttk.Label(self.status_bar, text="Listo", anchor="w")
        self.status_label.pack(side="left", padx=5)
        self.readings_label = ttk.Label(self.status_bar, text="Lecturas: 0", anchor="e")
        self.readings_label.pack(side="right", padx=10)

    def on_tab_changed(self, event):
        """Actualiza los datos de la pestaña seleccionada automáticamente."""
        tab_idx = self.notebook.index('current')
        
        # Actualizar según la pestaña activa (0=Dashboard, 1=Sensores, 2=Tópicos, 3=Suscripciones)
        if tab_idx == 0:  # Dashboard
            self.refresh_stats()
        elif tab_idx == 1:  # Sensores
            self.refresh_sensors()
        elif tab_idx == 2:  # Tópicos
            self.refresh_topics()
        elif tab_idx == 3:  # Suscripciones
            self.refresh_subscriptions()
            self.refresh_public_topics()
        
        self.status_label.config(text=f"Pestaña '{self.notebook.tab(tab_idx, 'text')}' actualizada")
        self.readings_label.pack(side="right", padx=10)

    def create_dashboard_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Inicio")

        frame = ttk.LabelFrame(tab, text="Estado de Conexión")
        frame.pack(fill="x", padx=10, pady=10)

        self.status_var = tk.StringVar(value="Desconectado")
        ttk.Label(frame, textvariable=self.status_var, style='Header.TLabel').pack(pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        self.connect_btn = ttk.Button(btn_frame, text="Conectar", command=self.connect_to_broker)
        self.connect_btn.pack(side="left", padx=5)
        self.disconnect_btn = ttk.Button(btn_frame, text="Desconectar", command=self.disconnect_from_broker, state="disabled")
        self.disconnect_btn.pack(side="left", padx=5)

        # Cliente
        client_frame = ttk.LabelFrame(tab, text="Identidad")
        client_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(client_frame, text="ID:").pack(side="left", padx=5)
        self.client_id_var = tk.StringVar()
        ttk.Entry(client_frame, textvariable=self.client_id_var, width=15).pack(side="left", padx=5)
        ttk.Button(client_frame, text="Cambiar ID", command=self.change_client_id).pack(side="left", padx=5)
        ttk.Label(client_frame, text="Nombre:").pack(side="left", padx=5)
        self.name_var = tk.StringVar()
        ttk.Entry(client_frame, textvariable=self.name_var, width=15).pack(side="left", padx=5)
        ttk.Label(client_frame, text="Email:").pack(side="left", padx=5)
        self.email_var = tk.StringVar()
        ttk.Entry(client_frame, textvariable=self.email_var, width=20).pack(side="left", padx=5)
        ttk.Button(client_frame, text="Actualizar", command=self.update_metadata).pack(side="left", padx=5)

        # Estadísticas
        stats_frame = ttk.LabelFrame(tab, text="Estadísticas")
        stats_frame.pack(fill="x", padx=10, pady=5)
        self.stats_text = tk.Text(stats_frame, height=12, wrap="word")
        self.stats_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.stats_text.config(state="disabled")
        ttk.Button(stats_frame, text="Refrescar", command=self.refresh_stats).pack(pady=5)


    def create_sensors_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Sensores")

        main_frame = ttk.Frame(tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Lista de sensores
        left = ttk.LabelFrame(main_frame, text="Sensores")
        left.pack(side="left", fill="y", padx=(0, 10))
        self.sensors_listbox = tk.Listbox(left, width=30)
        self.sensors_listbox.pack(fill="y", expand=True, padx=5, pady=5)
        self.sensors_listbox.bind('<<ListboxSelect>>', self.on_sensor_selected)
        ttk.Button(left, text="Refrescar", command=self.refresh_sensors).pack(fill="x", padx=5, pady=5)

        # Detalles
        right = ttk.LabelFrame(main_frame, text="Detalles")
        right.pack(side="left", fill="both", expand=True)
        
        # Información básica del sensor
        info = ttk.Frame(right)
        info.pack(fill="x", padx=10, pady=10)
        ttk.Label(info, text="ID:").grid(row=0, column=0, sticky="w")
        self.sensor_id_var = tk.StringVar()
        ttk.Label(info, textvariable=self.sensor_id_var).grid(row=0, column=1, sticky="w")
        ttk.Label(info, text="Nombre:").grid(row=1, column=0, sticky="w")
        self.sensor_name_var = tk.StringVar()
        ttk.Label(info, textvariable=self.sensor_name_var).grid(row=1, column=1, sticky="w")
        ttk.Label(info, text="Último valor:").grid(row=2, column=0, sticky="w")
        self.sensor_value_var = tk.StringVar()
        ttk.Label(info, textvariable=self.sensor_value_var).grid(row=2, column=1, sticky="w")
        ttk.Label(info, text="Última actualización:").grid(row=3, column=0, sticky="w")
        self.sensor_updated_var = tk.StringVar()
        ttk.Label(info, textvariable=self.sensor_updated_var).grid(row=3, column=1, sticky="w")

        # Pestañas para tiempo real e historial
        self.sensor_data_notebook = ttk.Notebook(right)
        self.sensor_data_notebook.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Pestaña de tiempo real
        realtime_frame = ttk.Frame(self.sensor_data_notebook)
        self.sensor_data_notebook.add(realtime_frame, text="Tiempo Real")
        
        # Opciones para tiempo real
        realtime_controls = ttk.Frame(realtime_frame)
        realtime_controls.pack(fill="x", pady=5)
        self.realtime_active_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(realtime_controls, text="Activar monitoreo", variable=self.realtime_active_var, 
                       command=self.toggle_realtime_monitoring).pack(side="left", padx=5)
        ttk.Button(realtime_controls, text="Limpiar", command=self.clear_realtime_data).pack(side="left", padx=5)
        
        # Vista de datos en tiempo real
        self.realtime_text = scrolledtext.ScrolledText(realtime_frame, height=8)
        self.realtime_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.realtime_text.config(state="disabled")
        
        # Pestaña de historial (existente)
        history_frame = ttk.Frame(self.sensor_data_notebook)
        self.sensor_data_notebook.add(history_frame, text="Historial")
        
        # Controles de historial
        controls = ttk.Frame(history_frame)
        controls.pack(fill="x", pady=5)
        ttk.Label(controls, text="Límite:").pack(side="left", padx=5)
        self.history_limit_var = tk.StringVar(value="20")
        ttk.Combobox(controls, textvariable=self.history_limit_var, values=["10", "20", "50", "100"], width=5, state="readonly").pack(side="left", padx=5)
        ttk.Button(controls, text="Cargar", command=self.load_sensor_history).pack(side="left", padx=5)
        
        # Vista de historial
        self.history_text = scrolledtext.ScrolledText(history_frame, height=8)
        self.history_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.history_text.config(state="disabled")

    # Métodos adicionales para el monitoreo en tiempo real
    def toggle_realtime_monitoring(self):
        """Activa o desactiva el monitoreo en tiempo real para el sensor seleccionado."""
        if self.realtime_active_var.get():
            sensor_id = self.sensor_id_var.get()
            if not sensor_id:
                messagebox.showinfo("Información", "Selecciona un sensor primero")
                self.realtime_active_var.set(False)
                return
            # Si activamos, limpiar la vista
            self.clear_realtime_data()
            self.realtime_text.config(state="normal")
            self.realtime_text.insert(tk.END, "Monitoreo en tiempo real activado. Esperando datos...\n\n")
            self.realtime_text.config(state="disabled")
        else:
            self.realtime_text.config(state="normal")
            self.realtime_text.insert(tk.END, "Monitoreo en tiempo real desactivado.\n")
            self.realtime_text.config(state="disabled")

    def clear_realtime_data(self):
        """Limpia los datos en tiempo real."""
        self.realtime_text.config(state="normal")
        self.realtime_text.delete("1.0", tk.END)
        self.realtime_text.config(state="disabled")
        
    def on_sensor_data(self, sensor_name, data):
        """Callback cuando se recibe un nuevo dato de sensor."""
        # Actualizar el monitoreo en tiempo real si está activo
        current_sensor_name = self.sensor_name_var.get()
        if self.realtime_active_var.get() and sensor_name == current_sensor_name:
            timestamp = datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            value_text = f"{data['value']} {data.get('units', '')}"
            
            # Actualizar la interfaz de usuario en el hilo principal
            self.root.after(0, lambda: self.update_realtime_display(timestamp, value_text))
        
        # También actualizar últimos valores si es el sensor actual
        if sensor_name == current_sensor_name:
            self.root.after(0, lambda: self.update_sensor_latest_value(data))
    
    def update_realtime_display(self, timestamp, value_text):
        """Actualiza la visualización en tiempo real (llamada desde el hilo principal)."""
        self.realtime_text.config(state="normal")
        
        # Mantener un máximo de líneas (por ejemplo, 100)
        lines = self.realtime_text.get("1.0", tk.END).splitlines()
        if len(lines) > 100:
            self.realtime_text.delete("1.0", f"{len(lines) - 100}.0")
        
        self.realtime_text.insert(tk.END, f"{timestamp}: {value_text}\n")
        self.realtime_text.see(tk.END)  # Desplazarse automáticamente al final
        self.realtime_text.config(state="disabled")
    
    def update_sensor_latest_value(self, data):
        """Actualiza los valores más recientes del sensor en la interfaz."""
        self.sensor_value_var.set(f"{data['value']} {data.get('units', '')}")
        timestamp = datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        self.sensor_updated_var.set(timestamp)
        
    def create_topics_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Tópicos")

        main_frame = ttk.Frame(tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Lista de tópicos
        left = ttk.LabelFrame(main_frame, text="Tópicos")
        left.pack(side="left", fill="y", padx=(0, 10))
        self.topics_listbox = tk.Listbox(left, width=30)
        self.topics_listbox.pack(fill="y", expand=True, padx=5, pady=5)
        self.topics_listbox.bind('<<ListboxSelect>>', self.on_topic_selected)
        ttk.Button(left, text="Refrescar", command=self.refresh_topics).pack(fill="x", padx=5, pady=5)
        # Botón para crear tópico
        ttk.Button(left, text="Crear Tópico", command=self.open_create_topic_dialog).pack(fill="x", padx=5, pady=5)

        # Detalles y acciones
        right = ttk.LabelFrame(main_frame, text="Detalles")
        right.pack(side="left", fill="both", expand=True)
        info = ttk.Frame(right)
        info.pack(fill="x", padx=10, pady=10)
        ttk.Label(info, text="ID:").grid(row=0, column=0, sticky="w")
        self.topic_id_var = tk.StringVar()
        ttk.Label(info, textvariable=self.topic_id_var).grid(row=0, column=1, sticky="w")
        ttk.Label(info, text="Nombre:").grid(row=1, column=0, sticky="w")
        self.topic_name_var = tk.StringVar()
        ttk.Label(info, textvariable=self.topic_name_var).grid(row=1, column=1, sticky="w")
        ttk.Label(info, text="Publicando:").grid(row=2, column=0, sticky="w")
        self.topic_publish_var = tk.StringVar()
        ttk.Label(info, textvariable=self.topic_publish_var).grid(row=2, column=1, sticky="w")

        pub_frame = ttk.Frame(right)
        pub_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(pub_frame, text="Activar Publicación", command=lambda: self.toggle_topic_publish(True)).pack(side="left", padx=5)
        ttk.Button(pub_frame, text="Desactivar Publicación", command=lambda: self.toggle_topic_publish(False)).pack(side="left", padx=5)

        # Sensores asociados
        sensors_frame = ttk.LabelFrame(right, text="Sensores en el Tópico")
        sensors_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.topic_sensors_text = scrolledtext.ScrolledText(sensors_frame, height=5)
        self.topic_sensors_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.topic_sensors_text.config(state="disabled")

        # Añadir sensor
        add_frame = ttk.Frame(sensors_frame)
        add_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(add_frame, text="Sensor:").pack(side="left", padx=5)
        self.sensor_to_add_var = tk.StringVar()
        self.sensor_combo = ttk.Combobox(add_frame, textvariable=self.sensor_to_add_var, state="readonly")
        self.sensor_combo.pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(add_frame, text="Agregar", command=self.add_sensor_to_topic).pack(side="left", padx=5)
        ttk.Button(add_frame, text="Eliminar", command=self.remove_sensor_from_topic).pack(side="left", padx=5)

    def open_create_topic_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Crear nuevo tópico")
        dialog.geometry("320x150")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Nombre del tópico:").pack(pady=(10, 2))
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=25)
        name_entry.pack(pady=2)
        name_entry.focus()

        publish_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Publicar al crear", variable=publish_var).pack(pady=2)

        def on_create():
            name = name_var.get().strip()
            publish = publish_var.get()
            if not name:
                messagebox.showinfo("Información", "Debes ingresar un nombre para el tópico", parent=dialog)
                return
            try:
                self.db.create_topic(name, publish)
                messagebox.showinfo("Éxito", f"Tópico '{name}' creado correctamente", parent=dialog)
                self.refresh_topics()
                self.refresh_public_topics()  # Añadir esta línea para actualizar tópicos públicos
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear el tópico: {str(e)}", parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="Crear", command=on_create).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side="left", padx=5)

    def create_subscriptions_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Suscripciones")

        main_frame = ttk.Frame(tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Lista de suscripciones
        left = ttk.LabelFrame(main_frame, text="Suscripciones Activas")
        left.pack(side="left", fill="y", padx=(0, 10))
        self.subscriptions_listbox = tk.Listbox(left, width=35)
        self.subscriptions_listbox.pack(fill="y", expand=True, padx=5, pady=5)
        self.subscriptions_listbox.bind('<<ListboxSelect>>', self.on_subscription_selected)
        
        # Botones para gestionar suscripciones
        buttons_frame = ttk.Frame(left)
        buttons_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(buttons_frame, text="Refrescar", command=self.refresh_subscriptions).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(buttons_frame, text="Desuscribirse", command=self.unsubscribe_from_topic).pack(side="left", expand=True, fill="x", padx=2)

        # NUEVO: Lista de tópicos públicos para suscribirse
        public_topics_frame = ttk.LabelFrame(left, text="Tópicos Públicos Disponibles")
        public_topics_frame.pack(fill="x", padx=5, pady=10)
        self.public_topics_combo = ttk.Combobox(public_topics_frame, state="readonly")
        self.public_topics_combo.pack(fill="x", padx=5, pady=5)
        # Vincular evento de clic para refrescar la lista de tópicos públicos
        self.public_topics_combo.bind("<ButtonPress-1>", lambda e: self.refresh_public_topics())
        ttk.Button(public_topics_frame, text="Suscribirse", command=self.subscribe_to_public_topic).pack(fill="x", padx=5, pady=5)


       # Detalles y acciones
        right = ttk.LabelFrame(main_frame, text="Detalles")
        right.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(right)
        controls.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(controls, text="Tópico:").pack(side="left", padx=5)
        # Crear StringVar para los campos
        self.sub_topic_var = tk.StringVar()
        self.sub_topic_entry = ttk.Entry(controls, state="readonly", textvariable=self.sub_topic_var)
        self.sub_topic_entry.pack(side="left", padx=5)
        
        ttk.Label(controls, text="Cliente Origen:").pack(side="left", padx=5)
        self.sub_client_var = tk.StringVar()
        self.sub_client_entry = ttk.Entry(controls, state="readonly", textvariable=self.sub_client_var)
        self.sub_client_entry.pack(side="left", padx=5)
        
        ttk.Button(controls, text="Suscribirse", command=self.subscribe_to_topic).pack(side="left", padx=5)
        ttk.Button(controls, text="Cancelar Suscripción", command=self.unsubscribe_from_topic).pack(side="left", padx=5)

        # Datos de suscripción
        data_frame = ttk.LabelFrame(right, text="Datos Recibidos")
        data_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.sub_data_text = scrolledtext.ScrolledText(data_frame, height=8)
        self.sub_data_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.sub_data_text.config(state="disabled")
        ttk.Button(data_frame, text="Limpiar", command=self.clear_sub_data).pack(pady=5)

    def refresh_subscriptions(self):
        try:
            subscriptions = self.db.get_subscriptions()
            self.subscriptions_listbox.delete(0, tk.END)
            for sub in subscriptions:
                self.subscriptions_listbox.insert(tk.END, f"{sub['id']}: {sub['topic']} ({sub['source_client_id']})")
            self.status_label.config(text=f"Se encontraron {len(subscriptions)} suscripciones")
            # NUEVO: refrescar lista de tópicos públicos
            self.refresh_public_topics()
        except Exception as e:
            messagebox.showerror("Error", f"Error al refrescar suscripciones: {str(e)}")

    def refresh_public_topics(self):
        try:
            public_topics = self.db.get_published_topics()
            topic_names = [t["name"] for t in public_topics]
            self.public_topics_combo['values'] = topic_names
            if topic_names:
                self.public_topics_combo.current(0)
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar tópicos públicos: {str(e)}")

    def subscribe_to_public_topic(self):
        topic_name = self.public_topics_combo.get()
        if not topic_name:
            messagebox.showinfo("Información", "Selecciona un tópico público para suscribirte")
            return
        
        # Pedir el ID del cliente origen
        client_id = tk.simpledialog.askstring("Cliente Origen", "Ingresa el ID del cliente origen (publisher):", parent=self.root)
        if not client_id:
            return
        
        # Si estamos conectados al broker, proceder con la suscripción
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
            
        try:
            self.db.add_subscription(topic_name, client_id)
            def subscription_callback(topic_str, message):
                try:
                    message_str = message.decode('utf-8') if isinstance(message, bytes) else str(message)
                    timestamp = int(time.time())
                    self.db.add_subscription_data(topic_name, client_id, timestamp, message_str)
                    self.add_realtime_message("Recibido", f"Tópico: {topic_name} ({client_id})\nMensaje: {message_str}")
                except Exception as e:
                    print(f"Error en callback de suscripción: {e}")
            
            broker_topic = f"{client_id}/{topic_name}"
            success = self.client.subscribe(broker_topic, subscription_callback)
            if success:
                messagebox.showinfo("Éxito", f"Suscrito al tópico '{topic_name}' del cliente '{client_id}'")
                self.refresh_subscriptions()
            else:
                self.db.remove_subscription(topic_name, client_id)
                messagebox.showerror("Error", "No se pudo suscribir al tópico")
        except Exception as e:
            messagebox.showerror("Error", f"Error al suscribirse: {str(e)}")
            
    def start_das(self):
        try:
            self.das = DataAcquisitionService(self.db, verbose=False)
            self.das.add_data_callback(self.on_sensor_data)  # Asegúrate de que esta línea exista
            self.das.start()
            self.status_label.config(text="DAS iniciado correctamente")
        except Exception as e:
            messagebox.showerror("Error", f"Error al iniciar DAS: {str(e)}")

    def update_data_loop(self):
        while self.running:
            if self.das:
                try:
                    stats = self.das.get_stats()
                    readings_count = stats.get('readings_received', 0)
                    self.root.after(0, lambda c=readings_count: self.readings_label.config(text=f"Lecturas: {c}"))
                except Exception:
                    pass
            time.sleep(1)

    def connect_to_broker(self):
        host = getattr(self, "host_entry", None)
        port = getattr(self, "port_entry", None)
        host = host.get().strip() if host else "localhost"
        try:
            port = int(port.get().strip()) if port else 1505
        except ValueError:
            messagebox.showerror("Error", "El puerto debe ser un número")
            return

        client_id = self.db.get_client_id()
        if not client_id:
            messagebox.showerror("Error", "ID de cliente no establecido")
            return

        self.status_label.config(text=f"Conectando a {host}:{port}...")
        try:
            if self.client and self.client.connected:
                self.client.disconnect()
            # Agrega el ID del usuario al mensaje de estado
            self.client = Client(client_id, host, port)
            if self.client.connect():
                self.status_var.set(f"Conectado (ID: {client_id})")
                self.connect_btn.config(state="disabled")
                self.disconnect_btn.config(state="normal")
                self.status_label.config(text=f"Conectado a {host}:{port} (ID: {client_id})")
            else:
                messagebox.showerror("Error", "No se pudo conectar al broker")
        except Exception as e:
            messagebox.showerror("Error de conexión", str(e))

    def disconnect_from_broker(self):
        if self.client and self.client.connected:
            try:
                self.client.disconnect()
                self.status_var.set("Desconectado")
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
                self.status_label.config(text="Desconectado del broker")
            except Exception as e:
                messagebox.showerror("Error", f"Error al desconectar: {str(e)}")
        else:
            messagebox.showinfo("Información", "No hay conexión activa")

    def change_client_id(self):
        new_id = self.client_id_var.get().strip()
        if not new_id:
            messagebox.showerror("Error", "El ID del cliente no puede estar vacío")
            return
        try:
            self.db.set_client_id(new_id)
            messagebox.showinfo("Éxito", f"ID de cliente cambiado a: {new_id}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cambiar ID: {str(e)}")

    def update_metadata(self):
        name = self.name_var.get().strip()
        email = self.email_var.get().strip()
        metadata = self.db.get_client_metadata()
        if name:
            metadata["name"] = name
        if email:
            metadata["email"] = email
        try:
            self.db.set_client_metadata(metadata)
            messagebox.showinfo("Éxito", "Metadatos actualizados")
        except Exception as e:
            messagebox.showerror("Error", f"Error al actualizar metadatos: {str(e)}")

    def refresh_stats(self):
        self.stats_text.config(state="normal")
        self.stats_text.delete("1.0", tk.END)
        stats_text = ""
        if self.das:
            das_stats = self.das.get_stats()
            stats_text += f"Lecturas recibidas: {das_stats['readings_received']}\n"
            stats_text += f"DAS en ejecución: {'Sí' if das_stats['running'] else 'No'}\n"
        else:
            stats_text += "DAS no iniciado\n"
        if self.client and self.client.connected:
            stats_text += f"Conectado al broker: {self.client.host}:{self.client.port}\n"
            stats_text += f"ID de cliente: {self.client.client_id}\n"
        else:
            stats_text += "No conectado al broker\n"
        try:
            sensors_count = len(self.db.get_sensors())
            topics_count = len(self.db.get_topics())
            subscriptions_count = len(self.db.get_subscriptions())
            stats_text += f"Sensores registrados: {sensors_count}\n"
            stats_text += f"Tópicos registrados: {topics_count}\n"
            stats_text += f"Suscripciones activas: {subscriptions_count}\n"
        except Exception:
            stats_text += "Error al obtener estadísticas de la base de datos\n"
        self.stats_text.insert("1.0", stats_text)
        self.stats_text.config(state="disabled")

    def refresh_sensors(self):
        try:
            sensors = self.db.get_sensors()
            self.sensors_listbox.delete(0, tk.END)
            for sensor in sensors:
                self.sensors_listbox.insert(tk.END, f"{sensor['id']}: {sensor['name']}")
            self.status_label.config(text=f"Se encontraron {len(sensors)} sensores")
        except Exception as e:
            messagebox.showerror("Error", f"Error al refrescar sensores: {str(e)}")

    def on_sensor_selected(self, event):
        selection = self.sensors_listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        selected_item = self.sensors_listbox.get(selected_index)
        sensor_id = selected_item.split(":")[0].strip()
        try:
            sensor = self.db.get_sensor(sensor_id)
            if not sensor:
                return
            self.sensor_id_var.set(str(sensor["id"]))
            self.sensor_name_var.set(sensor["name"])
            self.sensor_value_var.set(sensor["last_value"])
            timestamp = datetime.fromtimestamp(sensor["last_updated"]).strftime("%Y-%m-%d %H:%M:%S")
            self.sensor_updated_var.set(timestamp)
            self.load_sensor_history()
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar detalles del sensor: {str(e)}")

    def load_sensor_history(self):
        sensor_id = self.sensor_id_var.get()
        if not sensor_id:
            messagebox.showinfo("Información", "Selecciona un sensor primero")
            return
        try:
            limit = int(self.history_limit_var.get())
        except ValueError:
            limit = 20
        try:
            sensor = self.db.get_sensor(sensor_id)
            if not sensor:
                return
            readings = self.db.get_readings(sensor["name"], limit=limit)
            self.history_text.config(state="normal")
            self.history_text.delete("1.0", tk.END)
            if not readings:
                self.history_text.insert(tk.END, "No hay lecturas para este sensor.")
            else:
                self.history_text.insert(tk.END, f"Historial de últimas {len(readings)} lecturas:\n\n")
                for reading in readings:
                    timestamp = datetime.fromtimestamp(reading["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                    self.history_text.insert(tk.END, f"{timestamp}: {reading['value']} {reading['units']}\n")
            self.history_text.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar historial: {str(e)}")

    def refresh_topics(self):
        try:
            topics = self.db.get_topics()
            self.topics_listbox.delete(0, tk.END)
            topic_names = []
            for topic in topics:
                status = "✓" if topic["publish"] else " "
                self.topics_listbox.insert(tk.END, f"{topic['id']}: {topic['name']} [{status}]")
                topic_names.append(topic['name'])
            sensors = self.db.get_sensors()
            sensor_names = [s["name"] for s in sensors]
            self.sensor_combo['values'] = sensor_names
            self.status_label.config(text=f"Se encontraron {len(topics)} tópicos")
        except Exception as e:
            messagebox.showerror("Error", f"Error al refrescar tópicos: {str(e)}")

    def on_topic_selected(self, event):
        selection = self.topics_listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        selected_item = self.topics_listbox.get(selected_index)
        topic_id = selected_item.split(":")[0].strip()
        try:
            topic = self.db.get_topic(topic_id)
            if not topic:
                return
            self.topic_id_var.set(str(topic["id"]))
            self.topic_name_var.set(topic["name"])
            self.topic_publish_var.set("Sí" if topic["publish"] else "No")
            sensors = self.db.get_topic_sensors(topic["name"])
            self.topic_sensors_text.config(state="normal")
            self.topic_sensors_text.delete("1.0", tk.END)
            if not sensors:
                self.topic_sensors_text.insert(tk.END, "No hay sensores asociados a este tópico.")
            else:
                for sensor in sensors:
                    self.topic_sensors_text.insert(tk.END, f"- {sensor['name']}: {sensor['last_value']}\n")
            self.topic_sensors_text.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar detalles del tópico: {str(e)}")

    def toggle_topic_publish(self, publish):
        topic_name = self.topic_name_var.get()
        if not topic_name:
            messagebox.showinfo("Información", "Selecciona un tópico primero")
            return
        try:
            self.db.set_topic_publish(topic_name, publish)
            self.topic_publish_var.set("Sí" if publish else "No")
            state = "activada" if publish else "desactivada"
            messagebox.showinfo("Éxito", f"Publicación {state} para el tópico '{topic_name}'")
            self.refresh_topics()
            self.refresh_public_topics()  # Añadir esta línea para actualizar tópicos públicos
        except Exception as e:
            messagebox.showerror("Error", f"Error al cambiar estado de publicación: {str(e)}")

    def add_sensor_to_topic(self):
        topic_name = self.topic_name_var.get()
        sensor_name = self.sensor_to_add_var.get()
        if not topic_name or not sensor_name:
            messagebox.showinfo("Información", "Selecciona un tópico y un sensor")
            return
        try:
            sensors = self.db.get_topic_sensors(topic_name)
            for sensor in sensors:
                if sensor["name"] == sensor_name:
                    messagebox.showinfo("Información", f"El sensor '{sensor_name}' ya está en el tópico")
                    return
            self.db.add_sensor_to_topic(topic_name, sensor_name)
            messagebox.showinfo("Éxito", f"Sensor '{sensor_name}' añadido al tópico '{topic_name}'")
            self.on_topic_selected(None)
        except Exception as e:
            messagebox.showerror("Error", f"Error al añadir sensor: {str(e)}")

    def remove_sensor_from_topic(self):
        topic_name = self.topic_name_var.get()
        sensor_name = self.sensor_to_add_var.get()
        if not topic_name or not sensor_name:
            messagebox.showinfo("Información", "Selecciona un tópico y un sensor")
            return
        try:
            self.db.remove_sensor_from_topic(topic_name, sensor_name)
            messagebox.showinfo("Éxito", f"Sensor '{sensor_name}' eliminado del tópico '{topic_name}'")
            self.on_topic_selected(None)
        except Exception as e:
            messagebox.showerror("Error", f"Error al eliminar sensor: {str(e)}")

    def refresh_subscriptions(self):
        try:
            subscriptions = self.db.get_subscriptions()
            self.subscriptions_listbox.delete(0, tk.END)
            for sub in subscriptions:
                self.subscriptions_listbox.insert(tk.END, f"{sub['id']}: {sub['topic']} ({sub['source_client_id']})")
            self.status_label.config(text=f"Se encontraron {len(subscriptions)} suscripciones")
        except Exception as e:
            messagebox.showerror("Error", f"Error al refrescar suscripciones: {str(e)}")

    def on_subscription_selected(self, event):
        selection = self.subscriptions_listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        selected_item = self.subscriptions_listbox.get(selected_index)
        match = re.match(r'^\d+:\s+(.+)\s+\((.+)\)$', selected_item)
        if not match:
            return
        topic, client = match.groups()
        
        # Actualizar las variables en lugar de usar delete/insert
        self.sub_topic_var.set(topic)
        self.sub_client_var.set(client)
        self.view_sub_data()
        
    def subscribe_to_topic(self):
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
        # Usar las variables en lugar de .get()
        topic = self.sub_topic_var.get().strip()
        source_client = self.sub_client_var.get().strip()
        if not topic or not source_client:
            messagebox.showinfo("Información", "Completa tópico y cliente origen")
            return
        try:
            self.db.add_subscription(topic, source_client)
            def subscription_callback(topic_str, message):
                try:
                    message_str = message.decode('utf-8') if isinstance(message, bytes) else str(message)
                    timestamp = int(time.time())
                    self.db.add_subscription_data(topic, source_client, timestamp, message_str)
                    self.add_realtime_message("Recibido", f"Tópico: {topic} ({source_client})\nMensaje: {message_str}")
                except Exception:
                    pass
            
            broker_topic = f"{source_client}/{topic}"
            success = self.client.subscribe(broker_topic, subscription_callback)
            if success:
                messagebox.showinfo("Éxito", f"Suscrito al tópico '{topic}' del cliente '{source_client}'")
                self.refresh_subscriptions()
            else:
                self.db.remove_subscription(topic, source_client)
                messagebox.showerror("Error", "No se pudo suscribir al tópico")
        except Exception as e:
            messagebox.showerror("Error", f"Error al suscribirse: {str(e)}")

    def unsubscribe_from_topic(self):
        selection = self.subscriptions_listbox.curselection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona una suscripción primero")
            return
        selected_index = selection[0]
        selected_item = self.subscriptions_listbox.get(selected_index)
        match = re.match(r'^\d+:\s+(.+)\s+\((.+)\)$', selected_item)
        if not match:
            return
        topic, client = match.groups()
        try:
            if self.client and self.client.connected:
                self.client.unsubscribe(f"{client}/{topic}")
            self.db.remove_subscription(topic, client)
            messagebox.showinfo("Éxito", f"Cancelada suscripción al tópico '{topic}' del cliente '{client}'")
            self.refresh_subscriptions()
        except Exception as e:
            messagebox.showerror("Error", f"Error al cancelar suscripción: {str(e)}")

    def on_sensor_data(self, sensor_name, data):
        """Callback cuando se recibe un nuevo dato de sensor."""
        # Actualizar el monitoreo en tiempo real si está activo
        current_sensor_name = self.sensor_name_var.get()
        if self.realtime_active_var.get() and sensor_name == current_sensor_name:
            timestamp = datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            value_text = f"{data['value']} {data.get('units', '')}"
            
            # Actualizar la interfaz de usuario en el hilo principal
            self.root.after(0, lambda: self.update_realtime_display(timestamp, value_text))
        
        # También actualizar últimos valores si es el sensor actual
        if sensor_name == current_sensor_name:
            self.root.after(0, lambda: self.update_sensor_latest_value(data))

    def add_realtime_message(self, source, content):
        """Muestra mensajes recibidos en las suscripciones en tiempo real."""
        # Verificar si hay una suscripción seleccionada que coincida con el origen
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        
        # Si hay una suscripción seleccionada y el mensaje coincide con su origen,
        # actualizar la vista de datos de suscripción
        if topic and client and source == "Recibido" and content.startswith(f"Tópico: {topic} ({client})"):
            # Extraer el mensaje de la cadena content
            message_start = content.find("\nMensaje: ")
            if message_start > 0:
                message_text = content[message_start + 10:]  # +10 para saltar "\nMensaje: "
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.root.after(0, lambda: self.append_to_sub_data(f"[{timestamp}] {message_text}\n"))

    def append_to_sub_data(self, text):
        """Añade texto al área de datos de suscripción."""
        self.sub_data_text.config(state="normal")
        self.sub_data_text.insert(tk.END, text)
        self.sub_data_text.see(tk.END)  # Auto-scroll al final
        self.sub_data_text.config(state="disabled")
    
    def view_sub_data(self):
        # Usar las variables en lugar de .get()
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        if not topic or not client:
            messagebox.showinfo("Información", "Selecciona una suscripción primero")
            return
        try:
            data = self.db.get_subscription_data(topic, client, limit=20)
            self.sub_data_text.config(state="normal")
            self.sub_data_text.delete("1.0", tk.END)
            if not data:
                self.sub_data_text.insert(tk.END, f"No hay datos para el tópico '{topic}' del cliente '{client}'")
            else:
                self.sub_data_text.insert(tk.END, f"Datos para el tópico '{topic}' del cliente '{client}':\n\n")
                for item in data:
                    timestamp = datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                    self.sub_data_text.insert(tk.END, f"[{timestamp}] {item['data']}\n\n")
            self.sub_data_text.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar datos: {str(e)}")

    def clear_sub_data(self):
        self.sub_data_text.config(state="normal")
        self.sub_data_text.delete("1.0", tk.END)
        self.sub_data_text.config(state="disabled")

def main():
    root = tk.Tk()
    app = TinyMQGUI(root)
    def on_closing():
        app.running = False
        if app.das:
            app.das.stop()
        if app.client and app.client.connected:
            app.client.disconnect()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()