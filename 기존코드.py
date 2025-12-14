# final_streamlit.py
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import re
import pytz


# =================================================================
# 0. 초기 설정 및 라이브러리 로드
# =================================================================

# KST Timezone 객체 정의
KST = pytz.timezone('Asia/Seoul')

# 🚨 알림 모듈 불러오기
try:
    from notifier import send_notification_to_user
except ImportError:
    def send_notification_to_user(reservation_data, df_row):
        print(f"[Dummy Notifier] 알림 전송 요청: {df_row.get('title')}")
        return False

# 파일 경로 설정
DATA_FILE = 'final_crawling.csv'
RESERVATION_FILE = 'reservations.json'
FAVORITE_FILE = 'favorites.json'
CONFIG_FILE = 'config.json'


# =================================================================
# 1. 데이터 로드 (수정 없음)
# =================================================================
@st.cache_data
def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame()

    try:
        df = pd.read_csv(DATA_FILE, encoding='utf-8-sig')
    except Exception as e:
        st.error(f"데이터 파일 읽기 오류: {e}")
        return pd.DataFrame()

    df = df.fillna('')

    # [핵심] 명시적인 OTT 플랫폼 리스트 정의
    OTT_NAMES = {'NETFLIX', 'COUPANG PLAY', 'BOXOFFICE', 'TVING', 'WATCHA', 'WAVVE', 'DISNEY+'}

    # [수정] OTT/TV 구분 정규화 로직
    def normalize_platform_channel(row):
        source = str(row.get('source', '')).strip().upper()
        raw_platform = str(row.get('platform', '')).strip()
        raw_channel = str(row.get('channel', '')).strip()

        p_upper = raw_platform.upper()
        c_upper = raw_channel.upper()

        # 1. source가 OTT이거나, platform/channel에 명시된 OTT 이름이 있는 경우
        is_explicitly_ott = source == 'OTT' or p_upper in OTT_NAMES or c_upper in OTT_NAMES

        if is_explicitly_ott:
            # 실제 OTT 이름 (예: Netflix)을 찾아서 채널명으로 설정
            ott_name = ""
            if p_upper in OTT_NAMES:
                ott_name = raw_platform
            elif c_upper in OTT_NAMES:
                ott_name = raw_channel
            elif source == 'OTT' and raw_platform:
                ott_name = raw_platform
            elif raw_channel and raw_channel.upper() != 'OTT':
                ott_name = raw_channel
            else:
                ott_name = 'OTT'

            # 결과: platform='OTT' (구분), channel=OTT_NAME (채널명)
            return 'OTT', ott_name

        # 2. TV/Cable인 경우 (source='TV'이거나 platform이 'Cable')
        if source == 'TV' or p_upper == 'CABLE':
            # platform='Cable/TV'로 통일하여 화면에 표시
            return 'Cable/TV', raw_channel

            # 3. 기타 (기존 값 유지)
        return raw_platform, raw_channel

    if 'platform' in df.columns and 'channel' in df.columns:
        new_cols = df.apply(normalize_platform_channel, axis=1, result_type='expand')
        df['platform'] = new_cols[0]
        df['channel'] = new_cols[1]

    # 장르 정규화 (기존 로직 유지)
    def normalize_text(text_str):
        if not isinstance(text_str, str) or not text_str.strip():
            return str(text_str)
        text_map = {
            'DRAMA': '드라마', 'MOVIE': '영화', 'ACTION': '액션',
            'COMEDY': '코미디', 'ROMANCE': '로맨스', 'DOCUMENTARY': '다큐멘터리'
        }
        upper_text = text_str.upper()
        return text_map.get(upper_text, text_str.title())

    if 'genre' in df.columns:
        df['genre'] = df['genre'].apply(normalize_text)
    else:
        df['genre'] = ''

    # 날짜/시간 결합 로직 (OTT 데이터 보존 로직 유지)
    def clean_date_and_combine(row):
        p_str = str(row.get('platform', '')).strip().upper()

        # 정규화된 platform 컬럼이 'OTT'인 경우 현재 시간을 부여해 dropna 방지
        if p_str == 'OTT':
            return datetime.now(KST).strftime('%y%m%d %H%M')

        # TV 프로그램 처리 (기존 로직 유지)
        date_part = str(row.get('broadcast_date', '')).split(' ')[0]
        time_part = str(row.get('broadcast_time', '')).replace(':', '').strip().zfill(4)
        current_year = str(datetime.now().year)[2:]
        ymd_part = ""

        if date_part:
            try:
                dt_obj = pd.to_datetime(date_part, errors='raise').strftime('%y%m%d')
                ymd_part = dt_obj
            except:
                pass

        if not ymd_part and '.' in date_part:
            try:
                month, day = date_part.split('.')
                ymd_part = f"{current_year}{month.zfill(2)}{day.zfill(2)}"
            except:
                pass

        if not ymd_part:
            ymd_part = datetime.now().strftime('%y%m%d')

        if not time_part or time_part == '0000':
            return f"{ymd_part} 0000"

        return f"{ymd_part} {time_part}"

    df['full_time'] = df.apply(clean_date_and_combine, axis=1)
    df['datetime'] = pd.to_datetime(df['full_time'], format='%y%m%d %H%M', errors='coerce')
    df.dropna(subset=['datetime'], inplace=True)
    df['datetime'] = df['datetime'].dt.tz_localize(KST)

    def get_time_slot(hour):
        if 5 <= hour < 12: return '오전 (5시~11시)'
        if 12 <= hour < 18: return '오후 (12시~17시)'
        if 18 <= hour < 22: return '저녁 (18시~21시)'
        return '심야/새벽 (22시~4시)'

    df['time_slot'] = df['datetime'].dt.hour.apply(get_time_slot)
    df.sort_values(by='datetime', ascending=True, inplace=True)
    return df


