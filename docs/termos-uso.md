# Cultivee - Termos de Uso (DRAFT)

> **AVISO IMPORTANTE**: Esta e uma MINUTA. Nao usar em producao sem revisao
> por advogado com conhecimento em direito digital/consumidor/LGPD. Os textos
> entre colchetes `[...]` precisam ser preenchidos.

**Vigencia:** a partir de `[data da publicacao]`
**Contato:** contato@cultivee.com.br

## 1. Sobre o servico

Cultivee e uma plataforma de **Internet das Coisas (IoT) para cultivo vegetal**,
composta por:
- **Hardware** (dispositivos ESP32 pre-configurados nos modelos HIDRO, HIDRO-FARM e CAM);
- **Servico online** (`app.cultivee.com.br`) que permite controlar, monitorar e
  visualizar os dispositivos pela internet;
- **Aplicativo web** (PWA) instalavel em celular/desktop.

Este servico e oferecido por **`[razao social, CNPJ]`** ("Cultivee", "nos").

## 2. Quem pode usar

- Maiores de 18 anos com capacidade civil plena.
- Menores podem usar com consentimento de responsavel legal.
- Pessoas juridicas devem usar conta corporativa (com CNPJ).
- Aceitando estes termos, voce confirma que as informacoes do cadastro sao verdadeiras.

## 3. Conta, seguranca e uso aceitavel

- Sua conta e **pessoal e intransferivel**. Manter a senha em segredo e de sua responsabilidade.
- Ative o 2FA (recomendado) — disponivel em "Perfil → Seguranca".
- Voce se compromete a **nao**:
  - Tentar acessar dados de outros usuarios;
  - Fazer engenharia reversa ou explorar vulnerabilidades sem autorizacao;
  - Usar o servico para atividades ilegais;
  - Revender acesso sem autorizacao expressa.
- Violacoes podem levar a suspensao/encerramento da conta.

## 4. Pagamento, assinatura e cancelamento

> **TODO operacional**: esta secao depende do modelo comercial adotado.
> Minuta generica abaixo — ajustar conforme plano de precificacao real.

- O hardware e comprado separadamente (pagamento unico).
- O servico online pode ser gratuito (plano basico) ou pago (plano `[premium]`) —
  conforme anunciado em **cultivee.com.br/planos**.
- Pagamentos processados por `[gateway de pagamento — Stripe/PagSeguro/Mercado Pago]`. Nao armazenamos dados de cartao.
- Voce pode **cancelar a qualquer momento** sem multa. O acesso pago continua ate
  o fim do ciclo ja cobrado.
- Reembolso: primeiros **7 dias** apos ativacao, conforme CDC (Art. 49).

## 5. Garantia do hardware

- Garantia de **12 meses** contra defeitos de fabricacao, a partir da data de compra.
- Nao cobre:
  - Dano fisico (queda, liquido)
  - Modificacoes nao autorizadas (gravar firmware customizado, alterar circuito)
  - Uso fora das especificacoes (tensao errada, ambiente extremo)
  - Desgaste natural de componentes (reles tem vida util finita em chaveamentos)
- RMA: enviar email pra `suporte@cultivee.com.br` com serial, descricao e foto do defeito. Analise em ate 5 dias uteis.

## 6. Limitacao de responsabilidade

**LEIA COM ATENCAO** — os limites aqui sao importantes pra voce tomar
decisao informada antes de contratar.

- O servico e oferecido **"no estado em que se encontra"**, sem garantia de
  disponibilidade 100%. SLA almejado: **99% uptime mensal** (ajustar conforme SLA real).
- Quando o servico esta indisponivel, o dispositivo continua operando a
  automacao local (exceto camera). Em caso de queda de energia ou dano ao
  hardware, a automacao para — voce e responsavel por monitorar seu cultivo.
- **Cultivee nao se responsabiliza por**:
  - Perda de colheita ou plantacao;
  - Dano a equipamento conectado aos reles do dispositivo (iluminacao, bomba, etc.);
  - Consumo de energia alem do esperado;
  - Uso do dispositivo em ambiente que nao corresponde ao projeto (exterior, umidade alta).
- **Limite de responsabilidade financeira**: em qualquer circunstancia, nossa
  responsabilidade fica limitada ao **valor pago pelo hardware + 12 meses de
  assinatura**, exceto em caso de dolo ou culpa grave comprovada.

## 7. Propriedade intelectual

- O hardware, firmware, servidor, PWA, logotipo e nome "Cultivee" sao de propriedade da `[razao social]`.
- O **firmware** esta sob licenca proprietaria (binario). Partes de codigo-fonte
  podem ser disponibilizadas em GitHub (`github.com/mardoqueucosta/cultivee-platform`) — o que estiver publico la e licenciado conforme o LICENSE do repositorio.
- Voce adquire o hardware com **direito de uso pessoal**, nao adquire a propriedade intelectual do software embarcado.

## 8. Privacidade e LGPD

Tratamento de dados pessoais segue a **Politica de Privacidade** ([privacy.html](../server/templates/privacy.html)), que e parte integrante destes termos.

Voce tem direito a:
- Acessar, corrigir, exportar ou apagar seus dados;
- Revogar consentimento a qualquer momento;
- Reclamar a ANPD.

## 9. Alteracoes dos termos

Podemos atualizar estes termos com aviso de **30 dias** por email e banner no app.
Se voce discordar, pode cancelar a conta antes da vigencia.

## 10. Foro

- Lei aplicavel: **Republica Federativa do Brasil**.
- Foro: **`[comarca da sede da empresa]`** para dirimir duvidas, exceto quando
  a lei (como o CDC para pessoa fisica consumidora) determinar outro foro.

## 11. Contato

Para duvidas, reclamacoes ou exercer direitos LGPD:
- **Email geral**: contato@cultivee.com.br
- **Encarregado de dados (DPO)**: dpo@cultivee.com.br
- **Correspondencia**: `[endereco fisico da empresa]`

---

**Anexos (documentos relacionados):**
- [Politica de Privacidade](../server/templates/privacy.html)
- [Guia de Usuario](./manual-usuario.md)
- [AIPD](./lgpd-aipd.md) (interno — nao publicar)
