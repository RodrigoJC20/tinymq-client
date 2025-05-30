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
from typing import Dict, List, Optional, Any, Tuple
import json
import re
import traceback

from tinymq import Client, DataAcquisitionService, Database

class TinyMQGUI:
    """Interfaz gráficaa simplificada para el cliente TinyMQ."""

    def __init__(self, root):  # Cambiar _init_ a __init__
        self.root = root
        self.root.title("TinyMQ Client")
        self.root.geometry("900x600")
        self.db = Database()
        self.das = None
        self.client = None
        self.running = True
        self.topic_owners = {} 

        self.configure_style()
        self.create_widgets()
        self.start_das()

        self.update_thread = threading.Thread(target=self.update_data_loop, daemon=True)
        self.update_thread.start()

    def on_admin_result(self, result_data):
        """Maneja los resultados de solicitudes administrativas."""
        try:
            if result_data.get('__admin_revoked', False):
                # Notificación de revocación de privilegios
                topic_name = result_data.get('topic_name', '')
                owner_id = result_data.get('owner_id', '')
                revoked_admin = result_data.get('revoked_admin', '')
                
                print(f"🔔 [GUI] Privilegios de administrador revocados: {revoked_admin} en {topic_name} por {owner_id}")
                
                # Mostrar notificación al usuario
                message = f"Tus privilegios de administrador para el tópico '{topic_name}' han sido revocados por '{owner_id}'"
                messagebox.showwarning("Privilegios Revocados", message)
                
                # Actualizar las vistas correspondientes si están abiertas
                self.refresh_my_topics_admin()
                
            elif result_data.get('__admin_result', False):
                # Resultado de una solicitud de administración
                topic_name = result_data.get('topic_name', '')
                approved = result_data.get('approved', False)
                owner_id = result_data.get('owner_id', '')
                
                if approved:
                    message = f"¡Tu solicitud de administración para '{topic_name}' ha sido APROBADA por '{owner_id}'!"
                    messagebox.showinfo("Solicitud Aprobada", message)
                else:
                    message = f"Tu solicitud de administración para '{topic_name}' ha sido RECHAZADA por '{owner_id}'"
                    messagebox.showwarning("Solicitud Rechazada", message)
                
                # Actualizar la lista de solicitudes enviadas
                self.refresh_my_admin_requests_status()
            
        except Exception as e:
            print(f"Error procesando resultado administrativo en GUI: {e}")
            import traceback
            traceback.print_exc()
    
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
        self.create_admin_tab()

        # Barra de estado
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = ttk.Label(self.status_bar, text="Listo", anchor="w")
        self.status_label.pack(side="left", padx=5)
        self.readings_label = ttk.Label(self.status_bar, text="Lecturas: 0", anchor="e")
        self.readings_label.pack(side="right", padx=10)

    def on_tab_changed(self, event):
        tab_id = self.notebook.select()
        tab_text = self.notebook.tab(tab_id, "text")
        self.status_label.config(text=f"Pestaña seleccionada: {tab_text}")

        if tab_text == "Administración":
            current_subtab = self.admin_notebook.index("current") 
            if current_subtab == 0:
                self.refresh_admin_requests()
            elif current_subtab == 1:
                self.refresh_my_topics_admin()
            elif current_subtab == 2:
                self.refresh_my_subscriptions_for_admin()
                self.refresh_my_admin_requests_status()
            self._update_admin_tab_badge()

        # Refrescar dashboard solo al cambiar a esa pestaña
        if tab_text == "Inicio":
            self.refresh_stats()
        elif tab_text == "Sensores":
            self.refresh_sensors()
        elif tab_text == "Tópicos":
            self.refresh_topics()
        elif tab_text == "Suscripciones":
            self.refresh_subscriptions()

    def create_dashboard_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Inicio")

        frame = ttk.LabelFrame(tab, text="Estado de Conexión")
        frame.pack(fill="x", padx=10, pady=10)

        # Sección para IP y puerto del servidor
        server_frame = ttk.Frame(frame)
        server_frame.pack(pady=5)
        ttk.Label(server_frame, text="IP del servidor:").pack(side="left", padx=5)
        # Cargar host y puerto guardados, si existen
        saved_host = self.db.get_broker_host() or "localhost"
        saved_port = self.db.get_broker_port() or 1505
        self.host_entry = ttk.Entry(server_frame, width=16)
        self.host_entry.pack(side="left", padx=5)
        self.host_entry.insert(0, saved_host)
        ttk.Label(server_frame, text="Puerto:").pack(side="left", padx=5)
        self.port_entry = ttk.Entry(server_frame, width=6)
        self.port_entry.pack(side="left", padx=5)
        self.port_entry.insert(0, str(saved_port))

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
        
        # Inicializar todas las variables StringVar primero
        self.client_id_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        
        # Ahora cargar los datos y asignarlos a las variables
        current_id = self.db.get_client_id() or ""
        self.client_id_var.set(current_id)
        
        # Cargar metadatos
        metadata = self.db.get_client_metadata()
        if metadata:
            self.name_var.set(metadata.get("name", ""))
            self.email_var.set(metadata.get("email", ""))
        
        # Ahora crear los widgets con las variables ya inicializadas
        ttk.Label(client_frame, text="ID:").pack(side="left", padx=5)
        ttk.Entry(client_frame, textvariable=self.client_id_var, width=15).pack(side="left", padx=5)
        ttk.Button(client_frame, text="Cambiar ID", command=self.change_client_id).pack(side="left", padx=5)
        
        ttk.Label(client_frame, text="Nombre:").pack(side="left", padx=5)
        ttk.Entry(client_frame, textvariable=self.name_var, width=15).pack(side="left", padx=5)
        
        ttk.Label(client_frame, text="Email:").pack(side="left", padx=5)
        ttk.Entry(client_frame, textvariable=self.email_var, width=20).pack(side="left", padx=5)
        
        ttk.Button(client_frame, text="Actualizar", command=self.update_metadata).pack(side="left", padx=5)

        # Estadísticas
        stats_frame = ttk.LabelFrame(tab, text="Estadísticas")
        stats_frame.pack(fill="x", padx=10, pady=5)
        self.stats_text = tk.Text(stats_frame, height=12, wrap="word")
        self.stats_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.stats_text.config(state="disabled")
        ttk.Button(stats_frame, text="Refrescar", command=self.refresh_stats).pack(pady=5)
        
        self.refresh_stats()  # Cargar estadísticas al inicio

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

        # Lista de tópicos con selección múltiple
        left = ttk.LabelFrame(main_frame, text="Tópicos")
        left.pack(side="left", fill="y", padx=(0, 10))
        self.topics_listbox = tk.Listbox(left, width=30, selectmode=tk.EXTENDED)
        self.topics_listbox.pack(fill="y", expand=True, padx=5, pady=5)
        self.topics_listbox.bind('<<ListboxSelect>>', self.on_topic_selected)
        ttk.Button(left, text="Refrescar", command=self.refresh_topics).pack(fill="x", padx=5, pady=5)

        # Botón para crear tópico SOLO si está conectado
        def open_create_topic_dialog_guarded():
            if not self.client or not self.client.connected:
                messagebox.showwarning("No conectado", "Debes conectarte al broker antes de crear un tópico.")
                return
            self.open_create_topic_dialog()
        ttk.Button(left, text="Crear Tópico", command=open_create_topic_dialog_guarded).pack(fill="x", padx=5, pady=5)

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
        ttk.Button(add_frame, text="Marcar como Activable", command=self.mark_sensor_as_activable).pack(side="left", padx=5)
            
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

        # Botones
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Crear", command=lambda: on_create()).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancelar", command=dialog.destroy).pack(side="left", padx=5)

        def on_create():
          
            if not self.client or not self.client.connected:
                messagebox.showwarning("No conectado", "Debes conectarte al broker antes de crear un tópico.", parent=dialog)
                return

            name = name_var.get().strip()
            publish = publish_var.get()
            if not name:
                messagebox.showinfo("Información", "Debes ingresar un nombre para el tópico", parent=dialog)
                return
            try:
                # Crear tópico en la BD local
                self.db.create_topic(name, publish)
                
                if self.client and self.client.connected:
                    # Crear tópico en el broker
                    self.client.create_topic(name)
                    
                    # Si se debe publicar, actualizar estado
                    if publish:
                        self.client.set_topic_publish(name, True)
                
                messagebox.showinfo("Éxito", f"Tópico '{name}' creado correctamente", parent=dialog)
                self.refresh_topics()
                self.refresh_public_topics()
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear el tópico: {str(e)}", parent=dialog)
                
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
        self.sub_topic_var = tk.StringVar()
        self.sub_topic_entry = ttk.Entry(controls, state="readonly", textvariable=self.sub_topic_var)
        self.sub_topic_entry.pack(side="left", padx=5)

        ttk.Label(controls, text="Cliente Origen:").pack(side="left", padx=5)
        self.sub_client_var = tk.StringVar()
        self.sub_client_entry = ttk.Entry(controls, state="readonly", textvariable=self.sub_client_var)
        self.sub_client_entry.pack(side="left", padx=5)
                    
        # Datos de suscripción - MEJORAS VISUALES AQUÍ
        data_frame = ttk.LabelFrame(right, text="Datos Recibidos")
        data_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Nueva configuración de fuente para mejor legibilidad
        self.sub_data_text = scrolledtext.ScrolledText(data_frame, height=8, font=("Consolas", 9))
        self.sub_data_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.sub_data_text.config(state="disabled")
        

        
        # Panel de control para visualización
        control_panel = ttk.Frame(data_frame)
        control_panel.pack(fill="x", pady=2)
        
        # Botón para limpiar el texto de datos recibidos
        ttk.Button(control_panel, text="Limpiar", command=self.clear_sub_data).pack(side="left", padx=5)
        
        # Selector de modo de visualización
        ttk.Label(control_panel, text="Visualización:").pack(side="left", padx=(10, 5))
        self.view_mode = tk.StringVar(value="Tabla")
        self.view_mode_combo = ttk.Combobox(control_panel, values=["Tabla", "JSON"], textvariable=self.view_mode, 
                                        width=8, state="readonly")
        self.view_mode_combo.pack(side="left", padx=5)
        self.view_mode_combo.current(0)
        ttk.Button(control_panel, text="Aplicar", command=self.refresh_view).pack(side="left", padx=5)
        
        
        # NUEVO: Cuadro para escribir mensajes manuales
        message_frame = ttk.LabelFrame(right, text="Enviar Mensaje")
        message_frame.pack(fill="x", padx=10, pady=5)

        self.message_entry = ttk.Entry(message_frame)
        self.message_entry.pack(fill="x", padx=5, pady=5)

        # Botones de acción
        message_buttons = ttk.Frame(message_frame)
        message_buttons.pack(fill="x", padx=5, pady=(0, 5))

        ttk.Button(message_buttons, text="Enviar", command=self.send_message_placeholder).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(message_buttons, text="Limpiar Entrada", command=lambda: self.message_entry.delete(0, tk.END)).pack(side="left", expand=True, fill="x", padx=2)
    
    
    def refresh_view(self):
        """Actualiza la vista según el modo seleccionado"""
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        if not topic or not client:
            return
            
        # Limpiar el área de visualización
        self.sub_data_text.config(state="normal")
        self.sub_data_text.delete("1.0", tk.END)
        
        try:
            # Obtener los datos de la suscripción
            data = self.db.get_subscription_data(topic, client, limit=50)
            
            # Aplicar el formato según el modo seleccionado
            mode = self.view_mode.get()
            
            if mode == "Tabla":
                # Mostrar encabezado de tabla
                header = f"{'Fecha/Hora':19} | {'Cliente':15} | {'Sensor':12} | {'Valor':8} | {'Unidades':8}\n"
                header += "-"*70 + "\n"
                self.sub_data_text.insert(tk.END, header)
                
                # Mostrar datos en formato tabla
                for item in data:
                    timestamp = datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                    cliente = client
                    try:
                        msg = item['data']
                        # Intentar convertir diccionario Python a objeto Python
                        if isinstance(msg, str):
                            try:
                                # Primero intentar como JSON válido
                                msg = json.loads(msg)
                            except json.JSONDecodeError:
                                try:
                                    # Si falla, intentar como diccionario Python
                                    import ast
                                    msg = ast.literal_eval(msg)
                                except (ValueError, SyntaxError):
                                    # Si todo falla, usar un diccionario vacío
                                    msg = {}
                        
                        # Extraer datos del mensaje
                        sensor = msg.get("sensor", "-")
                        valor = msg.get("value", "-")
                        unidades = msg.get("units", "-")
                        
                        line = f"{timestamp:19} | {cliente:15} | {sensor:12} | {valor:8} | {unidades:8}\n"
                        self.sub_data_text.insert(tk.END, line)
                    except Exception:
                        line = f"{timestamp:19} | {cliente:15} | {'ERROR':12} | {'-':8} | {'-':8}\n"
                        self.sub_data_text.insert(tk.END, line)
            else:  # Modo JSON
                # Mostrar datos en formato JSON indentado
                for item in data:
                    timestamp = datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        msg = item['data']
                        if isinstance(msg, str):
                            try:
                                # Primero intentar como JSON válido
                                msg_obj = json.loads(msg)
                            except json.JSONDecodeError:
                                try:
                                    # Si falla, intentar como diccionario Python
                                    import ast
                                    msg_obj = ast.literal_eval(msg)
                                except (ValueError, SyntaxError):
                                    # Si todo falla, mostrar el mensaje como texto
                                    self.sub_data_text.insert(tk.END, f"[{timestamp}] {client}/{topic}\n{msg}\n\n")
                                    continue
                            
                            # Convertir a JSON formateado
                            formatted_json = json.dumps(msg_obj, indent=2)
                            
                            # Insertar con timestamp y luego el JSON formateado
                            self.sub_data_text.insert(tk.END, f"[{timestamp}] {client}/{topic}\n")
                            self.sub_data_text.insert(tk.END, f"{formatted_json}\n\n")
                        else:
                            self.sub_data_text.insert(tk.END, f"[{timestamp}] {client}/{topic}\n{msg}\n\n")
                    except Exception as e:
                        self.sub_data_text.insert(tk.END, f"[{timestamp}] Error al formatear: {str(e)}\n\n")
        except Exception as e:
            self.sub_data_text.insert(tk.END, f"Error al cargar datos: {str(e)}")
            
        self.sub_data_text.config(state="disabled")
        self.sub_data_text.see(tk.END)  # Desplazarse al final

    def _get_sensor_tag(self, sensor_name):
        """Determina el tag apropiado según el tipo de sensor"""
        if not sensor_name:
            return "default"
            
        sensor_lower = sensor_name.lower()
        
        if "temp" in sensor_lower:
            return "temperature"
        elif "hum" in sensor_lower:
            return "humidity"
        elif "light" in sensor_lower or "lum" in sensor_lower:
            return "light"
        elif "pres" in sensor_lower:
            return "pressure"
        else:
            return "default"

    def apply_sensor_filters(self):
        """Aplica filtros para mostrar/ocultar ciertos tipos de sensores"""
        # Guardar la posición actual
        current_pos = self.sub_data_text.yview()[0]
        
        # Ocultar todos los mensajes primero
        self.sub_data_text.tag_configure("hidden", elide=True)
        
        # Aplicar o quitar filtros según las opciones seleccionadas
        self.sub_data_text.tag_configure("temperature", elide=not self.show_temp.get())
        self.sub_data_text.tag_configure("humidity", elide=not self.show_humidity.get())
        self.sub_data_text.tag_configure("light", elide=not self.show_light.get())
        self.sub_data_text.tag_configure("default", elide=not self.show_other.get())
        self.sub_data_text.tag_configure("pressure", elide=not self.show_other.get())
        
        # Mantener la misma posición de desplazamiento
        self.sub_data_text.yview_moveto(current_pos)
    
    def send_message_placeholder(self):
        topic_name = self.sub_topic_var.get().strip()
        client_id = self.sub_client_var.get().strip()
        message_text = self.message_entry.get().strip()


        print(f"[MSG] {topic_name} {client_id} {message_text}")

        # Validar campos vacíos
        if not topic_name or not client_id:
            messagebox.showwarning("Faltan datos", "Por favor selecciona un tópico y un cliente origen.")
            return

        if not message_text:
            messagebox.showwarning("Mensaje vacío", "Escribe un mensaje antes de enviarlo.")
            return

        # Verificar si el cliente está conectado
        if not self.client or not self.client.connected:
            messagebox.showerror("Error de conexión", "El cliente no está conectado.")
            return

        try:
                # Obtener el ID del cliente actual (remitente)
                my_client_id = self.db.get_client_id()
                
                message = {
                    "cliente": client_id,     # ID del propietario del tópico (para enrutamiento)
                    "sender": my_client_id,   # ID del cliente que envía el mensaje (remitente)
                    "sensor": "mensaje",
                    "value": message_text,
                    "timestamp": time.time(),
                    "units": ""
                }
                json_message = json.dumps(message)
                result = self.client.publish(topic_name, json_message)
                if not result:
                    messagebox.showerror("Error", f"No se pudo publicar en el tópico {topic_name}.")
                else:
                    messagebox.showinfo("Éxito", f"Mensaje enviado a {topic_name}.")
                    self.message_entry.delete(0, tk.END) 
        except Exception as e:
                messagebox.showerror("Error", f"Error al publicar el mensaje: {e}")
        

    def refresh_public_topics(self):
        """Obtiene los tópicos públicos directamente del broker"""
        try:
            if not self.client or not self.client.connected:
                messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
                return
                
            # Mostrar que estamos actualizando
            self.status_label.config(text="Actualizando tópicos públicos...")
            
            # Dar tiempo al sistema para actualizar la interfaz
            self.root.update_idletasks()
            
            # Obtener los tópicos publicados del broker
            topics = self.client.get_published_topics()
        
            
            # Actualizar el combobox con los nombres de los tópicos
            topic_names = []
            topic_display_names = []  # Nuevo: para mostrar nombre(propietario)
            topic_owners = {}  # Diccionario para almacenar {nombre_tópico: cliente_propietario}
            
            for topic in topics:
                # Verificar que el diccionario tenga las claves esperadas
                if "name" in topic and "owner" in topic:
                    topic_name = topic["name"]
                    owner_id = topic["owner"]
                    
                    # Crear el nombre para mostrar en formato nombre(propietario)
                    display_name = f"{topic_name}({owner_id})"
                    
                    topic_names.append(topic_name)
                    topic_display_names.append(display_name)  # Añadir nombre de visualización
                    topic_owners[topic_name] = owner_id
                    print(f"DEBUG: Procesando tópico: {topic_name} (propietario: {owner_id})")
            
            # Guardar la información de propietarios para uso posterior
            self.topic_owners = topic_owners
            
            # Actualizar el combobox con los nombres formateados
            self.public_topics_combo['values'] = topic_display_names
            
            # Seleccionar el primer tópico si hay alguno
            if topic_display_names:
                self.public_topics_combo.current(0)
                
            self.status_label.config(text=f"Se encontraron {len(topic_names)} tópicos públicos")
        except Exception as e:
            import traceback
            print(f"ERROR: {traceback.format_exc()}")
            messagebox.showerror("Error", f"Error al obtener tópicos públicos: {str(e)}")
    
    def subscribe_to_public_topic(self):
        """Suscribirse a un tópico público sin solicitar ID del cliente"""
        display_name = self.public_topics_combo.get()
        if not display_name:
            messagebox.showinfo("Información", "Selecciona un tópico público para suscribirte")
            return
        
        # Extraer el nombre real del tópico del formato nombre(propietario)
        match = re.match(r'^(.+)\((.+)\)$', display_name)
        if match:
            topic_name = match.group(1)
            client_id = match.group(2)
        else:
            # Si por alguna razón no coincide con el patrón, usar el método anterior
            topic_name = display_name
            client_id = self.topic_owners.get(topic_name, "")
        
        if not client_id:
            messagebox.showinfo("Error", "No se pudo determinar el propietario del tópico")
            return
        
        # Verificar si ya existe una suscripción para este tópico y cliente
        subscriptions = self.db.get_subscriptions()
        for sub in subscriptions:
            if sub["topic"] == topic_name and sub["source_client_id"] == client_id:
                messagebox.showinfo("Información", f"Ya estás suscrito al tópico '{topic_name}' del cliente '{client_id}'")
                return
        
        # Si estamos conectados al broker, proceder con la suscripción
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
                
        try:
            self.db.add_subscription(topic_name, client_id)
            
            # Usar el callback centralizado
            callback = self.create_subscription_callback(topic_name, client_id)
            
            # El formato CORRECTO del tópico en el broker es client_id/topic_name
            broker_topic = f"{client_id}/{topic_name}"
            print(f"Suscribiéndose a tópico del broker: {broker_topic}")
            success = self.client.subscribe(broker_topic, callback)
            
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
        """Conecta al broker TinyMQ."""
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        client_id = self.client_id_var.get().strip()

        if not host or not port_str or not client_id:
            messagebox.showerror("Error", "Por favor complete todos los campos de conexión")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "El puerto debe ser un número válido")
            return
        
        self.connect_btn.config(state="disabled")
        self.status_var.set("Intentando conectar...")
        self.status_label.config(text=f"Conectando a {host}:{port}...")
        self.root.update_idletasks()  # Actualizar la interfaz antes de iniciar la conexión

        # Guardar configuración del broker
        self.db.set_broker_host(host)
        self.db.set_broker_port(port)
        self.db.set_client_id(client_id)

        # Iniciar la conexión en un hilo separado
        connection_thread = threading.Thread(
            target=self._connect_thread,
            args=(client_id, host, port),
            daemon=True
        )
        connection_thread.start()

    def _connect_thread(self, client_id, host, port):
        """Realiza la conexión en un hilo separado para no bloquear la UI."""
        try:
            # Crear cliente
            self.client = Client(client_id, host, port)
            
            # Register connection state callback BEFORE connecting
            self.client.register_connection_state_callback(self.on_connection_state_changed)
            
            # Intentar conectar con timeout razonable
            connection_success = self.client.connect()
            
            # Actualizar la UI en el hilo principal
            self.root.after(0, lambda: self._handle_connection_result(connection_success))
        except Exception as e:
            # En caso de error, actualizar la UI en el hilo principal
            self.root.after(0, lambda e=e: self._handle_connection_error(e))

    def _handle_connection_result(self, success):
        """Maneja el resultado de la conexión en el hilo principal."""
        
        print(f"DEBUG: Conexión al broker {'exitosa' if success else 'fallida'}")
        if success:
            # Don't update UI state here since the connection callback will handle it
            # Just perform the setup tasks
            try:
                if self.das and self.das.running:
                    self.client.subscribe_to_sensor_control(self.das)
                    print("✅ Control remoto de sensores configurado")
                
                client_id = self.db.get_client_id()
                admin_topic = f"{client_id}/admin_notifications"
                print(f"📢 Suscribiéndose a notificaciones administrativas: {admin_topic}")
                self.client.subscribe(admin_topic, self.on_admin_notify_message)
                
                # Registrar callbacks para notificaciones administrativas
                self.client.register_admin_notification_handler(self.on_admin_notification)
                self.client.register_admin_result_handler(self.on_admin_result)
                self.client.register_sensor_status_callback(self.show_sensor_notification)
                
                # AÑADIR ESTA LÍNEA para suscribirse a las notificaciones de control de sensores
                if self.das and self.das.running:
                    self.client.subscribe_to_sensor_control(self.das)
            
        
                # Configurar la publicación de tópicos existentes
                published_topics = self.db.get_published_topics()
                for topic_info in published_topics:
                    self._setup_topic_publishing(topic_info["name"])

                # Re-suscribirse a todos los tópicos guardados
                subscriptions = self.db.get_subscriptions()
                for sub in subscriptions:
                    topic = sub["topic"]
                    source_client = sub["source_client_id"]
                    callback = self.create_subscription_callback(topic, source_client)
                    broker_topic = f"{source_client}/{topic}"
                    self.client.subscribe(broker_topic, callback)
            except Exception as e:
                messagebox.showwarning("Advertencia", f"Error al restaurar configuración: {str(e)}")
        else:
            # Handle connection failure (the callback won't be called in this case)
            self.client = None
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")
            self.status_var.set("Desconectado")
            self.status_label.config(text="No se pudo conectar al broker")
            messagebox.showerror("Error", "No se pudo conectar al broker")

    def on_admin_notify_message(self, topic_str, payload):
        """Procesa notificaciones administrativas recibidas por publicación."""
        try:
            if not payload:
                return
                
            print(f"📢 Notificación admin recibida en {topic_str}: {payload}")
            data = json.loads(payload.decode('utf-8'))
            
            # Verificar si es un comando de sensor
            if isinstance(data, dict) and data.get("command") == "set_sensor":
                sensor_name = data.get("sensor_name")
                active = data.get("active")
                
                print(f"🔄 Procesando comando remoto: {sensor_name}={active}")
                
                # Enviar al ESP32 a través del DAS
                if self.das and self.das.running:
                    cmd = {
                        "command": f"set_{sensor_name}",
                        "value": 1 if active else 0
                    }
                    print(f"🛠️ Enviando comando al ESP32: {cmd}")
                    success = self.das.send_command(cmd)
                    print(f"📤 Resultado de envío al ESP32: {success}")
                else:
                    print("⚠️ DAS no está corriendo, no se puede enviar comando")
        except Exception as e:
            print(f"❌ Error procesando notificación admin: {e}")
            import traceback
            traceback.print_exc()
        
    def _handle_connection_error(self, error):
        """Maneja errores de conexión en el hilo principal."""
        print(f"ERROR: Error de conexión: {error}")
        self.client = None
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.status_var.set("Desconectado")
        self.status_label.config(text=f"Error de conexión: {str(error)}")
        messagebox.showerror("Error", f"Error de conexión: {str(error)}")

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
        
        # Verificar si está conectado
        if self.client and self.client.connected:
            respuesta = messagebox.askyesno("Atención", 
                "Cambiar el ID requiere desconectarse del broker. ¿Deseas continuar?")
            if not respuesta:
                return
            # Desconectar antes de cambiar el ID
            try:
                self.client.disconnect()
                self.status_var.set("Desconectado")
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
            except Exception as e:
                messagebox.showerror("Error", f"Error al desconectar: {str(e)}")
                return
        
        try:
            self.db.set_client_id(new_id)
            messagebox.showinfo("Éxito", f"ID de cliente cambiado a: {new_id}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cambiar ID: {str(e)}")

    def update_metadata(self):
        name = self.name_var.get().strip()
        email = self.email_var.get().strip()

        # Validar que no estén vacíos
        if not name or not email:
            messagebox.showerror("Error", "El nombre y el email no pueden estar vacíos.")
            return

        # Verificar si está conectado
        if self.client and self.client.connected:
            respuesta = messagebox.askyesno("Atención", 
                "Actualizar metadatos requiere desconectarse del broker. ¿Deseas continuar?")
            if not respuesta:
                return
            # Desconectar antes de cambiar metadatos
            try:
                self.client.disconnect()
                self.status_var.set("Desconectado")
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
            except Exception as e:
                messagebox.showerror("Error", f"Error al desconectar: {str(e)}")
                return

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
            if not sensors:
                self.sensors_listbox.insert(tk.END, "Sin sensores registrados")
            else:
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
        
        # Si se estaba monitoreando otro sensor, limpiar el área de tiempo real
        if self.realtime_active_var.get():
            self.clear_realtime_data()
        
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
            
            # Si estaba activo el monitoreo, mostrar mensaje informativo
            if self.realtime_active_var.get():
                self.realtime_text.config(state="normal")
                self.realtime_text.insert(tk.END, f"Monitoreo en tiempo real activado para sensor: {sensor['name']}\nEsperando datos...\n\n")
                self.realtime_text.config(state="disabled")
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
            # Guardar el índice seleccionado actualmente
            selected = self.topics_listbox.curselection()
            selected_index = selected[0] if selected else None

            topics = self.db.get_topics()
            self.topics_listbox.delete(0, tk.END)
            topic_names = []
            if not topics:
                self.topics_listbox.insert(tk.END, "Sin tópicos registrados")
            else: 
                for topic in topics:
                    status = "✓" if topic["publish"] else " "
                    display = f"{topic['id']}: {topic['name']} [{status}]"
                    self.topics_listbox.insert(tk.END, display)
                    topic_names.append(topic['name'])

            # Restaurar la selección por índice si corresponde
            if selected_index is not None and self.topics_listbox.size() > selected_index:
                self.topics_listbox.selection_set(selected_index)
                self.topics_listbox.see(selected_index)

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
        
        # Usar el primer tópico seleccionado para mostrar detalles
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
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
        
        selection = self.topics_listbox.curselection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona al menos un tópico primero")
            return
        
        # Almacenar IDs de tópicos para reselección posterior
        selected_topic_ids = []
        for idx in selection:
            item = self.topics_listbox.get(idx)
            topic_id = item.split(":")[0].strip()
            selected_topic_ids.append(topic_id)
        
        success_count = 0
        
        for selected_index in selection:
            selected_item = self.topics_listbox.get(selected_index)
            topic_id = selected_item.split(":")[0].strip()
            try:
                topic = self.db.get_topic(topic_id)
                if not topic:
                    continue
                
                # Saltar silenciosamente si el tópico ya está en el estado deseado
                if topic["publish"] == publish:
                    continue
                
                # Actualizar la base de datos local
                self.db.set_topic_publish(topic["name"], publish)
                
                # NUEVO: Actualizar el estado en el broker si estamos conectados
                if self.client and self.client.connected:
                    self.client.set_topic_publish(topic["name"], publish)
                    
                success_count += 1
            except Exception as e:
                messagebox.showerror("Error", f"Error en tópico ID {topic_id}: {str(e)}")
                
        # Actualizar UI si se realizaron cambios
        if success_count > 0:
            # Actualizar el panel de detalles
            if len(selection) > 0:
                self.topic_publish_var.set("Sí" if publish else "No")
            
            # Refrescar listas
            self.refresh_topics()
            self.refresh_public_topics()
            
            # Reseleccionar tópicos después de refrescar
            for i in range(self.topics_listbox.size()):
                item = self.topics_listbox.get(i)
                topic_id = item.split(":")[0].strip()
                if topic_id in selected_topic_ids:
                    self.topics_listbox.selection_set(i)
            
            # Mostrar mensaje de éxito
            state = "activada" if publish else "desactivada"
            messagebox.showinfo("Éxito", f"Publicación {state} para {success_count} tópico(s)")
            

    def add_sensor_to_topic(self):
        selection = self.topics_listbox.curselection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona al menos un tópico")
            return
            
        sensor_name = self.sensor_to_add_var.get()
        if not sensor_name:
            messagebox.showinfo("Información", "Selecciona un sensor para agregar")
            return
        
        success_count = 0
        for selected_index in selection:
            selected_item = self.topics_listbox.get(selected_index)
            topic_id = selected_item.split(":")[0].strip()
            try:
                topic = self.db.get_topic(topic_id)
                if not topic:
                    continue
                
                # Verificar si el sensor ya está en el tópico
                sensors = self.db.get_topic_sensors(topic["name"])
                sensor_exists = False
                for sensor in sensors:
                    if sensor["name"] == sensor_name:
                        sensor_exists = True
                        break
                
                if sensor_exists:
                    continue
                
                self.db.add_sensor_to_topic(topic["name"], sensor_name)
                
                self._setup_topic_publishing(topic["name"])
                success_count += 1
            except Exception as e:
                messagebox.showerror("Error", f"Error al agregar sensor al tópico ID {topic_id}: {str(e)}")
        
        if success_count > 0:
            messagebox.showinfo("Éxito", f"Sensor '{sensor_name}' añadido a {success_count} tópico(s)")
            self.on_topic_selected(None)

            
    def remove_sensor_from_topic(self):
        selection = self.topics_listbox.curselection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona al menos un tópico")
            return
            
        sensor_name = self.sensor_to_add_var.get()
        if not sensor_name:
            messagebox.showinfo("Información", "Selecciona un sensor para eliminar")
            return
        
        success_count = 0
        not_found_topics = []
        
        for selected_index in selection:
            selected_item = self.topics_listbox.get(selected_index)
            topic_id = selected_item.split(":")[0].strip()
            try:
                topic = self.db.get_topic(topic_id)
                if not topic:
                    continue
                
                # Verificar si el sensor está en el tópico
                sensors = self.db.get_topic_sensors(topic["name"])
                sensor_exists = False
                for sensor in sensors:
                    if sensor["name"] == sensor_name:
                        sensor_exists = True
                        break
                
                if not sensor_exists:
                    not_found_topics.append(topic["name"])
                    continue
                
                self.db.remove_sensor_from_topic(topic["name"], sensor_name)
                
                self._setup_topic_publishing(topic["name"])
                success_count += 1
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar sensor del tópico ID {topic_id}: {str(e)}")
        
        message = ""
        if success_count > 0:
            message = f"Sensor '{sensor_name}' eliminado de {success_count} tópico(s). "
            
        if not_found_topics:
            message += f"Advertencia: El sensor no estaba presente en los tópicos: {', '.join(not_found_topics)}"
            
        if message:
            messagebox.showinfo("Resultado", message)
        
        self.on_topic_selected(None)

    def refresh_subscriptions(self):
        try:
            # Si no hay conexión, solo limpiar la lista y mostrar mensaje informativo
            if not self.client or not self.client.connected:
                self.subscriptions_listbox.delete(0, tk.END)
                self.subscriptions_listbox.insert(tk.END, "Sin suscripciones activas")
                self.status_label.config(text="No hay conexión con el broker")
                return

            subscriptions = self.db.get_subscriptions()
            self.subscriptions_listbox.delete(0, tk.END)
            if not subscriptions:
                self.subscriptions_listbox.insert(tk.END, "Sin suscripciones activas")
            else:
                for sub in subscriptions:
                    self.subscriptions_listbox.insert(tk.END, f"{sub['id']}: {sub['topic']} ({sub['source_client_id']})")
            self.status_label.config(text=f"Se encontraron {len(subscriptions)} suscripciones")
            self.refresh_public_topics()
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
        
        # Actualizar las variables
        self.sub_topic_var.set(topic)
        self.sub_client_var.set(client)
        self.view_sub_data()
        
        # Programar actualización periódica
        self.schedule_subscription_refresh()

    def schedule_subscription_refresh(self):
        # Cancelar timer anterior si existe
        if hasattr(self, '_refresh_timer'):
            self.root.after_cancel(self._refresh_timer)
        
        # Programar nueva actualización cada 30 segundos
        self._refresh_timer = self.root.after(30000, self._auto_refresh_subscription_data)

    def _auto_refresh_subscription_data(self):
        # Solo actualizar si hay un tópico y cliente seleccionado
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        if topic and client:
            self.view_sub_data()
            # Programar siguiente actualización
            self.schedule_subscription_refresh()
        
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
        
        # Verificar si ya existe una suscripción para este tópico y cliente
        subscriptions = self.db.get_subscriptions()
        for sub in subscriptions:
            if sub["topic"] == topic and sub["source_client_id"] == source_client:
                messagebox.showinfo("Información", f"Ya estás suscrito al tópico '{topic}' del cliente '{source_client}'")
                return
                
        try:
            self.db.add_subscription(topic, source_client)
            
            # Usar el callback centralizado
            callback = self.create_subscription_callback(topic, source_client)
            
            broker_topic = topic if "/" in topic else f"{source_client}/{topic}"
            print(f"Suscribiéndose a tópico del broker: {broker_topic}")
            success = self.client.subscribe(broker_topic, callback)
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
            broker_topic = topic if "/" in topic else f"{client}/{topic}"
            if self.client and self.client.connected:
                self.client.unsubscribe(f"{broker_topic}")
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
        print(f"DEBUG: add_realtime_message recibió: {source}, {content}")
        
        # Verificar si hay una suscripción seleccionada que coincida con el origen
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        
        # Extraer información del contenido
        message_start = content.find("\nMensaje: ")
        if message_start > 0:
            topic_info = content[:message_start]  # Extraer información del tópico
            message_text = content[message_start + 10:]  # +10 para saltar "\nMensaje: "
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"DEBUG: Mensaje para mostrar: [{timestamp}] {message_text}")
            
            # Mostrar todos los mensajes recibidos, sin importar el tópico seleccionado
            if source == "Recibido":
                if not topic or topic_info.find(topic) >= 0:
                    # Se corrigió el corchete faltante en la timestamp
                    self.root.after(0, lambda: self.append_to_sub_data(f"[{timestamp}] {client}/{topic}  {message_text}\n"))
        else:
            print(f"DEBUG: Formato incorrecto en contenido: {content}")

    def append_to_sub_data(self, text):
        """Añade texto al área de datos de suscripción."""
        try:
            print(f"DEBUG: Intentando añadir texto a sub_data_text: {text[:50]}...")
            self.sub_data_text.config(state="normal")
            self.sub_data_text.insert(tk.END, text)
            self.sub_data_text.see(tk.END)  # Auto-scroll al final
            self.sub_data_text.config(state="disabled")
            print("DEBUG: Texto añadido correctamente")
        except Exception as e:
            print(f"ERROR: No se pudo añadir texto a sub_data_text: {e}")
            import traceback
            traceback.print_exc()

    def view_sub_data(self):
        topic = self.sub_topic_var.get()
        client = self.sub_client_var.get()
        if not topic or not client:
            messagebox.showinfo("Información", "Selecciona una suscripción primero")
            return
        try:
            # Mantener el límite alto para asegurar que se muestren todos los mensajes históricos
            data = self.db.get_subscription_data(topic, client, limit=500)  
            self.sub_data_text.config(state="normal")
            self.sub_data_text.delete("1.0", tk.END)
        
            # Cabecera
            header = f"{'Fecha/Hora':19} | {'Cliente':15} | {'Sensor':12} | {'Valor':8} | {'Unidades':8}\n"
            header += "-"*70 + "\n"
            self.sub_data_text.insert(tk.END, header)
            
            # Dejar espacio entre cabecera y datos
            self.sub_data_text.insert(tk.END, "\n")
            
            # Ordenar explícitamente los datos por timestamp para garantizar orden cronológico
            data = sorted(data, key=lambda x: x["timestamp"])
            
            for item in data:
                timestamp = datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                cliente = client
                try:
                    msg = item['data']
                    # Intentar convertir diccionario Python a objeto Python
                    if isinstance(msg, str):
                        try:
                            # Primero intentar como JSON válido
                            msg = json.loads(msg)
                        except json.JSONDecodeError:
                            try:
                                # Si falla, intentar como diccionario Python
                                import ast
                                msg = ast.literal_eval(msg)
                            except (ValueError, SyntaxError):
                                # Si todo falla, usar un diccionario vacío
                                msg = {}
                    
                    # Extraer datos del mensaje
                    sensor = msg.get("sensor", "-")
                    valor = msg.get("value", "-")
                    unidades = msg.get("units", "-")
                    
                    line = f"{timestamp:19} | {cliente:15} | {sensor:12} | {valor:8} | {unidades:8}\n"
                    self.sub_data_text.insert(tk.END, line)
                    
                except Exception:
                    sensor = valor = unidades = "-"
                    line = f"{timestamp:19} | {cliente:15} | {sensor:12} | {valor:8} | {unidades:8}\n"
                    self.sub_data_text.insert(tk.END, line)
                    
            self.sub_data_text.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar datos: {str(e)}")

    def configure_style(self):
        style = ttk.Style()
        style.configure('TButton', font=('Helvetica', 10))
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('Header.TLabel', font=('Helvetica', 12, 'bold'))

    def clear_sub_data(self):
        self.sub_data_text.config(state="normal")
        self.sub_data_text.delete("1.0", tk.END)
        self.sub_data_text.config(state="disabled")

    def _setup_topic_publishing(self, topic_name: str) -> None:
        """
        Setup publishing for a topic.
        Args:
            topic_name: Name of topic to publish
        """
        if not self.das or not self.client or not self.client.connected:
            return

        # Eliminar todos los callbacks previos para evitar duplicados y publicaciones de sensores eliminados
        self.das.clear_callbacks()

        # Registrar de nuevo los callbacks para todos los tópicos publicados
        published_topics = self.db.get_published_topics()
        for topic_info in published_topics:
            t_name = topic_info["name"]
            sensors = self.db.get_topic_sensors(t_name)
            if not sensors:
                continue
            sensor_names = [s["name"] for s in sensors]

            def make_publish_callback(topic_name, sensor_names):
                def publish_callback(sensor_name: str, data: dict):
                    current_topic_info = self.db.get_topic(topic_name)
                    if not current_topic_info or not current_topic_info["publish"]:
                        return
                    if sensor_name in sensor_names and self.client and self.client.connected:
                        message = {
                            "sensor": sensor_name,
                            "value": data["value"],
                            "timestamp": data["timestamp"],
                            "units": data["units"]
                        }
                        try:
                            json_message = json.dumps(message)
                            result = self.client.publish(topic_name, json_message)
                            if not result:
                                messagebox.showinfo("Error", f'Error al publicar en el topico {topic_name}')
                        except Exception as e:
                            messagebox.showinfo("Error", f'Error: {e}')
                return publish_callback

            self.das.add_data_callback(make_publish_callback(t_name, sensor_names))

    def create_subscription_callback(self, topic, source_client):
        def callback(topic_str, message):
            if not self.is_window_alive():
                return
            try:
                message_str = message.decode('utf-8') if isinstance(message, bytes) else str(message)
                timestamp = int(time.time())
                
                # Normalizar el formato de tópico
                if topic_str.startswith('['):
                    try:
                        topic_str = json.loads(topic_str)[0]
                    except Exception as e:
                        print(f"ERROR decodificando JSON: {e}")
                
                # Separar client_id/topic
                parts = topic_str.split('/', 1)
                if len(parts) == 2:
                    actual_client_id = parts[0]  # ID del propietario (para enrutamiento)
                    actual_topic_name = parts[1]
                else:
                    actual_client_id = source_client
                    actual_topic_name = topic
                
                # IMPORTANTE: Normalizar formato del mensaje a JSON válido antes de guardar
                try:
                    # Si ya es un JSON válido, parsearlo
                    msg_obj = json.loads(message_str)
                    # Re-serializar para garantizar formato JSON válido
                    message_json = json.dumps(msg_obj)
                except json.JSONDecodeError:
                    # Si parece un diccionario Python (con comillas simples), convertirlo a JSON
                    if message_str.startswith('{') and message_str.endswith('}'):
                        try:
                            import ast
                            msg_obj = ast.literal_eval(message_str)
                            message_json = json.dumps(msg_obj)
                        except (ValueError, SyntaxError):
                            # Si no se puede parsear, guardarlo como está
                            message_json = message_str
                    else:
                        # No es un formato reconocible, guardarlo como está
                        message_json = message_str
                
                # Guardar en BD el mensaje normalizado en formato JSON
                self.db.add_subscription_data(topic, source_client, timestamp, message_json)
                
                # Mostrar SOLO si la suscripción seleccionada coincide
                selected_topic = self.sub_topic_var.get()
                selected_client = self.sub_client_var.get()
                if selected_topic == actual_topic_name and selected_client == actual_client_id:
                    try:
                        # Usar el objeto ya parseado si está disponible
                        if 'msg_obj' in locals():
                            data = msg_obj
                        else:
                            # Si no se pudo parsear antes, intentarlo de nuevo
                            data = json.loads(message_json)
                        
                        # Extraer información del remitente si está disponible
                        sender_id = data.get("sender", actual_client_id)
                        sensor = data.get("sensor", "-")
                        valor = data.get("value", "-")
                        unidades = data.get("units", "-")
                        time_fmt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Enviar datos estructurados incluyendo el remitente
                        message_data = {
                            "timestamp": time_fmt,
                            "client": actual_client_id,  # ID propietario (para referencia)
                            "sender": sender_id,         # ID remitente (quien envió el mensaje)
                            "topic": actual_topic_name,
                            "sensor": sensor,
                            "value": valor,
                            "units": unidades
                        }
                        
                        # Actualizar la vista según el modo seleccionado
                        if self.view_mode.get() == "Tabla":
                            self.root.after(0, lambda data=message_data: self.append_formatted_data(data))
                        else:
                            # Si está en modo JSON, usar el formato JSON
                            formatted_json = json.dumps(data, indent=2)
                            text = f"[{time_fmt}] {sender_id}@{actual_client_id}/{actual_topic_name}\n{formatted_json}\n\n"
                            self.root.after(0, lambda t=text: self.append_to_sub_data(t))
                    except Exception as e:
                        # Si falla el parseo, registrar el error y mostrar en formato de texto
                        print(f"ERROR al procesar mensaje como JSON: {e}")
                        time_fmt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        msg_text = f"[{time_fmt}] {actual_client_id}/{actual_topic_name} - {message_str}\n"
                        self.root.after(0, lambda text=msg_text: self.append_to_sub_data(text))
                        
            except Exception as e:
                    print(f"⚠️ ERROR EN CALLBACK: {e}")
                    import traceback
                    traceback.print_exc()

        return callback

    

    def append_formatted_data(self, data):
        """Añade datos formateados al área de visualización."""
        try:
            self.sub_data_text.config(state="normal")
            
            # CAMBIO: Ahora mostramos "sender" (remitente) en lugar de "client" (propietario)
            sender_id = data.get('sender', data['client'])  # Usar sender si está disponible, si no client
            
            # Si el remitente es diferente del propietario, mostrarlo con formato especial
            if sender_id != data['client']:
                # Formato: timestamp | remitente@propietario | sensor | valor | unidades
                line = f"{data['timestamp']:19} | {sender_id:15} | {data['sensor']:12} | {data['value']:8} | {data['units']:8}\n"
            else:
                # Si remitente == propietario, mostrar de forma normal
                line = f"{data['timestamp']:19} | {sender_id:15} | {data['sensor']:12} | {data['value']:8} | {data['units']:8}\n"
            
            # Insertar al final sin tag específico
            self.sub_data_text.insert(tk.END, line)
            
            # Mantener un máximo de líneas (por ejemplo, 100)
            lines = self.sub_data_text.get("1.0", tk.END).splitlines()
            if len(lines) > 100:
                self.sub_data_text.delete("1.0", "2.0")  # Eliminar primera línea
            
            # Desplazarse al final automáticamente
            self.sub_data_text.see(tk.END)
            self.sub_data_text.config(state="disabled")
            
        except Exception as e:
            print(f"ERROR: No se pudo añadir datos formateados: {e}")
            import traceback
            traceback.print_exc()
            
    def create_admin_tab(self):
        """Crea la pestaña de Administración con sub-pestañas."""
        admin_tab = ttk.Frame(self.notebook)
        self.notebook.add(admin_tab, text="Administración")

        # Crear notebook para sub-pestañas dentro de administración
        self.admin_notebook = ttk.Notebook(admin_tab)
        self.admin_notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Sub-pestaña 1: Solicitudes Pendientes
        self.create_admin_requests_tab()
        
        # Sub-pestaña 2: Mis Tópicos
        self.create_my_topics_management_tab()
        
        # Sub-pestaña 3: Solicitar Administración
        self.create_request_admin_tab()
        
        self.create_admin_management_tab()  # NUEVA PESTAÑA
        
        # Agregar manejador para cambios de sub-pestaña
        self.admin_notebook.bind("<<NotebookTabChanged>>", self.on_admin_subtab_changed)

    def on_admin_subtab_changed(self, event):
        """Maneja el cambio de sub-pestañas en administración."""
        try:
            subtab_id = self.admin_notebook.select()
            subtab_text = self.admin_notebook.tab(subtab_id, "text")
            
            print(f"[DEBUG] Cambiando a sub-pestaña: {subtab_text}")
            
            # AGREGAR DELAY PARA EVITAR MÚLTIPLES LLAMADAS RÁPIDAS
            if hasattr(self, '_last_admin_tab_change'):
                time_since_last = time.time() - self._last_admin_tab_change
                if time_since_last < 1.0:  # Ignorar cambios muy rápidos
                    print(f"[DEBUG] Cambio de pestaña muy rápido, ignorando...")
                    return
            
            self._last_admin_tab_change = time.time()
            
            if subtab_text == "Mis Administraciones":
                print(f"[DEBUG] Refrescando mis administraciones...")
                # Aumentar el delay para evitar problemas de threading
                self.root.after(200, self.refresh_my_admin_topics)
                
            elif subtab_text == "Solicitar Administración":
                self.root.after(200, self.refresh_available_topics_for_admin)
                
            elif subtab_text == "Solicitudes Recibidas":
                self.root.after(200, self.refresh_admin_requests)
                
            elif subtab_text == "Mis Tópicos":
                self.root.after(200, self.refresh_my_topics_admin)
                
        except Exception as e:
            print(f"[ERROR] Error en on_admin_subtab_changed: {e}")
        
    def create_admin_management_tab(self):
        """Crea la pestaña para gestionar mis administraciones."""
        tab = ttk.Frame(self.admin_notebook)
        self.admin_notebook.add(tab, text="Mis Administraciones")
        
        # Frame principal
        main_frame = ttk.Frame(tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Lista de tópicos donde soy administrador
        ttk.Label(main_frame, text="Tópicos donde soy administrador:").pack(anchor="w", pady=(0, 5))
        
        # Treeview para mostrar mis tópicos admin
        columns = ('topic', 'owner', 'status', 'granted_date')
        self.my_admin_topics_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=8)
        
        self.my_admin_topics_tree.heading('topic', text='Tópico')
        self.my_admin_topics_tree.heading('owner', text='Propietario')
        self.my_admin_topics_tree.heading('status', text='Estado')
        self.my_admin_topics_tree.heading('granted_date', text='Otorgado el')
        
        self.my_admin_topics_tree.column('topic', width=200)
        self.my_admin_topics_tree.column('owner', width=150)
        self.my_admin_topics_tree.column('status', width=100)
        self.my_admin_topics_tree.column('granted_date', width=150)
        
        self.my_admin_topics_tree.pack(fill="both", expand=True, pady=(0, 10))
        self.my_admin_topics_tree.bind('<<TreeviewSelect>>', self.on_my_admin_topic_selected)
        
        # Botones
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(btn_frame, text="Actualizar Lista", command=self.refresh_my_admin_topics).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Cargar Sensores", command=self.load_sensors_in_bottom_panel).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Renunciar a Administración", command=self.resign_from_admin).pack(side="left")
        
        # Frame para sensores del tópico seleccionado
        sensors_frame = ttk.LabelFrame(main_frame, text="Sensores del tópico seleccionado")
        sensors_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        # Treeview para sensores - AGREGAR COLUMNA "Activable"
        sensor_columns = ('sensor', 'status', 'activable', 'configured_date')
        self.admin_topic_sensors_tree = ttk.Treeview(sensors_frame, columns=sensor_columns, show="headings", height=6)
        
        self.admin_topic_sensors_tree.heading('sensor', text='Sensor')
        self.admin_topic_sensors_tree.heading('status', text='Estado')
        self.admin_topic_sensors_tree.heading('activable', text='Activable')  # NUEVA COLUMNA
        self.admin_topic_sensors_tree.heading('configured_date', text='Configurado el')
        
        self.admin_topic_sensors_tree.column('sensor', width=180)
        self.admin_topic_sensors_tree.column('status', width=80)
        self.admin_topic_sensors_tree.column('activable', width=80)  # NUEVA COLUMNA
        self.admin_topic_sensors_tree.column('configured_date', width=150)
        
        self.admin_topic_sensors_tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Botones para gestión de sensores
        sensor_btn_frame = ttk.Frame(sensors_frame)
        sensor_btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        ttk.Button(sensor_btn_frame, text="Activar Sensor", command=lambda: self.toggle_sensor_status(True)).pack(side="left", padx=(0, 10))
        ttk.Button(sensor_btn_frame, text="Desactivar Sensor", command=lambda: self.toggle_sensor_status(False)).pack(side="left")
        
        
    def load_sensors_in_bottom_panel(self):
        """Carga los sensores del tópico seleccionado en la sección inferior."""
        selection = self.my_admin_topics_tree.selection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona un tópico para ver sus sensores")
            return
            
        item = self.my_admin_topics_tree.item(selection[0])
        topic_name = item['values'][0]
        owner_id = item['values'][1]
        
        print(f"🔍 DEBUG GUI: Cargando sensores para {topic_name} (propietario: {owner_id})")
        
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return
        
        try:
            # Limpiar lista de sensores actual
            for item in self.admin_topic_sensors_tree.get_children():
                self.admin_topic_sensors_tree.delete(item)
            
            print(f"🔍 DEBUG GUI: Solicitando sensores al cliente...")
            # Obtener configuración de sensores desde el broker
            sensors = self.client.get_topic_sensors_config(topic_name)
            print(f"🔍 DEBUG GUI: Sensores recibidos: {sensors}")
            
            if not sensors:
                print("🔍 DEBUG GUI: No se recibieron sensores")
                # Insertar mensaje informativo
                self.admin_topic_sensors_tree.insert("", "end", values=(
                    "No hay sensores configurados", "N/A", "N/A", "N/A"
                ))
                return
            
            # Cargar sensores en el TreeView inferior
            print(f"🔍 DEBUG GUI: Procesando {len(sensors)} sensores para mostrar:")
            for i, sensor in enumerate(sensors):
                print(f"🔍 DEBUG GUI: Sensor {i}: {sensor}")
                name = sensor.get("name", "N/A")
                
                # DEBUG: Mostrar el tipo y valor de activable
                activable = sensor.get("activable", "false")
                print(f"🔍 DEBUG GUI: Campo activable: tipo={type(activable)}, valor={activable}")
                
                # Convertir a string y luego comparar
                activable_str = str(activable).lower()
                activable_text = "Sí" if activable_str in ["true", "1", "yes", "sí"] else "No"
                print(f"🔍 DEBUG GUI: activable_str={activable_str}, activable_text={activable_text}")
                
                # DEBUG: Mostrar el tipo y valor de active
                active = sensor.get("active", "false")
                print(f"🔍 DEBUG GUI: Campo active: tipo={type(active)}, valor={active}")
                
                # Convertir a string y luego comparar
                active_str = str(active).lower()
                status = "Activo" if active_str in ["true", "1", "yes", "sí"] else "Inactivo"
                print(f"🔍 DEBUG GUI: active_str={active_str}, status={status}")
                
                configured_date = sensor.get("configured_at", "N/A")
                if configured_date and configured_date != "N/A":
                    configured_date = str(configured_date)[:19]
                print(f"🔍 DEBUG GUI: configured_date={configured_date}")
                
                # DEBUG: Mostrar exactamente lo que se va a insertar en el TreeView
                values = (name, status, activable_text, configured_date)
                print(f"🔍 DEBUG GUI: Insertando valores en TreeView: {values}")
                
                # Usar las columnas existentes: sensor, status, activable, configured_date
                self.admin_topic_sensors_tree.insert("", "end", values=values)
            
            # Mostrar mensaje de éxito
            self.status_label.config(text=f"Cargados {len(sensors)} sensores para '{topic_name}'")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar sensores: {e}")
            print(f"❌ Error cargando sensores: {e}")
            import traceback
            traceback.print_exc()
            
    def refresh_my_admin_topics(self):
        """Actualiza la lista de tópicos donde soy administrador."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return
        
        # PREVENIR MÚLTIPLES REFRESCOS SIMULTÁNEOS
        if hasattr(self, '_refreshing_admin_topics') and self._refreshing_admin_topics:
            print(f"[DEBUG GUI] Refresh ya en progreso, ignorando...")
            return
        
        try:
            self._refreshing_admin_topics = True  # Flag para prevenir duplicados
            print(f"[DEBUG GUI] Iniciando refresh_my_admin_topics")
            
            # Limpiar lista actual
            for item in self.my_admin_topics_tree.get_children():
                self.my_admin_topics_tree.delete(item)
            
            print(f"[DEBUG GUI] Lista limpiada, obteniendo tópicos admin...")
            
            # Obtener tópicos donde soy admin
            admin_topics = self.client.get_my_admin_topics()
            
            print(f"[DEBUG GUI] Recibidos {len(admin_topics)} tópicos admin")
            
            for i, topic in enumerate(admin_topics):
                print(f"[DEBUG GUI] Procesando tópico {i+1}: {topic}")
                status = "Activo" if topic.get('publish', 'false') == 'true' else "Inactivo"
                granted_date = topic.get('granted_at', '')[:19] if topic.get('granted_at') else ''
                
                self.my_admin_topics_tree.insert("", "end", values=(
                    topic.get('name', ''),
                    topic.get('owner_client_id', ''),
                    status,
                    granted_date
                ))
            
            self.status_label.config(text=f"Administrador de {len(admin_topics)} tópicos")
            print(f"[DEBUG GUI] Actualización completada: {len(admin_topics)} tópicos")
            
        except Exception as e:
            print(f"[ERROR GUI] Error en refresh_my_admin_topics: {e}")
            messagebox.showerror("Error", f"No se pudo actualizar la lista: {e}")
        finally:
            self._refreshing_admin_topics = False  # Liberar el flag


    def on_my_admin_topic_selected(self, event):
        """Maneja la selección de un tópico donde soy administrador."""
        selection = self.my_admin_topics_tree.selection()
        if not selection:
            # Limpiar la sección de sensores si no hay selección
            for item in self.admin_topic_sensors_tree.get_children():
                self.admin_topic_sensors_tree.delete(item)
            return
        
        # Cargar sensores automáticamente cuando se selecciona un tópico
        self.load_sensors_in_bottom_panel()

    def load_admin_topic_sensors(self, topic_name):
        """Carga los sensores de un tópico donde soy administrador."""
        if not self.client or not self.client.connected:
            return
        
        try:
            # Limpiar lista de sensores
            for item in self.admin_topic_sensors_tree.get_children():
                self.admin_topic_sensors_tree.delete(item)
            
            # Obtener configuración de sensores
            sensors = self.client.get_topic_sensors_config(topic_name)
            
            for sensor in sensors:
                status = "Activo" if sensor.get('active', False) else "Inactivo"
                configured_date = sensor.get('configured_at', '')[:19] if sensor.get('configured_at') else ''
                
                self.admin_topic_sensors_tree.insert("", "end", values=(
                    sensor.get('name', ''),
                    status,
                    configured_date
                ))
            
        except Exception as e:
            print(f"Error cargando sensores: {e}")


    def resign_from_admin(self):
        """Renuncia a la administración del tópico seleccionado."""
        selection = self.my_admin_topics_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un tópico primero")
            return
        
        item = self.my_admin_topics_tree.item(selection[0])
        topic_name = item['values'][0]
        owner = item['values'][1]
        
        # Confirmar renuncia
        confirm = messagebox.askyesno(
            "Confirmar Renuncia",
            f"¿Estás seguro de que deseas renunciar a la administración del tópico '{topic_name}' de {owner}?\n\n"
            "Esta acción no se puede deshacer."
        )
        
        if not confirm:
            return
        
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return
        
        try:
            def resign_callback(success, message):
                self.root.after(0, lambda: self._handle_resign_result(success, message, topic_name))
            
            success = self.client.resign_admin_status(topic_name, callback=resign_callback)
            if success:
                self.status_label.config(text="Procesando renuncia...")
            else:
                messagebox.showerror("Error", "No se pudo enviar la solicitud de renuncia")
        except Exception as e:
            messagebox.showerror("Error", f"Error al renunciar: {str(e)}")

    def _handle_resign_result(self, success, message, topic_name):
        """Maneja el resultado de la renuncia administrativa."""
        if success:
            messagebox.showinfo("Renuncia Exitosa", f"Has renunciado exitosamente a la administración del tópico '{topic_name}'")
            # Refrescar la lista
            self.refresh_my_admin_topics()
        else:
            messagebox.showerror("Error", f"No se pudo procesar la renuncia: {message}")
        
        self.status_label.config(text="Listo")

    def toggle_sensor_status(self, active):
        """Activa o desactiva un sensor como administrador."""
        # Obtener tópico seleccionado
        topic_selection = self.my_admin_topics_tree.selection()
        if not topic_selection:
            messagebox.showwarning("Advertencia", "Selecciona un tópico primero")
            return
        
        topic_item = self.my_admin_topics_tree.item(topic_selection[0])
        topic_name = topic_item['values'][0]
        owner_id = topic_item['values'][1]
        
        # Obtener sensor seleccionado
        sensor_selection = self.admin_topic_sensors_tree.selection()
        if not sensor_selection:
            messagebox.showwarning("Advertencia", "Selecciona un sensor primero")
            return
        
        sensor_item = self.admin_topic_sensors_tree.item(sensor_selection[0])
        sensor_name = sensor_item['values'][0]  # Ahora es solo el nombre
        
        is_controllable = sensor_item['values'][2] == "Sí"  # NUEVA COLUMNA: índice 2
        
        # Verificar que el sensor sea controlable
        if not is_controllable:
            messagebox.showwarning("Advertencia", 
                                f"El sensor '{sensor_name}' no está marcado como controlable")
            return
        
        # Verificar si es mensaje informativo
        if sensor_name == "No hay sensores configurados":
            messagebox.showinfo("Información", "No hay sensores para controlar")
            return
        
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return
        
        # Mostrar que estamos procesando la solicitud
        self.status_label.config(text=f"Enviando comando para {'activar' if active else 'desactivar'} sensor...")
        
        # Enviar el comando usando la función del cliente
        success = self.client.send_sensor_command(topic_name, owner_id, sensor_name, active)
        
        if success:
            # El mensaje se envió, la notificación será manejada por show_sensor_notification
            self.status_label.config(text="Comando enviado, esperando confirmación...")
        else:
            messagebox.showerror("Error", "No se pudo enviar el comando")
            self.status_label.config(text="Error al enviar comando")
        
    def _update_sensor_status_ui(self, topic_name, sensor_name, active):
        """Actualiza la UI cuando se confirma un cambio de estado de sensor."""
        # Buscar el item en el TreeView
        for item in self.admin_topic_sensors_tree.get_children():
            values = self.admin_topic_sensors_tree.item(item, "values")
            if values[0] == sensor_name:  # Primera columna es el nombre del sensor
                # Actualizar el estado (segunda columna)
                new_status = "Activo" if active else "Inactivo"
                current_values = list(values)
                current_values[1] = new_status
                
                # Actualizar el item
                self.admin_topic_sensors_tree.item(item, values=current_values)
                
                # Mostrar mensaje de confirmación
                status_text = "activado" if active else "desactivado"
                messagebox.showinfo("Éxito", f"Sensor '{sensor_name}' {status_text} correctamente")
                self.status_label.config(text=f"Sensor {sensor_name} {status_text}")
                
                # Si estamos conectados al DAS, enviar comando al ESP32
                if hasattr(self, 'das') and self.das and self.das.running:
                    try:
                        # El ventilador es un caso especial que queremos controlar
                        if sensor_name.lower() == "fan":
                            command = {
                                "command": "set_fan",
                                "value": 1 if active else 0
                            }
                            print(f"✅ Enviando comando al ESP32: {command}")
                            self.das.send_command(command)
                    except Exception as e:
                        print(f"❌ Error enviando comando al ESP32: {e}")
                
                return
                
        # Si llegamos aquí, no encontramos el sensor en la lista
        self.status_label.config(text="Estado actualizado, pero no encontrado en la lista")
            
    def create_request_admin_tab(self):
        """Crea la sub-pestaña para solicitar administración de tópicos."""
        request_tab = ttk.Frame(self.admin_notebook)
        self.admin_notebook.add(request_tab, text="Solicitar")

        main_frame = ttk.Frame(request_tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Panel superior: Lista de suscripciones con botón integrado
        topics_frame = ttk.LabelFrame(main_frame, text="Mis Suscripciones")
        topics_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Toolbar con mensaje explicativo y botón de solicitud
        toolbar_frame = ttk.Frame(topics_frame)
        toolbar_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Button(toolbar_frame, text="Actualizar Lista", 
                command=self.refresh_my_subscriptions_for_admin).pack(side="left", padx=(0, 5))
        
        # Botón de solicitud en el mismo toolbar
        ttk.Button(toolbar_frame, text="Solicitar Privilegios de Administrador", 
                command=self.request_admin_for_selected_topic).pack(side="left", padx=(10, 5))
        
        ttk.Label(toolbar_frame, text="Seleccione un tópico y solicite administración").pack(side="right", padx=5)

        # TreeView para mostrar tópicos disponibles - Solo 2 columnas
        columns = ("topic", "owner")
        self.available_topics_tree = ttk.Treeview(topics_frame, columns=columns, show="headings", height=10)
        
        self.available_topics_tree.heading("topic", text="Nombre del Tópico")
        self.available_topics_tree.heading("owner", text="Propietario")
        
        self.available_topics_tree.column("topic", width=400)
        self.available_topics_tree.column("owner", width=200)

        # Scrollbar - Directamente junto al TreeView
        scrollbar = ttk.Scrollbar(topics_frame, orient="vertical", command=self.available_topics_tree.yview)
        self.available_topics_tree.configure(yscrollcommand=scrollbar.set)
        
        # Empaquetar TreeView y scrollbar
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.available_topics_tree.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)

        self.available_topics_tree.bind("<<TreeviewSelect>>", self.on_available_topic_selected)

        # Panel de estado de solicitudes (arreglado)
        status_frame = ttk.LabelFrame(main_frame, text="Mis Solicitudes Enviadas")
        status_frame.pack(fill="both", expand=True)

        # Toolbar para el estado - Sin separación extra
        status_toolbar = ttk.Frame(status_frame)
        status_toolbar.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(status_toolbar, text="Estado de sus solicitudes de administración:").pack(side="right", padx=5)
        ttk.Button(status_toolbar, text="Actualizar Estado", 
                command=self.refresh_my_admin_requests_status).pack(side="left", padx=5)

        # TreeView para solicitudes - Directamente en status_frame
        request_columns = ("topic", "owner", "date", "status")
        self.my_requests_tree = ttk.Treeview(status_frame, columns=request_columns, show="headings", height=6)
        
        self.my_requests_tree.heading("topic", text="Tópico")
        self.my_requests_tree.heading("owner", text="Propietario")
        self.my_requests_tree.heading("date", text="Fecha Solicitud")
        self.my_requests_tree.heading("status", text="Estado")
        
        self.my_requests_tree.column("topic", width=220)
        self.my_requests_tree.column("owner", width=150)
        self.my_requests_tree.column("date", width=150)
        self.my_requests_tree.column("status", width=100)

        # Scrollbar para solicitudes - Directamente junto al TreeView
        requests_scrollbar = ttk.Scrollbar(status_frame, orient="vertical", 
                                        command=self.my_requests_tree.yview)
        self.my_requests_tree.configure(yscrollcommand=requests_scrollbar.set)
        
        # Empaquetar TreeView y scrollbar de solicitudes
        requests_scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.my_requests_tree.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        
        
    def refresh_my_subscriptions_for_admin(self):
        """Actualiza la lista mostrando solo tópicos a los que estoy suscrito para solicitar administración."""
        try:
            # Limpiar la lista actual
            for item in self.available_topics_tree.get_children():
                self.available_topics_tree.delete(item)
    
            # Obtener mis suscripciones
            my_subscriptions = self.db.get_subscriptions()
            current_client_id = self.client_id_var.get()
            
            if not my_subscriptions:
                return
            
            for subscription in my_subscriptions:
                topic_name = subscription.get('topic', '')
                owner_id = subscription.get('source_client_id', '')
                
                # No mostrar mis propios tópicos ya que no se puede solicitar administración de ellos
                if owner_id == current_client_id:
                    continue
                
                # Insertar en la lista - solo nombre y propietario
                self.available_topics_tree.insert("", "end", values=(
                    topic_name,
                    owner_id
                ))
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar las suscripciones: {e}")     
    def refresh_available_topics_for_admin(self):
        """Actualiza la lista de tópicos disponibles para solicitar administración."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return

        try:
            # Limpiar la lista actual
            for item in self.available_topics_tree.get_children():
                self.available_topics_tree.delete(item)

            # Obtener tópicos publicados del broker
            published_topics = self.client.get_published_topics()
            
            # Obtener mis suscripciones actuales
            my_subscriptions = self.db.get_subscriptions()
            subscribed_topics = [sub['topic'] for sub in my_subscriptions]

            # Filtrar tópicos (excluir los propios)
            current_client_id = self.client_id_var.get()
            
            for topic_info in published_topics:
                topic_name = topic_info.get('name', '')
                owner = topic_info.get('owner', '')
                
                # No mostrar mis propios tópicos
                if owner == current_client_id:
                    continue
                    
                # Determinar si estoy suscrito
                is_subscribed = topic_name in subscribed_topics
                subscribed_text = "✓ Sí" if is_subscribed else "✗ No"
                
                # Insertar en la lista
                self.available_topics_tree.insert("", "end", values=(
                    topic_name,
                    owner,
                    "Publicado",
                    subscribed_text
                ))
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo actualizar la lista de tópicos: {e}")

    def show_my_subscriptions_admin(self):
        """Muestra solo los tópicos a los que estoy suscrito."""
        try:
            # Limpiar la lista actual
            for item in self.available_topics_tree.get_children():
                self.available_topics_tree.delete(item)

            # Obtener mis suscripciones
            my_subscriptions = self.db.get_subscriptions()
            current_client_id = self.client_id_var.get()
            
            for subscription in my_subscriptions:
                topic_name = subscription.get('topic', '')
                owner_id = subscription.get('source_client_id', '')
                
                # No mostrar mis propios tópicos
                if owner_id == current_client_id:
                    continue
                
                # Insertar en la lista
                self.available_topics_tree.insert("", "end", values=(
                    topic_name,
                    owner_id,
                    "Suscrito",
                    "✓ Sí"
                ))
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar las suscripciones: {e}")

    def on_available_topic_selected(self, event):
        """Maneja la selección de un tópico disponible."""
        selection = self.available_topics_tree.selection()
        if not selection:
            # Limpiar variables si no hay selección
            if hasattr(self, 'selected_topic_name_var'):
                self.selected_topic_name_var.set("")
            if hasattr(self, 'selected_topic_owner_var'):
                self.selected_topic_owner_var.set("")
            return
    
        item = self.available_topics_tree.item(selection[0])
        values = item['values']
        
        if len(values) >= 2:
            topic_name, owner = values[:2]
            
            # Asegurar que las variables existan
            if not hasattr(self, 'selected_topic_name_var'):
                self.selected_topic_name_var = tk.StringVar()
            if not hasattr(self, 'selected_topic_owner_var'):
                self.selected_topic_owner_var = tk.StringVar()
                
            self.selected_topic_name_var.set(str(topic_name))
            self.selected_topic_owner_var.set(str(owner))
   
    def request_admin_for_selected_topic(self):
        """Solicita administración para el tópico seleccionado."""
        selection = self.available_topics_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Debe seleccionar un tópico primero")
            return
        
        item = self.available_topics_tree.item(selection[0])
        values = item['values']
        
        if len(values) < 2:
            messagebox.showwarning("Advertencia", "Información del tópico incompleta")
            return
        
        topic_name = str(values[0])
        owner_id = str(values[1])
        
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return
        
        # Confirmar la acción
        result = messagebox.askyesno(
            "Confirmar Solicitud", 
            f"¿Está seguro de que desea solicitar administración del tópico '{topic_name}' a '{owner_id}'?"
        )
        
        if not result:
            return
        
        try:
            # CORREGIR: Definir callback para manejar la respuesta con 4 parámetros
            def handle_response(success, message, error_code, topic_name):
                # Usar after para ejecutar en el hilo principal de la GUI
                self.root.after(0, lambda: self._show_admin_request_result(success, message, error_code, topic_name))
            
            # Enviar solicitud a través del cliente con callback
            self.client.request_admin_status(topic_name, owner_id, callback=handle_response)
            
            # Mostrar mensaje temporal
            self.status_label.config(text="Enviando solicitud de administración...")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar solicitud: {e}")  
            
            
    def _show_admin_request_result(self, success, message, error_code, topic_name):
        """Muestra el resultado de la solicitud de administración en el hilo principal."""
        if success:
            messagebox.showinfo("Éxito", f"Solicitud de administración enviada para el tópico '{topic_name}'")
            # Actualizar la lista de solicitudes
            self.refresh_my_admin_requests_status()
        else:
            # Mostrar mensaje de error específico
            if error_code == "ALREADY_HAS_ADMIN":
                messagebox.showwarning("Solicitud Rechazada", 
                                     f"El tópico '{topic_name}' ya tiene un administrador asignado")
            elif error_code == "NOT_SUBSCRIBED":
                messagebox.showwarning("Solicitud Rechazada", 
                                     f"Debes estar suscrito al tópico '{topic_name}' para solicitar administración")
            elif error_code == "SELF_REQUEST":
                messagebox.showwarning("Solicitud Inválida", 
                                     f"No puedes solicitar administración de tu propio tópico '{topic_name}'")
            elif error_code == "TOPIC_NOT_FOUND":
                messagebox.showerror("Error", f"El tópico '{topic_name}' no existe")
            elif error_code == "OWNER_NOT_FOUND":
                messagebox.showerror("Error", f"El propietario '{owner_id}' no existe")
            else:
                messagebox.showerror("Error", f"No se pudo enviar la solicitud: {message}")
        
        # Limpiar mensaje de estado
        self.status_label.config(text="Listo")
   
   
    def create_admin_requests_tab(self):
        """Crea la sub-pestaña de solicitudes pendientes."""
        requests_tab = ttk.Frame(self.admin_notebook)
        self.admin_notebook.add(requests_tab, text="Pendientes")
    
        # Panel principal
        main_frame = ttk.Frame(requests_tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Panel izquierdo: lista de solicitudes (ahora más ancho)
        left_frame = ttk.LabelFrame(main_frame, text="Solicitudes de Administración Pendientes")
        left_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        # Panel superior para acciones
        toolbar = ttk.Frame(left_frame)
        toolbar.pack(fill="x", padx=5, pady=5)
        
        ttk.Button(toolbar, text="Actualizar Solicitudes", command=self.on_update_admin_requests).pack(side="left", padx=5)
        ttk.Label(toolbar, text="Seleccione una solicitud para ver detalles").pack(side="right", padx=5)
        
        # Lista de solicitudes con TreeView
        self.requests_frame = ttk.Frame(left_frame)
        self.requests_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        cols = ('id', 'requester', 'topic', 'timestamp')
        self.requests_tree = ttk.Treeview(self.requests_frame, columns=cols, show='headings', height=20)
        
        # Configurar columnas
        self.requests_tree.heading('id', text='ID')
        self.requests_tree.heading('requester', text='Solicitante')
        self.requests_tree.heading('topic', text='Tópico')
        self.requests_tree.heading('timestamp', text='Fecha')
        
        self.requests_tree.column('id', width=50, anchor='center')
        self.requests_tree.column('requester', width=180)
        self.requests_tree.column('topic', width=250)
        self.requests_tree.column('timestamp', width=150)
        
        self.requests_tree.bind('<<TreeviewSelect>>', self.on_request_selected)
        self.requests_tree.pack(side="left", fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.requests_frame, orient="vertical", command=self.requests_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.requests_tree.configure(yscrollcommand=scrollbar.set)
        
        # Botones de acción
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(btn_frame, text="Aprobar Solicitud", command=self.approve_admin_request,
                   width=20).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Rechazar Solicitud", command=self.reject_admin_request,
                   width=20).pack(side="left", padx=5)
        
        # Panel derecho: detalles (ahora más compacto)
        right_frame = ttk.LabelFrame(main_frame, text="Detalles de la Solicitud")
        right_frame.pack(side="right", fill="y", padx=5)
        
        # Variables para los detalles
        self.req_id_var = tk.StringVar()
        self.req_client_var = tk.StringVar()
        self.req_topic_var = tk.StringVar()
        self.req_time_var = tk.StringVar()
        
        # Grid de detalles más limpio y compacto
        details_grid = ttk.Frame(right_frame)
        details_grid.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(details_grid, text="ID:", width=10).grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(details_grid, textvariable=self.req_id_var, font=("Helvetica", 9, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(details_grid, text="Solicitante:", width=10).grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(details_grid, textvariable=self.req_client_var, font=("Helvetica", 9, "bold")).grid(row=1, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(details_grid, text="Tópico:", width=10).grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(details_grid, textvariable=self.req_topic_var, font=("Helvetica", 9, "bold")).grid(row=2, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(details_grid, text="Fecha:", width=10).grid(row=3, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(details_grid, textvariable=self.req_time_var).grid(row=3, column=1, sticky="w", padx=5, pady=3)
        
    def refresh_admin_tab(self):
        """Actualiza solo la sub-pestaña de administración actualmente visible."""
        try:
            # Si no hay conexión, simplemente retornar sin mostrar errores
            if not self.client or not self.client.connected:
                # No mostrar mensajes de error si aún no se ha conectado
                return
                
            # Determinar qué sub-pestaña está activa
            current_subtab = self.admin_notebook.index("current")
            
            # Actualizar solo la sub-pestaña activa
            if current_subtab == 0:  # Pendientes
                self.refresh_admin_requests()
            elif current_subtab == 1:  # Mis Tópicos
                self.refresh_my_topics_admin()
            elif current_subtab == 2:  # Solicitar
                self.refresh_my_subscriptions_for_admin()
                self.refresh_my_admin_requests_status()
            
            # Actualizar siempre el badge de notificaciones (esto es ligero)
            self._update_admin_tab_badge()
            
        except Exception as e:
            print(f"❌ Error actualizando pestaña de administración: {e}")
            
    def refresh_my_admin_requests_status(self):
        """Actualiza el estado de mis solicitudes de administración enviadas."""
        try:
            # Limpiar lista actual
            for item in self.my_requests_tree.get_children():
                self.my_requests_tree.delete(item)

            if not self.client or not self.client.connected:
                return

            # Obtener mis solicitudes enviadas
            my_requests = self.client.get_my_admin_requests()
            
            if not my_requests:
                return
                
            # Insertar en la tabla de mis solicitudes
            for req in my_requests:
                topic_name = req.get("topic_name", "Desconocido")
                owner_id = req.get("owner_id", "Desconocido")
                
                # Formatear fecha
                timestamp_raw = req.get("request_timestamp", int(time.time()))
                if isinstance(timestamp_raw, (int, float)):
                    timestamp = datetime.fromtimestamp(timestamp_raw).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    timestamp = str(timestamp_raw)
                    
                status = req.get("status", "pending")
                status_text = {
                    "pending": "Pendiente",
                    "approved": "Aprobado",
                    "rejected": "Rechazado"
                }.get(status, status.capitalize() if isinstance(status, str) else "Desconocido")
                
                self.my_requests_tree.insert("", "end", values=(
                    topic_name,
                    owner_id,
                    timestamp,
                    status_text
                ))
                
            # Log de actualización
            timestamp = time.strftime("%H:%M:%S")
                
        except Exception as e:
            print(f"❌ Error actualizando estado de mis solicitudes: {e}")
            import traceback
            traceback.print_exc()
            
    def create_my_topics_management_tab(self):
        """Crea la sub-pestaña de gestión de mis tópicos."""
        my_topics_tab = ttk.Frame(self.admin_notebook)
        self.admin_notebook.add(my_topics_tab, text="Mis Tópicos")

        main_frame = ttk.Frame(my_topics_tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ====== PANEL SUPERIOR: LISTA DE TÓPICOS ======
        topics_frame = ttk.LabelFrame(main_frame, text="Tópicos que he Creado")
        topics_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Barra de herramientas
        toolbar_frame = ttk.Frame(topics_frame)
        toolbar_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Button(toolbar_frame, text="Actualizar Mis Tópicos", 
                command=self.on_update_my_topics_admin).pack(side="left", padx=(0, 5))
        ttk.Label(toolbar_frame, text="Seleccione un tópico para gestionar").pack(side="right", padx=5)
        
        # TreeView con contenedor para scrollbar
        tree_container = ttk.Frame(topics_frame)
        tree_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Definición del TreeView
        columns = ("name", "status", "admin", "created")
        self.my_topics_admin_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=10)
        
        self.my_topics_admin_tree.heading("name", text="Nombre del Tópico")
        self.my_topics_admin_tree.heading("status", text="Estado")
        self.my_topics_admin_tree.heading("admin", text="Administrador")
        self.my_topics_admin_tree.heading("created", text="Creado")
        
        self.my_topics_admin_tree.column("name", width=220)
        self.my_topics_admin_tree.column("status", width=100)
        self.my_topics_admin_tree.column("admin", width=150)
        self.my_topics_admin_tree.column("created", width=100)

        # Agregar TreeView y scrollbar al contenedor
        self.my_topics_admin_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.my_topics_admin_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.my_topics_admin_tree.configure(yscrollcommand=scrollbar.set)

        self.my_topics_admin_tree.bind("<<TreeviewSelect>>", self.on_my_topic_admin_selected)

        # ====== PANEL INFERIOR: DETALLES Y ACCIONES ======
        details_frame = ttk.LabelFrame(main_frame, text="Detalles del Tópico")
        details_frame.pack(fill="x", pady=(0, 5))

        # Variables para mostrar info del tópico seleccionado
        self.my_topic_admin_name_var = tk.StringVar()
        self.my_topic_admin_status_var = tk.StringVar()
        self.my_topic_admin_admin_var = tk.StringVar()

        # Panel de información
        info_frame = ttk.Frame(details_frame)
        info_frame.pack(fill="x", padx=10, pady=10)

        # Información del tópico en dos filas
        ttk.Label(info_frame, text="Tópico:", width=12).grid(row=0, column=0, sticky="w")
        ttk.Label(info_frame, textvariable=self.my_topic_admin_name_var, 
                font=("Helvetica", 10, "bold")).grid(row=0, column=1, sticky="w")

        ttk.Label(info_frame, text="Estado:", width=12).grid(row=0, column=2, sticky="w", padx=(20, 5))
        ttk.Label(info_frame, textvariable=self.my_topic_admin_status_var).grid(row=0, column=3, sticky="w")

        ttk.Label(info_frame, text="Administrador:", width=12).grid(row=1, column=0, sticky="w")
        ttk.Label(info_frame, textvariable=self.my_topic_admin_admin_var).grid(row=1, column=1, 
                sticky="w", columnspan=3)
        
        ttk.Button(main_frame, text="Revocar Admin", 
                command=self.revoke_topic_admin_privilege, padding=5).pack(side="bottom", padx=5, pady=5, anchor="w")
               
    def on_update_my_topics_admin(self):
        """Callback para el botón 'Actualizar Lista' en Mis Tópicos."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
        self.refresh_my_topics_admin()
                    
    def refresh_my_topics_admin(self):
        """Actualiza la lista de mis tópicos en la pestaña de administración."""
        if not self.client or not self.client.connected:
            #messagebox.showwarning("Advertencia", "No estás conectado al broker")
            return

        try:
            # Obtener tópicos del broker
            my_topics = self.client.get_my_topics()
            
            # Limpiar la lista actual
            for item in self.my_topics_admin_tree.get_children():
                self.my_topics_admin_tree.delete(item)
            
            # Agregar tópicos a la lista
            for topic in my_topics:
                name = topic.get("name", "")
                status = "✓ Activo" if topic.get("publish_active", False) else "✗ Inactivo"
                admin = topic.get("admin_client_id", "Sin administrador")
                if admin == "":
                    admin = "Sin administrador"
                created_raw = topic.get("created_at", "")
                created = ""
                if created_raw:
                    try:
                        from datetime import datetime
                        # Si es timestamp numérico
                        if isinstance(created_raw, (int, float)) or (isinstance(created_raw, str) and created_raw.isdigit()):
                            created_dt = datetime.fromtimestamp(int(float(created_raw)))
                            created = created_dt.strftime("%d/%m/%Y")
                        # Si es string tipo ISO
                        elif "T" in created_raw:
                            # Quitar zona si existe
                            iso = created_raw.split("T")[0]
                            # Si tiene formato completo, parsear
                            try:
                                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                                created = created_dt.strftime("%d/%m/%Y")
                            except Exception:
                                # Si falla, solo mostrar la parte de la fecha
                                created = iso.replace("-", "/")
                                               # Si es string pero no ISO ni timestamp, intentar extraer la fecha
                        try:
                            # Buscar patrón de fecha al inicio del string
                            import re
                            match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(created_raw))
                            if match:
                                # Formatear como dd/mm/yyyy
                                created = f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
                            else:
                                created = str(created_raw)
                        except Exception:
                            created = str(created_raw)
                    except Exception:
                        created = str(created_raw)
                self.my_topics_admin_tree.insert("", "end", values=(name, status, admin, created))
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener mis tópicos: {str(e)}")
        
        
    def on_my_topic_admin_selected(self, event):
        """Maneja la selección de un tópico en la lista de administración."""
        selection = self.my_topics_admin_tree.selection()
        if not selection:
            return
        
        item = self.my_topics_admin_tree.item(selection[0])
        values = item["values"]
        
        if len(values) >= 3:
            self.my_topic_admin_name_var.set(values[0])
            self.my_topic_admin_status_var.set(values[1])
            self.my_topic_admin_admin_var.set(values[2])

    def toggle_my_topic_admin_publish(self, publish: bool):
        """Activa o desactiva la publicación del tópico seleccionado."""
        selection = self.my_topics_admin_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un tópico primero")
            return
        
        item = self.my_topics_admin_tree.item(selection[0])
        topic_name = item["values"][0]
        
        if self.client and self.client.connected:
            success = self.client.set_topic_publish(topic_name, publish)
            if success:
                action = "activada" if publish else "desactivada"
                messagebox.showinfo("Éxito", f"Publicación {action} para '{topic_name}'")
              
            else:
                messagebox.showerror("Error", "No se pudo cambiar el estado de publicación")
        else:
            messagebox.showwarning("Advertencia", "No estás conectado al broker")

    def revoke_topic_admin_privilege(self):
        """Revoca los privilegios de administrador del tópico seleccionado."""
        selection = self.my_topics_admin_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un tópico primero")
            return
        
        # si no esta conectado mostrar mensaje
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No estás conectado al broker")
            return
        
        item = self.my_topics_admin_tree.item(selection[0])
        topic_name = item["values"][0]
        admin_id = item["values"][2]
        
        if admin_id == "Sin administrador":
            messagebox.showinfo("Info", "Este tópico no tiene administrador")
            return
        
        # Confirmar revocación
        if messagebox.askyesno("Confirmar Revocación", 
                            f"¿Estás seguro de revocar privilegios de administrador a '{admin_id}' para el tópico '{topic_name}'?\n\n"
                            "Esta acción no se puede deshacer."):
            try:
                if self.client and self.client.connected:
                    success = self.client.revoke_admin_privileges(topic_name, admin_id)
                    if success:
                        messagebox.showinfo("Éxito", f"Privilegios revocados a '{admin_id}' para '{topic_name}'")
                
                        self.refresh_my_topics_admin()
                    else:
                        messagebox.showerror("Error", "No se pudieron revocar los privilegios")
                else:
                    messagebox.showwarning("Advertencia", "No estás conectado al broker")
            except Exception as e:
                messagebox.showerror("Error", f"Error revocando privilegios: {str(e)}")

        
    def on_request_selected(self, event):
        """Maneja la selección de una solicitud en el árbol."""
        selected_items = self.requests_tree.selection()
        if not selected_items:
            return
            
        item = selected_items[0]
        values = self.requests_tree.item(item, 'values')
        if not values or len(values) < 4:
            return
            
        # Actualizar variables de detalles
        self.req_id_var.set(values[0])
        self.req_client_var.set(values[1])
        self.req_topic_var.set(values[2])
        self.req_time_var.set(values[3])
        

    def on_update_admin_requests(self):
        """Callback para el botón 'Actualizar Lista' en la pestaña de administración."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debe conectarse primero al broker")
            return
        self.refresh_admin_requests()

    def refresh_admin_requests(self):
        """Actualiza la lista de solicitudes de administración pendientes."""
        if not self.client or not self.client.connected:
            # Solo limpiar la lista y mostrar mensaje informativo, sin popup
            self.requests_tree.delete(*self.requests_tree.get_children())
            self.requests_tree.insert('', 'end', values=("Sin solicitudes pendientes", "", "", ""))
            self.status_label.config(text="No hay conexión con el broker")
            return
            
        self.requests_tree.delete(*self.requests_tree.get_children())
        try:
            # Obtener solicitudes pendientes
            requests = self.client.get_pending_admin_requests()
            
            if not requests:
                self.requests_tree.insert('', 'end', values=("Sin solicitudes pendientes", "", "", ""))
                return

            # Agregar cada solicitud al árbol
            for req in requests:
                # Extraer el ID de solicitud
                req_id = req.get('id', 'N/A')

                # Extraer ID del solicitante
                requester_id = req.get('requester_id', req.get('requester_client_id', 'Desconocido'))
                
                # Extraer nombre del tópico - puede venir de diferentes formas según JOIN SQL
                topic_name = "Desconocido"
                if 'topic' in req and isinstance(req['topic'], str):
                    # Si es solo el nombre del tópico
                    topic_name = req['topic']
                elif 'topic' in req and isinstance(req['topic'], dict):
                    # Si es un objeto con la información del tópico
                    topic_name = req['topic'].get('name', 'Desconocido')
                elif 'topic_name' in req:
                    # Si viene directamente como topic_name
                    topic_name = req['topic_name']
                
                # Formatear fecha - puede venir como timestamp numérico o string
                timestamp = "Desconocido"
                timestamp_raw = req.get('request_time', req.get('request_timestamp', req.get('timestamp', None)))
                
                if timestamp_raw:
                    try:
                        # Si es un entero (timestamp Unix)
                        if isinstance(timestamp_raw, (int, float)):
                            dt = datetime.fromtimestamp(timestamp_raw)
                            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                        # Si es una cadena ISO o formato DB
                        elif isinstance(timestamp_raw, str):
                            if timestamp_raw.isdigit():
                                # Si es un timestamp en string
                                dt = datetime.fromtimestamp(int(timestamp_raw))
                                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                # Intentar como formato ISO o similar
                                try:
                                    # Formato ISO
                                    dt = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                                except:
                                    # Usar como está si no se puede parsear
                                    timestamp = timestamp_raw
                    except Exception as e:
                        timestamp = str(timestamp_raw)
                    
                # Insertar en el TreeView con los valores extraídos
                values = (req_id, requester_id, topic_name, timestamp)
         
                self.requests_tree.insert('', 'end', values=values)
                
            
        except Exception as e:
            import traceback
        
    def send_admin_request(self):
        """Envía una solicitud para ser administrador de un tópico."""
        topic = self.req_topic_var.get().strip()
        owner = self.req_owner_var.get().strip()
        
        if not topic or not owner:
            messagebox.showinfo("Error", "Debe especificar tópico y dueño")
            return
                
        if not self.client or not self.client.connected:
            messagebox.showinfo("Error", "No está conectado al broker")
            return
        
        # Verificar que no soy el dueño
        my_client_id = self.db.get_client_id()
        if owner == my_client_id:
            messagebox.showinfo("Información", "No puedes solicitar administrar tu propio tópico")
            return
        
        # CORREGIR: Definir callback con 4 parámetros
        def admin_request_callback(success, message, error_code, topic_name):
            self.root.after(0, lambda: self._show_admin_request_result(success, message, error_code, topic_name))
        
        success = self.client.request_admin_status(topic, owner, callback=admin_request_callback)
        if success:
            self.status_label.config(text="Enviando solicitud de administración...")
        else:
            messagebox.showerror("Error", "No se pudo enviar la solicitud")

    def setup_admin_notifications(self):
        """Configura las notificaciones para administración."""
        print("🔧 [GUI DEBUG] Configurando notificaciones administrativas...")
        if self.client and self.client.connected:
            print("✅ [GUI DEBUG] Cliente conectado, registrando handler...")
            
            def admin_callback(notification):
                print(f"🎯 [GUI CALLBACK] Notificación recibida: {notification}")
                # Ejecutar en el hilo principal de Tkinter
                self.root.after(0, lambda: self.on_admin_notification(notification))
            
            result = self.client.register_admin_notification_handler(admin_callback)
            print(f"🔧 [GUI DEBUG] Resultado del registro: {result}")
            
            if result:
                print("✅ [GUI DEBUG] Notificaciones configuradas correctamente")
            else:
                print("❌ [GUI DEBUG] Error configurando notificaciones")
                
        else:
            print("❌ [GUI DEBUG] Cliente no conectado")

    def on_admin_notification(self, data):
        """Maneja notificaciones administrativas recibidas."""
        try:
            print(f"🔔 [GUI NOTIFICATION] Procesando notificación: {data}")
            
            # Si es un comando para sensor (nuevo caso)
            if "command" in data and data["command"] == "set_sensor":
                print(f"🔧 Comando de sensor recibido: {data['sensor_name']} = {data['active']}")
                
                if self.das and self.das.running:
                    # Convertir al formato que espera el ESP32
                    esp_command = {
                        "command": f"set_{data['sensor_name']}",
                        "value": 1 if data["active"] else 0
                    }
                    
                    # Enviar el comando al ESP32 a través del DAS
                    success = self.das.send_command(esp_command)
                    if success:
                        print(f"✅ Comando enviado al ESP32: {data['sensor_name']} {'activado' if data['active'] else 'desactivado'}")
                        # Actualizar interfaz si lo necesitas
                        if hasattr(self, 'update_sensor_status'):
                            self.update_sensor_status(data['sensor_name'], data['active'])
                    else:
                        print(f"❌ Error enviando comando al ESP32")
                else:
                    print(f"⚠️ No hay DAS configurado o no está funcionando")
                return
            
            notification_type = data.get("type")
            if notification_type == "request":
                topic_name = data.get("topic_name", "")
                requester_id = data.get("requester_id", "")
                msg = f"Has recibido una nueva solicitud de administración para el tópico '{topic_name}' de '{requester_id}'."
                self.show_admin_notification("Nueva solicitud de administración", msg)
                return

                
            # Resto del código existente para otros tipos de notificaciones
            notification_type = data.get("type")
            print(f"🔔 [GUI NOTIFICATION] Tipo: {notification_type}")
            
            if notification_type == "request":
                # Código existente para solicitudes...
                pass
            else:
                print(f"❌ [GUI NOTIFICATION] Tipo de notificación no reconocido: {notification_type}")
        except Exception as e:
            print(f"❌ [GUI NOTIFICATION] Error procesando notificación: {e}")
            import traceback
            traceback.print_exc()
        
    def show_admin_notification(self, title, message):
        """Muestra una ventana de notificación flotante."""
        # Crear ventana flotante
        popup = tk.Toplevel(self.root)
        popup.title("Notificación")
        popup.geometry("300x150+50+50")
        popup.attributes("-topmost", True)
        
        # Configurar ventana como modal
        popup.transient(self.root)
        popup.grab_set()
        
        # Contenido
        ttk.Label(popup, text=title, font=("Helvetica", 12, "bold")).pack(pady=(15,5), padx=10)
        ttk.Label(popup, text=message, wraplength=280).pack(pady=10, padx=10)
        ttk.Button(popup, text="Ver ahora", command=lambda: self._view_admin_requests(popup)).pack(pady=5)
        ttk.Button(popup, text="Más tarde", command=popup.destroy).pack(pady=5)
        
        # Reproducir sonido (opcional)
        try:
            import winsound
            winsound.MessageBeep()
        except:
            pass

    def _view_admin_requests(self, popup=None):
        """Muestra la pestaña de solicitudes administrativas."""
        # Cerrar notificación si existe
        if popup:
            popup.destroy()
        
        # Cambiar a la pestaña de administración
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text").startswith("Administración"):
                self.notebook.select(i)
                break
        
        # Refrescar las solicitudes
        self.refresh_admin_requests()
        
    def _update_admin_tab_badge(self):
        """Actualiza el contador de notificaciones en la pestaña de admin."""
        # Obtener cantidad de solicitudes pendientes
        count = 0
        if self.client and self.client.connected:
            try:
                requests = self.client.get_admin_requests()
                count = len(requests)
            except:
                pass
        
        # Actualizar nombre de la pestaña
        for i in range(self.notebook.index("end")):
            tab_text = self.notebook.tab(i, "text") 
            if tab_text.startswith("Administración"):
                if count > 0:
                    self.notebook.tab(i, text=f"Administración ({count})")
                else:
                    self.notebook.tab(i, text="Administración")
                break

    def approve_admin_request(self):
        """Aprueba la solicitud de administrador seleccionada."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
                
        selected_items = self.requests_tree.selection()
        if not selected_items:
            messagebox.showinfo("Selección requerida", "Selecciona una solicitud primero")
            return
        
        item = selected_items[0]
        values = self.requests_tree.item(item, 'values')
        if not values or len(values) < 3:
            messagebox.showerror("Error", "Formato de solicitud inválido")
            return
            
        # Los valores están en el orden definido en las columnas: id, requester, topic, timestamp
        request_id = values[0]  
        requester_id = values[1]
        topic_name = values[2]
        
        confirm = messagebox.askyesno(
            "Confirmar",
            f"¿Realmente deseas aprobar a {requester_id} como administrador de '{topic_name}'?"
        )
        
        if confirm:
            try:
                success = self.client.respond_to_admin_request(request_id, topic_name, requester_id, True)
                if success:
                    messagebox.showinfo("Éxito", f"Se ha aprobado a {requester_id} como administrador")
                    self.refresh_admin_requests()
                    self._update_admin_tab_badge()
                else:
                    messagebox.showerror("Error", "No se pudo aprobar la solicitud")
            except Exception as e:
                messagebox.showerror("Error", f"Error al aprobar solicitud: {str(e)}")
                
    def reject_admin_request(self):
        """Rechaza la solicitud de administrador seleccionada."""
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
                
        selected_items = self.requests_tree.selection()
        if not selected_items:
            messagebox.showinfo("Selección requerida", "Selecciona una solicitud primero")
            return
        
        item = selected_items[0]
        values = self.requests_tree.item(item, 'values')
        if not values or len(values) < 3:
            messagebox.showerror("Error", "Formato de solicitud inválido")
            return
            
        # Los valores están en el orden definido en las columnas: id, requester, topic, timestamp
        request_id = values[0]  
        requester_id = values[1]
        topic_name = values[2]
        
        confirm = messagebox.askyesno(
            "Confirmar",
            f"¿Realmente deseas rechazar la solicitud de {requester_id} para administrar '{topic_name}'?"
        )
        
        if confirm:
            try:
                success = self.client.respond_to_admin_request(request_id, topic_name, requester_id, False)
                if success:
                    messagebox.showinfo("Éxito", f"Se ha rechazado la solicitud de {requester_id}")
                    self.refresh_admin_requests()
                    self._update_admin_tab_badge()
                else:
                    messagebox.showerror("Error", "No se pudo rechazar la solicitud")
            except Exception as e:
                messagebox.showerror("Error", f"Error al rechazar solicitud: {str(e)}")
        
    def on_admin_topic_selected(self, event):
        """Maneja la selección de un tópico administrado."""
        selection = self.admin_topics_listbox.curselection()
        if not selection:
            return
            
        # Similar a on_topic_selected pero para tópicos administrados
        # Llena el TreeView de sensores con sus estados

    def set_admin_sensor_status(self, active):
        """Activa o desactiva un sensor como administrador."""
        selection = self.admin_sensors_tree.selection()
        if not selection:
            messagebox.showinfo("Selección requerida", "Selecciona un sensor primero")
            return
        
        # Obtener sensor seleccionado
        item = selection[0]
        sensor_name = self.admin_sensors_tree.item(item, "values")[0]
        
        # Obtener tópico
        topic_selection = self.admin_topics_listbox.curselection()
        if not topic_selection:
            messagebox.showinfo("Selección requerida", "Selecciona un tópico primero")
            return
        
        topic_item = self.admin_topics_listbox.get(topic_selection[0])
        # Extraer nombre del tópico y dueño
        
        # Enviar configuración
        if self.client and self.client.connected:
            success = self.client.set_sensor_status(topic_name, sensor_name, active)
            if success:
                # Actualizar vista
                status = "Activo" if active else "Inactivo"
                self.admin_sensors_tree.item(item, values=(sensor_name, status))
                messagebox.showinfo("Éxito", f"Sensor {sensor_name} ahora está {status.lower()}")
            else:
                messagebox.showerror("Error", "No se pudo cambiar el estado del sensor")

    def request_topic_admin(self):
        """Solicita ser administrador del tópico seleccionado."""
        selection = self.topics_listbox.curselection()
        if not selection:
            messagebox.showinfo("Información", "Selecciona un tópico primero")
            return
        
        selected_index = selection[0]
        selected_item = self.topics_listbox.get(selected_index)
        topic_id = selected_item.split(":")[0].strip()
        
        try:
            topic = self.db.get_topic(topic_id)
            if not topic:
                messagebox.showinfo("Error", "No se pudo obtener información del tópico")
                return
                
            topic_name = topic["name"]
            owner_id = topic["owner_client_id"]
            
            # Verificar que no soy el dueño
            my_client_id = self.db.get_client_id()
            if owner_id == my_client_id:
                messagebox.showinfo("Información", "No puedes solicitar administrar tu propio tópico")
                return
            
            # Confirmar solicitud
            confirm = messagebox.askyesno(
                "Confirmar solicitud",
                f"¿Deseas solicitar ser administrador de '{topic_name}' (dueño: {owner_id})?"
            )
            
            if not confirm:
                return
            
            # Enviar solicitud
            if self.client and self.client.connected:
                # CORREGIR: Callback con 4 parámetros
                def admin_request_callback(success, message, error_code, topic_name):
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Éxito", f"Solicitud enviada al dueño {owner_id}"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Error", f"No se pudo enviar la solicitud: {message}"))
                
                success = self.client.request_admin_status(topic_name, owner_id, callback=admin_request_callback)
                if not success:
                    messagebox.showerror("Error", "No se pudo enviar la solicitud")
            else:
                messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al solicitar administración: {str(e)}")     
                
    def refresh_subscribable_topics(self):
        """Actualiza la lista de tópicos disponibles para solicitar administración"""
        try:
            # Limpiar la lista primero
            self.admin_subscribable_topics_listbox.delete(0, tk.END)
            
            # Obtener las suscripciones del usuario
            subscriptions = self.db.get_subscriptions()
            
            # Mostrar mensaje si no hay suscripciones
            if not subscriptions:
                self.admin_subscribable_topics_listbox.insert(tk.END, "No hay suscripciones activas")
                return
                    
            # Obtener mi ID de cliente
            my_client_id = self.db.get_client_id()
            if not my_client_id:
                self.admin_subscribable_topics_listbox.insert(tk.END, "Error: ID de cliente no configurado")
                return
            
            # Debug para verificar valores
            print(f"ID de cliente: {my_client_id}")
            print(f"Suscripciones encontradas: {len(subscriptions)}")
            for sub in subscriptions:
                print(f"- Suscripción: {sub}")
                
            # Para cada suscripción, verificar si el usuario es dueño del tópico
            found_topics = False
            for sub in subscriptions:
                topic = sub.get('topic')
                owner_id = sub.get('source_client_id')
                
                if not topic or not owner_id:
                    continue
                    
                # Añadir todos los tópicos a los que estamos suscritos
                # - No necesitamos filtrar por dueño ya que eso se verificará al solicitar
                self.admin_subscribable_topics_listbox.insert(tk.END, f"{topic} ({owner_id})")
                found_topics = True
                        
            if not found_topics:
                self.admin_subscribable_topics_listbox.insert(tk.END, "No hay tópicos disponibles para solicitar administración")
                    
        except Exception as e:
            self.admin_subscribable_topics_listbox.delete(0, tk.END)
            self.admin_subscribable_topics_listbox.insert(tk.END, f"Error: {str(e)}")
            print(f"Error al actualizar tópicos disponibles para administración: {e}")
            import traceback
            traceback.print_exc()
        
    def request_admin_for_selected(self):
        """Solicita administración para el tópico seleccionado en la lista"""
        selection = self.admin_subscribable_topics_listbox.curselection()
        if not selection:
            messagebox.showinfo("Selección requerida", "Selecciona un tópico primero")
            return
        
        selected_item = self.admin_subscribable_topics_listbox.get(selection[0])
        # Formato esperado: "topic (owner_id)"
        match = re.match(r'^(.+)\s+\((.+)\)$', selected_item)
        if not match:
            messagebox.showerror("Error", "Formato de tópico inválido")
            return
            
        topic_name = match.group(1)
        owner_id = match.group(2)
        
        # Verificar que no soy el dueño
        my_client_id = self.db.get_client_id()
        if owner_id == my_client_id:
            messagebox.showinfo("Información", "No puedes solicitar administrar tu propio tópico")
            return
            
        if not self.client or not self.client.connected:
            messagebox.showwarning("No conectado", "Debes conectarte al broker primero")
            return
            
        confirm = messagebox.askyesno(
            "Confirmar solicitud",
            f"¿Deseas solicitar ser administrador de '{topic_name}' (dueño: {owner_id})?"
        )
        
        if confirm:
            try:
                # CORREGIR: Callback con 4 parámetros
                def admin_request_callback(success, message, error_code, topic_name):
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Éxito", f"Solicitud enviada al dueño {owner_id}"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Error", f"No se pudo enviar la solicitud: {message}"))
                
                success = self.client.request_admin_status(topic_name, owner_id, callback=admin_request_callback)
                if not success:
                    messagebox.showerror("Error", "No se pudo enviar la solicitud")
            except Exception as e:
                messagebox.showerror("Error", f"Error al solicitar administración: {str(e)}")
                
    def mark_sensor_as_activable(self):
        """
        Marca un sensor como activable/controlable por administradores.
        """
        if not self.client or not self.client.connected:
            messagebox.showwarning("Advertencia", "No hay conexión con el broker")
            return

        # Obtener sensor seleccionado
        sensor_name = self.sensor_to_add_var.get()
        if not sensor_name:
            messagebox.showwarning("Advertencia", "Selecciona un sensor primero")
            return

        # Obtener tópico seleccionado
        topic_selection = self.topics_listbox.curselection()
        if not topic_selection:
            messagebox.showwarning("Advertencia", "Selecciona un tópico primero")
            return

        # Solo permite marcar en el primer tópico seleccionado (puedes hacer un ciclo si quieres varios)
        selected_index = topic_selection[0]
        selected_item = self.topics_listbox.get(selected_index)
        topic_id = selected_item.split(":")[0].strip()
        topic = self.db.get_topic(topic_id)
        if not topic:
            messagebox.showwarning("Advertencia", "No se pudo obtener el tópico")
            return
        topic_name = topic["name"]

        # Confirmar acción
        result = messagebox.askyesno(
            "Confirmar",
            f"¿Desea marcar el sensor '{sensor_name}' como activable en el tópico '{topic_name}'?\n\n"
            "Los administradores podrán activar/desactivar este sensor remotamente."
        )
        if not result:
            return

        # Llamar al método del cliente
        success = self.client.mark_sensor_as_activable(topic_name, sensor_name, True)
        if success:
            messagebox.showinfo("Éxito", f"Sensor '{sensor_name}' marcado como activable en '{topic_name}'")
        else:
            messagebox.showerror("Error", "No se pudo marcar el sensor como activable")

    def show_sensor_notification(self, sensor_data):
        print(f"DEBUG: show_sensor_notification llamado con: {sensor_data}")

        """Muestra una notificación cuando cambia el estado de un sensor."""
        try:
            topic_name = sensor_data.get("topic_name", "desconocido")
            sensor_name = sensor_data.get("sensor_name", "desconocido")
            active = sensor_data.get("active", False)
            estado = "activado" if active else "desactivado"
            
            # Crear ventana emergente
            popup = tk.Toplevel(self.root)
            popup.title("Estado de Sensor Actualizado")
            popup.geometry("320x180+50+50")
            popup.attributes("-topmost", True)
            popup.transient(self.root)
            
            # Añadir contenido
            frame = ttk.Frame(popup, padding=15)
            frame.pack(fill="both", expand=True)
            
            # Icono según estado
            icon_label = ttk.Label(frame, text="✅" if active else "❌", font=("Helvetica", 24))
            icon_label.pack(pady=(0, 10))
            
            # Mensaje principal
            ttk.Label(frame, text=f"Sensor {sensor_name}", 
                    font=("Helvetica", 12, "bold")).pack(pady=2)
            ttk.Label(frame, text=f"ha sido {estado} exitosamente", 
                    font=("Helvetica", 11)).pack(pady=2)
            ttk.Label(frame, text=f"Tópico: {topic_name}", 
                    font=("Helvetica", 10), foreground="gray").pack(pady=2)
            
            # Botón de cerrar
            ttk.Button(frame, text="Aceptar", command=popup.destroy).pack(pady=(10, 0))
            
            # Auto-cerrar después de 10 segundos
            popup.after(10000, popup.destroy)
            
        except Exception as e:
            print(f"Error mostrando notificación de sensor: {e}")

    def on_connection_state_changed(self, connected: bool):
        """
        Callback para manejar cambios de estado de conexión.
        Se ejecuta cuando el broker termina la conexión o cuando se conecta.
        
        Args:
            connected: True si está conectado, False si se desconectó
        """
        def update_ui():
            if connected:
                print("🔗 GUI: Conexión establecida")
                self.connected = True
                self.connect_btn.config(state="disabled")
                self.disconnect_btn.config(state="normal")
                self.status_var.set("Conectado")
                self.status_label.config(text="Conectado al broker correctamente")
            else:
                print("🔌 GUI: Conexión perdida - actualizando UI")
                self.connected = False
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
                self.status_var.set("Desconectado")
                self.status_label.config(text="Conexión perdida con el broker")
                
                # Show notification to user about lost connection
                messagebox.showwarning(
                    "Conexión Perdida", 
                    "Se ha perdido la conexión con el broker. Puede volver a conectarse usando el botón 'Conectar'."
                )
        
        # Schedule UI update in the main thread
        self.root.after(0, update_ui)

    def is_window_alive(self):
        try:
            return bool(self.root.winfo_exists())
        except:
            return False

def main():
    root = tk.Tk()
    app = TinyMQGUI(root)
    def on_closing():
        app.running = False
        try:
            if app.das:
                try:
                    app.das.stop()
                except Exception:
                    pass  # Ignorar cualquier error al detener DAS
            if app.client and app.client.connected:
                try:
                    app.client.disconnect()
                except Exception:
                    pass  # Ignorar cualquier error al desconectar
        except Exception:
            pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        # Permitir cerrar con Ctrl+C sin traceback feo
        print("Cerrando aplicación por KeyboardInterrupt...")
        on_closing()


if __name__ == "__main__":
    main()