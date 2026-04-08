/*
  Cultivee Modulo - Camera
  Captura JPEG, streaming MJPEG, upload para servidor
*/

#ifndef MOD_CAM_H
#define MOD_CAM_H
#ifdef MOD_CAM

// ===================== INIT =====================

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_UXGA;  // Init na resolucao maxima para alocar buffer suficiente
  config.jpeg_quality = 10;
  config.fb_count = 1;                  // UXGA precisa de fb_count=1 (PSRAM limitada)
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;  // Sempre pega o frame mais recente

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Erro camera: 0x%x\n", err);
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_vflip(s, 0);
  s->set_hmirror(s, 0);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_wb_mode(s, 0);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 1);
  s->set_gain_ctrl(s, 1);
  s->set_raw_gma(s, 1);
  s->set_lenc(s, 1);
  s->set_saturation(s, 0);

  // Flush frames iniciais (auto-exposure/WB estabiliza)
  for (int i = 0; i < 5; i++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) esp_camera_fb_return(fb);
    delay(100);
  }

  // Reduz para VGA como resolucao padrao (UXGA sob demanda para captura)
  s->set_framesize(s, FRAMESIZE_VGA);
  s->set_quality(s, 12);

  Serial.println("Camera OK!");
  return true;
}

// ===================== CAPTURE HELPERS =====================

// Muda para resolucao de captura, tira foto, e volta para VGA
camera_fb_t* captureHighRes() {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) return nullptr;

  // Seta resolucao e qualidade de captura
  s->set_framesize(s, captureFrameSize);
  s->set_quality(s, captureQuality);

  // Flush buffers da resolucao anterior
  for (int i = 0; i < 3; i++) {
    camera_fb_t* old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
  }
  delay(150);  // Aguarda sensor estabilizar na nova resolucao

  camera_fb_t* fb = esp_camera_fb_get();
  return fb;
}

void restoreDefaultRes() {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) return;
  s->set_framesize(s, FRAMESIZE_VGA);
  s->set_quality(s, 12);
  for (int i = 0; i < 2; i++) {
    camera_fb_t* old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
  }
}

// ===================== ROUTE HANDLERS =====================

void handleCapture() {
  if (!cameraReady) {
    sendCORS();
    server.send(503, "application/json", "{\"error\":\"Camera nao inicializada\"}");
    return;
  }

  camera_fb_t* fb = captureHighRes();
  if (!fb) {
    restoreDefaultRes();
    sendCORS();
    server.send(500, "application/json", "{\"error\":\"Erro ao capturar\"}");
    return;
  }

  WiFiClient client = server.client();
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.println("Content-Length: " + String(fb->len));
  client.println("Access-Control-Allow-Origin: *");
  client.println("Cache-Control: no-cache, no-store");
  client.println("Connection: close");
  client.println();

  uint8_t* buf = fb->buf;
  size_t remaining = fb->len;
  while (remaining > 0) {
    size_t chunk = remaining > 4096 ? 4096 : remaining;
    client.write(buf, chunk);
    buf += chunk;
    remaining -= chunk;
  }

  size_t sent = fb->len;
  esp_camera_fb_return(fb);
  restoreDefaultRes();
  Serial.printf("Capture: %d bytes\n", sent);
}

