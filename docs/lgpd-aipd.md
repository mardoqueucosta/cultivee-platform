# Cultivee - Avaliacao de Impacto a Protecao de Dados (AIPD)

**Status:** DRAFT — precisa de revisao por DPO/juridico antes de publicar.

A LGPD (Lei 13.709/2018) exige que operacoes com dados pessoais de risco elevado
tenham uma **Avaliacao de Impacto a Protecao de Dados Pessoais (AIPD)** —
documento que descreve o tratamento, os riscos e as medidas mitigadoras.

## 1. Identificacao

- **Controlador dos dados:** `[preencher razao social]`
- **CNPJ:** `[preencher]`
- **Encarregado (DPO):** `[nome + email]` (obrigatorio — ainda nao designado)
- **Contato DPO publico:** `dpo@cultivee.com.br` (criar caixa)
- **Data da avaliacao:** `[data da publicacao]`
- **Revisao prevista:** anual ou em mudanca material

## 2. Descricao do tratamento

### Finalidades
1. **Prestacao do servico IoT**: associar o hardware comprado a uma conta de usuario, permitir controle remoto, historico, alertas.
2. **Suporte tecnico**: diagnosticar problemas, responder duvidas.
3. **Seguranca**: autenticacao, detecao de abuso, auditoria de acoes administrativas.
4. **Comunicacao transacional**: confirmacao de email, recuperacao de senha, alertas do sistema.

**Nao ha finalidade de marketing ativo** na v4.1.26 (nenhum envio de marketing). Quando
houver, exigira novo consentimento separado.

### Dados coletados

| Categoria          | Campos                                                                      | Base legal              |
|--------------------|-----------------------------------------------------------------------------|-------------------------|
| **Cadastro**       | nome, email, senha (hash bcrypt), telefone, data de nascimento              | Execucao do contrato    |
| **Endereco**       | CEP, logradouro, numero, complemento, bairro, cidade, estado                | Execucao do contrato    |
| **Fiscais**        | PF ou PJ, CPF ou CNPJ, razao social                                         | Obrigacao legal (NF-e)  |
| **Tecnicos**       | IP, user-agent, horario de login, sessoes ativas                            | Legitimo interesse (seguranca) |
| **Dispositivos**   | chip_id (MAC ESP32), nome personalizado, modulos pareados, historico de uso | Execucao do contrato    |
| **Imagens**        | Fotos capturadas pela camera (se tiver kit Cam)                             | Execucao do contrato    |
| **Notificacoes**   | Endpoint Web Push, email alternativo para alertas                           | Consentimento           |

### Categorias sensiveis
- **Nao coletamos** dados sensiveis (origem racial, religiao, saude, biometria etc.)
- Imagens da camera sao do ambiente de cultivo, nao de pessoas. Usuario deve evitar
  apontar a camera pra areas com pessoas (e responsabilidade dele).

### Compartilhamentos

| Recebedor               | Finalidade                     | Dados enviados              |
|-------------------------|--------------------------------|-----------------------------|
| Cloudflare (DNS/CDN)    | Infra web                       | IP, user-agent              |
| HostGator (SMTP)        | Envio de email transacional     | Email destinatario, conteudo |
| Let's Encrypt (TLS)     | Certificado SSL                 | dominio publico             |

Nao ha compartilhamento com parceiros de marketing, data brokers, analytics externos
(a v4.1.26 nao tem analytics). Antes de habilitar analytics, atualizar esta AIPD.

### Transferencia internacional
- Cloudflare e Let's Encrypt tem presenca global — ha transferencia internacional
  incidental (CDN). Base: execucao de contrato.
- Servidor da aplicacao: **VPS no Brasil** (verificar IP 129.121.50.168 — confirmar provedor).

### Retencao

| Dado                     | Prazo                              |
|--------------------------|------------------------------------|
| Cadastro + perfil        | Enquanto a conta existir           |
| Sessoes (tokens)         | 30 dias por sessao                 |
| Logs de auditoria admin  | 2 anos (pratica recomendada)       |
| Alertas enviados         | 1 ano                              |
| Imagens capturadas       | Enquanto o usuario nao apagar      |
| Dados apos exclusao      | 30 dias em backup → purge definitivo |

Quando o usuario exclui a conta pelo app (`DELETE /api/profile/`):
- Perfil + tokens + push subscriptions: **removidos imediatamente**
- Imagens em `captures/`, `thumbs/`, `live/` + firmware pendente: **removidos imediatamente** (v4.1.26)
- Modulos pareados: **desvinculados** (chip_id fica "livre" pra ser repareado)
- Audit log + alert log: **preservados** com referencia anonimizada (obrigacao de registros administrativos + seguranca)

