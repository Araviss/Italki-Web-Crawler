import time
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common import StaleElementReferenceException
from selenium.webdriver import ActionChains, Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient
import pandas as pd
from undetected_chromedriver import ChromeOptions


class ItalkiScraper:

    def __init__(self):
        self.df = None
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=options)

    def run(self):
        self.driver.get('https://www.italki.com/en/teachers/english')
        self.create_data_frame()
        self.press_lang_menu()
        self.language_selector()
        self.driver.quit()

    def create_data_frame(self):
        columns = ['Rating', '# of Students', '# of Lessons', 'Attendance', 'Price', 'About Me', 'As a Teacher',
                   'Teaching Style']
        self.df = pd.DataFrame(columns=columns)

    #Sometimes page doesn't load correctly and needs to be refreshed
    def refresh_page(self):
        self.driver.refresh()

    def press_lang_menu(self):
        try:
            language_button = self.wait_for_element(By.XPATH, '//*[@id="new-filter-bar"]/div[1]/div[1]')
            language_button.click()
            time.sleep(10)
        except:
            self.refresh_page()
            self.perform_teacher_search()
            self.press_lang_menu()


    def wait_for_element(self, by, selector, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def update_teacher_info(self, rating, num_of_students, num_of_lessons, attendance, price,
                  about_descr, teacher_descr, style_descr, languages):
        new_row = {
            'Rating': rating,
            '# of Students': num_of_students,
            '# of Lessons': num_of_lessons,
            'Attendance': attendance[:len(attendance) - 1],
            'Price': price[0] if price else None,
            'About Me': about_descr,
            'As a Teacher': teacher_descr,
            'Teaching Style': style_descr,
            'Language': languages
        }
        self.df = self.df.append(new_row, ignore_index=True)


    def match_country(self, text):
        pattern = r'^From'
        return re.sub(pattern, '', text)

    def print_teacher_info(self):
        time.sleep(10)
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        teacher_type = self.extract_teacher_type(soup)
        language_taught = self.extract_language_taught(soup)
        country = self.extract_country(soup)
        descriptions = self.extract_descriptions(soup)
        teacher_stat_elems = self.extract_teacher_stat_elems(soup)
        rating = self.driver.find_element(By.CSS_SELECTOR, 'div.text-warning').text
        num_of_students, num_of_lessons, attendance = self.extract_teacher_stats(teacher_stat_elems)
        price_match = self.extract_price()

        self.update_teacher_info(rating, num_of_students, num_of_lessons, attendance, price_match,
                                 descriptions[0].text, descriptions[1].text, descriptions[2].text, language_taught)
        self.insert_records_to_mongodb()

    def extract_teacher_type(self, soup):
        return soup.find_all('div', class_='md:mb-4 flex flex-row items-center tiny-caption text-gray3 uppercase')

    def extract_language_taught(self, soup):
        language_taught_parent = soup.find('div', class_='flex regular-body flex-wrap space-y-1 md:space-y-0')
        language_taught_html = language_taught_parent.find_all('span', class_='small-secondary text-gray1')
        return [language.text for language in language_taught_html]

    def extract_country(self, soup):
        country_parent = soup.find('div', class_='flex flex-col tiny-caption text-gray2').findChildren()[0].text
        return self.match_country(country_parent)

    def extract_descriptions(self, soup):
        return soup.find_all('span', class_='block mt-3 small-secondary text-gray2 break-words whitespace-pre-wrap')

    def extract_teacher_stat_elems(self, soup):
        return soup.find_all('div', class_='mb-2 flex flex-row items-center h4 text-title')

    def extract_teacher_stats(self, teacher_stat_elems):
        num_of_students = teacher_stat_elems[1].text
        num_of_lessons = teacher_stat_elems[2].text
        attendance = teacher_stat_elems[3].text
        return num_of_students, num_of_lessons, attendance

    def extract_price(self):
        price = self.driver.find_element(By.XPATH, '//*[@id="lessons"]/div[2]/div[1]/div[1]/div/div[2]/div').text
        return re.findall(r'\d+\.\d+', price)

    def prepare_page(self):
        self.driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(5)
        self.exclude_instant_book_banner()

    def exclude_instant_book_banner(self):
        try:
            elements_to_exclude = self.driver.find_element(By.CSS_SELECTOR, 'div.relative.py-4.bg-transparent.rounded-1')
            self.driver.execute_script("arguments[0].remove()", elements_to_exclude)
        except Exception as e:
            print(e)



    def open_teacher_tabs(self):
        #Scrolls to the top so that driver focus frame
        self.prepare_page()
        try:
            teacher_object_collection = self.driver.find_element(By.XPATH, '//*[@id="teacher-search-list"]/div[3]/div[1]')
            teacher_list = teacher_object_collection.find_elements(By.TAG_NAME, 'a')
            teacher_list = teacher_list[:-5]
        except:
            self.refresh_page()
            time.sleep(4)

        try:
            for i in range(len(teacher_list) - 3,len(teacher_list) - 1):
                self.open_teacher_tab( teacher_list[i])
        except:
            return


    def open_teacher_tab(self, teacher_element):
        action_chains = ActionChains(self.driver)
        action_chains.key_down(Keys.CONTROL).click(teacher_element).key_up(Keys.CONTROL).perform()
        self.driver.switch_to.window(self.driver.window_handles[-1])  # Switch to the newly opened tab/window
        try:
            self.print_teacher_info()
        except Exception as e:
            print(e)
        finally:
            self.close_and_switch_tab()

    def close_and_switch_tab(self):
        self.driver.close()  # Close the tab/window
        self.driver.switch_to.window(self.driver.window_handles[0])

    def scroll_to_top(self):
        self.driver.execute_script("window.scrollTo(0, 0)")

    def has_results(self):
        return len(self.driver.find_elements(By.CSS_SELECTOR, '.flex-1.flex.flex-col')) > 0

    def click_show_more_button(self):
        show_more_button = WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.ant-btn.w-50.ant-btn-white"))
        )
        show_more_button.click()

    def get_page_link(self):
        return self.driver.find_element(By.CSS_SELECTOR, 'a.ant-btn.w-50.ant-btn-white').get_attribute('href')

    def is_last_page(self, page_link):
        return page_link[-2:] == "10"

    def perform_teacher_search(self):
        self.scroll_to_top()
        while True:
            if not self.has_results():
                break

            try:
                self.click_show_more_button()
                page_link = self.get_page_link()
                if self.is_last_page(page_link):
                    break
            except:
                self.open_teacher_tabs()
                break

            time.sleep(5)

    def find_language_list(self):
        wait = WebDriverWait(self.driver, 10)
        return wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, 'ul.ant-menu.ant-menu-light.ant-menu-root.ant-menu-vertical')))

    #Remove curated list of languages
    #otherwise we'll be doubling languages
    def remove_popular_languages(self,language_list):
        language_list.pop(0)

    def get_children_count(self,parent_element):
        return len(parent_element.find_elements(By.TAG_NAME, 'li'))

    def iterate_language_list(self,language_list):

        for i in range(len(language_list)):

            children = language_list[i].find_elements(By.TAG_NAME, 'li')
            self.iterate_children(children,i)

    def iterate_children(self, children, i):

        for j in range(len(children)):
            try:
                children[j].click()
                self.perform_teacher_search()
                self.press_lang_menu()
                print("this is 'I': ", i)
                print("this is 'J': ", j)

            except StaleElementReferenceException:
                print("StaleElementReferenceException occurred. Refreshing the page and trying again.")
                self.refresh_page()
                time.sleep(5)
                children = self.driver.find_elements(By.TAG_NAME, 'li')


    def insert_records_to_mongodb(self):
        if not self.df.empty:
            records = self.df.to_dict(orient='records')
            client = MongoClient('mongodb://localhost:27017')
            db = client['Italki']
            collection = db['teacher_info']
            with pd.option_context('display.max_rows', None, 'display.max_columns', None):
                print(self.df)
            collection.insert_many(records)
            self.df.drop(self.df.index, inplace=True)

    def language_selector(self):
        language_list = self.find_language_list()
        self.remove_popular_languages(language_list)
        self.iterate_language_list(language_list)




if __name__ == "__main__":
    scraper = ItalkiScraper()
    scraper.run()
