"""
TinyMQ packet implementation.

This module implements the packet structure for the TinyMQ protocol.
"""
import enum
import struct
from typing import Optional, Tuple


class PacketType(enum.IntEnum):
    # Conexión básica
    CONN = 0x01              # First connection (requires client id)
    CONNACK = 0x02           # First connection acknowledgement
    
    # Publicación y suscripción
    PUB = 0x03               # Publish request
    PUBACK = 0x04            # Publish acknowledgement
    SUB = 0x05               # Subscribe request
    SUBACK = 0x06            # Subscribe acknowledgement
    UNSUB = 0x07             # Unsubscribe request
    UNSUBACK = 0x08          # Unsubscribe acknowledgement
    
    # Tópicos
    TOPIC_REQ = 0x09         # Request published topics
    TOPIC_RESP = 0x0A        # Response with published topics
    
    # Administración de tópicos - Solicitudes
    ADMIN_REQ = 0x0B         # Request admin status for a topic
    ADMIN_REQ_ACK = 0x0C     # Acknowledge admin request received
    ADMIN_NOTIFY = 0x0D      # Notify owner about new admin request
    ADMIN_RESPONSE = 0x0E    # Owner's response (approve/deny)
    ADMIN_RESULT = 0x0F      # Final result notification
    
    # Administración de tópicos - Listas y consultas
    ADMIN_LIST_REQ = 0x10    # Request list of admin requests
    ADMIN_LIST_RESP = 0x11   # Response with admin requests list
    ADMIN_RESP = 0x12        # Admin response packet
    MY_ADMIN_REQ = 0x13      # Request my admin requests
    MY_ADMIN_RESP = 0x14     # Response with my admin requests
    
    # Gestión de mis tópicos
    MY_TOPICS_REQ = 0x20     # Solicitar mis tópicos (como propietario)
    MY_TOPICS_RESP = 0x21    # Respuesta con mis tópicos
    
    # Gestión de administraciones
    MY_ADMIN_TOPICS_REQ = 0x22    # Solicitar tópicos donde soy admin
    MY_ADMIN_TOPICS_RESP = 0x23   # Respuesta con mis tópicos admin
    ADMIN_RESIGN = 0x24           # Renunciar a administración
    ADMIN_RESIGN_ACK = 0x25       # Confirmación de renuncia
    
    # Gestión de sensores
    TOPIC_SENSORS_REQ = 0x26      # Solicitar sensores de un tópico
    TOPIC_SENSORS_RESP = 0x27     # Respuesta con sensores

    SENSOR_STATUS_RESP = 0x35  # Respuesta de cambio de estado de sensor

class Packet:
    HEADER_SIZE = 4  # 1 byte type + 1 byte flags + 2 bytes payload length

    def __init__(
        self, 
        packet_type: PacketType, 
        flags: int = 0, 
        payload: bytes = b''
    ):
        self.packet_type = packet_type
        self.flags = flags
        self.payload = payload
    
    def serialize(self) -> bytes:
        """Serialize the packet into bytes."""
        header = struct.pack(
            '!BBH', 
            self.packet_type, 
            self.flags, 
            len(self.payload)
        )
        return header + self.payload
    
    @classmethod
    def deserialize(cls, data: bytes) -> Tuple[Optional['Packet'], int]:
        """
        Deserialize bytes into a Packet.
        
        Returns:
            Tuple containing the deserialized packet and bytes consumed.
            If not enough data, returns (None, 0).
        """
        if len(data) < cls.HEADER_SIZE:
            return None, 0
        
        packet_type, flags, payload_length = struct.unpack('!BBH', data[:cls.HEADER_SIZE])
        
        if len(data) < cls.HEADER_SIZE + payload_length:
            return None, 0
        
        payload = data[cls.HEADER_SIZE:cls.HEADER_SIZE + payload_length]
        
        try:
            packet = cls(PacketType(packet_type), flags, payload)
            return packet, cls.HEADER_SIZE + payload_length
        except ValueError:
            # Invalid packet type
            return None, cls.HEADER_SIZE + payload_length 