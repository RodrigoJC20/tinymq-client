"""
TinyMQ client implementation.

This module provides the client functionality for the TinyMQ protocol.
"""
import json
import socket
import threading
import time
from typing import Dict, Callable, Optional, List

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
        
        self.topic_handlers: Dict[str, Callable[[str, bytes], None]] = {}
        self.read_thread: Optional[threading.Thread] = None
        self.running = False
        
        self._recv_buffer = bytearray()
        self._recv_lock = threading.Lock()
    
    def connect(self) -> bool:
        """
        Connect to the TinyMQ broker.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            
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
        
        self.connected = False
    
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
            broker_topic = f"{self.client_id}/{topic}"
            
            broker_topic_bytes = broker_topic.encode('utf-8')
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
                print(f"Read error: {e}")
                break
        
        # Ensure we're disconnected on error, but don't call disconnect() directly
        # as it would try to join the current thread
        self.running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def _handle_packet(self, packet: Packet) -> None:
        """
        Handle a received packet.
        
        Args:
            packet: Packet to handle
        """
        if packet.packet_type == PacketType.CONNACK:
            self.connected = True
        
        elif packet.packet_type == PacketType.PUBACK:
            # Could track message IDs for QoS in future
            pass
            
        elif packet.packet_type == PacketType.SUBACK:
            # Could track subscription IDs in future
            pass
            
        elif packet.packet_type == PacketType.UNSUBACK:
            # Could track unsubscription IDs in future
            pass
            
        elif packet.packet_type == PacketType.PUB:
            # Parse payload
            try:
                data = json.loads(packet.payload.decode('utf-8'))
                topic = data.get("topic")
                message = data.get("message", "")
                
                if topic and topic in self.topic_handlers:
                    self.topic_handlers[topic](topic, message)
            except json.JSONDecodeError:
                print("Invalid JSON in PUB packet")
            except Exception as e:
                print(f"Error handling PUB packet: {e}") 