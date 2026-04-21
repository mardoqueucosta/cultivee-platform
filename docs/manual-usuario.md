# Cultivee - Guia de Primeiros Passos

Bem-vindo! Este guia mostra o caminho do desempacotamento ate sua primeira
leitura do sistema na tela. Vai levar entre **5 e 15 minutos**.

> Se ficar preso em algum passo, pule direto pra [Suporte](#suporte-e-troubleshooting).

## O que voce recebeu na caixa

Dependendo do kit adquirido:

**Kit HIDRO**: ESP32-WROOM, modulo de 4 reles, cabos, fonte 5V.  
**Kit HIDRO-FARM**: ESP32-WROOM, modulo de 6 reles, 2 boias reed-switch, sensor DHT11, fonte 5V.  
**Kit CAM**: ESP32-WROVER com camera OV2640, fonte 5V.

## Passo 1 - Ligue o dispositivo

Conecte a fonte de energia. O LED azul do ESP32 acende. O primeiro boot
leva cerca de **10 segundos** — espere.

## Passo 2 - Conecte o dispositivo no WiFi

1. No seu celular, abra as **Configuracoes de WiFi**.
2. Procure por uma rede chamada `Cultivee-Hidro`, `Cultivee-HidroFarm` ou `Cultivee-Cam` (depende do kit).
3. Conecte nela — **sem senha**. O celular deve abrir automaticamente a tela de configuracao (**portal cativo**). Se nao abrir em 10s, abra o navegador e digite `192.168.4.1`.
4. Selecione a sua rede WiFi domestica na lista, digite a senha, toque **Conectar**.
5. A tela mostra uma contagem regressiva + **seu codigo de pareamento** (4 caracteres). **Anote o codigo** — voce vai usar no passo 4.
6. O dispositivo reinicia sozinho.

## Passo 3 - Crie sua conta no app

1. Volte seu celular pra **rede WiFi de casa**.
2. Abra o navegador em **<https://app.cultivee.com.br>**.
3. Toque **Criar conta**, preencha nome, email, senha, aceite os termos.
4. Um email de confirmacao chega em ate 2 minutos. Clique no link pra ativar.

> **Nao recebeu o email?** Olhe no spam/lixeira. Se nao chegou, use "Reenviar email de verificacao" dentro do app. Se ainda nao, fale com o [suporte](#suporte-e-troubleshooting).

## Passo 4 - Adicione seu dispositivo

1. No app, toque **+ Adicionar Modulo**.
2. Digite o codigo de 4 caracteres que voce anotou no passo 2.
3. Pronto — o dispositivo aparece na lista, com um LED verde indicando que esta online.

Se o dispositivo nao aparece, espere mais 30 segundos e toque "Buscar novamente".
Se ainda nao aparece, veja [Troubleshooting](#suporte-e-troubleshooting).

## Passo 5 - Configure (opcional)

### Hidro / Hidro-Farm
- Toque no card do modulo → **Configurar Fases**.
- Cada fase define quanto tempo dura, quando a luz acende, quando a bomba liga.
- Defina a data de inicio do ciclo (hoje, por padrao).

### Camera
- Toque no card da camera → **Capturar** tira uma foto agora.
- **Ao Vivo** mostra video por ate 10 minutos.
- **Gravacao** ativa capturas agendadas (intervalo de 30s a 24h).

## Ative as notificacoes (recomendado)

No seu perfil:
1. Toque **Perfil** → **Notificacoes**.
2. Toque **Ativar notificacoes** — o navegador pede permissao, aceite.
3. A partir dai voce recebe alerta quando:
   - Reservatorio fica vazio por mais tempo que o limite configurado
   - Dispositivo fica offline (planejado pra v4.2)

## Seguranca da conta

- Use uma **senha unica** (pelo menos 8 caracteres, misturando letras e numeros).
- Ative o **2FA** em **Perfil → Seguranca**. Precisa de um app autenticador (Google Authenticator, Authy, 1Password).
- Em **Meus dispositivos** voce ve todas as sessoes ativas — se ver uma que nao reconhece, toque "Revogar".

## Perguntas frequentes

**Q: Funciona sem internet?**  
A: O hidroponico continua executando a automacao local mesmo offline (o relogio e mantido pelo chip RTC). Voce ve os dados quando o internet voltar. Camera + galeria precisam de internet pra sincronizar.

**Q: Quantos dispositivos posso ligar?**  
A: No plano atual, sem limite rigido. Cada modulo roda em um ESP32 separado.

**Q: E se o WiFi de casa mudar de senha?**  
A: Segure o botao BOOT do ESP32 por 3 segundos. A rede `Cultivee-*` volta a aparecer — refaca o passo 2.

**Q: Posso mover o kit pra outra casa?**  
A: Sim — refaca o setup de WiFi (segure BOOT 3s). O dispositivo continua pareado com sua conta.

**Q: Os dados sao seus?**  
A: Sim. Em **Perfil → Dados** voce pode **exportar** tudo que temos da sua conta, ou **apagar** a conta junto com fotos e historico (LGPD).

## Suporte e troubleshooting

### Problema: dispositivo nao entra no modo de setup
- Segure o botao BOOT por 3 segundos — o LED pisca 2x. Tenta de novo.
- Se o LED nao piscar, a fonte pode nao ter amperagem suficiente. Teste com outra fonte 5V / 2A.

### Problema: nao consigo conectar no WiFi do dispositivo (`Cultivee-*`)
- Afaste celular de outros roteadores. Se o seu WiFi e 5GHz, o ESP32 so ve 2.4GHz — nao e problema de setup, so o selector no passo 2 que nao encontra.
- Feche o app de internet do celular e entre direto pelas Configuracoes de WiFi.

### Problema: dispositivo conecta mas nao aparece no app
- Espere 1 minuto. O primeiro registro pode levar ate 30s.
- Confira em **Perfil → Meus dispositivos** se o codigo bate.
- Segure BOOT por 3s pra refazer o setup — as vezes um restart resolve.

### Contato

- **Email**: contato@cultivee.com.br (resposta em 1 dia util)
- **WhatsApp**: (planejado pra v4.2)
- **Status do servico**: <https://status.cultivee.com.br> (planejado pra v4.2)

Tenha em maos:
- Codigo de pareamento do dispositivo (4 caracteres)
- Email da conta
- O que voce estava fazendo quando deu problema
- Print/foto da tela se tiver erro visivel