void handleStream() {
  if (!cameraReady) {
    sendCORS();
    server.send(503, "text/plain", "Camera nao inicializada");
    return;
  }

  localStreamActive = true;
  Serial.println("Stream local: INICIADO");

  // Reduz resolucao e qualidade para stream fluido
  sensor_t* s = esp_camera_sensor_get();
  framesize_t prevSize = FRAMESIZE_VGA;
  int prevQuality = 12;
  if (s) {
    prevSize = s->status.framesize;
    prevQuality = s->status.quality;
    s->set_framesize(s, FRAMESIZE_QVGA);  // 320x240 — leve para AP
    s->set_quality(s, 15);                  // Compressao maior ~3-8KB/frame
  }
  // Flush buffers antigos da resolucao anterior
  for (int i = 0; i < 3; i++) {
    camera_fb_t* old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
  }

  WiFiClient client = server.client();
  client.setNoDelay(true);
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Access-Control-Allow-Origin: *");
  client.println("Cache-Control: no-cache");
  client.println("Connection: close");
  client.println();

  unsigned long streamStart = millis();
  while (client.connected() && (millis() - streamStart < 300000)) {  // Max 5 min
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) { delay(5); continue; }

    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n", fb->len);

    uint8_t* buf = fb->buf;
    size_t remaining = fb->len;
    while (remaining > 0 && client.connected()) {
      size_t chunk = remaining > 16384 ? 16384 : remaining;
      client.write(buf, chunk);
      buf += chunk;
      remaining -= chunk;
    }
    client.print("\r\n");
    esp_camera_fb_return(fb);
    delay(30);  // ~25-30 FPS alvo
  }

  // Restaura resolucao original para capturas
  if (s) {
    s->set_framesize(s, prevSize);
    s->set_quality(s, prevQuality);
    for (int i = 0; i < 3; i++) {
      camera_fb_t* old = esp_camera_fb_get();
      if (old) esp_camera_fb_return(old);
    }
  }

  localStreamActive = false;
  Serial.println("Stream local: PARADO");
}

// ===================== STATUS JSON =====================

String cam_register_json() {
  return "\"camera_ready\":" + String(cameraReady ? "true" : "false");
}

String cam_status_json() {
  return ",\"camera_ready\":" + String(cameraReady ? "true" : "false");
}

// ===================== DASHBOARD HTML =====================

