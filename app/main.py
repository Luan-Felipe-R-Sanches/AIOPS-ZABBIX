import os
import asyncio
import json
import logging
import unicodedata
import random
import re
from datetime import datetime
from typing import List, Set, Dict, Optional

from fastapi import FastAPI, WebSocket, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import APIKeyCookie
from dotenv import load_dotenv
import aiohttp
from openai import AsyncOpenAI

# --- Configurações ---
load_dotenv()
ZABBIX_URL = os.getenv("ZABBIX_URL")
ZABBIX_USER = os.getenv("ZABBIX_USER")
ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AIOPS")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# --- ESTADO GLOBAL ---
zabbix_auth_token = None
processing_events: Set[str] = set()
handled_events: Set[str] = set()
ai_memory_cache: Dict[str, dict] = {} 
total_tokens_used = 0

# --- Helpers ---
def format_tags_text(tags):
    if not tags: return ""
    return ", ".join([f"{t['tag']}:{t['value']}" if t['value'] else t['tag'] for t in tags[:4]])

# --- Integrações ---
async def send_telegram_alert(host, problem, severity, ai_summary, ai_action, tags):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    await asyncio.sleep(random.uniform(0.5, 1.5))
    
    sev_icon = {'Info': 'ℹ️', 'Aviso': '⚠️', 'Média': '🟠', 'Alta': '🔥', 'Crítica': '☠️'}.get(severity, '❓')
    tag_list = [f"#{t['tag']}:{t['value']}" if t['value'] else f"#{t['tag']}" for t in tags[:3]]
    tag_str = " ".join(tag_list)
    
    html_text = f"<b>{sev_icon} {severity.upper()} | {host}</b>\n<code>{problem}</code>\n\n🤖 <b>Análise IA:</b>\n{ai_summary}\n\n🚀 <b>Ação:</b>\n<pre>{ai_action}</pre>\n<span class=\"tg-spoiler\">{tag_str}</span>"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": html_text, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200: logger.error(f"Telegram Erro: {await resp.text()}")
    except: pass

async def get_zabbix_token():
    payload = {"jsonrpc": "2.0", "method": "user.login", "params": {"username": ZABBIX_USER, "password": ZABBIX_PASSWORD}, "id": 1}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{ZABBIX_URL}/api_jsonrpc.php", json=payload) as resp:
                data = await resp.json()
                return data.get('result')
    except: return None

async def post_zabbix_comment(event_id, message):
    if not zabbix_auth_token: return False
    payload = {"jsonrpc": "2.0", "method": "event.acknowledge", "params": {"eventids": event_id, "action": 4, "message": message}, "auth": zabbix_auth_token, "id": 99}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{ZABBIX_URL}/api_jsonrpc.php", json=payload) as resp:
                await resp.json()
                return True
    except: return False

# --- IA ---
async def analyze_with_ai(problem_name, host_name, tags):
    global total_tokens_used
    context = format_tags_text(tags)
    prompt = f"Contexto: {context}\nErro: {problem_name}\nHost: {host_name}\nResponda JSON:\n{{\"analysis\": \"Causa (max 20 palavras)\", \"command\": \"Comando Linux ou 'Verificar logs'\"}}"
    try:
        response = await aclient.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        if response.usage: total_tokens_used += response.usage.total_tokens
        return json.loads(response.choices[0].message.content)
    except: return {"analysis": "Erro IA", "command": "N/A"}

async def run_ai_pipeline(event_id, problem, host, severity, tags):
    try:
        logger.info(f"🧠 Analisando: {problem}")
        ai_data = await analyze_with_ai(problem, host, tags)
        summary = ai_data.get("analysis", "Indisponível")
        action = ai_data.get("command", "N/A")
        
        zabbix_msg = f"IA: {summary} | CMD: {action}"
        ai_memory_cache[event_id] = {"summary": summary, "action": action}
        
        await post_zabbix_comment(event_id, zabbix_msg)
        sev_map = {'1':'Info', '2':'Aviso', '3':'Média', '4':'Alta', '5':'Crítica'}
        await send_telegram_alert(host, problem, sev_map.get(str(severity), 'Erro'), summary, action, tags)
    except Exception as e: logger.error(f"Pipeline: {e}")
    finally:
        if event_id in processing_events: processing_events.remove(event_id)

