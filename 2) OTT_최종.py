# ott_crawling_fast_stable.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, StaleElementReferenceException
)
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd
import re

# ===================================================================
# 1. OTT 랭킹 URL 목록
# ===================================================================
OTT_URLS = {
    "Netflix": "https://m.kinolights.com/ranking/netflix",
    "TVING": "https://m.kinolights.com/ranking/tving",
    "Coupang Play": "https://m.kinolights.com/ranking/coupang",
    "Wavve": "https://m.kinolights.com/ranking/wavve",
    "Disney+": "https://m.kinolights.com/ranking/disney",
    "Watcha": "https://m.kinolights.com/ranking/watcha",
    "BoxOffice": "https://m.kinolights.com/ranking/boxoffice"
}

# ===================================================================
# 2. 제목 정규화 함수
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
# 3. 키노라이츠 상세 정보 가져오기
# ===================================================================
def fetch_kinolights_info(driver, title: str, wait_time=10):
    info = {
        "synopsis": "",
        "genre": "",
        "cast": "",
        "director": "",
        "age_rating": "",
        "running_time": "",
        "poster_image": ""
    }
    try:
        wait = WebDriverWait(driver, wait_time)

        # 1. 검색 페이지 이동
        driver.get("https://m.kinolights.com/search")
        search_input = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input.search-form__input")
        ))
        search_input.clear()
        search_input.send_keys(title)
        search_input.send_keys(Keys.RETURN)
        time.sleep(1.0)

        # 2. 첫 번째 결과 클릭
        try:
            first_result = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.content__body")
            ))
            first_result.click()
        except TimeoutException:
            return info  # 검색 결과 없으면 빈 정보 반환

        time.sleep(2)  # 상세 페이지 로딩 대기

        # 3. 상세 정보 추출
        # 줄거리
        # 줄거리
        try:
            # 더보기 버튼 클릭 시도
            try:
                more_btn = driver.find_element(By.CSS_SELECTOR, "button.more")
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(0.5)  # 펼쳐지는 시간 잠깐 대기
            except:
                pass  # 더보기 버튼이 없으면 그냥 넘어감

            synopsis = driver.find_element(By.CSS_SELECTOR, "div.synopsis .text")
            info["synopsis"] = synopsis.text.strip()
        except NoSuchElementException:
            info["synopsis"] = ""

        # 장르
        try:
            genre_xpath = "//span[contains(text(),'장르')]/following-sibling::span"
            genre_el = driver.find_element(By.XPATH, genre_xpath)
            info["genre"] = genre_el.text.strip().replace("/", ", ")
        except NoSuchElementException:
            info["genre"] = ""

        # 출연진
        try:
            cast_elements = driver.find_elements(By.CSS_SELECTOR, "div.person div.names div.name")
            info["cast"] = ", ".join([c.text.strip() for c in cast_elements if c.text.strip()])
        except:
            info["cast"] = ""

        # 감독
        try:
            director = ""
            staff_sections = driver.find_elements(By.CSS_SELECTOR, "div.staff")
            for sec in staff_sections:
                try:
                    title_text = sec.find_element(By.CSS_SELECTOR, "span.staff__title").text
                    if "감독" in title_text or "연출" in title_text:
                        director = sec.find_element(By.CSS_SELECTOR, "a.names__name span").text.strip()
                        break
                except:
                    continue
            info["director"] = director
        except:
            info["director"] = ""

        # 연령 등급
        try:
            age_xpath = "//span[contains(text(),'연령등급')]/following-sibling::span"
            age_el = driver.find_element(By.XPATH, age_xpath)
            info["age_rating"] = age_el.text.strip()
        except:
            info["age_rating"] = ""

        # 러닝타임 / 회차
        try:
            rt_xpath = "//span[contains(text(),'회차')]/following-sibling::span"
            rt_el = driver.find_element(By.XPATH, rt_xpath)
            info["running_time"] = rt_el.text.strip()
        except:
            try:
                runtime_xpath = "//span[contains(text(),'러닝타임')]/following-sibling::span"
                runtime_el = driver.find_element(By.XPATH, runtime_xpath)
                info["running_time"] = runtime_el.text.strip()
            except:
                info["running_time"] = ""

        # 포스터
        try:
            poster_el = driver.find_element(By.CSS_SELECTOR, ".poster img.image-container__image")
            info["poster_image"] = poster_el.get_attribute("src")
        except:
            info["poster_image"] = ""

    except Exception as e:
        print(f"fetch_kinolights_info 예외: {e}")

    return info

# ===================================================================
# 4. OTT 랭킹 목록 크롤링
# ===================================================================
def crawl_ott(platform, url):
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1200,900")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(url)
        time.sleep(2)

        # 랭킹 아이템
        try:
            items = driver.find_elements(By.CSS_SELECTOR, "ul.content-ranking-list > li")
        except:
            items = []

        data = []
        for idx, item in enumerate(items, 1):
            try:
                # rank
                try:
                    rank = item.find_element(By.CSS_SELECTOR, ".rank__number span").text.strip()
                except:
                    rank = ""

                # rank change
                try:
                    change_el = item.find_element(By.CSS_SELECTOR, ".rank__change span")
                    change_val = change_el.text.strip()

                    classes = change_el.get_attribute("class")

                    if "change--up" in classes:
                        rank_change = f"+{change_val}"
                    elif "change--down" in classes:
                        rank_change = f"-{change_val}"
                    elif "change--same" in classes:
                        rank_change = "0"
                    elif "change--new" in classes:
                        rank_change = "NEW"
                    else:
                        rank_change = change_val

                except:
                    rank_change = ""

                # title
                try:
                    title = item.find_element(By.CSS_SELECTOR, "h5.info__title").text.strip()
                except:
                    try:
                        title = item.find_element(By.CSS_SELECTOR, ".title").text.strip()
                    except:
                        title = ""
                if not title:
                    continue
                # poster
                try:
                    poster_el = item.find_element(By.CSS_SELECTOR, "img")
                    poster_image = poster_el.get_attribute("src")
                except:
                    poster_image = ""

                # 검색용 title
                search_title = clean_title(title)

                # 상세 정보 새 탭에서 크롤링
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[1])
                detail_info = fetch_kinolights_info(driver, search_title)
                driver.close()
                driver.switch_to.window(driver.window_handles[0])

                row = {
                    "platform": platform,
                    "rank": rank,
                    "rank_change": rank_change,
                    "title": title,
                    "poster_image": poster_image or detail_info["poster_image"],
                    "genre": detail_info["genre"],
                    "cast": detail_info["cast"],
                    "director": detail_info["director"],
                    "synopsis": detail_info["synopsis"],
                    "age_rating": detail_info["age_rating"],
                    "running_time": detail_info["running_time"]
                }
                data.append(row)
                print(f"[{idx}/{len(items)}] {title} 처리 완료")
            except StaleElementReferenceException:
                continue
            except Exception as e:
                print(f"아이템 처리 중 예외: {e}")
                continue
        return data
    finally:
        driver.quit()

# ===================================================================
# 5. 메인
# ===================================================================
if __name__ == "__main__":
    all_data = []
    for platform, url in OTT_URLS.items():
        result = crawl_ott(platform, url)
        all_data.extend(result)

    if all_data:
        df = pd.DataFrame(all_data)
        out_file = "ott_crawling.csv"
        df.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"\n🎉 OTT 크롤링 완료! 총 {len(df)}건 저장됨. 파일명: {out_file}")
    else:
        print("⚠️ OTT 크롤링 결과 없음")
