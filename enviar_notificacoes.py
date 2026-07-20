# ============================================================
# ROBÔ DE NOTIFICAÇÕES — Agenda "Meu Dia"
# Roda no GitHub Actions a cada 10 minutos.
# Lê as agendas no Firebase Realtime Database e envia,
# via Firebase Cloud Messaging (FCM):
#   1. O resumo matinal, no horário configurado por cada usuário
#   2. Os lembretes de cada compromisso do dia
# ============================================================

import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, db, messaging

# ---------- Configuração (vem dos "Secrets" do GitHub) ----------
FUSO = ZoneInfo("America/Sao_Paulo")
LINK_DO_APP = "https://oprogramadordoseculo.github.io/agendapersonalizada/"

credenciais_json = os.environ["FIREBASE_CREDENCIAIS"]
database_url = os.environ["DATABASE_URL"]

cred = credentials.Certificate(json.loads(credenciais_json))
firebase_admin.initialize_app(cred, {"databaseURL": database_url})

# ---------- Utilitários de data ----------
def hoje_str(agora):
    return agora.strftime("%Y-%m-%d")

def dia_da_semana(data_str):
    a, m, d = map(int, data_str.split("-"))
    return datetime(a, m, d).weekday()  # segunda=0 ... domingo=6

def ocorre_em(evento, data_str):
    """O evento ocorre nesta data? (trata repetições)"""
    if data_str < evento.get("data", "9999-12-31"):
        return False
    repete = evento.get("repete", "nao")
    if repete == "diario":
        return True
    if repete == "semanal":
        return dia_da_semana(data_str) == dia_da_semana(evento["data"])
    return evento["data"] == data_str

def esta_concluido(evento, data_str):
    return data_str in (evento.get("concluidoEm") or [])

# ---------- Envio via FCM ----------
def enviar(token, titulo, corpo):
    mensagem = messaging.Message(
        token=token,
        notification=messaging.Notification(title=titulo, body=corpo),
        webpush=messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(link=LINK_DO_APP)
        ),
    )
    messaging.send(mensagem)

# ---------- Lógica principal ----------
def processar():
    agora = datetime.now(FUSO)
    hoje = hoje_str(agora)
    agendas = db.reference("agendas").get() or {}
    print(f"[{agora:%d/%m %H:%M}] {len(agendas)} agenda(s) na nuvem.")

    for id_usuario, agenda in agendas.items():
        token = agenda.get("token")
        if not token:
            continue

        eventos = agenda.get("eventos") or []
        eventos_hoje = sorted(
            [e for e in eventos if ocorre_em(e, hoje)],
            key=lambda e: e.get("hora") or "99:99",
        )

        # ----- 1. Resumo matinal -----
        try:
            h, m = map(int, (agenda.get("horaResumo") or "07:00").split(":"))
            hora_resumo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
            if agora >= hora_resumo and agenda.get("ultimoResumo") != hoje:
                if eventos_hoje:
                    linhas = [
                        (f"{e['hora']} — " if e.get("hora") else "") + e.get("titulo", "")
                        for e in eventos_hoje[:5]
                    ]
                    corpo = "\n".join(linhas)
                    if len(eventos_hoje) > 5:
                        corpo += f"\n…e mais {len(eventos_hoje) - 5}."
                else:
                    corpo = "Nenhum compromisso agendado. Dia livre! ✦"
                enviar(token, "🌅 Seu dia de hoje", corpo)
                db.reference(f"agendas/{id_usuario}/ultimoResumo").set(hoje)
                print(f"  Resumo enviado para {id_usuario}")
        except Exception as erro:
            print(f"  Erro no resumo de {id_usuario}: {erro}")

        # ----- 2. Lembretes dos compromissos -----
        # Janela de 12 min: cobre o intervalo entre execuções do robô
        for evento in eventos_hoje:
            try:
                hora = evento.get("hora")
                lembrete_min = int(evento.get("lembreteMin", -1))
                if not hora or lembrete_min < 0 or esta_concluido(evento, hoje):
                    continue
                h, m = map(int, hora.split(":"))
                momento = agora.replace(hour=h, minute=m, second=0, microsecond=0)
                disparo = momento - timedelta(minutes=lembrete_min)
                if not (disparo <= agora <= disparo + timedelta(minutes=12)):
                    continue
                chave = f"{hoje}|{evento.get('id')}"
                ref_enviados = db.reference(f"agendas/{id_usuario}/enviados/{chave.replace('|', '_')}")
                if ref_enviados.get():
                    continue  # já foi enviado
                texto = (
                    f"Em {lembrete_min} minutos ({hora})."
                    if lembrete_min > 0
                    else f"Agora ({hora})."
                )
                enviar(token, "⏰ " + evento.get("titulo", "Compromisso"), texto)
                ref_enviados.set(True)
                print(f"  Lembrete '{evento.get('titulo')}' enviado para {id_usuario}")
            except Exception as erro:
                print(f"  Erro em lembrete de {id_usuario}: {erro}")

if __name__ == "__main__":
    processar()