# =================================================================
# 2. JSON 파일 로드/저장 함수 (config.json 로직 보강)
# =================================================================
def load_json_file(filepath, is_set=False):
    if filepath == RESERVATION_FILE:
        is_set = True

    # 💡 config.json 로드를 위한 기본값 정의
    DEFAULT_CONFIG = {
        'notification_methods': ['telegram'],
        'notification_minutes': 5,
        'contact_info': {'telegram': '', 'email': ''},  # 연락처 정보 추가
        'openai_api_key': ''  # 챗봇 API 키 기본값 추가
    }

    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)

                if filepath == CONFIG_FILE:
                    # 기존 데이터가 딕셔너리 형태가 아니거나 없으면 기본값 반환
                    if not isinstance(data, dict):
                        return DEFAULT_CONFIG

                    # 기존 데이터를 로드한 후, 누락된 키(특히 openai_api_key)는 기본값으로 채우기
                    config = DEFAULT_CONFIG.copy()
                    config.update(data)
                    return config

                if is_set:
                    return set(data) if isinstance(data, list) else set()
                return data if isinstance(data, dict) else {}

            except (json.JSONDecodeError, KeyError, TypeError):
                # 파일 내용 오류 시: config는 기본값 반환, 다른 파일은 빈 값 반환
                if filepath == CONFIG_FILE:
                    return DEFAULT_CONFIG
                return set() if is_set else {}

    # 파일 자체가 없을 경우: config는 기본값 반환, 다른 파일은 빈 값 반환
    if filepath == CONFIG_FILE:
        return DEFAULT_CONFIG
    return set() if is_set else {}


def save_json_file(filepath, data, is_set=False):
    # ... (이 함수는 수정할 필요 없음)
    if filepath == RESERVATION_FILE:
        is_set = True
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            if is_set:
                json.dump(list(data), f, ensure_ascii=False, indent=4)
            else:
                json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")


# =================================================================
# 3. 데이터 에디터 핸들러 (수정: 상세보기 로직 통합 및 RERUN 수정)
# =================================================================
def handle_editor_changes():
    if 'schedule_editor' not in st.session_state or 'current_display_df' not in st.session_state:
        return

    editor_state = st.session_state.get('schedule_editor', {})
    edited_rows = editor_state.get('edited_rows', {})
    df_current = st.session_state.get('current_display_df', None)

    if df_current is None or not edited_rows:
        return

    current_reservations = load_json_file(RESERVATION_FILE, is_set=True)
    current_favorites = load_json_file(FAVORITE_FILE, is_set=True)
    reservation_changes_made = False
    favorite_changes_made = False
    detail_change_detected = False  # 💡 추가: 상세보기 변경 플래그

    if 'toast_list' not in st.session_state:
        st.session_state.toast_list = []
    temp_toast_list = []
    now_kst = datetime.now(KST)

    for row_idx, updates in edited_rows.items():
        try:
            row_idx_int = int(row_idx)
            # 편집된 행의 원본 데이터를 현재 표시 중인 DataFrame에서 가져옴
            row = df_current.iloc[row_idx_int]
        except Exception:
            continue

        program_title = row['title']

        # [핵심] 정규화된 platform_type (OTT 또는 Cable/TV)을 사용하여 OTT 판단
        is_ott = (str(row.get('platform_type', '')).upper() == 'OTT')

        # 종료 여부 판단
        is_ended = False
        if not is_ott:
            try:
                prog_dt_kst = row['datetime']
                is_ended = (prog_dt_kst < now_kst)
            except Exception:
                is_ended = True

        # ------------------------------------------------------------------
        # 1. 상세보기 처리 (NEW)
        # ------------------------------------------------------------------
        if '상세보기' in updates:
            is_checked = updates["상세보기"]
            if is_checked:
                # 상세보기를 켠 경우: 해당 row index 저장
                st.session_state['detail_view_row_index'] = row_idx_int
            else:
                # 상세보기를 끈 경우: 현재 인덱스이면 해제
                if st.session_state.get('detail_view_row_index') == row_idx_int:
                    st.session_state['detail_view_row_index'] = None

            detail_change_detected = True

        # ------------------------------------------------------------------
        # 2. 예약 처리 (Existing logic)
        # ------------------------------------------------------------------
        if '예약' in updates:
            new_state = updates['예약']
            if new_state:
                if is_ott or is_ended:
                    # 예약 불가 (UI는 다음 렌더링에서 자동으로 False로 돌아감)
                    if is_ott:
                        temp_toast_list.append(("❌ OTT 프로그램은 예약할 수 없습니다.", '🚫'))
                    else:
                        temp_toast_list.append(("❌ 이미 종료된 프로그램은 예약할 수 없습니다.", '🚫'))
                elif program_title not in current_reservations:
                    current_reservations.add(program_title)
                    temp_toast_list.append((f"📅 '{program_title}' 예약 완료!", '📌'))
                    reservation_changes_made = True
            else:
                if program_title in current_reservations:
                    current_reservations.remove(program_title)
                    temp_toast_list.append((f"🗑️ '{program_title}' 예약 취소됨", '❌'))
                    reservation_changes_made = True

        # 3. 즐겨찾기 처리 (Existing logic)
        if '⭐ 즐겨찾기' in updates:
            fav_state = updates['⭐ 즐겨찾기']
            if fav_state and program_title not in current_favorites:
                current_favorites.add(program_title)
                temp_toast_list.append((f"⭐ '{program_title}' 즐겨찾기 추가", '👍'))
                favorite_changes_made = True
            elif not fav_state and program_title in current_favorites:
                current_favorites.remove(program_title)
                temp_toast_list.append((f"➖ '{program_title}' 즐겨찾기 제거", '👎'))
                favorite_changes_made = True

    st.session_state.toast_list.extend(temp_toast_list)

    # 💡 RERUN 로직 통합: 예약/즐겨찾기 변경이 있거나, 상세보기 변경이 있으면 RERUN
    if reservation_changes_made or favorite_changes_made:
        # 영구 저장되는 데이터가 변경된 경우
        if reservation_changes_made:
            save_json_file(RESERVATION_FILE, current_reservations, is_set=True)
        if favorite_changes_made:
            save_json_file(FAVORITE_FILE, current_favorites, is_set=True)
        st.rerun()

    elif detail_change_detected:
        # 상세보기 상태만 변경된 경우 (이전 단계에서 누락될 수 있던 부분)
        st.rerun()

    # =================================================================


