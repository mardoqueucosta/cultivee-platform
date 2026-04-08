/*
  Cultivee Core - Web Server, CORS, Captive Portal, WiFi Setup Pages
*/

#ifndef CORE_SERVER_H
#define CORE_SERVER_H

// ===================== CORS =====================

void sendCORS() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

// ===================== CAPTIVE PORTAL =====================

void handleCaptiveAndroid() {
  // Responde 204 para Android confiar no WiFi e nao priorizar 4G
  // Sem 204, Android detecta "sem internet" e roteia tudo pelo 4G
  Serial.println("Portal cativo: Android → 204 (WiFi confiavel)");
  server.send(204);
}

void handleCaptiveApple() {
  // Responde Success para iOS confiar no WiFi e nao priorizar dados moveis
  Serial.println("Portal cativo: Apple → Success (WiFi confiavel)");
  server.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>");
}

void handleCaptiveWindows() {
  Serial.println("Portal cativo: Windows detectado");
  server.sendHeader("Location", "http://192.168.4.1/");
  server.send(302, "text/html", "<html><body>Redirecionando...</body></html>");
}

void handleCaptiveGeneric() {
  Serial.println("Portal cativo: generico");
  server.sendHeader("Location", "http://192.168.4.1/");
  server.send(302, "text/html", "<html><body><a href='http://192.168.4.1/'>Configurar WiFi</a></body></html>");
}

// ===================== WIFI SETUP PAGE =====================

