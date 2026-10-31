#include <Arduino.h>
#include <HX711.h>
#include <Preferences.h>
#include <esp_system.h>
#include <cstdlib>
#include <cstring>
#include "ScaleCore.h"

// Safe default: fixture samples, no physical sensor required. Set to 0 for HX711.
#ifndef AGROSCAN_SIMULATION
#define AGROSCAN_SIMULATION 1
#endif
constexpr bool SIMULATION = AGROSCAN_SIMULATION != 0;
constexpr int PIN_DT = 32, PIN_SCK = 33;
constexpr uint32_t SAMPLE_MS = 100, REPORT_MS = 500;
struct StoredCalibration { uint32_t magic; agroscan::Calibration value; };
constexpr uint32_t CAL_MAGIC = 0x41475331;
agroscan::ScaleCore scale;
HX711 hx;
Preferences prefs;
bool storageReady = false, simConnected = true, simNoise = false;
double simGrams = 0;
char bootId[33], deviceId[40], command[80];
size_t commandSize = 0;
bool commandOverflow = false;
uint32_t lastSample = 0, lastReport = 0, seq = 0;

void event(const char* status) {
  Serial.printf("{\"type\":\"event\",\"status\":\"%s\",\"simulated\":%s}\n", status, SIMULATION?"true":"false");
}
void saveCalibration() {
  if (SIMULATION) { event("simulation_not_saved"); return; }
  StoredCalibration record{}; record.magic = CAL_MAGIC; record.value = scale.calibration();
  if (!storageReady || prefs.putBytes("cal", &record, sizeof(record)) != sizeof(record)) event("storage_error");
  else event("calibration_saved");
}
bool parseNumber(const char* text, double& result) {
  char* end = nullptr; result = strtod(text, &end);
  return end != text && *end == '\0' && std::isfinite(result);
}
void executeCommand(char* line) {
  double value;
  if (!strcmp(line,"TARE")) event(scale.tare(millis())?"tare_ok":"tare_rejected_wait_for_stable_empty_platform");
  else if (!strncmp(line,"CAL ",4) && parseNumber(line+4,value)) {
    if (scale.calibrate(value,millis())) { event("calibration_ok"); saveCalibration(); }
    else event("calibration_rejected_check_zero_mass_and_stability");
  } else if (!strcmp(line,"SAVE")) {
    if(scale.calibration().revision) saveCalibration(); else event("uncalibrated");
  } else if (!strcmp(line,"STATUS")) {
    const auto& c=scale.calibration();
    Serial.printf("{\"type\":\"calibration\",\"simulated\":%s,\"offset\":%.4f,\"counts_per_gram\":%.8f,\"revision\":%lu}\n",SIMULATION?"true":"false",c.offset,c.counts_per_gram,(unsigned long)c.revision);
  } else if (SIMULATION && !strncmp(line,"WEIGHT ",7) && parseNumber(line+7,value) && value>=0 && value<=5000) {
    simGrams=value;event("simulation_weight_changed");
  } else if (SIMULATION && !strcmp(line,"DISCONNECT")) {simConnected=false;scale.fault();event("simulation_disconnected");}
  else if (SIMULATION && !strcmp(line,"CONNECT")) {simConnected=true;event("simulation_connected");}
  else if (SIMULATION && !strcmp(line,"NOISE ON")) {simNoise=true;event("simulation_noise_on");}
  else if (SIMULATION && !strcmp(line,"NOISE OFF")) {simNoise=false;event("simulation_noise_off");}
  else event("unknown_or_invalid_command");
}
void pollCommands() {
  // Bounded work per loop; malformed/overlong commands never execute a suffix.
  for (int budget=0;Serial.available() && budget<96;++budget) {
    char ch=Serial.read(); if(ch=='\r')continue;
    if(ch=='\n') {
      if(commandOverflow) event("command_too_long");
      else if(commandSize) {command[commandSize]='\0';executeCommand(command);}
      commandSize=0;commandOverflow=false;
    } else if(commandSize<sizeof(command)-1 && !commandOverflow) command[commandSize++]=ch;
    else commandOverflow=true;
  }
}
void report(uint32_t now) {
  auto r=scale.reading(now);
  const auto& c=scale.calibration();
  // Only measurement holds the communicated backend fields; diagnostics stay outside it.
  Serial.printf("{\"type\":\"telemetry\",\"simulated\":%s,\"uptime_ms\":%lu,\"status\":\"%s\",\"raw_mean\":",SIMULATION?"true":"false",(unsigned long)now,r.status);
  if(scale.fresh(now))Serial.printf("%.3f",scale.mean());else Serial.print("null");
  Serial.print(",\"measurement\":");
  if (!r.valid || seq == UINT32_MAX) Serial.print("null");
  else {
    ++seq;

Serial.printf(
    "{\"schema_version\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\",\"seq\":%lu,\"weight_g\":%.3f,\"stable\":%s,\"zero_confirmed\":%s,\"calibration_version\":\"%s%s-%lu\"}",
    deviceId,
    bootId,
    (unsigned long)seq,
    r.weight_g,
    r.stable ? "true" : "false",
    scale.zeroConfirmed() ? "true" : "false",
    SIMULATION ? "simulated-" : "cal-",
    bootId,
    (unsigned long)c.revision
);
  }
  Serial.println("}");
}
void setup() {
  Serial.begin(115200);
  snprintf(bootId,sizeof(bootId),"%08lx%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());
  snprintf(deviceId,sizeof(deviceId),"%s%012llx",SIMULATION?"simulator-esp32-":"esp32-",(unsigned long long)ESP.getEfuseMac());
  if (SIMULATION) {
    // Fixture only: these numbers are never a real calibration and never enter NVS.
    agroscan::Calibration c; c.offset=100000;c.counts_per_gram=100;c.revision=1;scale.restore(c);
    event("simulation_ready_tare_empty_platform");
  } else {
    hx.begin(PIN_DT,PIN_SCK,128);
    storageReady=prefs.begin("agroscan",false);
    StoredCalibration record{};
    if(storageReady && prefs.getBytesLength("cal")==sizeof(record)
        && prefs.getBytes("cal",&record,sizeof(record))==sizeof(record) && record.magic==CAL_MAGIC) scale.restore(record.value);
    if(!storageReady)event("storage_error");
    event("hardware_ready_tare_empty_platform");
  }
}
void loop() {
  uint32_t now=millis();
  if(uint32_t(now-lastSample)>=SAMPLE_MS) {
    lastSample=now;
    if(SIMULATION) {
      if(simConnected) {
        double noise=simNoise?((now/SAMPLE_MS)%2?400:-400):0;
        scale.add((int32_t)(100000+simGrams*100+noise),now);
      }
    } else if(hx.is_ready()) scale.add((int32_t)hx.read(),now);
    // No read_average/tare loops waiting indefinitely for DOUT.
  }
  pollCommands();
  if(uint32_t(now-lastReport)>=REPORT_MS) {lastReport=now;report(now);}
}
