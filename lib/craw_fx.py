import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import urllib.request
from selenium.webdriver.common.keys import Keys

# 🔹 Hardcoded Prompt
HARDCODED_PROMPT = "flying cars"

# 🔹 Max wait time (reduce if images appear faster)
MAX_WAIT_TIME = 40  # Seconds

# 🔹 Persistent User Profile Path
USER_PROFILE_DIR = os.path.join(os.getcwd(), "chrome_profile")
os.makedirs(USER_PROFILE_DIR, exist_ok=True)

def start_driver(headless=True):
    """Starts a Selenium WebDriver instance with specified headless mode."""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless")  # Headless mode initially
    
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(f"--user-data-dir={USER_PROFILE_DIR}")  # Persistent login
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def download_image_fx():
    """Automates Google ImageFX to generate and download images, handling login manually if required."""
    print(f"🚀 Starting automation with prompt: '{HARDCODED_PROMPT}'")

    driver = start_driver(headless=True)  # Start in headless mode

    try:
        driver.get("https://labs.google/fx/tools/image-fx/")
        print("✅ Navigated to Image FX website")

        # **Check if login is required**
        try:
            sign_in_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Sign in with Google')]"))
            )
            if sign_in_button.is_displayed():
                print("🔑 Login required. Restarting with UI...")
                driver.quit()

                # Re-run in visible mode for manual login
                driver = start_driver(headless=False)
                driver.get("https://labs.google/fx/tools/image-fx/")
                input("👤 Please log in manually, then press Enter to continue...")

                # Save the session and restart headless
                print("✅ Login successful. Restarting headless mode...")
                driver.quit()
                driver = start_driver(headless=True)
                driver.get("https://labs.google/fx/tools/image-fx/")
        except:
            print("✅ Already logged in, continuing.")

        # **Find and prepare input field**
        input_field_xpath = "//div[@role='textbox']"
        prompt_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, input_field_xpath))
        )
        prompt_input.click()
        time.sleep(0.5)
        prompt_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)  # Clear field

        # **Type the prompt (simulating human input)**
        for char in HARDCODED_PROMPT:
            prompt_input.send_keys(char)
            time.sleep(0.05)  # Simulated human typing

        print(f"✅ Prompt entered: {HARDCODED_PROMPT}")

        # **Find and click generate button**
        button_xpath = "//button[.//div[contains(text(),'Create')] or .//div[contains(text(),\"I'm feeling lucky\")]]"
        action_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, button_xpath))
        )
        action_button.click()
        print("🖱️ Clicked generate button.")

        # **Wait for images to appear (checks every 1s, up to MAX_WAIT_TIME)**
        start_time = time.time()
        image_elements = []
        while time.time() - start_time < MAX_WAIT_TIME:
            try:
                image_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'sc-43d791a1')]//img")
                if image_elements:
                    break  # Exit loop if images are found
            except:
                pass
            time.sleep(1)

        # **Download images and return file paths**
        file_paths = []
        if image_elements:
            os.makedirs("downloads", exist_ok=True)
            downloaded_urls = set()

            for idx, img in enumerate(image_elements):
                image_url = img.get_attribute("src")
                if image_url and image_url not in downloaded_urls:
                    downloaded_urls.add(image_url)
                    filename = f"downloads/{HARDCODED_PROMPT.replace(' ', '_')}_{idx+1}.jpg"
                    urllib.request.urlretrieve(image_url, filename)
                    file_paths.append(os.path.abspath(filename))
                    print(f"✅ Image {idx+1} saved: {filename}")
        
        driver.quit()  # Close browser after downloading

        return file_paths

    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        driver.save_screenshot("error_screenshot.png")
        print("🛠️ Error screenshot saved for debugging.")
        driver.quit()
        return []

# Run the function
if __name__ == "__main__":
    images = download_image_fx()
    print("\n📂 Downloaded image file paths:")
    for img in images:
        print(img)