# 4. 알림 전송 로직 (수정 없음)
# =================================================================
def check_and_send_notifications_set_compat(df, reservations_set, config):
    now = datetime.now(KST)
    notified_list = []

    methods = config.get('notification_methods', ['telegram']) if isinstance(config, dict) else ['telegram']
    minutes_before = config.get('notification_minutes', 5) if isinstance(config, dict) else 5
    contact_info = config.get('contact_info', {'telegram': '', 'email': ''}) if isinstance(config, dict) else {
        'telegram': '', 'email': ''}

    if not isinstance(reservations_set, set) or not reservations_set:
        return

    df_reserved = df[df['title'].isin(reservations_set)].copy()
    sent_notifications_file = 'sent_notifications.json'
    sent_reservations = load_json_file(sent_notifications_file, is_set=True)

    reservation_data = {
        'alert_minutes_before': minutes_before,
        'options': methods,
        'contact_info': contact_info
    }

    for index, row in df_reserved.iterrows():
        title = row['title']
        full_time_str = row.get('full_time', '')
        notification_key = f"{title}_{full_time_str}_{minutes_before}"

        if notification_key in sent_reservations:
            continue

        try:
            # OTT나 시간이 없는 경우 패스
            if full_time_str.endswith('0000') or pd.isna(row.get('datetime', None)) or str(
                    row.get('platform', '')).upper() == 'OTT':
                continue

            broadcast_dt = row['datetime']
            target_time = broadcast_dt - timedelta(minutes=minutes_before)

            if now >= target_time and now < target_time + timedelta(seconds=30):
                df_row_dict = row.to_dict()
                options = reservation_data.get('options', [])

                external_options = [opt for opt in options if opt != 'web']
                external_reservation_data = reservation_data.copy()
                external_reservation_data['options'] = external_options

                external_sent = False
                try:
                    external_sent = send_notification_to_user(external_reservation_data, df_row_dict)
                except Exception as e:
                    print(f"외부 알림 전송 예외: {e}")
                    external_sent = False

                web_sent = False
                if 'web' in options:
                    st.toast(f"💻 웹 알림: '{title}' 방영 {minutes_before}분 전입니다.", icon='💻')
                    web_sent = True

                if external_sent or web_sent:
                    notified_list.append(notification_key)
                    st.toast(f"✅ 알림 발송 완료: '{title}'", icon='📣')

        except Exception as e:
            continue

    if notified_list:
        sent_reservations.update(notified_list)
        save_json_file(sent_notifications_file, sent_reservations, is_set=True)


