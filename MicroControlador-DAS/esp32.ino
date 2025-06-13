// Código de ejemplo para ESP32

/*
 * ESP32 Smart Home Sensor Integration (Versión Serial)
 *
 * Este programa implementa un sistema domótico que:
 * 1. Lee datos de temperatura y humedad desde un sensor DHT11
 * 2. Lee datos de un sensor de luz ambiental
 * 3. Controla un ventilador mediante PWM
 * 4. Controla un relé para luces
 * 5. Envía todos los datos por puerto serial en formato JSON cada 5 segundos
 * 6. Procesa comandos JSON recibidos por serial para control remoto
 */

#include <dht11.h>
#include <time.h>
#include <ArduinoJson.h> // Necesaria para procesar y generar datos en formato JSON

// ===== DEFINICIÓN DE PINES =====
// Sensores
#define DHT11PIN 17         // Sensor de temperatura y humedad
#define LIGHT_SENSOR_PIN 34 // Sensor de luz analógico
#define BUTTON_PIN 5        // Botón físico para control manual

// Actuadores
#define MOTOR_PIN1 19      // Control del ventilador (IN1)
#define MOTOR_PIN2 18      // Control del ventilador (IN2)
#define LIGHT_RELAY_PIN 27 // Relé para control de iluminación

// ===== VARIABLES GLOBALES =====
dht11 DHT11; // Objeto para manejar el sensor DHT11

bool fanState = false;       // Estado actual del ventilador
bool lastButtonState = HIGH; // Estado anterior del botón (para detección de flancos)

// Control de tiempo para envío periódico de datos
unsigned long lastSensorTime = 0;          // Timestamp de la última lectura
const unsigned long sensorInterval = 5000; // Intervalo de envío: 5 segundos

/**
 * Configura los pines del motor y canales PWM para control del ventilador
 */
void setupMotor()
{
  pinMode(MOTOR_PIN1, OUTPUT);
  pinMode(MOTOR_PIN2, OUTPUT);
  digitalWrite(MOTOR_PIN1, LOW);
  digitalWrite(MOTOR_PIN2, LOW);

  // Configurar canales PWM para control de velocidad
  ledcSetup(1, 1200, 8); // Canal 1, 1.2 kHz, resolución 8 bits
  ledcAttachPin(MOTOR_PIN1, 1);
  ledcSetup(2, 1200, 8); // Canal 2, 1.2 kHz, resolución 8 bits
  ledcAttachPin(MOTOR_PIN2, 2);

  // Inicializar apagado
  ledcWrite(1, 0);
  ledcWrite(2, 0);
}

/**
 * Controla el estado del ventilador
 *
 * @param on true para encender, false para apagar
 */
void setFan(bool on)
{
  fanState = on;
  if (on)
  {
    ledcWrite(1, 0);  // Una dirección a 0
    ledcWrite(2, 70); // Otra dirección al 27% de potencia (70/255)
  }
  else
  {
    ledcWrite(1, 0); // Ambas direcciones a 0 = apagado
    ledcWrite(2, 0);
  }
}

/**
 * Envía los datos de todos los sensores por puerto serial en formato JSON
 *
 * @param temp Temperatura en grados Celsius
 * @param humidity Humedad relativa en porcentaje
 * @param light Nivel de luz en porcentaje
 * @param fan Estado del ventilador (1=encendido, 0=apagado)
 */
void sendAllSensorData(float temp, float humidity, int light, int fan)
{
  unsigned long timestamp = millis() / 1000; // Timestamp en segundos

  // Crear array JSON con las lecturas de todos los sensores
  String json = "[";
  json += "{\"name\":\"temperature\",\"value\":" + String(temp) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"C\"},";
  json += "{\"name\":\"humidity\",\"value\":" + String(humidity) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"%\"},";
  json += "{\"name\":\"light\",\"value\":" + String(light) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"%\"},";
  json += "{\"name\":\"fan\",\"value\":" + String(fan) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"\"}";
  json += "]\n";

  Serial.println(json); // Enviar al puerto serial
}

