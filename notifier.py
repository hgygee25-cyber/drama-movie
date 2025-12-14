# notifier.py (수정 버전: 텔레그램, 이메일 지원)

import requests
import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart  # 이메일 전송을 위해 추가
import ssl  # SSL context for email

# =================================================================
# 1. 공통 설정 (⚠️ 반드시 본인의 정보로 수정하세요!)
# =================================================================

# 🌟 1. 텔레그램 봇 토큰 (실제 토큰으로 변경해야 작동합니다)
TELEGRAM_BOT_TOKEN = "8550446450:AAEVJfyFfP5oNnIJVEmOJC7uSfgekirAz_Q"

# 🌟 2. 이메일 SMTP 설정 (Gmail 예시 - 실제 정보로 변경해야 작동합니다)
# ⚠️ SENDER_PASSWORD는 실제 비밀번호 대신 '앱 비밀번호'를 사용해야 보안이 안전합니다.
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "hgygee25@gmail.com"  # ⚠️ 보내는 사람 이메일 주소로 수정
SENDER_PASSWORD = "eeib hkqn cmas askm"  # ⚠️ 이메일 앱 비밀번호(Gmail의 경우)로 수정


# =================================================================
# 2. 알림 채널별 발송 함수 (수신자 정보를 인수로 받도록 변경)
# =================================================================

def send_telegram_message(chat_id: str, message: str) -> bool:
    """지정된 텔레그램 Chat ID로 메시지를 전송합니다."""
    # 토큰이 기본값이거나 chat_id가 비어있으면 전송하지 않음
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        print("❌ 텔레그램 토큰 미설정 또는 Chat ID가 유효하지 않습니다.")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': chat_id,  # 동적 ID 사용
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, data=data)
        if response.json().get('ok'):
            print(f"✅ 텔레그램 알림 성공: {chat_id}")
            return True
        else:
            print(f"❌ 텔레그램 알림 실패 ({chat_id}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ 텔레그램 알림 요청 중 오류 발생: {e}")
        return False


def send_email_message(recipient_email: str, subject: str, body: str) -> bool:
    """지정된 이메일 주소로 이메일을 전송합니다."""
    # 이메일 설정이 기본값이거나 수신자 이메일이 유효하지 않으면 전송하지 않음
    if SENDER_EMAIL == "your_email@gmail.com" or not recipient_email or "@" not in recipient_email:
        print("❌ 이메일 전송 정보 미설정 또는 수신자 이메일 주소가 유효하지 않습니다.")
        return False

    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        print(f"✅ 이메일 알림 성공: {recipient_email}")
        return True
    except Exception as e:
        print(f"❌ 이메일 알림 실패 ({recipient_email}): {e}")
        return False


def send_web_notification(message: str) -> bool:
    """웹 푸시 알림 PLACEHOLDER 함수 (실제 구현 필요)"""
    # Streamlit은 서버 측이므로, 실제 웹 푸시를 하려면 별도의 서비스(VAPID) 연동이 필요합니다.
    print("⚠️ 웹 알림 기능은 현재 PLACEHOLDER로 처리됩니다. 실제 구현은 별도 작업이 필요합니다.")
    return True


# =================================================================
# 3. 통합 알림 발송 함수 (4) streamlit.py에서 호출할 메인 함수)
# =================================================================
def send_notification_to_user(reservation_data: dict, df_row: dict):
    """예약 정보에 따라 필요한 모든 채널로 알림을 보냅니다."""

    # 예약 정보
    title = df_row['title']
    channel = df_row['channel']
    platform = df_row['platform']
    time_str = df_row['broadcast_time']

    minutes = reservation_data.get('alert_minutes_before', 5)  # 기본 5분 전

    # 텔레그램 메시지
    telegram_message = (
        f"🔔 **방영 알림!**\n\n"
        f"🎬 **{title}**\n"
        f"📺 채널/OTT: **{channel}** ({platform})\n"
        f"⏰ **{time_str}** 방영 시작이 곧 다가옵니다!\n"
        f"놓치지 마세요!"
    )

    # 이메일 메시지
    email_body = (
        f"[방영 알림]\n\n"
        f"프로그램: {title}\n"
        f"채널/OTT: {channel} ({platform})\n"
        f"방영 시간: {time_str}\n"
        f"{minutes}분 후 방영 시작입니다!"
    )

    is_sent = False
    options = reservation_data.get('options', [])
    contact = reservation_data.get('contact_info', {})

    # 텔레그램 발송
    if 'telegram' in options and contact.get('telegram'):
        ok = send_telegram_message(contact['telegram'], telegram_message)
        if ok:
            is_sent = True

    # 이메일 발송
    if 'email' in options and contact.get('email'):
        ok = send_email_message(contact['email'], f"[방영 알림] {title}", email_body)
        if ok:
            is_sent = True

    return is_sent
