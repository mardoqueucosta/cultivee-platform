"""
Cultivee - Camada PUBLIC (v4.1.30)

Endpoints publicos consumidos pelo site institucional (cultivee.com.br):
- Formulario de contato (/api/public/contact)
- Inscricao newsletter (/api/public/newsletter)

Diferente das outras camadas, aqui os endpoints NAO exigem autenticacao — sao
acessados direto do navegador dos visitantes do site marketing. Protecoes:
- Honeypot (campo `company_fax` invisivel pros humanos, bots preenchem)
- Rate limit in-memory (5 envios/hora por IP)
- Validacao de campos + limite de tamanho da mensagem
- escape HTML no conteudo antes de inserir no email
- CORS restrito (configurado no app.py) — so cultivee.com.br e www.cultivee.com.br

Segue o mesmo padrao do /api/contact do biopdi-nextjs (nodemailer + escapeHtml +
honeypot + rate limit), adaptado para Flask + smtplib.
"""
