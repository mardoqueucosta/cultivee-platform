/*
  Cultivee Core - Web OTA (Over-The-Air Firmware Update)
  Upload de firmware via navegador em /update
*/

#ifndef CORE_OTA_H
#define CORE_OTA_H

bool otaInProgress = false;

void handleOtaPage() {
  String html = R"rawliteral(<!DOCTYPE html><html><head>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta charset='UTF-8'>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1d23;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#22252d;border-radius:20px;padding:30px;width:90%;max-width:400px;text-align:center;border:1px solid #2a2d35}
.logo{width:48px;height:48px;background:#27ae60;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:#fff;font-size:1.5rem;font-weight:800}
h1{color:#27ae60;font-size:1.4rem;margin-bottom:4px}
.sub{color:#888;font-size:0.85rem;margin-bottom:20px}
.ver{background:#1a1d23;border-radius:10px;padding:10px;margin-bottom:20px;font-size:0.8rem;color:#888}
.ver b{color:#27ae60}
.file-label{display:block;padding:40px 20px;border:2px dashed #3a3d45;border-radius:12px;cursor:pointer;margin-bottom:12px;transition:all 0.2s}
.file-label:hover{border-color:#27ae60;background:rgba(39,174,96,0.05)}
.file-label.has-file{border-color:#27ae60;background:rgba(39,174,96,0.1)}
.file-label span{display:block;color:#888;font-size:0.9rem}
.file-label .fname{color:#27ae60;font-weight:600;margin-top:6px;word-break:break-all}
input[type='file']{display:none}
button{width:100%;padding:14px;background:#27ae60;color:#fff;border:none;border-radius:10px;font-size:1.1rem;font-weight:700;cursor:pointer;transition:all 0.2s}
button:disabled{background:#3a3d45;color:#666;cursor:not-allowed}
button:active:not(:disabled){transform:scale(0.97)}
.progress{display:none;margin-top:16px}
.progress-bar{height:8px;background:#1a1d23;border-radius:4px;overflow:hidden}
.progress-fill{height:100%;background:#27ae60;border-radius:4px;width:0%;transition:width 0.3s}
.progress-text{font-size:0.8rem;color:#888;margin-top:6px}
.result{display:none;margin-top:16px;padding:14px;border-radius:10px;font-weight:600}
.result.ok{background:rgba(39,174,96,0.15);color:#27ae60}
.result.err{background:rgba(231,76,60,0.15);color:#e74c3c}
.back{display:inline-block;margin-top:16px;color:#888;font-size:0.8rem;text-decoration:none}
.back:hover{color:#27ae60}
.warn{background:rgba(230,126,34,0.1);border:1px solid rgba(230,126,34,0.3);border-radius:8px;padding:10px;margin-bottom:16px;font-size:0.75rem;color:#e67e22;text-align:left}
</style></head><body>
<div class='card'>
<div class='logo'>C</div>
<h1>Atualizar Firmware</h1>
<p class='sub'>)rawliteral" + String(PRODUCT_NAME) + R"rawliteral(</p>

<div class='ver'>Versao atual: <b>)rawliteral" + String(FIRMWARE_VERSION) + R"rawliteral(</b><br>
Chip: )rawliteral" + chipId + R"rawliteral( | Free: )rawliteral" + String(ESP.getFreeSketchSpace()) + R"rawliteral( bytes</div>

<div class='warn'>&#9888; Nao desligue o dispositivo durante a atualizacao. O processo leva cerca de 30 segundos.</div>

<form id='otaForm'>
<label class='file-label' id='fileLabel' for='fileInput'>
<span>Toque para selecionar o arquivo .bin</span>
</label>
<input type='file' id='fileInput' accept='.bin' onchange='fileSelected(this)'>
<button type='submit' id='btnUpload' disabled>Selecione um arquivo</button>
</form>

<div class='progress' id='progress'>
<div class='progress-bar'><div class='progress-fill' id='progressFill'></div></div>
<p class='progress-text' id='progressText'>Enviando...</p>
</div>

<div class='result' id='result'></div>
<a href='/' class='back'>&larr; Voltar ao Dashboard</a>
</div>

<script>
function fileSelected(input) {
  var label = document.getElementById('fileLabel');
  var btn = document.getElementById('btnUpload');
  if (input.files.length > 0) {
    var f = input.files[0];
    label.className = 'file-label has-file';
    label.innerHTML = '<span>Arquivo selecionado:</span><span class="fname">' + f.name + ' (' + (f.size/1024).toFixed(0) + ' KB)</span>';
    btn.disabled = false;
    btn.textContent = 'Atualizar Firmware';
  }
}

document.getElementById('otaForm').addEventListener('submit', function(e) {
  e.preventDefault();
  var file = document.getElementById('fileInput').files[0];
  if (!file) return;

  var btn = document.getElementById('btnUpload');
  var prog = document.getElementById('progress');
  var fill = document.getElementById('progressFill');
  var text = document.getElementById('progressText');
  var result = document.getElementById('result');

  btn.disabled = true;
  btn.textContent = 'Enviando...';
  prog.style.display = 'block';
  result.style.display = 'none';

  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/update', true);

  xhr.upload.addEventListener('progress', function(e) {
    if (e.lengthComputable) {
      var pct = Math.round((e.loaded / e.total) * 100);
      fill.style.width = pct + '%';
      text.textContent = pct < 100 ? 'Enviando: ' + pct + '%' : 'Gravando no flash...';
    }
  });

  xhr.onload = function() {
    try {
      var r = JSON.parse(xhr.responseText);
      result.style.display = 'block';
      if (r.success) {
        result.className = 'result ok';
        result.innerHTML = '&#10003; Atualizado! Reiniciando em 5s...';
        setTimeout(function(){ location.href = '/'; }, 5000);
      } else {
        result.className = 'result err';
        result.innerHTML = '&#10007; Erro: ' + r.message;
        btn.disabled = false;
        btn.textContent = 'Tentar novamente';
      }
    } catch(e) {
      result.style.display = 'block';
      result.className = 'result ok';
      result.innerHTML = '&#10003; Atualizado! Reiniciando...';
      setTimeout(function(){ location.href = '/'; }, 5000);
    }
  };

  xhr.onerror = function() {
    fill.style.width = '100%';
    text.textContent = 'Gravando...';
    result.style.display = 'block';
    result.className = 'result ok';
    result.innerHTML = '&#10003; Firmware enviado! Reiniciando...';
    setTimeout(function(){ location.href = '/'; }, 8000);
  };

  var formData = new FormData();
  formData.append('firmware', file);
  xhr.send(formData);
});
</script>
</body></html>)rawliteral";

  server.send(200, "text/html", html);
}

void handleOtaUpload() {
  HTTPUpload& upload = server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("OTA: Recebendo %s\n", upload.filename.c_str());
    otaInProgress = true;
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Serial.printf("OTA: Erro ao iniciar: %s\n", Update.errorString());
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Serial.printf("OTA: Erro ao gravar: %s\n", Update.errorString());
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.printf("OTA: Sucesso! %u bytes gravados\n", upload.totalSize);
    } else {
      Serial.printf("OTA: Erro ao finalizar: %s\n", Update.errorString());
    }
    otaInProgress = false;
  }
}

void handleOtaResult() {
  if (Update.hasError()) {
    server.send(200, "application/json",
      "{\"success\":false,\"message\":\"" + String(Update.errorString()) + "\"}");
  } else {
    server.send(200, "application/json", "{\"success\":true}");
    delay(1000);
    ESP.restart();
  }
}

void ota_register_routes() {
  server.on("/update", HTTP_GET, handleOtaPage);
  server.on("/update", HTTP_POST, handleOtaResult, handleOtaUpload);
}

#endif
