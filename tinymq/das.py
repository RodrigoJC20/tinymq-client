"""
Data Acquisition Service (DAS) for TinyMQ client.

This module receives and processes sensor data from an ESP32 device.
"""
import json
import socket
import threading
import time
from typing import Optional, List, Dict, Any, Callable

from .db import Database


class DataAcquisitionService:
    """
    Data Acquisition Service for TinyMQ client.
    
    Receives sensor data from ESP32 devices and stores it in the database.
    """
    
    def __init__(self, db: Database, host: str = "0.0.0.0", port: int = 12345, verbose: bool = False):
        """
        Initialize the Data Acquisition Service.
        
        Args:
            db: Database instance
            host: Host to bind to
            port: Port to listen on
            verbose: Whether to print details of every sensor reading
        """
        self.db = db
        self.host = host
        self.port = port
        self.verbose = verbose
        
        self.server: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        self.on_data_received_callbacks: List[Callable[[str, Any], None]] = []
        self.total_readings_received = 0
    
    def start(self) -> bool:
        """
        Start the Data Acquisition Service.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.running:
            return True
            
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            
            self.running = True
            self.thread = threading.Thread(target=self._accept_connections)
            self.thread.daemon = True
            self.thread.start()
            
            return True
        except Exception as e:
            print(f"Failed to start DAS: {e}")
            if self.server:
                self.server.close()
                self.server = None
            return False
    
    def stop(self) -> None:
        """Stop the Data Acquisition Service."""
        self.running = False
        if self.server:
            try:
                self.server.close()
            except:
                pass
            self.server = None
        
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
    
    def add_data_callback(self, callback: Callable[[str, Any], None]) -> None:
        """
        Add a callback to be called when data is received.
        
        Args:
            callback: Function to call with (sensor_name, sensor_data)
        """
        self.on_data_received_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the DAS.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "readings_received": self.total_readings_received,
            "running": self.running
        }
    
    def set_verbose(self, verbose: bool) -> None:
        """
        Set verbosity mode.
        
        Args:
            verbose: Whether to print details of every sensor reading
        """
        self.verbose = verbose
    
    def _accept_connections(self) -> None:
        """Accept connections and handle them."""
        if not self.server:
            return
            
        self.server.settimeout(1.0)  # Allow checking self.running
        
        print(f"DAS listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                client, addr = self.server.accept()
                print(f"ESP32 connection from {addr}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, addr)
                )
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue  # Just checking if we should still be running
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
    
    def _handle_client(self, client: socket.socket, addr: tuple) -> None:
        """
        Handle a client connection.
        
        Args:
            client: Client socket
            addr: Client address
        """
        buffer = b""
        client.settimeout(5.0)  # 5 second timeout for receiving data
        readings_count = 0
        
        try:
            while self.running:
                try:
                    data = client.recv(4096)
                    if not data:
                        break  # Connection closed
                    
                    buffer += data
                    
                    # Process any complete lines (JSON objects)
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line.strip():
                            count = self._process_data(line)
                            readings_count += count
                except socket.timeout:
                    continue  # Just checking if we should still be running
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            try:
                client.close()
            except:
                pass
            print(f"ESP32 connection from {addr} closed (received {readings_count} readings)")
    
    def _process_data(self, data: bytes) -> int:
        """
        Process sensor data from an ESP32 device.
        
        Args:
            data: JSON data as bytes
            
        Returns:
            Number of readings processed
        """
        count = 0
        try:
            json_data = json.loads(data.decode('utf-8'))
            
            if isinstance(json_data, list):
                # List of sensors
                for sensor in json_data:
                    if not isinstance(sensor, dict):
                        continue
                        
                    name = sensor.get("name")
                    value = sensor.get("value")
                    timestamp = sensor.get("timestamp", int(time.time()))
                    units = sensor.get("units", "")
                    
                    if name is not None and value is not None:
                        self._store_sensor_reading(name, value, timestamp, units)
                        count += 1
            elif isinstance(json_data, dict):
                # Single sensor
                name = json_data.get("name")
                value = json_data.get("value")
                timestamp = json_data.get("timestamp", int(time.time()))
                units = json_data.get("units", "")
                
                if name is not None and value is not None:
                    self._store_sensor_reading(name, value, timestamp, units)
                    count += 1
                    
        except json.JSONDecodeError:
            print(f"Invalid JSON: {data.decode('utf-8')}")
        except Exception as e:
            print(f"Error processing data: {e}")
        
        return count
    
    def _store_sensor_reading(self, name: str, value: Any, timestamp: int, units: str) -> None:
        """
        Store a sensor reading in the database.
        
        Args:
            name: Sensor name
            value: Sensor value
            timestamp: Timestamp
            units: Units
        """
        try:
            # Convert to string if not already
            if not isinstance(value, str):
                value = str(value)
            
            self.db.add_reading(name, value, timestamp, units)
            self.total_readings_received += 1
            
            for callback in self.on_data_received_callbacks:
                try:
                    callback(name, {
                        "value": value,
                        "timestamp": timestamp,
                        "units": units
                    })
                except Exception as e:
                    print(f"Error in data callback: {e}")
            
            # Only print if verbose mode is enabled
            if self.verbose:
                print(f"Stored reading: {name}={value}{units} @ {timestamp}")
        except Exception as e:
            print(f"Error storing sensor reading: {e}") 