from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.webelement import WebElement

import pandas as pd
import time
import re

# ===================================================================
# 1. 기본 URL 및 타겟 채널 설정
# ===================================================================
BASE_URL = "http://211.43.210.44/tvguide/index.php?main=cable&sub=cable0"
TARGET_CHANNELS = {
    "MBC 드라마넷": "253",
    "KBS 드라마": "148",
    "CHING": "780",
    "CNTV": "355",
    "DRAMAcube": "499"
}

today_date_info = "날짜 정보 없음"
all_data = []
driver = None


# ===================================================================
# 2. 제목 정규화 함수 (생략: 변경 없음)
# ===================================================================
def clean_title(title: str) -> str:
    if not title:
        return ""
    title = re.sub(r'<.*?>', '', title)
    title = re.sub(r'\s*\[.*?\]', '', title)
    title = re.sub(r'\([^\)]+\)', '', title)
    title = re.sub(r'\b(?:EP|Ep|ep|E)\s*\.?\s*\d+\b', '', title)
    title = re.sub(r'\b\d+\s*기\b', '', title)
    title = re.sub(r'\b\d+\s*(회|화|부|편)\b', '', title)
    title = re.sub(r'\s*\d+$', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


# ===================================================================
# 3. 키노라이츠 상세 정보 보강 함수 (줄거리 및 추가 정보 크롤링)
# ===================================================================
def fetch_kinolights_info(title: str):
    kinolights_driver = None
    info = {
        'plot': '',
        'genre': '',
        'cast': '',
        'director': '',
        'age_rating': '정보 없음',  # 1. 연령층 (완성)
        'poster_url': '포스터 URL 없음',  # 2. 포스터 (완성)
        'runtime_or_episode': '정보 없음'  # 3. 러닝타임/회차 (완성)
    }

    try:
        kinolights_driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        kinolights_driver.get("https://m.kinolights.com/search")
        wait = WebDriverWait(kinolights_driver, 10)

        # 1. 검색어 입력 및 검색
        search_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.search-form__input"))
        )
        search_input.clear()
        search_input.send_keys(title)
        search_input.send_keys(webdriver.common.keys.Keys.RETURN)

        time.sleep(1)

        # 2. 첫 번째 검색 결과 클릭 (상세 페이지로 이동)
        first_result = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.content__body"))
        )
        first_result.click()

        time.sleep(2)  # 상세 페이지 로딩 대기

        # ----------------------------------------------------
        # ✨ 1. '연령층' 가져오기 (Age Rating) - 사용자 HTML 기반 XPath
        # ----------------------------------------------------
        try:
            # item__title이 '연령등급'인 항목의 item__body를 찾습니다.
            # 예: //span[@class='item__title' and text()='연령등급']/following-sibling::span[@class='item__body']
            age_rating_xpath = "//span[@class='item__title' and text()='연령등급']/following-sibling::span"
            age_rating_el = kinolights_driver.find_element(By.XPATH, age_rating_xpath)
            info['age_rating'] = age_rating_el.text.strip()
        except NoSuchElementException:
            pass  # '정보 없음' 유지

        # ----------------------------------------------------
        # ✨ 3. '러닝타임' 혹은 '회차' 가져오기 - 사용자 HTML 기반 XPath
        # ----------------------------------------------------
        try:
            # 1. '회차' 정보 먼저 시도 (TV 드라마/시리즈)
            episode_xpath = "//span[@class='item__title' and text()='회차']/following-sibling::span"
            episode_el = kinolights_driver.find_element(By.XPATH, episode_xpath)
            info['runtime_or_episode'] = episode_el.text.strip()

        except NoSuchElementException:
            # 2. '회차'가 없으면 '러닝타임' 정보 시도 (영화/단편)
            try:
                runtime_xpath = "//span[@class='item__title' and text()='러닝타임']/following-sibling::span"
                runtime_el = kinolights_driver.find_element(By.XPATH, runtime_xpath)
                info['runtime_or_episode'] = runtime_el.text.strip()
            except NoSuchElementException:
                pass  # '정보 없음' 유지
        # ----------------------------------------------------

        # ----------------------------------------------------
        # ✨ 2. '포스터' 이미지 가져오기 (Poster URL) - 기존 확정 로직
        # ----------------------------------------------------
        try:
            poster_element = kinolights_driver.find_element(By.CSS_SELECTOR, ".poster img.image-container__image")
            info['poster_url'] = poster_element.get_attribute("src")
        except NoSuchElementException:
            pass
        # ----------------------------------------------------

        # ----------------------------------------------------
        # 기존 줄거리, 장르, 출연진, 감독 로직 (유지)
        # ----------------------------------------------------

        # 줄거리 (Plot)
        try:
            # 기본 줄거리 가져오기
            synopsis_el = kinolights_driver.find_element(By.CSS_SELECTOR, "div.synopsis .text")
            info["plot"] = synopsis_el.text.strip()

            # "더보기" 버튼이 있으면 클릭 후 전체 줄거리 가져오기
            try:
                more_button = kinolights_driver.find_element(By.CSS_SELECTOR, "button.more")
                if more_button.is_displayed():
                    more_button.click()
                    time.sleep(0.5)  # 클릭 후 로딩 대기
                    # 클릭 후 전체 줄거리 다시 가져오기
                    full_synopsis_el = kinolights_driver.find_element(By.CSS_SELECTOR, "div.synopsis .text")
                    info["plot"] = full_synopsis_el.text.strip()
            except NoSuchElementException:
                pass  # 더보기 버튼 없으면 그냥 기본 줄거리 유지

        except Exception:
            info["plot"] = ""

        # 장르
        try:
            genre_el = wait.until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//span[contains(text(), '장르')]/following-sibling::span"
                ))
            )
            info['genre'] = genre_el.text.strip().replace("/", ", ")
        except:
            info['genre'] = ""

        # 출연진
        try:
            actors = kinolights_driver.find_elements(By.CSS_SELECTOR, "div.person.list__avatar div.names div.name")
            info['cast'] = ", ".join([a.text.strip() for a in actors if a.text.strip()])
        except:
            info['cast'] = ""

        # 감독
        try:
            director = ""
            staff_sections = kinolights_driver.find_elements(By.CSS_SELECTOR, "div.staff")
            for sec in staff_sections:
                try:
                    t = sec.find_element(By.CSS_SELECTOR, "span.staff__title").text
                    if "감독" in t or "연출" in t:
                        director = sec.find_element(By.CSS_SELECTOR, "a.names__name span").text.strip()
                        break
                except:
                    pass
            info['director'] = director
        except:
            info['director'] = ""

        return info

    except Exception as e:
        # 검색 실패 등의 큰 오류 발생 시
        # print(f"키노라이츠 정보 추출 오류: {e}")
        return info

    finally:
        if kinolights_driver:
            kinolights_driver.quit()