# =================================================================
# 5. 화면 UI 구현 (수정: 랭킹 정보를 제목에 통합)
# =================================================================
def render_home_screen(df, reservations, favorites):
    st.caption("💡 정규방송과 일일 랭킹 TOP 100의 OTT 드라마/영화 방영 정보를 제공합니다.")

    # 상단 검색바/필터바 (기존 유지)
    col1, col2 = st.columns([1, 2])
    with col1:
        search_option = st.selectbox('🔍 검색 기준', ['전체', '제목', '배우', '감독', '장르' ], key='search_opt')
    with col2:
        search_query = st.text_input('검색어 입력 (엔터키를 누르세요)', '', key='search_q').strip().lower()

    col3, col4, col5 = st.columns([1, 1, 1])
    with col3:
        sort_option = st.selectbox('📊 정렬 기준', ['시간 순', '제목 순', '채널 순'], key='sort_opt')
    with col4:
        time_slots = ['전체', '오전 (5시~11시)', '오후 (12시~17시)', '저녁 (18시~21시)', '심야/새벽 (22시~4시)']
        time_slot_filter = st.selectbox('⏰ 시간대 필터', time_slots, key='time_filter')
    with col5:
        st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
        show_reservations_only = st.checkbox('🔒 예약 목록만 보기', key='show_res_only')

    st.markdown("---")

    # 데이터 필터링/정렬 (기존 유지)
    df_filtered = df.copy()

    # 검색 필터링 로직 (기존 유지)
    if search_query:
        def contains_safe(col):
            if col in df_filtered.columns:
                return df_filtered[col].astype(str).str.lower().str.contains(search_query, na=False)
            return pd.Series([False] * len(df_filtered), index=df_filtered.index)

        if search_option == '제목':
            df_filtered = df_filtered[contains_safe('title')]
        elif search_option == '배우':
            df_filtered = df_filtered[contains_safe('cast')]
        elif search_option == '감독':
            df_filtered = df_filtered[contains_safe('director')]
        elif search_option == '장르':
            df_filtered = df_filtered[contains_safe('genre')]
        else:
            mask = (contains_safe('title') | contains_safe('cast') | contains_safe('director') | contains_safe('genre'))
            df_filtered = df_filtered[mask]

    if time_slot_filter != '전체' and 'time_slot' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['time_slot'] == time_slot_filter]

    if show_reservations_only:
        df_filtered = df_filtered[df_filtered['title'].isin(reservations)]

    if sort_option == '시간 순':
        df_filtered.sort_values(by='datetime', ascending=True, inplace=True)
    elif sort_option == '제목 순':
        df_filtered.sort_values(by='title', ascending=True, inplace=True)
    elif sort_option == '채널 순':
        cols = [c for c in ['platform', 'channel'] if c in df_filtered.columns]
        if cols: df_filtered.sort_values(by=cols, ascending=True, inplace=True)

    # -------------------------------------------------------------
    # [화면 구성] 리스트 생성 (수정: 랭킹 정보를 제목에 통합)
    # -------------------------------------------------------------
    display_list = []
    now = datetime.now(KST)

    # 상세보기 상태 초기화 (Index 기반)
    if 'detail_view_row_index' not in st.session_state:
        st.session_state['detail_view_row_index'] = None

    for idx, row in df_filtered.iterrows():
        program_title_raw = row.get('title', '')

        # [핵심] 정규화된 platform 컬럼을 사용: 'OTT' 또는 'Cable/TV'
        raw_platform = str(row.get('platform', '')).strip()
        raw_channel = str(row.get('channel', '')).strip()

        is_ott = (raw_platform.upper() == 'OTT')

        display_title = program_title_raw  # 기본 제목 설정

        if is_ott:
            p_type = 'OTT'  # 구분: OTT
            c_name = raw_channel  # 채널명: Netflix, Coupang Play 등
            disp_time = "-"

            # 🚀 랭킹 정보를 제목에 통합
            rank = row.get('rank')
            rank_change = row.get('rank_change', '')

            if pd.notna(rank) and rank != '':
                try:
                    rank_int = int(float(rank))  # rank가 float으로 로드될 수 있음
                    rank_text = f"({rank_int}위"

                    if rank_change:
                        change_str = str(rank_change).strip()
                        if change_str:
                            change_value = change_str.replace('+', '').replace('-', '')

                            # 화살표 아이콘 결정
                            if change_str.startswith('+'):
                                change_sign = '▲'
                            elif change_str.startswith('-'):
                                change_sign = '▼'
                            elif change_str.upper() == 'NEW':
                                change_sign = 'NEW'
                                change_value = ''
                            else:
                                change_sign = '='
                                change_value = ''

                            if change_sign != '=' and change_sign != 'NEW':
                                rank_text += f" {change_sign}{change_value}"
                            elif change_sign == 'NEW':
                                rank_text += f" {change_sign}"
                            else:
                                rank_text += f" {change_sign}"  # 변동 없음은 =

                    rank_text += ")"
                    display_title = f"{program_title_raw} {rank_text}"

                except Exception:
                    display_title = program_title_raw
        else:
            p_type = 'Cable/TV'
            c_name = raw_channel  # 채널명: CHING, MBC 드라마넷 등
            disp_time = row.get('broadcast_time', '')

        is_reserved = program_title_raw in reservations
        is_favorite = program_title_raw in favorites

        is_ended = False
        reservation_status_text = ""

        try:
            prog_dt = row.get('datetime', None)
            # OTT가 아니고 시간이 지났으면 종료 처리
            if not is_ott and prog_dt is not None and prog_dt < now:
                # 랭킹이 통합된 제목이더라도 종료 표시를 앞에 붙임
                display_title = f"🕒 [종료] {display_title}"
                is_ended = True
        except Exception:
            pass

        # 예약불가사유 텍스트 설정
        if is_ott:
            reservation_status_text = 'OTT'
        elif is_ended:
            reservation_status_text = '시간지남'

        reservation_value = program_title_raw in reservations

        # df_display에서 해당 행의 0-based index (현재 for loop의 카운터와 동일)
        current_display_list_index = len(display_list)

        # 현재 행이 상세보기 토글이 켜진 행인지 확인
        is_detail_open = (st.session_state.get("detail_view_row_index") == current_display_list_index)

        display_list.append({
            '플랫폼': p_type,
            '채널명': c_name,
            '상세보기': is_detail_open,
            '시간': disp_time,
            '제목': display_title,  # ✨ 랭킹 정보가 통합된 제목
            '장르': row.get('genre', ''),
            '출연진': row.get('cast', ''),
            '감독': row.get('director', ''),
            '⭐ 즐겨찾기': bool(is_favorite),
            '예약': bool(reservation_value),
            '예약 상태': reservation_status_text,

            # 숨겨진 데이터 (로직용) - 기존 유지
            'channel': raw_channel,
            'broadcast_date': row.get('broadcast_date', ''),
            'broadcast_time': row.get('broadcast_time', ''),
            'title': program_title_raw,  # 순수 제목 (로직용)
            '_full_time_hidden': row.get('full_time', ''),
            'platform_type': p_type,
            'channel_name': c_name,
            'datetime': row.get('datetime', None),
            'detail_title': program_title_raw,  # 순수 제목 (엑스팬더 제목용)
            'detail_poster': row.get('poster_url', ''),
            'detail_story': row.get('plot', ''),
            'detail_age': row.get('age_rating', ''),
            'detail_runtime': row.get('runtime', ''),
            'detail_rank': row.get('rank', ''),
            'detail_rank_change': row.get('rank_change', ''),
        })

    if not display_list:
        st.warning("⚠️ 검색 결과가 없습니다.")
        return

    df_display = pd.DataFrame(display_list)
    st.session_state['current_display_df'] = df_display.copy()

    if 'datetime' in df_display.columns and not df_display['datetime'].isnull().all():
        min_date = df_display['datetime'].min().strftime('%Y.%m.%d')
        max_date = df_display['datetime'].max().strftime('%Y.%m.%d')

        if min_date == max_date:
            date_range_str = f"({min_date})"
        else:
            date_range_str = f"({min_date} ~ {max_date})"

        # 2. subheader에 날짜 범위와 건수를 함께 표시
        st.subheader(f"📺 방영일정표 {date_range_str}")
    else:
        # datetime 정보가 없거나 필터링으로 인해 모두 사라진 경우
        st.subheader(f"📺 방영일정표")

    if search_query:
        st.markdown(f"💡 **'{search_query}'**(으)로 검색된 결과입니다.")

    # -------------------------------------------------------------
    # 컬럼 순서 및 헤더 설정 (기존 유지)
    # -------------------------------------------------------------
    visible_cols = [
        '플랫폼', '채널명', '상세보기', '시간', '제목',
        '⭐ 즐겨찾기', '예약',
        '예약 상태'
    ]

    column_config = {
        "플랫폼": st.column_config.TextColumn("구분", width="small"),
        "채널명": st.column_config.TextColumn("채널명", width="small"),
        "상세보기": st.column_config.CheckboxColumn(
            "상세보기",
            default=False,
            help="클릭하여 상세 정보를 확인합니다.",
            width="small"
        ),
        "시간": st.column_config.TextColumn("방영시간", width="small"),

        "제목": st.column_config.TextColumn("제목", width="medium"),
        "⭐ 즐겨찾기": st.column_config.CheckboxColumn("즐겨찾기", default=False),
        "예약": st.column_config.CheckboxColumn("알림 예약", default=False),
        "예약 상태": st.column_config.TextColumn("예약불가사유", width="small"),
    }

    st.data_editor(
        df_display[visible_cols],
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        key='schedule_editor',
        on_change=handle_editor_changes  # 💡 on_change에 모든 상태 변경 로직이 통합됨
    )

    # -------------------------------------------------------------
    # ❌ [삭제] 상세보기 토글 감지 및 화면 갱신 로직 삭제 (handle_editor_changes로 통합됨)
    # -------------------------------------------------------------

    # -------------------------------------------------------------
    # [수정] 상세정보 표시 (토글된 행의 정보 표시)
    # -------------------------------------------------------------
    if st.session_state.get("detail_view_row_index") is not None:
        idx = st.session_state["detail_view_row_index"]
        try:
            row = df_display.iloc[idx]
        except IndexError:
            st.session_state['detail_view_row_index'] = None
            st.rerun()
            return

        # 엑스팬더 제목은 순수 제목(detail_title)으로 유지
        with st.expander(f"🔍 상세보기 - {row['detail_title']}", expanded=True):

            # ✨ 서브헤더에 랭킹이 통합된 '제목' 컬럼 값을 사용
            st.subheader(row['제목'])

            colA, colB = st.columns([1, 3])
            with colA:
                # 포스터
                if row['detail_poster']:
                    st.image(row['detail_poster'], width=180)
                else:
                    st.write("포스터 없음")

            with colB:
                # 요청된 정보 표시 (detail_** 필드를 사용)
                st.write(f"**연령 등급:** {row['detail_age'] or '정보 없음'}")
                st.write(f"**회차/러닝타임:** {row['detail_runtime'] or '정보 없음'}")
                # 별도의 랭킹 및 랭킹 변화 표시는 제거됨
                st.write(f"**장르:** {row['장르']or '정보 없음'}")
                st.write(f"**출연:** {row['출연진'] or '정보 없음'}")
                st.write(f"**감독:** {row['감독'] or '정보 없음'}")

            st.markdown("---")
            st.markdown("### 📘 줄거리")
            st.write(row['detail_story'] or "줄거리 정보 없음")

    st.markdown("---")
    st.caption("💡 '예약불가사유'가 **OTT** 또는 **시간지남**인 항목은 예약(알림) 설정이 불가능합니다.")