async def process_queue(triggers):
    global processing_events, handled_events
    for t in triggers:
        ev = t.get('lastEvent', {})
        eid = ev.get('eventid')
        if not eid or eid in processing_events or eid in handled_events: continue
        if eid in ai_memory_cache: continue

        has_ack = False
        for ack in ev.get('acknowledges', []):
            if "IA:" in ack.get('message', ''):
                has_ack = True
                try:
                    parts = ack['message'].split('| CMD:')
                    ai_memory_cache[eid] = {"summary": parts[0].replace('IA:', '').strip(), "action": parts[1].strip() if len(parts) > 1 else "N/A"}
                except: pass
                break
        
        if not has_ack:
            processing_events.add(eid)
            handled_events.add(eid)
            asyncio.create_task(run_ai_pipeline(eid, t['description'], t['hosts'][0]['name'], t['priority'], t.get('tags', [])))

async def fetch_data():
    global zabbix_auth_token
    if not zabbix_auth_token:
        zabbix_auth_token = await get_zabbix_token()
        if not zabbix_auth_token: return []

    payload = {
        "jsonrpc": "2.0", "method": "trigger.get",
        "params": {
            "output": ["triggerid", "description", "priority", "lastchange"],
            "selectHosts": ["name"], "selectLastEvent": "extend", "selectTags": "extend",
            "only_true": True, "monitored": True, "active": True, "expandDescription": True, "sortfield": "lastchange", "sortorder": "DESC"
        },
        "auth": zabbix_auth_token, "id": 2
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{ZABBIX_URL}/api_jsonrpc.php", json=payload) as resp:
                data = await resp.json()
                if 'error' in data: 
                    zabbix_auth_token = None
                    return []
                triggers = data.get('result', [])
                await process_queue(triggers)
                return triggers
    except: return []

def format_dashboard(triggers):
    if not triggers: return None
    formatted = []
    stats = {"total": 0, "critical": 0, "tokens": total_tokens_used}
    for t in triggers:
        stats["total"] += 1
        if t['priority'] in ['4', '5']: stats["critical"] += 1
        eid = t.get('lastEvent', {}).get('eventid')
        summary = ai_memory_cache.get(eid, {}).get('summary', "Aguardando...") if eid in ai_memory_cache else ("⚡ Processando..." if eid in processing_events else "Aguardando...")
        action = ai_memory_cache.get(eid, {}).get('action')
        frontend_tags = [f"{tag['tag']}: {tag['value']}" if tag['value'] else tag['tag'] for tag in t.get('tags', [])[:4]]
        formatted.append({
            "id": eid or t['triggerid'], "host": t['hosts'][0]['name'] if t['hosts'] else "?",
            "problem": t['description'], "severity": t['priority'],
            "time": datetime.fromtimestamp(int(t['lastchange'])).strftime('%H:%M'),
            "tags": frontend_tags, "ai_summary": summary, "ai_action": action
        })
    return {"stats": stats, "data": formatted}

async def loop():
    logger.info("🚀 AIOPS v9 (Fixed Syntax) Iniciado")
    while True:
        try:
            raw = await fetch_data()
            dash = format_dashboard(raw)
            if dash: await manager.broadcast(json.dumps(dash))
        except Exception as e: logger.error(f"Loop: {e}")
        await asyncio.sleep(4)

@app.on_event("startup")
async def startup(): asyncio.create_task(loop())

# --- ROTAS ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, token: str = Form(...)):
    if token == DASHBOARD_TOKEN:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="access_token", value="authorized", httponly=True)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Token Inválido"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    token = request.cookies.get("access_token")
    if not token or token != "authorized":
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    token = websocket.cookies.get("access_token")
    if not token or token != "authorized":
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        manager.disconnect(websocket)