# ===================================================================
# 4. TV 편성표 크롤링 (생략: 변경 없음)
# ===================================================================
def crawl_single_channel(channel_name, channel_code):
    global today_date_info
    channel_data = []
    TARGET_URL = f"{BASE_URL}&c={channel_code}"

    print(f"\n📡 {channel_name} 크롤링 시도: {TARGET_URL}")

    try:
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 15)

        # '오늘' 날짜 열 찾기 (생략)
        header_tr_xpath = "//table[@id='main_channel']/tbody/tr[1]"
        header_row = wait.until(EC.presence_of_element_located((By.XPATH, header_tr_xpath)))
        date_cols = header_row.find_elements(By.TAG_NAME, "td")

        target_col_index = -1
        for i, col in enumerate(date_cols):
            if i == 0:
                continue
            try:
                col.find_element(By.XPATH, ".//img[contains(@src, 'today.jpg')]")
                target_col_index = i
                if today_date_info == "날짜 정보 없음":
                    date_text = col.text.strip().split('\n')[0].replace('오늘', '').strip()
                    if date_text:
                        today_date_info = date_text
                break
            except NoSuchElementException:
                continue

        wait.until(EC.presence_of_element_located((By.ID, "result_tbl")))

        # 시간대별 프로그램 추출 (생략)
        for row_index in range(1, 25):
            try:
                time_td_xpath = f"//table[@id='result_tbl']/tbody/tr[{row_index}]/td[1]"
                time_td = wait.until(EC.presence_of_element_located((By.XPATH, time_td_xpath)))

                hour_match = re.search(r'^\d+', time_td.text.strip())
                if not hour_match:
                    continue
                hour = hour_match.group(0).zfill(2)

                cell_xpath = f"//table[@id='result_tbl']/tbody/tr[{row_index}]/td[{target_col_index + 1}]"
                cell = wait.until(EC.presence_of_element_located((By.XPATH, cell_xpath)))

                program_rows = cell.find_elements(By.XPATH, ".//table//tr")
                for pr in program_rows:
                    tds = pr.find_elements(By.TAG_NAME, "td")
                    if len(tds) < 2:
                        continue

                    minute = tds[0].text.strip().zfill(2)
                    title = tds[1].text.strip()

                    if minute and title and title not in ("프로그램 정보가 없습니다.", "광고", ""):
                        channel_data.append({
                            "channel": channel_name,
                            "broadcast_date": today_date_info,
                            "broadcast_time": f"{hour}:{minute}",
                            "title": title,
                            "plot": "",
                            "genre": "",
                            "cast": "",
                            "director": ""
                        })
            except:
                continue

        print(f"✅ {channel_name} {len(channel_data)}개 프로그램 추출 완료.")
        return channel_data

    except Exception as e:
        print(f"❌ {channel_name} 크롤링 오류: {e}")
        return []


