from typing import Optional, List, Dict, Any, Callable
import serial  # Librería para comunicación serial
import threading
import time
import json
import serial.tools.list_ports

from .db import Database


class DataAcquisitionService:
    """
    Data Acquisition Service for TinyMQ client using Serial communication.
    """

    def __init__(self, db: Database, serial_port: str = "COM8", baud_rate: int = 115200, verbose: bool = False):
        """
        Args:
            db: Instancia de la base de datos
            serial_port: Puerto serial (ej. "COM3" en Windows o "/dev/ttyUSB0" en Linux)
            baud_rate: Velocidad de transmisión en baudios
            verbose: Si se debe imprimir cada lectura recibida
        """
        self.db = db
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.verbose = verbose

        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Atributos para manejar reconexión con detección USB
        self.retry_thread: Optional[threading.Thread] = None
        self.retry_running = False

        self.on_data_received_callbacks: List[Callable[[str, Any], None]] = []
        self.total_readings_received = 0

    def start(self, retry=True) -> bool:
        """
        Inicia el servicio de adquisición de datos desde el puerto serial.
        
        Args:
            retry: Si debe reintentar automáticamente la conexión en caso de fallo
            
        Returns:
            bool: True si se conectó exitosamente, False si falló la conexión inicial
        """
        if self.running:
            return True
        
        # Intentar conectar una vez
        success = self._connect()
        
        # Si falló y queremos reintentar, iniciar thread de monitoreo de USB
        if not success and retry:
            self._start_usb_monitor()
            
        return success
            
    def _connect(self) -> bool:
        """
        Intenta establecer una conexión con el puerto serial.
        
        Returns:
            bool: True si se conectó correctamente, False en caso contrario
        """
        try:
            # Verificar si el puerto existe antes de intentar conectar
            available_ports = [port.device for port in serial.tools.list_ports.comports()]
            if self.serial_port not in available_ports:
                if self.verbose:
                    print(f"❌ DAS: Puerto {self.serial_port} no disponible. Puertos disponibles: {available_ports}")
                return False
            
            # Iniciar conexión serial
            self.serial_conn = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            time.sleep(2)  # Dar tiempo al ESP32 para inicializarse
            
            self.running = True
            self.thread = threading.Thread(target=self._read_serial_data)
            self.thread.daemon = True
            self.thread.start()
            
            print(f"✅ DAS: Servicio iniciado en puerto {self.serial_port}")
            return True
        except Exception as e:
            print(f"❌ DAS: Error iniciando servicio: {e}")
            return False
    
    def stop(self) -> None:
        """Detiene el servicio de adquisición de datos y el monitoreo USB."""
        # Detener monitoreo USB
        self.retry_running = False
        if self.retry_thread and self.retry_thread.is_alive():
            self.retry_thread.join(timeout=1.0)
            
        # Detener servicio principal
        if not self.running:
            return
            
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
                
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except:
                pass
            self.serial_conn = None
            
        print("✅ DAS: Servicio detenido")
            
    def _start_usb_monitor(self) -> None:
        """Inicia el monitoreo de dispositivos USB para detectar reconexiones."""
        if self.retry_running:
            return
            
        self.retry_running = True
        self.retry_thread = threading.Thread(target=self._usb_monitor)
        self.retry_thread.daemon = True
        self.retry_thread.start()
        print(f"🔌 DAS: Monitoreando conexiones USB para puerto {self.serial_port}")
        
    def _usb_monitor(self) -> None:
        """
        Monitorea la disponibilidad del puerto USB y reintenta la conexión
        SOLO cuando se detecta un nuevo dispositivo USB.
        """
        last_ports = set()
        
        # Obtener puertos iniciales
        try:
            last_ports = set(port.device for port in serial.tools.list_ports.comports())
            print(f"🔌 DAS: Puertos iniciales detectados: {last_ports}")
        except:
            pass
        
        print("🔌 DAS: Esperando nuevos dispositivos USB...")
        
        while self.retry_running and not self.running:
            try:
                # Obtener puertos actuales
                current_ports = set(port.device for port in serial.tools.list_ports.comports())
                
                # Detectar SOLO si se agregaron nuevos puertos
                new_ports = current_ports - last_ports
                
                if new_ports:
                    print(f"🔌 DAS: Nuevos dispositivos USB detectados: {new_ports}")
                    
                    # Solo intentar conectar cuando hay nuevos USBs
                    if self._connect():
                        self.retry_running = False
                        print("✅ DAS: Reconexión exitosa")
                        break
                    else:
                        print("❌ DAS: Falló conexión con nuevos dispositivos")
                
                # Actualizar lista de puertos para la próxima comparación
                last_ports = current_ports
                
                # Esperar un poco antes de verificar nuevamente (pero NO para reintentar)
                time.sleep(1)  # Solo 1 segundo para verificar cambios USB
                    
            except Exception as e:
                if self.verbose:
                    print(f"❌ DAS: Error en monitoreo USB: {e}")
                time.sleep(1)
                
        if self.retry_running and not self.running:
            print("ℹ️ DAS: Monitoreo USB finalizado sin éxito")
        self.retry_running = False
        
    def send_command(self, command: Dict) -> bool:
        """
        Envía un comando al ESP32.
        
        Args:
            command: Diccionario con el comando a enviar. Debe tener un campo 'command'
                    y los parámetros necesarios (ej. {"command": "set_fan", "value": 1})
                    
        Returns:
            bool: True si se envió el comando, False en caso de error
        """
        if not self.running or not self.serial_conn:
            print("❌ DAS: No hay conexión serial activa para enviar comandos")
            return False
        
        try:
            # Convertir comando a JSON
            cmd_json = json.dumps(command)
            if self.verbose:
                print(f"📤 DAS: Enviando comando: {cmd_json}")
            
            # Enviar comando
            self.serial_conn.write(f"{cmd_json}\n".encode('utf-8'))
            self.serial_conn.flush()
            return True
        except Exception as e:
            print(f"❌ DAS: Error enviando comando: {e}")
            return False
    
    def _read_serial_data(self) -> None:
        """Función principal de lectura de datos seriales. Corre en un thread separado."""
        try:
            buffer = ""
            while self.running and self.serial_conn:
                try:
                    # Leer un byte del puerto serial
                    byte = self.serial_conn.read(1)
                    if not byte:
                        continue
                    
                    char = byte.decode('utf-8')
                    buffer += char
                    
                    # Si encontramos un salto de línea, procesar la línea
                    if char == '\n':
                        data_read = self._process_data(buffer.encode('utf-8'))
                        buffer = ""
                        
                        if data_read > 0:
                            self.total_readings_received += data_read
                except UnicodeDecodeError:
                    # Ignorar errores de decodificación
                    buffer = ""
                    continue
        except Exception as e:
            if self.running:  # Solo mostrar error si todavía debería estar corriendo
                print(f"❌ DAS: Error en thread de lectura: {e}")
        finally:
            print("ℹ️ DAS: Thread de lectura finalizado")
            
    def _process_data(self, data: bytes) -> int:
        """
        Procesa los datos recibidos del ESP32.
        
        Args:
            data: Datos recibidos como bytes
            
        Returns:
            int: Número de lecturas procesadas
        """
        try:
            # Decodificar los datos
            data_str = data.decode('utf-8').strip()
            if not data_str:
                return 0
                
            if self.verbose:
                print(f"📥 DAS: Datos recibidos: {data_str}")
                
            # Intentar parsear como JSON
            try:
                json_data = json.loads(data_str)
                
                # Es una respuesta de comando
                if isinstance(json_data, dict) and "result" in json_data:
                    if self.verbose:
                        print(f"✅ DAS: Respuesta de comando: {json_data['result']}")
                    return 0
                
                # Es un error
                if isinstance(json_data, dict) and "error" in json_data:
                    print(f"❌ DAS: Error del ESP32: {json_data['error']}")
                    return 0
                    
                # Es una lectura de sensores
                if isinstance(json_data, list):
                    timestamp = int(time.time())
                    count = 0
                    
                    for reading in json_data:
                        if isinstance(reading, dict) and "name" in reading and "value" in reading:
                            sensor_name = reading["name"]
                            value = reading["value"]
                            units = reading.get("units", "")
                            
                            # Almacenar lectura en BD
                            self._store_sensor_reading(sensor_name, value, timestamp, units)
                            count += 1
                    
                    return count
            except json.JSONDecodeError:
                # No es JSON, probablemente sea un mensaje de texto simple
                if self.verbose:
                    print(f"ℹ️ DAS: Mensaje (no JSON): {data_str}")
                return 0
                
        except Exception as e:
            print(f"❌ DAS: Error procesando datos: {e}")
            return 0

    def _store_sensor_reading(self, name: str, value: Any, timestamp: int, units: str) -> None:
        """
        Almacena una lectura de sensor y notifica a los callbacks registrados.
        
        Args:
            name: Nombre del sensor
            value: Valor del sensor
            timestamp: Timestamp de la lectura
            units: Unidades de medida
        """
        try:
            # Guardar en la base de datos
            if self.db:
                # Cambiar store_sensor_reading por add_reading
                self.db.add_reading(name, value, timestamp, units)
            
            # Notificar a los callbacks
            for callback in self.on_data_received_callbacks:
                try:
                    callback(name, {
                        "value": value,
                        "timestamp": timestamp,
                        "units": units
                    })
                except Exception as e:
                    print(f"❌ DAS: Error en callback: {e}")
        except Exception as e:
            print(f"❌ DAS: Error almacenando lectura: {e}")
        
    def add_data_callback(self, callback: Callable[[str, Any], None]) -> None:
        """
        Añade un callback que será llamado cuando se reciba una nueva lectura.
        
        Args:
            callback: Función que recibe (sensor_name, data_dict)
        """
        if callback not in self.on_data_received_callbacks:
            self.on_data_received_callbacks.append(callback)
            print(f"✅ DAS: Callback registrado ({len(self.on_data_received_callbacks)} total)")

    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del servicio."""
        return {
            "running": self.running,
            "port": self.serial_port,
            "baud_rate": self.baud_rate,
            "readings_received": self.total_readings_received,  # <- Cambiado aquí
            "callbacks_registered": len(self.on_data_received_callbacks)
        }

    def set_verbose(self, verbose: bool) -> None:
        """Activa o desactiva el modo verboso."""
        self.verbose = verbose
        print(f"ℹ️ DAS: Modo verboso {'activado' if verbose else 'desactivado'}")
        
    def clear_callbacks(self) -> None:
        """Elimina todos los callbacks registrados."""
        self.on_data_received_callbacks.clear()
        print("✅ DAS: Callbacks eliminados")