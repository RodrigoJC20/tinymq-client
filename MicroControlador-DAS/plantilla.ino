// Plantilla para implementar sus propios sensores y actuadores

/*
 * ESP32 - Plantilla de Comunicación Serial con JSON
 *
 * Esta plantilla muestra cómo:
 * 1. Leer datos de sensores periódicamente
 * 2. Formatear los datos en JSON
 * 3. Enviarlos por puerto serial
 * 4. Recibir comandos JSON por serial
 */

#include <ArduinoJson.h>

// === DEFINICIÓN DE PINES (PERSONALIZAR) ===
// Define aquí los pines para tus sensores y actuadores
#define SENSOR_PIN_1 34   // Ejemplo: pin para sensor analógico
#define ACTUATOR_PIN_1 27 // Ejemplo: pin para un actuador (LED, relé, etc)

// === VARIABLES GLOBALES ===
// Variables para estado de actuadores
bool actuator1State = false;

// Variables para control de tiempo
unsigned long lastSensorTime = 0;
const unsigned long sensorInterval = 5000; // Enviar datos cada 5 segundos

// === FUNCIÓN PARA ENVIAR DATOS EN FORMATO JSON ===
// Esta es la función principal para formatear y enviar datos
void sendSensorData(float value1, float value2, int value3, bool state1)
{
  unsigned long timestamp = millis() / 1000;

  // Formato JSON para enviar múltiples valores de sensores
  String json = "[";
  json += "{\"name\":\"sensor1\",\"value\":" + String(value1) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"C\"},";
  json += "{\"name\":\"sensor2\",\"value\":" + String(value2) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"%\"},";
  json += "{\"name\":\"sensor3\",\"value\":" + String(value3) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"lux\"},";
  json += "{\"name\":\"actuator1\",\"value\":" + String(state1 ? 1 : 0) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"\"}";
  json += "]\n";

  // Enviar el JSON por el puerto serial
  Serial.println(json);
}

// === PROCESAR COMANDOS RECIBIDOS POR SERIAL ===
void processSerialCommand()
{
  if (Serial.available())
  {
    // Leer comando del puerto serial
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0)
      return;

    // Parsear JSON recibido
    StaticJsonDocument<128> doc;
    DeserializationError error = deserializeJson(doc, input);
    if (error)
    {
      Serial.println("{\"error\":\"JSON parse error\"}");
      return;
    }

    // Procesar comando
    const char *command = doc["command"];
    if (command)
    {
      // Ejemplo de comando para controlar un actuador
      if (strcmp(command, "set_actuator") == 0)
      {
        int value = doc["value"] | 0;
        actuator1State = (value == 1);
        digitalWrite(ACTUATOR_PIN_1, actuator1State ? HIGH : LOW);
        Serial.printf("{\"result\":\"actuator set to %d\"}\n", value);
      }

      // Añade más comandos aquí según necesites
    }
  }
}

void setup()
{
  // Inicializar comunicación serial
  Serial.begin(115200);

  // Configurar pines
  pinMode(SENSOR_PIN_1, INPUT);
  pinMode(ACTUATOR_PIN_1, OUTPUT);

  // Estado inicial de actuadores
  digitalWrite(ACTUATOR_PIN_1, LOW);

  Serial.println("{\"status\":\"device_ready\"}");
}

void loop()
{
  // Procesar comandos entrantes
  processSerialCommand();

  // === LECTURA PERIÓDICA DE SENSORES ===
  unsigned long currentTime = millis();
  if (currentTime - lastSensorTime >= sensorInterval)
  {
    // === LEER SENSORES ===
    // Reemplaza estas líneas con tu código para leer sensores reales
    float value1 = analogRead(SENSOR_PIN_1) * 0.1; // Ejemplo: convertir lectura a valor significativo
    float value2 = random(30, 80);                 // Ejemplo: valor simulado
    int value3 = random(100, 1000);                // Ejemplo: valor simulado

    // === ENVIAR DATOS ===
    sendSensorData(value1, value2, value3, actuator1State);

    // Actualizar tiempo de última lectura
    lastSensorTime = currentTime;
  }
}