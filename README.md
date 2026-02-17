
# 👁️ AIOPS ZABBIX


> **Monitoramento Inteligente para Ambientes Críticos.**

O **AIOPS ZABBIX** é uma camada de inteligência artificial que transforma o monitoramento passivo do Zabbix em um sistema proativo. Ele captura incidentes em tempo real, utiliza IA (GPT-4o) para determinar a causa raiz técnica e sugere comandos de correção imediatos, exibindo tudo em um **TV Wallboard** de alto contraste e notificando via **Telegram**.

---

## 📸 Visão Geral

### 🖥️ NOC TV Wall
*Dashboard desenhado para grandes telas (TVs), com alertas visuais, suporte a Tags do Zabbix e atualização via WebSockets.*
<img width="1901" height="856" alt="image" src="https://github.com/user-attachments/assets/9b53d277-7962-4ec8-b5f3-ca7eca78f31d" />


### 📱 Telegram Alerts
*Notificações ricas com ícones de severidade, análise técnica resumida e comando para copiar.*
<img width="519" height="718" alt="image" src="https://github.com/user-attachments/assets/3260c323-279f-4fd8-965f-a70ea3eb7d83" />

---

## 🚀 Funcionalidades Enterprise

* **⚡ Real-Time Engine:** Backend assíncrono (FastAPI) que processa alertas em milissegundos.
* **🧠 Análise Neural:** A IA analisa o erro + contexto (Tags) e retorna:
  * *Causa Raiz:* Explicação técnica direta (ex: "Deadlock no MySQL").
  * *Ação:* Comando exato para resolver (ex: `systemctl restart mysql`).
* **💰 Controle de Custos:** Monitoramento em tempo real do consumo de Tokens da OpenAI direto no cabeçalho.
* **🏷️ Tags do Zabbix:** Integração nativa com tags (ex: `Scope: Availability`, `App: Nginx`) para melhor contexto visual.
* **💾 Smart Cache:** Sistema de cache em memória para resposta instantânea no Frontend, independente da latência do banco de dados.
* **🔐 Segurança:** Autenticação via Token no Dashboard e WebSocket.
* **📺 Modo TV:** Interface auto-ajustável com fontes grandes e alto contraste para salas de monitoramento (NOC).

---

## 🛠️ Instalação (Docker)

### 1. Clone o repositório
```bash
git clone https://github.com/Luan-Felipe-R-Sanches/AIOPS-ZABBIX.git
cd aiops-zabbix

```

### 2. Configure o Ambiente

Crie um arquivo `.env` na raiz do projeto com suas credenciais:

```ini
# --- Zabbix ---
ZABBIX_URL=http://seu-zabbix-ip:8080
ZABBIX_USER=Admin
ZABBIX_PASSWORD=sua_senha_zabbix

# --- Segurança (IMPORTANTE) ---
# Esta será a SENHA para entrar no Dashboard
DASHBOARD_TOKEN=defina_uma_senha_forte_aqui

# --- OpenAI ---
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini

# --- Telegram ---
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789

```

### 3. Execute

```bash
docker-compose up -d --build

```

---

## 🔐 Como Acessar (Login)

O sistema possui uma tela de login para proteger seu dashboard.

1. Acesse: `http://seu-servidor:8000`
2. **Senha de Acesso:** Digite o valor que você configurou na variável `DASHBOARD_TOKEN` dentro do arquivo `.env`.

> ⚠️ **Atenção:** Se você não alterou o arquivo `.env`, a senha será o token padrão que está escrito lá. Recomendamos alterá-lo para algo seguro antes de colocar em produção.

---

## ⚙️ Arquitetura Técnica

O sistema opera em um loop de eventos de alta performance:

1. **Polling Inteligente:** O Python consulta a API do Zabbix a cada 4s (configurável).
2. **Filtro de Relevância:** Ignora eventos já tratados ou irrelevantes.
3. **Pipeline de IA:**
* Envia Erro + Tags para a OpenAI (JSON Mode).
* Recebe Análise e Comando.


4. **Ação Simultânea:**
* Grava a análise no Zabbix (Acknowledge).
* Dispara notificação no Telegram.
* Atualiza o Cache de Memória.
* Envia via WebSocket para todas as TVs conectadas.



---

## 📂 Estrutura de Arquivos

```
aiops-zabbix/
├── app/
│   ├── templates/
│   │   ├── index.html       # NOC TV Wall (Frontend)
│   │   └── login.html       # Tela de Acesso
│   ├── main.py              # Core da Aplicação
│   ├── requirements.txt     # Dependências
│   └── Dockerfile           # Build da Imagem
├── docker-compose.yml       # Orquestração
├── .env                     # Configurações (Ignorado pelo Git)
└── README.md                # Documentação

```

---