# =================================================================
# 6. 예약/즐겨찾기 페이지 (수정 없음)
# =================================================================
def format_reservation_datetime_display(datetime_str):
    if not datetime_str or datetime_str.endswith('0000'):
        return "상시 방영", "정보 없음"
    try:
        dt_obj = datetime.strptime(datetime_str, '%y%m%d %H%M').replace(tzinfo=KST)
        date_display = dt_obj.strftime('%y.%m.%d')
        time_display = dt_obj.strftime('%H:%M')
        return time_display, date_display
    except ValueError:
        return "시간 정보 오류", "날짜 정보 오류"


def render_reservation_page(df_all, reservations):
    st.header("📅 예약된 프로그램 목록")
    if not reservations:
        st.info("현재 예약된 프로그램이 없습니다. 홈 화면에서 예약해주세요!")
        return

    df_reserved = df_all[df_all['title'].isin(reservations)].copy()
    if df_reserved.empty:
        st.info("예약된 프로그램은 있지만, 현재 데이터셋에 해당하는 방송 정보가 없습니다.")
        return

    df_reserved.sort_values(by=['title', 'datetime'], ascending=[True, True], inplace=True)
    grouped_by_title = df_reserved.groupby('title')

    for title, group in grouped_by_title:
        with st.expander(f"{title}", expanded=True):
            col_info, col_cancel = st.columns([5, 1])
            first_row = group.iloc[0]
            with col_info:
                st.markdown(f"**장르:** {first_row.get('genre', '정보 없음')}")
                st.markdown(f"**출연:** {first_row.get('cast', '정보 없음')}")
                st.markdown(f"**감독:** {first_row.get('director', '정보 없음')}")
                st.markdown("---")
                st.markdown("**📺 방영 채널 및 시간**")

                now = datetime.now(KST)
                for _, row in group.iterrows():
                    # platform_type 대신 row의 channel과 platform으로 OTT 판단
                    is_ott = str(row.get('platform', '')).upper() == 'OTT'
                    p_type = 'OTT' if is_ott else 'Cable/TV'
                    c_name = row.get('channel', '')
                    time_display, date_display = format_reservation_datetime_display(row.get('full_time', ''))

                    is_ended = False
                    if not is_ott and row.get('datetime') is not None and row.get('datetime') < now:
                        is_ended = True

                    status_icon = "🟢 (예정)"
                    if is_ended:
                        status_icon = "🔴 (종료)"
                    elif is_ott:
                        status_icon = "🟡 (상시)"

                    disp_text = f"{status_icon} **{p_type}** ({c_name}): {date_display} {time_display}"
                    st.markdown(disp_text)

            with col_cancel:
                st.write("")
                st.write("")
                if st.button("❌ 예약 취소", key=f"cancel_all_{title}"):
                    reservations.remove(title)
                    save_json_file(RESERVATION_FILE, reservations, is_set=True)
                    st.toast(f"'{title}' 프로그램의 모든 예약이 취소되었습니다!", icon='🗑️')
                    st.rerun()


