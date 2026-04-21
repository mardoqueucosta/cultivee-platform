# Cultivee - License Gate / Vinculo hardware↔conta

**Status:** PROPOSTA — nao implementado em v4.1.26. Decisao de modelo comercial pendente.

## Problema

Hoje (v4.1.26), **qualquer conta autenticada pode parear qualquer dispositivo
que ainda nao tem dono** — basta saber o short_id (4 caracteres) do ESP32.

Implicacoes:
1. **Nao ha vinculo entre hardware comprado e conta** — um kit roubado/revendido
   funciona normalmente pra quem tiver ele em maos.
2. **Nao ha "receita recorrente"** atrelada ao uso do hardware — o servico continua
   funcionando indefinidamente apos a venda unica do kit.
3. **Cedo ou tarde**, alguem clonara o MAC de um ESP32 (o firmware pode ser
   reimpresso com qualquer MAC via eFuse em teoria, mas na pratica e raro).

## Opcoes de modelo

### A. Vinculo rigido (serial-lock na compra)

Cada kit e vendido com um **codigo de ativacao** unico gerado na fabricacao.
Codigo + short_id sao enviados ao cliente por email. Primeiro pareamento exige
os dois (short_id + codigo). Apos pareado, nao pode ser transferido sem
intervencao do suporte.

**Pros:** atrela venda a conta 1-pra-1, rastreabilidade total.  
**Contras:** se o cliente perde o email, suporte manual obrigatorio. Revenda
legitima (ex: amigo compra usado) vira atrito.

### B. Assinatura (pague pelo servico, nao pelo hardware)

Hardware e barato (ou gratis, subsidiado). Servico cobrado mensal/anual. Sem
assinatura ativa, ESP32 continua rodando automacao local mas o app mostra
"Assinatura vencida" e desativa features premium.

**Pros:** receita recorrente previsivel, incentivo a melhorar o servico. Modelo
moderno (Tesla, iRobot, etc.).  
**Contras:** cliente pode resistir ("paguei pelo hardware, por que pagar
mensal?"). Requer gateway de pagamento integrado.

### C. Licenca perpetua com suporte renovavel (modelo "softwares profissionais")

Hardware + 1 ano de suporte incluso. Depois do primeiro ano, cliente pode
renovar suporte anual (updates, alertas, backup dos dados) por valor reduzido.
Sem renovacao, servico continua mas sem garantia de uptime nem suporte.

**Pros:** percebido como justo ("paguei, e meu, mas suporte tem custo").  
**Contras:** churn natural do suporte ano a ano. Dificil defender o valor
quando "ja funciona".

### D. Hibrido (recomendado pra v4.2)

- Hardware vem com **1 ano de servico premium gratis** (alertas, backup, OTA remoto).
- Depois do 1 ano: servico cai pra **plano basico gratis** (dashboard, controle manual).
  Features premium ficam pagas (R$ X/mes por dispositivo ou flat).
- Nao bloqueia nada — so diferencia.

Mais fricao-baixa pra conversao inicial + receita recorrente opcional.

## Implementacao tecnica (qualquer modelo)

Independente do modelo escolhido, precisa:

1. **Tabela `licenses`** no banco:
   ```sql
   CREATE TABLE licenses (
     id INTEGER PRIMARY KEY,
     activation_code TEXT UNIQUE NOT NULL,  -- 16 chars base32
     chip_id TEXT,                           -- NULL ate ser ativada
     user_id INTEGER,                        -- NULL ate ser pareada
     plan TEXT NOT NULL,                     -- 'trial', 'premium', 'basic'
     activated_at TIMESTAMP,
     expires_at TIMESTAMP,                   -- NULL = perpetuo
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. **Geracao em lote na fabricacao**:
   ```bash
   python generate-licenses.py --count 100 --plan trial --output licenses.csv
   ```
   Cada linha: `activation_code,short_id_impresso_na_caixa`. Imprimir adesivos.

3. **Mudanca em `POST /api/modules/pair`**: alem de `short_id`, aceitar
   `activation_code`. Validar que o codigo e valido + pertence ao mesmo chip +
   ainda nao foi ativado.

4. **Middleware de plano**: decorator `@require_plan('premium')` em rotas
   premium (ex: alertas, OTA remoto, backup). Hoje todas as rotas sao livres —
   precisa auditoria do que entra no plano pago.

5. **Admin UI**:
   - Gerar codigos (interno)
   - Listar ativacoes recentes
   - Extender prazo manualmente (concessao de suporte)
   - Revogar codigo (cliente pediu reembolso)

6. **Renovacao**: integracao com gateway (Stripe tem plans/subscriptions prontos).
   Webhook → `expires_at = expires_at + 1 year`. Cancelamento → deixa `expires_at` como esta.

## Esforco estimado (opcao D hibrida)

- Schema + CRUD de licenses: **1 dia**
- Admin UI de geracao/listagem: **1 dia**
- Integracao Stripe + webhooks: **3-4 dias**
- Decorator de plano + rollout gradual: **2 dias**
- Email de boas-vindas com codigo: **meio dia**
- Testes end-to-end: **2 dias**

**Total: ~2 semanas de engenharia** + revisao legal do modelo escolhido.

## Bloqueios anteriores a implementar

Antes de codificar license gate, resolver:
1. Escolher o modelo (A/B/C/D ou outro) — **decisao de produto**.
2. Escolher o gateway (Stripe/PagSeguro/Mercado Pago) — **decisao operacional**.
3. Definir precos — **estudo de mercado necessario**.
4. Aprovar Termos de Uso com clausulas de servico (ja tem draft em [termos-uso.md](./termos-uso.md) § 4).

Enquanto isso nao acontecer, **Cultivee opera como servico gratuito aberto** — o que serve pra beta fechado com amigos/early adopters, nao pra venda ao publico.