String cam_dashboard_html() {
  String html = "";
  html += "<div class='card' style='padding:0;overflow:hidden'>";
  html += "<div onclick='camTgl()' style='display:flex;justify-content:space-between;align-items:center;padding:14px;cursor:pointer'>";
  html += "<div style='display:flex;align-items:center;gap:8px'>";
  html += "<span style='width:8px;height:8px;border-radius:50%;background:" + String(cameraReady ? "#27ae60" : "#e74c3c") + "'></span>";
  html += "<b style='font-size:0.9rem'>Camera</b>";
  html += "<span style='color:#888;font-size:0.8rem'>" + String(cameraReady ? "Pronta" : "Offline") + "</span>";
  html += "</div>";
  html += "<svg id='cam-chv' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='#888' stroke-width='2' style='transition:transform 0.25s'><polyline points='6 9 12 15 18 9'/></svg>";
  html += "</div>";
  html += "<div id='cam-body' style='display:none;padding:0 14px 14px;border-top:1px solid #2a2d35'>";
  html += "<div id='cam-img' style='background:#1a1d23;border-radius:8px;min-height:120px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin-top:10px'>";
  html += "<span style='color:#555;font-size:0.85rem'>Toque em Capturar</span>";
  html += "</div>";
  html += "<div style='display:flex;gap:8px;margin-top:8px'>";
  html += "<button id='cam-btn' onclick='cap()' style='flex:1;padding:10px;border-radius:10px;border:1px solid #3a3d45;background:#2a2d35;color:#aaa;font-weight:600;font-size:0.85rem;cursor:pointer' " + String(cameraReady ? "" : "disabled") + ">&#128247; Capturar</button>";
  html += "<button id='live-btn' onclick='live()' style='flex:1;padding:10px;border-radius:10px;border:1px solid #3a3d45;background:#2a2d35;color:#aaa;font-weight:600;font-size:0.85rem;cursor:pointer' " + String(cameraReady ? "" : "disabled") + ">&#127909; Ao Vivo</button>";
  html += "</div>";
  // Dropdowns resolucao + qualidade
  html += "<div style='display:flex;gap:8px;margin-top:8px'>";
  html += "<div style='flex:1'><label style='font-size:0.7rem;color:#888'>Resolucao</label>";
  html += "<select id='cam-res' onchange='setRes(this.value)' style='width:100%;padding:8px;border:1px solid #3a3d45;border-radius:8px;font-size:0.85rem;background:#2a2d35;color:#aaa'>";
  html += "<option value='VGA'>640x480</option><option value='SVGA' selected>800x600</option><option value='UXGA'>1600x1200</option></select></div>";
  html += "<div style='flex:1'><label style='font-size:0.7rem;color:#888'>Qualidade</label>";
  html += "<select id='cam-qual' onchange='setQual(this.value)' style='width:100%;padding:8px;border:1px solid #3a3d45;border-radius:8px;font-size:0.85rem;background:#2a2d35;color:#aaa'>";
  html += "<option value='8' selected>Alta (q8)</option><option value='10'>Boa (q10)</option><option value='15'>Normal (q15)</option></select></div></div>";
  // Captura Agendada (offline — timer local no JS)
  html += "<div style='margin-top:12px;padding-top:12px;border-top:1px solid #2a2d35'>";
  html += "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>";
  html += "<b style='font-size:0.85rem;color:#e0e0e0'>Captura Agendada</b>";
  html += "<span id='sched-badge' style='display:none;font-size:0.65rem;font-weight:700;color:#27ae60;padding:2px 8px;border-radius:99px;background:rgba(39,174,96,0.15);border:1px solid rgba(39,174,96,0.3)'>&#9679; Gravando</span>";
  html += "</div>";
  html += "<div style='margin-bottom:8px'>";
  html += "<label style='font-size:0.75rem;color:#888'>Intervalo</label>";
  html += "<select id='sched-interval' style='width:100%;padding:8px;border:1px solid #3a3d45;border-radius:8px;font-size:0.85rem;background:#2a2d35;color:#aaa'>";
  html += "<option value='10'>10 segundos</option><option value='30'>30 segundos</option><option value='60'>1 minuto</option>";
  html += "<option value='300'>5 minutos</option><option value='600' selected>10 minutos</option>";
  html += "<option value='1800'>30 minutos</option><option value='3600'>1 hora</option></select></div>";
  html += "<div id='sched-progress' style='display:none;margin-bottom:8px'>";
  html += "<span id='sched-label' style='font-size:0.75rem;color:#888'>Proxima captura em --:--</span>";
  html += "<div style='height:4px;background:#2a2d35;border-radius:2px;overflow:hidden;margin-top:4px'><div id='sched-bar' style='height:100%;background:#27ae60;border-radius:2px;width:0%;transition:width 1s linear'></div></div></div>";
  html += "<button id='sched-btn' onclick='schedToggle()' style='width:100%;padding:10px;border-radius:10px;border:1px solid #27ae60;background:transparent;color:#27ae60;font-weight:600;font-size:0.85rem;cursor:pointer' " + String(cameraReady ? "" : "disabled") + ">&#9654; Iniciar Gravacao</button>";
  html += "</div>";
  html += "</div></div>";
  return html;
}