def render_favorite_page(df_all, favorites):
    st.header("⭐ 나만의 즐겨찾기")
    if not favorites:
        st.info("즐겨찾기 목록이 비어있습니다. '⭐ 즐겨찾기'를 체크해보세요!")
        return

    fav_list = list(favorites)
    for title in fav_list:
        match_row = df_all[df_all['title'] == title].head(1)
        genre = "정보 없음"
        cast = "정보 없음"
        director = "정보 없음"

        if not match_row.empty:
            genre = match_row.iloc[0].get('genre', '정보 없음')
            cast = match_row.iloc[0].get('cast', '정보 없음')
            director = match_row.iloc[0].get('director', '정보 없음')

        # st.container에는 border 인자가 없을 수 있으므로 단순화
        with st.container():
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.subheader(title)
                st.text(f"장르: {genre}")
                st.text(f"출연진: {cast}")
                st.text(f"감독: {director}")
            with col_b:
                if st.button("삭제", key=f"del_fav_{title}"):
                    if title in favorites:
                        favorites.remove(title)
                        save_json_file(FAVORITE_FILE, favorites, is_set=True)
                        st.toast(f"'{title}'이(가) 즐겨찾기에서 제거되었습니다.", icon='👎')
                        st.rerun()


# =================================================================
# 7. 알림 설정 페이지 렌더링 함수 (API Key 입력 필드 제거 완료)
# =================================================================
def render_notification_setting_page(config):
    st.header("🔔 알림 설정")
    st.caption("프로그램 방영 알림을 받을 수단과 시점을 설정합니다.")
    st.markdown("---")

    current_minutes = config.get('notification_minutes', 5) if isinstance(config, dict) else 5
    st.subheader("1️⃣ 알림 시점 설정")
    new_minutes = st.select_slider(
        "프로그램 시작 몇 분 전에 알림을 받으시겠습니까?",
        options=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
                 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54,
                 55, 56, 57, 58, 59, 60],
        value=current_minutes,
        help="1분 전부터 60분 전까지 설정 가능합니다."
    )

    st.markdown("---")
    st.subheader("2️⃣ 알림 수단 선택 (중복 가능)")
    current_methods = config.get('notification_methods', ['telegram']) if isinstance(config, dict) else ['telegram']
    new_methods = st.multiselect(
        "어떤 수단으로 알림을 받으시겠습니까?",
        options=['telegram', 'email', 'web'],
        default=current_methods,
        format_func=lambda
            x: f"텔레그램 (Telegram)" if x == 'telegram' else f"이메일 (Email)" if x == 'email' else f"웹 알림 (Streamlit Toast)"
    )

    st.markdown("---")
    st.subheader("3️⃣ 수신자 개인정보 입력")
    st.caption("텔레그램/이메일 알림을 받으려면 정보를 정확히 입력해야 합니다.")
    st.caption("**💡 OpenAI API Key는 `config.json` 파일을 직접 수정하여 설정해주세요.**")

    current_contact_info = config.get('contact_info', {'telegram': '', 'email': ''}) if isinstance(config, dict) else {
        'telegram': '', 'email': ''}

    new_telegram_chat_id = st.text_input(
        "💬 텔레그램 Chat ID",
        value=current_contact_info.get('telegram', ''),
        help="텔레그램 봇에게 /start 명령을 보내면 봇이 알려주는 Chat ID를 입력하세요."
    )

    new_email_address = st.text_input(
        "📧 이메일 주소",
        value=current_contact_info.get('email', ''),
        help="알림을 수신할 이메일 주소를 입력하세요."
    )

    st.markdown("---")
    if st.button("✅ 설정 저장"):
        if not new_methods:
            st.error("알림 수단을 1개 이상 선택해야 합니다.")
        else:
            if 'telegram' in new_methods and not new_telegram_chat_id.strip():
                st.error("텔레그램 알림을 선택했으므로, Chat ID를 입력해야 합니다.")
                return
            if 'email' in new_methods and ('@' not in new_email_address or '.' not in new_email_address):
                st.error("이메일 알림을 선택했으므로, 유효한 이메일 주소를 입력해야 합니다.")
                return

            config['notification_methods'] = new_methods
            config['notification_minutes'] = new_minutes
            # config['openai_api_key']는 변경하지 않음 (개발자 관리)
            config['contact_info'] = {
                'telegram': new_telegram_chat_id.strip(),
                'email': new_email_address.strip()
            }

            save_json_file(CONFIG_FILE, config)
            st.success("🎉 알림 설정 및 연락처 정보가 성공적으로 저장되었습니다!")
            st.rerun()
