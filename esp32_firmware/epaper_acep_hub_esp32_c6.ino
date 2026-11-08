/**
 * epaper_acep_hub_esp32_c6.ino - Modo Carrusel Automático (1 min por pantalla)
 * Placa: Seeed Studio XIAO ESP32-C6 (RISC-V Wi-Fi 6) + Waveshare 7.3" ACeP 7 Colores (800x480)
 * 
 * MAPEO DE PINES PARA SEEED STUDIO XIAO ESP32-C6:
 * =======================================================================================
 * CABLE WAVESHARE (8 HILOS) | PIN EN LA XIAO ESP32-C6 | GPIO INTERNO | FUNCIÓN
 * ---------------------------------------------------------------------------------------
 * Rojo   (VCC)             | 3V3                     | 3.3V Out     | Alimentación (¡NUNCA 5V!)
 * Negro  (GND)             | GND                     | GND          | Tierra / Masa común
 * Azul   (DIN / MOSI)      | D10                     | GPIO 18      | Hardware SPI Data Out
 * Amarillo (CLK / SCK)     | D8                      | GPIO 19      | Hardware SPI Clock
 * Naranja (CS)             | D3                      | GPIO 21      | Chip Select
 * Verde  (DC)              | D1                      | GPIO 1       | Data / Command
 * Blanco (RST)             | D2                      | GPIO 2       | Hardware Reset
 * Violeta (BUSY)           | D0                      | GPIO 0       | Busy Status
 * =======================================================================================
 * 
 * MODO CARRUSEL AUTOMÁTICO (Sin necesidad de botón):
 *   - 1 minuto: Dashboard Principal (Clima InkyPi, Google Cal, Gastos, Domótica)
 *   - 1 minuto: Calendario Mensual Doodle (Patrick Hand)
 *   - 1 minuto por cada Foto activa / Cómic de Las Gaturrakas
 *   - 1 minuto: Modo Visitas (QR Wi-Fi CASA GATURRAKAS)
 *   - 1 minuto: Diagnóstico Técnico y Calibración ACeP
 *   - Vuelve a empezar en bucle infinito.
 * 
 * * Botón BOOT integrado en la placa (GPIO 9): Funciona como "Siguiente", permitiendo
 *   avanzar de pantalla inmediatamente sin esperar que pasen los 60 segundos.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <SPI.h>

#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #include "secrets.example.h"
#endif

// ================= CONFIGURACIÓN DE RED Y VPS =================
const char* WIFI_SSID        = SECRET_WIFI_SSID;
const char* WIFI_PASS        = SECRET_WIFI_PASS;
const char* VPS_BASE_URL     = SECRET_VPS_HOST "/api/screen.bin";
const char* FIRMWARE_VERSION = "1.1.0-carrusel";
const char* OTA_CHECK_URL    = SECRET_VPS_HOST "/api/ota/check";
const char* OTA_DOWNLOAD_URL = SECRET_VPS_HOST "/api/ota/download";

// ================= PINES SEEED STUDIO XIAO ESP32-C6 =================
#if defined(D10)
  #define EPD_MOSI_PIN  D10  // GPIO 18
  #define EPD_SCK_PIN   D8   // GPIO 19
  #define EPD_CS_PIN    D3   // GPIO 21
  #define EPD_DC_PIN    D1   // GPIO 1
  #define EPD_RST_PIN   D2   // GPIO 2
  #define EPD_BUSY_PIN  D0   // GPIO 0
#else
  #define EPD_MOSI_PIN  18
  #define EPD_SCK_PIN   19
  #define EPD_CS_PIN    21
  #define EPD_DC_PIN    1
  #define EPD_RST_PIN   2
  #define EPD_BUSY_PIN  0
#endif

// Botón BOOT integrado en la placa XIAO
#define BUTTON_PIN    9

// Tiempo de exhibición por cada pantalla: 60 segundos (1 minuto)
#define ROTATION_INTERVAL_MS 60000UL

static const size_t EXPECTED_BIN_BYTES = 192000; // 800 * 480 / 2
char lastEtag[40] = {0};

// ---------------- Primitivas de bajo nivel SPI E-Paper ----------------
void epdSendCommand(uint8_t cmd) {
  digitalWrite(EPD_DC_PIN, LOW);
  digitalWrite(EPD_CS_PIN, LOW);
  SPI.transfer(cmd);
  digitalWrite(EPD_CS_PIN, HIGH);
}

void epdSendData(uint8_t data) {
  digitalWrite(EPD_DC_PIN, HIGH);
  digitalWrite(EPD_CS_PIN, LOW);
  SPI.transfer(data);
  digitalWrite(EPD_CS_PIN, HIGH);
}

void epdWaitBusy() {
  while (digitalRead(EPD_BUSY_PIN) == LOW) {
    delay(10);
  }
}

void epdHardwareReset() {
  digitalWrite(EPD_RST_PIN, HIGH); delay(20);
  digitalWrite(EPD_RST_PIN, LOW);  delay(4);
  digitalWrite(EPD_RST_PIN, HIGH); delay(20);
  epdWaitBusy();
}

void epdInit7Color() {
  epdHardwareReset();
  epdSendCommand(0xAA); epdSendData(0x49); epdSendData(0x55); epdSendData(0x20); epdSendData(0x08); epdSendData(0x09); epdSendData(0x18);
  epdSendCommand(0x01); epdSendData(0x3F); epdSendData(0x00); epdSendData(0x32); epdSendData(0x2A); epdSendData(0x0E); epdSendData(0x2A);
  epdSendCommand(0x00); epdSendData(0x5F); epdSendData(0x69);
  epdSendCommand(0x03); epdSendData(0x00); epdSendData(0x54); epdSendData(0x00); epdSendData(0x44);
  epdSendCommand(0x05); epdSendData(0x40); epdSendData(0x1F); epdSendData(0x1F); epdSendData(0x2C);
  epdSendCommand(0x06); epdSendData(0x6F); epdSendData(0x1F); epdSendData(0x1F); epdSendData(0x22);
  epdSendCommand(0x08); epdSendData(0x6F); epdSendData(0x1F); epdSendData(0x1F); epdSendData(0x22);
  epdSendCommand(0x13); epdSendData(0x00); epdSendData(0x04);
  epdSendCommand(0x30); epdSendData(0x3C);
  epdSendCommand(0x41); epdSendData(0x00);
  epdSendCommand(0x50); epdSendData(0x3F);
  epdSendCommand(0x60); epdSendData(0x02); epdSendData(0x00);
  epdSendCommand(0x61); epdSendData(0x03); epdSendData(0x20); epdSendData(0x01); epdSendData(0xE0); // 800x480
  epdSendCommand(0x82); epdSendData(0x1E);
  epdSendCommand(0x84); epdSendData(0x00);
  epdSendCommand(0x86); epdSendData(0x00);
  epdSendCommand(0xE3); epdSendData(0x2F);
  epdSendCommand(0xCC); epdSendData(0x00);
  epdSendCommand(0x04); // Power ON
  epdWaitBusy();
}

void epdRefreshAndSleep() {
  epdSendCommand(0x12); // Display Refresh
  epdSendData(0x00);
  delay(100);
  epdWaitBusy();
  epdSendCommand(0x02); // Power OFF
  epdSendData(0x00);
  epdWaitBusy();
  epdSendCommand(0x07); // Deep Sleep del controlador e-Paper
  epdSendData(0xA5);
}

// Ciclo profundo anti-ghosting (Pulsación sostenida > 3s)
void epdDeepCleanCycle() {
  epdInit7Color();
  const uint8_t cleanColors[3] = {0x11, 0x00, 0x11}; // Blanco -> Negro -> Blanco
  for (int c = 0; c < 3; c++) {
    epdSendCommand(0x10);
    digitalWrite(EPD_DC_PIN, HIGH);
    digitalWrite(EPD_CS_PIN, LOW);
    for (size_t i = 0; i < EXPECTED_BIN_BYTES; i++) {
      SPI.transfer(cleanColors[c]);
    }
    digitalWrite(EPD_CS_PIN, HIGH);
    epdSendCommand(0x12);
    epdSendData(0x00);
    epdWaitBusy();
  }
  epdRefreshAndSleep();
}

void streamScreenFromVPS(const char* cycleMode) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Reconectando...");
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 8000) {
      delay(100);
    }
  }

  int rssi = WiFi.RSSI();
  String ipStr = WiFi.localIP().toString();

  String url = String(VPS_BASE_URL) + "?touches=" + String(cycleMode) + "&rssi=" + String(rssi) + "&ip=" + ipStr;

  HTTPClient http;
  http.begin(url);
  http.setTimeout(15000);

  const char* headerKeys[] = {"ETag", "X-Epaper-Mode", "X-Render-Ms"};
  http.collectHeaders(headerKeys, 3);

  int code = http.GET();
  if (code == HTTP_CODE_NOT_MODIFIED) {
    Serial.println("[EPAPER] Buffer idéntico (HTTP 304), sin cambios.");
    http.end();
    return;
  }

  if (code == HTTP_CODE_OK && http.getSize() == (int)EXPECTED_BIN_BYTES) {
    String currentMode = http.header("X-Epaper-Mode");
    String renderMs = http.header("X-Render-Ms");
    Serial.printf("[EPAPER] ¡Pantalla recibida! Modo: %s (Render: %s ms)\n", currentMode.c_str(), renderMs.c_str());

    WiFiClient* stream = http.getStreamPtr();
    epdInit7Color();
    epdSendCommand(0x10);

    uint8_t chunk[1024];
    size_t remaining = EXPECTED_BIN_BYTES;

    digitalWrite(EPD_DC_PIN, HIGH);
    digitalWrite(EPD_CS_PIN, LOW);
    while (http.connected() && remaining > 0) {
      size_t avail = stream->available();
      if (avail > 0) {
        size_t toRead = min(avail, min(remaining, sizeof(chunk)));
        size_t bytesRead = stream->readBytes(chunk, toRead);
        SPI.writeBytes(chunk, bytesRead);
        remaining -= bytesRead;
      } else {
        delay(1);
      }
    }
    digitalWrite(EPD_CS_PIN, HIGH);

    Serial.println("[EPAPER] Refrescando panel 7 colores Waveshare (esto toma ~15 segundos)...");
    epdRefreshAndSleep();
    Serial.println("[EPAPER] Refresco completo.");
  } else {
    Serial.printf("[ERROR] HTTP GET falló: código %d, tamaño recibido: %d bytes\n", code, http.getSize());
  }
  http.end();
}

// ---------------- Verificación y Ejecución de Firmware OTA ----------------
void checkForFirmwareUpdate() {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;
  String checkUrl = String(OTA_CHECK_URL) + "?version=" + String(FIRMWARE_VERSION);
  http.begin(client, checkUrl);
  http.setTimeout(4000);
  int httpCode = http.GET();
  if (httpCode == 200) {
    String payload = http.getString();
    if (payload.indexOf("update_available") >= 0 && payload.indexOf("true") >= 0) {
      Serial.println("[OTA] ¡Nueva versión detectada en VPS! Actualizando...");
      http.end();

      httpUpdate.rebootOnUpdate(true);
      t_httpUpdate_return ret = httpUpdate.update(client, OTA_DOWNLOAD_URL);
      if (ret == HTTP_UPDATE_FAILED) {
        Serial.printf("[OTA] Error (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
      }
      return;
    }
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=======================================================");
  Serial.println("  E-Paper Hub Waveshare 7.3 ACeP (XIAO ESP32-C6)");
  Serial.println("  Modo: CARRUSEL CONTINUO (1 minuto por pantalla)");
  Serial.println("=======================================================");

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(EPD_CS_PIN, OUTPUT);
  pinMode(EPD_RST_PIN, OUTPUT);
  pinMode(EPD_DC_PIN, OUTPUT);
  pinMode(EPD_BUSY_PIN, INPUT);

  // Inicializar hardware SPI en XIAO ESP32-C6 (SCK=D8, MOSI=D10)
  SPI.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, EPD_CS_PIN);
  SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));

  Serial.printf("[WIFI] Conectando a red: %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 15000) {
    delay(200);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] ¡Conectado con éxito! IP: " + WiFi.localIP().toString());
    checkForFirmwareUpdate();

    // Iniciar carrusel mostrando la primera pantalla de inmediato
    Serial.println("\n[CARRUSEL] Cargando primera pantalla...");
    streamScreenFromVPS("auto");
  } else {
    Serial.println("\n[WIFI] Error de conexión Wi-Fi. Reintentará en el loop.");
  }
}

void loop() {
  // Cuenta regresiva de 60 segundos (1 minuto) en el Monitor Serie
  Serial.println("\n-----------------------------------------------------------");
  Serial.println("[CARRUSEL] Mostrando pantalla actual durante 1 minuto (60s)...");
  Serial.println("[TIP] Podés presionar el botón BOOT en la XIAO para saltar a la siguiente.");

  uint32_t waitStart = millis();
  int lastSecPrinted = -1;

  while (millis() - waitStart < ROTATION_INTERVAL_MS) {
    // Si presionan el botón BOOT integrado, avanza inmediatamente
    if (digitalRead(BUTTON_PIN) == LOW) {
      Serial.println("\n[BOTÓN BOOT] ¡Presionado! Saltando de pantalla inmediatamente...");
      delay(300); // debounce
      break;
    }

    int remainingSec = (ROTATION_INTERVAL_MS - (millis() - waitStart)) / 1000;
    if (remainingSec % 15 == 0 && remainingSec != lastSecPrinted && remainingSec > 0) {
      Serial.printf("[CARRUSEL] Siguiente pantalla en: %d segundos...\n", remainingSec);
      lastSecPrinted = remainingSec;
    }
    delay(100);
  }

  // Al cumplirse el minuto (o presionar el botón), solicitar la siguiente pantalla al servidor
  Serial.println("\n[CARRUSEL] >> Avanzando a la siguiente pantalla del ciclo...");
  streamScreenFromVPS("auto");
}