String cam_dashboard_js() {
  return R"rawliteral(
var liveOn=false,liveImg=null;
function live(){
var im=document.getElementById('cam-img'),b=document.getElementById('live-btn');
if(liveOn){
liveOn=false;
if(liveImg){liveImg.src='';liveImg=null}
im.innerHTML='<span style="color:#555;font-size:0.85rem">Toque em Capturar</span>';
b.innerHTML='&#127909; Ao Vivo';
b.style.borderColor='#3a3d45';b.style.background='#2a2d35';b.style.color='#aaa';
} else {
liveOn=true;
var img=document.createElement('img');
img.src='/stream?t='+Date.now();img.style.cssText='width:100%;border-radius:8px';
img.onerror=function(){if(liveOn){setTimeout(function(){img.src='/stream?t='+Date.now()},1000)}};
liveImg=img;
im.innerHTML='';im.appendChild(img);
b.innerHTML='&#9632; Parar';
b.style.borderColor='#e74c3c';b.style.background='rgba(231,76,60,0.1)';b.style.color='#e74c3c';
}
}
function camTgl(){
var b=document.getElementById('cam-body'),c=document.getElementById('cam-chv');
var open=b.style.display==='none';
b.style.display=open?'block':'none';
c.style.transform=open?'rotate(180deg)':'';
}
function cap(){
var b=document.getElementById('cam-btn'),im=document.getElementById('cam-img');
b.disabled=true;b.innerHTML='&#9203; Capturando...';
im.innerHTML='<div style="padding:20px;text-align:center"><div style="width:24px;height:24px;border:3px solid #333;border-top-color:#27ae60;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto"></div><p style="color:#555;margin-top:8px;font-size:0.8rem">Aguardando imagem...</p></div>';
fetch('/capture').then(r=>{if(!r.ok)throw'err';return r.blob()}).then(bl=>{
var url=URL.createObjectURL(bl);
im.innerHTML='<img src="'+url+'" style="width:100%;border-radius:8px">';
b.disabled=false;b.innerHTML='&#128247; Capturar';
}).catch(()=>{
im.innerHTML='<span style="color:#e74c3c;font-size:0.85rem">Erro ao capturar</span>';
b.disabled=false;b.innerHTML='&#128247; Capturar';
})
}
function setRes(v){fetch('/set-camera?resolution='+v).then(()=>{}).catch(()=>{})}
function setQual(v){fetch('/set-camera?quality='+v).then(()=>{}).catch(()=>{})}
var schedOn=false,schedTimer=null,schedRemaining=0;
function schedToggle(){
var btn=document.getElementById('sched-btn'),badge=document.getElementById('sched-badge'),prog=document.getElementById('sched-progress'),sel=document.getElementById('sched-interval');
if(schedOn){
schedOn=false;clearInterval(schedTimer);schedTimer=null;
btn.innerHTML='&#9654; Iniciar Gravacao';btn.style.borderColor='#27ae60';btn.style.color='#27ae60';
badge.style.display='none';prog.style.display='none';sel.disabled=false;
}else{
schedOn=true;var interval=parseInt(sel.value);schedRemaining=interval;
btn.innerHTML='&#9632; Parar Gravacao';btn.style.borderColor='#e74c3c';btn.style.color='#e74c3c';
badge.style.display='inline-flex';prog.style.display='block';sel.disabled=true;
cap();
schedTimer=setInterval(function(){
schedRemaining--;
if(schedRemaining<=0){schedRemaining=interval;cap()}
var pct=((interval-schedRemaining)/interval)*100;
document.getElementById('sched-bar').style.width=pct+'%';
var m=Math.floor(schedRemaining/60),s=String(schedRemaining%60).padStart(2,'0');
document.getElementById('sched-label').textContent='Proxima captura em '+m+':'+s;
},1000);
}
}
)rawliteral";
}

// ===================== LIVE MODE (push frames para servidor) =====================

HTTPClient liveHttp;
bool liveHttpReady = false;

void setLiveResolution(bool live) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) return;
  if (live) {
    s->set_framesize(s, FRAMESIZE_QVGA);   // 320x240 — frames menores, upload rapido
    s->set_quality(s, 20);                   // Compressao alta para live (~5-8KB/frame)
  } else {
    s->set_framesize(s, FRAMESIZE_VGA);     // 640x480 — qualidade full para captura
    s->set_quality(s, 12);
  }
  // Flush buffers apos mudar resolucao
  for (int i = 0; i < 3; i++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) esp_camera_fb_return(fb);
  }
}

void liveHttpConnect() {
  if (liveHttpReady) return;
  String url = String(SERVER_URL) + "/api/" + String(MODULE_TYPE) + "/" + chipId + "/live-frame";
  liveHttp.begin(url);
  liveHttp.addHeader("Content-Type", "image/jpeg");
  liveHttp.setTimeout(3000);
  liveHttp.setReuse(true);  // Keep-alive — reutiliza conexao TCP
  liveHttpReady = true;
}