# ================================================================
# 🔍 상세 페이지 렌더링 함수 (URL 쿼리 기반 상세 페이지, 수정 없음)
# ================================================================
def render_detail_page(df, title):
    st.title(f"🔍 상세 정보 - {title}")

    # 데이터 찾기
    row = df[df['title'] == title].head(1)
    if row.empty:
        st.error("해당 프로그램을 찾을 수 없습니다.")
        return

    row = row.iloc[0]

    # 기본 정보 가져오기
    # 합본 파일의 컬럼명에 맞게 수정
    poster = row.get("poster_url", "")
    story = row.get("plot", "줄거리 정보 없음")
    age = row.get("age_rating", "정보 없음")
    runtime = row.get("runtime", "정보 없음")
    rank = row.get("rank", "정보 없음")
    change = row.get("rank_change", "정보 없음")
    cast = row.get("cast", "정보 없음")
    director = row.get("director", "정보 없음")

    # 레이아웃 구성
    col1, col2 = st.columns([1, 3])

    with col1:
        if poster:
            st.image(poster, width=250)
        else:
            st.write("포스터 없음")

    with col2:
        st.subheader(title)
        st.write(f"**연령 등급:** {age}")
        st.write(f"**회차/러닝타임:** {runtime}")
        # 랭킹 정보는 OTT에만 있으므로, 있을 경우에만 표시
        if rank:
            st.write(f"**랭킹:** {rank}")
        if change:
            st.write(f"**랭킹 변화:** {change}")

        st.write(f"**출연:** {cast}")
        st.write(f"**감독:** {director}")

    st.markdown("---")
    st.subheader("📘 줄거리")
    st.write(story)


# =================================================================
# 7. 메인 실행부 (수정 없음)
# =================================================================
def clean_expired_reservations(df, reservations):
    # 간단한 정리 로직 (OTT는 유지)
    return False


def post_rerun_toast():
    if 'toast_list' in st.session_state and st.session_state.get('toast_list'):
        for message, icon in st.session_state.get('toast_list', []):
            st.toast(message, icon=icon)
        st.session_state['toast_list'] = []


