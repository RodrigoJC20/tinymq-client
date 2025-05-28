"""
TinyMQ client implementation.

This module provides the client functionality for the TinyMQ protocol.
"""
import json
import socket
import threading
import time
from tkinter import messagebox
from typing import Dict, Callable, Optional, List, Any

from .packet import Packet, PacketType


class Client:
    """TinyMQ client implementation."""
    
    def __init__(self, client_id: str, host: str = "localhost", port: int = 1505):
        """
        Initialize a TinyMQ client.
        
        Args:
            client_id: Unique identifier for this client
            host: Broker hostname or IP address
            port: Broker port
        """
        self.client_id = client_id
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        
        # Inicializar variables para handlers y callbacks
        self._admin_notify_callback = None
        self._admin_result_callback = None
        self._admin_request_callback = None
        self._admin_resign_callback = None
        self._sensor_status_callback = None  # AÑADIR ESTA LÍNEA
        self._connection_state_callback = None  # NEW: Callback for connection state changes

        
        # Inicializar estructuras de datos para handlers temporales
        self._temp_handlers = {}
        self._temp_handlers_lock = threading.Lock()
        self._requesting_published_topics = False
        self._requesting_admin_topics = False
        self._cached_admin_requests = []
        
        # Resto de configuraciones
        self.topic_handlers: Dict[str, Callable[[str, bytes], None]] = {}
        self.read_thread: Optional[threading.Thread] = None
        self.running = False
        self._recv_buffer = bytearray()
        self._recv_lock = threading.Lock()
    
    def create_topic(self, topic: str, callback: Callable[[str, bytes], None] = None) -> bool:
        """Crea un tópico inmediatamente."""
        if not self.connected:
            print("No conectado al broker.")
            return False

        try:
            # Primero suscribirse al tópico
            if callback:
                success = self.subscribe(topic, callback)
                if not success:
                    return False
            
            # Luego notificar al broker de la creación
            create_message = json.dumps({
                "__topic_create": True,
                "client_id": self.client_id,
                "topic_name": topic,
                "timestamp": int(time.time())
            })
            
            return self.publish(topic, create_message)
            
        except Exception as e:
            print(f"Error creando tópico: {e}")
            return False
        
    def connect(self) -> bool:
        """Conecta al broker con timeout."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Configurar timeout de 5 segundos para la conexión
            self.socket.settimeout(5.0)  
            
            self.socket.connect((self.host, self.port))
            # Restaurar el comportamiento normal después de conectar
            self.socket.settimeout(None)
        
            # Send CONN packet with client ID
            conn_packet = Packet(
                packet_type=PacketType.CONN,
                payload=self.client_id.encode('utf-8')
            )
            self._send_packet(conn_packet)
            
            # Start the read thread
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
            
            # Wait for CONNACK
            start_time = time.time()
            while not self.connected and time.time() - start_time < 5:
                time.sleep(0.1)
            
            return self.connected
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the TinyMQ broker."""
        self.running = False
        if self.read_thread:
            # Only attempt to join the thread if we're not in the read thread itself
            current_thread = threading.current_thread()
            if current_thread != self.read_thread:
                self.read_thread.join(timeout=1.0)
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        was_connected = self.connected
        self.connected = False
        # NEW: Notify about connection state change if we were connected
        if was_connected:
            self._notify_connection_state_change(False)
    
    def publish(self, topic: str, message: str) -> bool:
        """
        Publish a message to a topic.
        
        Args:
            topic: Topic to publish to
            message: Message to publish
            
        Returns:
            True if the message was sent, False otherwise.
        """
        if not self.connected:
            return False
        
        try:
            message_dict = json.loads(message)

            # Ahora sí puedes acceder a 'cliente'
            broker_topic = f"{message_dict['cliente']}/{topic}" if "cliente" in message_dict else f"{self.client_id}/{topic}"
            wrapped_topic = json.dumps([broker_topic])

            broker_topic_bytes = wrapped_topic.encode('utf-8')
            topic_length = len(broker_topic_bytes)
            
            if topic_length > 255:
                print(f"Error: Topic '{broker_topic}' is too long (max 255 bytes).")
                return False
            
            message_bytes = message.encode('utf-8')
            
            payload = bytes([topic_length]) + broker_topic_bytes + message_bytes
            
            packet = Packet(packet_type=PacketType.PUB, payload=payload)
            # Print packet details
            print(f"Sending packet: Type={packet.packet_type.name}, Flags={packet.flags}, Payload Length={len(packet.payload)}")
            result = self._send_packet(packet)
            return result
        except Exception as e:
            print(f"Publish error: {e}")
            return False
    
    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> bool:
        """
        Subscribe to a topic.
        
        Args:
            topic: Topic to subscribe to
            callback: Function to call when a message is received
            
        Returns:
            True if the subscription request was sent, False otherwise.
        """
        if not self.connected:
            return False
        
        try:
            # Format: ["topic_name"]
            payload = json.dumps([topic]).encode('utf-8')
            packet = Packet(packet_type=PacketType.SUB, payload=payload)
            
            if self._send_packet(packet):
                self.topic_handlers[topic] = callback
                return True
            return False
        except Exception as e:
            print(f"Subscribe error: {e}")
            return False
    
    def unsubscribe(self, topic: str) -> bool:
        """
        Unsubscribe from a topic.
        
        Args:
            topic: Topic to unsubscribe from
            
        Returns:
            True if the unsubscribe request was sent, False otherwise.
        """
        if not self.connected:
            return False
        
        try:
            # Format: ["topic_name"]
            payload = json.dumps([topic]).encode('utf-8')
            packet = Packet(packet_type=PacketType.UNSUB, payload=payload)
            
            if self._send_packet(packet):
                if topic in self.topic_handlers:
                    del self.topic_handlers[topic]
                return True
            return False
        except Exception as e:
            print(f"Unsubscribe error: {e}")
            return False
    
    def _send_packet(self, packet: Packet) -> bool:
        """Send a packet to the broker."""
        if not self.socket:
            return False
        
        try:
            data = packet.serialize()
            self.socket.sendall(data)
            return True
        except Exception as e:
            print(f"Send error: {e}")
            self.disconnect()
            return False
    
    def _read_loop(self) -> None:
        """Read packets from the broker."""
        while self.running and self.socket:
            try:
                # Read some data
                data = self.socket.recv(4096)
                if not data:
                    # Connection closed
                    break
                # Append to buffer
                with self._recv_lock:
                    self._recv_buffer.extend(data)
                    buffer = self._recv_buffer.copy()
                
                # Process packets
                consumed = 0
                while consumed < len(buffer):
                    packet, bytes_consumed = Packet.deserialize(buffer[consumed:])
                    if packet is None:
                        # Need more data
                        break
                    self._handle_packet(packet)
                    consumed += bytes_consumed
                
                # Remove processed data
                with self._recv_lock:
                    self._recv_buffer = self._recv_buffer[consumed:]
                
            except Exception as e:
                #print(f"Read error: {e}")
                break
        
        # Ensure we're disconnected on error, but don't call disconnect() directly
        # as it would try to join the current thread
        self.running = False
        self.connected = False
        # NEW: Notify about connection state change
        self._notify_connection_state_change(False)
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def _handle_packet(self, packet: Packet) -> None:
        """Handle a received packet."""
        
        print(f"DEBUG: Recibido paquete tipo {packet.packet_type.name}, tamaño payload: {len(packet.payload)} bytes")

        # PRIMERO: Verificar si hay un handler temporal para este tipo de paquete
        if packet.packet_type in self._temp_handlers:
            try:
                handler = self._temp_handlers[packet.packet_type]
                print(f"[DEBUG] Ejecutando handler temporal para {packet.packet_type.name}")
                
                # CORRECCIÓN: Verificar la signatura del handler y llamarlo correctamente
                import inspect
                sig = inspect.signature(handler)
                
                if len(sig.parameters) == 2:
                    # Handler espera (packet_type, payload)
                    result = handler(packet.packet_type, packet.payload)
                else:
                    # Handler legacy o diferente signatura
                    result = handler(packet)
                
                # Solo remover si el handler retorna True o no retorna nada
                if result is not False:
                    print(f"[DEBUG] Removiendo handler temporal usado para {packet.packet_type.name}")
                    # CORRECCIÓN: Verificar que el handler aún existe antes de eliminarlo
                    if packet.packet_type in self._temp_handlers:
                        del self._temp_handlers[packet.packet_type]
                    return  # IMPORTANTE: salir después de procesar con handler temporal
                
            except Exception as e:
                print(f"Error en handler temporal para {packet.packet_type.name}: {e}")
                import traceback
                traceback.print_exc()
                
                # CORRECCIÓN: Verificar que el handler existe antes de eliminarlo
                if packet.packet_type in self._temp_handlers:
                    del self._temp_handlers[packet.packet_type]
                # No hacer return aquí para que se procese normalmente

        # SEGUNDO: Manejo normal de paquetes (resto del código igual)
        if packet.packet_type == PacketType.CONNACK:
            self.connected = True
            # NEW: Notify about connection state change
            self._notify_connection_state_change(True)
            print("✅ Conectado al broker")
        
        elif packet.packet_type == PacketType.PUBACK:
            print(f"DEBUG: PacketType.PUBACK")
            pass
        
        elif packet.packet_type == PacketType.PUBACK:
            print(f"DEBUG: PacketType.PUBACK")
            pass
            
        elif packet.packet_type == PacketType.SUBACK:
            print(f"DEBUG: PacketType.SUBACK")
            pass
            
        elif packet.packet_type == PacketType.UNSUBACK:
            print(f"DEBUG: PacketType.UNSUBACK")
            pass
        
        
        
        elif packet.packet_type == PacketType.ADMIN_REQ_ACK:
            self._handle_admin_request_response(packet)
            
        elif packet.packet_type == PacketType.PUB:
            try:
                data = json.loads(packet.payload.decode('utf-8'))
                topic = data.get('topic', '')
                message = data.get('message', b'')

                # Normaliza el nombre del tópico para el handler
                topic_normalized = topic
                if topic.startswith('["') and topic.endswith('"]'):
                    topic_normalized = topic[2:-2]

                # Decodifica el mensaje si es string JSON
                if isinstance(message, str):
                    try:
                        message_obj = json.loads(message)
                    except Exception:
                        message_obj = message
                else:
                    message_obj = message

                # Debug
                #print(f"DEBUG: Handler keys: {list(self.topic_handlers.keys())}")
                #print(f"DEBUG: Buscando handler para: '{topic}' o '{topic_normalized}'")

                # Llama al handler correcto
                if topic in self.topic_handlers:
                    self.topic_handlers[topic](topic, message_obj)
                elif topic_normalized in self.topic_handlers:
                    self.topic_handlers[topic_normalized](topic_normalized, message_obj)
                else:
                    print(f"WARNING: No handler registrado para '{topic}' ni '{topic_normalized}'")
            except json.JSONDecodeError:
                print(f"Invalid JSON in PUB packet: {packet.payload}")
            except Exception as e:
                print(f"Error handling PUB packet: {e}")
        
        elif packet.packet_type == PacketType.SENSOR_STATUS_RESP:
            try:
                print("DEBUG: Recibido SENSOR_STATUS_RESP")
                payload_str = packet.payload.decode('utf-8')
                data = json.loads(payload_str)
                print(f"DEBUG: Contenido de SENSOR_STATUS_RESP: {data}")
                if self._sensor_status_callback:
                    print("DEBUG: Llamando a _sensor_status_callback")
                    self._sensor_status_callback(data)
                else:
                    print("⚠️ No hay callback registrado para notificaciones de estado de sensor")
            except Exception as e:
                print(f"❌ Error procesando respuesta de estado de sensor: {e}")
    
        elif packet.packet_type == PacketType.ADMIN_RESP:
            try:
                response_data = json.loads(packet.payload.decode('utf-8'))
                print(f"[ADMIN] Respuesta administrativa recibida: {response_data}")
            except Exception as e:
                print(f"Error procesando respuesta administrativa: {e}")
    
        # CASOS QUE PUEDEN SER MANEJADOS POR HANDLERS TEMPORALES O NORMALMENTE
        elif packet.packet_type == PacketType.TOPIC_RESP:
            print(f"[DEBUG] Recibido paquete TOPIC_RESP estándar")
            
        elif packet.packet_type == PacketType.ADMIN_LIST_RESP:
            print(f"[DEBUG] Recibido paquete ADMIN_LIST_RESP")
            
        elif packet.packet_type == PacketType.MY_TOPICS_RESP:
            print(f"[DEBUG] Recibido paquete MY_TOPICS_RESP - no manejado")
            
        elif packet.packet_type == PacketType.MY_ADMIN_RESP:
            print(f"[DEBUG] Recibido paquete MY_ADMIN_RESP - no manejado")
            
        elif packet.packet_type == PacketType.MY_ADMIN_TOPICS_RESP:
            print(f"[DEBUG] Recibido paquete MY_ADMIN_TOPICS_RESP - no manejado")
            
        elif packet.packet_type == PacketType.ADMIN_RESIGN_ACK:
            self._handle_admin_resign_response(packet)
            
        elif packet.packet_type == PacketType.TOPIC_SENSORS_RESP:
            print(f"[DEBUG] Recibido paquete TOPIC_SENSORS_RESP - no manejado")
            

        elif packet.packet_type == PacketType.ADMIN_NOTIFY:
            try:
                print("DEBUG: Recibido ADMIN_NOTIFY")
                notification_data = json.loads(packet.payload.decode('utf-8'))
                print(f"DEBUG: Contenido de ADMIN_NOTIFY: {notification_data}")
                if self._admin_notify_callback:
                    print("DEBUG: Llamando a _admin_notify_callback")
                    self._admin_notify_callback(notification_data)
            except Exception as e:
                print(f"Error procesando notificación administrativa: {e}")

                
        elif packet.packet_type == PacketType.ADMIN_RESULT:
            try:
                result_data = json.loads(packet.payload.decode('utf-8'))
                print(f"[ADMIN] Resultado recibido: {result_data}")
                
                if self._admin_result_callback:
                    self._admin_result_callback(result_data)
            except Exception as e:
                print(f"Error procesando resultado administrativo: {e}")
                
        else:
            print(f"[WARNING] Tipo de paquete no manejado: {packet.packet_type.name}")
            
    def register_sensor_status_callback(self, callback):
        """
        Registra un callback que será llamado cuando el estado de un sensor cambie.
        
        Args:
            callback: Función que recibirá los datos de confirmación del cambio
        """
        self._sensor_status_callback = callback
        print(f"✅ Callback de estado de sensor registrado")
        
    def register_connection_state_callback(self, callback):
        """
        Registra un callback que será llamado cuando el estado de conexión cambie.
        
        Args:
            callback: Función que recibirá el nuevo estado de conexión (True/False)
        """
        self._connection_state_callback = callback

    def _notify_connection_state_change(self, connected: bool):
        """
        Notifica un cambio en el estado de conexión.
        
        Args:
            connected: Nuevo estado de conexión
        """
        if self._connection_state_callback:
            try:
                self._connection_state_callback(connected)
            except Exception as e:
                print(f"Error in connection state callback: {e}")
            
    def get_my_admin_topics(self) -> List[Dict[str, Any]]:
        """
        Obtiene los tópicos donde soy administrador.
        
        Returns:
            Lista de tópicos donde el cliente es administrador
        """
        if not self.connected:
            return []
        
        # PREVENIR SOLICITUDES DUPLICADAS
        if self._requesting_admin_topics:
            print(f"[DEBUG] Solicitud de admin topics ya en progreso, ignorando...")
            return []
                
        try:
            self._requesting_admin_topics = True  # Flag para prevenir duplicados
            topics = []
            response_received = threading.Event()
            response_processed = False  # Flag adicional
            
            def handle_response(packet_type, payload):
                nonlocal topics, response_processed
                
                # Evitar procesamiento múltiple
                if response_processed:
                    print(f"[DEBUG] Respuesta ya procesada, ignorando...")
                    return
                    
                print(f"[DEBUG] Handler MY_ADMIN_TOPICS_RESP ejecutado, payload size: {len(payload) if payload else 0}")
                if payload:
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        topics = data if isinstance(data, list) else []
                        print(f"[DEBUG] Tópicos admin parseados: {len(topics)} encontrados")
                        response_processed = True
                    except Exception as e:
                        print(f"[ERROR] Error parseando respuesta MY_ADMIN_TOPICS: {e}")
                        topics = []
                else:
                    print(f"[DEBUG] Payload vacío en MY_ADMIN_TOPICS_RESP")
                    topics = []
                
                response_received.set()
            
            print(f"[DEBUG] Registrando handler temporal para MY_ADMIN_TOPICS_RESP")
            self._register_temp_packet_handler(PacketType.MY_ADMIN_TOPICS_RESP, handle_response)
            
            # Enviar solicitud
            print(f"[DEBUG] Enviando solicitud MY_ADMIN_TOPICS_REQ")
            packet = Packet(PacketType.MY_ADMIN_TOPICS_REQ, 0, b'')
            if self._send_packet(packet):
                print(f"[DEBUG] Esperando respuesta...")
                if response_received.wait(timeout=5.0):  # Reducir timeout
                    print(f"[DEBUG] Respuesta recibida: {len(topics)} tópicos")
                    return topics
                else:
                    print(f"[ERROR] Timeout esperando MY_ADMIN_TOPICS_RESP")
            else:
                print(f"[ERROR] Error enviando MY_ADMIN_TOPICS_REQ")
            
            return []
        except Exception as e:
            print(f"Error getting admin topics: {e}")
            return []
        finally:
            with self._temp_handlers_lock:
                if PacketType.MY_ADMIN_TOPICS_RESP in self._temp_handlers:
                    print(f"[DEBUG] Limpiando handler temporal MY_ADMIN_TOPICS_RESP")
                    del self._temp_handlers[PacketType.MY_ADMIN_TOPICS_RESP]
            self._requesting_admin_topics = False
            
            
    def resign_admin_status(self, topic_name: str, callback=None) -> bool:
        """
        Renuncia a la administración de un tópico.
        
        Args:
            topic_name: Nombre del tópico
            callback: Función callback(success, message) para recibir respuesta
            
        Returns:
            True si la solicitud se envió correctamente
        """
        if not self.connected:
            if callback:
                callback(False, "No hay conexión con el broker")
            return False
        
        try:
            # Guardar callback para la respuesta
            if callback:
                self._admin_resign_callback = callback
            
            # Enviar solicitud de renuncia
            topic_bytes = topic_name.encode('utf-8')
            packet = Packet(PacketType.ADMIN_RESIGN, 0, topic_bytes)
            return self._send_packet(packet)
        except Exception as e:
            if callback:
                callback(False, f"Error enviando renuncia: {str(e)}")
            return False
        
        
    def get_topic_sensors_config(self, topic_name: str) -> List[Dict[str, Any]]:
        """Obtiene la configuración de sensores de un tópico."""
        print(f"🔍 DEBUG: Solicitando sensores para tópico: {topic_name}")
        if not self.connected:
            print("❌ No conectado al broker")
            return []
                
        try:
            sensors = []
            response_received = threading.Event()
            
            def handle_response(packet_type, payload):
                nonlocal sensors
                try:
                    if payload:
                        # Debug del payload recibido
                        payload_str = payload.decode('utf-8')
                        print(f"🔍 DEBUG: Payload recibido: {payload_str[:200]}...")
                        
                        data = json.loads(payload_str)
                        print(f"🔍 DEBUG: JSON parseado: {json.dumps(data, indent=2)}")
                        
                        sensors_list = data.get('sensors', [])
                        print(f"🔍 DEBUG: Lista de sensores extraída: {json.dumps(sensors_list, indent=2)}")
                        
                        # Asegurarse de que cada sensor tenga todos los campos necesarios
                        for i, sensor in enumerate(sensors_list):
                            print(f"🔍 DEBUG: Procesando sensor {i}: {sensor}")
                            print(f"🔍 DEBUG: Tipos de datos - name: {type(sensor.get('name'))}, activable: {type(sensor.get('activable'))}, active: {type(sensor.get('active'))}")
                            
                            if "activable" not in sensor:
                                sensor["activable"] = "false"  # Valor por defecto
                                print(f"🔍 DEBUG: Agregado campo 'activable' por defecto")
                            else:
                                print(f"🔍 DEBUG: Campo 'activable' encontrado: {sensor['activable']}")
                                
                            if "active" not in sensor:
                                sensor["active"] = "false"     # Valor por defecto
                                print(f"🔍 DEBUG: Agregado campo 'active' por defecto")
                            else:
                                print(f"🔍 DEBUG: Campo 'active' encontrado: {sensor['active']}")
                                
                            if "name" not in sensor:
                                sensor["name"] = "Unknown"
                                print(f"🔍 DEBUG: Agregado campo 'name' por defecto")
                            else:
                                print(f"🔍 DEBUG: Campo 'name' encontrado: {sensor['name']}")
                                
                            if "configured_at" not in sensor:
                                sensor["configured_at"] = ""
                                print(f"🔍 DEBUG: Agregado campo 'configured_at' por defecto")
                            else:
                                print(f"🔍 DEBUG: Campo 'configured_at' encontrado: {sensor['configured_at']}")
                        
                        sensors = sensors_list
                        print(f"✅ Procesados {len(sensors)} sensores para {topic_name}")
                        print(f"🔍 DEBUG: Sensores finales: {json.dumps(sensors, indent=2)}")
                    else:
                        print("⚠️ Payload vacío en respuesta de sensores")
                        sensors = []
                except Exception as e:
                    print(f"❌ Error parsing sensors config: {e}")
                    import traceback
                    traceback.print_exc()
                    sensors = []
                finally:
                    response_received.set()
            
            print(f"🔍 DEBUG: Registrando handler temporal para TOPIC_SENSORS_RESP")
            # Registrar handler temporal
            self._register_temp_packet_handler(PacketType.TOPIC_SENSORS_RESP, handle_response)
            
            print(f"🔍 DEBUG: Enviando paquete TOPIC_SENSORS_REQ para {topic_name}")
            # Enviar solicitud
            topic_bytes = topic_name.encode('utf-8')
            packet = Packet(PacketType.TOPIC_SENSORS_REQ, 0, topic_bytes)
            
            if self._send_packet(packet):
                print(f"🔍 DEBUG: Esperando respuesta...")
                if response_received.wait(timeout=5.0):
                    print(f"🔍 DEBUG: Respuesta recibida, retornando {len(sensors)} sensores")
                    return sensors
                else:
                    print("⚠️ Timeout esperando respuesta de sensores")
            else:
                print("❌ No se pudo enviar la solicitud de sensores")
            
            return []
            
        except Exception as e:
            print(f"❌ Error obteniendo sensores: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            # Limpiar handler temporal
            with self._temp_handlers_lock:
                if PacketType.TOPIC_SENSORS_RESP in self._temp_handlers:
                    del self._temp_handlers[PacketType.TOPIC_SENSORS_RESP]
                    print(f"🧹 Handler TOPIC_SENSORS_RESP eliminado")
        
    def _handle_admin_resign_response(self, packet: Packet) -> None:
        """Maneja la respuesta de renuncia administrativa."""
        try:
            if packet.payload:
                response_data = json.loads(packet.payload.decode('utf-8'))
                success = response_data.get('success', False)
                message = response_data.get('message', 'Respuesta recibida')
                
                if self._admin_resign_callback:
                    self._admin_resign_callback(success, message)
                    self._admin_resign_callback = None
        except Exception as e:
            print(f"Error procesando respuesta de renuncia: {e}")

    def get_published_topics(self) -> List[Dict[str, str]]:
        """Obtiene una lista de tópicos publicados desde el broker."""
        if not self.connected:
            return []
        
        # PREVENIR SOLICITUDES DUPLICADAS
        if self._requesting_published_topics:
            print(f"[DEBUG] Solicitud de published topics ya en progreso, ignorando...")
            return []
        try:
            self._requesting_published_topics = True
            topics = []
            response_received = threading.Event()
            response_processed = False
            
            def handle_response(packet_type, payload):
                nonlocal topics, response_processed
                
                if response_processed:
                    return True  # Ya procesado
                    
                if payload:
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        topics = data if isinstance(data, list) else []
                        response_processed = True
                        print(f"[DEBUG] Procesados {len(topics)} tópicos")
                    except Exception as e:
                        print(f"Error parsing topics response: {e}")
                        topics = []
                
                response_received.set()
                return True  # Indicar que se procesó correctamente
            
            self._register_temp_packet_handler(PacketType.TOPIC_RESP, handle_response)
            
            packet = Packet(PacketType.TOPIC_REQ, 0, b'')
            if self._send_packet(packet):
                if response_received.wait(timeout=5.0):
                    return topics
            
            return []
        except Exception as e:
            print(f"Error getting published topics: {e}")
            return []
        finally:
                with self._temp_handlers_lock:
                    handler = self._temp_handlers.pop(PacketType.TOPIC_RESP, None)
                    if handler is not None:
                        print(f"[DEBUG] Handler TOPIC_RESP eliminado en finally")
                    else:
                        print(f"[DEBUG] Handler TOPIC_RESP ya fue eliminado previamente")
                self._requesting_published_topics = False
        
    def _register_temp_packet_handler(self, packet_type, handler_func):
        """Registra un handler temporal para un tipo de paquete específico."""
        print(f"[DEBUG] Registrando handler temporal para {packet_type.name}")
        with self._temp_handlers_lock:
            # Limpiar handler anterior si existe
            if packet_type in self._temp_handlers:
                print(f"[DEBUG] Reemplazando handler existente para {packet_type.name}")
                del self._temp_handlers[packet_type]
            self._temp_handlers[packet_type] = handler_func
            print(f"[DEBUG] Handler registrado. Total handlers: {len(self._temp_handlers)}")
                    
    def set_topic_publish(self, topic: str, publish: bool = True) -> bool:
        """Cambia el estado de publicación inmediatamente."""
        if not self.connected:
            print("No conectado al broker.")
            return False
            
        try:
            # Usar el mecanismo de publicación existente para notificar cambio
            publish_message = json.dumps({
                "__topic_publish_update": True,
                "client_id": self.client_id,
                "topic_name": topic,
                "publish": publish,
                "timestamp": int(time.time())
            })
            
            return self.publish(topic, publish_message)
            
        except Exception as e:
            print(f"Error actualizando tópico: {e}")
            return False
        
    def request_admin_status(self, topic_name: str, owner_id: str, callback=None) -> bool:
        """
        Solicita ser administrador de un tópico.
        
        Args:
            topic_name: Nombre del tópico
            owner_id: ID del cliente dueño del tópico
            callback: Función callback(success, message, error_code) para recibir respuesta
            
        Returns:
            True si la solicitud se envió correctamente
        """
        if not self.connected:
            if callback:
                callback(False, "No hay conexión con el broker", "NOT_CONNECTED")
            return False
            
        try:
            # Guardar callback para usar en la respuesta
            if callback:
                self._admin_request_callback = callback
            
            # Crear mensaje especial para solicitud de administrador
            request_message = json.dumps({
                "__admin_request": True,
                "client_id": self.client_id,
                "topic_name": topic_name,
                "owner_id": owner_id,
                "timestamp": int(time.time())
            })
            
            # El tópico para enviar la solicitud es uno especial
            admin_topic = f"{owner_id}/admin"
            
            # Publicar mensaje
            result = self.publish(admin_topic, request_message)
            return result
        except Exception as e:
            error_msg = f"Error enviando solicitud: {str(e)}"
            print(f"❌ {error_msg}")
            if callback:
                callback(False, error_msg, "EXCEPTION")
            return False
   
   
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
            
    def get_admin_requests(self):
        """Obtiene las solicitudes de administración pendientes"""
        try:
            # Verificar que estamos conectados
            if not self.connected:
                return []
            
            # Solicitar las peticiones al broker
            packet = Packet(packet_type=PacketType.ADMIN_REQ)
            if not self._send_packet(packet):
                print("Error al enviar solicitud de administración")
                return []
                
            # Implementación real que devuelve las solicitudes
            # Esto es solo un ejemplo y debe adaptarse a tu sistema
            return self._cached_admin_requests  # Esta variable debería poblarse cuando llegan notificaciones
        except Exception as e:
            print(f"Error al obtener solicitudes de administración: {e}")
            return []
        
    def respond_to_admin_request(self, request_id, topic_name, requester_id, approved):
        """
        Responde a una solicitud de administración.
        
        Args:
            request_id: ID de la solicitud
            topic_name: Nombre del tópico
            requester_id: ID del cliente solicitante
            approved: True para aprobar, False para rechazar
            
        Returns:
            True si se envió correctamente
        """
        if not self.connected:
            print("❌ [ADMIN] No conectado al broker")
            return False
        
        try:
            print(f"📤 [ADMIN] Enviando respuesta: {topic_name} -> {requester_id} = {'APROBADO' if approved else 'RECHAZADO'}")
            
            # Formato binario esperado por el broker
            # [approved:1][topic_len:1][topic][requester_len:1][requester_id]
            payload = bytearray()
            payload.append(1 if approved else 0)
            
            topic_bytes = topic_name.encode('utf-8')
            payload.append(len(topic_bytes))
            payload.extend(topic_bytes)
            
            requester_bytes = requester_id.encode('utf-8')
            payload.append(len(requester_bytes))
            payload.extend(requester_bytes)
            
            packet = Packet(PacketType.ADMIN_RESPONSE, 0, bytes(payload))
            
            return self._send_packet(packet)
        except Exception as e:
            print(f"❌ [ADMIN] Error enviando respuesta: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def set_sensor_status(self, topic_name, sensor_name, active):
        """
        Configura el estado de un sensor como administrador.
        
        Args:
            topic_name: Nombre del tópico
            sensor_name: Nombre del sensor
            active: True para activar, False para desactivar
            
        Returns:
            True si se envió correctamente
        """
        if not self.connected:
            return False
            
        try:
            # Crear mensaje de configuración
            config = json.dumps({
                "__admin_sensor_config": True,
                "client_id": self.client_id,
                "topic_name": topic_name,
                "sensor_name": sensor_name, 
                "active": active,
                "timestamp": int(time.time())
            })
            
            # Tópico para configuración
            config_topic = f"system/admin/config"
            
            # Publicar configuración
            return self.publish(config_topic, config)
        except Exception as e:
            print(f"Error configurando sensor: {e}")
            return False


    def get_pending_admin_requests(self) -> List[Dict]:
        """
        Obtiene las solicitudes de administración pendientes para este cliente.
        
        Returns:
            Lista de solicitudes de administración pendientes
        """
        if not self.connected:
            print("❌ [ADMIN] No conectado al broker")
            return []
            
        try:
            # Enviar paquete de solicitud de lista de admin
            packet = Packet(packet_type=PacketType.ADMIN_LIST_REQ, flags=0, payload=b'')
            
            # Variables para controlar la respuesta asíncrona
            admin_requests = []
            response_received = False
            response_event = threading.Event()
            
            # Handler temporal para recibir la respuesta
            def admin_list_handler(packet_type, payload):
                nonlocal admin_requests, response_received
                
                if packet_type == PacketType.ADMIN_LIST_RESP:
                    try:
                        # Decodificar el JSON de respuesta
                        payload_str = payload.decode('utf-8')
                        data = json.loads(payload_str)
                        print(f"✅ [ADMIN] Recibidas {len(data)} solicitudes pendientes")
                        admin_requests = data
                        response_received = True
                        response_event.set()
                        return True  # Indicar que se procesó el paquete
                    except Exception as e:
                        print(f"❌ [ADMIN] Error decodificando respuesta: {e}")
                        response_event.set()
                        return False
                return False
            
            # Registrar handler temporal
            self._register_temp_packet_handler(PacketType.ADMIN_LIST_RESP, admin_list_handler)
            
            # Enviar solicitud
            if not self._send_packet(packet):
                print("❌ [ADMIN] Error enviando solicitud de lista")
                return []
                
            # Esperar respuesta con timeout
            response_event.wait(timeout=5.0)
            
            # NUEVO: Eliminar el handler temporal después de usarlo
            with self._temp_handlers_lock:
                if PacketType.ADMIN_LIST_RESP in self._temp_handlers:
                    del self._temp_handlers[PacketType.ADMIN_LIST_RESP]
            
            if not response_received:
                print("⚠️ [ADMIN] Tiempo de espera agotado sin recibir respuesta")
            
            # Almacenar en caché para uso futuro
            self._cached_admin_requests = admin_requests
            
            return admin_requests
        except Exception as e:
            print(f"❌ [ADMIN] Error obteniendo solicitudes: {e}")
            import traceback
            traceback.print_exc()
            return []
        
    def get_my_topics(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los tópicos propios del cliente con su estado y administradores.
        
        Returns:
            Lista de diccionarios con información de los tópicos propios.
            Cada diccionario contiene: name, publish_active, admin_client_id, created_at
        """
        if not self.connected:
            print("No conectado al broker.")
            return []
        
        try:
            # Crear y enviar el paquete de solicitud
            packet = Packet(packet_type=PacketType.MY_TOPICS_REQ)
            if not self._send_packet(packet):
                print("Error al enviar solicitud MY_TOPICS_REQ")
                return []
            
            # Variables para capturar la respuesta
            topics_response = []
            response_received = False
            
            def my_topics_response_handler(packet_type, payload):
                nonlocal topics_response, response_received
                if packet_type == PacketType.MY_TOPICS_RESP:
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        topics_response = data
                        response_received = True
                        print(f"✅ Recibidos {len(data)} tópicos propios")
                        return True  # Marcar como procesado
                    except Exception as e:
                        print(f"Error procesando respuesta de mis tópicos: {e}")
                        response_received = True
                        return True
                return False
            
            # Registrar handler temporal
            self._register_temp_packet_handler(PacketType.MY_TOPICS_RESP, my_topics_response_handler)
            
            # Esperar respuesta con timeout
            start_time = time.time()
            while not response_received and time.time() - start_time < 10:
                time.sleep(0.1)
            
            # Limpiar el handler después del uso
            with self._temp_handlers_lock:
                if PacketType.MY_TOPICS_RESP in self._temp_handlers:
                    del self._temp_handlers[PacketType.MY_TOPICS_RESP]
            
            if not response_received:
                print("Timeout esperando respuesta de mis tópicos")
                
            return topics_response
            
        except Exception as e:
            print(f"Error solicitando mis tópicos: {e}")
            return []
        
    def revoke_admin_privileges(self, topic_name: str, admin_id: str) -> bool:
        """Revoca privilegios de administrador de un tópico."""
        if not self.connected:
            print("No conectado al broker.")
            return False
        
        try:
            revoke_message = json.dumps({
                "__admin_revoke": True,
                "client_id": self.client_id,
                "topic_name": topic_name,
                "admin_to_revoke": admin_id,
                "timestamp": int(time.time())
            })
            
            return self.publish(f"system/admin/revoke", revoke_message)
            
        except Exception as e:
            print(f"Error revocando privilegios: {e}")
            return False
        
    def get_my_admin_requests(self) -> List[Dict[str, Any]]:
        """
        Obtiene las solicitudes de administración enviadas por este cliente.
        
        Returns:
            Lista de solicitudes enviadas con su estado actual
        """
        if not self.connected:
            print("❌ [ADMIN] No conectado al broker")
            return []
            
        try:
            print(f"📤 [ADMIN] Solicitando mis solicitudes enviadas...")
            
            # Usar el paquete MY_ADMIN_REQ para solicitar mis solicitudes
            packet = Packet(packet_type=PacketType.MY_ADMIN_REQ, flags=0, payload=b'')
            
            if not self._send_packet(packet):
                print("❌ [ADMIN] Error enviando solicitud de mis peticiones")
                return []
            
            # Variables para controlar la respuesta asíncrona
            my_requests = []
            response_received = False
            
            def my_requests_handler(packet_type, payload):
                nonlocal my_requests, response_received
                
                if packet_type != PacketType.MY_ADMIN_RESP:
                    return False  # No procesamos este paquete
                    
                try:
                    # Decodificar el payload como JSON
                    data = json.loads(payload.decode('utf-8'))
                    my_requests = data
                    response_received = True
                    return True  # Indicamos que procesamos el paquete
                except Exception as e:
                    print(f"❌ [ADMIN] Error procesando respuesta: {e}")
                    return False
            
            # Registrar handler temporal
            self._register_temp_packet_handler(PacketType.MY_ADMIN_RESP, my_requests_handler)
            
            # Esperar respuesta con timeout
            start_time = time.time()
            while not response_received and time.time() - start_time < 5:
                time.sleep(0.1)
            
            # Limpiar el handler después del uso
            with self._temp_handlers_lock:
                if PacketType.MY_ADMIN_RESP in self._temp_handlers:
                    del self._temp_handlers[PacketType.MY_ADMIN_RESP]
            
            if not response_received:
                print("⚠️ [ADMIN] Timeout esperando respuesta de solicitudes enviadas")
                
            return my_requests
            
        except Exception as e:
            print(f"❌ [ADMIN] Error obteniendo mis solicitudes: {e}")
            import traceback
            traceback.print_exc()
            return []
        
    def register_admin_notification_handler(self, handler):
        """
        Registra un manejador para notificaciones de administración.
        
        Args:
            handler: Función que será llamada cuando lleguen notificaciones administrativas
        """
        self._admin_notify_callback = handler
        print(f"[DEBUG] Registrado handler de notificaciones administrativas")
    
    def register_admin_result_handler(self, handler):
        """
        Registra un manejador para resultados de solicitudes administrativas.
        
        Args:
            handler: Función que será llamada cuando lleguen resultados administrativos
        """
        self._admin_result_callback = handler
        print(f"[DEBUG] Registrado handler de resultados administrativos")    
    
            
            # En client.py - Agregar esta función nueva
    def _handle_admin_request_response(self, packet: Packet) -> None:
        """Maneja la respuesta de una solicitud de administración."""
        try:
            if packet.flags == 0:  # Éxito
                if packet.payload:
                    response_data = json.loads(packet.payload.decode('utf-8'))
                    message = response_data.get('message', 'Solicitud enviada correctamente')
                    topic_name = response_data.get('topic_name', 'desconocido')
                    
                    if self._admin_request_callback:
                        self._admin_request_callback(True, message, "SUCCESS", topic_name)
                
            else:  # Error (flags == 1)
                if packet.payload:
                    error_data = json.loads(packet.payload.decode('utf-8'))
                    error_code = error_data.get('error_code', 'UNKNOWN_ERROR')
                    error_message = error_data.get('error_message', 'Error desconocido')
                    topic_name = error_data.get('topic_name', 'desconocido')
                    
                    # Mensajes específicos para diferentes códigos de error
                    if error_code == "ALREADY_PENDING":
                        message = f"Ya tienes una solicitud pendiente para el tópico '{topic_name}'. Espera la respuesta del propietario."
                    elif error_code == "NOT_SUBSCRIBED":
                        message = f"Debes estar suscrito al tópico '{topic_name}' para solicitar administración."
                    elif error_code == "ALREADY_HAS_ADMIN":
                        message = f"El tópico '{topic_name}' ya tiene un administrador asignado."
                    else:
                        message = error_message
                    
                    if self._admin_request_callback:
                        self._admin_request_callback(False, message, error_code, topic_name)
                else:
                    if self._admin_request_callback:
                        self._admin_request_callback(False, "Error al procesar solicitud", "PACKET_ERROR", "")
        
        except Exception as e:
            print(f"Error procesando respuesta de admin request: {e}")
            if self._admin_request_callback:
                self._admin_request_callback(False, f"Error interno: {str(e)}", "PARSE_ERROR", "")  
                    
    def subscribe_to_sensor_control(self, das: 'DataAcquisitionService') -> None:
        """
        Suscribe al cliente a los mensajes de control para sus sensores y configura
        el reenvío de comandos al ESP32.
        
        Args:
            das: Servicio de adquisición de datos
        """
        print(f"✅ Configurando suscripción para control de sensores")
        
        # Suscribirse al tópico especial de notificaciones admin
        admin_topic = f"{self.client_id}/admin_notifications"
        
        def on_admin_notify(topic, payload):
            try:
                data = json.loads(payload.decode('utf-8'))
                print(f"🔔 Notificación recibida: {data}")
                
                # Si es un comando para un sensor
                if isinstance(data, dict) and data.get("command") == "set_sensor":
                    sensor_name = data.get("sensor_name")
                    active = data.get("active")
                    
                    print(f"🔄 Reenviando comando al ESP32: {sensor_name}={active}")
                    
                    # Convertir al formato que el ESP32 espera
                    esp_command = {
                        "command": "set_" + sensor_name,
                        "value": 1 if active else 0
                    }
                    
                    # Enviar comando al ESP32 a través del DAS
                    das.send_command(esp_command)
            except Exception as e:
                print(f"❌ Error procesando comando: {e}")
        
        print(f"🔔 Suscrito a comandos en: {admin_topic}")
        self.subscribe(admin_topic, on_admin_notify)
        
        # También suscribirse al tópico con formato JSON para compatibilidad
        json_topic = f"[\"{self.client_id}/admin_notifications\"]"
        print(f"🔔 Suscrito a comandos en formato JSON: {json_topic}")
        self.subscribe(json_topic, on_admin_notify)
        
        
    def mark_sensor_as_activable(self, topic_name: str, sensor_name: str, activable: bool = True) -> bool:
        if not self.connected:
            print("❌ No conectado al broker")
            return False

        import json
        try:
            msg = {
                "__admin_sensor_activable": True,
                "topic_name": topic_name,
                "sensor_name": sensor_name,
                "activable": activable,
                "client_id": self.client_id
            }
            # Publicar en un tópico especial de administración
            return self.publish("system/admin/sensor_activable", json.dumps(msg))
        except Exception as e:
            print(f"❌ Error configurando sensor: {e}")
            return False
            
    def publish_available_sensors(self, topic_name: str) -> bool:
        """
        Publica la lista de sensores disponibles para un tópico al broker.
        Esto permite que los administradores vean qué sensores existen y cuáles son controlables.
        
        Args:
            topic_name: Nombre del tópico
            
        Returns:
            True si se publicó correctamente
        """
        if not self.connected:
            print("❌ No conectado al broker")
            return False
        
        try:
            # Para simplificar, solo publicamos el ventilador como sensor controlable
            sensors_info = [
                {
                    "name": "temperature", 
                    "activable": False,
                    "current_value": "25.0",
                    "units": "C"
                },
                {
                    "name": "humidity", 
                    "activable": False,
                    "current_value": "60",
                    "units": "%"
                },
                {
                    "name": "fan", 
                    "activable": True,  # 👈 El ventilador es controlable
                    "current_value": "0",
                    "units": ""
                }
            ]
            
            # Enviar esta información en un formato estándar
            sensors_message = json.dumps({
                "__sensor_info": True,
                "topic": topic_name,
                "sensors": sensors_info,
                "timestamp": int(time.time())
            })
            
            # Publicar en un tópico especial para administradores
            sensor_info_topic = f"{self.client_id}/{topic_name}/sensor_info"
            return self.publish(sensor_info_topic, sensors_message)
            
        except Exception as e:
            print(f"❌ Error publicando sensores: {e}")
            return False
        
    def subscribe_to_sensor_info(self, topic_name: str, owner_id: str, callback):
        """
        Suscribe a la información de sensores de un tópico.
        
        Args:
            topic_name: Nombre del tópico
            owner_id: ID del cliente propietario
            callback: Función a llamar con la información de sensores
        
        Returns:
            True si se suscribió correctamente
        """
        if not self.connected:
            print("❌ No conectado al broker")
            return False
        
        # Tópico de información de sensores
        info_topic = f"{owner_id}/{topic_name}/sensor_info"
        
        def handle_info(topic, payload):
            try:
                data = json.loads(payload.decode('utf-8'))
                if isinstance(data, dict) and data.get("__sensor_info") and "sensors" in data:
                    # Pasar la lista de sensores al callback
                    callback(data.get("sensors", []))
            except Exception as e:
                print(f"❌ Error procesando información de sensores: {e}")
        
        return self.subscribe(info_topic, handle_info)

        
    
    def send_sensor_command(self, topic_name: str, owner_id: str, sensor_name: str, active: bool) -> bool:
        print(f"🔧 Enviando comando de sensor: {sensor_name} en {topic_name} (activo: {active})")
        """
        Envía un comando para controlar un sensor remoto.
        
        Args:
            topic_name: Nombre del tópico
            owner_id: ID del cliente propietario  
            sensor_name: Nombre del sensor
            active: True para activar, False para desactivar
            
        Returns:
            True si se envió correctamente
        """
        if not self.connected:
            print("❌ No conectado al broker")
            return False
            
        try:
            # Crear mensaje de control
            control_message = json.dumps({
                "command": "set_sensor",
                "topic_name": topic_name,
                "sensor_name": sensor_name,
                "active": active,
                "sender_id": self.client_id,
                "timestamp": int(time.time())
            })
            
            print(f"🔍 DEBUG: Enviando comando de sensor: {control_message}")
            
            # Publicar en el tópico de control
            control_topic = f"system/admin/config"
            print(f"🔍 DEBUG: Publicando en tópico: {control_topic}")
            
            return self.publish(control_topic, control_message)
        except Exception as e:
            print(f"❌ Error enviando comando de sensor: {e}")
            return False
            
    def setup_sensor_publishing(self, das: 'DataAcquisitionService', db: 'Database') -> None:
        """
        Configura la publicación periódica de sensores para todos los tópicos.
        
        Args:
            das: Servicio de adquisición de datos
            db: Base de datos local
        """
        self.db = db  # Guardar referencia a la base de datos
        
        # Publicar sensores cuando se reciba un nuevo dato
        def on_new_sensor_data(sensor_name, data):
            # Buscar tópicos con este sensor
            try:
                topics = self.db.get_published_topics()
                for topic_info in topics:
                    topic_name = topic_info["name"]
                    # Verificar si este sensor está en el tópico
                    topic_sensors = self.db.get_topic_sensors(topic_name)
                    if any(s["name"] == sensor_name for s in topic_sensors):
                        # Publicar información actualizada de sensores
                        self.publish_available_sensors(topic_name)
            except Exception as e:
                print(f"Error actualizando información de sensores: {e}")
        
        # Registrar el callback para nuevos datos
        das.add_data_callback(on_new_sensor_data)
        
        # Publicar estado inicial de sensores para todos los tópicos
        topics = self.db.get_published_topics()
        for topic_info in topics:
            self.publish_available_sensors(topic_info["name"])