void handleSetupPage() {
  int n = WiFi.scanNetworks();
  String options = "";
  for (int i = 0; i < n; i++) {
    options += "<option value='" + WiFi.SSID(i) + "'>" + WiFi.SSID(i) + " (" + String(WiFi.RSSI(i)) + " dBm)</option>";
  }

  String html = R"rawliteral(<!DOCTYPE html><html><head>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta charset='UTF-8'>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#fff;border-radius:20px;padding:30px;width:90%;max-width:360px;box-shadow:0 4px 20px rgba(0,0,0,0.1);text-align:center}
.logo{width:48px;height:48px;background:#27ae60;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:#fff;font-size:1.5rem;font-weight:800}
h1{color:#27ae60;font-size:1.6rem;margin-bottom:4px}
.sub{color:#888;font-size:0.85rem;margin-bottom:20px}
.step{display:flex;align-items:center;gap:8px;background:#f8f9fa;border-radius:10px;padding:10px 14px;margin-bottom:12px;text-align:left}
.step-num{width:24px;height:24px;background:#27ae60;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:700;flex-shrink:0}
.step-text{font-size:0.85rem;color:#555}
.step-active .step-num{animation:pulse-step 1.5s infinite}
@keyframes pulse-step{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
select,input[type='password'],input[type='text']{width:100%;padding:14px;margin:6px 0;border:1px solid #ddd;border-radius:10px;font-size:1rem;-webkit-appearance:none;appearance:none}
select{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='6'%3E%3Cpath d='M0 0l6 6 6-6' fill='%23888'/%3E%3C/svg%3E") no-repeat right 14px center/12px;background-color:#fff;padding-right:36px}
select:focus,input:focus{outline:none;border-color:#27ae60;box-shadow:0 0 0 3px rgba(39,174,96,0.15)}
button{width:100%;padding:14px;background:#27ae60;color:#fff;border:none;border-radius:10px;font-size:1.1rem;font-weight:700;cursor:pointer;margin-top:10px;transition:all 0.2s}
button:active{transform:scale(0.97)}
.loading{display:none;margin-top:15px}
.spinner{width:28px;height:28px;border:3px solid #e0e0e0;border-top-color:#27ae60;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 8px}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{color:#888;font-size:0.85rem}
</style>
<script>
function onSubmit(){
  var btn=document.getElementById('btn');
  var ld=document.getElementById('loading');
  btn.disabled=true;btn.textContent='Conectando...';btn.style.opacity='0.7';
  ld.style.display='block';
  return true;
}
</script>
</head><body>
<div class='card'>
<div class='logo'>C</div>
<h1>)rawliteral" + String(PRODUCT_NAME) + R"rawliteral(</h1>
<p class='sub'>Configure o WiFi do dispositivo</p>
<div class='step step-active'><span class='step-num'>1</span><span class='step-text'>Selecione sua rede WiFi</span></div>
<form method='POST' action='/save-wifi' onsubmit='return onSubmit()'>
<select name='ssid'>)rawliteral" + options + R"rawliteral(</select>
<input type='password' name='password' placeholder='Senha do WiFi' id='pass'>
<label style='display:flex;align-items:center;gap:10px;font-size:0.95rem;margin:12px 0;cursor:pointer;color:#666;-webkit-tap-highlight-color:transparent'>
<input type='checkbox' style='width:22px;height:22px;accent-color:#27ae60;flex-shrink:0' onclick="document.getElementById('pass').type=this.checked?'text':'password'"> Mostrar senha</label>
<button type='submit' id='btn'>Conectar</button>
</form>
<div style='margin-top:16px;padding-top:16px;border-top:1px solid #eee'>
<a href='/skip-wifi' style='display:block;padding:12px;background:#f8f9fa;color:#666;border:1px solid #ddd;border-radius:10px;font-size:0.9rem;font-weight:600;text-decoration:none;text-align:center;transition:all 0.2s'>Usar sem WiFi</a>
<p style='color:#aaa;font-size:0.75rem;margin-top:6px'>Controle local via rede )rawliteral" + String(AP_SSID) + R"rawliteral(</p>
</div>
<div class='loading' id='loading'>
<div class='spinner'></div>
<div class='loading-text'>Salvando configuracao...</div>
</div>
</div></body></html>)rawliteral";

  server.send(200, "text/html", html);
}

// ===================== SAVE WIFI =====================

void handleSaveWiFi() {
  String ssid = server.arg("ssid");
  String pass = server.arg("password");

  if (ssid.length() == 0) {
    server.send(400, "text/plain", "SSID vazio");
    return;
  }

  saveWiFiCredentials(ssid, pass);

  // URL do app (definida no produto — sempre HTTPS em producao, HTTP em local)
  String appDomain = String(APP_URL);

  String html = R"rawliteral(<!DOCTYPE html><html><head>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta charset='UTF-8'>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#fff;border-radius:20px;padding:30px;width:90%;max-width:360px;box-shadow:0 4px 20px rgba(0,0,0,0.1);text-align:center}
.check-circle{width:56px;height:56px;background:#27ae60;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;animation:pop 0.4s ease-out}
.check-circle svg{width:28px;height:28px;stroke:#fff;stroke-width:3;fill:none}
@keyframes pop{0%{transform:scale(0)}60%{transform:scale(1.15)}100%{transform:scale(1)}}
h2{color:#27ae60;margin:8px 0}
.steps{text-align:left;margin:16px 0}
.step{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;margin:4px 0;font-size:0.85rem;color:#999;transition:all 0.3s}
.step.done{color:#27ae60;background:#f0f9f1}
.step.active{color:#333;background:#f8f9fa}
.step-icon{width:20px;height:20px;border-radius:50%;border:2px solid #ddd;display:flex;align-items:center;justify-content:center;font-size:0.65rem;flex-shrink:0;transition:all 0.3s}
.step.done .step-icon{background:#27ae60;border-color:#27ae60;color:#fff}
.step.active .step-icon{border-color:#27ae60;animation:pulse-s 1.5s infinite}
@keyframes pulse-s{0%,100%{box-shadow:0 0 0 0 rgba(39,174,96,0.3)}50%{box-shadow:0 0 0 6px rgba(39,174,96,0)}}
.spinner-sm{width:14px;height:14px;border:2px solid #e0e0e0;border-top-color:#27ae60;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.progress-bar{width:100%;height:4px;background:#e8e8e8;border-radius:4px;margin:16px 0 8px;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,#27ae60,#2ecc71);border-radius:4px;transition:width 1s linear}
.code{font-size:1.8rem;font-weight:800;color:#1a472a;letter-spacing:0.15em;margin:8px 0;padding:10px;background:#f0f9f1;border-radius:12px}
.btn{display:inline-block;padding:12px 24px;background:#27ae60;color:#fff;text-decoration:none;border-radius:10px;font-weight:700;margin-top:8px;transition:all 0.2s}
.btn:active{transform:scale(0.97)}
.status-box{margin-top:12px;padding:12px 16px;border-radius:12px;background:#f8f9fa;border:1px solid #e8e8e8;transition:all 0.3s}
.status-text{font-size:0.95rem;font-weight:600;color:#555}
.status-sub{font-size:0.8rem;color:#888;margin-top:4px}
</style>
<script>
var s=6,total=6;
var steps=['WiFi salvo','Reiniciando modulo','Conectando na rede','Abrindo o app'];
function tick(){
  s--;
  var pct=((total-s)/total)*100;
  document.getElementById('pbar').style.width=pct+'%';
  var msgs=['Salvando configuracao...','Preparando reinicio...','Reiniciando modulo...','Conectando na rede...','Verificando conexao...','Quase pronto...'];
  var mi=total-s-1;if(mi<0)mi=0;if(mi>=msgs.length)mi=msgs.length-1;
  document.getElementById('status-text').textContent=msgs[mi];
  document.getElementById('status-sub').textContent='Passo '+(total-s)+' de '+total;
  var si=Math.min(Math.floor(((total-s)/total)*steps.length), steps.length-1);
  for(var i=0;i<steps.length;i++){
    var el=document.getElementById('s'+i);
    if(i<si){el.className='step done';el.querySelector('.step-icon').innerHTML='&#10003;';}
    else if(i==si){el.className='step active';el.querySelector('.step-icon').innerHTML='<div class="spinner-sm"></div>';}
  }
  if(s<=0){
    document.getElementById('s'+(steps.length-1)).className='step done';
    document.getElementById('s'+(steps.length-1)).querySelector('.step-icon').innerHTML='&#10003;';
    tryRedirect();
  }
  else setTimeout(tick,1000);
}
setTimeout(tick,800);
function tryRedirect(){
  document.getElementById('step2').style.display='block';
  document.getElementById('step1').style.display='none';
}
</script>
</head><body>
<div class='card'>
<div class='check-circle'><svg viewBox='0 0 24 24'><polyline points='6 12 10 16 18 8'/></svg></div>
<h2>WiFi configurado!</h2>
<p style='color:#888;font-size:0.9rem'>Rede: <strong>)rawliteral" + ssid + R"rawliteral(</strong></p>
<div class='progress-bar'><div class='progress-fill' id='pbar' style='width:5%'></div></div>

<div id='step1'>
<div class='steps'>
<div class='step done' id='s0'><span class='step-icon'>&#10003;</span><span>WiFi salvo</span></div>
<div class='step' id='s1'><span class='step-icon'></span><span>Reiniciando modulo</span></div>
<div class='step' id='s2'><span class='step-icon'></span><span>Conectando na rede</span></div>
<div class='step' id='s3'><span class='step-icon'></span><span>Abrindo o app</span></div>
</div>
<div class='status-box' id='status-box'>
<div class='status-text' id='status-text'>Preparando...</div>
<div class='status-sub' id='status-sub'>O modulo vai reiniciar automaticamente</div>
</div>
</div>

<div id='step2' style='display:none'>
<p style='color:#888;font-size:0.8rem;margin:12px 0 4px'>Seu codigo de pareamento:</p>
<div class='code'>)rawliteral" + shortId + R"rawliteral(</div>
<div class='status-box' style='text-align:left;margin-top:12px'>
<div style='font-weight:600;color:#555;font-size:0.9rem;margin-bottom:8px'>Agora conecte no seu WiFi:</div>
<div style='display:flex;align-items:center;gap:8px;color:#888;font-size:0.85rem;margin-bottom:6px'>
<span style='background:#27ae60;color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:0.7rem;flex-shrink:0'>1</span>
Conecte na rede <b style='color:#555'>)rawliteral" + ssid + R"rawliteral(</b></div>
<div style='display:flex;align-items:center;gap:8px;color:#888;font-size:0.85rem'>
<span style='background:#27ae60;color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:0.7rem;flex-shrink:0'>2</span>
Toque em <b style='color:#555'>Abrir App</b> abaixo</div>
</div>
<a href='intent:#Intent;action=android.settings.WIFI_SETTINGS;end' onclick='event.preventDefault();try{location.href=this.href}catch(e){alert("Abra as Configuracoes WiFi do celular manualmente")}' style='display:block;padding:12px;background:#f0f2f5;color:#555;border:1px solid #ddd;border-radius:10px;font-weight:600;text-decoration:none;text-align:center;margin-top:10px;font-size:0.9rem'>&#9881; Trocar WiFi do celular</a>
<a href=')rawliteral" + appDomain + "?code=" + shortId + R"rawliteral(' class='btn' style='margin-top:8px;display:block;text-align:center'>Abrir App</a>
</div>
</div></body></html>)rawliteral";

  server.send(200, "text/html", html);
  delay(8000);
  ESP.restart();
}

// ===================== OUTROS HANDLERS WIFI =====================

void handleResetWiFi() {
  clearWiFiCredentials();
  server.send(200, "text/plain", "WiFi resetado. Reiniciando...");
  delay(1000);
  ESP.restart();
}

void handleSkipWiFi() {
  currentMode = MODE_OFFLINE;
  Serial.println("Modo sem WiFi — controle local via AP");
  server.sendHeader("Location", "/");
  server.send(302);
}

// ===================== RESET BUTTON (compartilhado) =====================

void checkResetButton() {
  static unsigned long pressStart = 0;
  static bool wasPressed = false;

  if (digitalRead(RESET_BTN) == LOW) {
    if (!wasPressed) {
      pressStart = millis();
      wasPressed = true;
      Serial.println("Botao pressionado...");
    }
    if (millis() - pressStart > 1000) {
      digitalWrite(LED_ONBOARD, (millis() / 200) % 2);
    }
    if (millis() - pressStart >= 3000) {
      Serial.println(">>> RESET WiFi via botao! <<<");
      digitalWrite(LED_ONBOARD, HIGH);
      delay(500);
      digitalWrite(LED_ONBOARD, LOW);
      delay(200);
      digitalWrite(LED_ONBOARD, HIGH);
      delay(500);
      digitalWrite(LED_ONBOARD, LOW);
      clearWiFiCredentials();
      ESP.restart();
    }
  } else {
    if (wasPressed) {
      digitalWrite(LED_ONBOARD, LOW);
      Serial.println("Botao solto antes dos 3s");
    }
    wasPressed = false;
  }
}

// ===================== REGISTRO DE ROTAS CORE =====================

void core_register_routes() {
  // WiFi setup
  server.on("/save-wifi", HTTP_POST, handleSaveWiFi);
  server.on("/setup-wifi", handleSetupPage);
  server.on("/skip-wifi", handleSkipWiFi);
  server.on("/reset-wifi", handleResetWiFi);

  // Captive portal
  server.on("/generate_204", handleCaptiveAndroid);
  server.on("/gen_204", handleCaptiveAndroid);
  server.on("/connectivitycheck/gstatic/com", handleCaptiveAndroid);
  server.on("/hotspot-detect.html", handleCaptiveApple);
  server.on("/library/test/success.html", handleCaptiveApple);
  server.on("/captive-portal/api/session", handleCaptiveApple);
  server.on("/connecttest.txt", handleCaptiveWindows);
  server.on("/ncsi.txt", handleCaptiveWindows);
  server.on("/fwlink", handleCaptiveWindows);
  server.on("/redirect", handleCaptiveWindows);
  server.on("/canonical.html", handleCaptiveGeneric);
  server.on("/success.txt", handleCaptiveGeneric);
  server.on("/generate204", handleCaptiveAndroid);  // Android tambem usa sem underscore
  server.on("/mobile/status.php", handleCaptiveGeneric);

  server.onNotFound([]() {
    if (currentMode == MODE_SETUP) {
      handleCaptiveGeneric();
    } else {
      server.send(404, "text/plain", "Not found");
    }
  });
}

#endif