# ================================================================
# 8. 챗봇 페이지 렌더링 함수 (오류 수정 및 API 키 안내 수정 완료)
# ================================================================
# 💡 OpenAI 라이브러리 임포트는 파일 최상단에서 한 번만 합니다.
from openai import OpenAI


def render_chatbot_page(config):
    st.header("💬 프로그램 사용 안내 챗봇")

    # --- 1) API 키 불러오기 ---
    api_key = config.get("openai_api_key", "").strip()
    if not api_key:
        # 키가 없을 경우 안내 문구 수정
        st.error("❌ OpenAI API 키가 설정되지 않았습니다. [config.json] 파일을 직접 수정하여 API 키를 입력해주세요.")
        return

    # API 키가 있으면 클라이언트 초기화
    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(f"❌ OpenAI 클라이언트 초기화 오류: {e}")
        return

    # --- 2) 설명문서를 불러오기 ---
    guide_text = ""
    guide_file = "chatbot_guide.txt"
    try:
        with open(guide_file, "r", encoding="utf-8") as f:
            guide_text = f.read()
    except FileNotFoundError:
        st.warning(f"⚠️ '{guide_file}' 파일을 찾을 수 없습니다. 설명문서 파일을 프로젝트 폴더에 생성해주세요.")
        guide_text = "이 앱은 TV/OTT 드라마/영화 방영 정보를 제공하며, 예약(알림), 즐겨찾기, 상세 검색 기능을 지원합니다."

    # --- 3) System Prompt 구성 ---
    system_prompt = f"""
    당신은 사용자가 이 웹앱을 사용하는 방법을 안내하는 도움말 챗봇입니다.
    아래 문서의 내용만 기반으로 답변해야 하며, 문서에 없는 내용은 추측하지 말고 
    '해당 내용은 제공된 설명문서에 없습니다.' 라고 답해야 합니다. 
    답변은 항상 친절하고 명확하게 한국어로 작성해야 합니다.

    --- [설명문서 시작] ---
    {guide_text}
    --- [설명문서 끝] ---
    """

    # --- 4) 세션 메시지 초기화 ---
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
        st.session_state.chat_messages.append(
            {"role": "assistant", "content": "안녕하세요! 챗봇입니다. 이 프로그램 사용법 중 궁금한 점을 질문해주세요. 제가 아는 범위 내에서 자세히 안내해드리겠습니다."})

    # --- 5) 기존 대화 표시 ---
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- 6) 사용자 입력 및 GPT 요청 ---
    user_input = st.chat_input("무엇이 궁금하신가요?")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state.chat_messages.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            with st.spinner("생각중..."):
                try:
                    messages = [{"role": "system", "content": system_prompt}] + st.session_state.chat_messages

                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages
                    )

                    # 💡 오류 수정 지점: .content 속성으로 접근
                    bot_reply = response.choices[0].message.content

                    st.markdown(bot_reply)

                    st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
                except Exception as e:
                    # 상세한 오류 메시지 대신 사용자에게 친절한 메시지 제공
                    st.error("API 통신 중 오류가 발생했습니다. (OpenAI 키, 네트워크 상태 등을 확인해주세요.)")
                    print(f"DEBUG: GPT API Error: {e}")  # 디버깅용 메시지 출력
                    st.session_state.chat_messages.pop()  # 오류 질문 제거

def main():
    st.set_page_config(layout="wide", page_title="드라마&영화 알리미")
    st.title("🎬 드라마&영화 방영 일정표")
    post_rerun_toast()

    df = load_data()
    if df.empty:
        st.error(f"❌ '{DATA_FILE}' 파일이 없습니다. 파일을 확인하거나 합본 생성 코드를 실행해주세요.")
        return

    reservations = load_json_file(RESERVATION_FILE, is_set=True)
    favorites = load_json_file(FAVORITE_FILE, is_set=True)
    config = load_json_file(CONFIG_FILE)

    if 'detail_view_row_index' not in st.session_state:
        st.session_state['detail_view_row_index'] = None

    check_and_send_notifications_set_compat(df, reservations, config)

    params = st.query_params
    detail_title = params.get("detail", None)

    if detail_title:
        render_detail_page(df, detail_title)
        return

    # ------------------------------------------
    #  🔥 여기부터가 반드시 왼쪽(Margin 0)에 있어야 함!!
    # ------------------------------------------
    with st.sidebar:
        st.header("메뉴")
        menu = st.radio(
            "이동",
            ["🏠 홈 화면", "📅 예약 확인", "⭐ 즐겨찾기", "⚙️ 알림 설정", "💬 챗봇 안내"]
        )
        st.divider()
        st.caption(f"예약: {len(reservations)}개 | 즐겨찾기: {len(favorites)}개")

    if menu == "🏠 홈 화면":
        render_home_screen(df, reservations, favorites)
    elif menu == "📅 예약 확인":
        render_reservation_page(df, reservations)
    elif menu == "⭐ 즐겨찾기":
        render_favorite_page(df, favorites)
    elif menu == "⚙️ 알림 설정":
        render_notification_setting_page(config)
    elif menu == "💬 챗봇 안내":
        render_chatbot_page(config)

if __name__ == "__main__":
    main()