## 3. Direitos do titular (Art. 18 LGPD)

Todos implementados em `/api/profile/*` (v4.1.20):

| Direito                                   | Como exercer                          |
|-------------------------------------------|---------------------------------------|
| Confirmacao de tratamento + acesso         | `GET /api/profile/` (UI "Perfil")     |
| Correcao                                   | `PUT /api/profile/` (UI "Editar")     |
| Portabilidade                              | `GET /api/profile/export` (download JSON) |
| Anonimizacao, bloqueio ou eliminacao       | `DELETE /api/profile/` (UI "Excluir conta") |
| Informacao sobre compartilhamentos         | Este documento + pagina `/privacidade` |
| Revogacao do consentimento                 | Excluir conta ou desativar notificacoes |

Prazo de resposta: **15 dias** (Art. 19 LGPD).

## 4. Medidas de seguranca

### Tecnicas
- Senhas com **bcrypt** (rounds 12) (v4.1.26 — migrado de SHA-256 legado)
- **HTTPS/TLS** obrigatorio no acesso via navegador (Let's Encrypt via Traefik)
- **HSTS, CSP, X-Frame-Options** e demais security headers ativos (v4.1.23)
- **2FA opcional** (TOTP) em todas as contas (v4.1.22)
- **Rate limiting** em endpoints sensiveis (login, recovery)
- **Tokens de sessao** com expiracao (30 dias) e metadata (IP, user-agent)
- **Audit log** de todas as acoes administrativas + notificacao a outros admins
- **Path traversal fixed** em todas as rotas de imagens (v4.1.26)
- **SHA-256 do firmware OTA** valido antes de aplicar (v4.1.26)
- **Backups** diarios com SHA-256 de integridade (v4.1.26 — [backup-vps.sh](../backup-vps.sh))

### Organizacionais
- Acesso ao servidor **por chave SSH** (nao senha), com `fail2ban` ativo.
- Secrets em **`.env` da VPS** (nunca no repositorio — GitGuardian monitora).
- Rotacao trimestral de secrets (ver [operacao.md](./operacao.md) § 3).
- **Encarregado (DPO)** designado — `[PENDENTE — requer decisao do controlador]`.

### Limitacoes conhecidas (v4.1.26)
- Banco SQLite em disco **nao criptografado** em repouso — apenas isolado via permissoes de filesystem e container. Migrar pra Postgres com criptografia at-rest em v4.2.
- Comunicacao **ESP32 ↔ servidor via HTTP puro** — sem TLS. Mitigado por:
  - SHA-256 do firmware (v4.1.26)
  - Validacao de chip_id no pareamento
  - Rede local do cliente e, normalmente, confiavel
  - Alvo de v5.0: TLS com certificado client-side no ESP32

## 5. Analise de risco

| Risco                                   | Probabilidade | Impacto | Mitigacao |
|------------------------------------------|:-:|:-:|---|
| Vazamento de banco de dados              | Baixa  | Alto   | Backup diario, ssh hardening, audit |
| Invasao por senha fraca                  | Media  | Medio  | bcrypt + rate limit + 2FA opcional |
| XSS via nome de modulo/fase              | Baixa  | Medio  | Escape HTML (v4.1.26) em todos os pontos de saida |
| Path traversal em imagens                | Baixa  | Alto   | Resolvido em v4.1.26 |
| OTA com firmware malicioso               | Baixa  | Critico | SHA-256 obrigatorio + rollback A/B (v4.1.26) |
| Perda de dados por falha de hardware     | Baixa  | Alto   | Backup diario testado mensalmente |
| Cross-tenant leak (usuario A ve de B)    | Muito baixa | Alto | Filtros `WHERE user_id=?` em todas as queries + capability check |
| DPO/contato legal indisponivel           | Alta   | Medio  | Designar DPO antes da comercializacao |

Risco residual apos mitigacoes: **aceitavel pra operacao com supervisao**. Revisao
semestral obrigatoria enquanto a plataforma estiver em crescimento.

## 6. Proximas acoes

Ordem de prioridade pra fechar a AIPD completa:

1. **Designar DPO** — pode ser terceirizado (varias firmas oferecem DPO-as-a-service).
2. **Publicar contato DPO** no rodape do site e em `/privacidade`.
3. **Revisar Termos de Uso** (minuta em [termos-uso.md](./termos-uso.md)) com advogado.
4. **Treinar equipe interna** (ainda que seja so fundador) em tratamento de incidente LGPD: o que fazer se houver vazamento, prazos de notificacao a ANPD (48h), template de comunicacao ao titular.
5. **Contrato com parceiros** (HostGator, Cloudflare) — conferir se tem DPA (Data Processing Addendum). Cloudflare tem modelo pronto.