/**
 * Procesa comandos recibidos por el puerto serial en formato JSON
 * Comandos soportados:
 * - {"command":"set_fan", "value":1}  → Enciende el ventilador
 * - {"command":"set_fan", "value":0}  → Apaga el ventilador
 * - {"command":"set_led", "value":1}  → Enciende la luz
 * - {"command":"set_led", "value":0}  → Apaga la luz
 */
void processSerialCommand()
{
  if (Serial.available())
  {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0)
      return;

    // Parsear el comando JSON
    StaticJsonDocument<128> doc;
    DeserializationError error = deserializeJson(doc, input);
    if (error)
    {
      Serial.println("{\"error\":\"JSON parse error\"}");
      return;
    }

    // Ejecutar el comando correspondiente
    const char *command = doc["command"];
    if (command)
    {
      // Comando para controlar el ventilador
      if (strcmp(command, "set_fan") == 0)
      {
        int value = doc["value"] | 0;
        setFan(value != 0); // Convertir a booleano
        Serial.printf("{\"result\":\"fan set to %d\"}\n", value);
      }
      // Comando para controlar la luz
      else if (strcmp(command, "set_led") == 0)
      {
        int value = doc["value"] | 0;
        digitalWrite(LIGHT_RELAY_PIN, value ? HIGH : LOW);
        Serial.printf("{\"result\":\"light set to %d\"}\n", value);
      }
    }
  }
}

/**
 * Configuración inicial del sistema
 */
void setup()
{
  // Inicializar comunicación serial a 115200 baudios
  Serial.begin(115200);

  // Configurar pines de entrada
  pinMode(LIGHT_SENSOR_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP); // Botón

  // Configurar pin de salida para el relé de luz
  pinMode(LIGHT_RELAY_PIN, OUTPUT);
  digitalWrite(LIGHT_RELAY_PIN, LOW); // Luz apagada por defecto

  // Inicializar motor y ventilador
  setupMotor();
  setFan(false); // Ventilador apagado por defecto
}

/**
 * Bucle principal del programa
 */
void loop()
{
  // Verificar y procesar comandos recibidos por serial
  processSerialCommand();

  // Control manual del ventilador mediante el botón físico
  bool currentButtonState = digitalRead(BUTTON_PIN);
  if (lastButtonState == HIGH && currentButtonState == LOW)
  {
    delay(50);                          // Debounce (anti-rebote) del botón
    if (digitalRead(BUTTON_PIN) == LOW) // Verificar que sigue presionado
    {
      setFan(!fanState); // Alternar estado del ventilador
      Serial.printf("Fan %s\n", fanState ? "ON" : "OFF");

      // Esperar a que se suelte el botón
      while (digitalRead(BUTTON_PIN) == LOW)
        delay(10);
    }
  }
  lastButtonState = currentButtonState; // Actualizar estado anterior

  // Lectura y envío periódico de datos de sensores
  unsigned long currentTime = millis();
  if (currentTime - lastSensorTime >= sensorInterval)
  {
    // Leer temperatura y humedad del sensor DHT11
    int chk = DHT11.read(DHT11PIN);
    float temperature = (float)DHT11.temperature;
    float humidity = (float)DHT11.humidity;

    // Leer sensor de luz y convertir a porcentaje (0-100%)
    int lightValue = analogRead(LIGHT_SENSOR_PIN);       // Valor raw (0-4095)
    int lightPercent = map(lightValue, 0, 4095, 0, 100); // Escalar a porcentaje

    // Enviar datos de todos los sensores por serial
    sendAllSensorData(temperature, humidity, lightPercent, fanState ? 1 : 0);

    // Actualizar timestamp para próximo envío
    lastSensorTime = currentTime;
  }
}