# ===================================================================
# 5. 전체 데이터 보강 (새 컬럼 추가)
# ===================================================================
def enrich_data(df: pd.DataFrame) -> pd.DataFrame:
    df['search_title'] = df['title'].apply(clean_title)
    unique_titles = df['search_title'].unique()
    results_map = {}

    print(f"\n🚀 총 {len(unique_titles)}개의 고유 프로그램 상세 정보 보강 시작")

    for i, title in enumerate(unique_titles):
        if not title:
            continue

        info = fetch_kinolights_info(title)
        results_map[title] = info

        print(f"[{i + 1}/{len(unique_titles)}] '{title}' 처리 완료")
        time.sleep(1)

    # 새로 추가된 키 포함: poster_url, age_rating, runtime_or_episode
    for key in ['plot', 'genre', 'cast', 'director', 'poster_url', 'age_rating', 'runtime_or_episode']:
        df[key] = df['search_title'].apply(lambda x: results_map.get(x, {}).get(key, ""))
    df.drop(columns=['search_title'], inplace=True)
    return df

# 포스터 추출
def extract_poster_url_from_html(driver: webdriver.Chrome) -> str:
    """
    Kinolights 상세 페이지에서 포스터 이미지 URL을 추출합니다.
    (사용자님 제공 HTML 기반)
    """
    poster_url = "포스터 URL 없음"
    try:
        # 1. 포스터를 담고 있는 가장 바깥쪽 class="poster" 내부에서
        # 2. 실제 이미지 URL을 가진 img 태그를 찾습니다.
        #    가장 명확한 CSS 선택자는 .poster 클래스 내부의 img 태그입니다.
        poster_element = driver.find_element(By.CSS_SELECTOR, ".poster img.image-container__image")

        # 이미지 태그의 'src' 속성(URL)을 가져옵니다.
        poster_url = poster_element.get_attribute("src")

    except NoSuchElementException:
        print("  -> 포스터 이미지 요소를 찾을 수 없습니다.")

    return poster_url

# ===================================================================
# 6. 메인 실행부 (생략: 변경 없음)
# ===================================================================
if __name__ == "__main__":
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

        for name, code in TARGET_CHANNELS.items():
            result = crawl_single_channel(name, code)
            all_data.extend(result)
            time.sleep(1.5)

    finally:
        if driver:
            driver.quit()

    if all_data:
        df = pd.DataFrame(all_data)
        df.sort_values(by=['channel', 'broadcast_time'], inplace=True)

        df = enrich_data(df)

        df.to_csv('tv_crawling.csv', index=False, encoding='utf-8-sig')
        print(f"\n🎉 'tv_crawling.csv' 저장 완료 ({len(df)}건)")
    else:
        print("⚠️ 크롤링 결과가 없습니다.")