void liveHttpDisconnect() {
  if (!liveHttpReady) return;
  liveHttp.end();
  liveHttpReady = false;
}

void pushLiveFrame() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return;

  liveHttpConnect();
  int httpCode = liveHttp.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (httpCode != 200) {
    Serial.printf("Live frame erro: HTTP %d\n", httpCode);
    liveHttpDisconnect();  // Reconecta no proximo frame
  }
}

void cam_loop() {
  if (!camLiveMode || !cameraReady) return;

  // Timeout de seguranca (2 min max)
  if (millis() - liveStartTime > LIVE_MAX_DURATION) {
    camLiveMode = false;
    liveHttpDisconnect();
    setLiveResolution(false);
    Serial.println("Live mode: timeout, parando");
    return;
  }

  if (millis() - lastLiveFrame >= LIVE_FRAME_INTERVAL) {
    lastLiveFrame = millis();
    pushLiveFrame();
  }
}

// ===================== COMMAND HANDLER =====================

bool cam_process_command(String cmd, String obj) {
  if (cmd == "capture") {
    if (cameraReady) {
      camera_fb_t* fb = captureHighRes();
      if (fb) {
        HTTPClient camHttp;
        String uploadUrl = String(SERVER_URL) + "/api/" + String(MODULE_TYPE) + "/" + chipId + "/upload-capture";
        camHttp.begin(uploadUrl);
        camHttp.addHeader("Content-Type", "image/jpeg");
        camHttp.setTimeout(15000);
        int httpCode = camHttp.POST(fb->buf, fb->len);
        Serial.printf("Capture push: %d bytes -> HTTP %d\n", fb->len, httpCode);
        camHttp.end();
        esp_camera_fb_return(fb);
      } else {
        Serial.println("Capture: erro ao capturar frame");
      }
      restoreDefaultRes();
    } else {
      Serial.println("Capture: camera nao inicializada");
    }
    return true;
  }

  if (cmd == "start-live") {
    if (cameraReady) {
      setLiveResolution(true);
      camLiveMode = true;
      liveStartTime = millis();
      lastLiveFrame = 0;
      Serial.println("Live mode: INICIADO (QVGA)");
    } else {
      Serial.println("Live mode: camera nao inicializada");
    }
    return true;
  }

  if (cmd == "stop-live") {
    camLiveMode = false;
    liveHttpDisconnect();
    setLiveResolution(false);
    Serial.println("Live mode: PARADO (VGA restaurado)");
    return true;
  }

  if (cmd == "set-camera") {
    // Salva resolucao/qualidade para proximas capturas
    String res = jsonVal(obj, "resolution");
    int qual = jsonInt(obj, "quality");

    if (res == "UXGA") captureFrameSize = FRAMESIZE_UXGA;
    else if (res == "SVGA") captureFrameSize = FRAMESIZE_SVGA;
    else if (res == "VGA") captureFrameSize = FRAMESIZE_VGA;

    if (qual > 0 && qual <= 63) captureQuality = qual;

    Serial.printf("Camera config: %s q%d\n", res.c_str(), captureQuality);
    return true;
  }

  return false;
}

// ===================== SETUP & ROUTES =====================

void cam_setup() {
  cameraReady = initCamera();
}

void handleSetCamera() {
  String res = server.arg("resolution");
  int qual = server.arg("quality").toInt();

  if (res == "UXGA") captureFrameSize = FRAMESIZE_UXGA;
  else if (res == "SVGA") captureFrameSize = FRAMESIZE_SVGA;
  else if (res == "VGA") captureFrameSize = FRAMESIZE_VGA;

  if (qual > 0 && qual <= 63) captureQuality = qual;

  Serial.printf("Camera local: %s q%d\n", res.c_str(), captureQuality);
  sendCORS();
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

void cam_register_routes() {
  server.on("/capture", handleCapture);
  server.on("/stream", handleStream);
  server.on("/set-camera", handleSetCamera);
}

#endif // MOD_CAM
#endif // MOD_CAM_H
