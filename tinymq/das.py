from typing import Optional, List, Dict, Any, Callable
import serial  # Librería para comunicación serial
import threading  # Para procesos en paralelo
import time
import json  # Para trabajar con formato JSON
import serial.tools.list_ports  # Para detectar puertos disponibles

from .db import Database


class DataAcquisitionService:
    """
    Servicio de Adquisición de Datos (DAS) para TinyMQ
    
    Este servicio se encarga de:
    1. Conectarse al ESP32 mediante puerto serial (USB)
    2. Recibir datos de los sensores automáticamente
    3. Enviar comandos para controlar actuadores (ventilador, luz, etc.)
    4. Almacenar los datos recibidos en la base de datos
    5. Reintentar conexión automáticamente si se desconecta el ESP32
    """

    def __init__(self, db: Database, serial_port: str = "COM8", baud_rate: int = 115200, verbose: bool = False):
        """
        Inicializa el servicio de comunicación serial
        
        Parámetros:
            db: Base de datos donde se guardarán las lecturas de sensores
            serial_port: Puerto donde está conectado el ESP32 (ej. "COM8" en Windows, "/dev/ttyUSB0" en Linux)
            baud_rate: Velocidad de comunicación (debe coincidir con la configurada en el ESP32)
            verbose: Si es True, muestra mensajes detallados sobre las operaciones
        """
        self.db = db
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.verbose = verbose

        # Conexión serial (se inicializa en None hasta que se establezca)
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False  # Indica si el servicio está activo
        self.thread: Optional[threading.Thread] = None  # Hilo para recibir datos en paralelo
        
        # Atributos para reconexión automática
        self.retry_thread: Optional[threading.Thread] = None
        self.retry_running = False

        # Lista de funciones que se ejecutarán cuando lleguen nuevos datos
        self.on_data_received_callbacks: List[Callable[[str, Any], None]] = []
        self.total_readings_received = 0  # Contador de lecturas recibidas

    def start(self, retry=True) -> bool:
        """
        Inicia la comunicación con el ESP32
        
        Parámetros:
            retry: Si es True, intentará reconectarse automáticamente si falla
            
        Retorna:
            True si se conectó exitosamente, False si falló
            
        Ejemplo:
            das = DataAcquisitionService(db, "COM8")
            if das.start():
                print("¡Conectado al ESP32!")
        """
        if self.running:
            return True  # Ya está conectado
        
        # Intento de conexión inicial
        success = self._connect()
        
        # Si falla y queremos reconexión automática
        if not success and retry:
            self._start_usb_monitor()
            
        return success
            
    def _connect(self) -> bool:
        """
        Función interna que intenta conectarse al puerto serial
        
        Retorna:
            True si se conectó correctamente, False si falló
        """
        try:
            # Verificar qué puertos están disponibles
            available_ports = [port.device for port in serial.tools.list_ports.comports()]
            if self.serial_port not in available_ports:
                if self.verbose:
                    print(f"❌ DAS: Puerto {self.serial_port} no disponible. Puertos disponibles: {available_ports}")
                return False
            
            # Abrir conexión serial
            self.serial_conn = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            time.sleep(2)  # Esperamos a que el ESP32 se inicialice
            
            # Iniciar proceso de lectura en segundo plano
            self.running = True
            self.thread = threading.Thread(target=self._read_serial_data)
            self.thread.daemon = True  # El thread terminará cuando termine el programa principal
            self.thread.start()
            
            print(f"✅ DAS: Conectado al puerto {self.serial_port}")
            return True
        except Exception as e:
            print(f"❌ DAS: Error de conexión: {e}")
            return False
    
    def stop(self) -> None:
        """
        Detiene la comunicación y cierra la conexión serial
        
        Ejemplo:
            das.stop()  # Detener comunicación antes de cerrar la aplicación
        """
        # Detener monitor de reconexión
        self.retry_running = False
        if self.retry_thread and self.retry_thread.is_alive():
            self.retry_thread.join(timeout=1.0)
            
        # Detener servicio principal
        if not self.running:
            return
            
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
                
        # Cerrar conexión serial
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except:
                pass
            self.serial_conn = None
            
        print("✅ DAS: Servicio detenido")
            
    def _start_usb_monitor(self) -> None:
        """
        Función interna que inicia el monitoreo de conexiones USB
        para detectar cuando se conecta el ESP32
        """
        if self.retry_running:
            return
            
        self.retry_running = True
        self.retry_thread = threading.Thread(target=self._usb_monitor)
        self.retry_thread.daemon = True
        self.retry_thread.start()
        print(f"🔌 DAS: Esperando conexión del ESP32 en puerto {self.serial_port}...")
        
    def _usb_monitor(self) -> None:
        """
        Función interna que vigila continuamente si se conecta el ESP32
        y establece la conexión automáticamente
        """
        last_ports = set()  # Lista de puertos detectados anteriormente
        
        # Detectar puertos iniciales
        try:
            last_ports = set(port.device for port in serial.tools.list_ports.comports())
            print(f"🔌 DAS: Puertos detectados inicialmente: {last_ports}")
        except:
            pass
        
        print("🔌 DAS: Esperando conexión del ESP32...")
        
        # Bucle principal de monitoreo
        while self.retry_running and not self.running:
            try:
                # Obtener puertos actuales
                current_ports = set(port.device for port in serial.tools.list_ports.comports())
                
                # Verificar si hay nuevos puertos conectados
                new_ports = current_ports - last_ports
                
                if new_ports:
                    print(f"🔌 DAS: Nuevo dispositivo conectado: {new_ports}")
                    
                    # Intentar conectar cuando aparece un nuevo dispositivo
                    if self._connect():
                        self.retry_running = False
                        print("✅ DAS: Conexión automática exitosa")
                        break
                    else:
                        print("❌ DAS: No se pudo conectar al nuevo dispositivo")
                
                # Actualizar lista de puertos
                last_ports = current_ports
                time.sleep(1)  # Esperar antes de verificar nuevamente
                    
            except Exception as e:
                if self.verbose:
                    print(f"❌ DAS: Error monitoreando USB: {e}")
                time.sleep(1)
                
        # Mensaje final si se detuvo el monitoreo
        if self.retry_running and not self.running:
            print("ℹ️ DAS: Monitoreo de conexiones finalizado")
        self.retry_running = False
        
    def send_command(self, command: Dict) -> bool:
        """
        Envía un comando al ESP32 en formato JSON
        
        Parámetros:
            command: Diccionario con el comando a enviar
            
        Retorna:
            True si se envió correctamente, False si hubo error
            
        Ejemplo:
            # Encender el ventilador
            das.send_command({"command": "set_fan", "value": 1})
            
            # Apagar la luz
            das.send_command({"command": "set_led", "value": 0})
        """
        if not self.running or not self.serial_conn:
            print("❌ DAS: No hay conexión activa con el ESP32")
            return False
        
        try:
            # Convertir comando a texto JSON
            cmd_json = json.dumps(command)
            if self.verbose:
                print(f"📤 DAS: Enviando comando: {cmd_json}")
            
            # Enviar comando por serial (añadiendo salto de línea)
            self.serial_conn.write(f"{cmd_json}\n".encode('utf-8'))
            self.serial_conn.flush()
            return True
        except Exception as e:
            print(f"❌ DAS: Error enviando comando: {e}")
            return False
    
    def _read_serial_data(self) -> None:
        """
        Función interna que lee continuamente datos del puerto serial
        y los procesa cuando llegan (corre en un hilo separado)
        """
        try:
            buffer = ""  # Almacena los caracteres recibidos
            was_disconnected = False
            
            # Bucle principal de lectura
            while self.running:
                try:
                    # Verificar si la conexión está activa
                    if not self.serial_conn or not self.serial_conn.is_open:
                        if not was_disconnected:
                            was_disconnected = True
                        time.sleep(0.5)
                        continue

                    # Notificar si hubo reconexión
                    if was_disconnected:
                        print(f"✅ DAS: Conexión restablecida en {self.serial_port}")
                        was_disconnected = False

                    # Leer un byte a la vez
                    byte = self.serial_conn.read(1)
                    if not byte:  # No hay datos, seguir esperando
                        continue

                    # Convertir byte a carácter y añadir al buffer
                    char = byte.decode('utf-8')
                    buffer += char

                    # Si encontramos un fin de línea, procesar el mensaje completo
                    if char == '\n':
                        data_read = self._process_data(buffer.encode('utf-8'))
                        buffer = ""  # Reiniciar buffer

                        if data_read > 0:
                            self.total_readings_received += data_read
                            
                except (serial.SerialException, OSError, PermissionError) as e:
                    # Error de conexión serial
                    print(f"⚠️ DAS: Conexión perdida: {e}")
                    if self.serial_conn:
                        try:
                            self.serial_conn.close()
                        except:
                            pass
                        self.serial_conn = None
                    was_disconnected = True
                    
                    # Detener y reiniciar conexión
                    self.running = False
                    if not self.retry_running:
                        self._start_usb_monitor()
                    break  # Salir del bucle
                    
                except UnicodeDecodeError:
                    # Error en datos recibidos, reiniciar buffer
                    buffer = ""
                    continue
                    
        except Exception as e:
            if self.running:
                print(f"❌ DAS: Error en lectura de datos: {e}")
        finally:
            print("ℹ️ DAS: Proceso de lectura finalizado")

    def _process_data(self, data: bytes) -> int:
        """
        Función interna que procesa los datos recibidos del ESP32
        
        Parámetros:
            data: Datos recibidos en bytes
            
        Retorna:
            Número de lecturas de sensores procesadas
        """
        try:
            # Convertir bytes a texto
            data_str = data.decode('utf-8').strip()
            if not data_str:
                return 0
                
            if self.verbose:
                print(f"📥 DAS: Datos recibidos: {data_str}")
                
            # Intentar interpretar como JSON
            try:
                json_data = json.loads(data_str)
                
                # Caso 1: Es una respuesta a un comando
                if isinstance(json_data, dict) and "result" in json_data:
                    if self.verbose:
                        print(f"✅ DAS: Respuesta del ESP32: {json_data['result']}")
                    return 0
                
                # Caso 2: Es un mensaje de error
                if isinstance(json_data, dict) and "error" in json_data:
                    print(f"❌ DAS: Error reportado por ESP32: {json_data['error']}")
                    return 0
                    
                # Caso 3: Son lecturas de sensores (array de objetos)
                if isinstance(json_data, list):
                    timestamp = int(time.time())
                    count = 0
                    
                    # Procesar cada sensor
                    for reading in json_data:
                        if isinstance(reading, dict) and "name" in reading and "value" in reading:
                            sensor_name = reading["name"]
                            value = reading["value"]
                            units = reading.get("units", "")
                            
                            # Guardar lectura en base de datos
                            self._store_sensor_reading(sensor_name, value, timestamp, units)
                            count += 1
                    
                    return count
            except json.JSONDecodeError:
                # No es JSON válido, probablemente mensaje de texto
                if self.verbose:
                    print(f"ℹ️ DAS: Mensaje recibido: {data_str}")
                return 0
                
        except Exception as e:
            print(f"❌ DAS: Error procesando datos: {e}")
            return 0

    def _store_sensor_reading(self, name: str, value: Any, timestamp: int, units: str) -> None:
        """
        Función interna que guarda una lectura en la base de datos
        y notifica a los callbacks registrados
        
        Parámetros:
            name: Nombre del sensor (ej. "temperature", "humidity")
            value: Valor leído
            timestamp: Marca de tiempo (segundos desde 1970)
            units: Unidades de medida (ej. "C", "%")
        """
        try:
            # 1. Guardar en la base de datos
            if self.db:
                self.db.add_reading(name, value, timestamp, units)
            
            # 2. Notificar a todos los callbacks registrados
            for callback in self.on_data_received_callbacks:
                try:
                    callback(name, {
                        "value": value,
                        "timestamp": timestamp,
                        "units": units
                    })
                except Exception as e:
                    print(f"❌ DAS: Error en función callback: {e}")
        except Exception as e:
            print(f"❌ DAS: Error guardando lectura: {e}")
        
    def add_data_callback(self, callback: Callable[[str, Any], None]) -> None:
        """
        Registra una función que se ejecutará cuando lleguen nuevos datos
        
        Parámetros:
            callback: Función que recibe (sensor_name, datos)
            
        Ejemplo:
            # Función que muestra nuevas lecturas
            def mostrar_lectura(sensor, datos):
                print(f"Nuevo dato de {sensor}: {datos['value']} {datos['units']}")
                
            # Registrar la función
            das.add_data_callback(mostrar_lectura)
        """
        if callback not in self.on_data_received_callbacks:
            self.on_data_received_callbacks.append(callback)
            print(f"✅ DAS: Nueva función callback registrada (total: {len(self.on_data_received_callbacks)})")

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del servicio
        
        Retorna:
            Diccionario con información sobre el estado del servicio
            
        Ejemplo:
            stats = das.get_stats()
            print(f"Lecturas recibidas: {stats['readings_received']}")
        """
        return {
            "running": self.running,  # Si está conectado
            "port": self.serial_port,  # Puerto serial usado
            "baud_rate": self.baud_rate,  # Velocidad
            "readings_received": self.total_readings_received,  # Total de lecturas
            "callbacks_registered": len(self.on_data_received_callbacks)  # Callbacks
        }

    def set_verbose(self, verbose: bool) -> None:
        """
        Activa o desactiva mensajes detallados
        
        Parámetros:
            verbose: True para mostrar todos los mensajes, False para mostrar solo importantes
            
        Ejemplo:
            das.set_verbose(True)  # Ver todos los mensajes
        """
        self.verbose = verbose
        print(f"ℹ️ DAS: Modo detallado {'activado' if verbose else 'desactivado'}")
        
    def clear_callbacks(self) -> None:
        """
        Elimina todas las funciones callback registradas
        
        Ejemplo:
            das.clear_callbacks()  # Eliminar todas las notificaciones
        """
        self.on_data_received_callbacks.clear()
        print("✅ DAS: Todas las funciones callback han sido eliminadas")