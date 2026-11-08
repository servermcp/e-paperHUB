/**
 * epaper_acep_hub_esp32.ino — Firmware Ultrabajo Consumo para ESP32 + E-Paper 7.3" ACeP (800x480)
 * Filosofía: CERO renderizado local. Descarga stream HTTP de 192.000 bytes (4-bit nibbles)
 * desde el VPS de Tokyo y lo inyecta directo vía SPI al controlador ACeP (GDEY073D46 / Waveshare 7.3"F).
 *
 * Interacción por Pin Táctil Capacitivo (T0 / GPIO 4):
 *   - 1 toque: Dashboard Principal
 *   - 2 toques: Calendario Mensual Minimalista (Patrick Hand + Google Calendar)
 *   - 3 toques: Modo Marco de Fotos (Carrusel 7 Colores / Cómic del Día)
 *   - 4 toques: Modo Visitas (QR Wi-Fi CASA GATURRAKAS)
 *   - 5 toques: Pantalla de Diagnóstico Técnico y Calibración ACeP
 *   - Toque largo (3-5 s): Ciclo físico de limpieza profunda anti-ghosting
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <SPI.h>
#include "esp_sleep.h"

#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #include "secrets.example.h"
#endif

// ================= CONFIGURACIÓN DE RED Y VPS =================
const char* WIFI_SSID     = SECRET_WIFI_SSID;
const char* WIFI_PASS     = SECRET_WIFI_PASS;
const char* VPS_BASE_URL  = SECRET_VPS_HOST "/api/screen.bin";
const char* FIRMWARE_VERSION = "1.0.0";
const char* OTA_CHECK_URL    = SECRET_VPS_HOST "/api/ota/check";
const char* OTA_DOWNLOAD_URL = SECRET_VPS_HOST "/api/ota/download";

// ================= PINES SPI DISPLAY E-PAPER 7.3" ACeP ========
#define EPD_SCK_PIN   18
#define EPD_MOSI_PIN  23
#define EPD_CS_PIN    5
#define EPD_RST_PIN   16
#define EPD_DC_PIN    17
#define EPD_BUSY_PIN  4

// Pin táctil capacitivo para Wakeup + Conteo de toques (T3 = GPIO 15)
#define TOUCH_WAKE_PAD    T3
#define TOUCH_WAKE_GPIO   15
#define TOUCH_THRESHOLD   40

// Pin ADC de lectura de batería LiPo (divisor 1/2 en GPIO 35)
#define VBAT_ADC_PIN      35

// Intervalo de Deep Sleep automático: 15 minutos
#define SLEEP_MINUTES     15ULL
#define uS_TO_S_FACTOR    1000000ULL

static const size_t EXPECTED_BIN_BYTES = 192000; // 800 * 480 / 2
RTC_DATA_ATTR char lastEtag[40] = {0};

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

// Ciclo profundo anti-ghosting (Toque largo 3-5s)
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

float readBatteryVoltage() {
  uint16_t raw = analogRead(VBAT_ADC_PIN);
  return (raw / 4095.0f) * 3.3f * 2.0f * 1.06f;
}

// Detecta 1..4 toques o toque largo (retorna 99 para toque largo >= 3.2s)
int detectCapacitiveTouches() {
  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TOUCHPAD) {
    return 0; // Despertó por RTC Timer
  }
  uint32_t pressStart = millis();
  while (touchRead(TOUCH_WAKE_PAD) < TOUCH_THRESHOLD) {
    if (millis() - pressStart > 3200) {
      return 99; // Toque largo -> Anti-ghosting
    }
    delay(20);
  }
  int touches = 1;
  uint32_t windowEnd = millis() + 1400;
  bool wasReleased = true;
  while (millis() < windowEnd && touches < 4) {
    bool isPressed = (touchRead(TOUCH_WAKE_PAD) < TOUCH_THRESHOLD);
    if (isPressed && wasReleased) {
      touches++;
      wasReleased = false;
      windowEnd = millis() + 900;
    } else if (!isPressed) {
      wasReleased = true;
    }
    delay(25);
  }
  return touches;
}

void streamScreenFromVPS(int touches) {
  float vbat = readBatteryVoltage();
  int rssi = WiFi.RSSI();
  String ipStr = WiFi.localIP().toString();

  String url = String(VPS_BASE_URL) + "?vbat=" + String(vbat, 2) + "&rssi=" + String(rssi) + "&ip=" + ipStr;
  if (touches >= 1 && touches <= 5) {
    url += "&touches=" + String(touches);
  }

  HTTPClient http;
  http.begin(url);
  if (touches == 0 && strlen(lastEtag) > 0) {
    http.addHeader("If-None-Match", String(lastEtag));
  }

  const char* headerKeys[] = {"ETag", "X-Epaper-Mode"};
  http.collectHeaders(headerKeys, 2);

  int code = http.GET();
  if (code == HTTP_CODE_NOT_MODIFIED) {
    http.end();
    return; // El buffer no cambió, ahorramos refresco de pantalla
  }

  if (code == HTTP_CODE_OK && http.getSize() == (int)EXPECTED_BIN_BYTES) {
    String newEtag = http.header("ETag");
    if (newEtag.length() > 0 && newEtag.length() < sizeof(lastEtag)) {
      newEtag.toCharArray(lastEtag, sizeof(lastEtag));
    }

    WiFiClient* stream = http.getStreamPtr();
    epdInit7Color();
    epdSendCommand(0x10); // Iniciar escritura en GRAM del panel

    uint8_t chunk[1024];
    size_t remaining = EXPECTED_BIN_BYTES;

    digitalWrite(EPD_DC_PIN, HIGH);
    digitalWrite(EPD_CS_PIN, LOW);
    while (http.connected() && remaining > 0) {
      size_t avail = stream->available();
      if (avail > 0) {
        size_t toRead = min(avail, min(remaining, sizeof(chunk)));
        size_t bytesRead = stream->readBytes(chunk, toRead);
        SPI.writeBytes(chunk, bytesRead); // Envío por hardware SPI DMA
        remaining -= bytesRead;
      } else {
        delay(1);
      }
    }
    digitalWrite(EPD_CS_PIN, HIGH);
    epdRefreshAndSleep();
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
    if (payload.indexOf("\"update_available\":true") >= 0 || payload.indexOf("\"update_available\": true") >= 0) {
      Serial.println("[OTA] ¡Nueva versión detectada en el servidor VPS! Iniciando actualización...");
      http.end();

      httpUpdate.rebootOnUpdate(true);
      t_httpUpdate_return ret = httpUpdate.update(client, OTA_DOWNLOAD_URL);
      if (ret == HTTP_UPDATE_FAILED) {
        Serial.printf("[OTA] Error en actualización (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
      }
      return;
    }
  }
  http.end();
}

void setup() {
  pinMode(EPD_CS_PIN, OUTPUT);
  pinMode(EPD_RST_PIN, OUTPUT);
  pinMode(EPD_DC_PIN, OUTPUT);
  pinMode(EPD_BUSY_PIN, INPUT);
  SPI.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, EPD_CS_PIN);
  SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));

  int action = detectCapacitiveTouches();
  if (action == 99) {
    epdDeepCleanCycle();
    action = 1; // Luego de limpiar, pintar el Dashboard
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 12000) {
    delay(100);
  }

  if (WiFi.status() == WL_CONNECTED) {
    // 1. Chequear actualización OTA antes de pintar
    checkForFirmwareUpdate();

    // 2. Descargar pantalla del VPS
    streamScreenFromVPS(action);
    WiFi.disconnect(true);
  }

  // Configurar Touch Wakeup + Timer Wakeup y entrar en Deep Sleep (~14 uA)
  touchAttachInterrupt(TOUCH_WAKE_PAD, [](){}, TOUCH_THRESHOLD);
  esp_sleep_enable_touchpad_wakeup();
  esp_sleep_enable_timer_wakeup(SLEEP_MINUTES * 60ULL * uS_TO_S_FACTOR);
  esp_deep_sleep_start();
}

void loop() {}
