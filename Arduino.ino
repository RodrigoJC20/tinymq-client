/*
 * ESP32 Smart Home Sensor Integration (Versión Serial)
 *
 * Este programa recoge datos de sensores y los imprime en formato JSON por el monitor serial.
 * Se eliminó toda la lógica de red (WiFi y servidor TCP).
 */

#include <dht11.h>
#include <ESP32_Servo.h>
#include <time.h>
#include <ArduinoJson.h> // Asegúrate de instalar la librería ArduinoJson

// Sensor pins
#define DHT11PIN 17
#define LIGHT_SENSOR_PIN 34
#define BUTTON_PIN 5
#define MOTOR_PIN1 19
#define MOTOR_PIN2 18
#define TRIG_PIN 12
#define ECHO_PIN 13
#define SERVO_PIN 26

// Variables
dht11 DHT11;
Servo myservo;

bool fanState = false;
bool servoOpen = false;
bool lastButtonState = HIGH;
unsigned long lastSensorTime = 0;
const unsigned long sensorInterval = 2000;

void setupMotor()
{
  pinMode(MOTOR_PIN1, OUTPUT);
  pinMode(MOTOR_PIN2, OUTPUT);
  digitalWrite(MOTOR_PIN1, LOW);
  digitalWrite(MOTOR_PIN2, LOW);

  ledcSetup(1, 1200, 8);
  ledcAttachPin(MOTOR_PIN1, 1);
  ledcSetup(2, 1200, 8);
  ledcAttachPin(MOTOR_PIN2, 2);

  ledcWrite(1, 0);
  ledcWrite(2, 0);
}

void setFan(bool on)
{
  fanState = on;
  if (on)
  {
    ledcWrite(1, 0);
    ledcWrite(2, 70);
  }
  else
  {
    ledcWrite(1, 0);
    ledcWrite(2, 0);
  }
}

int readDistance()
{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH);
  int distance = duration / 58;
  return distance;
}

void sendAllSensorData(float temp, float humidity, int light, int fan, int distance, int servo)
{
  unsigned long timestamp = millis() / 1000;

  String json = "[";
  json += "{\"name\":\"temperature\",\"value\":" + String(temp) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"C\"},";
  json += "{\"name\":\"humidity\",\"value\":" + String(humidity) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"%\"},";
  json += "{\"name\":\"light\",\"value\":" + String(light) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"%\"},";
  json += "{\"name\":\"fan\",\"value\":" + String(fan) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"\"},";
  json += "{\"name\":\"distance\",\"value\":" + String(distance) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"cm\"},";
  json += "{\"name\":\"servo\",\"value\":" + String(servo) + ",\"timestamp\":" + String(timestamp) + ",\"units\":\"\"}";
  json += "]\n";

  Serial.println(json);
}

void forceSetFan(bool on)
{
  // Asegurar estado del ventilador independientemente de interferencias
  fanState = on;

  // Apagar completamente antes de encender (estabiliza el circuito)
  ledcWrite(1, 0);
  ledcWrite(2, 0);
  delay(50); // Pequeña pausa para estabilización

  // Configurar al estado deseado
  if (on)
  {
    ledcWrite(1, 0);
    ledcWrite(2, 70);
  }
}

// REEMPLAZAR LA FUNCIÓN processSerialCommand
void processSerialCommand()
{
  if (Serial.available())
  {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0)
      return;

    StaticJsonDocument<128> doc;
    DeserializationError error = deserializeJson(doc, input);
    if (error)
    {
      Serial.println("{\"error\":\"JSON parse error\"}");
      return;
    }

    const char *command = doc["command"];
    if (command)
    {
      if (strcmp(command, "set_fan") == 0)
      {
        int value = doc["value"] | 0;
        forceSetFan(value == 1);
        Serial.printf("{\"result\":\"fan set to %d\"}\n", value);
      }
      else if (strcmp(command, "set_servo") == 0)
      {
        int value = doc["value"] | 0;
        bool previousFanState = fanState;

        // GUARDAR ESTADO DE PINES DEL VENTILADOR
        int previousPwmValue = ledcRead(2);

        // MOVER SERVO
        if (value == 1)
        {
          myservo.write(80);
          servoOpen = true;
        }
        else
        {
          myservo.write(180);
          servoOpen = false;
        }

        // ESPERAR A QUE EL SERVO TERMINE DE MOVERSE
        delay(200);

        // RESTAURAR ESTADO DEL VENTILADOR FORZADAMENTE
        forceSetFan(previousFanState);

        Serial.printf("{\"result\":\"servo set to %d\"}\n", value);
      }
    }
  }
}

void setup()
{
  Serial.begin(115200);

  pinMode(LIGHT_SENSOR_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  setupMotor();
  fanState = false;

  myservo.attach(SERVO_PIN);
  myservo.write(180);

  setFan(false);
}

void loop()
{
  processSerialCommand(); // <-- Agrega esta línea al inicio del loop

  bool currentButtonState = digitalRead(BUTTON_PIN);
  if (lastButtonState == HIGH && currentButtonState == LOW)
  {
    delay(50);
    if (digitalRead(BUTTON_PIN) == LOW)
    {
      setFan(!fanState);
      Serial.printf("Fan %s\n", fanState ? "ON" : "OFF");
      while (digitalRead(BUTTON_PIN) == LOW)
        delay(10);
    }
  }
  lastButtonState = currentButtonState;

  int distance = readDistance();
  if (distance <= 7)
  {
    if (!servoOpen)
    {
      bool previousFanState = fanState;

      // GUARDAR ESTADO DE PINES DEL VENTILADOR
      int previousPwmValue = ledcRead(2);

      // MOVER SERVO
      myservo.write(80);
      servoOpen = true;
      Serial.println("Object detected, opening servo");

      // ESPERAR A QUE EL SERVO TERMINE DE MOVERSE
      delay(200);

      // RESTAURAR VENTILADOR FORZADAMENTE
      forceSetFan(previousFanState);
    }
  }
  else
  {
    if (servoOpen)
    {
      bool previousFanState = fanState;

      // GUARDAR ESTADO DE PINES DEL VENTILADOR
      int previousPwmValue = ledcRead(2);

      // MOVER SERVO
      myservo.write(180);
      servoOpen = false;
      Serial.println("No object detected, closing servo");

      // ESPERAR A QUE EL SERVO TERMINE DE MOVERSE
      delay(200);

      // RESTAURAR VENTILADOR FORZADAMENTE
      forceSetFan(previousFanState);
    }
  }
}