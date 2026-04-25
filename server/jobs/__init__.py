"""
Cultivee — Pacote de jobs em background (v4.1.38+)

Threads daemon iniciadas no startup do app.py. Cada job e responsavel
por seu proprio loop + sleep + tratamento de erros (nao quebra o app
se falhar).

- offline_watcher.py — detecta modulos offline > threshold e dispara
  alerta proativo (push + email).
"""
